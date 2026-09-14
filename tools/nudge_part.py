#!/usr/bin/env python3
"""
Move a part a fraction of a millimetre so its pad can reach copper it cannot reach now.

The last unconnected item is a 1.52 mm2 sliver of B.Cu ground pour carrying C71.2, the
ground end of the 9 V buck's compensation capacitor. Leaving it floating is a real
fault, not a cosmetic one - the regulator's control loop loses its reference - so it is
worth more than a shrug.

Everything else has been ruled out, and the reason is specific rather than vague:

  * the sliver is sealed - a flood from inside it reaches exactly its own 3001 cells
  * no via fits inside it; the best spot is 0.085 mm short
  * the traces holding it cannot be shoved, because C71's and C72's own pads box them in
  * BUCK_EN cannot be rerouted, because the one via position that WOULD free the sliver
    is precisely the corridor BUCK_EN needs to reach R5.1 - the two are mutually
    exclusive, so no amount of routing settles it

What is left is to move the part, which is what a layout engineer would have done long
before writing four tools. A 0402 shifted a couple of tenths of a millimetre is nothing
electrically - and C71 sits in a compensation network whose placement is already flagged
for review in docs/LAYOUT.md.

Moving a footprint detaches every trace that ended on its pads, so each one is stitched
back - and the stitch is ROUTED, not drawn straight. Straight stitches threw away every
workable offset for C71: of roughly a thousand positions where its pads fit, all of them
failed either because a straight line back to the old trace end clipped something, or
because the ground pad had no straight shot to live copper. One flood per layer, out
from the copper that has to be reached, answers both questions for every offset at once
and gives the actual path to lay down.

The part's OWN pads move too, and they are obstacles to each other's routes. Leaving
them out of the flood is what made the first working placements short C71's ground link
straight through its own BUCK9_COMP2 pad - a genuine short, not a clearance nit. So the
screening flood is optimistic and every surviving candidate is re-routed against a grid
that has the moved pads in their new places before it is written.

Offsets are tried smallest first, screened geometrically, and only the survivors cost a
DRC run.

Turning the part round is tried as well as sliding it. C71 is a ceramic capacitor with
no polarity, so a 180 degree rotation is free electrically, and it swaps which end of
the part its ground pad sits at - which is the whole problem here. Rotating is applied
as a reflection of each pad through the footprint origin, so there is no sign
convention to get wrong.

--toward REF.PAD changes what "best" means. By default the smallest move wins, which is
right when the goal is just to get a pad onto live copper. When the goal is to shorten a
decoupling path the smallest move is the wrong objective entirely - what matters is the
distance to the pin being decoupled, so that becomes the sort key instead.

Usage:  python3 tools/nudge_part.py C71 [--apply] [--max MM] [--step MM] [--no-rotate]
        python3 tools/nudge_part.py C39 --toward U7.11 --apply
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove, island_route as ir

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/nudge_backup.kicad_pcb"
RPT   = "/tmp/nav/nudge.rpt"
TIERS = [(0.45, 0.20), (0.50, 0.25), (0.60, 0.30)]
# Copper clearance is not the only rule a moved part has to satisfy. Two more bit on
# the first attempt and both are cheap to screen for, so they are screened rather than
# discovered one slow DRC run at a time:
#   MASK_GAP  - the solder mask web between apertures of different nets. Copper 0.1016
#               mm apart is legal but its mask openings merge, and a merged aperture is
#               a solder bridge waiting to happen. It caught the routed ground link
#               running past C71's own BUCK9_COMP2 pad.
#   courtyard - two parts may not overlap courtyards even when their copper clears.
MASK_GAP = 0.28
TOMM  = route.TOMM
MM    = pcbnew.FromMM


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def pad_info(board, fp):
    """Each pad's net, layers, half-size and the track ends currently landing on it."""
    out = []
    for pad in fp.Pads():
        n = pad.GetNet()
        nm = n.GetNetname() if n else ""
        bb = pad.GetBoundingBox()
        p = pad.GetPosition()
        hw = TOMM(bb.GetRight() - bb.GetLeft()) / 2
        hh = TOMM(bb.GetBottom() - bb.GetTop()) / 2
        ls = frozenset(L for L in shove.COPPER if pad.IsOnLayer(board.GetLayerID(L)))
        ends = []
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != pad.GetNetCode():
                continue
            lay = board.GetLayerName(t.GetLayer())
            if lay not in ls:
                continue
            for q in (t.GetStart(), t.GetEnd()):
                if bb.GetLeft() <= q.x <= bb.GetRight() and \
                   bb.GetTop() <= q.y <= bb.GetBottom():
                    ends.append((lay, (TOMM(q.x), TOMM(q.y))))
        out.append({"num": pad.GetNumber(), "net": nm, "lset": ls,
                    "pos": (TOMM(p.x), TOMM(p.y)), "hw": hw, "hh": hh, "ends": ends})
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print(__doc__.strip().splitlines()[-1]); return 2
    ref = sys.argv[1]
    apply = "--apply" in sys.argv
    maxr = float(sys.argv[sys.argv.index("--max")+1]) if "--max" in sys.argv else 0.60
    step = float(sys.argv[sys.argv.index("--step")+1]) if "--step" in sys.argv else 0.05
    step_grid = 0.02
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, _ = drc()
    print(f"baseline {hard0} errors, {un0} unconnected\n")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        print(f"{ref} not found"); return 1
    pads = pad_info(board, fp)
    gnd = [p for p in pads if p["net"] == "GND"]
    if not gnd:
        print(f"{ref} has no ground pad to rescue"); return 1
    print(f"{ref}: " + ", ".join(f"{p['num']}[{p['net']}] {len(p['ends'])} track end(s)"
                                 for p in pads))

    # Obstacles: everything except this part's own pads, which are moving.
    allsh = []
    for other in board.GetFootprints():
        if other.GetReference() == ref:
            continue
        for pad in other.Pads():
            n = pad.GetNet()
            bb = pad.GetBoundingBox()
            ls = frozenset(L for L in shove.COPPER
                           if pad.IsOnLayer(board.GetLayerID(L)))
            allsh.append(shove.Shape(("rect", TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                                      TOMM(bb.GetRight()), TOMM(bb.GetBottom())),
                                     "pad", n.GetNetname() if n else "", lset=ls))
    for t in board.GetTracks():
        n = t.GetNet()
        nm = n.GetNetname() if n else ""
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            try:
                r = TOMM(t.GetWidth(board.GetLayerID("F.Cu"))) / 2
            except TypeError:
                r = route.VIA_D / 2
            allsh.append(shove.Shape(("cap", TOMM(p.x), TOMM(p.y),
                                      TOMM(p.x), TOMM(p.y), r), "via", nm))
        else:
            a, b = t.GetStart(), t.GetEnd()
            lay = board.GetLayerName(t.GetLayer())
            allsh.append(shove.Shape(("cap", TOMM(a.x), TOMM(a.y), TOMM(b.x), TOMM(b.y),
                                      TOMM(t.GetWidth())/2), "track", nm, layer=lay,
                                     lset=frozenset([lay])))
    idx = shove.ShapeIndex(allsh)
    # foreign pads only, for the mask-web test
    pidx = shove.ShapeIndex([x for x in allsh if x.kind == "pad"])
    # Courtyards of every other part on the SAME SIDE, as boxes. Comparing a front
    # courtyard against a back-side part's is a false positive by construction - the two
    # can never touch. It is also not a small one: U5's front courtyard boxes over 14
    # back-side parts, so every offset in the search "overlapped a courtyard" and the
    # tool reported no workable placement for a part it had never actually tested.
    def side_of(f):
        return pcbnew.B_CrtYd if f.GetLayer() == pcbnew.B_Cu else pcbnew.F_CrtYd

    my_side = side_of(fp)
    yards = []
    for other in board.GetFootprints():
        if other.GetReference() == ref:
            continue
        # The OTHER part's courtyard on THIS part's side, not the other's own side.
        # Taking the other's own side just puts every back-side part back into the list.
        try:
            poly = other.GetCourtyard(my_side)
        except Exception:
            continue
        if poly.OutlineCount() == 0:
            continue
        bb = poly.BBox()
        yards.append((TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                      TOMM(bb.GetRight()), TOMM(bb.GetBottom())))
    my_yard = None
    try:
        poly = fp.GetCourtyard(my_side)
        if poly.OutlineCount():
            bb = poly.BBox()
            my_yard = (TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                       TOMM(bb.GetRight()), TOMM(bb.GetBottom()))
    except Exception:
        my_yard = None
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)

    # One flood per thing that must be reached. Obstacles for a net's own route never
    # include that net's copper - there is no clearance rule between same-net pieces.
    cx0 = TOMM(fp.GetPosition().x); cy0 = TOMM(fp.GetPosition().y)
    fbox = (cx0 - maxr, cy0 - maxr, cx0 + maxr, cy0 + maxr)
    floods = {}
    def flood_for(key, lay, net, seeds):
        if key in floods:
            return floods[key]
        keep = [x for x in allsh if x.net != net]
        g = ir.Grid(board, lay, fbox, step_grid, keep, 2.0)
        cells = set()
        for sp in seeds:
            c = g.cell(*sp)
            if g.ok(*c):
                cells.add(c)
            else:                       # seed sits under copper; take a legal neighbour
                for di in range(-4, 5):
                    for dj in range(-4, 5):
                        if g.ok(c[0]+di, c[1]+dj):
                            cells.add((c[0]+di, c[1]+dj))
        if not cells:
            floods[key] = None
            return None
        floods[key] = (g,) + shove.spread(g, cells)
        return floods[key]

    route.fill(board)
    glay = sorted(gnd[0]["lset"])[0]
    main_pour = [q for q in ir.gnd_polys(board).get(glay, []) if ir.area(q) > 50.0]
    pour_seeds = [pt for q in main_pour for pt in q[::max(1, len(q)//200)]]
    print(f"{len(main_pour)} main ground pour region(s) on {glay}, "
          f"{len(pour_seeds)} seed points")

    def clear_rect(cx, cy, hw, hh, lset, net, margin):
        """Does a pad at (cx,cy) keep `margin` from foreign copper on its layers?"""
        for sh in idx.near(cx, cy, max(hw, hh) + margin + 1.0):
            if sh.net == net or not (sh.lset & lset):
                continue
            # distance from the pad rectangle to the shape, sampled on its border
            for u in range(-6, 7):
                for v in (-1, 1):
                    px, py = cx + hw*u/6.0, cy + hh*v
                    if route.gap_to_shape(px, py, sh.geom) < margin:
                        return False
                    px, py = cx + hw*v, cy + hh*u/6.0
                    if route.gap_to_shape(px, py, sh.geom) < margin:
                        return False
            if route.gap_to_shape(cx, cy, sh.geom) < margin:
                return False
        return True

    def seg_clear(a, b, lay, net, margin):
        for x, y in shove._walk([a, b], 0.02):
            for sh in idx.near(x, y, margin + 1.0):
                if sh.net == net or lay not in sh.lset:
                    continue
                if route.gap_to_shape(x, y, sh.geom) < margin:
                    return False
        return True

    def mask_ok(x, y, net, margin=MASK_GAP):
        """Would a mask aperture here merge with a foreign net's aperture?"""
        for sh in pidx.near(x, y, margin + 1.0):
            if sh.net == net:
                continue
            if route.gap_to_shape(x, y, sh.geom) < margin:
                return False
        return True

    def yard_ok(dx, dy):
        if my_yard is None:
            return True
        x1, y1, x2, y2 = my_yard[0]+dx, my_yard[1]+dy, my_yard[2]+dx, my_yard[3]+dy
        for a1, b1, a2, b2 in yards:
            if x1 < a2 and a1 < x2 and y1 < b2 and b1 < y2:
                return False
        return True

    def run_ok(run, net):
        return all(mask_ok(x, y, net) for x, y in shove._walk(run, 0.04))

    def via_here(x, y, net):
        for via_d, drill in TIERS:
            need = via_d/2 + route.VIA_CLEAR + 0.005
            if not route.inside_board(x, y, via_d/2 + 0.35):
                continue
            if any(x1 - via_d/2 < x < x2 + via_d/2 and y1 - via_d/2 < y < y2 + via_d/2
                   for x1, y1, x2, y2 in kos):
                continue
            if not route.hole_ok(x, y, holes, drill):
                continue
            if any(route.gap_to_shape(x, y, sh.geom) < need
                   for sh in idx.near(x, y, need + 1.0) if sh.net != net):
                continue
            return via_d, drill
        return None

    def moved_pad_shapes(rot, dx, dy, skip_net):
        """The part's own pads at their new places, as obstacles for another net."""
        out = []
        for q in pads:
            if q["net"] == skip_net:
                continue
            qx, qy = placed(q, rot, dx, dy)
            out.append(shove.Shape(("rect", qx - q["hw"], qy - q["hh"],
                                    qx + q["hw"], qy + q["hh"]),
                                   "pad", q["net"], lset=q["lset"]))
        return out

    def route_run(lay, net, seeds, target, rot, dx, dy):
        """Route `net` on `lay` from `target` back to `seeds`, moved pads included."""
        keep = [x for x in allsh if x.net != net] + moved_pad_shapes(rot, dx, dy, net)
        g = ir.Grid(board, lay, fbox, step_grid, keep, 2.0)
        cells = set()
        for sp in seeds:
            c = g.cell(*sp)
            if g.ok(*c):
                cells.add(c)
            else:
                for di in range(-4, 5):
                    for dj in range(-4, 5):
                        if g.ok(c[0]+di, c[1]+dj):
                            cells.add((c[0]+di, c[1]+dj))
        if not cells:
            return None
        d, pv = shove.spread(g, cells)
        tc = g.cell(*target)
        if tc not in d:
            return None
        run = shove.straighten(shove.walk_back(g, pv, tc))[::-1]
        run[-1] = target
        return run

    def full_routes(rot, dx, dy):
        """Every piece of copper this placement needs, or None if any of it fails."""
        out = []
        for q in pads:
            qx, qy = placed(q, rot, dx, dy)
            for lay, e in q["ends"]:
                run = route_run(lay, q["net"],
                                [w for l2, w in q["ends"] if l2 == lay],
                                (qx, qy), rot, dx, dy)
                if run is None or not run_ok(run, q["net"]):
                    return None
                out.append((lay, q["net"], run))
        gx, gy = placed(gnd[0], rot, dx, dy)
        if not any(ir.inside(q, gx, gy) for q in main_pour):
            run = route_run(glay, "GND", pour_seeds, (gx, gy), rot, dx, dy)
            if run is None or not run_ok(run, "GND"):
                return None
            out.append((glay, "GND", run))
        return out

    n = int(maxr / step)
    cands = []
    stat = {"total": 0, "pad": 0, "stitch": 0, "no_ground": 0,
            "yard": 0, "mask": 0}
    fpx, fpy = TOMM(fp.GetPosition().x), TOMM(fp.GetPosition().y)
    rots = [0] if "--no-rotate" in sys.argv else [0, 180]
    toward_pt = None
    if "--toward" in sys.argv:
        spec = sys.argv[sys.argv.index("--toward") + 1]
        tref, tnum = spec.split(".", 1)
        tfp = board.FindFootprintByReference(tref)
        tp = next((q for q in tfp.Pads() if q.GetNumber() == tnum), None) if tfp else None
        if tp is None:
            print(f"  no pad {spec}"); return 1
        toward_pt = (TOMM(tp.GetPosition().x), TOMM(tp.GetPosition().y))
        cur = min(math.hypot(q["pos"][0]-toward_pt[0], q["pos"][1]-toward_pt[1])
                  for q in pads)
        print(f"  moving toward {spec}: closest pad is {cur:.2f} mm away now")

    def placed(p, rot, dx, dy):
        """Where pad `p` ends up for this rotation and offset."""
        px, py = p["pos"]
        if rot == 180:                       # reflection through the footprint origin
            px, py = 2*fpx - px, 2*fpy - py
        return px + dx, py + dy
    for rot in rots:
      for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            dx, dy = i*step, j*step
            r = math.hypot(dx, dy)
            if r > maxr or (r < 1e-9 and rot == 0):
                continue
            stat["total"] += 1
            if not yard_ok(dx, dy):
                stat["yard"] += 1
                continue
            ok = True
            for p in pads:
                cx, cy = placed(p, rot, dx, dy)
                if not clear_rect(cx, cy, p["hw"], p["hh"], p["lset"], p["net"],
                                  route.CLEAR + 0.005):
                    ok = False; stat["pad"] += 1; break
                if not clear_rect(cx, cy, p["hw"], p["hh"], p["lset"], p["net"],
                                  MASK_GAP) and not mask_ok(cx, cy, p["net"]):
                    ok = False; stat["mask"] += 1; break
                for lay, e in p["ends"]:
                    if seg_clear(e, (cx, cy), lay, p["net"],
                                 route.TRACK_W/2 + route.CLEAR + 0.005):
                        continue
                    fl = flood_for((p["net"], lay), lay, p["net"],
                                   [q for l2, q in p["ends"] if l2 == lay])
                    if fl is None or fl[0].cell(cx, cy) not in fl[1]:
                        ok = False; stat["stitch"] += 1; break
                    rr_ = shove.straighten(shove.walk_back(
                        fl[0], fl[2], fl[0].cell(cx, cy)))[::-1]
                    rr_[-1] = (cx, cy)
                    if not run_ok(rr_, p["net"]):
                        ok = False; stat["mask"] += 1; break
                if not ok:
                    break
            if not ok:
                continue
            # The pad is grounded either by landing on the main pour - which needs no
            # via at all - or by taking one. Requiring a via was too strict: it ruled
            # out every offset within 1.5 mm while ignoring the simpler outcome.
            gx, gy = placed(gnd[0], rot, dx, dy)
            v = via_here(gx, gy, "GND")
            on_pour = any(ir.inside(poly, gx, gy) for poly in main_pour)
            reach = False
            if v is None and not on_pour:
                fl = flood_for(("GND", glay), glay, "GND", pour_seeds)
                reach = fl is not None and fl[0].cell(gx, gy) in fl[1]
                if reach:
                    rr_ = shove.straighten(shove.walk_back(
                        fl[0], fl[2], fl[0].cell(gx, gy)))[::-1]
                    rr_[-1] = (gx, gy)
                    if not run_ok(rr_, "GND"):
                        reach = False
            if v is None and not on_pour and not reach:
                stat["no_ground"] += 1
                continue
            if toward_pt is not None:
                # sort by how close the part's own pads get to the pin being decoupled,
                # not by how little the part moves
                near = min(math.hypot(placed(q, rot, dx, dy)[0] - toward_pt[0],
                                      placed(q, rot, dx, dy)[1] - toward_pt[1])
                           for q in pads)
                cands.append((0 if on_pour else 1, round(near, 4), dx, dy, v, rot))
            else:
                cands.append((0 if on_pour else 1, r, dx, dy, v, rot))
    print(f"    of {stat['total']} offsets: {stat['yard']} overlap a courtyard, "
          f"{stat['pad']} collide a pad, {stat['stitch']} a stitch, "
          f"{stat['mask']} bridge the solder mask, {stat['no_ground']} leave the "
          f"ground pad with nowhere to connect")
    # sort on the comparable fields only - the via tuple may be None
    cands.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
    if not cands:
        print(f"no offset within {maxr} mm puts {ref}'s ground pad on live copper")
        return 1
    onp = sum(1 for c in cands if c[0] == 0)
    label = "closest approach" if toward_pt is not None else "best"
    print(f"{len(cands)} workable placements ({onp} land straight on the main pour); "
          f"{label}: {cands[0][1]:.2f} mm ({cands[0][2]:+.2f},{cands[0][3]:+.2f})"
          + (f" turned {cands[0][5]} deg" if cands[0][5] else "")
          + (f", {cands[0][4][0]} mm via" if cands[0][4] else ", straight onto the pour"))
    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0

    tried = 0
    for _pref, r, dx, dy, v, rot in cands:
        runs = full_routes(rot, dx, dy)
        if runs is None:
            continue
        tried += 1
        if tried > 25:
            break
        shutil.copy(BOARD, BAK)
        bd = pcbnew.LoadBoard(BOARD)
        route.set_rules(bd)
        f2 = bd.FindFootprintByReference(ref)
        if rot:
            f2.SetOrientationDegrees(f2.GetOrientationDegrees() + rot)
        f2.Move(pcbnew.VECTOR2I(MM(dx), MM(dy)))
        for lay, netname, run in runs:
            nt = bd.FindNet(netname)
            for k in range(len(run) - 1):
                route.add_track(bd, run[k], run[k+1], lay, nt, width=route.TRACK_W)
        if v is not None:
            gp = placed(gnd[0], rot, dx, dy)
            vv = route.add_via(bd, gp[0], gp[1], bd.FindNet("GND"))
            vv.SetWidth(MM(v[0])); vv.SetDrill(MM(v[1]))
        route.fill(bd)
        bd.Save(BOARD)
        hard, un, txt = drc()
        if hard <= hard0 and un < un0:
            print(f"  moved {ref} by ({dx:+.2f},{dy:+.2f}) mm"
                  + (f", turned {rot} deg" if rot else "")
                  + (f", via {v[0]} mm in its ground pad" if v else
                     ", its ground pad now sits on the main pour")
                  + f" -> {un} unconnected, {hard} errors")
            return 0
        bad = [z for z in re.split(r'^\[', txt, flags=re.M)
               if z and not z.startswith("unconnected_items") and not z.startswith("** ")]
        print(f"  ({dx:+.2f},{dy:+.2f}) rot{rot} -> +{hard-hard0} err, {un} unconn"
              + (f": {bad[0].splitlines()[0]}" if bad else ""))
        shutil.copy(BAK, BOARD)
    print("no offset survived DRC")
    return 1


if __name__ == "__main__":
    sys.exit(main())
