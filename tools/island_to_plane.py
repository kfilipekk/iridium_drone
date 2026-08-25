#!/usr/bin/env python3
"""
Route OUT of a stranded pour island with a trace, instead of dropping a via into it.

stitch_islands.py ties an island down by placing a via inside it. The last GND islands
are slivers - 1.52, 1.22 and 0.87 mm2, widest gaps 0.00 to 0.19 mm - and no via fits at
any sampling density. That is a real result for a via, and irrelevant for a trace: a
0.1016 mm track needs about a third of the room a 0.45 mm via does.

So this picks the most open point inside the island and A* routes from there to copper
that provably reaches the plane, exactly as track_to_plane.py does for a stranded track.
The trace leaves the island through a gap a via could never occupy.

Usage:  python3 tools/island_to_plane.py [--apply]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/itp_backup.kicad_pcb"
RPT   = "/tmp/nav/itp.rpt"
MM    = pcbnew.FromMM


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items")


def untied(board, net="GND"):
    """Islands on a non-plane layer with no via joining them to the plane."""
    plane = board.GetLayerID(route.PLANE[net])
    code = board.FindNet(net).GetNetCode()
    vias = [(t.GetPosition(), t) for t in board.GetTracks()
            if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == code]
    out = []
    for z in board.Zones():
        if z.GetNetname() != net:
            continue
        for li in z.GetLayerSet().CuStack():
            if li == plane:
                continue
            poly = z.GetFilledPolysList(li)
            for i in range(poly.OutlineCount()):
                tied = False
                for p, t in vias:
                    if t.IsOnLayer(li) and t.IsOnLayer(plane) \
                       and poly.Contains(pcbnew.VECTOR2I(p.x, p.y), i):
                        tied = True; break
                if not tied:
                    out.append((z, li, i, poly, poly.Outline(i).Area()/1e12))
    out.sort(key=lambda r: -r[4])
    return out


def open_points(poly, i, foreign, board, limit=12):
    """Points inside the island, most open first - candidate trace start points."""
    bb = poly.Outline(i).BBox()
    x0, y0 = bb.GetLeft()/1e6, bb.GetTop()/1e6
    x1, y1 = bb.GetRight()/1e6, bb.GetBottom()/1e6
    found = []
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            if poly.Contains(pcbnew.VECTOR2I(MM(x), MM(y)), i) and \
               route.inside_board(x, y, 0.3):
                g = min((route.gap_to_shape(x, y, r) for r in foreign), default=9.0)
                if g > route.TRACK_W/2 + route.CLEAR:
                    found.append((g, x, y))
            x += 0.06
        y += 0.06
    found.sort(reverse=True)
    return [(x, y) for _, x, y in found[:limit]]


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0 = drc()
    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    isl = untied(board)
    print(f"baseline {hard0} errors, {un0} unconnected; {len(isl)} untied islands\n")

    kept = failed = 0
    for z, li, i, poly, area in isl:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        net = "GND"
        n = board.FindNet(net)
        code = n.GetNetCode()
        plane = board.GetLayerID(route.PLANE[net])
        # re-find the island on the reloaded board
        tgt = None
        for z2 in board.Zones():
            if z2.GetNetname() != net:
                continue
            if li not in list(z2.GetLayerSet().CuStack()):
                continue
            p2 = z2.GetFilledPolysList(li)
            for k in range(p2.OutlineCount()):
                if abs(p2.Outline(k).Area()/1e12 - area) < 1e-3:
                    tgt = (p2, k); break
            if tgt:
                break
        if not tgt:
            failed += 1
            continue
        p2, k = tgt
        foreign = route.obstacle_shapes(board, exclude_net=net)
        starts = open_points(p2, k, foreign, board)
        if not starts:
            failed += 1
            print(f"  {area:6.2f} mm2 on {board.GetLayerName(li)}: no open point inside")
            continue
        anchors = [(route.TOMM(t.GetPosition().x), route.TOMM(t.GetPosition().y))
                   for t in board.GetTracks()
                   if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == code
                   and t.IsOnLayer(plane)]
        r = route.Router(board)
        goals = r.cells_of_net(code, anchors)
        path = None
        used_start = None
        for s in starts:
            path = r.route_to_any(code, s, goals, via_cost=10)
            if path:
                used_start = s
                break
        if not path:
            failed += 1
            print(f"  {area:6.2f} mm2 on {board.GetLayerName(li)}: "
                  f"no path from {len(starts)} start points")
            continue
        if not apply:
            kept += 1
            print(f"  {area:6.2f} mm2 on {board.GetLayerName(li)}: would route out")
            continue
        shutil.copy(BOARD, BAK)
        r.commit(code, n, path)
        # The router snaps its start to the 0.0625 mm grid. These islands are 0.15 mm
        # wide, so the snapped cell centre often lands OUTSIDE the sliver and the
        # committed trace never touches the copper it was meant to rescue - which is
        # why this reported success three times while the islands stayed untied.
        # Stitch the true start point to the first routed point explicitly.
        first = (path[0][1], path[0][2])
        if math.hypot(first[0]-used_start[0], first[1]-used_start[1]) > 1e-6:
            route.add_track(board, used_start, first,
                            board.GetLayerName(li), n, width=route.TRACK_W)
        route.fill(board)
        board.Save(BOARD)
        hard, un = drc()
        if hard > hard0 or un > un0:
            shutil.copy(BAK, BOARD); failed += 1
            print(f"  {area:6.2f} mm2: rolled back (+{hard-hard0} err, +{un-un0} unconn)")
        else:
            kept += 1; un0 = un
            print(f"  {area:6.2f} mm2 on {board.GetLayerName(li)}: routed out -> {un}")

    hard, un = drc()
    print(f"\nkept {kept}, failed {failed} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
