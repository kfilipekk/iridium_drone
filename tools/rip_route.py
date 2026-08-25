#!/usr/bin/env python3
"""
Rip out the trace that fences in the last ground island, and route it again elsewhere.

One 1.52 mm2 sliver of the B.Cu ground pour is still sealed - the flood from inside it
reaches exactly its own 3001 cells and no more - and it carries C71.2, the ground end of
the 9 V buck's compensation capacitor. That is not decoration: an ungrounded
compensation cap leaves the regulator's control loop without its reference.

A via fits nowhere inside it. The nearest position is short by 0.085 mm, held by
BUCK_EN on B.Cu, and BUCK_EN cannot be shoved because C71's and C72's own pads box it
in on both sides. Shoving has run out of room.

So stop trying to nudge it and take it out. A shove is a local detour that keeps a
trace's shape; a rip-up throws the route away and finds a new one, which is a far
bigger move and the standard answer when a board is this full. Both endpoints are put
back exactly where they were, so whatever the trace connected to stays connected, and
the new route is found on the same 0.02 mm grid the island search uses - with the new
via already in place as an obstacle, so the reroute cannot simply take the space back.

Every attempt is written, checked by whole-board DRC, and reverted unless it both keeps
the error count at zero and reduces the unconnected count.

Usage:  python3 tools/rip_route.py [--apply] [--grid MM] [--tries N]
"""
import os, sys, math, shutil, subprocess, re
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heapq
import pcbnew, route, shove, island_route as ir, island_via as iv

SIG = ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu")   # In1/In4 are planes, never routed

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/rr2_backup.kicad_pcb"
RPT   = "/tmp/nav/rr2.rpt"
TOMM  = route.TOMM
NET   = "GND"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def chain_shapes(ch):
    """A chain's own copper, so it can be taken out of the obstacle set."""
    out = []
    for i in range(len(ch["pts"]) - 1):
        p, q = ch["pts"][i], ch["pts"][i+1]
        out.append(shove.Shape(("cap", p[0], p[1], q[0], q[1], ch["width"]/2),
                               "track", ch["net"], layer=ch["layer"],
                               width=ch["width"], p1=p, p2=q,
                               lset=frozenset([ch["layer"]])))
    return out


