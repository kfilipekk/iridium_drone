#!/usr/bin/env python3
"""
Walk an orphaned ground island out to the main pour, on a grid fine enough to see.

Three slivers of the GND pour are cut off from the rest of the net - 0.87 mm2 on F.Cu
and 1.52 and 1.22 mm2 on B.Cu - and each one holds pads whose only ground contact it is.
No via fits inside any of them, which is where every previous attempt stopped.

Two things were wrong with those attempts, and both are geometry rather than routing:

  * Pads blocked every layer. route.obstacle_shapes() models a pad as a rectangle with
    no layer, so a surface-mount pad on F.Cu blocked copper on In2.Cu that it cannot
    physically touch. Under the dense parts that is most of the board.
  * Same-net copper counted as an obstacle. The GND pour is the thing being escaped TO;
    treating it as something to avoid walls the island in behind its own net.

With both fixed, the only real obstacles to a ground trace leaving a ground island are
foreign copper ON THAT LAYER and the board edge - and there is far more room than the
old model could see. The search runs on a 0.02 mm grid, three times finer than
tools/route.py's 0.0625 mm, because these gaps are decided in hundredths.

Targets are, in order of preference:
  1. the main pour on the same layer - a plain track, no via, nothing to drill
  2. anywhere a via legally fits - drop to the In1.Cu ground plane instead

Usage:  python3 tools/island_route.py [--apply] [--grid MM] [--margin MM]
"""
import os, sys, math, shutil, subprocess, re
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/isr_backup.kicad_pcb"
RPT   = "/tmp/nav/isr.rpt"
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


# ---------------------------------------------------------------- pour geometry

def poly_pts(sh, i):
    o = sh.Outline(i)
    return [(TOMM(o.CPoint(k).x), TOMM(o.CPoint(k).y)) for k in range(o.PointCount())]


def area(p):
    a = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]; x2, y2 = p[(i+1) % len(p)]
        a += x1*y2 - x2*y1
    return abs(a) / 2


def inside(p, x, y):
    c, j = False, len(p) - 1
    for k in range(len(p)):
        if (p[k][1] > y) != (p[j][1] > y) and \
           x < (p[j][0]-p[k][0]) * (y-p[k][1]) / (p[j][1]-p[k][1] + 1e-12) + p[k][0]:
            c = not c
        j = k
    return c


def gnd_polys(board):
    """{layer name: [polygon, ...]} for the ground pour, as actually filled."""
    out = {}
    for z in board.Zones():
        n = z.GetNet()
        if not n or n.GetNetname() != NET:
            continue
        for lid in z.GetLayerSet().CuStack():
            lname = board.GetLayerName(lid)
            try:
                sh = z.GetFilledPolysList(lid)
            except Exception:
                continue
            out.setdefault(lname, []).extend(
                poly_pts(sh, i) for i in range(sh.OutlineCount()))
    return out


