#!/usr/bin/env python3
"""
Give a power rail a plane region where it does not have one, and stitch a pad into it.

The In4.Cu rails are rectangles punched into a +3V3 base pour, built by
route.power_islands() as bounding boxes around each rail's pad clusters. That works for
pads in the middle of a cluster and fails completely for the ones at the edges: VBAT's
two rectangles span x=117-136 while J2.2, the battery connector, is at x=101.9. It sits
on no plane at all, so every amp the aircraft draws enters the board through 4 mil
copper.

Widening the traces helps and is not enough - tools/widen_net.py got VBAT from 0.45 A to
0.60 A against the 1.7 A it needs, because the bottleneck segments are hemmed in. The
copper has to come from the plane.

This adds a rectangular zone for a rail on In4.Cu and drops stitching vias from a pad
into it. Zones of the same net merge where they overlap, so extending a rail is a matter
of adding a corridor that reaches the existing region rather than resizing anything.

Priority matters: +3V3 is the base pour at priority 0 and every other rail sits above it.
A new region only has to outrank +3V3, and must not be dropped on top of a different
rail's rectangle.

Usage:
  python3 tools/extend_pour.py --net VBAT --rect 101.0,118.0,118.0,123.0 \
      --stitch J2.2 --prio 2 [--apply]
"""
import os, re, sys, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/pour_backup.kicad_pcb"
RPT   = "/tmp/nav/pour.rpt"
TOMM  = route.TOMM
MM    = pcbnew.FromMM
VIA_D, DRILL = 0.45, 0.20


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def existing_rails(board):
    """Every In4.Cu rail rectangle already on the board, with its net and priority."""
    out = []
    lid = board.GetLayerID("In4.Cu")
    for z in board.Zones():
        n = z.GetNet()
        if not n or lid not in list(z.GetLayerSet().CuStack()):
            continue
        o = z.Outline()
        if not o.OutlineCount():
            continue
        ol = o.Outline(0)
        pts = [(TOMM(ol.CPoint(k).x), TOMM(ol.CPoint(k).y))
               for k in range(ol.PointCount())]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        out.append((n.GetNetname(), z.GetAssignedPriority(),
                    (min(xs), min(ys), max(xs), max(ys))))
    return out


