#!/usr/bin/env python3
"""
Move parts to satisfy the adjacency rules in design.ADJACENCY.

The packer places by size and treats adjacency as a preference, so it best-efforts
the table and gives up: 26 rules were unmet, including the 5 V buck's catch diode
14.6 mm from the switch node and decoupling 7-8 mm from the pin it serves. Those are
switching-loop and decoupling defects, not cosmetic ones.

This runs on a STRIPPED board on purpose. With no copper down, a part only has to
avoid other footprints, so the search is both far freer and far simpler - and the
routing is going to be redone from scratch afterwards regardless. Running it against
a routed board would mean ripping and re-routing around every move.

Worst violation first, since the big movers are the ones that need the free space.

Usage:  python3 tools/fix_adjacency.py <board.kicad_pcb> [--apply]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design, route

MM = pcbnew.FromMM
B  = design.BOARD
GAP = 0.35         # courtyard breathing room between footprint bodies
HOLE_KEEP = 2.9    # keep pads clear of an M3 cap head (2.75 mm) with margin

CX = B["X0"] + B["W"]/2
CY = B["Y0"] + B["H"]/2
HOLES = [(CX + dx, CY + dy)
         for dx in (-B["MOUNT"]/2, B["MOUNT"]/2)
         for dy in (-B["MOUNT"]/2, B["MOUNT"]/2)]


def clears_holes(x0, y0, x1, y1):
    """No part of the box may sit under a mounting screw head."""
    for hx, hy in HOLES:
        dx = max(x0 - hx, 0, hx - x1)
        dy = max(y0 - hy, 0, hy - y1)
        if math.hypot(dx, dy) < HOLE_KEEP:
            return False
    return True

# Never shove these aside to make room for something else: the MCU, the connectors
# whose position is mechanically fixed, the sensors whose position is functional
# (IMUs at the centroid, flow and ToF looking down), and the crystal we just spent
# real effort putting under the OSC pins.
ANCHORS = {"U1", "J1", "J2", "J3", "J8", "U2", "U3", "U4", "U6", "U7",
           "Y1", "SW1", "SW2", "U8", "U18", "U9", "U10", "U11", "U5", "U12", "U17"}


def bbox(fp):
    r = fp.GetBoundingBox(False, False)
    return (r.GetLeft()/1e6, r.GetTop()/1e6, r.GetRight()/1e6, r.GetBottom()/1e6)


def pad_xy(board, ref, num):
    fp = board.FindFootprintByReference(ref)
    if not fp:
        return None
    for p in fp.Pads():
        if p.GetNumber() == str(num):
            q = p.GetPosition()
            return (q.x/1e6, q.y/1e6)
    return None


def pad_gap(fp, target):
    """Closest approach from any of fp's pads to the target point."""
    best = 1e9
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        x0, y0 = bb.GetLeft()/1e6, bb.GetTop()/1e6
        x1, y1 = bb.GetRight()/1e6, bb.GetBottom()/1e6
        dx = max(x0 - target[0], 0, target[0] - x1)
        dy = max(y0 - target[1], 0, target[1] - y1)
        best = min(best, math.hypot(dx, dy))
    return best


