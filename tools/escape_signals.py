#!/usr/bin/env python3
"""
Give stranded SIGNAL pads an escape via, so the routers have something to aim at.

route.fanout() only ever escaped plane nets - it skips anything not in route.PLANE.
Signal pins therefore depend entirely on freerouting's own fanout, which reached 73%
of pins on this board. The 27% it missed are why SPI1, SPI4, VCAP2, M1 and SD_CK do
not appear in the SES at all: freerouting never escaped their pins, so it could not
route them, and no amount of extra passes changes that.

VCAP2 is the clearest case. U1.73 and C9.1 are 1.8 mm apart on opposite sides of the
board. The connection is trivial - it needs one via, and neither end had one.

A via plus a short stub is placed next to each stranded signal pad, on the pad's own
layer, DRC-verified with rollback. route_remaining.py can then route pad-to-pad
through them.

Usage:  python3 tools/escape_signals.py [--apply]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/esc_backup.kicad_pcb"
RPT   = "/tmp/nav/esc.rpt"
TIERS = [(0.60, 0.30), (0.50, 0.25), (0.45, 0.20)]


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def stranded_signals(text):
    out = set()
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        for m in re.finditer(r'Pad (\S+) \[([^\]]+)\] of (\w+)', blk[:400]):
            pad, net, ref = m.groups()
            if net not in route.PLANE:
                out.add((net, ref, pad))
    return sorted(out)


def has_via_near(board, pad, code, radius=0.9):
    p = pad.GetPosition()
    x, y = route.TOMM(p.x), route.TOMM(p.y)
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T or t.GetNetCode() != code:
            continue
        q = t.GetPosition()
        if math.hypot(route.TOMM(q.x) - x, route.TOMM(q.y) - y) < radius:
            return True
    return False


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, text = drc()
    todo = stranded_signals(text)
    print(f"baseline {hard0} errors, {un0} unconnected; "
          f"{len(todo)} stranded signal pads\n")

    placed = skipped = 0
    for net, ref, padname in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        fp = board.FindFootprintByReference(ref)
        pad = next((q for q in fp.Pads() if q.GetNumber() == padname), None) if fp else None
        if pad is None or n is None:
            skipped += 1
            continue
        if has_via_near(board, pad, n.GetNetCode()):
            skipped += 1
            continue

        foreign = route.obstacle_shapes(board, exclude_net=net)
        holes = route.hole_shapes(board)
        kos = route.keepout_boxes(board)
        p = pad.GetPosition()
        px, py = route.TOMM(p.x), route.TOMM(p.y)
        pr = math.hypot(route.TOMM(pad.GetSize().x),
                        route.TOMM(pad.GetSize().y)) / 2
        bb = pad.GetBoundingBox()
        own = ("rect", route.TOMM(bb.GetLeft()), route.TOMM(bb.GetTop()),
               route.TOMM(bb.GetRight()), route.TOMM(bb.GetBottom()))
        layer = "F.Cu" if pad.IsOnLayer(board.GetLayerID("F.Cu")) else "B.Cu"

        spot = None
        for via_d, drill in TIERS:
            need = via_d / 2 + route.VIA_CLEAR
            rad = pr + need + 0.05
            while rad <= pr + need + 2.2 and not spot:
                for k in range(72):
                    a = k * math.pi / 36
                    vx, vy = px + rad*math.cos(a), py + rad*math.sin(a)
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
                    # A STRAIGHT stub is too strict. VCAP2 has 8 legal via
                    # positions 1.5 mm out, and every one was rejected because the
                    # straight line to it crosses other copper - even though a
                    # two-segment path around that copper exists. Accept the position
                    # here and let A* find the stub below.
                    spot = (vx, vy, via_d, drill); break
                rad += 0.05
            if spot:
                break

        if not spot:
            skipped += 1
            print(f"  {ref}.{padname:<4} {net:12} no escape within 2.2 mm")
            continue
        if not apply:
            placed += 1
            print(f"  {ref}.{padname:<4} {net:12} would escape via "
                  f"{spot[2]:.2f} mm at ({spot[0]:.2f},{spot[1]:.2f})")
            continue

        shutil.copy(BOARD, BAK)
        vx, vy, via_d, drill = spot
        # Route the stub rather than drawing it straight - the whole point of
        # accepting a position the straight line could not reach.
        r = route.Router(board)
        stub = r.route(n.GetNetCode(), (px, py), (vx, vy))
        if not stub:
            shutil.copy(BAK, BOARD)
            skipped += 1
            print(f"  {ref}.{padname:<4} {net:12} via spot found but no stub path")
            continue
        v = route.add_via(board, vx, vy, n)
        v.SetWidth(pcbnew.FromMM(via_d)); v.SetDrill(pcbnew.FromMM(drill))
        r.commit(n.GetNetCode(), n, stub)
        route.fill(board)
        board.Save(BOARD)
        hard, un, _ = drc()
        if hard > hard0 or un > un0:
            shutil.copy(BAK, BOARD)
            skipped += 1
            print(f"  {ref}.{padname:<4} {net:12} rolled back (+{hard-hard0} err)")
        else:
            placed += 1
            un0 = un
            print(f"  {ref}.{padname:<4} {net:12} escaped via {via_d:.2f} mm -> {un}")

    hard, un, _ = drc()
    print(f"\nplaced {placed}, skipped {skipped} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
