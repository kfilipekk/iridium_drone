#!/usr/bin/env python3
"""A maze router that knows what a clearance rule is.

WHY THIS EXISTS. Three earlier attempts to connect U19 failed in three different ways,
all of them the same underlying defect - reasoning about a property ADJACENT to the one
that matters:

  * route_nets.py / route_remaining.py joined a pad to same-net copper 0.01 mm away on
    a DIFFERENT LAYER and reported the net as routed. Proximity is not connectivity.
  * routing it by hand against a per-layer copper listing missed that a THROUGH VIA is
    an obstacle on all six layers, not just the two it is drawn on. A +5V via sitting
    on In3 shorted an In1 track that nothing on In1 could see.
  * routing it by hand against the drawn geometry treated a via as its track's
    half-width. A 0.60 mm via is 0.30 mm of copper, not 0.05 mm, and two routes missed
    by 0.018 mm and 0.044 mm.

So this searches a real grid, on every layer at once, against the board's own rules -
clearance, hole clearance and hole-to-hole are READ FROM THE BOARD, not typed here. A
via is only permitted where all six layers are clear of other nets. Zones are ignored
on purpose: a pour retreats around a track when it is refilled, so treating it as an
obstacle would forbid every route on a plane layer.

It is pure standard library. numpy is not installed for the interpreter that carries
pcbnew, and a tool that needs a pip install is a tool that fails on a fresh clone.

A pad spec may carry a trailing "^", meaning STITCH: route it on its own layer to
the nearest point where a via is legal, and drop one. That exists because a pad sitting
in a ground pour is not necessarily connected to ground. Routing U19 pinched a 0.576 mm2
island of B.Cu pour whose only occupants were U19's own GND balls, and DRC reported no
unconnected pad - the pads WERE connected, to a scrap of copper joined to nothing. Only
a via crosses to the planes, so the stitch is explicit rather than assumed.

    python3 tools/route_maze.py U19.B2^ U19.A1 U19.A2 U19.B1 C74.1
"""
import heapq
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD = "NAVCORE-SoOP.kicad_pcb"
STEP = float(os.environ.get("ROUTE_STEP", "0.025"))   # grid pitch, mm; coarser for long runs
TRACK_W = 0.1016        # these nets carry microamps; the board minimum is right
VIA_DIA, VIA_DRILL = 0.45, 0.20
VIA_COST_MM = 1.2       # a via must buy at least this much detour to be worth taking
EDGE_KEEP = 0.35
# In4.Cu is the POWER layer: +3V3, +3V3A, +5V and VBAT live there as zone fills, and
# HEAD carries no signal track on it at all. A signal routed across it carves the
# fills - 18 mm of QOUT_P severed the +3V3 island feeding U5 and nothing reported it
# until the island's only path was gone. Never route there.
# In1.Cu is the GND plane directly under F.Cu and is kept SOLID: HEAD carries no track
# on it, preflight refuses "planes carry no routing" and "GND plane is solid" if one
# appears, and every F.Cu signal's return current runs in it. It looked empty when
# the first routes went down precisely because it is forbidden. Routing layers on
# this board are F.Cu, In2.Cu, In3.Cu and B.Cu.
NO_ROUTE_LAYERS = {"In1.Cu", "In4.Cu"}
WINDOW_MM = float(os.environ.get("ROUTE_WINDOW", "7.0"))


