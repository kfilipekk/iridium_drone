#!/usr/bin/env python3
"""Split an exposed thermal pad into a paste aperture array instead of one solid opening.

Usage:
    python3 tools/windowpane_paste.py --scan             find pads that need it
    python3 tools/windowpane_paste.py U13 29 [--apply]   treat one
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD = 'NAVCORE-SoOP.kicad_pcb'
GAP = 0.40
BIG_PAD_MM2 = 6.0
EXPOSED_MM2 = 4.0     # what counts as a thermal slug worth windowpaning
MIN_PADS_FOR_SLUG = 5 # below this a big pad is a termination, not a slug - see scan()


def scan(b):
    """Every SMD pad big enough to be a thermal slug, and whether it still carries a solid
    aperture. Exists so the tool cannot go on pointing at a deleted part.
    """
    hits = []
    for fp in b.GetFootprints():
        pads = list(fp.Pads())
        for pad in pads:
            sz = pad.GetSize()
            area = pcbnew.ToMM(sz.x) * pcbnew.ToMM(sz.y)
            if area < EXPOSED_MM2 or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            lay = pcbnew.B_Paste if fp.IsFlipped() else pcbnew.F_Paste
            slug = len(pads) >= MIN_PADS_FOR_SLUG
            hits.append((fp.GetReference(), pad.GetNumber(), area,
                         pad.IsOnLayer(lay), slug, len(pads)))
    return hits


def main():
    apply = '--apply' in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    if '--scan' in sys.argv:
        print(f"{'ref':6} {'pad':4} {'area':>8} {'pads':>5}  verdict")
        need = 0
        for ref, pn, area, solid, slug, npads in scan(b):
            if not slug:
                verdict = "termination on a 2-pad part - LEAVE ALONE"
            elif solid:
                verdict = "THERMAL SLUG, solid 100% aperture - NEEDS WINDOWPANING"
                need += 1
            else:
                verdict = "thermal slug, already windowpaned"
            print(f"{ref:6} {pn:4} {area:7.2f}mm2 {npads:5}  {verdict}")
        print(f"\n{need} pad(s) need windowpaning")
        return 1 if need else 0
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        print("usage: windowpane_paste.py <REF> <PAD> [--apply]   (or --scan)")
        return 2
    REF, PAD = args
    fp = b.FindFootprintByReference(REF)
    if fp is None:
        print(f"{REF} is not on the board")
        return 1
    pad = next((p for p in fp.Pads() if p.GetNumber() == PAD), None)
    if pad is None:
        print(f"{REF}.{PAD} not found")
        return 1

    paste_layer = pcbnew.B_Paste if fp.IsFlipped() else pcbnew.F_Paste
    if not pad.IsOnLayer(paste_layer):
        print(f"{REF}.{PAD} already has no paste on its own layer - looks done")
        return 0

    sz = pad.GetSize()
    w_mm, h_mm = pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)
    n = 3 if w_mm * h_mm >= BIG_PAD_MM2 else 2
    aw = (w_mm - (n - 1) * GAP) / n
    ah = (h_mm - (n - 1) * GAP) / n
    cov = n * n * aw * ah / (w_mm * h_mm) * 100
    c = pad.GetPosition()
    print(f"{REF}.{PAD}  {w_mm:.2f} x {h_mm:.2f} mm = {w_mm*h_mm:.2f} mm2, "
          f"one 100% aperture")
    print(f"  -> {n}x{n} of {aw:.2f} x {ah:.2f} mm on "
          f"{b.GetLayerName(paste_layer)}, {GAP:.2f} mm gaps = {cov:.1f}% coverage "
          f"(IPC-7093: 50-80%)")
    if not 50.0 <= cov <= 80.0:
        print(f"  REFUSING: {cov:.1f}% is outside IPC-7093's 50-80% band")
        return 1

    if not apply:
        print("\ndry run - pass --apply")
        return 0

    ls = pad.GetLayerSet()
    ls.removeLayer(paste_layer)
    pad.SetLayerSet(ls)

    off = [(i - (n - 1) / 2.0) for i in range(n)]
    for ix in off:
        for iy in off:
            cx = c.x + pcbnew.FromMM(ix * (aw + GAP))
            cy = c.y + pcbnew.FromMM(iy * (ah + GAP))
            s = pcbnew.PCB_SHAPE(fp)
            s.SetShape(pcbnew.SHAPE_T_RECT)
            s.SetStart(pcbnew.VECTOR2I(cx - pcbnew.FromMM(aw / 2),
                                       cy - pcbnew.FromMM(ah / 2)))
            s.SetEnd(pcbnew.VECTOR2I(cx + pcbnew.FromMM(aw / 2),
                                     cy + pcbnew.FromMM(ah / 2)))
            s.SetLayer(paste_layer)
            s.SetFilled(True)
            s.SetWidth(0)
            fp.Add(s)

    b.Save(BOARD)
    print("saved - now diff the B_Paste gerber; nothing else may change")
    return 0


if __name__ == '__main__':
    sys.exit(main())
