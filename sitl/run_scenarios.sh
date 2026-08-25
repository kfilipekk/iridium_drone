#!/usr/bin/env bash
set -uo pipefail

if [ -z "${NAVCORE_SNAPSHOT:-}" ]; then
  _here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _snap="$(mktemp -t navcore-run-scenarios.XXXXXX.sh)"
  cp "$_here/$(basename "${BASH_SOURCE[0]}")" "$_snap"
  NAVCORE_SNAPSHOT="$_here" exec bash "$_snap" "$@"
fi
# Best effort: the snapshot is small and /tmp is cleaned, but do not leave litter.
trap 'rm -f "$0" 2>/dev/null' EXIT

HERE="$NAVCORE_SNAPSHOT"
REPO="$(dirname "$HERE")"
AP="${AP_DIR:-$HOME/.cache/navcore/ardupilot}"
PY="${PY:-$HOME/.cache/navcore/apvenv/bin/python3}"
OUT="${OUT:-/tmp/nav/sitl}"
BIN="$AP/build/sitl/bin/arducopter"
BASE="$AP/Tools/autotest/default_params/copter.parm"
BOARD="$REPO/firmware/NAVCORE_SoOP/defaults.parm"

DURATION=110
ONLY=""
RATE=""
TRACK=""
SEED=""
REPEAT=1
PARAMS_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --duration) DURATION="$2"; shift 2;;
    --only)     ONLY="$2";     shift 2;;
    --rate)     RATE="$2";     shift 2;;
    --track)    TRACK=1;       shift;;
    --seed)     SEED="$2";     shift 2;;
    # Repeat N: run each scenario N times and report how often it DIVERGED.
    --repeat)   REPEAT="$2";   shift 2;;
    --list)     "$PY" -u "$HERE/scenarios.py" --list; exit 0;;
    --params)   PARAMS_ONLY=1; shift;;
    *) echo "unknown option $1"; exit 2;;
  esac
done

mkdir -p "$OUT"
[ -x "$BIN" ]  || { echo "no SITL binary - build it with:  cd $AP && ./waf configure --board sitl && ./waf copter"; exit 1; }
[ -f "$BOARD" ]|| { echo "no $BOARD - run tools/gen_hwdef.py"; exit 1; }

# SITL rejects parameters its build has no driver for.
STRIPPED="$OUT/board-sitl.parm"
grep -vE '^(SERIAL[0-9]_|RNGFND[0-9]_ADDR|BRD_|NTF_LED_TYPES|SERVO13_)' "$BOARD" > "$STRIPPED"

# Kill SITL by process name, never by command line.
stop_sitl() {
  pkill -x arducopter 2>/dev/null
  for _ in 1 2 3 4 5; do pgrep -x arducopter >/dev/null || break; sleep 1; done
  pkill -9 -x arducopter 2>/dev/null
  # Wait for the port to actually free.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    ss -ltn 2>/dev/null | grep -q ':5760 ' || break
    sleep 1
  done
}
trap stop_sitl EXIT

