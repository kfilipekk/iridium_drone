#!/usr/bin/env bash
# Render the board the way the tracked pictures are made.
set -euo pipefail
cd "$(dirname "$0")/.."
BOARD=NAVCORE-SoOP.kicad_pcb
JLC=${JLC_LIB:-$(cd .. && pwd)/.libraries/jlc.pretty}
[ -d "$JLC/packages3d" ] || { echo "no packages3d under $JLC - set JLC_LIB" >&2; exit 1; }
export JLC_LIB="$JLC"

echo "=== 1. the tracked renders ==="
mkdir -p docs/img
render () {   # <output> <side> [extra kicad-cli args...]
  local out="$1" side="$2"; shift 2
  kicad-cli pcb render --output "$out" --side "$side" -D "JLC_LIB=$JLC" "$@" "$BOARD" \
    >/dev/null 2>&1
  echo "  $out"
}
# The two square plots: the whole board, straight on.
render docs/img/board-top.png    top    --width 1400 --height 1400 --quality high
render docs/img/board-bottom.png bottom --width 1400 --height 1400 --quality high
PRES=(--width 2016 --height 1512 --quality high --background opaque --floor)
render docs/img/render-top-flat.png    top    "${PRES[@]}"
render docs/img/render-bottom-flat.png bottom "${PRES[@]}"
render docs/img/render-iso.png         top    "${PRES[@]}" --rotate -45,0,45 --perspective
render docs/img/render-iso-bottom.png  bottom "${PRES[@]}" --rotate -45,0,45 --perspective

echo; echo "=== 2. does every body sit on its own footprint? ==="
# Measured in the exported GLB, which is what the viewer draws.
python3 tools/check_model_alignment.py | grep -v '^$' | tail -4

echo; echo "=== 3. did any parts actually render? ==="
python3 - "$JLC" <<'PY'
import os, sys
sys.path.insert(0, 'tools')
import pcbnew
JLC = sys.argv[1]
board = pcbnew.LoadBoard('NAVCORE-SoOP.kicad_pcb')
present = missing = 0
for fp in board.GetFootprints():
    fid = fp.GetFPIDAsString()
    if 'TestPoint' in fid or 'Fiducial' in fid:
        continue
    if any(os.path.exists(os.path.expandvars(m.m_Filename.replace('${JLC_LIB}', JLC)))
           for m in fp.Models()):
        present += 1
    else:
        missing += 1
        print(f"  no body: {fp.GetReference()} {fid}")
print(f"parts with a body that loads: {present}; without: {missing}")
sys.exit(1 if missing else 0)
PY
