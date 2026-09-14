#!/usr/bin/env python3
"""
Carry +3V3 where its plane tracks carried it, then delete the tracks.

WHY THIS EXISTS
---------------
tools/preflight.py fails "planes carry no routing": 26 track segments, 5.99 mm, all of
them +3V3 on In4.Cu. They are not litter - delete them and U3.10 and R12.1 come back
unconnected - and they are not a plane that failed to pour. They are three short bridges
that join up +3V3 pour FRAGMENTS the secondary-rail rectangles cut out of the +3V3 floor:

    run 0   17 seg  2.21 mm  bbox (124.260,121.200)-(124.640,123.160)
    run 1    8 seg  3.43 mm  bbox (123.216,108.984)-(124.356,111.824)
    run 2    1 seg  0.35 mm  bbox (137.575,119.241)-(137.611,119.590)

Run 1 lands on U3.10 and on R12.1, two +3V3 pads that sit inside rail territory; run 0
and run 2 join fragments with no pad of their own. So the honest fix is not to re-route
them - a 0.45 mm via at either end of a 2 mm bridge in that congestion does not have a
home - but to make the +3V3 plane reach them, which is what tools/repour_power.py's four
priority-22 restoration patches already do for four other stubs.

WHAT THIS ADDS, IN TWO HALVES
-----------------------------
1. Every In4 zone goes onto the board's own clearance rule. The rail rectangles and the
   priority-22 patches all carry SetLocalClearance(0.25), 2.5x the 0.1016 the rest of the
   board uses. That value decides the hole a rail leaves around a foreign via and the gap
   a +3V3 path needs. On the board's rule the rails are MEASURABLY better - VBAT's
   tightest cut goes from 1.8 A to 2.0 A - because every via hole in a rail shrinks by
   0.148 mm of radius. Both values are legal; only one of them is the board's rule.

2. One +3V3 zone per run, priority 23 (above every rail rectangle, as the priority-22
   patches are), whose outline is the run's own polyline buffered by CORRIDOR mm. Then
   the tracks are removed and the board is filled.

The corridors are deliberately tight rather than rectangular boxes: run 0 is a 17-segment
staircase in a 0.38 x 1.96 mm box, and a bounding box there takes far more copper from
VBAT than the track it replaces. Buffering the polyline keeps the corridor close to the
copper it replaced.

The corridor width is set by the rule, not by taste. With the rails on 0.1016, a corridor
outline 2*CORRIDOR wide fills 2*CORRIDOR - 2*0.1016 mm, and the fill has to clear the
zone's min thickness to survive at all:

    2 * 0.20 - 2 * 0.1016 = 0.197 mm of copper, against the 0.1016 min thickness.

THE SHAPE MATTERS MORE THAN THE WIDTH, and getting it wrong cost several wrong answers.
The first version boxed every segment in an upright rectangle. Several of these runs are
45-degree staircases, so boxing them fanned each corridor out to roughly the segment's
own length - which both ate VBAT copper (1.6 A, a check_power_cut failure) and got the
corridor chopped into pieces by vias it was never near. Widening it made things worse,
not better, which is the tell. Offsetting perpendicular to the segment instead gives a
capsule that sits where the track sat:

                          VBAT      unconnected   +3V3 plane
    rails 0.25, boxes      1.6 A     3             split
    rails 0.1016, boxes    2.0 A     3             split
    rails 0.1016, capsules 2.0 A     2             whole

With capsules the result is width-insensitive from 0.16 to 0.25 mm, so 0.20 is chosen for
margin over the 0.1524 the min thickness needs.

check_power_cut.py is the arbiter for the rail half: VBAT is the tight rail (1.7 A
needed) and this change takes it from 1.8 A to 2.0 A. Run it after any change here.

Usage:
  python3 tools/extend_plus3v3.py            # dry run, report what it would do
  python3 tools/extend_plus3v3.py --apply    # write the board

board.Remove() leaves pcbnew's ZONES list stale and the next Add() segfaults, so the
strip and the rebuild run in separate processes - same reason as repour_power.py.
"""
import math, os, subprocess, sys
from collections import defaultdict

BOARD = "NAVCORE-SoOP.kicad_pcb"
HERE = os.path.abspath(__file__)
CORRIDOR = 0.20          # mm buffered around each run (fill = 2*C - 2*clearance)
BOARD_RULE = 0.1016      # the board's own min clearance; what every other zone uses
NET = "+3V3"
PLANE = "In4.Cu"
PRIO = 23


def runs(board):
    """Connected runs of +3V3 track on the plane layer, as lists of (a, b) in mm."""
    import pcbnew
    segs = [t for t in board.GetTracks()
            if t.Type() != pcbnew.PCB_VIA_T
            and board.GetLayerName(t.GetLayer()) == PLANE
            and t.GetNetname() == NET]
    par = {}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    def key(p):
        return (round(p.x / 1000), round(p.y / 1000))

    for t in segs:
        for p in (t.GetStart(), t.GetEnd()):
            par.setdefault(key(p), key(p))
    for t in segs:
        uni(key(t.GetStart()), key(t.GetEnd()))
    g = defaultdict(list)
    for t in segs:
        s, e = t.GetStart(), t.GetEnd()
        g[find(key(s))].append(((s.x / 1e6, s.y / 1e6), (e.x / 1e6, e.y / 1e6)))
    return sorted(g.values(), key=lambda r: -len(r))


