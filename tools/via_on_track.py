#!/usr/bin/env python3
"""
Drop a via onto plane-net tracks that never reach their plane.

The last connections on this board are not routing problems - they are Track-to-Track
and Pad-to-Track items on GND, +3V3, +5V, +9V and VBAT. The copper is already there
and already in the right place; it simply has no via taking it down to In1 (GND) or
In4 (power). route_remaining.py joins such pairs happily and the unconnected count
does not move, because joining two stubs that both float above the plane connects
nothing.

So this walks the track named in each item and tries to land a via anywhere along it,
working down the via tiers, honouring hole-to-hole clearance, and verifying with DRC
and rollback per via.

Usage:  python3 tools/via_on_track.py [--apply]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/vot_backup.kicad_pcb"
RPT   = "/tmp/nav/vot.rpt"
TIERS = [(0.60, 0.30), (0.50, 0.25), (0.45, 0.20)]


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def track_targets(text):
    """(net, x, y, length) for tracks named in plane-net unconnected items."""
    out = set()
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        for m in re.finditer(r'@\(([\d.]+) mm, ([\d.]+) mm\): Track \[([^\]]+)\]'
                             r' on \S+, length ([\d.]+) mm', blk[:400]):
            net = m.group(3)
            if net in route.PLANE:
                out.add((net, float(m.group(1)), float(m.group(2)), float(m.group(4))))
    return sorted(out)


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, text = drc()
    todo = track_targets(text)
    print(f"baseline {hard0} errors, {un0} unconnected; "
          f"{len(todo)} plane-net tracks with no via to their plane\n")

    kept = failed = 0
    for net, tx, ty, tlen in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        if n is None:
            failed += 1
            continue
        # find that exact track
        trk = None
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != n.GetNetCode():
                continue
            p = t.GetStart()
            if abs(route.TOMM(p.x) - tx) < 1e-3 and abs(route.TOMM(p.y) - ty) < 1e-3 \
               and abs(t.GetLength()/1e6 - tlen) < 1e-3:
                trk = t; break
        if trk is None:
            failed += 1
            continue

        a, b = trk.GetStart(), trk.GetEnd()
        ax, ay = route.TOMM(a.x), route.TOMM(a.y)
        bx, by = route.TOMM(b.x), route.TOMM(b.y)
        foreign = route.obstacle_shapes(board, exclude_net=net)
        holes = route.hole_shapes(board)
        kos = route.keepout_boxes(board)

        spot = None
        for via_d, drill in TIERS:
            need = via_d / 2 + route.VIA_CLEAR
            steps = max(2, int(math.hypot(bx-ax, by-ay) / 0.05))
            for i in range(steps + 1):
                f = i / steps
                vx, vy = ax + (bx-ax)*f, ay + (by-ay)*f
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

        if not spot:
            failed += 1
            print(f"  {net:7} track at ({tx:6.2f},{ty:6.2f}) len {tlen:4.2f}  no via fits")
            continue
        if not apply:
            kept += 1
            print(f"  {net:7} track at ({tx:6.2f},{ty:6.2f})  would via {spot[2]:.2f} mm")
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
            print(f"  {net:7} track at ({tx:6.2f},{ty:6.2f})  rolled back")
        else:
            kept += 1
            print(f"  {net:7} via {via_d:.2f} mm at ({vx:.2f},{vy:.2f}) -> {un}")
            un0 = un

    hard, un, _ = drc()
    print(f"\nkept {kept}, failed {failed} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
