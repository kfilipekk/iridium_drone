#!/usr/bin/env python3
"""
Drop a via into each orphaned ground island, shoving copper aside where needed.

Three slivers of the GND pour float free - 0.87 mm2 on F.Cu, 1.22 and 1.52 mm2 on
B.Cu - and each one carries a ground pad (U1.49, C19.2, C71.2) whose ONLY path to
ground it is. A geometric union-find over the ground net confirms it: each of those
pads sits in a component of one to four items that reaches no via at all. They are
genuinely floating, not merely cosmetically isolated.

Every earlier attempt concluded that no via fits in any of them. That conclusion was
wrong, and the reason is worth stating plainly: route.obstacle_shapes() gives a pad no
layer, so a surface-mount pad on the far side of the board blocked vias it cannot
touch, and same-net ground copper was treated as an obstacle to a ground via. With the
model corrected (see tools/shove.py) a 0.45 mm via fits in two of the three islands
with 0.33 mm of copper clearance - comfortably legal, and there all along.

The third is short by 0.08 mm, held by three traces - BUCK_EN on B.Cu, BOOT0 on In2.Cu
and +5V on In3.Cu - all of which can be shoved. A via is drilled through the whole
stack, so all three have to move, each on its own layer.

Order of preference: a via on island copper needing nothing moved, then one reachable
by a short track across the island's own pocket, then one that needs a shove.

Usage:  python3 tools/island_via.py [--apply] [--grid MM]
"""
import os, sys, math, shutil, subprocess, re
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove, island_route as ir

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/isv_backup.kicad_pcb"
RPT   = "/tmp/nav/isv.rpt"
TIERS = [(0.45, 0.20), (0.50, 0.25), (0.60, 0.30)]
TOMM  = route.TOMM
NET   = "GND"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items")


def pocket(g, isl):
    """Cells a ground trace can reach starting from inside this island."""
    src = []
    for j in range(g.ny):
        for i in range(g.nx):
            if g.free[j*g.nx + i]:
                x, y = g.pos(i, j)
                if ir.inside(isl, x, y):
                    src.append((i, j))
    seen, q = set(src), deque(src)
    while q:
        i, j = q.popleft()
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = (i+di, j+dj)
            if nb in seen or not g.ok(*nb):
                continue
            seen.add(nb); q.append(nb)
    return src, seen


def candidates(g, isl, cells, idx, holes, kos):
    """Every via position in the pocket, best first.

    Sorted so that a via needing nothing moved and sitting on island copper wins over
    one needing a track, which wins over one needing a shove.
    """
    out = []
    for via_d, drill in TIERS:
        need = via_d/2 + route.VIA_CLEAR + 0.005
        for (i, j) in cells:
            x, y = g.pos(i, j)
            if not route.inside_board(x, y, via_d/2 + 0.35):
                continue
            if any(x1 - via_d/2 < x < x2 + via_d/2 and y1 - via_d/2 < y < y2 + via_d/2
                   for x1, y1, x2, y2 in kos):
                continue
            if not route.hole_ok(x, y, holes, drill):
                continue
            blk = [s for s in idx.near(x, y, need + 1.5)
                   if route.gap_to_shape(x, y, s.geom) < need]
            if any(not s.shovable for s in blk):
                continue
            on_isl = ir.inside(isl, x, y)
            out.append((len(blk), 0 if on_isl else 1, x, y, via_d, drill, blk, on_isl))
        if any(c[0] == 0 for c in out):
            break                       # a free position at this size beats a bigger via
    out.sort(key=lambda c: (c[0], c[1]))
    return out


def track_to(g, cells, src, target):
    """Shortest path across the pocket from island copper to `target` cell."""
    if target in set(src):
        return []
    prev = {s: None for s in src}
    q = deque(src)
    ok = set(cells)
    while q:
        cur = q.popleft()
        if cur == target:
            path = [cur]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            return [g.pos(*c) for c in reversed(path)]
        i, j = cur
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = (i+di, j+dj)
            if nb in prev or nb not in ok:
                continue
            prev[nb] = cur
            q.append(nb)
    return None


