#!/usr/bin/env python3
"""A* maze router for the last connections, on F.Cu and B.Cu, using KiCad's collision engine.

tools/route_last_two.py could only try a straight or L-shaped run to a candidate via, and
reported "no clear via" when what it really meant was "no via I can reach in two segments".
Free via sites exist all round U18 - the copper between them is the problem. So this does
the real thing: a grid, an A* search over both outer layers with via transitions, and the
blocked map built by asking pcbnew whether a track centred on each cell would collide.

    python3 tools/maze_route.py --dry
    python3 tools/maze_route.py
"""
import argparse, heapq, os, sys
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from route_last_two import Board, mm, CLEAR, VIA_D, VIA_DRILL, TRACK_W

STEP = 0.05                      # grid pitch, mm; 0.10 is enough for open work

# F.Cu COSTS MORE THAN B.Cu, on purpose. The first route this found ran 2.7 mm across
# the F.Cu ground pour before dropping to the back layer, and that cut U18's GND pad
# off onto a floating 2.37 mm^2 island with no via to the inner planes - the 9 V
# regulator would have had no ground return. F.Cu here is mostly poured GND, so every
# millimetre of it is a slit in the plane. Penalising it makes the router take the
# shortest escape to a via and do its travelling on B.Cu.
LAYER_COST = {}      # filled in main(): F.Cu expensive, B.Cu cheap

# Per-layer keepouts, as (layer, x0, x1, y0, y1) rectangles the router may not enter.
#
# WHICH SIDE the escape leaves U18.2 on decides whether the ground pour survives. The
# router's cheapest path dropped down the LEFT of the corridor, at x ~ 130.1, which
# closed U18.1's ground off from the main pour and stranded it on a 2.37 mm^2 island
# with no via to the inner planes. A free via site also exists on the RIGHT at
# (131.2, 124.27); leaving that way keeps U18.1's link to the pour open. So F.Cu is
# fenced off left of x = 130.25 and the escape has to take the right-hand route.
KEEPOUT = []

def build(bd, net, box, layers):
    x0, x1, y0, y1 = box
    nx = int(round((x1 - x0) / STEP)) + 1
    ny = int(round((y1 - y0) / STEP)) + 1
    def P(i, j): return (round(x0 + i * STEP, 3), round(y0 + j * STEP, 3))

    free = {l: bytearray(nx * ny) for l in layers}
    for l in layers:
        f = free[l]
        for j in range(ny):
            for i in range(nx):
                p = P(i, j)
                t = bd.seg(p, (p[0] + 1e-4, p[1]), l, net, TRACK_W)
                sh = t.GetEffectiveShape(l)
                ok = not any(it.GetNetname() != net
                             and sh.Collide(it.GetEffectiveShape(l), mm(CLEAR))
                             for it in bd.near(sh, l, mm(CLEAR)))
                if ok:
                    for kl, kx0, kx1, ky0, ky1 in KEEPOUT:
                        if kl == l and kx0 <= p[0] <= kx1 and ky0 <= p[1] <= ky1:
                            ok = False; break
                f[j * nx + i] = 1 if ok else 0
    viaok = bytearray(nx * ny)
    for j in range(ny):
        for i in range(nx):
            if not all(free[l][j * nx + i] for l in layers): continue
            v = bd.via(P(i, j), net)
            ok = True
            for l in bd.layers:
                sh = v.GetEffectiveShape(l)
                if any(it.GetNetname() != net
                       and sh.Collide(it.GetEffectiveShape(l), mm(CLEAR))
                       for it in bd.near(sh, l, mm(CLEAR))):
                    ok = False; break
            viaok[j * nx + i] = 1 if ok else 0
    return nx, ny, P, free, viaok

def astar(nx, ny, free, viaok, layers, starts, goals):
    VIA_COST = 12.0
    def h(n):
        i, j, _ = n
        cheapest = min(LAYER_COST.values()) if LAYER_COST else 1.0
        return min(abs(i - gi) + abs(j - gj) for gi, gj, _ in goals) * cheapest
    dist = {}
    pq = []
    for s in starts:
        dist[s] = 0.0
        heapq.heappush(pq, (h(s), 0.0, s, None))
    prev = {}
    goalset = set(goals)
    while pq:
        f, g, n, par = heapq.heappop(pq)
        if n in prev and dist.get(n, 1e18) < g: continue
        prev[n] = par
        if n in goalset:
            path = []
            while n is not None:
                path.append(n); n = prev[n]
            return path[::-1]
        i, j, l = n
        lc = LAYER_COST.get(l, 1.0)
        for di, dj, c in ((1,0,1.0), (-1,0,1.0), (0,1,1.0), (0,-1,1.0),
                          (1,1,1.414), (1,-1,1.414), (-1,1,1.414), (-1,-1,1.414)):
            c *= lc
            a, b = i + di, j + dj
            if not (0 <= a < nx and 0 <= b < ny): continue
            if not free[l][b * nx + a]: continue
            if di and dj:      # no diagonal squeeze between two blocked orthogonals
                if not (free[l][j * nx + a] and free[l][b * nx + i]): continue
            m = (a, b, l)
            ng = g + c * STEP
            if ng < dist.get(m, 1e18):
                dist[m] = ng
                heapq.heappush(pq, (ng + h(m) * STEP, ng, m, n))
        if viaok[j * nx + i]:
            for l2 in layers:
                if l2 == l: continue
                m = (i, j, l2)
                ng = g + VIA_COST * STEP
                if ng < dist.get(m, 1e18):
                    dist[m] = ng
                    heapq.heappush(pq, (ng + h(m) * STEP, ng, m, n))
    return None

