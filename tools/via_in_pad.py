#!/usr/bin/env python3
"""
Place a via inside a pad, for connections where that is the only thing missing.

Five of the last twelve items list `pad X [same net] (0.00 mm)` as the nearest thing to
where a via needs to go. That is not an obstruction - the pad belongs to the net being
routed. A trace on an inner layer ends directly above its own pad and nothing takes it
down. One via joins them.

Assembly caveat, deliberately not hidden: an unfilled via inside a pad wicks solder off
the joint during reflow or hand soldering. Under an LGA part - U2/U3 (ICM-42688-P /
ICM-42605), U7 (VL53L1X), U6 (PMW3901) - that risks a dry joint on a part you cannot
inspect. JLCPCB will fill and cap vias for an extra charge, which fixes it.

So OFFSET is tried first: a via just outside the pad, joined to it by a short stub. Only
if nothing fits there does it go in the pad itself, and the summary says which parts
ended up with one so the decision is visible rather than buried.

One item per process - looping LoadBoard segfaults after a rollback.

Usage:  python3 tools/via_in_pad.py [--apply] [--one N] [--allow-in-pad]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/vip_backup.kicad_pcb"
RPT   = "/tmp/nav/vip.rpt"
TIERS = [(0.60, 0.30), (0.50, 0.25), (0.45, 0.20)]
# Parts where a bare via-in-pad is a real assembly risk rather than a nuisance.
NO_BARE_VIA = {"U2", "U3", "U4", "U6", "U7", "U5", "U1", "U11", "U12", "U17"}


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def targets(text):
    """(net, ref, padnum) for unconnected items naming a pad of a plane/power net."""
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        for m in re.finditer(r'Pad (\S+) \[([^\]]+)\] of (\w+)', blk[:400]):
            out.append((m.group(2), m.group(3), m.group(1)))
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq


def main():
    apply = "--apply" in sys.argv
    allow_in_pad = "--allow-in-pad" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, text = drc()
    todo = targets(text)
    if "--one" in sys.argv:
        i = int(sys.argv[sys.argv.index("--one") + 1])
        todo = todo[i:i+1]
    else:
        print(f"baseline {hard0} errors, {un0} unconnected; {len(todo)} pads named\n")

    for net, ref, padnum in todo:
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        n = board.FindNet(net)
        fp = board.FindFootprintByReference(ref)
        pad = next((q for q in fp.Pads() if q.GetNumber() == padnum), None) if fp else None
        if pad is None or n is None:
            print(f"  {ref}.{padnum}: not found")
            continue

        p = pad.GetPosition()
        px, py = route.TOMM(p.x), route.TOMM(p.y)
        bb = pad.GetBoundingBox()
        pw = route.TOMM(bb.GetRight() - bb.GetLeft())
        ph = route.TOMM(bb.GetBottom() - bb.GetTop())
        foreign = route.obstacle_shapes(board, exclude_net=net)
        holes = route.hole_shapes(board)
        kos = route.keepout_boxes(board)

        def fits(vx, vy, via_d, drill):
            need = via_d / 2 + route.VIA_CLEAR
            if not route.inside_board(vx, vy, via_d/2 + 0.35):
                return False
            if any(x1 - via_d/2 < vx < x2 + via_d/2 and y1 - via_d/2 < vy < y2 + via_d/2
                   for x1, y1, x2, y2 in kos):
                return False
            if not route.hole_ok(vx, vy, holes, drill):
                return False
            return not any(route.gap_to_shape(vx, vy, r) < need for r in foreign)

        # Collect EVERY legal position, nearest first, rather than taking the first
        # geometric fit. A via can clear the obstacle model and still cost DRC errors
        # once the pours refill around it - U1.49's first candidate closed the
        # connection but added four. With a list, the caller can try the next one.
        cands = []
        base = math.hypot(pw, ph) / 2
        for via_d, drill in TIERS:
            rad = base + via_d/2 + route.VIA_CLEAR + 0.05
            while rad <= base + 1.8:
                for k in range(48):
                    a = k * math.pi / 24
                    vx, vy = px + rad*math.cos(a), py + rad*math.sin(a)
                    if fits(vx, vy, via_d, drill):
                        cands.append((rad, vx, vy, via_d, drill, False))
                rad += 0.05
        if allow_in_pad or ref not in NO_BARE_VIA:
            for via_d, drill in TIERS:
                if via_d + 2*route.VIA_CLEAR > min(pw, ph) + 0.2:
                    continue
                if fits(px, py, via_d, drill):
                    cands.append((0.0, px, py, via_d, drill, True))
        cands.sort(key=lambda c: c[0])
        spot = (cands[0][1], cands[0][2], cands[0][3], cands[0][4]) if cands else None
        in_pad = cands[0][5] if cands else False

        if not spot:
            note = "" if (allow_in_pad or ref not in NO_BARE_VIA) else \
                   f" (in-pad refused: {ref} is a part where that risks a dry joint)"
            print(f"  {ref}.{padnum:<4} {net:7} no via fits{note}")
            continue
        if not apply:
            print(f"  {ref}.{padnum:<4} {net:7} would via {spot[2]:.2f} mm "
                  + ("IN PAD" if in_pad else f"at ({spot[0]:.2f},{spot[1]:.2f})"))
            continue

        done = False
        for attempt, (_, vx, vy, via_d, drill, ip) in enumerate(cands[:40], 1):
            shutil.copy(BOARD, BAK)
            board = pcbnew.LoadBoard(BOARD)
            route.set_rules(board)
            n2 = board.FindNet(net)
            v = route.add_via(board, vx, vy, n2)
            v.SetWidth(pcbnew.FromMM(via_d)); v.SetDrill(pcbnew.FromMM(drill))
            if not ip:
                fp2 = board.FindFootprintByReference(ref)
                pad2 = next(q for q in fp2.Pads() if q.GetNumber() == padnum)
                lay = "F.Cu" if pad2.IsOnLayer(board.GetLayerID("F.Cu")) else "B.Cu"
                route.add_track(board, (px, py), (vx, vy), lay, n2, width=route.TRACK_W)
            route.fill(board)
            board.Save(BOARD)
            hard, un, _ = drc()
            if hard <= hard0 and un <= un0:
                print(f"  {ref}.{padnum:<4} {net:7} via {via_d:.2f} mm "
                      + ("IN PAD" if ip else "offset")
                      + f" (attempt {attempt}) -> {un} unconnected")
                done = True
                break
            shutil.copy(BAK, BOARD)
        if not done:
            print(f"  {ref}.{padnum:<4} {net:7} {len(cands)} positions tried, "
                  f"all cost DRC errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
