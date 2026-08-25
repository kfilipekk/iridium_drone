#!/usr/bin/env python3
"""
Last-resort fanout for power pads the normal pass could not escape.

route.fanout() tries 24 angles out to 1.4 mm from the pad and gives up. On a board
this dense that leaves pads stranded which are sitting DIRECTLY OVER their own plane
pour - 25 of the 30 stranded power pads here were in exactly that position. They need
no routing at all, only a via that lands somewhere legal.

So this searches much harder (72 angles, 0.05 mm radial steps, out to 3 mm) and adds
the one constraint that actually matters: the via must land inside the plane's filled
polygon. A via over the pour is a connection; a via next to it is just a hole.

Every placement is DRC-verified with rollback, so a bad one costs nothing.

Usage:  python3 tools/fanout_hard.py [--apply]
"""
import os, sys, math, re, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/fh_backup.kicad_pcb"
RPT   = "/tmp/nav/fh.rpt"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def stranded_power(rpt_text):
    out = set()
    for m in re.finditer(r'Pad (\S+) \[([^\]]+)\] of (\w+)', rpt_text):
        pad, net, ref = m.groups()
        if net in route.PLANE:
            out.add((net, ref, pad))
    return sorted(out)


def pour_of(board, net):
    pid = board.GetLayerID(route.PLANE[net])
    return pid, [z.GetFilledPolysList(pid) for z in board.Zones()
                 if z.GetNetname() == net and pid in list(z.GetLayerSet().CuStack())]


def over_pour(polys, x_mm, y_mm):
    p = pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))
    for poly in polys:
        for i in range(poly.OutlineCount()):
            if poly.Contains(p, i):
                return True
    return False


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0 = drc()
    print(f"baseline {hard0} errors, {un0} unconnected\n")
    targets = stranded_power(open(RPT).read())
    print(f"{len(targets)} stranded power pads\n")

    kept = skipped = 0
    for net, ref, padname in targets:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        fp = board.FindFootprintByReference(ref)
        pad = next((q for q in fp.Pads() if q.GetNumber() == padname), None) if fp else None
        if pad is None:
            continue
        pid, polys = pour_of(board, net)
        if not polys:
            continue

        foreign = route.obstacle_shapes(board, exclude_net=net)
        holes = route.hole_shapes(board)
        kos = route.keepout_boxes(board)
        p = pad.GetPosition()
        px, py = route.TOMM(p.x), route.TOMM(p.y)
        pr = math.hypot(route.TOMM(pad.GetSize().x), route.TOMM(pad.GetSize().y)) / 2
        bbp = pad.GetBoundingBox()
        own = ("rect", route.TOMM(bbp.GetLeft()), route.TOMM(bbp.GetTop()),
               route.TOMM(bbp.GetRight()), route.TOMM(bbp.GetBottom()))
        need = route.VIA_D / 2 + route.VIA_CLEAR
        base = pr + need

        spot = None
        rad = base + 0.05
        while rad <= base + 3.0 and not spot:
            for k in range(72):
                a = k * math.pi / 36
                vx, vy = px + rad*math.cos(a), py + rad*math.sin(a)
                if not route.inside_board(vx, vy, route.VIA_D/2 + 0.5):
                    continue
                if not over_pour(polys, vx, vy):
                    continue
                if any(x1 - route.VIA_D/2 < vx < x2 + route.VIA_D/2 and
                       y1 - route.VIA_D/2 < vy < y2 + route.VIA_D/2
                       for x1, y1, x2, y2 in kos):
                    continue
                if any(route.gap_to_shape(vx, vy, r) < need for r in foreign):
                    continue
                if not route.hole_ok(vx, vy, holes):
                    continue
                steps = max(3, int(math.hypot(vx-px, vy-py) / 0.1))
                ok = True
                for r in foreign:
                    if r == own:
                        continue
                    for t in range(steps + 1):
                        sx = px + (vx-px)*t/steps; sy = py + (vy-py)*t/steps
                        if route.gap_to_shape(sx, sy, r) < route.TRACK_W/2 + route.VIA_CLEAR:
                            ok = False; break
                    if not ok:
                        break
                if ok:
                    spot = (vx, vy); break
            rad += 0.05

        if not spot:
            skipped += 1
            print(f"  {ref}.{padname:<4} {net:6} no legal via within 3 mm")
            continue
        if not apply:
            kept += 1
            print(f"  {ref}.{padname:<4} {net:6} would via at ({spot[0]:.2f},{spot[1]:.2f})")
            continue

        shutil.copy(BOARD, BAK)
        route.add_via(board, spot[0], spot[1], pad.GetNet())
        lay = "F.Cu" if pad.IsOnLayer(board.GetLayerID("F.Cu")) else "B.Cu"
        route.add_track(board, (px, py), spot, lay, pad.GetNet(), width=0.25)
        route.fill(board); board.Save(BOARD)
        hard, un = drc()
        if hard > hard0 or un >= un0:
            shutil.copy(BAK, BOARD); skipped += 1
            print(f"  {ref}.{padname:<4} {net:6} rolled back "
                  f"({hard-hard0:+d} err, {un-un0:+d} unconn)")
        else:
            kept += 1; un0 = un
            print(f"  {ref}.{padname:<4} {net:6} via at ({spot[0]:.2f},{spot[1]:.2f})"
                  f"   unconnected now {un}")

    hard, un = drc()
    print(f"\nkept {kept}, skipped {skipped} -> {hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