class Grid:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.nx = int((x1 - x0) / STEP) + 1
        self.ny = int((y1 - y0) / STEP) + 1
        self.n = self.nx * self.ny

    def xy(self, i, j):
        return (self.x0 + i * STEP, self.y0 + j * STEP)

    def blank(self):
        return bytearray(self.n)

    def _win(self, lo_x, lo_y, hi_x, hi_y):
        i0 = max(0, int(math.floor((lo_x - self.x0) / STEP)))
        i1 = min(self.nx - 1, int(math.ceil((hi_x - self.x0) / STEP)))
        j0 = max(0, int(math.floor((lo_y - self.y0) / STEP)))
        j1 = min(self.ny - 1, int(math.ceil((hi_y - self.y0) / STEP)))
        return i0, i1, j0, j1

    def capsule(self, mask, x1, y1, x2, y2, r):
        i0, i1, j0, j1 = self._win(min(x1, x2) - r, min(y1, y2) - r,
                                   max(x1, x2) + r, max(y1, y2) + r)
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        r2 = r * r
        x0g, y0g, nx = self.x0, self.y0, self.nx
        for j in range(j0, j1 + 1):
            py = y0g + j * STEP
            base = j * nx
            for i in range(i0, i1 + 1):
                px = x0g + i * STEP
                if L2 < 1e-12:
                    ex, ey = px - x1, py - y1
                else:
                    t = ((px - x1) * dx + (py - y1) * dy) / L2
                    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                    ex, ey = px - (x1 + t * dx), py - (y1 + t * dy)
                if ex * ex + ey * ey <= r2:
                    mask[base + i] = 1

    def rect(self, mask, cx, cy, w, h, ang_deg, r):
        rad = math.radians(ang_deg)
        ca, sa = math.cos(rad), math.sin(rad)
        half = math.hypot(w, h) / 2 + r
        i0, i1, j0, j1 = self._win(cx - half, cy - half, cx + half, cy + half)
        hw, hh = w / 2, h / 2
        x0g, y0g, nx = self.x0, self.y0, self.nx
        for j in range(j0, j1 + 1):
            py = y0g + j * STEP - cy
            base = j * nx
            for i in range(i0, i1 + 1):
                px = x0g + i * STEP - cx
                lx = px * ca + py * sa
                ly = -px * sa + py * ca
                qx = abs(lx) - hw
                qy = abs(ly) - hh
                ox = qx if qx > 0 else 0.0
                oy = qy if qy > 0 else 0.0
                d = math.hypot(ox, oy) + min(max(qx, qy), 0.0)
                if d <= r:
                    mask[base + i] = 1


def pad_shape(pad):
    p = pad.GetPosition()
    cx, cy = p.x / 1e6, p.y / 1e6
    sz = pad.GetSize()
    w, h = sz.x / 1e6, sz.y / 1e6
    ang = pad.GetOrientationDegrees()
    sh = pad.GetShape()
    if sh == pcbnew.PAD_SHAPE_CIRCLE:
        return ("cap", (cx, cy, cx, cy, w / 2))
    if sh == pcbnew.PAD_SHAPE_OVAL:
        r = min(w, h) / 2
        ext = (max(w, h) - min(w, h)) / 2
        rad = math.radians(ang)
        ux, uy = ((math.cos(rad), math.sin(rad)) if w >= h
                  else (-math.sin(rad), math.cos(rad)))
        return ("cap", (cx - ux * ext, cy - uy * ext, cx + ux * ext, cy + uy * ext, r))
    return ("rect", (cx, cy, w, h, ang))


def via_radius(v):
    try:
        return v.GetWidth(pcbnew.F_Cu) / 2e6
    except TypeError:
        return v.GetWidth() / 2e6


def collect(board, cu_layers):
    """(netcode -> [(layer, kind, args)]), [(x, y, hole_r)]"""
    items, holes = {}, []

    def add(nc, layer, kind, args, src=None):
        items.setdefault(nc, []).append((layer, kind, args, src))

    for fp in board.Footprints():
        for pad in fp.Pads():
            kind, args = pad_shape(pad)
            for l in pad.GetLayerSet().CuStack():
                add(pad.GetNetCode(), l, kind, args, pad.m_Uuid.AsString())
            d = pad.GetDrillSize()
            if d.x > 0:
                p = pad.GetPosition()
                holes.append((p.x / 1e6, p.y / 1e6, max(d.x, d.y) / 2e6))
    for t in board.GetTracks():
        nc = t.GetNetCode()
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetStart()
            x, y, r = p.x / 1e6, p.y / 1e6, via_radius(t)
            for l in cu_layers:
                add(nc, l, "cap", (x, y, x, y, r), t.m_Uuid.AsString())
            holes.append((x, y, t.GetDrill() / 2e6))
        else:
            a, c = t.GetStart(), t.GetEnd()
            add(nc, t.GetLayer(), "cap",
                (a.x / 1e6, a.y / 1e6, c.x / 1e6, c.y / 1e6, t.GetWidth() / 2e6),
                t.m_Uuid.AsString())
    return items, holes


