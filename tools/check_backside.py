#!/usr/bin/env python3
"""Does anything with a pin through the board land under a part on the other side?

Usage: python3 tools/check_backside.py [--board PATH]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD = "NAVCORE-SoOP.kicad_pcb"
T = pcbnew.ToMM
CLEAR = 0.20      # mm between a hole and an opposite-side body


def body_box(fp):
    """Plan-view box of the part itself: Fab outline, else silk outline, plus its pads."""
    back = fp.IsFlipped()
    fab = pcbnew.B_Fab if back else pcbnew.F_Fab
    silk = pcbnew.B_SilkS if back else pcbnew.F_SilkS
    box = None
    for layer in (fab, silk):
        for g in fp.GraphicalItems():
            if g.GetLayer() != layer or g.Type() in (pcbnew.PCB_TEXT_T, pcbnew.PCB_FIELD_T):
                continue
            bb = g.GetBoundingBox()
            if box is None:
                box = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
            else:
                box.Merge(bb)
        if box is not None:
            break
    for p in fp.Pads():
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            continue    # its own holes are not its body
        bb = p.GetBoundingBox()
        if box is None:
            box = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
        else:
            box.Merge(bb)
    return box


def main():
    board = sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv else BOARD
    b = pcbnew.LoadBoard(board)
    fps = list(b.GetFootprints())
    bodies = {fp.GetReference(): body_box(fp) for fp in fps}
    fails, notes, n_holes = [], [], 0
    for fp in fps:
        for p in fp.Pads():
            if p.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            n_holes += 1
            pb = p.GetBoundingBox()          # the ring: for the courtyard note
            c, d = p.GetPosition(), p.GetDrillSize()
            if p.GetOrientationDegrees() % 180 != 0:
                d = pcbnew.VECTOR2I(d.y, d.x)
            hole = pcbnew.BOX2I(pcbnew.VECTOR2I(c.x - d.x // 2, c.y - d.y // 2), d)
            for o in fps:
                if o is fp or o.IsFlipped() == fp.IsFlipped():
                    continue
                where = f"{fp.GetReference()} pad {p.GetNumber() or '(hole)'} at " \
                        f"({T(p.GetPosition().x):.2f}, {T(p.GetPosition().y):.2f})"
                body = bodies[o.GetReference()]
                if body is not None:
                    g = pcbnew.BOX2I(body.GetOrigin(), body.GetSize())
                    g.Inflate(pcbnew.FromMM(CLEAR))
                    if g.Intersects(hole):
                        fails.append(f"{where} is under {o.GetReference()} ({o.GetValue()}) "
                                     f"on the other side")
                        continue
                    if g.Intersects(pb):
                        notes.append(f"{where}: its ring is within {CLEAR} mm of "
                                     f"{o.GetReference()}'s pads (the hole itself is clear)")
                        continue
                crt = o.GetCourtyard(pcbnew.B_CrtYd if o.IsFlipped() else pcbnew.F_CrtYd)
                if crt.OutlineCount() and crt.Collide(pcbnew.SHAPE_RECT(pb)):
                    notes.append(f"{where} is inside {o.GetReference()}'s courtyard margin "
                                 f"(body clear by >= {CLEAR} mm)")
    print(f"{n_holes} through-holes checked against every part on the other side")
    for n in notes:
        print(f"  note {n}")
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} pin(s)/hole(s) land under a part on the other side")
        return 1
    print("no pin or hole lands under a part on the other side")
    return 0


if __name__ == "__main__":
    sys.exit(main())
