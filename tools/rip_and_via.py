#!/usr/bin/env python3
"""
Rip the trace that blocks a needed via, place the via, then put the trace back.

The last stacked pairs cannot take a via anywhere: +5V has 289 candidate positions
across its whole overlap and foreign copper covers every one. No amount of searching
helps, because the space is occupied rather than merely tight.

What a person does here is move the thing that is in the way. So: find the foreign
track blocking the best candidate, delete it, place the via, and re-route the deleted
net with A*. If the re-route fails or DRC worsens, the whole attempt is rolled back -
trading one unconnected item for another is not progress.

Unlike tools/route_ripup.py (a documented dead end that explored far too large a graph
and never finished a round), this rips exactly ONE identified obstacle per attempt.

Usage:  python3 tools/rip_and_via.py [--apply]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/rv_backup.kicad_pcb"
RPT   = "/tmp/nav/rv.rpt"
TIERS = [(0.50, 0.25), (0.45, 0.20)]


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def stacked(text, radius=0.15):
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        eps = re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): (Pad \S+|Zone|Track|Via)'
                         r'[^\[]*\[([^\]]+)\][^\n]*?on (\S+?)[,\s]', blk[:400])[:2]
        if len(eps) != 2:
            continue
        a, b = eps
        if a[2] == "Zone" or b[2] == "Zone" or a[4] == b[4]:
            continue
        d = math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))
        if d <= radius:
            out.append((a[3], (float(a[0])+float(b[0]))/2, (float(a[1])+float(b[1]))/2))
    return out


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, text = drc()
    todo = stacked(text)
    print(f"baseline {hard0} errors, {un0} unconnected; "
          f"{len(todo)} stacked pairs with no room for a via\n")

    # ONE item per process. Looping LoadBoard here segfaults after the first
    # rollback - the same multi-load instability that forced fr_prepare.py into
    # separate stages. The caller drives the loop; see --one.
    only = None
    if "--one" in sys.argv:
        only = int(sys.argv[sys.argv.index("--one") + 1])
        todo = todo[only:only+1]

    kept = failed = 0
    for net, x, y in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        if n is None:
            failed += 1
            continue

        # Which foreign track sits on the spot we want?
        blockers = []
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                continue
            tn = t.GetNet()
            nm = tn.GetNetname() if tn else ""
            if nm == net or not nm:
                continue
            a, c = t.GetStart(), t.GetEnd()
            seg = ("cap", a.x/1e6, a.y/1e6, c.x/1e6, c.y/1e6, t.GetWidth()/2e6)
            g = route.gap_to_shape(x, y, seg)
            if g < 0.50:
                blockers.append((g, str(nm), t, (a.x/1e6, a.y/1e6), (c.x/1e6, c.y/1e6)))
        if not blockers:
            failed += 1
            print(f"  {net:7} at ({x:.2f},{y:.2f}): nothing to rip - blocked by pads")
            continue
        blockers.sort(key=lambda b: b[0])
        g, bnet, btrk, ba, bc = blockers[0]
        blay = board.GetLayerName(btrk.GetLayer())
        print(f"  {net:7} at ({x:.2f},{y:.2f}): blocked by [{bnet}] on {blay} "
              f"({g:.3f} mm)")
        if not apply:
            kept += 1
            continue

        shutil.copy(BOARD, BAK)
        # Gather ALL geometry before removing anything. board.Remove() invalidates the
        # SWIG wrapper, so calling route.hole_shapes(board) afterwards dies with
        # "'SwigPyObject' has no attribute 'Pads'" on a board that worked a line above.
        holes = route.hole_shapes(board)
        kos = route.keepout_boxes(board)
        foreign = route.obstacle_shapes(board, exclude_net=net)
        gone = ("cap", ba[0], ba[1], bc[0], bc[1], btrk.GetWidth()/2e6)
        foreign = [f for f in foreign
                   if not (f[0] == "cap" and abs(f[1]-gone[1]) < 1e-6
                           and abs(f[2]-gone[2]) < 1e-6
                           and abs(f[3]-gone[3]) < 1e-6
                           and abs(f[4]-gone[4]) < 1e-6)]
        board.Remove(btrk)
        placed = False
        for via_d, drill in TIERS:
            need = via_d / 2 + route.VIA_CLEAR
            if route.inside_board(x, y, via_d/2 + 0.4) \
               and route.hole_ok(x, y, holes, drill) \
               and not any(x1 - via_d/2 < x < x2 + via_d/2 and
                           y1 - via_d/2 < y < y2 + via_d/2
                           for x1, y1, x2, y2 in kos) \
               and not any(route.gap_to_shape(x, y, r) < need for r in foreign):
                v = route.add_via(board, x, y, n)
                v.SetWidth(pcbnew.FromMM(via_d)); v.SetDrill(pcbnew.FromMM(drill))
                placed = True
                break
        if not placed:
            shutil.copy(BAK, BOARD); failed += 1
            print(f"          still no room after ripping - reverted")
            continue

        # put the ripped net back
        bn = board.FindNet(bnet)
        r = route.Router(board)
        path = r.route(bn.GetNetCode(), ba, bc) if bn else None
        if path:
            r.commit(bn.GetNetCode(), bn, path)
        route.fill(board)
        board.Save(BOARD)
        hard, un, _ = drc()
        if hard > hard0 or un > un0:
            shutil.copy(BAK, BOARD); failed += 1
            print(f"          rolled back (+{hard-hard0} err, +{un-un0} unconn"
                  + ("" if path else ", reroute failed") + ")")
        else:
            kept += 1; un0 = un
            print(f"          via placed, [{bnet}] "
                  + ("rerouted" if path else "left open") + f" -> {un}")

    hard, un, _ = drc()
    print(f"\nkept {kept}, failed {failed} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