def clusters_of(board, netcode):
    """Connected clusters of one net: tracks, vias, pads and zone-fill islands.

    "Same-net copper" is only a useful routing target if it is NOT already joined to
    the source. Without this, a pad sitting in an orphaned scrap of pour, or a track
    left dangling by a rip-up, routes to its own cluster in zero moves and reports
    success - the U19 ground island and two SOOP_?_ADC gaps were exactly that.
    Returns {uuid: cluster_index} over tracks, vias and pads. Keyed by UUID and not
    id(): SWIG mints a new Python wrapper every time a board is iterated, so id() from
    one pass never matches id() from the next, and a lookup that returned None for
    everything made None == None exclude every target on the board."""
    tracks = [t for t in board.GetTracks() if t.GetNetCode() == netcode]
    pads = [q for fp in board.Footprints() for q in fp.Pads() if q.GetNetCode() == netcode]
    nodes = tracks + pads
    par = list(range(len(nodes)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def union(i, j):
        par[find(i)] = find(j)

    def seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def geom(n):
        if n.Type() == pcbnew.PCB_PAD_T:
            return ("pad", set(n.GetLayerSet().CuStack()), n.GetBoundingBox(), None)
        if n.Type() == pcbnew.PCB_VIA_T:
            p = n.GetStart()
            return ("via", None, (p.x, p.y), via_radius(n) * 1e6)
        a, c = n.GetStart(), n.GetEnd()
        return ("trk", n.GetLayer(), (a.x, a.y, c.x, c.y), n.GetWidth() / 2)

    G = [geom(n) for n in nodes]
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = G[i], G[j]
            if a[0] == "pad" and b[0] == "pad":
                continue
            if a[0] == "pad":
                a, b = b, a
            hit = False
            if b[0] == "pad":
                if a[0] == "trk" and a[1] not in b[1]:
                    continue
                pts = [(a[2][0], a[2][1]), (a[2][2], a[2][3])] if a[0] == "trk" else [a[2]]
                hit = any(b[2].Contains(pcbnew.VECTOR2I(int(x), int(y))) for x, y in pts)
            elif a[0] == "via" and b[0] == "via":
                hit = math.hypot(a[2][0] - b[2][0], a[2][1] - b[2][1]) <= a[3] + b[3]
            elif a[0] == "via" or b[0] == "via":
                v, t = (a, b) if a[0] == "via" else (b, a)
                hit = seg_dist(v[2][0], v[2][1], *t[2]) <= v[3] + t[3]
            else:
                if a[1] != b[1]:
                    continue
                tol = a[3] + b[3]
                hit = (seg_dist(a[2][0], a[2][1], *b[2]) <= tol or
                       seg_dist(a[2][2], a[2][3], *b[2]) <= tol or
                       seg_dist(b[2][0], b[2][1], *a[2]) <= tol or
                       seg_dist(b[2][2], b[2][3], *a[2]) <= tol)
            if hit:
                union(i, j)
    # zone-fill islands join every via/pad that lands inside them on that layer
    for z in board.Zones():
        if z.GetNetCode() != netcode or z.GetIsRuleArea():
            continue
        for layer in z.GetLayerSet().CuStack():
            ps = z.GetFilledPolysList(layer)
            for k in range(ps.OutlineCount()):
                inside = []
                for i, n in enumerate(nodes):
                    g = G[i]
                    if g[0] == "trk":
                        continue
                    if g[0] == "pad" and layer not in g[1]:
                        continue
                    p = n.GetPosition() if g[0] == "pad" else n.GetStart()
                    if ps.Contains(p, k):
                        inside.append(i)
                for i in inside[1:]:
                    union(inside[0], i)
    roots = {}
    out = {}
    for i, n in enumerate(nodes):
        r = find(i)
        out[n.m_Uuid.AsString()] = roots.setdefault(r, len(roots))
    out["_n"] = len(roots)
    return out


def keepouts(board, grid, cu_layers, block, viab, clr, edge_clr):
    """Rule areas and Edge.Cuts geometry are obstacles on every layer they touch.

    Neither is copper, so collect() never sees them, and the first routes past the
    mounting holes went straight through the hole and its keepout - seven
    copper_edge_clearance and nine items_not_allowed errors. A rule area blocks
    tracks AND vias on its layers; an edge cut (the outline, a screw hole drawn as a
    circle) blocks within the board's copper-to-edge clearance on every layer."""
    lidx = {l: k for k, l in enumerate(cu_layers)}
    zones = list(board.Zones()) + [z for fp in board.Footprints() for z in fp.Zones()]
    for z in zones:
        if not z.GetIsRuleArea():
            continue
        bb = z.GetBoundingBox()
        cx, cy = bb.GetCenter().x / 1e6, bb.GetCenter().y / 1e6
        w, h = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
        lays = [l for l in z.GetLayerSet().CuStack() if l in lidx] or list(lidx)
        for l in lays:
            grid.rect(block[lidx[l]], cx, cy, w, h, 0, clr)
        grid.rect(viab, cx, cy, w, h, 0, clr)
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        sh = d.GetShape() if hasattr(d, "GetShape") else None
        if sh == pcbnew.SHAPE_T_CIRCLE:
            c = d.GetCenter(); r = d.GetRadius() / 1e6
            for k in range(len(cu_layers)):
                grid.capsule(block[k], c.x / 1e6, c.y / 1e6, c.x / 1e6, c.y / 1e6, r + edge_clr)
            grid.capsule(viab, c.x / 1e6, c.y / 1e6, c.x / 1e6, c.y / 1e6, r + edge_clr + VIA_DIA / 2)
        elif sh in (pcbnew.SHAPE_T_SEGMENT, pcbnew.SHAPE_T_ARC):
            a, b = d.GetStart(), d.GetEnd()
            for k in range(len(cu_layers)):
                grid.capsule(block[k], a.x / 1e6, a.y / 1e6, b.x / 1e6, b.y / 1e6, edge_clr)
            grid.capsule(viab, a.x / 1e6, a.y / 1e6, b.x / 1e6, b.y / 1e6, edge_clr + VIA_DIA / 2)


def route_one(board, grid, cu_layers, src_pad, items, holes, rules, pending_pads,
              stitch=False):
    clr, hole_clr, h2h = rules
    mynet = src_pad.GetNetCode()
    trk_inf = clr + TRACK_W / 2
    via_inf = max(clr + VIA_DIA / 2, hole_clr + VIA_DRILL / 2)
    nL = len(cu_layers)
    lidx = {l: k for k, l in enumerate(cu_layers)}

    block = [grid.blank() for _ in range(nL)]
    viab = grid.blank()
    tgt = [grid.blank() for _ in range(nL)]

    cl = clusters_of(board, mynet)
    my_cluster = cl.get(src_pad.m_Uuid.AsString())
    assert my_cluster is not None, "source pad not in its own net's cluster map"

    for nc, lst in items.items():
        friend = (nc == mynet)
        for layer, kind, args, src in lst:
            k = lidx.get(layer)
            if k is None:
                continue
            if friend and src is not None and cl.get(src) == my_cluster:
                continue                # already joined to the source: not a target
            if friend:
                if kind == "cap":
                    grid.capsule(tgt[k], *args)
                else:
                    grid.rect(tgt[k], *args, 0.0)
            else:
                if kind == "cap":
                    x1, y1, x2, y2, rr = args
                    grid.capsule(block[k], x1, y1, x2, y2, rr + trk_inf)
                    grid.capsule(viab, x1, y1, x2, y2, rr + via_inf)
                else:
                    cx, cy, w, h, ang = args
                    grid.rect(block[k], cx, cy, w, h, ang, trk_inf)
                    grid.rect(viab, cx, cy, w, h, ang, via_inf)
    for (hx, hy, hr) in holes:
        grid.capsule(viab, hx, hy, hx, hy, hr + h2h + VIA_DRILL / 2)
    keepouts(board, grid, cu_layers, block, viab, clr + TRACK_W / 2,
             board.GetDesignSettings().m_CopperEdgeClearance / 1e6 + TRACK_W / 2)
    # NO VIA IN ANY PAD, same net or not. Other-net pads are already in viab with
    # full clearance; a same-net pad is not an electrical obstacle, but an unfilled
    # via inside a solder pad wicks the joint dry during reflow, and the first pass
    # of this put one on the corner of an 0402. A via must clear every pad's copper.
    for fp in board.Footprints():
        for pad in fp.Pads():
            kind, args = pad_shape(pad)
            if kind == "cap":
                x1, y1, x2, y2, rr = args
                grid.capsule(viab, x1, y1, x2, y2, rr + VIA_DIA / 2 + 0.05)
            else:
                cx, cy, w, h, ang = args
                grid.rect(viab, cx, cy, w, h, ang, VIA_DIA / 2 + 0.05)

    # A pad still waiting to be routed is not a valid target - joining two unrouted
    # pads leaves both disconnected from the net. PER PAD, not per footprint: the
    # first version excluded every pad of any footprint with a pending pad, so
    # routing R50.1 to U14.2 was refused because U14.1 was pending on a different
    # net, and five short links "had no path".
    for fp in board.Footprints():
        for pad in fp.Pads():
            if f"{fp.GetReference()}.{pad.GetNumber()}" not in pending_pads:
                continue
            if pad.GetNetCode() != mynet:
                continue
            kind, args = pad_shape(pad)
            m = grid.blank()
            if kind == "cap":
                grid.capsule(m, *args)
            else:
                grid.rect(m, *args, 0.0)
            for l in pad.GetLayerSet().CuStack():
                k = lidx.get(l)
                if k is None:
                    continue
                t = tgt[k]
                for idx, v in enumerate(m):
                    if v:
                        t[idx] = 0

    starts = []
    kind, args = pad_shape(src_pad)
    sm = grid.blank()
    if kind == "cap":
        grid.capsule(sm, *args)
    else:
        grid.rect(sm, *args, 0.0)
    for l in src_pad.GetLayerSet().CuStack():
        k = lidx.get(l)
        if k is None:
            continue
        for idx, v in enumerate(sm):
            if v:
                starts.append((k, idx))
                block[k][idx] = 0
    if not starts:
        return None, "source pad is outside the grid"

    if stitch:
        src_layers = {lidx[l] for l in src_pad.GetLayerSet().CuStack() if l in lidx}
        for k in range(nL):
            t = tgt[k]
            for idx in range(grid.n):
                t[idx] = 1 if (k in src_layers and not viab[idx]
                               and not block[k][idx]) else 0

    INF = float("inf")
    n, nx = grid.n, grid.nx
    dist = [INF] * (n * nL)
    prev = {}
    pq = []
    for (k, idx) in starts:
        f = k * n + idx
        if dist[f] != 0.0:
            dist[f] = 0.0
            heapq.heappush(pq, (0.0, f))
    D = STEP
    DD = STEP * 1.4142135623730951
    goal = None
    while pq:
        d, f = heapq.heappop(pq)
        if d > dist[f]:
            continue
        k, idx = divmod(f, n)
        if d > 0.0 and tgt[k][idx]:
            goal = f
            break
        j, i = divmod(idx, nx)
        bk = block[k]
        for di, dj, w in ((-1, 0, D), (1, 0, D), (0, -1, D), (0, 1, D),
                          (-1, -1, DD), (1, -1, DD), (-1, 1, DD), (1, 1, DD)):
            ni, nj = i + di, j + dj
            if ni < 0 or nj < 0 or ni >= nx or nj >= grid.ny:
                continue
            nidx = nj * nx + ni
            if bk[nidx]:
                continue
            nf = k * n + nidx
            nd = d + w
            if nd < dist[nf]:
                dist[nf] = nd
                prev[nf] = f
                heapq.heappush(pq, (nd, nf))
        if stitch or viab[idx]:
            continue
        for nk in range(nL):
            if nk == k or block[nk][idx]:
                continue
            nf = nk * n + idx
            nd = d + VIA_COST_MM
            if nd < dist[nf]:
                dist[nf] = nd
                prev[nf] = f
                heapq.heappush(pq, (nd, nf))
    if goal is None:
        # say how far the search got, per layer, so a failure is diagnosable
        reach = {}
        for k in range(nL):
            xs = [i for j in range(grid.ny) for i in range(nx)
                  if dist[k * n + j * nx + i] < INF]
            if xs:
                ys = [j for j in range(grid.ny) for i in range(nx)
                      if dist[k * n + j * nx + i] < INF]
                reach[board.GetLayerName(cu_layers[k])] = (
                    len(xs), round(grid.x0 + min(xs) * STEP, 1), round(grid.x0 + max(xs) * STEP, 1),
                    round(grid.y0 + min(ys) * STEP, 1), round(grid.y0 + max(ys) * STEP, 1))
        nvia = sum(1 for idx in range(n) if not viab[idx])
        return None, (f"no path exists on any layer; reached "
                      f"{ {k: f'{v[0]} cells x{v[1]}..{v[2]} y{v[3]}..{v[4]}' for k, v in reach.items()} }; "
                      f"{nvia} via-legal cells in window")
    path = [goal]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    return [(divmod(f % n, nx)[1], divmod(f % n, nx)[0], f // n) for f in path], None


def emit(board, grid, cu_layers, path, netcode, stitch=False):
    V = lambda x, y: pcbnew.VECTOR2I(int(round(x * 1e6)), int(round(y * 1e6)))
    net = board.FindNet(board.GetNetInfo().GetNetItem(netcode).GetNetname())
    runs, cur = [], [path[0]]
    for a, b in zip(path, path[1:]):
        if a[2] != b[2]:
            runs.append(("trk", cur))
            runs.append(("via", a))
            cur = [b]
        else:
            cur.append(b)
    runs.append(("trk", cur))
    if stitch:
        runs.append(("via", path[-1]))
    n_t = n_v = 0
    for r in runs:
        if r[0] == "via":
            i, j, _ = r[1]
            x, y = grid.xy(i, j)
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(V(x, y))
            v.SetDrill(int(VIA_DRILL * 1e6))
            v.SetWidth(int(VIA_DIA * 1e6))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(net)
            board.Add(v)
            n_v += 1
            continue
        cells = r[1]
        if len(cells) < 2:
            continue
        layer = cu_layers[cells[0][2]]
        pts = [grid.xy(i, j) for (i, j, _) in cells]
        keep = [pts[0]]
        for p in range(1, len(pts) - 1):
            ax, ay = pts[p - 1]
            bx, by = pts[p]
            cx, cy = pts[p + 1]
            if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-9:
                keep.append(pts[p])
        keep.append(pts[-1])
        for a, b in zip(keep, keep[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(V(*a))
            t.SetEnd(V(*b))
            t.SetWidth(int(TRACK_W * 1e6))
            t.SetLayer(layer)
            t.SetNet(net)
            board.Add(t)
            n_t += 1
    return n_t, n_v


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    board = pcbnew.LoadBoard(BOARD)
    ds = board.GetDesignSettings()
    rules = (ds.m_MinClearance / 1e6, ds.m_HoleClearance / 1e6,
             ds.m_HoleToHoleMin / 1e6)
    cu_layers = [l for l in board.GetEnabledLayers().CuStack()
                 if board.GetLayerName(l) not in NO_ROUTE_LAYERS]
    bb = board.GetBoardEdgesBoundingBox()

    pads = []
    for spec in argv:
        ref, num = spec.rstrip("^").split(".")
        fp = board.FindFootprintByReference(ref)
        assert fp, f"no footprint {ref}"
        pads.append((spec, ref, next(p for p in fp.Pads() if p.GetNumber() == num)))

    xs = [p.GetPosition().x / 1e6 for _, _, p in pads]
    ys = [p.GetPosition().y / 1e6 for _, _, p in pads]
    gx0 = max(bb.GetLeft() / 1e6 + EDGE_KEEP, min(xs) - WINDOW_MM)
    gy0 = max(bb.GetTop() / 1e6 + EDGE_KEEP, min(ys) - WINDOW_MM)
    gx1 = min(bb.GetRight() / 1e6 - EDGE_KEEP, max(xs) + WINDOW_MM)
    gy1 = min(bb.GetBottom() / 1e6 - EDGE_KEEP, max(ys) + WINDOW_MM)
    grid = Grid(gx0, gy0, gx1, gy1)
    print(f"grid {grid.nx}x{grid.ny} @ {STEP} mm, {len(cu_layers)} layers, "
          f"clearance {rules[0]} / hole {rules[1]} / hole-to-hole {rules[2]} mm")

    pending = {spec.rstrip("^") for spec, _, _ in pads}
    ok = True
    for spec, ref, pad in pads:
        items, holes = collect(board, cu_layers)
        pending.discard(spec.rstrip("^"))
        st = spec.endswith("^")
        path, err = route_one(board, grid, cu_layers, pad, items, holes,
                              rules, pending | {spec.rstrip("^")}, stitch=st)
        if path is None:
            print(f"  {spec:8} [{pad.GetNetname():10}] FAILED: {err}")
            ok = False
            continue
        n_t, n_v = emit(board, grid, cu_layers, path, pad.GetNetCode(), stitch=st)
        print(f"  {spec:8} [{pad.GetNetname():10}] {n_t} segment(s), {n_v} via(s)")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(BOARD)
    print("saved")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
