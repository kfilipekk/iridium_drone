#!/usr/bin/env bash
# Start ArduCopter SITL with THIS BOARD's defaults.parm, run the GNSS-denied scenarios,
# and report position error against simulator truth.
#
# The board's own defaults are loaded on top of the SITL copter defaults, so what is
# being tested is the parameter set that ships in ROMFS - not a hand-tuned variant.
#
# SITL IS RESTARTED FOR EVERY SCENARIO. Two reasons, both learned the hard way:
#   * its TCP port accepts a single client, so a second scenario reconnecting to a live
#     SITL simply gets no heartbeat;
#   * the previous scenario leaves the aircraft airborne or landing, and that state would
#     leak into the next one's measurements.
set -uo pipefail

# RUN FROM AN IMMUTABLE SNAPSHOT.
#
# bash reads a script from disk BY BYTE OFFSET as it executes, so editing the file while
# it is running makes the shell resume mid-token. That happened on 2026-09-02: a --repeat
# feature was added to this file during a 15-scenario run, and the run ended in
# "TAG: unbound variable" and "Bake: No such file or directory" AFTER all 15 scenarios had
# completed - losing the summary block for a 50-minute run whose measurements were all
# perfectly good. A suite that takes an hour WILL be edited while it runs; making that
# safe is cheaper than remembering not to.
if [ -z "${NAVCORE_SNAPSHOT:-}" ]; then
  _here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _snap="$(mktemp -t navcore-run-scenarios.XXXXXX.sh)"
  cp "$_here/$(basename "${BASH_SOURCE[0]}")" "$_snap"
  # The snapshot lives in /tmp, so pass the real location through rather than letting
  # dirname resolve to the temp directory.
  NAVCORE_SNAPSHOT="$_here" exec bash "$_snap" "$@"
fi
# Best effort: the snapshot is small and /tmp is cleaned, but do not leave litter.
trap 'rm -f "$0" 2>/dev/null' EXIT

HERE="$NAVCORE_SNAPSHOT"
REPO="$(dirname "$HERE")"
AP="${AP_DIR:-$HOME/.cache/navcore/ardupilot}"
# The venv moved out of /tmp - it was being wiped between sessions, which is also how
# an earlier board backup was lost. tools/build_firmware.sh creates it here.
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
    # --repeat N: run each scenario N times and report how often it DIVERGED.
    #
    # This exists because the headline result of this suite is a coin flip, and a single
    # run cannot express it. soop_dropout diverged on 3 of 6 runs and soop_gpsinput on 1
    # of 6, with the outcome bimodal - bounded runs top out at 79.6 m, diverged runs start
    # at 216.7 m, nothing in between. A single run reports one side of that coin and looks
    # authoritative. What is actually worth gating is the RATE.
    #
    # It cannot be done by sweeping --seed: --seed defaults to 1 and seeds only the
    # DopplerErrorModel RNG, while SITL itself gets no seed. Two runs at seed 1 gave
    # 52.53 and 270.29 m. So the repeats here are plain repeats, deliberately.
    --repeat)   REPEAT="$2";   shift 2;;
    --list)     "$PY" -u "$HERE/scenarios.py" --list; exit 0;;
    --params)   PARAMS_ONLY=1; shift;;
    *) echo "unknown option $1"; exit 2;;
  esac
done

mkdir -p "$OUT"
[ -x "$BIN" ]  || { echo "no SITL binary - build it with:  cd $AP && ./waf configure --board sitl && ./waf copter"; exit 1; }
[ -f "$BOARD" ]|| { echo "no $BOARD - run tools/gen_hwdef.py"; exit 1; }

# SITL rejects parameters its build has no driver for. Strip the hardware-only lines
# rather than letting them abort the load; what matters here is the nav configuration.
STRIPPED="$OUT/board-sitl.parm"
grep -vE '^(SERIAL[0-9]_|RNGFND[0-9]_ADDR|BRD_|NTF_LED_TYPES|SERVO13_)' "$BOARD" > "$STRIPPED"

# Kill SITL by PROCESS NAME, never by command line. `pkill -f <path>` and /proc/*/cmdline
# scans both match any shell whose own command line contains that path - including the one
# running this script, and including a caller that merely mentions it. That kills the
# caller; it happened three times in this project. No shell is ever named "arducopter".
stop_sitl() {
  pkill -x arducopter 2>/dev/null
  for _ in 1 2 3 4 5; do pgrep -x arducopter >/dev/null || break; sleep 1; done
  pkill -9 -x arducopter 2>/dev/null
  # Wait for the port to actually free. An orphan still holding 5760 makes the next SITL
  # fail to bind and die, and the harness then connects to the ORPHAN - which the next
  # teardown kills mid-scenario, presenting as an endless "EOF on TCP socket" spin.
  #
  # Check it PASSIVELY with ss. Probing by opening /dev/tcp actually connects, and SITL
  # accepts exactly one client - so the probe itself takes the slot and the real client
  # is then talking to a simulator that is about to drop it. That is a self-inflicted
  # version of the very bug this loop exists to prevent.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    ss -ltn 2>/dev/null | grep -q ':5760 ' || break
    sleep 1
  done
}
trap stop_sitl EXIT

# Stage the vendored Lua applets BEFORE anything boots SITL.
#
# SITL loads scripts from ./scripts in its WORKING DIRECTORY (real hardware uses
# APM/scripts/ on the SD card). This used to live inside the scenario loop, which meant
# --params exited before it ran and validated parameters against WHATEVER SCRIPT WAS LEFT
# IN THE WORK DIRECTORY from a previous run. Since the DR_* parameters are created BY the
# script, that made --params report the old script's defaults as the build's truth - and
# it did exactly that while the fault it was meant to catch was being fixed.
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
# SITL persists parameters to eeprom.bin in its WORKING DIRECTORY, and stored values
# override --defaults. A scenario that sets SIM_GPS1_ENABLE 0 to deny GPS therefore
# leaves every later run starting GPS-denied, so they never get a fix and fail to arm for
# a reason that has nothing to do with what they are testing. Results silently contaminate
# each other in run order.
#
# Run in a scratch directory and wipe the eeprom before every scenario, so each one starts
# from exactly the shipped defaults.
# SITL loads Lua scripts from ./scripts in its WORKING DIRECTORY (real hardware uses
# APM/scripts/ on the SD card), so stage the vendored applets in BOTH locations before
# every scenario. Without this the DR applet is absent and the deadreckon scenario
# measures nothing (SCR params load, script never runs).

for name in $NAMES; do
 for rep in $(seq 1 "$REPEAT"); do
  stop_sitl
  rm -f "$WORK/eeprom.bin"
  [ "$REPEAT" -gt 1 ] && echo "--- $name, run $rep of $REPEAT"
  TAG="$name"; [ "$REPEAT" -gt 1 ] && TAG="$name-r$rep"

  # Some parameters are @RebootRequired - GPS_TYPE2 and VISO_TYPE among them - so setting
  # them over MAVLink after startup never instantiates the backend. The failure is quiet:
  # the aircraft flies, the scenario runs, and there is simply no second GPS to fall back
  # to when GPS is denied. Bake them into the boot parameters instead.
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
