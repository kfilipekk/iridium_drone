#!/usr/bin/env python3
"""
Rip-up-and-retry pass over whatever the staged router could not reach.

The staged router is greedy: it takes the first legal path and never reconsiders, so
once the board fills up the remaining nets simply have nowhere to go. This pass lets a
blocked net cut through copper that is already there, rips up whoever was in the way,
and puts those nets back in the queue to be re-routed.

Safety: whole-board DRC is checked at the end and the whole pass is discarded if the
error count rose. Nets carried by a plane (GND, +3V3) are never ripped - their fanout
vias are the only thing connecting them.

Usage:  python3 tools/route_ripup.py [max_rounds]
"""
import os, sys, math, shutil, subprocess, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/navcore_ripup_backup.kicad_pcb"
RIP_LIMIT = 3          # how often one net may be ripped before it is left alone


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/rip_drc.rpt",
                    "--severity-error", BOARD], capture_output=True, timeout=300)
    rpt = open("/tmp/rip_drc.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', rpt, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def net_pads(board):
    out = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNet()
            if not n or not n.GetNetCode(): continue
            out.setdefault(n.GetNetCode(), []).append(pad)
    return out


def components(board):
    """Geometric union-find: which pads already share copper."""
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
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition(); union(("N", Q(p.x), Q(p.y)), ("V", Q(p.x), Q(p.y)))
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


def rip(board, code):
    """Remove every track and via belonging to a net. Returns how many were removed."""
    doomed = [t for t in board.GetTracks() if t.GetNet() and t.GetNet().GetNetCode() == code]
    for t in doomed: board.Remove(t)
    return len(doomed)


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    shutil.copy(BOARD, BAK)
    hard0, un0 = drc()
    print(f"baseline: {hard0} hard DRC errors, {un0} unconnected\n")
    print(f"{'round':>5} {'attempted':>10} {'routed':>7} {'ripped':>7} {'unconn':>8}")
    print("-" * 45)

    rip_count = {}
    for rnd in range(1, rounds + 1):
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        plane_codes = {board.FindNet(n).GetNetCode() for n in route.PLANE
                       if board.FindNet(n)}
        pads = net_pads(board)
        padkey, find = components(board)

        todo = []
        for code, ps in pads.items():
            if code in plane_codes or len(ps) < 2: continue
            roots = {}
            for p in ps: roots.setdefault(find(padkey[p.m_Uuid.AsString()]), []).append(p)
            if len(roots) < 2: continue          # already fully connected
            groups = list(roots.values())
            for gi in range(len(groups) - 1):    # join consecutive components
                a = groups[gi][0]; b = groups[gi+1][0]
                todo.append((code, a, b))

        if not todo:
            print(f"{rnd:>5}  nothing left to attempt"); break

        r = route.Router(board)
        routed = 0
        victims_all = set()
        blocked = []
        # Pass A: take every path that is legal right now.
        for code, pa, pb in todo:
            A = (route.TOMM(pa.GetPosition().x), route.TOMM(pa.GetPosition().y))
            B = (route.TOMM(pb.GetPosition().x), route.TOMM(pb.GetPosition().y))
            path = r.route(code, A, B)
            if path:
                r.commit(code, pa.GetNet(), path); routed += 1
            else:
                blocked.append((code, A, B))

        # Pass B: work out who is in the way of what is still blocked. Nothing is
        # ripped inside this loop - board.Remove() invalidates the board's Python
        # iteration, so victims are collected, ripped once, and re-routed next round.
        for code, A, B in blocked:
            if len(victims_all) >= 8: break
            path, victims = r.route_soft(code, A, B)
            if not path: continue
            victims = {v for v in victims
                       if v not in plane_codes and v != code
                       and rip_count.get(v, 0) < RIP_LIMIT}
            if not victims or len(victims) > 4: continue
            victims_all |= victims

        ripped = 0
        for v in victims_all:
            ripped += rip(board, v); rip_count[v] = rip_count.get(v, 0) + 1

        route.fill(board); board.Save(BOARD)
        hard, un = drc()
        print(f"{rnd:>5} {len(todo):>10} {routed:>7} {ripped:>7} {un:>8}"
              + ("" if hard <= hard0 else f"   ({hard-hard0} new errors)"))
        if hard > hard0:
            shutil.copy(BAK, BOARD); print("      -> rolled back, stopping"); break
        shutil.copy(BOARD, BAK)
        if routed == 0 and ripped == 0:
            print("      -> no progress, stopping"); break

    hard, un = drc()
    print("-" * 45)
    print(f"final: {hard} hard DRC errors, {un} unconnected")


if __name__ == "__main__":
    main()
