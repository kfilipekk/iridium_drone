#!/usr/bin/env python3
"""Join an orphaned ground island to the main ground pour with a straight track.

WHY THIS EXISTS, AND HOW IT DIFFERS FROM bridge_orphans.py
----------------------------------------------------------
bridge_orphans.py answers the same question with a grid BFS, and on the last two
islands on this board it answers "no path on B.Cu" - twice. That answer is wrong.
Measured by hand, a candidate at y=114.60 running west out of the U13.3 island has
1.085 mm of clearance against a 0.1524 mm rule; the island is 1.09 mm2 and the pour
it belongs to is 15 mm away at most. A search that certifies CELLS first and then
draws segments between them inherits two failure modes at once: cells inside the
island are blocked because the island's own edge is only 0.1016 mm from whatever cut
the pour, so the start set is thin, and the 0.05 mm safety margin on top of the rule
is bigger than the slack any grid cell has.

This asks it the other way round and never rasterises:

    for every point on the island's own boundary, and every direction in a 2 degree
    fan, march the ray outward until it lands on pour copper that is not the island,
    then measure the whole segment against foreign copper at 0.02 mm resolution.

A straight segment between two points that are both copper of the same net has no
pocket to stay inside, so there is nothing to mis-model. Every candidate is checked
against a rule with a small bias on top and the best by clearance wins; the board is
then refilled and DRC'd, and anything that does not reduce the count of unconnected
items without adding an error is rolled back.

Usage:  python3 tools/bridge_visible.py [--apply] [--net GND]
"""
import os, sys, math, re, shutil, subprocess, json, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove, island_route as ir

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK = "/tmp/nav/bridge_visible_backup.kicad_pcb"
RPT = "/tmp/nav/bridge_visible.rpt"
FROM = lambda v: v / 1e6
NEED = route.TRACK_W / 2 + route.CLEAR
BIAS = 0.005          # accept only paths with a little more than the design rule
EDGE_STEP = 0.04      # boundary densification, mm
MARCH = 0.05          # ray step, mm
MAXLEN = 2.5          # a longer crossing than this is a re-route, not a bridge
ANGLE_STEP = 3
PER_POINT = 3         # shortest distinct rays kept per boundary point


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                    "--units", "mm", "-o", RPT, BOARD], capture_output=True, timeout=900)
    d = json.load(open(RPT))
    hard = sum(1 for v in d.get("violations", []) if v.get("severity") == "error")
    return hard, len(d.get("unconnected_items", []))


def as_poly(pts):
    poly = pcbnew.SHAPE_POLY_SET()
    ch = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in pts:
        ch.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    ch.SetClosed(True)
    poly.AddOutline(ch)
    return poly


def densify(poly, step=EDGE_STEP):
    out = []
    for oi in range(poly.OutlineCount()):
        o = poly.Outline(oi)
        n = o.PointCount()
        for k in range(n):
            a = o.CPoint(k)
            b = o.CPoint((k + 1) % n)
            L = math.hypot(b.x - a.x, b.y - a.y) / 1e6
            m = max(1, int(L / step))
            for s in range(m):
                t = s / m
                out.append((FROM(a.x + t * (b.x - a.x)), FROM(a.y + t * (b.y - a.y))))
    return out


def clear_along(obs, p0, p1):
    """Worst distance from the centreline to foreign copper, sampled at 0.02 mm."""
    n = max(2, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / 0.02))
    worst, wat = 1e18, None
    for s in range(n + 1):
        t = s / n
        x = p0[0] + t * (p1[0] - p0[0])
        y = p0[1] + t * (p1[1] - p0[1])
        for sh in obs:
            d = route.gap_to_shape(x, y, sh.geom)
            if d < worst:
                worst, wat = d, (x, y)
    return worst, wat


def net_code_in_file(path, name):
    """The net code the FILE's own net table gives this net name.

    Read from the text rather than from pcbnew on purpose - see insert_segment.
    """
    m = re.search(r'^\t\(net (\d+) "%s"\)$' % re.escape(name),
                  open(path).read(), re.M)
    return int(m.group(1)) if m else None


