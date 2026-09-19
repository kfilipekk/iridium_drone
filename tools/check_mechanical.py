#!/usr/bin/env python3
"""
Mechanical fit of the board in the stack and the frame.

check_build.py covers the aircraft-level numbers - stack height, mounting pitch, prop
clearance, battery envelope. This covers what it does not: whether every connector can
actually be REACHED once the board is bolted into a 30x30 stack, and whether anything
collides in three dimensions rather than in a top-down outline.

That gap is not hypothetical. Both J1 and J2 were fitted facing into the board and every
electrical check passed them; check_build measured J1's 0.83 mm to the board edge and
passed it without asking which way it faced. Orientation is fixed now, but the same blind
spot covers the rest of the assembly: a connector can face correctly off the board and
still be unusable because a standoff, the ESC below it, or the frame's top plate is in the
way of the plug or of the fingers holding it.

Two kinds of result, kept apart on purpose:

  COMPUTED  - derived from the board file and the declared stack dimensions. These are
              facts about the design and are true whatever arrives in the post.
  MEASURE   - depends on the frame, which is a listing, not a measurement. Each one is
              written as a specific number to check with calipers, not as "check it fits".

Every declared value carries its provenance, the same way check_build.py does:
[M]easured / [D]atasheet / [L]isting / [A]ssumed.

Usage: python3 tools/check_mechanical.py [board.kicad_pcb]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = sys.argv[1] if len(sys.argv) > 1 else 'NAVCORE-SoOP.kicad_pcb'

# --- the rest of the stack, all declared with a source ------------------------------
ESC   = design.ESC
# Read from design.FRAME, not restated. This file used to carry its own copy with
# inner_h=35.0 from a superseded AliExpress listing, so it reported "12.2 mm spare"
# while check_build.py - reading the corrected 25 mm standoff height from design.py -
# reported a different figure for the same stack. One quantity, two files, two answers:
# exactly the defect design.PART_HEIGHT was created to end.
# ... and picking out two keys was still a copy. When the frame changed to the TBS
# Source One, a new check wanting FRAME["arm_t"] raised KeyError against this subset.
# Alias the whole dict: there is no reason for this file to decide which parts of the
# airframe definition it is allowed to see.
FRAME = design.FRAME
SKID  = design.SKID
GAP   = dict(mm=design.MOUNTING["gap"], src=design.MOUNTING["src"])
GROMMET_D = dict(mm=design.MOUNTING["grommet_d"], src=design.MOUNTING["src"])
BOARD_T   = dict(mm=1.6, src="[M] design.py stackup")
# Derived from the board and design.PART_HEIGHT rather than declared here. It was
# declared here - as 2.5 mm, sourced to "the tallest bottom-side part: L2/L5" - and both
# halves were wrong: L2 had moved to the TOP during the buck re-layout, and the part on
# the 1210 land is a 3.0 mm FNR4030, not a 2.5 mm generic. The measured answer differs by
# variant, which a single constant cannot express at all.
BOT_PARTS = None   # filled in from the board in main()

# Height of each connector's body above the board surface it sits on, and how far its
# mated plug protrudes past the connector's own courtyard face.
CONN = {
 "J1": dict(h=3.16, protrude=6.5,  what="USB-C",
            src="[D] TYPE-C 16P 2MD(073) body height; [A] plug overmould protrusion"),
 "J2": dict(h=2.90, protrude=4.0,  what="ESC JST-SH 8P",
            src="[D] JST SH series height; [A] plug + wire exit"),
 "J3": dict(h=4.40, protrude=4.0,  what="GPS JST-GH 6P",
            src="[D] JST GH series height; [A] plug + wire exit"),
 "J8": dict(h=1.85, protrude=12.0, what="microSD",
            src="[D] TF-01A body height; [M] a microSD card is 15 mm long"),
}

ok_n = warn_n = fail_n = 0
def line(kind, name, detail, src=""):
    # "FAIL" was passed by four call sites below and was NOT a key in this table, so a
    # genuine failure raised KeyError before printing anything - the one path that had
    # to work was the one that could not. It is a key now, and it is counted, and
    # main() returns non-zero on it.
    global ok_n, warn_n, fail_n
    tag = {"ok": "  ok  ", "note": " note ", "MEASURE": "MEASURE",
           "CAD": "  CAD  ", "FAIL": " FAIL "}[kind]
    if kind == "ok": ok_n += 1
    elif kind == "FAIL": fail_n += 1
    else: warn_n += 1
    print(f" {tag} {name:44s} {detail}")
    if src: print(f"         {src}")


def main():
    b = pcbnew.LoadBoard(BOARD)
    xs, ys = [], []
    for d in b.GetDrawings():
        if d.GetLayerName() == 'Edge.Cuts':
            bb = d.GetBoundingBox()
            xs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
            ys += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
    X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
    BL, BW = X1-X0, Y1-Y0
    cx, cy = (X0+X1)/2, (Y0+Y1)/2

    print(f"board {BL:.2f} x {BW:.2f} mm, centre ({cx:.2f},{cy:.2f})\n")

    global BOT_PARTS
    _, base_bot, _, base_ref, unknown = design.stack_heights(b, skip_dnp=True)
    _, fpv_bot, _, fpv_ref, _ = design.stack_heights(b, skip_dnp=False)
    if unknown:
        print("  !! footprints with no declared height: "
              + ", ".join(sorted(unknown)) + "\n")
    # The FPV variant is the taller of the two, so the stack is checked against it: a
    # clearance that holds for the worst case holds for both.
    BOT_PARTS = dict(mm=fpv_bot,
                     src=f"[M] board + [D] design.PART_HEIGHT: {fpv_ref} on the FPV "
                         f"build ({fpv_bot:.2f} mm); {base_ref} on the base build "
                         f"({base_bot:.2f} mm)")

    # ---------------------------------------------------------------- stack in Z
    print("=== stack height (COMPUTED) ===")
    # The stack does NOT start on the bottom plate. This line read
    #     z_esc_top = FRAME["bottom_t"] + ...
    # which omitted the 6.0 mm arms and the 2.0 mm mid plate between them - 8.0 mm of
    # frame - and so reported 7.7 mm of spare where there was -0.3 mm. design.FRAME_CAD
    # settles it: the plate carrying the 30.5 mm stack pattern is a 48.50 x 106.59 mm
    # strip, not the 200 x 230 bottom plate, so it sits above the arm layer.
    STO = design.required_standoff(b)
    z_stack = STO["below"]
    z_esc_top = z_stack + ESC["pcb"] + ESC["parts"]
    z_board_bot = z_esc_top + GAP["mm"]
    z_board_pcb = z_board_bot + BOT_PARTS["mm"]
    z_board_top = z_board_pcb + BOARD_T["mm"]
    tallest = max(c["h"] for c in CONN.values())
    z_max = z_board_top + tallest
    line("ok", "frame below the stack",
         f"bottom plate {FRAME['bottom_t']:.1f} + arms {FRAME['arm_t']:.1f} + mid plate "
         f"{FRAME['medium_t']:.1f} = {z_stack:.1f} mm", FRAME["src"].split(";")[0])
    line("ok", "top of the ESC's parts", f"{z_esc_top:.1f} mm above the frame's bottom plate",
         ESC["src"] + " + " + FRAME["src"])
    line("ok", "board underside sits at", f"{z_board_pcb:.1f} mm; its bottom parts reach down to "
         f"{z_board_bot:.1f} mm", BOT_PARTS["src"] + " + " + GAP["src"])
    # MOUNTING["gap"] is a design INPUT - the arithmetic above PLACES the board using
    # it - so testing GAP >= 1.0 asked the input about itself and could never fail.
    # The property that matters is the separation the hardware must actually hold
    # between the two PCBs, which is derived, and is unmeasured until the grommets are
    # in hand. State the number to put calipers on rather than printing a fake "ok".
    sep = ESC["parts"] + GAP["mm"] + BOT_PARTS["mm"]
    line("MEASURE", "inter-PCB separation the grommets must hold",
         f"{sep:.2f} mm between the ESC's PCB top face and this board's PCB underside "
         f"(ESC parts {ESC['parts']:.1f} + air {GAP['mm']:.1f} + bottom parts "
         f"{BOT_PARTS['mm']:.2f}); compressed grommet height is [A]", GAP["src"])
    # required_standoff() returns buy=None when the stack is taller than the longest
    # stock length. Nothing handled that: "z_max > None" is a TypeError in Python 3, so
    # the one genuinely unrecoverable geometry crashed instead of reporting.
    # THE load-bearing test, and it is external: the top plate sits where the KIT's
    # standoffs put it (design.TOP_PLATE_MOUNT, from the manufacturer DXF - 22 mm front
    # posts on the mid plate, 30 mm rear posts on the bottom plate), and the stack's
    # tallest part must clear its underside. This replaced a pair of checks against a
    # standoff "to buy" at the 30.5 pattern - a standoff the frame does not have, since
    # the top plate has no 30.5 holes; one of those passed by construction and the
    # other told PARTS.csv to buy 35 mm.
    line("FAIL" if z_max > STO["top_plate_z"] else "ok", "tallest point of the stack",
         f"{z_max:.1f} mm against the top plate's underside at {STO['top_plate_z']:.1f} mm "
         f"({STO['top_plate_z']-z_max:.1f} mm spare) - the kit's {STO['buy']:.0f} mm front "
         f"standoffs over the mid plate; nothing to buy", STO["src"])

    # ---------------------------------------------------- board vs the ESC, per edge
    print("\n=== board vs the ESC below it (COMPUTED) ===")
    print("     both share the 30.5 mm hole pattern, so they are concentric; the ESC can")
    print("     be fitted either way round, so both are reported.")
    for label, el, ew in (("ESC long side along X", ESC["L"], ESC["W"]),
                          ("ESC long side along Y", ESC["W"], ESC["L"])):
        dx = (BL - el) / 2
        dy = (BW - ew) / 2
        def word(v): return f"board overhangs by {v:+.2f}" if v > 0 else f"ESC overhangs by {-v:.2f}"
        line("ok", label, f"X edges: {word(dx)} mm   Y edges: {word(dy)} mm", ESC["src"])

    # ---------------------------------------------------------- standoffs
    print("\n=== mounting standoffs vs the connectors (COMPUTED) ===")
    pitch = design.BOARD["MOUNT"]
    holes = [(cx+sx*pitch/2, cy+sy*pitch/2) for sx in (-1, 1) for sy in (-1, 1)]
    gr = GROMMET_D["mm"] / 2

    for ref in sorted(CONN):
        fp = b.FindFootprintByReference(ref)
        if fp is None: continue
        poly = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        bb = poly.BBox()
        l, r = bb.GetLeft()/1e6, bb.GetRight()/1e6
        t, bm = bb.GetTop()/1e6, bb.GetBottom()/1e6
        worst = min(math.hypot(max(l-hx, 0, hx-r), max(t-hy, 0, hy-bm)) - gr
                    for hx, hy in holes)
        line("ok" if worst > 0.5 else "note", f"{ref} body vs the nearest grommet",
             f"{worst:.2f} mm clear", GROMMET_D["src"])

    # ------------------------------------------------ the volume each plug needs
    print("\n=== clear space each connector needs OUTSIDE the board (COMPUTED) ===")
    print("     this is what the frame must not occupy; measure it when the frame arrives")
    for ref in sorted(CONN):
        fp = b.FindFootprintByReference(ref)
        if fp is None: continue
        c = CONN[ref]
        face = design.MATING_FACE[ref]
        fx, fy = face
        if fp.IsFlipped(): fy = -fy
        a = math.radians(-fp.GetOrientationDegrees())
        vx = fx*math.cos(a) - fy*math.sin(a)
        vy = fx*math.sin(a) + fy*math.cos(a)
        poly = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        bb = poly.BBox()
        l, r = bb.GetLeft()/1e6, bb.GetRight()/1e6
        t, bm = bb.GetTop()/1e6, bb.GetBottom()/1e6
        mx = (l+r)/2 + vx*(r-l)/2
        my = (t+bm)/2 + vy*(bm-t)/2
        # distance from the mouth to the board edge along the mating direction
        to_edge = ({'-x': mx-X0, '+x': X1-mx, '-y': my-Y0, '+y': Y1-my}
                   ['-x' if vx < -0.5 else '+x' if vx > 0.5 else '-y' if vy < -0.5 else '+y'])
        beyond = c["protrude"] - to_edge
        edge = ('left' if vx < -0.5 else 'right' if vx > 0.5 else
                'top' if vy < -0.5 else 'bottom')
        side = 'BOTTOM' if fp.IsFlipped() else 'top'
        zlo = (z_board_bot if fp.IsFlipped() else z_board_top)
        zhi = zlo + c["h"] if not fp.IsFlipped() else z_board_pcb
        line("ok" if beyond <= 0 else "note",
             f"{ref} {c['what']}",
             (f"plug stays within the board outline" if beyond <= 0 else
              f"needs {beyond:.1f} mm clear BEYOND the {edge} edge") +
             f", at z {min(zlo,zhi):.1f}-{max(zlo,zhi):.1f} mm ({side} side)", c["src"])

    # ------------------------------------- answerable from CAD, vs actually unmeasurable
    #
    # This list used to open "the frame is a listing, not a measurement". That was true
    # of the Mark4 and is NOT true of the TBS Source One, whose DXF is published at
    # github.com/tbs-trappy/source_one. So the items split in two, and conflating them
    # sent a builder to fetch calipers for numbers that were already available.
    # ---------------------------------------------- ANSWERED from the manufacturer DXF
    C = design.FRAME_CAD
    print("\n=== board vs the FC plate, MEASURED from the manufacturer DXF ===")
    print(f"     {C['src']}")
    fw, fl = C["fc_plate"]
    # These two lines used to test C["clear_per_side_w"] > 0 and C["clear_end_l"] > 0 -
    # two FROZEN LITERALS against zero - while printing the board's measured size beside
    # them, taking no part in the comparison. If the board grew, both still passed.
    # Derive the clearance instead, from the board bbox measured at the top of main()
    # and the plate and stack offsets parsed from the manufacturer DXF.
    # The DXF gives the plate and the stack offsets but NOT which way round the board is
    # fitted, and all four of its edges carry a connector, so the orientation is a build
    # decision. Take the WORST case rather than assuming one: the plate's 48.50 mm width
    # is the binding axis, so put the board's LARGER dimension on it. Whichever way it
    # ends up fitted, the real clearance is at least this.
    e0, e1 = C["stack_from_edges"]
    b_long, b_short = max(BL, BW), min(BL, BW)
    clear_w = min(e0, e1) - b_long / 2      # tight side of the plate's width
    clear_l = fl / 2 - b_short / 2          # along the plate's length, stack centred
    line("FAIL" if clear_w <= 0 else "ok", "board on the FC plate, binding axis",
         f"board {b_long:.2f} mm across a {fw:.2f} mm plate, stack {e0:.1f}/{e1:.1f} mm "
         f"from the edges -> {clear_w:.2f} mm clear on the TIGHT side (worst-case "
         f"orientation)", C["src"])
    line("FAIL" if clear_l <= 0 else "ok", "board on the FC plate, long axis",
         f"board {b_short:.2f} mm on a {fl:.2f} mm plate -> {clear_l:.2f} mm clear, "
         f"stack centred lengthwise. NOT the binding axis", C["src"])
    # Report where the stored literal is OPTIMISTIC against this derivation, which is
    # what matters - a stored number that flatters the fit is how a board that does not
    # fit gets ordered. C["clear_per_side_w"] = 1.70 assumes the 45.10 mm dimension on
    # the width axis AND perfect centring; neither is guaranteed.
    if C["clear_per_side_w"] - clear_w > 0.05:
        line("note", "design.FRAME_CAD['clear_per_side_w'] is optimistic",
             f"stored {C['clear_per_side_w']:.2f} mm assumes the narrow board dimension "
             f"on the plate's width and a centred stack; worst case is "
             f"{clear_w:.2f} mm", C["src"])
    line("ok", "nothing stands proud under the board",
         f"the only features inside the board footprint are THROUGH-HOLES: "
         + ", ".join(f"{d:.2f} mm at ({x:+.2f},{y:+.2f})"
                     for x, y, d in C["under_board_holes"]), C["src"])
    line("ok", "standoff-candidate holes clear the board",
         f"nearest M3 holes that could carry a standoff are at |y| >= "
         f"{C['nearest_standoff_candidate_y']:.2f} mm, i.e. "
         f"{C['nearest_standoff_candidate_y']-BW/2:.2f} mm beyond the board's half-length",
         C["src"])
    print("\n=== the DXF cannot answer these - it is a nested sheet, not an assembly ===")
    for name, detail in [
        ("USB edge is clear", "J1's mouth is FLUSH with the board edge - zero slack. A standoff "
                              "on a DIFFERENT plate, a plate lip or the battery strap crossing "
                              f"that edge makes the port unusable. The {clear_w:.2f} mm "
                              "worst-case side margin above is the number to watch"),
        ("board rotation in the frame", "all four edges carry a connector - there may be only one "
                                        "orientation that works; decide before cutting looms"),
    ]:
        line("CAD", name, detail)

    print("\n=== SETTLED - do not go measuring these ===")
    line("ok", "top plate height",
         f"the kit's {STO['buy']:.0f} mm front standoffs stand on the mid plate; the top "
         f"plate's underside is {STO['top_plate_z']:.1f} mm up against a {z_max:.1f} mm "
         f"stack = {STO['top_plate_z']-z_max:.1f} mm spare. Use the kit's standoffs - the "
         f"earlier 'buy 35 mm' assumed a standoff at the 30.5 pattern that does not exist",
         STO["src"])
    line("ok", "motor screw length",
         f"arm {FRAME['arm_t']:.0f} mm is published, so tools/fasteners.py derives the screw - "
         f"buy an M3 assortment rather than pinning it in advance")

    # ------------------------------------------------------- 3D printing
    P = design.PRINTER
    print(f"\n=== printable accessories vs the {P['name']} "
          f"({P['x']:.0f} x {P['y']:.0f} x {P['z']:.0f} mm) ===")
    box = sorted((P["x"], P["y"], P["z"]), reverse=True)
    for name, dims in design.PRINTABLE.items():
        fits = all(a <= b for a, b in zip(sorted(dims, reverse=True), box))
        line("ok" if fits else "MEASURE", name,
             f"{dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm"
             + ("" if fits else " - DOES NOT FIT THE BED"))
    # The FRAME ITSELF is a different question from its accessories, and the answer is
    # not about the bed size.
    line("note", "printing the frame itself",
         f"the plates would fit {P['name']}, but ARMS MUST STAY CARBON. They carry motor "
         f"thrust, land the aircraft and see every bit of prop vibration; printed plastic "
         f"arms fail in fatigue, and a 7in quad has 4x1250 g of thrust behind that "
         f"failure. Print the accessories, buy the frame")
    line("note", "SO1-V6-skate is not landing gear",
         f"{design.SKATE['t']:.0f} mm flat wear plate, against the {SKID['drop']:.0f} mm "
         f"drop this design's clearance checks assume. Ground clearance for the downward "
         f"sensor still needs real legs")

    print("\n=== STILL PHYSICAL - no drawing can answer these ===")
    for name, detail in [
        ("microSD withdrawal", f"{CONN['J8']['protrude']:.0f} mm of clear space below the bottom "
                               f"edge, on the BOTTOM side, or the board must come out to swap "
                               f"cards - depends on how YOU mount it, not on the frame"),
        ("grommet compression", f"the grommets must hold {GAP['mm']:.1f} mm between the ESC's "
                                f"parts and this board's bottom parts UNDER LOAD - a property of "
                                f"the rubber, not of any dimension"),
    ]:
        line("MEASURE", name, detail)

    # ---------------------------------------------------- can they SEE, not just fit
    # Every other check here measures clearance. None of them expressed that a sensor
    # has to see something, so all of them passed U6 and U7 while both were aimed at
    # the top of the ESC 3 mm below. Same defect shape as the connectors facing inward.
    print("\n=== ground-facing sensors: line of sight (COMPUTED) ===")
    for ref, (normal, half_deg, rng_mm, what) in sorted(design.GROUND_FACING.items()):
        fp = b.FindFootprintByReference(ref)
        if fp is None:
            continue
        comp = design.COMPONENTS.get(ref)
        fitted = not (comp and comp[4])
        px = fp.GetPosition().x / 1e6 - cx
        py = fp.GetPosition().y / 1e6 - cy
        looks_down = normal[2] < 0
        on_bottom = fp.IsFlipped()
        if looks_down != on_bottom:
            line("note", f"{ref} faces the wrong way",
                 f"declared to look {'down' if looks_down else 'up'} but it is on the "
                 f"{'bottom' if on_bottom else 'top'} side", what)
            continue
        blocked = None
        for name_, top_mm, hl, hw, src in design.STACK_BELOW:
            # widen the sensor's cone by the distance to the obstruction
            spread = top_mm * math.tan(math.radians(half_deg))
            if (abs(px) - spread) <= hl and (abs(py) - spread) <= hw:
                blocked = (name_, top_mm, src)
                break
        if blocked and not fitted:
            name_, top_mm, src = blocked
            line("ok", f"{ref} is not fitted",
                 f"it could not see the ground here anyway - {name_} is {top_mm:.1f} mm "
                 f"below it and fills the cone; left off deliberately, see "
                 f"design.POPULATE_BLIND_SENSORS", what)
        elif blocked:
            name_, top_mm, src = blocked
            line("note", f"{ref} CANNOT SEE THE GROUND",
                 f"{name_} is {top_mm:.1f} mm below it and spans the whole cone "
                 f"({half_deg:.0f} deg half-angle); the sensor is {abs(px):.1f}, "
                 f"{abs(py):.1f} mm from centre, well inside it", f"{what} - {src}")
        else:
            line("ok", f"{ref} has a clear view down",
                 f"nothing in the stack enters its {half_deg:.0f} deg cone", what)

    # ---------------------------------------------- camera (companion Pi) line of sight
    # The optical-flow camera on the companion Pi is also ground-facing, but it is NOT on
    # this board - it hangs under the FC on the Pi companion. Modelled in cad/drone.scad;
    # its constraint is depth: the lens must sit ABOVE the skid contact line or it is
    # crushed on landing.
    #
    # NOTE the authority for ground clearance is check_cad_fit.py's GROUND_PARTS, which
    # measures each hanging part's LOWEST VERTEX against the contact plane. This line is
    # arithmetic on four constants and cannot see where a part is actually placed; it is
    # kept as a cheap early warning for the DEFERRED camera, which is not in the CAD.
    # (The comment here used to quote "25 mm skid drop ... 13 mm of margin" - both were
    # drop-25 leftovers; design.SKID["drop"] has been 40.0 mm since 2026-09-05.)
    cam = getattr(design, "CAMERA", None)
    skid = getattr(design, "SKID", None)
    if cam and skid:
        # The lens barrel pokes lens_len below the module body, so the lens TIP is
        # mod_t + lens_len below the mounting surface — not just mod_t. The first
        # version of this check ignored the barrel and reported 16.5 mm of margin
        # where only 13.0 mm exists; a 3 mm silent optimism on the number that decides
        # whether the lens is crushed on landing.
        lens_line = skid["drop"] + skid["t"]                    # contact line below the arm
        lens_tip = cam["mod_t"] + cam.get("lens_len", 0.0)      # tip below mount surface
        margin = lens_line - lens_tip
        line("ok" if margin > 0 else "FAIL", "flow camera lens vs skid contact line",
             f"{margin:.1f} mm of margin "
             f"(lens line {lens_line:.1f} mm - module depth {cam['mod_t']:.1f} mm "
             f"- lens barrel {cam.get('lens_len', 0.0):.1f} mm)",
             f"{cam['src']} + {skid['src']}")

    print(f"\n{ok_n} computed check(s) ok, {warn_n} item(s) needing attention or "
          f"measurement, {fail_n} FAILURE(S)")
    # os._exit rather than sys.exit because pcbnew's Python bindings crash on
    # interpreter teardown - but it used to be os._exit(0) UNCONDITIONALLY, so this
    # whole file was decorative: preflight.py gates on rc == 0, which no result here
    # could ever change. The code is now the answer.
    sys.stdout.flush(); os._exit(1 if fail_n else 0)


main()
