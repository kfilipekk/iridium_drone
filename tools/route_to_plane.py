#!/usr/bin/env python3
"""
Route stranded plane-net pads to copper that actually reaches the plane.

This is what tools/route_gnd.py was trying to be. That script routed each stranded
pad to "any cell already owned by the net", which on a mostly-GND board connects a pad
to copper it already touches - it reports success while nothing changes. The goal has
to be copper that is *demonstrably tied to the plane*, which means a via spanning both
this layer and the plane layer.

It also covers the case route_remaining.py cannot: a Pad-Zone unconnected item. The
DRC report gives a zone's outline origin rather than the island's position, so those
pairs carry no usable coordinate. Here the anchors are found geometrically instead.

Why a trace and not a via: these pads sit in pour slivers narrower than any legal via
- 0.45 mm plus clearance does not fit, at any sampling density. A 0.1016 mm trace needs
a fraction of that room, so it can leave where a via cannot.

Usage:  python3 tools/route_to_plane.py [net] [--apply]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/rtp_backup.kicad_pcb"
RPT   = "/tmp/nav/rtp.rpt"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def stranded(text, net):
    """Pads this net's unconnected items name, deduplicated."""
    out = set()
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        if f"[{net}]" not in blk[:400]:
            continue
        for m in re.finditer(r'Pad (\S+) \[' + re.escape(net) + r'\] of (\w+)', blk[:400]):
            out.add((m.group(2), m.group(1)))
    return sorted(out)


def anchors(board, net):
    """Points on copper that provably reaches the plane: vias spanning both layers."""
    plane = board.GetLayerID(route.PLANE[net])
    code = board.FindNet(net).GetNetCode()
    pts = []
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T or t.GetNetCode() != code:
            continue
        if not t.IsOnLayer(plane):
            continue
        p = t.GetPosition()
        pts.append((route.TOMM(p.x), route.TOMM(p.y)))
    return pts


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    net = args[0] if args else "GND"
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, text = drc()
    todo = stranded(text, net)
    print(f"baseline {hard0} errors, {un0} unconnected; "
          f"{len(todo)} stranded {net} pads\n")

    kept = failed = 0
    for ref, padname in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        fp = board.FindFootprintByReference(ref)
        pad = next((q for q in fp.Pads() if q.GetNumber() == padname), None) if fp else None
        if pad is None:
            failed += 1
            continue
        pts = anchors(board, net)
        if not pts:
            print("no plane-connected anchors at all - nothing to aim at")
            return 1
        p = pad.GetPosition()
        A = (route.TOMM(p.x), route.TOMM(p.y))
        pts.sort(key=lambda q: math.hypot(q[0] - A[0], q[1] - A[1]))

        r = route.Router(board)
        code = n.GetNetCode()
        path = None
        for B in pts[:12]:                      # nearest dozen anchors, closest first
            path = r.route(code, A, B)
            if path:
                break
        if not path:
            failed += 1
            print(f"  {ref}.{padname:<4} no path to any plane anchor")
            continue
        if not apply:
            kept += 1
            print(f"  {ref}.{padname:<4} would route")
            continue

        shutil.copy(BOARD, BAK)
        r.commit(code, n, path)
        route.fill(board)
        board.Save(BOARD)
        hard, un, _ = drc()
        if hard > hard0 or un > un0:
            shutil.copy(BAK, BOARD)
            failed += 1
            print(f"  {ref}.{padname:<4} rolled back "
                  f"(+{hard-hard0} err, +{un-un0} unconn)")
        else:
            kept += 1
            print(f"  {ref}.{padname:<4} routed -> {un} unconnected")
            un0 = un

    hard, un, _ = drc()
    print(f"\nkept {kept}, failed {failed} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
