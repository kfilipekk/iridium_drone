#!/usr/bin/env python3
"""
Thermal vias for the linear regulators, and a measurement of what they buy.

WHY THIS EXISTS. tools/check_thermal.py brackets U9 (AP2112K-3.3, SOT-23-5) at 132 C
continuous and 157 C peak against a 150 C junction limit - using the Diodes datasheet's
theta_JA of 184 C/W, which is explicitly the "No Heatsink" figure. That is the
MINIMAL-COPPER bound, not this board. A SOT-23-5 has no thermal pad, so every joule
leaves through the leads into whatever copper is attached to them, and the only lever
this design has is that copper.

WHAT IT DOES. For each thermal pad it searches for legal via positions, places a via and
a wide stub from the pad, and then MEASURES the result - via count and attached copper
area per pad - so the theta_JA bracket in check_thermal.py rests on a property of this
board rather than on an adjective.

WHAT IT DELIBERATELY DOES NOT DO. It does not claim a new theta_JA. Copper improves
theta_JA monotonically, so more vias cannot make it worse, but turning "12 vias and
44 mm2" into a number in C/W needs a thermocouple - docs/BUILD.md T3a. This tool moves
the bound and says by how much in copper; it does not convert copper into degrees.

Vias are placed OFFSET from the pad with a stub, never in-pad: an unfilled via inside a
pad wicks solder off the joint during reflow. Same reasoning as tools/via_in_pad.py.

    python3 tools/thermal_vias.py            # dry run, prints what it would place
    python3 tools/thermal_vias.py --apply    # writes the board
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design, route

BOARD = "NAVCORE-SoOP.kicad_pcb"

# Which pads carry heat out of which part. For a SOT-23-5 LDO that is every pin with a
# net: the die sits under the middle of the package and conducts to all of them. Pin 4
# is NC on the AP2112 and has no net, so it is not listed - a via there would connect to
# nothing and buy nothing.
# U10 is deliberately NOT here. It is the same package on the same rail pair, but it
# carries three MEMS sensors - 6 mA peak, 42 C junction with 83 C of margin. Adding vias
# to it would be churn on a board already at 67.5% courtyard, and churn on a dense board
# is not free: every via is an obstacle to the next reroute. Add it here if its load ever
# grows.
TARGETS = {
    "U9": ["2", "5", "1", "3"],     # GND, VOUT(+3V3), VIN(+5V), EN(+5V)
    # U8 is here for the MEASUREMENT, not to place anything, and only pin 1 is listed.
    # It is the part check_thermal.py brackets at 139 C, so its attached copper belongs on
    # the record next to U9's - without it the 139 C reads as a property of this board when
    # it is the JEDEC test board's. Pin 1 is GND and is the only safe copper here: pin 2 is
    # BUCK_PH, the switch node, and hanging copper on it adds parasitic capacitance to the
    # aggressor - worse EMI and more switching loss, for no thermal gain, because that pad
    # is not the die's heat path. Pins 4/5/6 (FB, EN, BOOT) carry no load current.
    # Measured 2026-09-19: 3 vias already within 1.7 mm, 7655.8 mm2 of GND plane attached,
    # and no legal position for another - so this places nothing and changes no copper.
    "U8": ["1"],
}

# A STUB IS COPPER TOO. The first version of this tool checked only the VIA position and
# placed a stub to it unchecked - and DRC immediately found a +5V stub crossing a +3V3
# track. That is this project's signature defect committed inside a new tool: it measured
# the property next to the one that mattered. check_stub() below is the fix, and the
# regression is that DRC must come back clean, not that the search finds more positions.
STUB_W      = 0.40   # mm. Wider than the 4 mil signal default: this stub is a heat path
                     # first and a conductor second, and 0.40 mm still clears easily.
MAX_R       = 1.70   # mm from pad centre. Beyond this the stub's own resistance and the
                     # spreading path stop paying for the space consumed.
MIN_EDGE    = 0.06   # mm of copper between pad edge and via edge - keeps the via OUT of
                     # the pad so it cannot wick solder, while staying tight enough to be
                     # a short thermal path.
PER_PAD_MAX = 3      # new vias per pad


def obstacles_on_layer(board, layer, exclude_net):
    """Obstacles that can actually conflict with copper on ONE layer.

    route.obstacle_shapes() is layer-blind - deliberately, because it was written for
    THROUGH vias, which occupy every layer and so must clear everything. A stub track
    does not: it lives on one layer, and an In2.Cu track cannot touch an F.Cu trace.
    Reusing the layer-blind list for the stub made the first honest run report "no legal
    position" for all four pads, blocked by inner-layer copper the stub cannot reach.
    That is the same over-blocking tools/island_via.py documents having been caught by.
    """
    lid = board.GetLayerID(layer)
    out = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == exclude_net or not pad.IsOnLayer(lid):
                continue
            bb = pad.GetBoundingBox()
            out.append(("rect", route.TOMM(bb.GetLeft()), route.TOMM(bb.GetTop()),
                        route.TOMM(bb.GetRight()), route.TOMM(bb.GetBottom())))
    for t in board.GetTracks():
        if t.GetNetname() == exclude_net:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            # a through via is on every layer
            p = t.GetPosition()
            out.append(("cap", route.TOMM(p.x), route.TOMM(p.y),
                        route.TOMM(p.x), route.TOMM(p.y), route.VIA_D / 2))
        elif t.GetLayer() == lid:
            a, c = t.GetStart(), t.GetEnd()
            out.append(("cap", route.TOMM(a.x), route.TOMM(a.y),
                        route.TOMM(c.x), route.TOMM(c.y), route.TOMM(t.GetWidth()) / 2))
    return out


def stub_ok(px, py, x, y, obs, half_w):
    """Is the pad->via stub itself clear of everything on its layer?

    Sampled rather than solved: at 0.04 mm steps against a 0.1016 mm rule, a sample can
    only miss an obstacle it is already clear of. Cheap, and it is checking the real
    path rather than its endpoints.
    """
    L = math.hypot(x - px, y - py)
    if L < 1e-9:
        return True
    steps = max(2, int(L / 0.04))
    for i in range(steps + 1):
        t = i / steps
        sx, sy = px + (x - px) * t, py + (y - py) * t
        for s in obs:
            if route.gap_to_shape(sx, sy, s) < half_w + route.VIA_CLEAR:
                return False
    return True


def pad_rect(pad):
    bb = pad.GetBoundingBox()
    return (route.TOMM(bb.GetLeft()), route.TOMM(bb.GetTop()),
            route.TOMM(bb.GetRight()), route.TOMM(bb.GetBottom()))


def copper_area_on_net(board, net, layers):
    """Filled zone area for `net`, in mm^2, over `layers`. Measured, not assumed."""
    total = 0.0
    for z in board.Zones():
        if z.GetNetname() != net:
            continue
        for lid in z.GetLayerSet().Seq():
            if board.GetLayerName(lid) not in layers:
                continue
            try:
                poly = z.GetFilledPolysList(lid)
            except Exception:
                continue
            if poly:
                total += route.TOMM(route.TOMM(poly.Area()))
    return total


def place(board, ref, pads_wanted, apply_it, log):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        log.append(f"  {ref}: not on the board")
        return 0
    holes = route.hole_shapes(board)
    placed_total = 0
    for pn in pads_wanted:
        pad = next((p for p in fp.Pads() if p.GetNumber() == pn), None)
        if pad is None:
            continue
        net = pad.GetNetname()
        if not net:
            log.append(f"  {ref}.{pn}: no net (NC pin) - skipped")
            continue
        px, py = route.TOMM(pad.GetPosition().x), route.TOMM(pad.GetPosition().y)
        x0, y0, x1, y1 = pad_rect(pad)
        # Obstacles EXCLUDING this net: same-net copper is not an obstacle to a via that
        # joins it. That correction is why tools/island_via.py found room where every
        # earlier attempt had concluded there was none.
        obs = route.obstacle_shapes(board, exclude_net=net)      # vias: every layer
        sobs = obstacles_on_layer(board, "F.Cu", net)            # stubs: F.Cu only
        vr = route.VIA_D / 2.0

        before = sum(1 for t in board.GetTracks()
                     if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == net
                     and math.hypot(route.TOMM(t.GetPosition().x) - px,
                                    route.TOMM(t.GetPosition().y) - py) <= MAX_R)

        cands = []
        r = 0.30
        while r <= MAX_R:
            steps = max(12, int(2 * math.pi * r / 0.10))
            for i in range(steps):
                a = 2 * math.pi * i / steps
                x, y = px + r * math.cos(a), py + r * math.sin(a)
                # must sit OUTSIDE the pad, by MIN_EDGE of copper
                if route.gap_to_rect(x, y, (x0, y0, x1, y1)) < vr + MIN_EDGE:
                    continue
                if not route.inside_board(x, y, 0.5):
                    continue
                if not route.hole_ok(x, y, holes):
                    continue
                if any(route.gap_to_shape(x, y, s) < vr + route.VIA_CLEAR for s in obs):
                    continue
                cands.append((r, x, y))
            r += 0.05

        chosen = []
        for _, x, y in sorted(cands, key=lambda c: c[0]):
            if len(chosen) >= PER_PAD_MAX:
                break
            # spread them out; two vias 0.1 mm apart share the same thermal path
            if any(math.hypot(x - cx, y - cy) < route.VIA_D + route.HOLE_CLEAR
                   for cx, cy in chosen):
                continue
            # and the stub that will connect it must fit too
            if not stub_ok(px, py, x, y, sobs, STUB_W / 2.0):
                continue
            chosen.append((x, y))

        for x, y in chosen:
            if apply_it:
                route.add_via(board, x, y, pad.GetNet())
                route.add_track(board, (px, py), (x, y), "F.Cu", pad.GetNet(),
                                width=STUB_W)
            # a placed via AND ITS STUB are obstacles to the next one
            obs.append(("cap", x, y, x, y, vr))
            sobs.append(("cap", x, y, x, y, vr))
            sobs.append(("cap", px, py, x, y, STUB_W / 2.0))
            holes.append((x, y, route.VIA_D / 2.0))
        placed_total += len(chosen)
        log.append(f"  {ref}.{pn} ({net:5}) had {before} via(s) within {MAX_R} mm, "
                   f"{'placed' if apply_it else 'would place'} {len(chosen)} more"
                   + (f" at {', '.join(f'({x:.2f},{y:.2f})' for x, y in chosen)}"
                      if chosen else " - no legal position"))
    return placed_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    board = pcbnew.LoadBoard(BOARD)

    print(__doc__.split("WHAT IT DOES")[0].strip()[:0] or "", end="")
    print("=== thermal vias ===")
    log = []
    n = 0
    for ref, pads in TARGETS.items():
        n += place(board, ref, pads, a.apply, log)
    print("\n".join(log))

    if a.apply and n:
        route.fill(board)
        board.Save(BOARD)
        print(f"\nplaced {n} via(s) and saved {BOARD}")
    elif a.apply:
        print("\nnothing to place; board not written")
    else:
        print(f"\n{n} via(s) would be placed - rerun with --apply")

    # ---- MEASURE what each thermal pad is actually attached to -------------------
    print("\n=== copper attached to each thermal pad (MEASURED from the board) ===")
    GND_L = ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "B.Cu")
    PWR_L = ("In4.Cu",)
    for ref, pads in TARGETS.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        for pn in pads:
            pad = next((p for p in fp.Pads() if p.GetNumber() == pn), None)
            if pad is None or not pad.GetNetname():
                continue
            net = pad.GetNetname()
            px, py = route.TOMM(pad.GetPosition().x), route.TOMM(pad.GetPosition().y)
            vias = [t for t in board.GetTracks()
                    if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == net
                    and math.hypot(route.TOMM(t.GetPosition().x) - px,
                                   route.TOMM(t.GetPosition().y) - py) <= MAX_R]
            area = copper_area_on_net(board, net, GND_L if net == "GND" else PWR_L)
            print(f"  {ref}.{pn} ({net:5}) {len(vias)} via(s) within {MAX_R} mm -> "
                  f"{area:8.1f} mm2 of {net} plane")
    print("\nMore copper cannot make theta_JA worse, so this moves the bound in the safe")
    print("direction. It does NOT license a number: docs/BUILD.md T3a measures it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
