#!/usr/bin/env python3
"""
Move the buck inductors to the top side, onto lands that fit the parts.

L2 and L5 were 1210 chip lands (3.2 x 2.5 mm) holding a 4.0 x 4.0 x 3.0 mm part, and L2
was carrying 1.89 A on a 1.6 A RMS rating. The bottom side cannot absorb a bigger land -
82 of 115 parts are down there, a 5x5 collides with 7 neighbours, and an incremental
shove thrashed: 60 moves, same 6 overlaps.

The top side has room, and there is a second reason to go there: BOTH buck ICs (U8, U18)
are already on the top while their inductors are underneath, so the switching loop
already crosses the board through vias. Putting each inductor beside its own IC shortens
the loop as well as fixing the fit.

Placement is by NEAREST FREE POSITION, not by incremental pushing. Pushing is what
thrashed - each shove created the next collision, one ring further out. Here every part
that has to move is placed directly at the closest spot where it collides with nothing,
which either succeeds or reports that it cannot.

Usage: python3 tools/move_inductors_top.py [--apply]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = 'NAVCORE-SoOP.kicad_pcb'
LIB   = '/usr/share/kicad/footprints/Inductor_SMD.pretty'
# ref -> (new footprint, the IC it must stay beside)
PLAN  = {'L2': ('L_APV_ANR5040', 'U8'), 'L5': ('L_APV_ANR4030', 'U18')}
CLR   = 0.20
X0, X1, Y0, Y1 = 100.35, 144.65, 100.35, 145.65
MOUNT = design.BOARD["MOUNT"]
CX, CY = 122.5, 123.0
HOLES = [(CX+sx*MOUNT/2, CY+sy*MOUNT/2) for sx in (-1, 1) for sy in (-1, 1)]


def crtyd(fp):
    bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
    return [bb.GetLeft()/1e6, bb.GetRight()/1e6, bb.GetTop()/1e6, bb.GetBottom()/1e6]


def boxes_on(b, side_flipped, exclude=()):
    out = []
    for f in b.GetFootprints():
        if f.IsFlipped() != side_flipped or f.GetReference() in exclude: continue
        out.append((f.GetReference(),) + tuple(crtyd(f)))
    return out


def free_at(gx, gy, w, h, occupied):
    l, r, t, bm = gx-w/2-CLR, gx+w/2+CLR, gy-h/2-CLR, gy+h/2+CLR
    if l < X0 or r > X1 or t < Y0 or bm > Y1: return False
    for hx, hy in HOLES:
        if math.hypot(hx-gx, hy-gy) < 2.0 + max(w, h)/2: return False
    for _ref, ol, orr, ot, obm in occupied:
        if orr > l and ol < r and obm > t and ot < bm: return False
    return True


def nearest_free(w, h, near, occupied, step=0.25, reach=22.0):
    best = None
    n = int(reach/step)
    for j in range(-n, n+1):
        for i in range(-n, n+1):
            gx, gy = near[0]+i*step, near[1]+j*step
            d = math.hypot(gx-near[0], gy-near[1])
            if d > reach or (best and d >= best[0]): continue
            if free_at(gx, gy, w, h, occupied): best = (d, gx, gy)
    return best


def main():
    apply = '--apply' in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    placed = []

    for ref, (newfp, icref) in PLAN.items():
        old = b.FindFootprintByReference(ref)
        nets = {p.GetPadName(): p.GetNet() for p in old.Pads()}
        val = old.GetValue()
        b.Remove(old)
        new = pcbnew.FootprintLoad(LIB, newfp)
        if new is None:
            print(f"  cannot load {newfp}"); os._exit(1)
        new.SetReference(ref); new.SetValue(val)
        b.Add(new)                                   # TOP side: no Flip call at all
        for p in new.Pads():
            if p.GetPadName() in nets: p.SetNet(nets[p.GetPadName()])
        c = crtyd(new)
        w, h = c[1]-c[0], c[3]-c[2]
        ic = b.FindFootprintByReference(icref)
        icp = (ic.GetPosition().x/1e6, ic.GetPosition().y/1e6)
        occ = boxes_on(b, False, exclude={ref} | {r for r, _f, _i in
                                                  [(k,)+v for k, v in PLAN.items()]})
        spot = nearest_free(w, h, icp, occ)
        if spot is None:
            print(f"  {ref}: no free {w:.2f} x {h:.2f} mm spot within reach of {icref}")
            os._exit(1)
        d, gx, gy = spot
        new.SetPosition(pcbnew.VECTOR2I(int(gx*1e6), int(gy*1e6)))
        placed.append((ref, newfp, gx, gy, d, icref))
        print(f"  {ref} -> {newfp} on the TOP at ({gx:.2f},{gy:.2f}), "
              f"{d:.2f} mm from {icref}, land {w:.2f} x {h:.2f} mm")

    # rip local copper on the nets that moved
    dirty, killed = set(), 0
    touched = set()
    for ref, _f, _x, _y, _d, _ic in placed:
        for p in b.FindFootprintByReference(ref).Pads():
            if p.GetNetname(): touched.add(p.GetNetname())
    for t in list(b.GetTracks()):
        if t.GetNetname() in touched:
            dirty.add(t.GetNetname()); b.Remove(t); killed += 1
    print(f"\n  ripped {killed} objects on {len(dirty)} net(s): {', '.join(sorted(dirty))}")

    if apply:
        pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(BOARD); print("  saved")
    else:
        print("  (dry run)")
    sys.stdout.flush(); os._exit(0)


main()
