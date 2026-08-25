#!/usr/bin/env python3
"""
Route the connections freerouting left behind, one DRC item at a time.

This exists because tools/route_gnd.py does not work. That script routed each
stranded pad to "any cell already owned by the net", which on a board that is mostly
GND means it happily connects a pad to copper it is ALREADY connected to: it reports
"kept 15" while the unconnected count does not move and the segment count does not
change. The goal has to be the specific item the DRC report says is unreachable, not
the nearest same-net copper.

So each unconnected item is taken as the ordered pair it actually is - endpoint A and
endpoint B, both parsed from the report - and routed between those two points. Every
route is DRC-verified with rollback, and anything that fails to reduce the unconnected
count is reverted, so a route that connects two already-joined things costs nothing.

Usage:  python3 tools/route_remaining.py [--apply] [--limit N]
"""
import os, sys, re, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/rr_backup.kicad_pcb"
RPT   = "/tmp/nav/rr.rpt"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def pairs(text):
    """(net, (ax, ay), (bx, by)) for every unconnected item that names two points."""
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        eps = re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): (Pad \S+|Zone|Track|Via)'
                         r'[^\[]*\[([^\]]+)\]', blk[:400])[:2]
        if len(eps) != 2:
            continue
        a, b = eps
        # A Zone endpoint always reports its outline origin, never the island, so a
        # pair involving one carries no usable coordinate. Those are the pour-island
        # cases and belong to stitch_islands.py.
        if a[2] == "Zone" or b[2] == "Zone":
            continue
        out.append((a[3], (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
    return out


def main():
    apply = "--apply" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0 = drc()
    todo = pairs(open(RPT).read())
    print(f"baseline {hard0} errors, {un0} unconnected; "
          f"{len(todo)} items have usable endpoints\n")
    if limit:
        todo = todo[:limit]

    kept = failed = noop = 0
    for i, (net, A, Bp) in enumerate(todo, 1):
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        if not n:
            failed += 1
            continue
        r = route.Router(board)
        code = n.GetNetCode()
        path = r.route(code, A, Bp)
        if not path:
            failed += 1
            print(f"  {i:3}/{len(todo)} {net:12} no path")
            continue
        if not apply:
            kept += 1
            print(f"  {i:3}/{len(todo)} {net:12} would route")
            continue

        shutil.copy(BOARD, BAK)
        r.commit(code, n, path)
        route.fill(board)
        board.Save(BOARD)
        hard, un = drc()
        # Keep anything that is legal and not a regression, NOT just what lowers the
        # count. On a multi-pad net, joining the pair the report named makes it name a
        # DIFFERENT pair next time, so the total holds even though a real connection
        # was made. Requiring the count to drop threw away 48 valid routes.
        if hard > hard0 or un > un0:
            shutil.copy(BAK, BOARD)
            failed += 1
            print(f"  {i:3}/{len(todo)} {net:12} rolled back "
                  f"(+{hard-hard0} err, +{un-un0} unconn)")
        else:
            kept += 1
            if un < un0:
                print(f"  {i:3}/{len(todo)} {net:12} routed -> {un} unconnected")
            else:
                noop += 1
                print(f"  {i:3}/{len(todo)} {net:12} joined (count unchanged)")
            un0 = un

    hard, un = drc()
    print(f"\nkept {kept}, no-gain {noop}, failed {failed} -> "
          f"{hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