def main():
    apply = "--apply" in sys.argv
    global CORRIDOR
    if "--corridor" in sys.argv:
        CORRIDOR = float(sys.argv[sys.argv.index("--corridor") + 1])
    sys.path.insert(0, os.path.dirname(HERE))
    import pcbnew, route

    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    rs = runs(b)
    lid = b.GetLayerID(PLANE)
    stale = [z for z in b.Zones()
             if z.GetNetname() == NET and z.GetAssignedPriority() == PRIO]
    if stale:
        print(f"{len(stale)} corridor zone(s) already present - run --strip first\n")
    fills = [z.GetFilledPolysList(lid) for z in b.Zones()
             if z.GetNetname() == NET and lid in z.GetLayerSet().CuStack()]

    def covered(x, y):
        p = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
        return any(pl.Collide(p, 0) for pl in fills)

    print(f"{sum(len(r) for r in rs)} {NET} segment(s) on {PLANE} "
          f"in {len(rs)} run(s); buffering each by {CORRIDOR} mm\n")
    total = 0.0
    for i, run in enumerate(rs):
        xs = [p[0] for s in run for p in s]
        ys = [p[1] for s in run for p in s]
        L = sum(math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]) for s in run)
        unc = 0.0
        for s in run:
            n = max(2, int(math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]) / 0.005))
            for k in range(n):
                t = (k + 0.5) / n
                x = s[0][0] + t * (s[1][0] - s[0][0])
                y = s[0][1] + t * (s[1][1] - s[0][1])
                if not covered(x, y):
                    unc += math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]) / n
        total += unc
        print(f"  run {i}: {len(run):2d} seg {L:5.3f} mm  "
              f"bbox ({min(xs):.3f},{min(ys):.3f})-({max(xs):.3f},{max(ys):.3f})  "
              f"{unc:.3f} mm not covered by the pour")
    print(f"\n{total:.3f} mm of {NET} copper on {PLANE} is carrying current the pour "
          f"cannot reach")
    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0

    # The corridor outlines are derived from the tracks, so once they are gone there is
    # nothing to re-derive them from. Refuse rather than quietly strip them and leave
    # the plane with no bridge at all - which is what a careless re-run did once.
    if not rs:
        print("\nno plane tracks left to derive corridors from - already applied? "
              "Re-run from a board that still has them (git checkout, or the backup).")
        return 1

    # ---- 1. strip any corridor zones from a previous run (separate process) ----
    subprocess.run([sys.executable, "-u", HERE, "--strip"], check=True)

    # ---- 2a. put every In4 zone on the board rule ----
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    n_clr = 0
    skip_clr = "--no-rail-clearance" in sys.argv
    for z in ([] if skip_clr else b.Zones()):
        if lid in z.GetLayerSet().CuStack() and \
           round(z.GetLocalClearance() / 1e6, 4) != BOARD_RULE:
            z.SetLocalClearance(pcbnew.FromMM(BOARD_RULE))
            n_clr += 1
    b.Save(BOARD)
    print(("skipped the rail clearance change (--no-rail-clearance)" if skip_clr else
           f"put {n_clr} In4 zone(s) on the board's {BOARD_RULE} mm clearance"))

    # ---- 2b. build the corridors ----
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    net = b.FindNet(NET)
    rs = runs(b)
    made = 0
    for run in rs:
        poly = pcbnew.SHAPE_POLY_SET()
        for (x1, y1), (x2, y2) in run:
            # Offsets are perpendicular to the segment, not axis-aligned. Boxing a
            # diagonal segment in an upright rectangle fans it out by up to its own
            # length, which ate VBAT copper and got the corridor chopped by vias it
            # was never near. Several of these runs are 45-degree staircases.
            ux, uy = x2 - x1, y2 - y1
            L = math.hypot(ux, uy)
            if L > 1e-9:
                ux, uy = ux / L, uy / L
            px, py = -uy, ux
            ax, ay = x1 - px * CORRIDOR, y1 - py * CORRIDOR
            bx, by = x1 + px * CORRIDOR, y1 + py * CORRIDOR
            cx, cy = x2 + px * CORRIDOR, y2 + py * CORRIDOR
            dx, dy = x2 - px * CORRIDOR, y2 - py * CORRIDOR
            poly.NewOutline()
            for ex, ey in ((ax, ay), (bx, by), (cx, cy), (dx, dy)):
                poly.Append(pcbnew.FromMM(ex), pcbnew.FromMM(ey))
        poly.Simplify()          # unions the overlapping per-segment quads
        z = pcbnew.ZONE(b)
        z.SetLayer(b.GetLayerID(PLANE))
        z.SetNet(net)
        z.SetAssignedPriority(PRIO)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetLocalClearance(pcbnew.FromMM(route.CLEAR))
        z.SetMinThickness(pcbnew.FromMM(route.TRACK_W))
        o = z.Outline()
        for i in range(poly.OutlineCount()):
            src = poly.Outline(i)
            o.NewOutline()
            for k in range(src.PointCount()):
                p = src.CPoint(k)
                o.Append(p.x, p.y)
        b.Add(z)
        made += 1
    print(f"added {made} {NET} corridor zone(s) at priority {PRIO}")

    # ---- 3. the tracks the corridors replace ----
    dead = [t for t in b.GetTracks()
            if t.Type() != pcbnew.PCB_VIA_T
            and b.GetLayerName(t.GetLayer()) == PLANE
            and t.GetNetname() == NET]
    for t in dead:
        b.Remove(t)
    print(f"removed {len(dead)} {NET} segment(s) from {PLANE}")

    route.fill(b)
    b.Save(BOARD)
    print("filled and saved")
    return 0


def strip():
    sys.path.insert(0, os.path.dirname(HERE))
    import pcbnew, route
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    n = 0
    for z in list(b.Zones()):
        if z.GetNetname() == NET and z.GetAssignedPriority() == PRIO:
            b.Remove(z)
            n += 1
    b.Save(BOARD)
    print(f"stripped {n} existing corridor zone(s)")


if __name__ == "__main__":
    if "--strip" in sys.argv:
        strip()
    else:
        sys.exit(main())
