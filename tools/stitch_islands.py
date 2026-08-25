#!/usr/bin/env python3
"""
Tie orphaned copper-pour islands to their plane with stitching vias.

route.stitch() drops GND vias on a blind 1.8 mm grid. That works for the big pours
but leaves behind exactly the islands the grid could not land in - the tight ones
between fine-pitch parts. Those show up in the DRC report as unconnected items with
a Zone endpoint, and the report is no help in finding them: every zone reports its
outline origin (100.3, 100.3), not the island's location. So they are found here
geometrically instead.

An island is "tied" if a via of the same net, spanning this layer and the plane
layer, lands inside it. Untied islands get one via at the most open point inside
them - the point furthest from any foreign copper, which is the position most likely
to survive DRC.

Usage:  python3 tools/stitch_islands.py [--apply]
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/stitch_backup.kicad_pcb"
MM    = pcbnew.FromMM


def drc(path=BOARD):
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/nav/st.rpt",
                    "--severity-error", path], capture_output=True, timeout=600)
    rpt = open("/tmp/nav/st.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', rpt, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def islands(board):
    """(zone, layer_id, outline_index, [(x_mm, y_mm) sample points]) per filled island."""
    out = []
    for z in board.Zones():
        net = z.GetNetname()
        if net not in route.PLANE:
            continue
        for li in z.GetLayerSet().CuStack():
            poly = z.GetFilledPolysList(li)
            for i in range(poly.OutlineCount()):
                out.append((z, li, i, poly))
    return out


def tied(board, z, li, poly, i, plane_id):
    """Does a via already join this island to its plane layer?"""
    code = z.GetNetCode()
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T or t.GetNetCode() != code:
            continue
        if not (t.IsOnLayer(li) and t.IsOnLayer(plane_id)):
            continue
        p = t.GetPosition()
        if poly.Contains(pcbnew.VECTOR2I(p.x, p.y), i):
            return True
    return False


# The pours that remain stranded are thin snakes weaving between fine-pitch parts,
# not blobs: an 18.8 mm2 island can have a widest gap of 0.20 mm. A 0.60 mm via needs
# 0.50 mm and simply does not fit. 0.45 mm / 0.25 mm drill is the smallest via still
# inside JLCPCB's standard 4-layer process (confirm before ordering - below this you
# are into HDI pricing), and it needs only 0.375 mm.
VIA_TIERS = [(0.60, 0.30), (0.50, 0.25), (0.45, 0.20)]


def legal_tiers(board):
    """Only tiers the board's own design rules allow.

    Emitting a 0.45 mm via on a board whose netclass sets a 0.60 mm minimum just
    trades an unconnected item for two rule violations, so the constraint is read
    from board setup rather than assumed. To use the smaller tier, raise it there
    first - and confirm the process supports it before ordering.
    """
    ds = board.GetDesignSettings()
    min_d = ds.m_ViasMinSize / 1e6
    min_h = ds.m_MinThroughDrill / 1e6
    ok = [(d, h) for d, h in VIA_TIERS if d >= min_d - 1e-9 and h >= min_h - 1e-9]
    if len(ok) < len(VIA_TIERS):
        print(f"board setup allows via >= {min_d:.2f} mm, drill >= {min_h:.2f} mm "
              f"-> using {len(ok)} of {len(VIA_TIERS)} tiers")
    return ok or [VIA_TIERS[0]]


def best_point(poly, i, foreign, board, via_d, holes=()):
    """Most open point inside island i: maximises distance to any foreign copper."""
    bb = poly.Outline(i).BBox()
    x0, y0 = bb.GetLeft() / 1e6, bb.GetTop() / 1e6
    x1, y1 = bb.GetRight() / 1e6, bb.GetBottom() / 1e6
    need = via_d / 2 + route.VIA_CLEAR
    best, bestgap, seen = None, need, 0.0
    step = 0.08          # fine enough to find a spot inside a narrow sliver
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            if poly.Contains(pcbnew.VECTOR2I(MM(x), MM(y)), i) and \
               route.inside_board(x, y, via_d / 2 + 0.5) and \
               (not holes or route.hole_ok(x, y, holes, via_d * 0.5)):
                gap = min((route.gap_to_rect(x, y, r) for r in foreign), default=99.0)
                seen = max(seen, gap)
                if gap > bestgap:
                    best, bestgap = (x, y), gap
            x += step
        y += step
    return best, seen


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)

    tiers = legal_tiers(board)
    todo = []
    for z, li, i, poly in islands(board):
        net = z.GetNetname()
        plane_id = board.GetLayerID(route.PLANE[net])
        if li == plane_id:
            continue                       # the plane itself needs no tie
        if tied(board, z, li, poly, i, plane_id):
            continue
        area = poly.Outline(i).Area() / 1e12
        todo.append((area, z, li, i, poly, net, plane_id))

    todo.sort(reverse=True)
    print(f"{len(todo)} untied islands (largest first)\n")
    print(f"{'net':8} {'layer':7} {'area mm2':>9}  {'via at':>16}  gap")
    print("-" * 56)

    placed = 0
    small = {}
    for area, z, li, i, poly, net, plane_id in todo:
        foreign = route.obstacles(board, exclude_net=net)
        holes = route.hole_shapes(board)
        lname = board.GetLayerName(li)
        for via_d, drill in tiers:
            pt, seen = best_point(poly, i, foreign, board, via_d, holes)
            if pt:
                break
        if not pt:
            print(f"{net:8} {lname:7} {area:9.2f}  {'none':>16}  "
                  f"widest gap {seen:.2f} (need >{tiers[-1][0]/2 + route.VIA_CLEAR:.2f})")
            continue
        v = route.add_via(board, pt[0], pt[1], z.GetNet())
        v.SetWidth(MM(via_d)); v.SetDrill(MM(drill))
        placed += 1
        small[via_d] = small.get(via_d, 0) + 1
        print(f"{net:8} {lname:7} {area:9.2f}  ({pt[0]:6.2f},{pt[1]:6.2f})  "
              f"{via_d:.2f} mm via")

    print(f"\nplaced {placed} stitching vias: "
          + ", ".join(f"{n} at {d:.2f} mm" for d, n in sorted(small.items(), reverse=True)))
    if not apply:
        print("dry run - pass --apply to write the board")
        return 0

    shutil.copy(BOARD, BAK)
    hard0, un0 = drc()
    route.fill(board)
    board.Save(BOARD)
    hard, un = drc()
    print(f"DRC: {hard0} -> {hard} errors, {un0} -> {un} unconnected")
    if hard > hard0 or un > un0:
        shutil.copy(BAK, BOARD)
        print("worse - rolled back")
        return 1
    print("kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
