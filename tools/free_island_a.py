#!/usr/bin/env python3
"""
Dissolve the U13.3 ground island by opening the corridor that fences it.

What this replaces
------------------
`tools/nudge_part.py` was the plan for this island: shift U5 east so a 0.45 mm via
becomes legal in the pocket beside it. That plan does not survive measurement, and the
reason is worth keeping. U5's pads are 1.27 mm pitch and 0.63 mm wide, so the channel
between U5.5 and U5.6 is **0.640 mm**, and a 0.45 mm via needs 2*(0.225 + 0.1016) =
**0.6532 mm** of it. Translating U5 moves that pair together, so the channel width never
changes and no offset can ever open a via there - measured best is a 0.437 mm via, and
docs/LAYOUT.md fixes this fab class at **min via pad 0.45 mm**. The earlier "ignoring
U5 gives a legal 0.3309 mm gap" result came from dropping *both* pads at once, which is
not something a move can do.

What actually works
-------------------
The island is the pour north of U13's pad row. Its only outlet is the 0.387 mm corridor
between that pad row and U13's exposed pad - and the corridor is filled by the VCC_RF
run at y 115.14 that ties U13.1/U13.2 to U13.6/U13.7. Take that run out from under
U13.3 and the pour rises from the exposed pad (ground, main pour) across U13.3's own
ground pad, which needs no clearance at all because it is the same net.

Measured: islands 2 -> 1 and DRC 0 errors, with island B (C8.2) untouched.

The run was the *only* link between VCC_RF's two halves - the tuner's supply filter
(R28, C49, U13.1/U13.2/U13.25) and the tuner's own VCC pins (U13.6/U13.7/U13.13 and the
long run east to x 143.08) - so cutting it splits the net. Two things repair that:

  * U13.6 is the one pad that only escapes south; it gets a 0.5 mm re-feed north at
    y 114.043 joining it to U13.7's north escape, so the east half stays whole.
  * the two halves are joined again by a new VCC_RF link, searched rather than guessed:
    legal via sites are found on each half (on pads as well as tracks) and a grid flood
    on the signal layers says whether a path exists between them. B.Cu cannot carry it -
    the wall is C36 and GC1's north escape, and B.Cu reaches 0 of 66 east sites - so the
    link runs on In2.Cu, which reaches 66 of 66.

Status: this works. The relink runs on In2.Cu from a via on R28.2's pad (138.11, 111.59)
to a via on the east half, and it is short. The earlier "the relink does NOT work" result
came from enumerating via sites on *tracks only*; R28.2 is a pad, so the west half looked
like it had just the two C49-branch sites, and that branch is a closed pocket. Sampling
pad interiors as well gives 9 legal west sites (R28.2 among them) and In2.Cu then reaches
all 66 east sites - measured 66/66, versus 0/66 if the link is forced onto B.Cu.

Usage:  python3 tools/free_island_a.py [--apply] [--layer In2.Cu|F.Cu|B.Cu]
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove, island_route as ir

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK = "/tmp/nav/isla_backup.kicad_pcb"
RPT = "/tmp/nav/isla.rpt"
SIG = ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu")
VIA_D, DRILL = 0.45, 0.20

# (start, end) of the corridor run segments to remove, in mm
DROP = [
    ((138.140, 115.181), (138.664, 115.181)),
    ((138.704, 115.142), (138.664, 115.181)),
    ((140.100, 115.142), (138.704, 115.142)),
    ((140.600, 115.142), (140.100, 115.142)),
    ((140.100, 114.593), (140.100, 115.142)),
]
# U13.6's replacement escape, from its pad north to U13.7's north escape
ADD = [
    ((140.100, 114.593), (140.100, 114.043)),
    ((140.100, 114.043), (140.600, 114.043)),
]


def nn(o):
    n = o.GetNet()
    return n.GetNetname() if n else ""


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
        cls.count("unconnected_items"), t


def islands():
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    return [(round(a, 3), l) for l, _p, _poly, a in ir.orphans(b, ir.gnd_polys(b))]


# Removing a track hands its ownership to the board. If the Python wrapper is then
# garbage collected, SWIG frees copper the board still points at and the next
# GetTracks() walk segfaults - so every removed object is kept alive for the run.
_KEEP = []


def cut(b):
    """Remove the corridor run and re-feed U13.6. Returns (removed, added)."""
    net = b.FindNet("VCC_RF")
    victims = []
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetNetname() != "VCC_RF":
            continue
        if b.GetLayerName(t.GetLayer()) != "B.Cu":
            continue
        s, e = t.GetStart(), t.GetEnd()
        a = (route.TOMM(s.x), route.TOMM(s.y))
        c = (route.TOMM(e.x), route.TOMM(e.y))
        for p, q in DROP:
            if (math.dist(a, p) < 0.01 and math.dist(c, q) < 0.01) or \
               (math.dist(a, q) < 0.01 and math.dist(c, p) < 0.01):
                victims.append(t)
    for t in victims:
        b.Remove(t)
    _KEEP.extend(victims)
    for p, q in ADD:
        route.add_track(b, p, q, "B.Cu", net, width=route.TRACK_W)
    return len(victims)


def shapes(b):
    """Every copper item as a shove.Shape, plus per-layer lists for collision work."""
    out = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            ls = frozenset(L for L in shove.COPPER if p.IsOnLayer(b.GetLayerID(L)))
            out.append(shove.Shape(("rect", route.TOMM(bb.GetLeft()), route.TOMM(bb.GetTop()),
                                    route.TOMM(bb.GetRight()), route.TOMM(bb.GetBottom())),
                                   "pad", nn(p), lset=ls))
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            c = t.GetPosition()
            try:
                r = route.TOMM(t.GetWidth(b.GetLayerID("F.Cu")))/2
            except TypeError:
                r = route.VIA_D/2
            out.append(shove.Shape(("cap", route.TOMM(c.x), route.TOMM(c.y),
                                    route.TOMM(c.x), route.TOMM(c.y), r), "via", nn(t)))
        else:
            s, e = t.GetStart(), t.GetEnd()
            lay = b.GetLayerName(t.GetLayer())
            out.append(shove.Shape(("cap", route.TOMM(s.x), route.TOMM(s.y),
                                    route.TOMM(e.x), route.TOMM(e.y),
                                    route.TOMM(t.GetWidth())/2), "track", nn(t),
                                   layer=lay, lset=frozenset([lay])))
    return out


def via_ok(b, allsh, x, y):
    need = VIA_D/2 + route.VIA_CLEAR + 0.005
    if not route.inside_board(x, y, VIA_D/2 + 0.35):
        return False
    if not route.hole_ok(x, y, route.hole_shapes(b), DRILL):
        return False
    for sh in allsh:
        if sh.net == "VCC_RF":
            continue
        if route.gap_to_shape(x, y, sh.geom) < need:
            return False
    return True


def half_points(b, lo, hi):
    """Points sitting ON VCC_RF copper with lo <= x <= hi (so a via there is bonded)."""
    pts = []
    # Pads as well as tracks. Leaving pads out was the blind spot that made the west
    # half look like it had only two legal via sites: both were on the C49 branch, and
    # that branch is a closed pocket. R28.2's own pad takes a via, and from there In2.Cu
    # reaches the east half across the whole board.
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != "VCC_RF":
                continue
            bb = p.GetBoundingBox()
            x1, y1 = route.TOMM(bb.GetLeft()), route.TOMM(bb.GetTop())
            x2, y2 = route.TOMM(bb.GetRight()), route.TOMM(bb.GetBottom())
            for fx, fy in ((0.5, 0.5), (0.3, 0.5), (0.7, 0.5)):
                px, py = x1 + (x2-x1)*fx, y1 + (y2-y1)*fy
                if lo <= px <= hi:
                    pts.append((px, py))
    for t in b.GetTracks():
        if t.GetNetname() != "VCC_RF":
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            c = t.GetPosition()
            x, y = route.TOMM(c.x), route.TOMM(c.y)
            if lo <= x <= hi:
                pts.append((x, y))
            continue
        s, e = t.GetStart(), t.GetEnd()
        x1, y1 = route.TOMM(s.x), route.TOMM(s.y)
        x2, y2 = route.TOMM(e.x), route.TOMM(e.y)
        n = max(2, int(math.dist((x1, y1), (x2, y2))/0.05))
        for k in range(n+1):
            x = x1 + (x2-x1)*k/n
            y = y1 + (y2-y1)*k/n
            if lo <= x <= hi:
                pts.append((x, y))
    return pts


# The corridor is exactly what must stay free, so the relink is not allowed to use it.
# Without this the B.Cu flood finds the shortest path straight through the corridor -
# which is the original run, rebuilt - and the island fences itself shut again.
CORRIDOR = (137.4, 114.80, 141.0, 115.60)


def block_corridor(g):
    x1, y1, x2, y2 = CORRIDOR
    for j in range(g.ny):
        for i in range(g.nx):
            x, y = g.pos(i, j)
            if x1 <= x <= x2 and y1 <= y <= y2:
                g.free[j*g.nx + i] = 0


def main():
    apply = "--apply" in sys.argv
    want = sys.argv[sys.argv.index("--layer")+1] if "--layer" in sys.argv else None
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, _ = drc()
    isl0 = islands()
    print(f"baseline: {hard0} errors, {un0} unconnected, islands {isl0}")
    if not isl0:
        print("no islands - nothing to do")
        return 0

    shutil.copy(BOARD, BAK)
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    n = cut(b)
    if not n:
        print("corridor segments not found - already cut?"); return 1
    print(f"cut {n} corridor segment(s), re-fed U13.6 from the north")

    # Candidate via sites on each half. The west window stops short of the island's
    # west edge only where a via's own copper could re-fence it - the corridor outlet is
    # what has to stay open, and that is nowhere near here.
    allsh = shapes(b)
    west = [p for p in half_points(b, 134.6, 138.35) if via_ok(b, allsh, *p)]
    east = [p for p in half_points(b, 140.80, 144.00) if via_ok(b, allsh, *p)]
    print(f"legal via sites: {len(west)} west, {len(east)} east")
    if not west or not east:
        print("no legal via site on one half - cannot relink here")
        return 1

    # Keep the cut state so each candidate layer starts from the same board.
    CUT = "/tmp/nav/isla_cut.kicad_pcb"
    b.Save(CUT)

    # Deliberately generous: the earlier search box hugged the via sites and its south
    # edge cut off any route around U13, which is exactly the kind of route that would
    # need no vias at all. B.Cu is tried first for that reason.
    box = (132.5, 109.5, 145.5, 121.5)
    for L in ([want] if want else ["B.Cu", "In2.Cu", "In3.Cu", "F.Cu"]):
        keep = [s for s in allsh if s.net != "VCC_RF"]
        g = ir.Grid(b, L, box, 0.05, keep, 2.0)
        block_corridor(g)
        seeds = set()
        for x, y in west:
            c = g.cell(x, y)
            if g.ok(*c):
                seeds.add(c)
        if not seeds:
            print(f"  {L}: west vias have no legal grid cell"); continue
        d, pv = shove.spread(g, seeds)
        hits = [(x, y) for x, y in east if g.cell(x, y) in d]
        print(f"  {L}: {len(hits)} of {len(east)} east sites reachable")
        if not hits:
            continue
        # Nearest east site by flood distance, not list order: the first match was
        # C50's pad, 9.8 mm away, when the east run itself is 3.5 mm from R28.
        target = min(hits, key=lambda p: d[g.cell(*p)])
        run = shove.straighten(shove.walk_back(g, pv, g.cell(*target)))[::-1]
        wsite = min(west, key=lambda p: math.dist(p, run[0]))
        run = [wsite] + run + [target]
        length = sum(math.dist(run[k], run[k+1]) for k in range(len(run)-1))
        print(f"  {L}: {length:.2f} mm, west via ({wsite[0]:.2f},{wsite[1]:.2f}), "
              f"east via ({target[0]:.2f},{target[1]:.2f})")

        shutil.copy(CUT, BOARD)
        b2 = pcbnew.LoadBoard(BOARD)
        route.set_rules(b2)
        net = b2.FindNet("VCC_RF")
        for p, q in zip(run, run[1:]):
            route.add_track(b2, p, q, L, net, width=route.TRACK_W)
        for site in (wsite, target):
            v = route.add_via(b2, site[0], site[1], net)
            v.SetWidth(pcbnew.FromMM(VIA_D)); v.SetDrill(pcbnew.FromMM(DRILL))
        route.fill(b2)
        b2.Save(BOARD)

        isl = islands()
        hard, un, txt = drc()
        print(f"     -> islands {isl}, DRC {hard} errors, {un} unconnected")
        if len(isl) == 1 and hard <= hard0 and un < un0:
            print("KEPT")
            return 0
        for blk in re.split(r'^\[', txt, flags=re.M)[1:][:4]:
            print("       " + blk.splitlines()[0])

    print("no layer produced a clean relink; reverting")
    shutil.copy(BAK, BOARD)
    return 1


if __name__ == "__main__":
    sys.exit(main())
