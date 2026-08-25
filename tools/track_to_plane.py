#!/usr/bin/env python3
"""
Route a stranded TRACK to copper that reaches its plane, using A*.

route_to_plane.py does this for pads. The last connections are tracks, and the two
tools that tried to help them both used straight lines: extend_stub.py walked 72
directions and found none that clear even 0.1 mm, and stitch_stacked.py needs a via to
fit on the spot. A* is not restricted to straight lines - it turns corners, which is
the whole point of a maze router and the one thing neither of those could do.

Anchors are vias that span both the track's layer and the plane layer, so landing on
one is a real connection rather than a join to more floating copper.

Usage:  python3 tools/track_to_plane.py [--apply]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/ttp_backup.kicad_pcb"
RPT   = "/tmp/nav/ttp.rpt"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def targets(text):
    """(net, layer, length) for every track named in a plane-net unconnected item."""
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        for m in re.finditer(r'Track \[([^\]]+)\] on (\S+), length ([\d.]+) mm', blk[:400]):
            if m.group(1) in route.PLANE:
                out.append((m.group(1), m.group(2), float(m.group(3))))
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, text = drc()
    todo = targets(text)
    print(f"baseline {hard0} errors, {un0} unconnected; {len(todo)} stranded tracks\n")

    kept = failed = 0
    for net, lay, length in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        if n is None:
            failed += 1
            continue
        code = n.GetNetCode()
        plane = board.GetLayerID(route.PLANE[net])
        lid = board.GetLayerID(lay)

        trk = None
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != code:
                continue
            if t.GetLayer() == lid and abs(t.GetLength()/1e6 - length) < 2e-3:
                trk = t; break
        if trk is None:
            failed += 1
            continue

        anchors = []
        for t in board.GetTracks():
            if t.Type() != pcbnew.PCB_VIA_T or t.GetNetCode() != code:
                continue
            if not t.IsOnLayer(plane):
                continue
            p = t.GetPosition()
            anchors.append((route.TOMM(p.x), route.TOMM(p.y)))
        if not anchors:
            failed += 1
            print(f"  {net:7} {lay}: no plane-connected anchors")
            continue

        a, c = trk.GetStart(), trk.GetEnd()
        ends = [(route.TOMM(a.x), route.TOMM(a.y)), (route.TOMM(c.x), route.TOMM(c.y))]
        r = route.Router(board)
        goals = r.cells_of_net(code, anchors)
        path = None
        start = None
        for e in ends:
            for vcost in (12, 6, 24):
                path = r.route_to_any(code, e, goals, via_cost=vcost)
                if path:
                    start = e; break
            if path:
                break
        if not path:
            failed += 1
            print(f"  {net:7} {lay} len {length:.3f}: no A* path to any of "
                  f"{len(anchors)} plane anchors")
            continue
        if not apply:
            kept += 1
            print(f"  {net:7} {lay} len {length:.3f}: would route from "
                  f"({start[0]:.2f},{start[1]:.2f})")
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
            print(f"  {net:7} {lay}: routed to plane anchor -> {un} unconnected")

    hard, un, _ = drc()
    print(f"\nkept {kept}, failed {failed} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