def reroute(board, ch, allsh, extra, step, pad=10.0, via_cost=40,
            via_d=0.45, drill=0.20):
    """Find a new path for a ripped chain, endpoints unchanged.

    Routes across all four signal layers rather than the one the trace started on.
    Staying on its own layer was not enough: BUCK_EN's two endpoints have no path
    between them on B.Cu at all once the new via is in place, so a same-layer reroute
    can only ever fail here. With layer changes allowed it can dive under the
    congestion and come back up.

    `extra` is copper that did not exist when the chain was first routed - the new via
    - so the reroute cannot take back the space the via now needs.

    `allsh` must be EVERY net's copper, not the island search's set. That set excludes
    GND, which is right when routing ground out of a ground island and badly wrong when
    routing a signal: a rerouted BUCK_EN has to clear ground tracks and ground pads like
    any other foreign copper. Ground ZONE fill is not in the set either way - the pour
    refills around whatever is placed.
    """
    a, b = ch["pts"][0], ch["pts"][-1]
    box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
    mine = {(sh.p1, sh.p2) for sh in chain_shapes(ch)}
    keep = [sh for sh in allsh
            if not (sh.layer == ch["layer"] and sh.p1 is not None
                    and (sh.p1, sh.p2) in mine)]
    keep = [sh for sh in keep if sh.net != ch["net"]] + list(extra)
    kidx = shove.ShapeIndex(keep)
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)
    grids = [ir.Grid(board, L, box, step, keep, pad) for L in SIG]
    g0 = grids[0]
    home = SIG.index(ch["layer"]) if ch["layer"] in SIG else 0
    ca, cb = g0.cell(*a), g0.cell(*b)

    # An endpoint that sits on a via of this net may be left on ANY layer - the via
    # already ties the whole stack together. Pinning both ends to the layer the trace
    # happened to use is what made BUCK_EN look unroutable: its start is its own via,
    # boxed into a 2.8 mm2 pocket on B.Cu with no room for a second via, but perfectly
    # open on In2.Cu and In3.Cu one layer down.
    own_vias = [(TOMM(t.GetPosition().x), TOMM(t.GetPosition().y))
                for t in board.GetTracks()
                if t.Type() == pcbnew.PCB_VIA_T and t.GetNet()
                and t.GetNet().GetNetname() == ch["net"]]
    def free_layers(p, cell):
        onvia = any(math.hypot(p[0]-vx, p[1]-vy) < 0.05 for vx, vy in own_vias)
        opts = range(len(SIG)) if onvia else [home]
        return [li for li in opts if grids[li].ok(*cell)]
    starts, goals = free_layers(a, ca), free_layers(b, cb)
    if not starts or not goals:
        return None, "an endpoint has no legal cell once the via is in place"

    need = via_d/2 + route.VIA_CLEAR + 0.005
    vcache = {}
    def via_ok(i, j):
        if (i, j) not in vcache:
            x, y = g0.pos(i, j)
            ok = route.inside_board(x, y, via_d/2 + 0.35) \
                and route.hole_ok(x, y, holes, drill) \
                and not any(x1 - via_d/2 < x < x2 + via_d/2 and
                            y1 - via_d/2 < y < y2 + via_d/2
                            for x1, y1, x2, y2 in kos) \
                and not any(route.gap_to_shape(x, y, sh.geom) < need
                            for sh in kidx.near(x, y, need + 1.0))
            vcache[(i, j)] = ok
        return vcache[(i, j)]

    goalset = {(li,) + cb for li in goals}
    dist, prev, pq = {}, {}, []
    for li in starts:
        st = (li,) + ca
        dist[st] = 0; prev[st] = None
        heapq.heappush(pq, (0, st))
    h = lambda n: abs(n[1] - cb[0]) + abs(n[2] - cb[1])
    goal = None
    while pq:
        f, cur = heapq.heappop(pq)
        if cur in goalset:
            goal = cur
            break
        d = dist[cur]
        if f - h(cur) > d:
            continue
        li, i, j = cur
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = (li, i+di, j+dj)
            if not grids[li].ok(i+di, j+dj):
                continue
            nd = d + (14 if di and dj else 10)
            if nd < dist.get(nb, 1 << 60):
                dist[nb] = nd; prev[nb] = cur
                heapq.heappush(pq, (nd + h(nb)*10, nb))
        if via_ok(i, j):
            for lj in range(len(SIG)):
                if lj == li or not grids[lj].ok(i, j):
                    continue
                nb = (lj, i, j)
                nd = d + via_cost*10
                if nd < dist.get(nb, 1 << 60):
                    dist[nb] = nd; prev[nb] = cur
                    heapq.heappush(pq, (nd + h(nb)*10, nb))
    if goal is None:
        return None, "no path between its endpoints on any signal layer"

    node, seq = goal, []
    while node is not None:
        seq.append(node); node = prev[node]
    seq.reverse()
    # split into per-layer runs; a layer change becomes a via
    runs, vias, cur_l, buf = [], [], seq[0][0], []
    for (li, i, j) in seq:
        if li != cur_l:
            runs.append((SIG[cur_l], shove.straighten([g0.pos(*c[1:]) for c in buf])))
            vias.append(g0.pos(i, j))
            cur_l, buf = li, []
        buf.append((li, i, j))
    runs.append((SIG[cur_l], shove.straighten([g0.pos(*c[1:]) for c in buf])))
    runs = [(lay, list(pts)) for lay, pts in runs]
    runs[0][1][0] = a
    runs[-1][1][-1] = b        # pin the endpoints to the exact original points
    n_seg = sum(len(r[1]) - 1 for r in runs)
    return (runs, vias), (f"{n_seg} segments, {len(vias)} via(s), "
                          f"{dist[goal]/10*step:.2f} mm")


