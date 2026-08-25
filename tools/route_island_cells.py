#!/usr/bin/env python3
"""
Route out of a stranded island, starting from a grid cell that is provably inside it.

island_to_plane.py picked its start by "most open point in the polygon" and then handed
that to route.Router, which snaps to its 0.0625 mm grid. On a 0.15 mm sliver the snapped
cell lands outside the island, so the committed trace never touched the copper it was
meant to rescue - it reported success three times while nothing changed.

Here the candidate starts are enumerated the other way round: walk the ROUTER'S OWN
cells, keep the ones whose centre falls inside the island polygon and which are clear
enough for a track, and route from those. Same coordinates the router will use, so
nothing shifts underneath. The islands have 30 to 108 such cells each - there was never
a shortage, only a mismatch.

Usage:  python3 tools/route_island_cells.py [--apply] [--one N]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/ric_backup.kicad_pcb"
RPT   = "/tmp/nav/ric.rpt"
MM    = pcbnew.FromMM


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items")


def main():
    apply = "--apply" in sys.argv
    only = int(sys.argv[sys.argv.index("--one") + 1]) if "--one" in sys.argv else None
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0 = drc()

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    net = "GND"
    n = board.FindNet(net)
    code = n.GetNetCode()
    plane = board.GetLayerID(route.PLANE[net])
    r = route.Router(board)
    # map a board layer id to the router's own signal-layer index
    LAYIDX = {board.GetLayerID(nm): k for k, nm in enumerate(route.SIG_LAYERS)}
    foreign = route.obstacle_shapes(board, exclude_net=net)
    need = route.TRACK_W/2 + route.CLEAR
    vias = [(t.GetPosition(), t) for t in board.GetTracks()
            if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == code]
    anchors = [(route.TOMM(p.x), route.TOMM(p.y)) for p, t in vias if t.IsOnLayer(plane)]
    goals = r.cells_of_net(code, anchors)

    todo = []
    for z in board.Zones():
        if z.GetNetname() != net or z.GetIsRuleArea():
            continue
        for li in z.GetLayerSet().CuStack():
            if li == plane:
                continue
            poly = z.GetFilledPolysList(li)
            for i in range(poly.OutlineCount()):
                if any(t.IsOnLayer(li) and t.IsOnLayer(plane)
                       and poly.Contains(pcbnew.VECTOR2I(p.x, p.y), i) for p, t in vias):
                    continue
                todo.append((li, i, poly, poly.Outline(i).Area()/1e12))
    todo.sort(key=lambda t: -t[3])
    if only is not None:
        todo = todo[only:only+1]
    print(f"baseline {hard0} errors, {un0} unconnected; {len(todo)} untied islands, "
          f"{len(goals)} goal cells\n")

    for li, i, poly, area in todo:
        bb = poly.Outline(i).BBox()
        ci0, cj0 = r.cell(bb.GetLeft()/1e6, bb.GetTop()/1e6)
        ci1, cj1 = r.cell(bb.GetRight()/1e6, bb.GetBottom()/1e6)
        starts = []
        for cj in range(cj0, cj1 + 1):
            for ci in range(ci0, ci1 + 1):
                x, y = r.pos(ci, cj)
                if not poly.Contains(pcbnew.VECTOR2I(MM(x), MM(y)), i):
                    continue
                if all(route.gap_to_shape(x, y, s) >= need for s in foreign):
                    starts.append((x, y))
        if not starts:
            print(f"  {area:5.2f} mm2 on {board.GetLayerName(li)}: no clear cell inside")
            continue
        # widest-spread first: try cells far apart before neighbours of a dead end
        starts = starts[::max(1, len(starts)//24)]
        path = used = None
        for s in starts:
            for vc in (10, 4, 18):
                path = r.route_to_any(code, s, goals, via_cost=vc,
                                      start_layer=LAYIDX.get(li))
                if path:
                    used = s; break
            if path:
                break
        if not path:
            print(f"  {area:5.2f} mm2 on {board.GetLayerName(li)}: "
                  f"no path from {len(starts)} in-island cells")
            continue
        print(f"  {area:5.2f} mm2 on {board.GetLayerName(li)}: path found from "
              f"({used[0]:.3f},{used[1]:.3f}), {len(path)} points")
        if apply:
            r.commit(code, n, path)

    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0
    shutil.copy(BOARD, BAK)
    route.fill(board)
    board.Save(BOARD)
    hard, un = drc()
    print(f"\nDRC: {hard0} -> {hard} errors, {un0} -> {un} unconnected")
    if hard > hard0 or un > un0:
        shutil.copy(BAK, BOARD); print("worse - rolled back"); return 1
    print("kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