def main():
    def arg(name, default=None):
        return sys.argv[sys.argv.index(name)+1] if name in sys.argv else default
    netname = arg("--net")
    rect = arg("--rect")
    stitch = [s for s in (arg("--stitch") or "").split(",") if s]
    prio = arg("--prio")
    apply = "--apply" in sys.argv
    if not netname or not rect:
        print(__doc__.strip()); return 2
    x1, y1, x2, y2 = (float(v) for v in rect.split(","))
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, _ = drc()
    print(f"baseline {hard0} errors, {un0} unconnected")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    net = board.FindNet(netname)
    if net is None:
        print(f"  no net {netname}"); return 1

    # refuse to sit on another rail's rectangle - the base +3V3 pour is fair game
    for nm, pr, (a1, b1, a2, b2) in existing_rails(board):
        # An unnamed zone is a keepout or rule area - the mounting-hole exclusions are
        # the ones on this board. A pour may overlap those: KiCad simply does not fill
        # inside them. Only another RAIL is a genuine conflict.
        if nm in (netname, "+3V3", "GND", ""):
            continue
        if x1 < a2 and a1 < x2 and y1 < b2 and b1 < y2:
            print(f"  refusing: overlaps the {nm} rail rectangle "
                  f"({a1:.1f},{b1:.1f})-({a2:.1f},{b2:.1f}) at priority {pr}")
            return 1
    # KiCad refuses two intersecting zones at the same priority, even on the same net.
    # The new region always overlaps something (that is the point), so pick a priority
    # nothing else is using rather than making the caller guess.
    used = {pr for _nm, pr, _r in existing_rails(board)}
    prio = int(prio) if prio else max(used) + 1
    if prio in used:
        prio = max(used) + 1
    print(f"  priority {prio} (in use: {sorted(used)})")

    kob = [r for nm, _p, r in existing_rails(board) if nm == ""]
    hit_ko = [r for r in kob if x1 < r[2] and r[0] < x2 and y1 < r[3] and r[1] < y2]
    if hit_ko:
        print(f"  note: overlaps {len(hit_ko)} keepout area(s) - the pour will not fill "
              f"there, so the corridor must not depend on that ground")

    touching = [r for nm, pr, r in existing_rails(board)
                if nm == netname and x1 < r[2] and r[0] < x2 and y1 < r[3] and r[1] < y2]
    print(f"  new {netname} region ({x1},{y1})-({x2},{y2}) = "
          f"{(x2-x1)*(y2-y1):.0f} mm2, overlaps {len(touching)} existing "
          f"{netname} region(s)")
    if not touching:
        print("  WARNING: does not touch an existing region of this net - it would be "
              "an island unless the stitched pad ties it down")

    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0

    shutil.copy(BOARD, BAK)
    z = pcbnew.ZONE(board)
    z.SetLayer(board.GetLayerID("In4.Cu"))
    z.SetNet(net)
    z.SetAssignedPriority(prio)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetLocalClearance(MM(0.1016))
    z.SetMinThickness(MM(0.1016))
    o = z.Outline(); o.NewOutline()
    for px, py in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        o.Append(MM(px), MM(py))
    board.Add(z)

    # stitch the named pads down into it
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)
    allsh = [s for s in shove.shapes_of(board) if s.net != netname]
    idx = shove.ShapeIndex(allsh)
    need = VIA_D/2 + route.VIA_CLEAR + 0.005
    placed = 0
    for spec in stitch:
        ref, num = spec.split(".", 1)
        fp = board.FindFootprintByReference(ref)
        pad = next((q for q in fp.Pads() if q.GetNumber() == num), None) if fp else None
        if pad is None:
            print(f"  {spec}: no such pad"); continue
        px, py = TOMM(pad.GetPosition().x), TOMM(pad.GetPosition().y)
        best = None
        for r in [v/100 for v in range(30, 300, 5)]:
            for k in range(48):
                a = k * math.pi / 24
                vx, vy = px + r*math.cos(a), py + r*math.sin(a)
                if not (x1 <= vx <= x2 and y1 <= vy <= y2):
                    continue
                if not route.inside_board(vx, vy, VIA_D/2 + 0.35):
                    continue
                if not route.hole_ok(vx, vy, holes, DRILL):
                    continue
                if any(a1 - VIA_D/2 < vx < a2 + VIA_D/2 and b1 - VIA_D/2 < vy < b2 + VIA_D/2
                       for a1, b1, a2, b2 in kos):
                    continue
                if any(route.gap_to_shape(vx, vy, s.geom) < need
                       for s in idx.near(vx, vy, need + 1.0)):
                    continue
                best = (vx, vy); break
            if best:
                break
        if not best:
            print(f"  {spec}: nowhere to stitch a via into the new region")
            continue
        vx, vy = best
        v = route.add_via(board, vx, vy, net)
        v.SetWidth(MM(VIA_D)); v.SetDrill(MM(DRILL))
        lay = "F.Cu" if pad.IsOnLayer(board.GetLayerID("F.Cu")) else "B.Cu"
        route.add_track(board, (px, py), (vx, vy), lay, net, width=0.5)
        placed += 1
        print(f"  {spec}: stitched at ({vx:.2f},{vy:.2f}), "
              f"{math.hypot(vx-px, vy-py):.2f} mm of 0.5 mm trace")

    route.fill(board)
    board.Save(BOARD)
    hard, un, txt = drc()
    if hard <= hard0 and un <= un0:
        print(f"  added {netname} region + {placed} stitch via(s) -> "
              f"{hard} errors, {un} unconnected")
        return 0
    bad = [z2 for z2 in re.split(r'^\[', txt, flags=re.M)
           if z2 and not z2.startswith("unconnected_items") and not z2.startswith("** ")]
    print(f"  rolled back: +{hard-hard0} err, {un} unconn"
          + (f" - {bad[0].splitlines()[0]}" if bad else ""))
    shutil.copy(BAK, BOARD)
    return 1


if __name__ == "__main__":
    sys.exit(main())
