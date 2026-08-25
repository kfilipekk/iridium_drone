#!/usr/bin/env python3
"""
Join same-net track ends that are simply not touching.

Some unconnected items are not routing problems at all. The +9V pair on B.Cu sit
0.563 mm apart at the same Y - two collinear stubs with a gap between them. The A*
router treats that as a full routing problem and often fails on it; all it needs is a
straight segment.

For every unconnected item naming two tracks, this finds the closest pair of endpoints
between them, and if they are on the same layer and the straight line between them is
clear, lays a track. Longer gaps are left to route_remaining.py, which is the right
tool for anything that needs to navigate.

Usage:  python3 tools/join_gaps.py [--apply] [--max-gap MM]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/join_backup.kicad_pcb"
RPT   = "/tmp/nav/join.rpt"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def track_pairs(text):
    """Nets whose unconnected item names two tracks."""
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        ts = re.findall(r'Track \[([^\]]+)\] on (\S+), length ([\d.]+) mm', blk[:400])
        if len(ts) == 2:
            out.append((ts[0][0], ts[0][1], float(ts[0][2]),
                        ts[1][1], float(ts[1][2])))
    return out


def main():
    apply = "--apply" in sys.argv
    maxgap = 3.0
    if "--max-gap" in sys.argv:
        maxgap = float(sys.argv[sys.argv.index("--max-gap") + 1])
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, text = drc()
    todo = track_pairs(text)
    print(f"baseline {hard0} errors, {un0} unconnected; "
          f"{len(todo)} items name two tracks\n")

    kept = skipped = 0
    for net, lay1, len1, lay2, len2 in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        if n is None:
            skipped += 1
            continue
        want = []
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != n.GetNetCode():
                continue
            L = t.GetLength() / 1e6
            ln = board.GetLayerName(t.GetLayer())
            if (ln == lay1 and abs(L-len1) < 2e-3) or (ln == lay2 and abs(L-len2) < 2e-3):
                a, c = t.GetStart(), t.GetEnd()
                want.append((t.GetLayer(), (a.x/1e6, a.y/1e6), (c.x/1e6, c.y/1e6)))
        best = None
        for i in range(len(want)):
            for j in range(i+1, len(want)):
                if want[i][0] != want[j][0]:
                    continue                      # different layers: needs a via
                for p in want[i][1:]:
                    for q in want[j][1:]:
                        d = math.hypot(p[0]-q[0], p[1]-q[1])
                        if d > 1e-6 and (best is None or d < best[0]):
                            best = (d, p, q, want[i][0])
        if not best or best[0] > maxgap:
            skipped += 1
            print(f"  {net:7} {lay1}/{lay2}: "
                  + (f"gap {best[0]:.2f} mm > {maxgap} - leave to the router"
                     if best else "not same-layer, needs a via"))
            continue

        d, p, q, lay = best
        foreign = route.obstacle_shapes(board, exclude_net=net)
        need = route.TRACK_W/2 + route.CLEAR
        steps = max(2, int(d / 0.02))
        clear = True
        for k in range(steps + 1):
            f = k / steps
            sx, sy = p[0] + (q[0]-p[0])*f, p[1] + (q[1]-p[1])*f
            if any(route.gap_to_shape(sx, sy, r) < need for r in foreign):
                clear = False; break
        if not clear:
            skipped += 1
            print(f"  {net:7} gap {d:.3f} mm on {board.GetLayerName(lay)}: blocked")
            continue
        if not apply:
            kept += 1
            print(f"  {net:7} would join {d:.3f} mm on {board.GetLayerName(lay)}")
            continue

        shutil.copy(BOARD, BAK)
        route.add_track(board, p, q, board.GetLayerName(lay), n, width=route.TRACK_W)
        route.fill(board)
        board.Save(BOARD)
        hard, un, _ = drc()
        if hard > hard0 or un > un0:
            shutil.copy(BAK, BOARD); skipped += 1
            print(f"  {net:7} rolled back (+{hard-hard0} err, +{un-un0} unconn)")
        else:
            kept += 1; un0 = un
            print(f"  {net:7} joined {d:.3f} mm on {board.GetLayerName(lay)} -> {un}")

    hard, un, _ = drc()
    print(f"\njoined {kept}, skipped {skipped} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
