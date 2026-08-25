#!/usr/bin/env python3
"""
Split U6's exposed pad into a paste aperture array instead of one solid opening.

U6 (PMW3901 optical flow) has the ONLY exposed pad on this board - 2.40 x 1.90 mm,
4.56 mm2 - and it carried a single 100% paste aperture. An earlier plan claimed U1, U2
and U3 needed the same treatment; checking every pad on the board showed otherwise. U1 is
LQFP-100 with no exposed pad, U2/U3 are LGA-14 with none, U8/U18/U11 are plain SOIC-8 and
U9/U10 are SOT. One pad, not four.

Why it matters: a single aperture that large deposits enough paste for the part to float
on it during reflow, and traps outgassing under the centre where it becomes a void.
IPC-7093 puts thermal-pad coverage at 50-80%; an array vents through the gaps and lands
the part flat. JLCPCB cuts its stencil from the paste gerber, so this is a real change to
what gets built, not a drawing convention.

This is a PASTE-ONLY change: B.Paste is removed from the pad's layer set and replaced by
four filled rectangles on B.Paste. No copper, no mask, no netlist. Verify by diffing
fab/gerbers/*B_Paste.gbr before and after - nothing else in the gerber set may move.

Geometry: 2x2, 0.40 mm gaps.
    aperture 1.00 x 0.75 mm, 4 x 0.75 mm2 = 3.00 mm2 of 4.56 = 65.8% coverage.

The array is symmetric about the pad centre, so U6's 180 degree rotation does not change
it. Shapes are added as footprint children at absolute coordinates; that is correct as
long as U6 is not subsequently moved, and the board is final.

Usage: python3 tools/windowpane_paste.py [--apply]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD = 'NAVCORE-SoOP.kicad_pcb'
REF, PAD = 'U6', '29'
GAP = 0.40


def main():
    apply = '--apply' in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    fp = b.FindFootprintByReference(REF)
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
    aw, ah = (w_mm - GAP) / 2, (h_mm - GAP) / 2
    cov = 4 * aw * ah / (w_mm * h_mm) * 100
    c = pad.GetPosition()
    print(f"{REF}.{PAD}  {w_mm:.2f} x {h_mm:.2f} mm = {w_mm*h_mm:.2f} mm2, "
          f"one 100% aperture")
    print(f"  -> 4 x {aw:.2f} x {ah:.2f} mm on {b.GetLayerName(paste_layer)}, "
          f"{GAP:.2f} mm gaps = {cov:.1f}% coverage")

    if not apply:
        print("\ndry run - pass --apply")
        return 0

    ls = pad.GetLayerSet()
    ls.removeLayer(paste_layer)
    pad.SetLayerSet(ls)

    for sx in (-1, 1):
        for sy in (-1, 1):
            cx = c.x + sx * pcbnew.FromMM((aw + GAP) / 2)
            cy = c.y + sy * pcbnew.FromMM((ah + GAP) / 2)
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