def main():
    apply = "--apply" in sys.argv
    step = float(sys.argv[sys.argv.index("--grid")+1]) if "--grid" in sys.argv else 0.02
    tries = int(sys.argv[sys.argv.index("--tries")+1]) if "--tries" in sys.argv else 8
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, _ = drc()
    print(f"baseline {hard0} errors, {un0} unconnected\n")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    route.fill(board)
    polys = ir.gnd_polys(board)
    isls = ir.orphans(board, polys)
    if not isls:
        print("no orphaned ground islands left")
        return 0
    allsh = shove.shapes_of(board, exclude_net=NET)
    idx = shove.ShapeIndex(allsh)
    # A signal being rerouted must clear ground copper too, so it gets the full set.
    allsh_full = shove.shapes_of(board)
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)
    chains, cindex = shove.build_chains(board)

    for lname, _pi, isl, a in isls:
        xs = [p[0] for p in isl]; ys = [p[1] for p in isl]
        print(f"=== {lname} {a:.2f} mm2 at ({min(xs):.2f},{min(ys):.2f})")
        g = ir.Grid(board, lname, (min(xs), min(ys), max(xs), max(ys)),
                    step, allsh, 4.0)
        src, cells = iv.pocket(g, isl)
        cands = iv.candidates(g, isl, cells, idx, holes, kos)
        print(f"    {len(cells)} cells in its pocket, {len(cands)} via positions")

        done = 0
        for nblk, _pref, x, y, via_d, drill, blk, on_isl in cands:
            if not blk or nblk > 2:
                continue
            cis = sorted({shove.chain_of(cindex, s) for s in blk})
            if any(c is None for c in cis):
                continue
            victims = [chains[c] for c in cis]
            if any(v["net"] in route.PLANE for v in victims):
                continue            # never rip a rail's own fanout
            newvia = shove.Shape(("cap", x, y, x, y, via_d/2), "via", NET)
            routes, why = [], None
            for ch in victims:
                res, note = reroute(board, ch, allsh_full, [newvia], max(step, 0.05))
                if res is None:
                    why = f"{ch['net']}/{ch['layer']}: {note}"
                    break
                routes.append((ch, res, note))
            if why:
                if done < 3:
                    print(f"    via {via_d} at ({x:.3f},{y:.3f}): {why}")
                    done += 1
                continue
            cell = g.cell(x, y)
            path = [] if on_isl else iv.track_to(g, cells, src, cell)
            if path is None:
                continue
            desc = (f"    via {via_d:.2f} at ({x:.3f},{y:.3f}), ripping "
                    + ", ".join(f"{ch['net']}/{ch['layer']} -> {note}"
                                for ch, _p, note in routes))
            print(desc)
            if not apply:
                break

            shutil.copy(BOARD, BAK)
            bd = pcbnew.LoadBoard(BOARD)
            route.set_rules(bd)
            n = bd.FindNet(NET)
            doomed_keys = set()
            for ch, _res, _note in routes:
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
            for ch, (runs, rvias) in ((c, r) for c, r, _n in routes):
                cnet = bd.FindNet(ch["net"])
                for lay, pts in runs:
                    for k in range(len(pts) - 1):
                        route.add_track(bd, pts[k], pts[k+1], lay, cnet,
                                        width=ch["width"])
                for vx, vy in rvias:
                    rv = route.add_via(bd, vx, vy, cnet)
                    rv.SetWidth(pcbnew.FromMM(0.45)); rv.SetDrill(pcbnew.FromMM(0.20))
            pp = ir.simplify(path) if path else []
            for k in range(len(pp) - 1):
                route.add_track(bd, pp[k], pp[k+1], lname, n, width=route.TRACK_W)
            v = route.add_via(bd, x, y, n)
            v.SetWidth(pcbnew.FromMM(via_d)); v.SetDrill(pcbnew.FromMM(drill))
            route.fill(bd)
            bd.Save(BOARD)
            hard, un, txt = drc()
            if hard <= hard0 and un < un0:
                print(f"       -> {un} unconnected, {hard} errors  "
                      f"({len(doomed)} segments ripped)")
                un0 = un
                break
            bad = [z for z in re.split(r'^\[', txt, flags=re.M)
                   if z and not z.startswith("unconnected_items")
                   and not z.startswith("** ")]
            print(f"       -> +{hard-hard0} err, {un} unconn"
                  + (f": {bad[0].splitlines()[0]}" if bad else ""))
            shutil.copy(BAK, BOARD)
            tries -= 1
            if tries <= 0:
                break

    hard, un, _ = drc()
    print(f"\n{hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
