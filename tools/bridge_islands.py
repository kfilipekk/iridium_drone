#!/usr/bin/env python3
"""
Bridge a stranded pour island to nearby same-net copper with an exact-geometry trace.

Everything else here reaches for a via. A 0.45 mm via needs 0.33 mm of clearance and
these islands offer 0.00 to 0.19 mm, so a via can never fit - that part was measured
correctly. But a 0.1016 mm TRACE needs only 0.15 mm, and two of the three islands have
more room than that. The tools kept failing not because the board is full, but because
they were all asking for the wrong thing.

island_to_plane.py did try a trace, and still failed: route.Router snaps to a 0.0625 mm
grid, and a 0.15 mm sliver is barely two cells wide, so the snapped start lands outside
the island. No grid here - the endpoints are taken from the polygon geometry directly.

Usage:  python3 tools/bridge_islands.py [--apply]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/bi_backup.kicad_pcb"
RPT   = "/tmp/nav/bi.rpt"
MM    = pcbnew.FromMM


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items")


def islands(board, net="GND"):
    """(layer, index, poly, area) for every filled island of this net."""
    out = []
    for z in board.Zones():
        if z.GetNetname() != net or z.GetIsRuleArea():
            continue
        for li in z.GetLayerSet().CuStack():
            poly = z.GetFilledPolysList(li)
            for i in range(poly.OutlineCount()):
                out.append((li, i, poly, poly.Outline(i).Area()/1e12))
    return out


def pts_in(poly, i, step=0.06):
    """Sample points inside island i."""
    bb = poly.Outline(i).BBox()
    x0, y0 = bb.GetLeft()/1e6, bb.GetTop()/1e6
    x1, y1 = bb.GetRight()/1e6, bb.GetBottom()/1e6
    out = []
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            if poly.Contains(pcbnew.VECTOR2I(MM(x), MM(y)), i):
                out.append((x, y))
            x += step
        y += step
    return out


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0 = drc()
    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    net = "GND"
    n = board.FindNet(net)
    code = n.GetNetCode()
    plane = board.GetLayerID(route.PLANE[net])

    vias = [(t.GetPosition(), t) for t in board.GetTracks()
            if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == code]
    isl = islands(board, net)
    small, big = [], []
    for li, i, poly, area in isl:
        if li == plane:
            big.append((li, i, poly)); continue
        tied = any(t.IsOnLayer(li) and t.IsOnLayer(plane)
                   and poly.Contains(pcbnew.VECTOR2I(p.x, p.y), i) for p, t in vias)
        (big if tied else small).append((li, i, poly))
    print(f"baseline {hard0} errors, {un0} unconnected; "
          f"{len(small)} untied islands, {len(big)} tied\n")

    foreign = route.obstacle_shapes(board, exclude_net=net)
    need = route.TRACK_W/2 + route.CLEAR
    kept = failed = 0

    for li, i, poly in small:
        src = pts_in(poly, i)
        # candidate destinations: tied islands ON THE SAME LAYER
        dsts = []
        for lj, j, poly2 in big:
            if lj != li:
                continue
            dsts += pts_in(poly2, j, step=0.35)
        if not src or not dsts:
            failed += 1
            print(f"  island on {board.GetLayerName(li)}: "
                  f"{len(src)} source pts, {len(dsts)} targets - nothing to bridge to")
            continue
        # Rank candidate pairs by distance FIRST and test only the closest few. The
        # exhaustive product of every interior point against every target point is
        # O(n^2) over thousands of samples and simply does not finish.
        pairs = []
        for a in src:
            for b in dsts:
                d = math.hypot(a[0]-b[0], a[1]-b[1])
                if d > 1e-6:
                    pairs.append((d, a, b))
        pairs.sort(key=lambda t: t[0])
        best = None
        for d, a, b in pairs[:400]:
            if best:
                break
            if True:
                steps = max(2, int(d / 0.02))
                ok = True
                for k in range(steps + 1):
                    sx = a[0] + (b[0]-a[0])*k/steps
                    sy = a[1] + (b[1]-a[1])*k/steps
                    if any(route.gap_to_shape(sx, sy, r) < need for r in foreign):
                        ok = False; break
                if ok:
                    best = (d, a, b)
        if not best:
            failed += 1
            print(f"  island on {board.GetLayerName(li)}: no clear straight bridge")
            continue
        d, a, b = best
        print(f"  island on {board.GetLayerName(li)}: bridge {d:.3f} mm "
              f"({a[0]:.2f},{a[1]:.2f}) -> ({b[0]:.2f},{b[1]:.2f})")
        if apply:
            route.add_track(board, a, b, board.GetLayerName(li), n, width=route.TRACK_W)
            kept += 1
        else:
            kept += 1

    if not apply:
        print(f"\n{kept} bridgeable, {failed} not - dry run")
        return 0
    shutil.copy(BOARD, BAK)
    route.fill(board)
    board.Save(BOARD)
    hard, un = drc()
    print(f"\nDRC: {hard0} -> {hard} errors, {un0} -> {un} unconnected")
    if hard > hard0 or un > un0:
        shutil.copy(BAK, BOARD)
        print("worse - rolled back")
        return 1
    print("kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