# Stage the vendored Lua applets before anything boots SITL.
WORK_STAGE() {
  local dst="$1"
  local src="$REPO/firmware/NAVCORE_SoOP/sdcard/APM/scripts"
  mkdir -p "$dst/APM/scripts" "$dst/scripts"
  if [ -d "$src" ]; then
    cp -f "$src"/*.lua "$dst/APM/scripts/" 2>/dev/null || true
    cp -f "$src"/*.lua "$dst/scripts/" 2>/dev/null || true
  fi
}
WORK="$OUT/work"
mkdir -p "$WORK"
WORK_STAGE "$WORK"

if [ "$PARAMS_ONLY" = 1 ]; then
  # Boot a stock build and ask it, one parameter at a time, what it actually has.
  stop_sitl
  mkdir -p "$OUT/work"; rm -f "$OUT/work/eeprom.bin"
  WORK_STAGE "$OUT/work"
  ( cd "$OUT/work" && "$BIN" --model quad --home 51.5074,-0.1278,20,0 \
        --defaults "$BASE,$STRIPPED" --sysid 1 > "$OUT/sitl-params.log" 2>&1 ) &
  for _ in $(seq 1 30); do ss -ltn 2>/dev/null | grep -q ':5760 ' && break; sleep 1; done
  "$PY" -u "$HERE/check_params_live.py"
  exit $?
fi

if [ -n "$ONLY" ]; then
  NAMES="$ONLY"
else
  NAMES=$("$PY" -u "$HERE/scenarios.py" --list | awk '{print $1}')
fi

RC=0
PARTS=""

for name in $NAMES; do
 for rep in $(seq 1 "$REPEAT"); do
  stop_sitl
  rm -f "$WORK/eeprom.bin"
  [ "$REPEAT" -gt 1 ] && echo "--- $name, run $rep of $REPEAT"
  TAG="$name"; [ "$REPEAT" -gt 1 ] && TAG="$name-r$rep"

  EXTRA="$OUT/startup-$name.parm"
  "$PY" -u "$HERE/scenarios.py" --startup-params "$name" > "$EXTRA" 2>/dev/null || : > "$EXTRA"
  [ -s "$EXTRA" ] && echo "  boot params for $name: $(tr '\n' ' ' < "$EXTRA")"

  ( cd "$WORK" && "$BIN" --model quad --home 51.5074,-0.1278,20,0 \
         --defaults "$BASE,$STRIPPED,$EXTRA" --sysid 1 > "$OUT/sitl-$TAG.log" 2>&1 ) &
  sleep 8
  pgrep -x arducopter >/dev/null || { echo "SITL died starting $name:"; tail -20 "$OUT/sitl-$TAG.log"; RC=1; continue; }
  ss -ltn 2>/dev/null | grep -q ':5760 ' || { echo "SITL is not listening on 5760 for $name"; tail -20 "$OUT/sitl-$TAG.log"; RC=1; continue; }
  "$PY" -u "$HERE/scenarios.py" --only "$name" --duration "$DURATION" \
        ${RATE:+--rate "$RATE"} ${SEED:+--seed "$SEED"} \
        ${TRACK:+--track "$OUT/track-$TAG-$SEED.csv"} \
        --report "$OUT/part-$TAG.json" || RC=1
  PARTS="$PARTS $OUT/part-$TAG.json"
 done
done
stop_sitl

"$PY" - "$OUT/report.json" $PARTS <<'PYEOF'
import json, sys
out, parts = sys.argv[1], sys.argv[2:]
merged = []
for p in parts:
    try:    merged += json.load(open(p))
    except Exception as e: merged.append({"scenario": p, "error": f"unreadable: {e}"})
json.dump(merged, open(out, "w"), indent=2)
print("\n===== summary =====")
for r in merged:
    print(f"  {r['scenario']:16} {r.get('verdict') or r.get('error')}")

# DIVERGENCE RATE. Only meaningful with repeats, and only for scenarios that declare a
# measured boundary (diverges_above), so it stays silent on a normal single-pass run
# rather than printing a 0/1 or 1/1 "rate" that invites over-reading.
import collections
runs = collections.defaultdict(list)
for r in merged:
    if "diverged" in r:
        runs[r["scenario"]].append(bool(r["diverged"]))
rates = {k: v for k, v in runs.items() if len(v) > 1}
if rates:
    print("\n===== divergence rate =====")
    print("  a run DIVERGED when p95 exceeded that scenario's measured boundary;")
    print("  the outcome is bimodal, so this rate is the result - not any single p95")
    for k, v in sorted(rates.items()):
        n, d = len(v), sum(v)
        print(f"  {k:16} {d}/{n} diverged  ({100.0*d/n:.0f}%)")
print(f"\nreport: {out}")
PYEOF
exit $RC