def insert_segment(path, p0, p1, code, layer="B.Cu", width=route.TRACK_W):
    """Add one track by editing the board file's text, not through pcbnew.

    THIS IS NOT LAZINESS. In this KiCad build, a track that this process creates OR
    EVEN JUST TOUCHES is written back with the WRONG NET. Measured on 2026-09-12,
    every route round trips through pcbnew.Save() as follows:

        net GND  (code 1) placed at (138.02, 113.29)  ->  saved as (net 96) = RFIN
        net +5V  (code 4) placed at (125.65, 113.09)  ->  saved as (net 5)  = +3V3
        net GND, never assigned at all                ->  saved as (net 96)
        an EXISTING GND track with its endpoints moved ->  saved as (net 96)
        a Duplicate() of an existing GND track         ->  saved as (net 96)
        the same with board.FindNet(), with GetNetsByNetcode(), with SetNetCode(),
        with SynchronizeNetsAndNetClasses(True) first, and with pcbnew.SaveBoard()

    board.FindNet("GND") is not even the same NETINFO_ITEM the existing tracks hold
    (`track.GetNet() is board.FindNet("GND")` is False), so the written code is not the
    one that was set. Existing tracks loaded from the file keep their nets, which is why
    this never showed up before: it only bites tracks this kind of tool ADDS, and every
    tool here adds tracks. It bit this one twice - the first GND bridge was written as
    RFIN and DRC reported a 0.35 mm RFIN stub 0.0000 mm from the GND pour.

    The board file is a text file and the net code is one number in it, so the bridge is
    written where it is known to be correct and then read back and checked.
    """
    txt = open(path).read()
    blk = (f"\t(segment\n\t\t(start {p0[0]:.6f} {p0[1]:.6f})\n"
           f"\t\t(end {p1[0]:.6f} {p1[1]:.6f})\n"
           f"\t\t(width {width})\n\t\t(layer \"{layer}\")\n"
           f"\t\t(net {code})\n\t\t(uuid \"{uuid.uuid4()}\")\n\t)\n")
    m = re.search(r"^\t\(segment\n", txt, re.M)
    if not m:
        return None
    return txt[:m.start()] + blk + txt[m.start():]