def snap(bd, nx, ny, P, free, pt, layer, net, maxr=12):
    """Nearest free grid node to an arbitrary point, reachable by a clear stub."""
    bi = min(range(nx), key=lambda i: abs(P(i, 0)[0] - pt[0]))
    bj = min(range(ny), key=lambda j: abs(P(0, j)[1] - pt[1]))
    out = []
    for r in range(maxr):
        for j in range(max(0, bj - r), min(ny, bj + r + 1)):
            for i in range(max(0, bi - r), min(nx, bi + r + 1)):
                if max(abs(i - bi), abs(j - bj)) != r: continue
                if not free[layer][j * nx + i]: continue
                q = P(i, j)
                sh = bd.seg(pt, q, layer, net, TRACK_W).GetEffectiveShape(layer)
                if not any(it.GetNetname() != net
                           and sh.Collide(it.GetEffectiveShape(layer), mm(CLEAR))
                           for it in bd.near(sh, layer, mm(CLEAR))):
                    out.append((i, j, layer))
        if out: return out
    return out

def route(bd, net, start, start_layer, goal, goal_layer, box, layers=None):
    # A single-layer call gets no via transitions, which is what a pour bridge wants.
    layers = layers or [pcbnew.F_Cu, pcbnew.B_Cu]
    print(f"   building grid over {box} at {STEP} mm ...")
    nx, ny, P, free, viaok = build(bd, net, box, layers)
    nfree = {bd.b.GetLayerName(l): sum(free[l]) for l in layers}
    print(f"   {nx}x{ny} nodes; free {nfree}; via sites {sum(viaok)}")
    starts = snap(bd, nx, ny, P, free, start, start_layer, net)
    goals  = snap(bd, nx, ny, P, free, goal,  goal_layer,  net)
    if not starts or not goals:
        print("   could not reach the grid from the pad/track"); return None
    path = astar(nx, ny, free, viaok, layers, starts, goals)
    if not path:
        print("   no path"); return None
    # EMIT EVERY BEND. This built a polyline of the path's corners and then appended
    # only (run[0], run[-1]) - the first and last point - throwing away every bend in
    # between and drawing one straight line across copper the search had just spent
    # 6500 nodes avoiding. Segments are emitted pairwise, and each one is re-checked
    # against the collision engine before it is returned.
    segs, vias = [], []
    pts = [(P(i, j), l) for i, j, l in path]
    segs.append((start, pts[0][0], start_layer))
    cur = pts[0]
    run = [cur[0]]

    def flush(pointlist, layer):
        for a, b_ in zip(pointlist, pointlist[1:]):
            if a != b_: segs.append((a, b_, layer))

    for q, l in pts[1:]:
        if l != cur[1]:
            flush(run, cur[1])
            vias.append(q)
            run = [q]; cur = (q, l)
            continue
        if len(run) >= 2:
            ax, ay = run[-1][0]-run[-2][0], run[-1][1]-run[-2][1]
            bx, by = q[0]-run[-1][0], q[1]-run[-1][1]
            if abs(ax*by - ay*bx) < 1e-9:
                run[-1] = q; cur = (q, l); continue
        run.append(q); cur = (q, l)
    flush(run, cur[1])
    segs.append((pts[-1][0], goal, goal_layer))

    bad = [s for s in segs if s[0] != s[1]
           and not bd.clear(bd.seg(s[0], s[1], s[2], net, TRACK_W)
                            .GetEffectiveShape(s[2]), s[2], net)]
    if bad:
        print(f"   REJECTED: {len(bad)} emitted segment(s) collide - not writing")
        for s in bad: print(f"      {bd.b.GetLayerName(s[2])} {s[0]} -> {s[1]}")
        return None
    return segs, vias

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "NAVCORE-SoOP.kicad_pcb")
    bd = Board(path)
    LAYER_COST.update({pcbnew.F_Cu: 6.0, pcbnew.B_Cu: 1.0})
    jobs = [("BUCK9_PH", (130.500, 122.369), pcbnew.F_Cu,
             (128.487, 122.969), pcbnew.B_Cu, (126.0, 133.5, 118.5, 127.0))]
    out = []
    for net, s, sl, g, gl, box in jobs:
        print(f"\n{net}: {s} ({bd.b.GetLayerName(sl)}) -> {g} ({bd.b.GetLayerName(gl)})")
        r = route(bd, net, s, sl, g, gl, box)
        if r:
            segs, vias = r
            print(f"   {len(segs)} segments, {len(vias)} via(s)")
            for x, y, l in segs:
                print(f"      {bd.b.GetLayerName(l):5s} {x} -> {y}")
            for v in vias: print(f"      VIA {v}")
            out.append((net, segs, vias))
    if a.dry or not out:
        print("\n(dry run)" if a.dry else "\nnothing routed"); return 0
    for net, segs, vias in out:
        for x, y, l in segs:
            if x != y: bd.b.Add(bd.seg(x, y, l, net, TRACK_W))
        for v in vias: bd.b.Add(bd.via(v, net))
    pcbnew.ZONE_FILLER(bd.b).Fill(bd.b.Zones())
    bd.b.Save(path)
    print(f"\nwrote {len(out)} connection(s)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
