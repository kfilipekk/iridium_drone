#!/usr/bin/env bash
#render the board the way the tracked pictures are made
set -euo pipefail
cd "$(dirname "$0")/.."
BOARD=NAVCORE-SoOP.kicad_pcb
JLC=${JLC_LIB:-$(cd .. && pwd)/.libraries/jlc.pretty}
[ -d "$JLC/packages3d" ] || { echo "no packages3d under $JLC - set JLC_LIB" >&2; exit 1; }
export JLC_LIB="$JLC"

echo "=== 1. the tracked renders ==="
mkdir -p docs/img
render () {   #output> <side> [extra kicad-cli args...]
  local out="$1" side="$2"; shift 2
  kicad-cli pcb render --output "$out" --side "$side" -D "JLC_LIB=$JLC" "$@" "$BOARD" \
    >/dev/null 2>&1
  echo "  $out"
}
#the two square plots: the whole board, straight on
render docs/img/board-top.png    top    --width 1400 --height 1400 --quality high
render docs/img/board-bottom.png bottom --width 1400 --height 1400 --quality high
PRES=(--width 2016 --height 1512 --quality high --background opaque --floor)
render docs/img/render-top-flat.png    top    "${PRES[@]}"
render docs/img/render-bottom-flat.png bottom "${PRES[@]}"
render docs/img/render-iso.png         top    "${PRES[@]}" --rotate -45,0,45 --perspective
render docs/img/render-iso-bottom.png  bottom "${PRES[@]}" --rotate -45,0,45 --perspective

#the layout as the pcb editor shows it: every copper layer, the top silk and the outline
LAY=$(mktemp -d)
kicad-cli pcb export pdf --mode-separate --theme _builtin_default --drill-shape-opt 2 \
  --layers B.Cu,In4.Cu,In3.Cu,In2.Cu,In1.Cu,F.Cu,F.Silkscreen,Edge.Cuts -o "$LAY/" "$BOARD" \
  >/dev/null 2>&1
python3 - "$LAY" <<'PY'
import os, subprocess, sys
import pcbnew
from PIL import Image
lay = sys.argv[1]
bb = pcbnew.LoadBoard('NAVCORE-SoOP.kicad_pcb').GetBoardEdgesBoundingBox()
dpi = 760
px = lambda mm: round(mm * dpi / 25.4)
x0, y0 = bb.GetLeft() / 1e6 - 1.5, bb.GetTop() / 1e6 - 1.5
w, h = bb.GetWidth() / 1e6 + 3.0, bb.GetHeight() / 1e6 + 3.0
out = Image.new("RGBA", (px(w), px(h)), (0, 16, 35, 255))     #the editor's background
#bottom up, each layer see-through as the editor draws it
for name, a in (("B_Cu", .55), ("In4_Cu", .35), ("In3_Cu", .35), ("In2_Cu", .35),
                ("In1_Cu", .35), ("F_Cu", .7), ("F_Silkscreen", 1), ("Edge_Cuts", 1)):
    png = os.path.join(lay, name)
    subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-r", str(dpi),
                    "-x", str(px(x0)), "-y", str(px(y0)), "-W", str(px(w)), "-H", str(px(h)),
                    os.path.join(lay, f"NAVCORE-SoOP-{name}.pdf"), png], check=True)
    im = Image.open(png + ".png").convert("RGBA")
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    out = Image.alpha_composite(out, im)
out = out.convert("RGB")
out.resize((1400, round(1400 * out.height / out.width)), Image.LANCZOS).save("docs/img/layout.png")
PY
rm -rf "$LAY"
echo "  docs/img/layout.png"

python3 tools/gen_padmap.py

echo; echo "=== 2. does every body sit on its own footprint? ==="
#measured in the exported GLB, which is what the viewer draws
python3 tools/check_board.py model_alignment | grep -v '^$' | tail -4

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
    if 'TestPoint' in fid or 'Fiducial' in fid or fp.IsExcludedFromPosFiles():
        continue                   #bare copper: nothing is placed there to draw
    if any(os.path.exists(os.path.expandvars(m.m_Filename.replace('${JLC_LIB}', JLC)))
           for m in fp.Models()):
        present += 1
    else:
        missing += 1
        print(f"  no body: {fp.GetReference()} {fid}")
print(f"parts with a body that loads: {present}; without: {missing}")
sys.exit(1 if missing else 0)
PY
