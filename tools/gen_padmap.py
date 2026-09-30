#!/usr/bin/env python3
#draw docs/img/padmap.svg from the board: every solder pad and test point, where it is,
#Usage: python3 tools/gen_padmap.py [--check]
#--check  fail if docs/img/padmap.svg is not what the board gives
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import design

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb")
OUT = os.path.join(REPO, "docs", "img", "padmap.svg")
T = pcbnew.ToMM
K = 14.0                  #px per mm
PAD, GAP = 20, 40         #frame margin, gap between the two sides


def svg(board):
    eb = board.GetBoardEdgesBoundingBox()
    x0, y0 = T(eb.GetLeft()), T(eb.GetTop())
    w, h = T(eb.GetWidth()), T(eb.GetHeight())
    pads = []
    for fp in board.GetFootprints():
        if "TestPoint" not in fp.GetFPIDAsString():
            continue
        p = fp.GetPosition()
        pads.append((fp.GetReference(), fp.IsFlipped(), T(p.x) - x0, T(p.y) - y0,
                     design.PAD_LABELS.get(fp.GetReference(), "?")))
    W = 2 * w * K + 2 * PAD + GAP
    H = h * K + 2 * PAD + 60
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
           f'viewBox="0 0 {W:.0f} {H:.0f}">',
           f'<rect width="100%" height="100%" fill="#faf9f7"/>',
           f'<text x="{PAD}" y="26" font-family="monospace" font-size="16" font-weight="bold" '
           f'fill="#111">NAVCORE-SoOP pad map ({w:.1f} x {h:.1f} mm) - reference, then what '
           f'the silkscreen prints</text>']
    for i, (side, name) in enumerate(((False, "TOP, seen from above"),
                                      (True, "BOTTOM, seen from below"))):
        ox = PAD + i * (w * K + GAP)
        oy = PAD + 30
        out.append(f'<rect x="{ox}" y="{oy}" width="{w * K:.1f}" height="{h * K:.1f}" rx="8" '
                   f'fill="#0f3d2e" stroke="#08251c" stroke-width="2"/>')
        out.append(f'<text x="{ox}" y="{oy + h * K + 22:.1f}" font-family="monospace" '
                   f'font-size="13" fill="#333">{name}</text>')
        for ref, flipped, x, y, fn in sorted(pads):
            if flipped != side:
                continue
            px = ox + ((w - x) if side else x) * K
            py = oy + y * K
            out.append(f'<rect x="{px - 9:.1f}" y="{py - 9:.1f}" width="18" height="18" rx="3" '
                       f'fill="#f5c542" stroke="#222"/>')
            out.append(f'<text x="{px:.1f}" y="{py - 12:.1f}" font-family="monospace" '
                       f'font-size="9" text-anchor="middle" fill="#fff">{ref}</text>')
            out.append(f'<text x="{px:.1f}" y="{py + 4:.1f}" font-family="monospace" '
                       f'font-size="9" font-weight="bold" text-anchor="middle" fill="#111">{fn}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    text = svg(pcbnew.LoadBoard(BOARD))
    if "--check" in sys.argv:
        ok = os.path.exists(OUT) and open(OUT).read() == text
        print("docs/img/padmap.svg is current" if ok else
              "docs/img/padmap.svg is stale - run tools/gen_padmap.py")
        return 0 if ok else 1
    open(OUT, "w").write(text)
    print(f"wrote {os.path.relpath(OUT, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
