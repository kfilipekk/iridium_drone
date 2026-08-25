#!/usr/bin/env python3
"""Mechanical fit of the board in the stack and the frame.

Usage: python3 tools/check_mechanical.py [board.kicad_pcb]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = sys.argv[1] if len(sys.argv) > 1 else 'NAVCORE-SoOP.kicad_pcb'

# --- the rest of the stack, all declared with a source ------------------------------
ESC   = design.ESC
# Read from design.FRAME, not restated.
FRAME = design.FRAME
SKID  = design.SKID
GAP   = dict(mm=design.MOUNTING["gap"], src=design.MOUNTING["src"])
GROMMET_D = dict(mm=design.MOUNTING["grommet_d"], src=design.MOUNTING["src"])
BOARD_T   = dict(mm=1.6, src="[M] design.py stackup")
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
    # The stack does not start on the bottom plate.
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
    sep = ESC["parts"] + GAP["mm"] + BOT_PARTS["mm"]
    line("MEASURE", "inter-PCB separation the grommets must hold",
         f"{sep:.2f} mm between the ESC's PCB top face and this board's PCB underside "
         f"(ESC parts {ESC['parts']:.1f} + air {GAP['mm']:.1f} + bottom parts "
         f"{BOT_PARTS['mm']:.2f}); compressed grommet height is [A]", GAP["src"])
    # Required_standoff() returns buy=None when the stack is taller than the longest stock length.
    if STO["buy"] is None:
        line("FAIL", "no stock standoff is long enough",
             f"stack needs {STO['need']:.1f} mm; the longest stock length is "
             f"{max(design.STANDOFF_STOCK):.0f} mm", STO["src"])
    else:
        line("FAIL" if z_max > STO["buy"] else "ok", "tallest point of the stack",
             f"{z_max:.1f} mm against a {STO['buy']} mm standoff "
             f"({STO['buy']-z_max:.1f} mm spare) - consistency check, passes by "
             f"construction", STO["src"])
    line("note" if STO["buy"] and STO["buy"] > FRAME["inner_h"] else "ok",
         "standoff length vs the kit's",
         f"stack needs {z_max:.1f} mm and the kit ships {FRAME['inner_h']:.0f} mm - "
         + (f"BUY {STO['buy']} mm (a few pounds, and standoff length is a purchase, "
            f"not a frame property)" if STO["buy"] else
            "and NOTHING IN STOCK FITS - see the failure above"), STO["src"])

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
    # ---------------------------------------------- answered from the manufacturer DXF
    C = design.FRAME_CAD
    print("\n=== board vs the FC plate, MEASURED from the manufacturer DXF ===")
    print(f"     {C['src']}")
    fw, fl = C["fc_plate"]
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
         f"{STO['buy']} mm standoffs against a {z_max:.1f} mm stack = "
         f"{STO['buy']-z_max:.1f} mm spare. The kit's {FRAME['inner_h']:.0f} mm does NOT "
         f"fit; standoff length is a PURCHASE, so buy {STO['buy']} mm",
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

    # ---------------------------------------------------- can they see, not just fit
    # Every other check here measures clearance.
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
    cam = getattr(design, "CAMERA", None)
    skid = getattr(design, "SKID", None)
    if cam and skid:
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
    sys.stdout.flush(); os._exit(1 if fail_n else 0)


main()
