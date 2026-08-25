#!/usr/bin/env python3
"""
Per-net routing: attempt every unconnected net one at a time, hardest-first, and
verify with real DRC before keeping it.

Finer-grained than route_stages.py, which accepted or rejected a whole functional
group. Here a single net that routes cleanly is kept even if its neighbours in the
same group fail. Each net also gets several attempts with different via costs, since
the A* is deterministic and one cost setting can box it in where another does not.

Usage: python3 tools/route_nets.py [drc_every]
"""
import os, sys, math, shutil, subprocess, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/navcore_net_backup.kicad_pcb"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/net_drc.rpt",
                    "--severity-error", BOARD], capture_output=True, timeout=300)
    rpt = open("/tmp/net_drc.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', rpt, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def components(board):
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
    nodes = [k for k in list(parent) if k[0] in ("N", "V")]
    padkey = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if not (pad.GetNet() and pad.GetNet().GetNetCode()): continue
            k = ("P", pad.m_Uuid.AsString()); find(k)
            padkey[pad.m_Uuid.AsString()] = k
            bb = pad.GetBoundingBox()
            x0, y0, x1, y1 = Q(bb.GetLeft()), Q(bb.GetTop()), Q(bb.GetRight()), Q(bb.GetBottom())
            for n in nodes:
                if x0 <= n[1] <= x1 and y0 <= n[2] <= y1: union(k, n)
    return padkey, find


def pending(board):
    """[(netname, netcode, padA, padB)] for every still-separate component pair."""
    padkey, find = components(board)
    plane = {n for n in route.PLANE}
    bynet = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNet()
            if not n or not n.GetNetCode() or n.GetNetname() in plane: continue
            bynet.setdefault(n.GetNetname(), []).append(pad)
    out = []
    for nn, ps in bynet.items():
        if len(ps) < 2: continue
        groups = {}
        for p in ps: groups.setdefault(find(padkey[p.m_Uuid.AsString()]), []).append(p)
        gl = list(groups.values())
        for i in range(len(gl) - 1):
            out.append((nn, ps[0].GetNet().GetNetCode(), gl[i][0], gl[i+1][0]))
    return out


def main():
    drc_every = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    shutil.copy(BOARD, BAK)
    hard0, un0 = drc()
    print(f"baseline: {hard0} hard DRC errors, {un0} unconnected")

    board = pcbnew.LoadBoard(BOARD)
    todo = pending(board)
    print(f"{len(todo)} unconnected pad pairs to attempt\n")
    print(f"{'#':>3} {'net':<16} {'result':<10} {'unconn':>7}")
    print("-" * 42)

    kept = failed = 0
    since_check = 0
    for idx, (nn, code, pa, pb) in enumerate(sorted(todo, key=lambda t: t[0]), 1):
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        # re-find the pads on the freshly loaded board by position
        A = (route.TOMM(pa.GetPosition().x), route.TOMM(pa.GetPosition().y))
        B = (route.TOMM(pb.GetPosition().x), route.TOMM(pb.GetPosition().y))
        net = board.FindNet(nn)
        if net is None: continue
        r = route.Router(board)
        path = None
        # A via cost that boxes one net in frees another. This genuinely varies the
        # search now - it used to set an attribute route() never read, so all four
        # "attempts" were the same search repeated and every net reported "no path".
        for via_cost in (12, 4, 30, 2, 60):
            r.via_cost = via_cost
            path = r.route(net.GetNetCode(), A, B)
            if path: break
        if not path:
            failed += 1
            print(f"{idx:>3} {nn:<16} {'no path':<10} {'-':>7}")
            continue
        r.commit(net.GetNetCode(), net, path)
        route.fill(board); board.Save(BOARD)
        since_check += 1
        if since_check >= drc_every:
            hard, un = drc(); since_check = 0
            if hard > hard0:
                shutil.copy(BAK, BOARD); failed += 1
                print(f"{idx:>3} {nn:<16} {'ROLLBACK':<10} {un:>7}  (+{hard-hard0} err)")
                continue
            shutil.copy(BOARD, BAK); kept += 1
            print(f"{idx:>3} {nn:<16} {'routed':<10} {un:>7}")
        else:
            kept += 1
            print(f"{idx:>3} {nn:<16} {'routed':<10} {'-':>7}")

    hard, un = drc()
    print("-" * 42)
    print(f"kept {kept}, failed {failed} -> {hard} hard DRC errors, {un} unconnected")


if __name__ == "__main__":
    main()
