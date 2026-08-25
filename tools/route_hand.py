#!/usr/bin/env python3
"""
Hand-style routing: finish each net by landing on whatever copper it already has.

The staged router routes pad-to-pad and converged at 64%. A person routing this board
would not do that - they would run the trace to the nearest point of the net's existing
copper. This does the same: for every still-separate pair, the goal is EVERY cell of the
target component, not one nominated pad, which turns each already-routed track into a
landing site instead of an obstacle.

DRC is checked after each net and the net is rolled back if it introduced an error, so
progress is monotonic.

Usage: python3 tools/route_hand.py [rounds]
"""
import os, sys, math, shutil, subprocess, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/navcore_hand_backup.kicad_pcb"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/hand_drc.rpt",
                    "--severity-error", BOARD], capture_output=True, timeout=300)
    rpt = open("/tmp/hand_drc.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', rpt, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def components(board):
    """Geometric union-find over pads and track endpoints, spatially bucketed."""
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    Q = lambda v: round(v / 1000.0)
    for t in board.GetTracks():
        p = t.GetPosition()
        if t.Type() == pcbnew.PCB_VIA_T:
            union(("N", Q(p.x), Q(p.y)), ("V", Q(p.x), Q(p.y)))
        else:
            a, c = t.GetStart(), t.GetEnd()
            union(("N", Q(a.x), Q(a.y)), ("N", Q(c.x), Q(c.y)))
    BK = 2000
    grid = {}
    for k in list(parent):
        if k[0] in ("N", "V"):
            grid.setdefault((k[1] // BK, k[2] // BK), []).append(k)
    padkey, padpos = {}, {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if not (pad.GetNet() and pad.GetNet().GetNetCode()): continue
            u = pad.m_Uuid.AsString()
            k = ("P", u); find(k); padkey[u] = k
            p = pad.GetPosition(); padpos[u] = (route.TOMM(p.x), route.TOMM(p.y))
            bb = pad.GetBoundingBox()
            x0, y0 = Q(bb.GetLeft()), Q(bb.GetTop())
            x1, y1 = Q(bb.GetRight()), Q(bb.GetBottom())
            for bi in range(x0 // BK, x1 // BK + 1):
                for bj in range(y0 // BK, y1 // BK + 1):
                    for n in grid.get((bi, bj), ()):
                        if x0 <= n[1] <= x1 and y0 <= n[2] <= y1:
                            union(k, n)
    # every node's position in mm, so a component can be turned into goal cells
    pos = {k: (k[1] / 1000.0 * 1.0, k[2] / 1000.0 * 1.0) for k in parent if k[0] in ("N", "V")}
    for u, k in padkey.items(): pos[k] = padpos[u]
    return parent, find, padkey, padpos, pos


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    hard0, un0 = drc()
    print(f"baseline: {hard0} hard DRC errors, {un0} unconnected\n")
    print(f"{'round':>5} {'attempted':>10} {'routed':>7} {'failed':>7} {'unconn':>8}")
    print("-" * 44)

    for rnd in range(1, rounds + 1):
        shutil.copy(BOARD, BAK)
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        parent, find, padkey, padpos, pos = components(board)

        bynet = {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                n = pad.GetNet()
                if not n or not n.GetNetCode() or n.GetNetname() in route.PLANE: continue
                bynet.setdefault(n.GetNetname(), []).append(pad)

        jobs = []
        for nn, ps in bynet.items():
            if len(ps) < 2: continue
            groups = {}
            for p in ps:
                groups.setdefault(find(padkey[p.m_Uuid.AsString()]), []).append(p)
            gl = list(groups.values())
            if len(gl) < 2: continue
            for i in range(len(gl) - 1):
                jobs.append((nn, gl[i][0], find(padkey[gl[i+1][0].m_Uuid.AsString()])))

        if not jobs:
            print(f"{rnd:>5}  nothing left"); break

        r = route.Router(board)
        # every node belonging to each component, so a whole component can be a goal
        comp_nodes = {}
        for k in list(parent):
            comp_nodes.setdefault(find(k), []).append(k)

        routed = failed = 0
        for nn, pa, root in jobs:
            net = board.FindNet(nn)
            if net is None: continue
            code = net.GetNetCode()
            pts = [pos[k] for k in comp_nodes.get(root, []) if k in pos]
            goals = r.cells_of_net(code, pts)
            if not goals:
                failed += 1; continue
            A = (route.TOMM(pa.GetPosition().x), route.TOMM(pa.GetPosition().y))
            path = None
            for vc in (12, 5, 25):
                path = r.route_to_any(code, A, goals, via_cost=vc)
                if path: break
            if not path:
                failed += 1; continue
            # Verify PER NET. A whole-round rollback threw away 9 good routes because
            # 5 others introduced errors; monotonic progress needs finer granularity.
            r.commit(code, net, path)
            route.fill(board); board.Save(BOARD)
            h, u = drc()
            if h > hard0:
                shutil.copy(BAK, BOARD)
                board = pcbnew.LoadBoard(BOARD); route.set_rules(board)
                r = route.Router(board)
                failed += 1
            else:
                shutil.copy(BOARD, BAK)
                routed += 1

        hard, un = drc()
        print(f"{rnd:>5} {len(jobs):>10} {routed:>7} {failed:>7} {un:>8}"
              + ("" if hard <= hard0 else f"   ROLLED BACK (+{hard-hard0} err)"))
        if routed == 0:
            print("      converged"); break

    hard, un = drc()
    print("-" * 44)
    print(f"final: {hard} hard DRC errors, {un} unconnected")


if __name__ == "__main__":
    main()