def main():
    apply = "--apply" in sys.argv
    step = float(sys.argv[sys.argv.index("--grid")+1]) if "--grid" in sys.argv else 0.02
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0 = drc()
    print(f"baseline {hard0} errors, {un0} unconnected\n")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    route.fill(board)
    polys = ir.gnd_polys(board)
    isls = ir.orphans(board, polys)
    allsh = shove.shapes_of(board, exclude_net=NET)
    idx = shove.ShapeIndex(allsh)
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)
    chains, cindex = shove.build_chains(board)
    print(f"{len(isls)} orphaned island(s), {len(allsh)} foreign copper shapes")

    jobs = []
    for lname, _pi, isl, a in isls:
        xs = [p[0] for p in isl]; ys = [p[1] for p in isl]
        g = ir.Grid(board, lname, (min(xs), min(ys), max(xs), max(ys)),
                    step, allsh, 4.0)
        src, cells = pocket(g, isl)
        cands = candidates(g, isl, cells, idx, holes, kos)
        head = f"  {lname:6} {a:5.2f} mm2 at ({min(xs):.2f},{min(ys):.2f})"
        if not cands:
            print(f"{head}: no via position anywhere in its pocket")
            continue
        picked = None
        for nblk, _pref, x, y, via_d, drill, blk, on_isl in cands[:400]:
            cell = g.cell(x, y)
            path = [] if on_isl else track_to(g, cells, src, cell)
            if path is None:
                continue
            plans = []
            if blk:
                plans = shove.plan_shoves((x, y), via_d, blk, allsh, chains, cindex)
                if plans is None:
                    continue
            picked = (lname, x, y, via_d, drill, path, plans)
            break
        if picked is None:
            print(f"{head}: {len(cands)} positions, none workable")
            continue
        _l, x, y, via_d, drill, path, plans = picked
        L = sum(math.hypot(path[i+1][0]-path[i][0], path[i+1][1]-path[i][1])
                for i in range(len(path)-1)) if path else 0.0
        print(f"{head}: via {via_d:.2f} at ({x:.3f},{y:.3f})"
              + (f", {L:.2f} mm of track to reach it" if L else " on island copper")
              + (", shoving " + ", ".join(
                  f"{chains[ci]['net']}/{chains[ci]['layer']} by {off:.2f} mm"
                  for ci, _p, off in plans) if plans else ", nothing moved"))
        jobs.append(picked)

    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0

    for lname, x, y, via_d, drill, path, plans in jobs:
        shutil.copy(BOARD, BAK)
        bd = pcbnew.LoadBoard(BOARD)
        route.set_rules(bd)
        n = bd.FindNet(NET)
        if plans:
            doomed_keys = set()
            for ci, _pts, _off in plans:
                ch = chains[ci]
                for k in range(len(ch["pts"]) - 1):
                    p, q = ch["pts"][k], ch["pts"][k+1]
                    doomed_keys.add((ch["net"], ch["layer"], tuple(sorted(
                        [(shove.Q(p[0]*1e6), shove.Q(p[1]*1e6)),
                         (shove.Q(q[0]*1e6), shove.Q(q[1]*1e6))]))))
            doomed = []
            for t in bd.GetTracks():
                if t.Type() == pcbnew.PCB_VIA_T:
                    continue
                nx = t.GetNet()
                aa, bb = t.GetStart(), t.GetEnd()
                k = (nx.GetNetname() if nx else "", bd.GetLayerName(t.GetLayer()),
                     tuple(sorted([(shove.Q(aa.x), shove.Q(aa.y)),
                                   (shove.Q(bb.x), shove.Q(bb.y))])))
                if k in doomed_keys:
                    doomed.append(t)
            for t in doomed:
                bd.Remove(t)
            for ci, pts, _off in plans:
                ch = chains[ci]
                cnet = bd.FindNet(ch["net"])
                for k in range(len(pts) - 1):
                    route.add_track(bd, pts[k], pts[k+1], ch["layer"], cnet,
                                    width=ch["width"])
        pts = ir.simplify(path) if path else []
        for i in range(len(pts) - 1):
            route.add_track(bd, pts[i], pts[i+1], lname, n, width=route.TRACK_W)
        v = route.add_via(bd, x, y, n)
        v.SetWidth(pcbnew.FromMM(via_d)); v.SetDrill(pcbnew.FromMM(drill))
        route.fill(bd)
        bd.Save(BOARD)
        hard, un = drc()
        if hard > hard0 or un >= un0:
            shutil.copy(BAK, BOARD)
            print(f"  {lname} at ({x:.2f},{y:.2f}) rolled back "
                  f"(+{hard-hard0} err, {un} unconnected)")
        else:
            un0 = un
            print(f"  {lname} at ({x:.2f},{y:.2f}) connected -> {un} unconnected")

    hard, un = drc()
    print(f"\n{hard} errors, {un} unconnected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
