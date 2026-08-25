#!/usr/bin/env python3
"""
Resolve overlapping courtyards by RELOCATING parts, not by pushing them.

The first version of this pushed the smaller part of each overlapping pair out by the
overlap distance and re-measured. It never converged: each push created the next
collision one ring further out, and pairs oscillated - 60 rounds, same six overlaps. The
same thing happened again at 40 rounds on the 4x4 attempt.

Pushing is the wrong primitive on a board that is 82 parts deep on one side. This places
each offending part at the NEAREST POSITION WHERE IT COLLIDES WITH NOTHING, searched
outward from where it already is, which either finds a spot or reports that there is
none. It cannot oscillate, because a part only ever moves to a position that is already
known to be clear of everything.

Parts with an adjacency limit in design.ADJACENCY are held to it: a decoupling capacitor
that solves the geometry by moving 20 mm from its pin has not solved anything.

Usage: python3 tools/settle_overlaps.py [--apply] [--rounds N]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD  = 'NAVCORE-SoOP.kicad_pcb'
PINNED = {'L2', 'L5', 'U1', 'U2', 'U3', 'U4', 'U6', 'U7', 'U8', 'U18', 'U5', 'U9',
          'U10', 'U11', 'U12', 'U17', 'J1', 'J2', 'J3', 'J8', 'Y1'}
CLR    = 0.15
X0, X1, Y0, Y1 = 100.35, 144.65, 100.35, 145.65
MOUNT = design.BOARD["MOUNT"]
HOLES = [(122.5+sx*MOUNT/2, 123.0+sy*MOUNT/2) for sx in (-1, 1) for sy in (-1, 1)]


def crtyd(fp):
    bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
    return [bb.GetLeft()/1e6, bb.GetRight()/1e6, bb.GetTop()/1e6, bb.GetBottom()/1e6]


def main():
    apply = '--apply' in sys.argv
    rounds = int(sys.argv[sys.argv.index('--rounds')+1]) if '--rounds' in sys.argv else 40
    b = pcbnew.LoadBoard(BOARD)
    moved = 0

    for rnd in range(rounds):
        info = {}
        for f in b.GetFootprints():
            info[f.GetReference()] = (crtyd(f), f.IsFlipped(), f)
        refs = sorted(info)
        pairs = []
        for i, a in enumerate(refs):
            ca, fa, _ = info[a]
            for bb_ in refs[i+1:]:
                cb, fb, _ = info[bb_]
                if fa != fb: continue
                ox = min(ca[1], cb[1]) - max(ca[0], cb[0])
                oy = min(ca[3], cb[3]) - max(ca[2], cb[2])
                if ox > 0 and oy > 0: pairs.append((ox*oy, a, bb_))
        if not pairs:
            print(f"  round {rnd}: clear"); break
        pairs.sort(reverse=True)
        _a, ra, rb = pairs[0]
        cand = sorted([(abs((info[r][0][1]-info[r][0][0])*(info[r][0][3]-info[r][0][2])), r)
                       for r in (ra, rb) if r not in PINNED])
        if not cand:
            print(f"  round {rnd}: {ra}/{rb} overlap but both are pinned"); break
        _sz, ref = cand[0]
        cme, flip, fp = info[ref]
        w, h = cme[1]-cme[0], cme[3]-cme[2]
        px, py = fp.GetPosition().x/1e6, fp.GetPosition().y/1e6
        others = [(r,) + tuple(info[r][0]) for r in refs
                  if r != ref and info[r][1] == flip]
        # keep an adjacency-constrained part near its target
        lim = design.ADJACENCY.get(ref)
        reach = min(lim[2] * 2.0, 10.0) if lim else 8.0

        best = None
        step = 0.1
        n = int(reach/step)
        for j in range(-n, n+1):
            for i in range(-n, n+1):
                gx, gy = px + i*step, py + j*step
                d = math.hypot(gx-px, gy-py)
                if d > reach or (best and d >= best[0]): continue
                l, r, t, bm = gx-w/2-CLR, gx+w/2+CLR, gy-h/2-CLR, gy+h/2+CLR
                if l < X0 or r > X1 or t < Y0 or bm > Y1: continue
                if any(math.hypot(hx-gx, hy-gy) < 2.0+max(w, h)/2 for hx, hy in HOLES): continue
                if any(orr > l and ol < r and obm > t and ot < bm
                       for _rr, ol, orr, ot, obm in others): continue
                best = (d, gx, gy)
        if best is None:
            print(f"  round {rnd}: no clear spot for {ref} within {reach:.1f} mm"); break
        d, gx, gy = best
        fp.SetPosition(pcbnew.VECTOR2I(int(gx*1e6), int(gy*1e6)))
        moved += 1
        print(f"  round {rnd}: {ref} relocated {d:.2f} mm (was overlapping {ra if ref!=ra else rb})")
    else:
        print("  hit the round limit")

    print(f"  {moved} relocation(s)")
    if apply:
        pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(BOARD); print("  saved")
    sys.stdout.flush(); os._exit(0)


main()