def main():
    board_path = sys.argv[1]
    apply = "--apply" in sys.argv
    board = pcbnew.LoadBoard(board_path)

    viol = []
    for ref, (tref, tpad, maxd) in design.ADJACENCY.items():
        fp = board.FindFootprintByReference(ref)
        t = pad_xy(board, tref, tpad)
        if not fp or not t:
            continue
        d = pad_gap(fp, t)
        if d > maxd:
            viol.append((d - maxd, d, maxd, ref, tref, tpad, t))
    viol.sort(reverse=True)
    print(f"{len(viol)} adjacency violations, worst first\n")

    fixed = stuck = 0
    for over, d, maxd, ref, tref, tpad, t in viol:
        fp = board.FindFootprintByReference(ref)
        q = fp.GetBoundingBox(False, False)
        w = (q.GetRight() - q.GetLeft())/1e6 + GAP
        h = (q.GetBottom() - q.GetTop())/1e6 + GAP
        others = [bbox(g) for g in board.GetFootprints()
                  if g.GetReference() != ref and g.IsFlipped() == fp.IsFlipped()]

        def free(cx, cy):
            x0, y0, x1, y1 = cx - w/2, cy - h/2, cx + w/2, cy + h/2
            if (x0 < B["X0"] + 0.4 or y0 < B["Y0"] + 0.4
                    or x1 > B["X0"] + B["W"] - 0.4 or y1 > B["Y0"] + B["H"] - 0.4):
                return False
            if not clears_holes(x0, y0, x1, y1):
                return False
            return not any(x0 < c and a < x1 and y0 < dd and bb < y1
                           for a, bb, c, dd in others)

        spot = None
        rad = 0.3
        while rad <= maxd + 1.0 and spot is None:
            for k in range(180):
                a = k * math.pi / 90
                cx, cy = t[0] + rad*math.cos(a), t[1] + rad*math.sin(a)
                if free(cx, cy):
                    old = fp.GetPosition()
                    fp.SetPosition(pcbnew.VECTOR2I(MM(cx), MM(cy)))
                    if pad_gap(fp, t) <= maxd:
                        spot = (cx, cy); break
                    fp.SetPosition(old)
            rad += 0.1

        moved_out = []
        if spot is None:
            # The buck areas are packed solid, so nothing is "free" there and the
            # first pass gives up on exactly the parts that matter most - the catch
            # diode and the input caps. Allow shoving small passives aside: find the
            # spot blocked by the fewest 0402-sized parts, park those anywhere legal,
            # then take the spot. Their own rules are re-checked on the next pass.
            SMALL = 3.0          # mm, longest side of a part we are willing to shove
            best = None
            rad = 0.3
            while rad <= maxd + 1.0:
                for k in range(180):
                    a = k * math.pi / 90
                    cx, cy = t[0] + rad*math.cos(a), t[1] + rad*math.sin(a)
                    x0, y0, x1, y1 = cx - w/2, cy - h/2, cx + w/2, cy + h/2
                    if (x0 < B["X0"] + 0.4 or y0 < B["Y0"] + 0.4
                            or x1 > B["X0"] + B["W"] - 0.4
                            or y1 > B["Y0"] + B["H"] - 0.4):
                        continue
                    if not clears_holes(x0, y0, x1, y1):
                        continue
                    block = [g for g in board.GetFootprints()
                             if g.GetReference() != ref
                             and g.IsFlipped() == fp.IsFlipped()
                             and (lambda r: x0 < r[2] and r[0] < x1
                                  and y0 < r[3] and r[1] < y1)(bbox(g))]
                    if any(max(bbox(g)[2]-bbox(g)[0], bbox(g)[3]-bbox(g)[1]) > SMALL
                           or g.GetReference() in ANCHORS
                           for g in block):
                        continue
                    if best is None or len(block) < len(best[2]):
                        best = (cx, cy, block)
                    if not block:
                        break
                if best and not best[2]:
                    break
                rad += 0.1
            if best:
                cx, cy, block = best
                # Put fp down FIRST. Parking blockers while fp still sat at its old
                # position let one be parked exactly where fp was about to go, and
                # the pair then overlapped - 10 courtyard overlaps and 39 clearance
                # errors traced back to this ordering.
                fp.SetPosition(pcbnew.VECTOR2I(MM(cx), MM(cy)))
                for g in block:
                    gq = g.GetBoundingBox(False, False)
                    gw = (gq.GetRight()-gq.GetLeft())/1e6 + GAP
                    gh = (gq.GetBottom()-gq.GetTop())/1e6 + GAP
                    parked = False
                    for rr in [z*0.5 for z in range(2, 40)]:
                        for kk in range(72):
                            aa = kk * math.pi / 36
                            gx, gy = cx + rr*math.cos(aa), cy + rr*math.sin(aa)
                            gx0, gy0 = gx-gw/2, gy-gh/2
                            gx1, gy1 = gx+gw/2, gy+gh/2
                            if (gx0 < B["X0"]+0.4 or gy0 < B["Y0"]+0.4
                                    or gx1 > B["X0"]+B["W"]-0.4
                                    or gy1 > B["Y0"]+B["H"]-0.4):
                                continue
                            if not clears_holes(gx0, gy0, gx1, gy1):
                                continue
                            clash = any(gx0 < c and a2 < gx1 and gy0 < d2 and b2 < gy1
                                        for a2, b2, c, d2 in
                                        [bbox(z) for z in board.GetFootprints()
                                         if z.GetReference() != g.GetReference()
                                         and z.IsFlipped() == g.IsFlipped()])
                            if clash:
                                continue
                            g.SetPosition(pcbnew.VECTOR2I(MM(gx), MM(gy)))
                            parked = True; break
                        if parked:
                            break
                    if parked:
                        moved_out.append(g.GetReference())
                if pad_gap(fp, t) <= maxd:
                    spot = (cx, cy)

        if spot:
            fixed += 1
            extra = f"   shoved aside: {', '.join(moved_out)}" if moved_out else ""
            print(f"  {ref:5} -> {tref}.{tpad:<4} {d:6.2f} -> "
                  f"{pad_gap(fp, t):5.2f} mm  (max {maxd}){extra}")
        else:
            stuck += 1
            print(f"  {ref:5} -> {tref}.{tpad:<4} {d:6.2f} mm  no free spot "
                  f"within {maxd} mm")

    print(f"\nfixed {fixed}, stuck {stuck}")
    if apply:
        # Refill, or the pour still sits where the pads used to be. Skipping this
        # produced 38 clearance and 34 mask-bridge errors, every one of them a pad
        # against a stale zone rather than a real placement problem.
        route.fill(board)
        board.Save(board_path)
        print(f"saved {board_path} (zones refilled)")
    else:
        print("dry run - pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
