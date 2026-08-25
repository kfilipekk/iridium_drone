#!/usr/bin/env python3
"""
Drop a via where two pieces of the same net sit on top of each other.

Several of the last unconnected items are pairs of tracks at the SAME XY on different
layers, with nothing joining them - +5V at (135.5312, 111.6562) on F.Cu and In3.Cu,
+3V3 at (126.0312, 126.7812) on In2.Cu and B.Cu, +3V3A at (119.2812, 143.6562) on F.Cu
and B.Cu. Two independent routes passed through the same grid cell on different layers
and neither knew about the other.

Every other tool here looks at one track at a time and asks "can this reach its plane".
None of them ask "are these two already touching except for a via". This does.

Usage:  python3 tools/stitch_stacked.py [--apply] [--radius MM]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/ss_backup.kicad_pcb"
RPT   = "/tmp/nav/ss.rpt"
TIERS = [(0.60, 0.30), (0.50, 0.25), (0.45, 0.20)]


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def stacked(text, radius):
    """Items whose two endpoints are on different layers within `radius` of each other.

    Also carries the reported track lengths, so the caller can walk ALONG both tracks
    rather than only trying the single point the DRC happened to name. The reported
    point is often in the tightest part of the run - the two traces may stay stacked
    for millimetres, and a via fits somewhere else along that overlap.
    """
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        eps = re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): (Pad \S+|Zone|Track|Via)'
                         r'[^\[]*\[([^\]]+)\][^\n]*?on (\S+?)[,\s]([^\n]*)', blk[:400])[:2]
        if len(eps) != 2:
            continue
        a, b = eps
        if a[2] == "Zone" or b[2] == "Zone":
            continue
        if a[4] == b[4]:
            continue                       # same layer: a via would not help
        d = math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))
        if d <= radius:
            def L(e):
                m = re.search(r'length ([\d.]+)', e[5])
                return float(m.group(1)) if m else None
            out.append((a[3], (float(a[0]) + float(b[0])) / 2,
                        (float(a[1]) + float(b[1])) / 2, d, a[4], b[4],
                        (a[4], L(a)), (b[4], L(b))))
    return out


def overlap_points(board, net, ta, tb, step=0.05, tol=0.12):
    """Points where the two named tracks are stacked, sampled along both."""
    code = board.FindNet(net).GetNetCode()
    def find(layname, length):
        if length is None:
            return None
        lid = board.GetLayerID(layname)
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != code:
                continue
            if t.GetLayer() != lid:
                continue
            if abs(t.GetLength()/1e6 - length) < 2e-3:
                a, c = t.GetStart(), t.GetEnd()
                return ((a.x/1e6, a.y/1e6), (c.x/1e6, c.y/1e6))
        return None
    A = find(*ta); B = find(*tb)
    if not A or not B:
        return []
    def samples(seg):
        L = math.hypot(seg[1][0]-seg[0][0], seg[1][1]-seg[0][1])
        n = max(1, int(L / step))
        return [(seg[0][0] + (seg[1][0]-seg[0][0])*i/n,
                 seg[0][1] + (seg[1][1]-seg[0][1])*i/n) for i in range(n+1)]
    out = []
    for p in samples(A):
        for q in samples(B):
            if math.hypot(p[0]-q[0], p[1]-q[1]) <= tol:
                out.append(((p[0]+q[0])/2, (p[1]+q[1])/2))
                break
    return out


def main():
    apply = "--apply" in sys.argv
    radius = 0.15
    if "--radius" in sys.argv:
        radius = float(sys.argv[sys.argv.index("--radius") + 1])
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, text = drc()
    todo = stacked(text, radius)
    print(f"baseline {hard0} errors, {un0} unconnected; "
          f"{len(todo)} stacked pairs within {radius} mm\n")

    kept = failed = 0
    for net, x, y, d, l1, l2, ta, tb in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        if n is None:
            failed += 1
            continue
        foreign = route.obstacle_shapes(board, exclude_net=net)
        holes = route.hole_shapes(board)
        kos = route.keepout_boxes(board)

        # Candidates: every point where the two traces are stacked, and a small
        # radial search around each. Overlap points alone missed a spot 0.3 mm off
        # the trace that a via did fit in; the radial search alone only ever looked
        # at the single point the DRC named.
        base = overlap_points(board, net, ta, tb) or [(x, y)]
        cands = []
        for (bx, by) in base:
            cands.append((bx, by))
            for rad in [r * 0.05 for r in range(1, 13)]:
                for k in range(24):
                    a = k * math.pi / 12
                    cands.append((bx + rad*math.cos(a), by + rad*math.sin(a)))
        spot = None
        for via_d, drill in TIERS:
            need = via_d / 2 + route.VIA_CLEAR
            for (cx, cy) in cands:
                if True:
                    vx, vy = cx, cy
                    if not route.inside_board(vx, vy, via_d/2 + 0.4):
                        continue
                    if any(x1 - via_d/2 < vx < x2 + via_d/2 and
                           y1 - via_d/2 < vy < y2 + via_d/2
                           for x1, y1, x2, y2 in kos):
                        continue
                    if not route.hole_ok(vx, vy, holes, drill):
                        continue
                    if any(route.gap_to_shape(vx, vy, r) < need for r in foreign):
                        continue
                    spot = (vx, vy, via_d, drill); break
                if spot:
                    break
            if spot:
                break

        if not spot:
            failed += 1
            print(f"  {net:7} {l1}/{l2}: no via fits at any of {len(cands)} overlap points")
            continue
        if not apply:
            kept += 1
            print(f"  {net:7} {l1}/{l2} at ({x:.2f},{y:.2f}): would via {spot[2]:.2f} mm")
            continue

        shutil.copy(BOARD, BAK)
        vx, vy, via_d, drill = spot
        v = route.add_via(board, vx, vy, n)
        v.SetWidth(pcbnew.FromMM(via_d)); v.SetDrill(pcbnew.FromMM(drill))
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
            print(f"  {net:7} via {via_d:.2f} mm at ({vx:.2f},{vy:.2f}) -> {un}")

    hard, un, _ = drc()
    print(f"\nplaced {kept}, failed {failed} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