def orphans(board, polys, max_area=25.0):
    """Islands of the pour with no via in them - so nothing ties them to the plane."""
    vias = [(TOMM(t.GetPosition().x), TOMM(t.GetPosition().y))
            for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    out = []
    for lname, ps in polys.items():
        if len(ps) <= 1:
            continue
        for i, p in enumerate(ps):
            a = area(p)
            if a > max_area:
                continue
            if any(inside(p, vx, vy) for vx, vy in vias):
                continue
            out.append((lname, i, p, a))
    return sorted(out, key=lambda r: r[3])


# ---------------------------------------------------------------- the grid

class Grid:
    """Where a GND trace may legally go on one layer, at `step` resolution."""

    def __init__(self, board, layer, box, step, allsh, margin):
        x1, y1, x2, y2 = box
        self.x0, self.y0, self.step = x1 - margin, y1 - margin, step
        self.nx = int((x2 - x1 + 2*margin) / step) + 1
        self.ny = int((y2 - y1 + 2*margin) / step) + 1
        self.free = bytearray(b"\x01" * (self.nx * self.ny))
        need = route.TRACK_W/2 + route.CLEAR + 0.005
        # Stamp each obstacle onto the grid rather than testing every cell against
        # every obstacle - 200k cells times 500 shapes does not finish.
        wx1, wy1 = x1 - margin - 2.0, y1 - margin - 2.0
        wx2, wy2 = x2 + margin + 2.0, y2 + margin + 2.0
        for sh in allsh:
            if layer not in sh.lset:
                continue
            g = sh.geom
            if g[0] == "rect":
                bx1, by1, bx2, by2 = g[1], g[2], g[3], g[4]
            else:
                bx1, by1 = min(g[1], g[3]) - g[5], min(g[2], g[4]) - g[5]
                bx2, by2 = max(g[1], g[3]) + g[5], max(g[2], g[4]) + g[5]
            i0, j0 = self.cell(bx1 - need, by1 - need)
            i1, j1 = self.cell(bx2 + need, by2 + need)
            for j in range(max(0, j0), min(self.ny, j1 + 1)):
                for i in range(max(0, i0), min(self.nx, i1 + 1)):
                    if not self.free[j*self.nx + i]:
                        continue
                    x, y = self.pos(i, j)
                    if route.gap_to_shape(x, y, g) < need:
                        self.free[j*self.nx + i] = 0
        for j in range(self.ny):
            for i in range(self.nx):
                if self.free[j*self.nx + i]:
                    x, y = self.pos(i, j)
                    if not route.inside_board(x, y, route.TRACK_W/2 + 0.30):
                        self.free[j*self.nx + i] = 0

    def cell(self, x, y):
        return int(round((x - self.x0)/self.step)), int(round((y - self.y0)/self.step))

    def pos(self, i, j):
        return self.x0 + i*self.step, self.y0 + j*self.step

    def ok(self, i, j):
        return 0 <= i < self.nx and 0 <= j < self.ny and self.free[j*self.nx + i]


def bfs(grid, sources, targets):
    """Shortest 8-connected path from any source cell to any target cell."""
    prev = {}
    q = deque()
    for s in sources:
        if grid.ok(*s):
            prev[s] = None
            q.append(s)
    tset = set(targets)
    while q:
        cur = q.popleft()
        if cur in tset and prev[cur] is not None:
            path = [cur]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            return list(reversed(path))
        i, j = cur
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = (i+di, j+dj)
            if nb in prev or not grid.ok(*nb):
                continue
            prev[nb] = cur
            q.append(nb)
    return None


def simplify(pts):
    """Collapse the cell-by-cell path into straight runs."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i][0]-out[-1][0], pts[i][1]-out[-1][1]
        bx, by = pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]
        if abs(ax*by - ay*bx) > 1e-9:
            out.append(pts[i])
    out.append(pts[-1])
    return out


# ---------------------------------------------------------------- per island

def solve(board, lname, isl, polys, allsh, idx, step, margin, holes, kos):
    xs = [p[0] for p in isl]; ys = [p[1] for p in isl]
    box = (min(xs), min(ys), max(xs), max(ys))
    g = Grid(board, lname, box, step, allsh, margin)

    src = []
    for j in range(g.ny):
        for i in range(g.nx):
            if g.free[j*g.nx + i]:
                x, y = g.pos(i, j)
                if inside(isl, x, y):
                    src.append((i, j))
    if not src:
        return None, "the island has no cell a trace could even start in"

    # target 1: the main pour on this layer
    main = [p for p in polys.get(lname, [])
            if area(p) > 3.0 and p is not isl]
    tgt = []
    for j in range(g.ny):
        for i in range(g.nx):
            if g.free[j*g.nx + i]:
                x, y = g.pos(i, j)
                if any(inside(p, x, y) for p in main):
                    tgt.append((i, j))
    path = bfs(g, src, tgt) if tgt else None
    if path:
        return ("track", [g.pos(*c) for c in path], None), \
               f"{len(src)} island cells, {len(tgt)} pour cells"

    # target 2: anywhere a via fits, then down to the In1.Cu plane
    for via_d, drill in TIERS:
        need = via_d/2 + route.VIA_CLEAR + 0.005
        vt = []
        for j in range(g.ny):
            for i in range(g.nx):
                if not g.free[j*g.nx + i]:
                    continue
                x, y = g.pos(i, j)
                if not route.inside_board(x, y, via_d/2 + 0.35):
                    continue
                if any(x1 - via_d/2 < x < x2 + via_d/2 and
                       y1 - via_d/2 < y < y2 + via_d/2 for x1, y1, x2, y2 in kos):
                    continue
                if not route.hole_ok(x, y, holes, drill):
                    continue
                # a via is drilled through every layer, so check them all
                if any(route.gap_to_shape(x, y, sh.geom) < need
                       for sh in idx.near(x, y, need + 1.0)):
                    continue
                vt.append((i, j))
        if not vt:
            continue
        path = bfs(g, src, vt)
        if path:
            return ("via", [g.pos(*c) for c in path], (via_d, drill)), \
                   f"{len(src)} island cells, {len(vt)} via-legal cells ({via_d} mm)"
    return None, f"{len(src)} island cells, no route to the pour and nowhere a via fits"


def main():
    apply = "--apply" in sys.argv
    step = float(sys.argv[sys.argv.index("--grid")+1]) if "--grid" in sys.argv else 0.02
    margin = float(sys.argv[sys.argv.index("--margin")+1]) \
        if "--margin" in sys.argv else 4.0
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0 = drc()
    print(f"baseline {hard0} errors, {un0} unconnected\n")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    route.fill(board)
    polys = gnd_polys(board)
    isls = orphans(board, polys)
    print(f"{len(isls)} orphaned ground island(s)")
    allsh = shove.shapes_of(board, exclude_net=NET)
    idx = shove.ShapeIndex(allsh)
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)
    print(f"{len(allsh)} copper shapes, {len(holes)} drilled holes")

    todo = []
    for lname, _pi, isl, a in isls:
        xs = [p[0] for p in isl]; ys = [p[1] for p in isl]
        res, note = solve(board, lname, isl, polys, allsh, idx, step,
                          margin, holes, kos)
        head = (f"  {lname:6} {a:5.2f} mm2 at ({min(xs):.2f},{min(ys):.2f})")
        if res is None:
            print(f"{head}: {note}")
            continue
        kind, pts, via = res
        pts = simplify(pts)
        L = sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
                for i in range(len(pts)-1))
        print(f"{head}: {kind} route, {L:.2f} mm in {len(pts)-1} segments  [{note}]")
        todo.append((lname, kind, pts, via))

    if not todo or not apply:
        if not apply:
            print("\ndry run - pass --apply to write the board")
        return 0

    for lname, kind, pts, via in todo:
        shutil.copy(BOARD, BAK)
        bd = pcbnew.LoadBoard(BOARD)
        route.set_rules(bd)
        n = bd.FindNet(NET)
        for i in range(len(pts) - 1):
            route.add_track(bd, pts[i], pts[i+1], lname, n, width=route.TRACK_W)
        if kind == "via":
            v = route.add_via(bd, pts[-1][0], pts[-1][1], n)
            v.SetWidth(pcbnew.FromMM(via[0])); v.SetDrill(pcbnew.FromMM(via[1]))
        route.fill(bd)
        bd.Save(BOARD)
        hard, un = drc()
        if hard > hard0 or un >= un0:
            shutil.copy(BAK, BOARD)
            print(f"  {lname} rolled back (+{hard-hard0} err, {un} unconnected)")
        else:
            un0 = un
            print(f"  {lname} connected -> {un} unconnected")

    hard, un = drc()
    print(f"\n{hard} errors, {un} unconnected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
