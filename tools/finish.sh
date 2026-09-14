#!/usr/bin/env bash
# Take a freerouting .ses all the way to verified fab output.
#
# Order matters here and each step earned its place:
#   1. fr_apply    import the SES, widen the traces freerouting necked, then fanout
#                  and stitch - freerouting never ties the pours to the planes.
#   2. stitch      orphan pour islands the blind 1.8 mm stitching grid could not land in.
#   3. fanout_hard pads still stranded over their own pour: 72 angles out to 3 mm,
#                  DRC-verified per pad with rollback.
#   4. verify      DRC, ERC, plane integrity, then the production gate.
#   5. outputs     gerbers, drill, BOM, CPL, render, hand-routing worklist.
#
# DANGER: this runs the ROUTING chain. It is for taking a fresh freerouting result to
# fab output, not for touching a board that is already finished. Run on the current
# board and it will rip up and re-lay copper that took an entire session to get right.
# It refuses to run when the board is already fully routed - pass --force if you really
# mean it, and bank the board first.
#
# Usage:  bash tools/finish.sh <out.ses> [--force]
set -euo pipefail
QUIET="${QUIET:-^$}"   # filter for noisy lines; default: suppress nothing
SES="${1:?usage: finish.sh <out.ses> [--force]}"
BOARD="NAVCORE-SoOP.kicad_pcb"

FORCE="${2:-}"
if [ "$FORCE" != "--force" ]; then
  mkdir -p /tmp/nav
  kicad-cli pcb drc --output /tmp/nav/finish_guard.rpt --severity-error "$BOARD" >/dev/null 2>&1 || true
  UN=$(grep -c '^\[unconnected_items\]' /tmp/nav/finish_guard.rpt || true)
  if [ "$UN" = "0" ]; then
    echo "REFUSING: $BOARD already has 0 unconnected items." >&2
    echo "finish.sh re-runs the routing chain and would rip up copper that is already" >&2
    echo "done. Bank the board, then pass --force if that is really what you want." >&2
    exit 1
  fi
  echo "board has $UN unconnected item(s) - proceeding"
fi

echo "=== 1. import the routing ==="
python3 tools/fr_apply.py "$BOARD" "$SES" 2>&1 | grep -viE "$QUIET" | tail -2

echo; echo "=== 2. stitch orphan pour islands ==="
python3 tools/stitch_islands.py --apply 2>&1 | grep -viE "$QUIET" | tail -2

echo; echo "=== 3. escape any pad still stranded over its plane ==="
python3 tools/fanout_hard.py --apply 2>&1 | grep -viE "$QUIET" | tail -1

echo; echo "=== 3b. clear any residual DRC violation ==="
python3 tools/fix_drc.py --apply 2>&1 | grep -viE "$QUIET" | tail -2

echo; echo "=== 3c. route what freerouting left, pair by pair ==="
python3 tools/route_remaining.py --apply 2>&1 | grep -viE "$QUIET" | tail -2

echo; echo "=== 3d. dissolve the ground islands ==="
# The routing chain above re-creates both B.Cu GND islands, and neither is fixable by
# routing: island A needs the VCC_RF corridor cut plus an In2 relink, island B needs C3
# 0.06 mm west. Both tools no-op when there is no island, and both revert themselves
# unless the island count AND the unconnected count improve, so they are safe to call
# here - but a rebuild of the placement can move the geometry they key on, in which case
# they exit 1 and say so rather than writing a broken board.
python3 tools/free_island_a.py --apply 2>&1 | grep -viE "$QUIET" | tail -3 \
  || echo "  free_island_a.py found no applicable corridor - re-measure before relying on it"
python3 tools/free_island_b.py --apply 2>&1 | grep -viE "$QUIET" | tail -3 \
  || echo "  free_island_b.py found no applicable fix - re-measure before relying on it"

echo; echo "=== 4. verify ==="
python3 tools/board_report.py "$BOARD" 2>&1 | grep -viE "$QUIET"

echo; echo "=== 5. fab outputs ==="
rm -rf fab/gerbers && mkdir -p fab/gerbers
kicad-cli pcb export gerbers --output fab/gerbers/ \
  --layers "F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" \
  --no-protel-ext "$BOARD" >/dev/null 2>&1 && echo "  gerbers ok"
kicad-cli pcb export drill --output fab/gerbers/ --format excellon \
  --drill-origin absolute --excellon-units mm --generate-map --map-format gerberx2 \
  "$BOARD" >/dev/null 2>&1 && echo "  drill ok"
python3 tools/gen_bom.py 2>&1 | grep -viE "$QUIET"
python3 tools/gen_worklist.py 2>&1 | grep -viE "$QUIET" | head -3

mkdir -p docs/img
for side in top bottom; do
  kicad-cli pcb render --output "docs/img/board-$side.png" --side "$side" \
    --width 1400 --height 1400 --quality high "$BOARD" >/dev/null 2>&1 \
    && echo "  rendered docs/img/board-$side.png"
done

echo; echo "=== 6. production gate ==="
python3 tools/preflight.py 2>&1 | grep -viE "$QUIET" | tail -20
