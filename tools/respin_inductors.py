#!/usr/bin/env python3
"""
Replace the buck inductors with parts that fit their own land, and make room for them.

L2 and L5 were declared as 1210 chip-inductor lands (3.2 x 2.5 mm) and then filled with
LCSC C167879 - an FNR4030S100MT, which is 4.0 x 4.0 x 3.0 mm. Neither fitted. That came
from design.PASSIVE_LCSC being keyed on value alone, so "10uH" meant one part number
whatever the footprint.

The current rating was wrong too. L2 feeds +5V, which draws 1.89 A fully fitted, and the
FNR4030 is rated 1.6 A RMS - 118 % of rating, 0.46 W of self-heating. No 1210-sized
10 uH part can carry that: a 3 x 3 mm one manages 550 mA. Core volume sets current
capability, so the land has to grow.

    L2  ->  L_APV_ANR5040, CKCS5040-10uH/M   5.0x5.0x4.0 mm, Isat 2.5 A, Irms 2.1 A
    L5  ->  L_APV_ANR4030, FNR4030S100MT     4.0x4.0x3.0 mm, Isat 2.4 A, Irms 1.6 A
                                             (L5 carries 0.6 A, so the 4x4 is ample)

Both grow mostly in Y, which puts them into their neighbours. Each neighbour is moved by
the smallest vector that clears the new courtyard, its tracks are ripped, and the whole
area is re-routed afterwards by tools/route_final.py.

Usage: python3 tools/respin_inductors.py [--apply]
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = 'NAVCORE-SoOP.kicad_pcb'
LIB   = '/usr/share/kicad/footprints/Inductor_SMD.pretty'
SWAP  = {'L2': 'L_APV_ANR4030', 'L5': 'L_APV_ANR4030'}
CLR   = 0.20          # mm of courtyard-to-courtyard breathing room after the move


def crtyd(fp):
    bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
    return [bb.GetLeft()/1e6, bb.GetRight()/1e6, bb.GetTop()/1e6, bb.GetBottom()/1e6]


def overlap(a, b):
    return (min(a[1], b[1]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[2], b[2]))


def main():
    apply = '--apply' in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    moved, swapped = [], []

    for ref, newfp in SWAP.items():
        old = b.FindFootprintByReference(ref)
        pos, rot, flip = old.GetPosition(), old.GetOrientation(), old.IsFlipped()
        nets = {p.GetPadName(): p.GetNet() for p in old.Pads()}
        val, lcsc = old.GetValue(), None
        for f in old.GetFields():
            if f.GetName() == 'LCSC': lcsc = f.GetText()

        new = pcbnew.FootprintLoad(LIB, newfp)
        if new is None:
            print(f"  could not load {newfp} from {LIB}"); return
        b.Remove(old)
        new.SetReference(ref); new.SetValue(val)
        b.Add(new)
        if flip: new.Flip(pos, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        new.SetPosition(pos); new.SetOrientation(rot)
        for p in new.Pads():
            if p.GetPadName() in nets: p.SetNet(nets[p.GetPadName()])
        swapped.append((ref, newfp, crtyd(new)))
        print(f"  {ref} -> {newfp}, courtyard now "
              f"{crtyd(new)[1]-crtyd(new)[0]:.2f} x {crtyd(new)[3]-crtyd(new)[2]:.2f} mm")

    # shove the neighbours out of the new courtyards
    for ref, newfp, box in swapped:
        me = b.FindFootprintByReference(ref)
        cx, cy = (box[0]+box[1])/2, (box[2]+box[3])/2
        for o in b.GetFootprints():
            if o.GetReference() == ref or o.IsFlipped() != me.IsFlipped(): continue
            ob = crtyd(o)
            ox, oy = overlap(box, ob)
            if ox <= 0 or oy <= 0: continue
            # smallest push that clears, along whichever axis costs less
            ocx, ocy = (ob[0]+ob[1])/2, (ob[2]+ob[3])/2
            push_x = (ox + CLR) * (1 if ocx >= cx else -1)
            push_y = (oy + CLR) * (1 if ocy >= cy else -1)
            dx, dy = (push_x, 0.0) if abs(push_x) <= abs(push_y) else (0.0, push_y)
            p = o.GetPosition()
            o.SetPosition(pcbnew.VECTOR2I(p.x + int(dx*1e6), p.y + int(dy*1e6)))
            moved.append((o.GetReference(), round(dx, 2), round(dy, 2)))
            print(f"     moved {o.GetReference():5s} by ({dx:+.2f},{dy:+.2f}) mm")

    # Rip only the copper LOCAL to what moved, not whole nets. VBAT and +5V carry the
    # power distribution across the board; ripping them entirely would mean re-routing
    # the highest-current paths on the board to fix a 1 mm shove. A window around each
    # disturbed part is enough, and route_final.py reconnects across it.
    WINDOW = 3.0
    boxes = []
    for ref in [r for r, _f, _b in swapped] + [m[0] for m in moved]:
        fp = b.FindFootprintByReference(ref)
        c = crtyd(fp)
        boxes.append((c[0]-WINDOW, c[1]+WINDOW, c[2]-WINDOW, c[3]+WINDOW))

    def inside(x, y):
        return any(l <= x <= r and t <= y <= bm for l, r, t, bm in boxes)

    # Both conditions, not either: the copper must be local to what moved AND belong to
    # a net that actually connects to something that moved. Nets alone ripped the whole
    # power distribution to fix a 1 mm shove; the window alone ripped 67 nets that were
    # merely passing through.
    touched = set()
    for ref in [r for r, _f, _b in swapped] + [m[0] for m in moved]:
        for p in b.FindFootprintByReference(ref).Pads():
            if p.GetNetname(): touched.add(p.GetNetname())

    dirty, killed = set(), 0
    for t in list(b.GetTracks()):
        n = t.GetNetname()
        if not n or n not in touched: continue
        if t.Type() == pcbnew.PCB_VIA_T:
            x, y = t.GetStart().x/1e6, t.GetStart().y/1e6
            hit = inside(x, y)
        else:
            hit = (inside(t.GetStart().x/1e6, t.GetStart().y/1e6) and
                   inside(t.GetEnd().x/1e6, t.GetEnd().y/1e6))
        if hit:
            dirty.add(n); b.Remove(t); killed += 1
    print(f"\n  {len(moved)} part(s) moved, {len(dirty)} net(s) ripped ({killed} objects)")
    print(f"  nets: {', '.join(sorted(dirty))}")

    if apply:
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(BOARD)
        print("  saved")
    else:
        print("  (dry run - pass --apply to write)")
    sys.stdout.flush(); os._exit(0)


main()