def main():
    apply_ = "--apply" in sys.argv
    net = sys.argv[sys.argv.index("--net") + 1] if "--net" in sys.argv else "GND"

    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    B = pcbnew.B_Cu
    zones = [z for z in b.Zones()
             if not z.GetIsRuleArea() and z.GetNetname() == net
             and B in z.GetLayerSet().CuStack()]
    if not zones:
        print(f"{net}: no zone on B.Cu")
        return 1
    pour = zones[0].GetFilledPolysList(B)
    allsh = shove.shapes_of(b, exclude_net=net)
    # shove.Shape.lset holds layer NAMES (COPPER = ("F.Cu", "In1.Cu", ...)), not
    # PCB_LAYER_IDs. Filtering with `pcbnew.B_Cu in s.lset` therefore matched nothing
    # but the vias, and this tool spent its first runs certifying bridges against a
    # board that had no tracks on it: the U13.3 bridge it called 0.196 mm clear passes
    # 0.010 mm from the RFIN trace at (138.173,113.262) - which is why KiCad re-netted
    # that segment to RFIN and the island stayed isolated. Everything it reported about
    # clearance before this line was wrong.
    obs = [s for s in allsh if s.kind == "via" or "B.Cu" in s.lset]
    isls = ir.orphans(b, ir.gnd_polys(b))
    print(f"{net}: {len(zones)} B.Cu zone(s), {len(obs)} obstacle(s), "
          f"{len(isls)} orphan island(s)")
    if not isls:
        print("nothing orphaned on B.Cu")
        return 0

    jobs = []
    for lname, _pi, isl, area in isls:
        poly = as_poly(isl)
        pts = densify(poly)
        # EVERY boundary point gets a turn. An earlier version stopped after 360
        # candidates and, because one vertex contributed a fan of 180 of them, the
        # search never reached the boundary point 0.2 mm away whose ray is the actual
        # bridge - it reported "none provable" on an island with a 0.35 mm crossing at
        # 0.164 mm of clearance. So per point keep only its few shortest different
        # rays: a bridge wants to be short anyway, and the point that matters gets
        # evaluated instead of being crowded out.
        cands = []
        for (px, py) in pts:
            hits = []
            for ang in range(0, 360, ANGLE_STEP):
                th = math.radians(ang)
                dx, dy = math.cos(th), math.sin(th)
                t, hit = 0.10, None
                while t <= MAXLEN:
                    qx, qy = px + t * dx, py + t * dy
                    t += MARCH
                    pv = pcbnew.VECTOR2I(pcbnew.FromMM(qx), pcbnew.FromMM(qy))
                    if not pour.Collide(pv, 0) or ir.inside(isl, qx, qy):
                        continue
                    hit = (qx, qy)
                    break
                if hit is None:
                    continue
                L = math.hypot(hit[0] - px, hit[1] - py)
                # A bridge shorter than the clearance it needs cannot be a real one.
                if L < NEED * 2:
                    continue
                hits.append((L, hit))
            hits.sort()
            seen = set()
            for L, hit in hits:
                key = (round(hit[0], 1), round(hit[1], 1))
                if key in seen:
                    continue
                seen.add(key)
                cands.append((L, (px, py), hit))
                if len(seen) >= PER_POINT:
                    break
        # Shortest bridge with real margin wins, so score the candidates SHORTEST
        # FIRST and stop at the first that has it. A hair over the rule is not a
        # margin: the filler rounds, DRC measures drawn copper, and this board has
        # already produced one bridge that measured 0.202 in the search and 0.0229 in
        # DRC. 0.03 mm of headroom is asked for first; without it, the plain rule.
        # Scoring every candidate instead of stopping early is what made this take
        # longer than a dry run is allowed to.
        cands.sort(key=lambda c: c[0])
        head = f"  {lname} island {area:.2f} mm2: {len(pts)} points, {len(cands)} ray(s)"
        pick, scanned = None, 0
        for want in (NEED + 0.030, NEED + BIAS):
            for L, p0, p1 in cands:
                scanned += 1
                if scanned > 900:
                    break
                w, _at = clear_along(obs, p0, p1)
                if w >= want:
                    pick = (w, L, p0, p1)
                    break
            if pick:
                break
        if not pick:
            print(f"{head}, none provable")
            continue
        w, L, p0, p1 = pick
        good = w >= NEED + 0.030
        print(f"{head}, bridge {L:.3f} mm  ({p0[0]:.3f},{p0[1]:.3f}) -> "
              f"({p1[0]:.3f},{p1[1]:.3f})  clearance {w:.3f} (rule {NEED:.4f})"
              + ("" if good else "  [NO MARGIN]") + f"  [{scanned} scanned]")
        jobs.append((lname, (p0, p1), w))

    if not jobs:
        print("\nnothing provable - board untouched")
        return 0
    if not apply_:
        print(f"\n{len(jobs)} bridge(s) ready - dry run, pass --apply")
        return 0

    code = net_code_in_file(BOARD, net)
    if code is None:
        print(f"{net}: not in the board file's net table")
        return 1
    hard0, un0 = drc()
    print(f"\nbaseline {hard0} errors, {un0} unconnected; {net} is net {code} in the file")
    # No refill. A track does not need one: it is its own copper and it overlaps pour
    # copper at both ends, so connectivity is geometric. route.fill() on this board
    # re-pours every zone and took +3V3 from 1 to 4 unconnected items when it was tried
    # here, which is the same regression tools/repour_power.py exists to undo.
    for lname, (p0, p1), w in jobs:
        shutil.copy(BOARD, BAK)
        d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        ux, uy = (p1[0] - p0[0]) / d, (p1[1] - p0[1]) / d
        # Bury both ends a little: p0 sits exactly ON the island's boundary vertex the
        # ray started from, and p1 lands on the first cell of pour copper it reached.
        # 0.08 mm inward at each end is inside copper that is already the same net.
        a = (p0[0] - 0.08 * ux, p0[1] - 0.08 * uy)
        c = (p1[0] + 0.08 * ux, p1[1] + 0.08 * uy)
        out = insert_segment(BOARD, a, c, code)
        if out is None:
            print(f"  {lname}: no (segment) block found to anchor to - skipped")
            continue
        open(BOARD, "w").write(out)
        hard, un = drc()
        back = [t for t in pcbnew.LoadBoard(BOARD).GetTracks()
                if t.Type() != pcbnew.PCB_VIA_T
                and abs(t.GetStart().x / 1e6 - a[0]) < 0.002
                and abs(t.GetStart().y / 1e6 - a[1]) < 0.002]
        got = back[0].GetNetname() if back else "MISSING"
        if got != net or hard > hard0 or un >= un0:
            shutil.copy(BAK, BOARD)
            print(f"  {lname} {w:.3f}mm: rolled back (net read back as {got!r}, "
                  f"{hard} errors, {un} unconnected)")
        else:
            hard0, un0 = hard, un
            print(f"  {lname} {w:.3f}mm: bridged as {got} -> {hard} errors, {un} unconnected")
    print(f"\n{hard0} errors, {un0} unconnected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
