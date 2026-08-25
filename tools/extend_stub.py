#!/usr/bin/env python3
"""
Lengthen a short stub until it reaches somewhere a via can go.

Several of the last connections are a long track on one layer and a 0.0625 mm stub on
another, sitting on top of each other. A via would join them, but the stub is one grid
cell long and every point along it is boxed in - stitch_stacked.py tried 289 and 867
overlap points on these and none had room.

The stub does not have to stay short. Extending it a millimetre in a direction that is
clear puts its far end somewhere a via does fit, and a via there connects the layers
just as well. This walks outward from the stub in every direction, in small steps,
looking for the first point that can take both the extension and a via.

Verified with DRC and rolled back per attempt.

Usage:  python3 tools/extend_stub.py [--apply] [--max-len MM]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/ext_backup.kicad_pcb"
RPT   = "/tmp/nav/ext.rpt"
TIERS = [(0.60, 0.30), (0.50, 0.25), (0.45, 0.20)]


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def pairs(text):
    """(net, (layer,len) of the SHORT track, (layer,len) of the other)."""
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        ts = re.findall(r'Track \[([^\]]+)\] on (\S+), length ([\d.]+) mm', blk[:400])
        if len(ts) != 2:
            continue
        a, b = ts
        if float(a[2]) <= float(b[2]):
            short, other = a, b
        else:
            short, other = b, a
        out.append((a[0], (short[1], float(short[2])), (other[1], float(other[2]))))
    return out


def main():
    apply = "--apply" in sys.argv
    maxlen = 2.5
    if "--max-len" in sys.argv:
        maxlen = float(sys.argv[sys.argv.index("--max-len") + 1])
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, text = drc()
    todo = pairs(text)
    print(f"baseline {hard0} errors, {un0} unconnected; {len(todo)} track pairs\n")

    kept = failed = 0
    for net, (slay, slen), (olay, olen) in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        if n is None:
            failed += 1
            continue
        lid = board.GetLayerID(slay)
        stub = None
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != n.GetNetCode():
                continue
            if t.GetLayer() == lid and abs(t.GetLength()/1e6 - slen) < 2e-3:
                stub = t; break
        if stub is None:
            failed += 1
            print(f"  {net:7} {slay}: stub not found")
            continue

        a, c = stub.GetStart(), stub.GetEnd()
        ax, ay, cx, cy = a.x/1e6, a.y/1e6, c.x/1e6, c.y/1e6
        foreign = route.obstacle_shapes(board, exclude_net=net)
        holes = route.hole_shapes(board)
        kos = route.keepout_boxes(board)

        best = None
        for (ox, oy) in ((ax, ay), (cx, cy)):          # grow from either end
            for k in range(72):
                ang = k * math.pi / 36
                dx, dy = math.cos(ang), math.sin(ang)
                L = 0.1
                while L <= maxlen:
                    ex, ey = ox + dx*L, oy + dy*L
                    # the extension itself must be clear
                    ok = True
                    steps = max(2, int(L / 0.03))
                    for s in range(steps + 1):
                        sx, sy = ox + dx*L*s/steps, oy + dy*L*s/steps
                        if any(route.gap_to_shape(sx, sy, r) < route.TRACK_W/2 + route.CLEAR
                               for r in foreign):
                            ok = False; break
                    if not ok:
                        break                            # blocked; try another angle
                    for via_d, drill in TIERS:
                        need = via_d/2 + route.VIA_CLEAR
                        if not route.inside_board(ex, ey, via_d/2 + 0.35):
                            continue
                        if any(x1 - via_d/2 < ex < x2 + via_d/2 and
                               y1 - via_d/2 < ey < y2 + via_d/2
                               for x1, y1, x2, y2 in kos):
                            continue
                        if not route.hole_ok(ex, ey, holes, drill):
                            continue
                        if any(route.gap_to_shape(ex, ey, r) < need for r in foreign):
                            continue
                        if best is None or L < best[0]:
                            best = (L, ox, oy, ex, ey, via_d, drill)
                        break
                    if best and best[0] <= L:
                        break
                    L += 0.05
        if not best:
            failed += 1
            print(f"  {net:7} {slay} stub: no direction reaches a via within {maxlen} mm")
            continue
        L, ox, oy, ex, ey, via_d, drill = best
        if not apply:
            kept += 1
            print(f"  {net:7} {slay} stub: extend {L:.2f} mm to ({ex:.2f},{ey:.2f}), "
                  f"via {via_d:.2f} mm")
            continue

        shutil.copy(BOARD, BAK)
        route.add_track(board, (ox, oy), (ex, ey), slay, n, width=route.TRACK_W)
        v = route.add_via(board, ex, ey, n)
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
            print(f"  {net:7} extended {L:.2f} mm + via {via_d:.2f} mm -> {un}")

    hard, un, _ = drc()
    print(f"\nkept {kept}, failed {failed} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
