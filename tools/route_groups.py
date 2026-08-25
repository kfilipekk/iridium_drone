#!/usr/bin/env python3
"""
Route each unconnected item to the TARGET'S WHOLE CONNECTED GROUP, not to one point.

route_remaining.py routes point A to point B, using the two coordinates the DRC report
happens to name. On a track-to-track item those are the two tracks' *start* points,
which are usually the worst places to aim for - the router has to arrive at one exact
cell instead of anywhere along several millimetres of existing copper. That is why it
keeps failing on the last few.

This finds the connected component that endpoint B belongs to - by geometric union-find
over the net's tracks, vias and pads - collects every grid cell that component owns, and
routes to ANY of them. That is what hand routing actually does: you land on the nearest
piece of that net, not on a nominated point.

It is deliberately NOT the route_gnd.py mistake. The goal set is one specific component,
excluding whatever A is already attached to, so a route that connects a group to itself
cannot be counted as progress.

Usage:  python3 tools/route_groups.py [--apply] [--via-cost N]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/rg_backup.kicad_pcb"
RPT   = "/tmp/nav/rg.rpt"
Q     = lambda v: round(v / 2000.0)       # 2 um cells; track ends meet within a micron


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


class UF(dict):
    def find(self, x):
        self.setdefault(x, x)
        while self[x] != x:
            self[x] = self[self[x]]; x = self[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self[ra] = rb


def components(board, code):
    """Geometric union-find over one net's copper. Returns (uf, point->key, keys)."""
    uf = UF()
    pts = []                       # (key, x_mm, y_mm)
    for t in board.GetTracks():
        if t.GetNetCode() != code:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            k = ("n", Q(p.x), Q(p.y))
            uf.find(k); pts.append((k, p.x/1e6, p.y/1e6))
        else:
            a, b = t.GetStart(), t.GetEnd()
            ka, kb = ("n", Q(a.x), Q(a.y)), ("n", Q(b.x), Q(b.y))
            uf.union(ka, kb)
            # sample along the track so a landing site anywhere on it is reachable
            L = math.hypot(b.x-a.x, b.y-a.y) / 1e6
            n = max(1, int(L / 0.2))
            for i in range(n + 1):
                f = i / n
                pts.append((ka, (a.x + (b.x-a.x)*f)/1e6, (a.y + (b.y-a.y)*f)/1e6))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() != code:
                continue
            p = pad.GetPosition()
            k = ("n", Q(p.x), Q(p.y))
            uf.find(k); pts.append((k, p.x/1e6, p.y/1e6))
            bb = pad.GetBoundingBox()
            for t in board.GetTracks():
                if t.GetNetCode() != code or t.Type() == pcbnew.PCB_VIA_T:
                    continue
                for q in (t.GetStart(), t.GetEnd()):
                    if bb.GetLeft() <= q.x <= bb.GetRight() and \
                       bb.GetTop() <= q.y <= bb.GetBottom():
                        uf.union(k, ("n", Q(q.x), Q(q.y)))
    return uf, pts


def endpoints(text):
    """(net, (ax,ay), (bx,by)) for every unconnected item with two usable points."""
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        eps = re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): (Pad \S+|Zone|Track|Via)'
                         r'[^\[]*\[([^\]]+)\]', blk[:400])[:2]
        if len(eps) != 2:
            continue
        a, b = eps
        if a[2] == "Zone" or b[2] == "Zone":
            continue                     # a zone reports its outline origin, useless
        out.append((a[3], (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
    return out


def main():
    apply = "--apply" in sys.argv
    vc = None
    if "--via-cost" in sys.argv:
        vc = int(sys.argv[sys.argv.index("--via-cost") + 1])
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, text = drc()
    todo = endpoints(text)
    print(f"baseline {hard0} errors, {un0} unconnected; {len(todo)} routable items\n")

    kept = failed = 0
    for net, A, B in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        if n is None:
            failed += 1
            continue
        code = n.GetNetCode()
        uf, pts = components(board, code)

        # which component does each endpoint belong to?
        def comp_of(p):
            best, bk = 1e9, None
            for k, x, y in pts:
                d = math.hypot(x - p[0], y - p[1])
                if d < best:
                    best, bk = d, k
            return uf.find(bk) if bk else None
        ca, cb = comp_of(A), comp_of(B)
        if ca is None:
            failed += 1
            continue
        # When both endpoints land in the SAME component, the DRC is naming two items
        # inside one isolated island - joining them achieves nothing. What that island
        # actually needs is a route to the main body of the net. So the target is
        # always the LARGEST component that is not the one A sits in.
        sizes = {}
        for k, x, y in pts:
            sizes[uf.find(k)] = sizes.get(uf.find(k), 0) + 1
        if cb == ca or cb is None:
            others = [(v, k) for k, v in sizes.items() if k != ca]
            if not others:
                failed += 1
                print(f"  {net:7} net has only one component - nothing to join")
                continue
            cb = max(others)[1]
            note = f" (retargeted to the main body, {sizes[cb]} pts)"
        else:
            note = ""

        target = [(x, y) for k, x, y in pts if uf.find(k) == cb]
        r = route.Router(board)
        goals = r.cells_of_net(code, target)
        if not goals:
            failed += 1
            print(f"  {net:7} target component owns no reachable cells")
            continue
        path = None
        for cost in ([vc] if vc else [12, 6, 24]):
            path = r.route_to_any(code, A, goals, via_cost=cost)
            if path:
                break
        if not path:
            failed += 1
            print(f"  {net:7} no path to the target component "
                  f"({len(goals)} candidate cells)")
            continue
        if not apply:
            kept += 1
            print(f"  {net:7} would route to a {len(goals)}-cell component{note}")
            continue

        shutil.copy(BOARD, BAK)
        r.commit(code, n, path)
        route.fill(board)
        board.Save(BOARD)
        hard, un, _ = drc()
        if hard > hard0 or un > un0:
            shutil.copy(BAK, BOARD)
            failed += 1
            print(f"  {net:7} rolled back (+{hard-hard0} err, +{un-un0} unconn)")
        else:
            kept += 1
            un0 = un
            print(f"  {net:7} routed -> {un} unconnected")

    hard, un, _ = drc()
    print(f"\nkept {kept}, failed {failed} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
