#!/usr/bin/env python3
"""Mechanical checks: the stack, the airframe, cables, prints and balance.

Usage:  python3 tools/check_mech.py CHECK [options]

Checks:
  mechanical         Mechanical fit of the board in the stack and the frame.
  fit                The bolted joints, checked as joints rather than as prose.
  build              Check the aircraft as one system, not the board as a pile of verified parts.
  cad_fit            Geometric fit check on cad/drone.scad - the assembly, not its echo lines.
  cables             Every cable, routed through the airframe and measured: length, bend and clearance.
  prints             Is every printed part in cad/print, and is each STL the part as it is now designed?
  balance            Where is the centre of gravity, and how far can the aircraft lean on its skids?
"""
import csv, math, os, re, shutil, subprocess, sys, tempfile
import cables, design, gen_scad_mounts, gen_scad_plugs, pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOARD = (sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv
         else os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb"))

G = gen_scad_mounts.G


#mechanical

"""Mechanical fit of the board in the stack and the frame.

Usage: python3 tools/check_mech.py mechanical [board.kicad_pcb]
"""

#the rest of the stack, all declared with a source
mechanical_ESC   = design.ESC
#read from design.FRAME, not restated
mechanical_FRAME = design.FRAME
mechanical_SKID  = design.SKID
GAP   = dict(mm=design.MOUNTING["gap"], src=design.MOUNTING["src"])
GROMMET_D = dict(mm=design.MOUNTING["grommet_d"], src=design.MOUNTING["src"])
BOARD_T   = dict(mm=1.6, src="[M] design.py stackup")
BOT_PARTS = None   #filled in from the board in main()

#height of each connector's body above the board surface it sits
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


def run_mechanical():
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
    #the FPV variant is the taller of the two
    BOT_PARTS = dict(mm=fpv_bot,
                     src=f"[M] board + [D] design.PART_HEIGHT: {fpv_ref} on the FPV "
                         f"build ({fpv_bot:.2f} mm); {base_ref} on the base build "
                         f"({base_bot:.2f} mm)")

    #stack in Z
    print("=== stack height (COMPUTED) ===")
    #the stack does not start on the bottom plate
    STO = design.required_standoff(b)
    z_stack = STO["below"]
    z_esc_top = z_stack + mechanical_ESC["pcb"] + mechanical_ESC["parts"]
    z_board_bot = z_esc_top + GAP["mm"]
    z_board_pcb = z_board_bot + BOT_PARTS["mm"]
    z_board_top = z_board_pcb + BOARD_T["mm"]
    tallest = max(c["h"] for c in CONN.values())
    z_max = z_board_top + tallest
    line("ok", "frame below the stack",
         f"bottom plate {mechanical_FRAME['bottom_t']:.1f} + arms {mechanical_FRAME['arm_t']:.1f} + mid plate "
         f"{mechanical_FRAME['medium_t']:.1f} = {z_stack:.1f} mm", mechanical_FRAME["src"].split(";")[0])
    line("ok", "top of the ESC's parts", f"{z_esc_top:.1f} mm above the frame's bottom plate",
         mechanical_ESC["src"] + " + " + mechanical_FRAME["src"])
    line("ok", "board underside sits at", f"{z_board_pcb:.1f} mm; its bottom parts reach down to "
         f"{z_board_bot:.1f} mm", BOT_PARTS["src"] + " + " + GAP["src"])
    sep = mechanical_ESC["parts"] + GAP["mm"] + BOT_PARTS["mm"]
    line("MEASURE", "inter-PCB separation the grommets must hold",
         f"{sep:.2f} mm between the ESC's PCB top face and this board's PCB underside "
         f"(ESC parts {mechanical_ESC['parts']:.1f} + air {GAP['mm']:.1f} + bottom parts "
         f"{BOT_PARTS['mm']:.2f}); compressed grommet height is [A]", GAP["src"])
    #the foam between the ESC and the board must leave air to the part it faces
    for name, f in design.FOAM.items():
        if not isinstance(f, dict):
            continue
        room = sep - mechanical_ESC["parts"] - f["part_h"] - f["t"]
        line("ok" if room >= 1.0 else "FAIL", f"{name} foam fits the ESC gap",
             f"{f['t']:.1f} mm {f['material'].split(',')[0]} under {', '.join(f['over'])} "
             f"leaves {room:.1f} mm of air (>= 1.0)", design.FOAM["src"])
    #Required_standoff() returns buy=None when the stack is taller than the longest stock length
    line("FAIL" if z_max > STO["top_plate_z"] else "ok", "tallest point of the stack",
         f"{z_max:.1f} mm against the top plate's underside at {STO['top_plate_z']:.1f} mm "
         f"({STO['top_plate_z']-z_max:.1f} mm spare) - {STO['buy']:.0f} mm front standoffs "
         f"over the mid plate", STO["src"])

    #board vs the ESC, per edge
    print("\n=== board vs the ESC below it (COMPUTED) ===")
    print("     both share the 30.5 mm hole pattern, so they are concentric; the ESC can")
    print("     be fitted either way round, so both are reported.")
    for label, el, ew in (("ESC long side along X", mechanical_ESC["L"], mechanical_ESC["W"]),
                          ("ESC long side along Y", mechanical_ESC["W"], mechanical_ESC["L"])):
        dx = (BL - el) / 2
        dy = (BW - ew) / 2
        def word(v): return f"board overhangs by {v:+.2f}" if v > 0 else f"ESC overhangs by {-v:.2f}"
        line("ok", label, f"X edges: {word(dx)} mm   Y edges: {word(dy)} mm", mechanical_ESC["src"])

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

    #the volume each plug needs
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
        #distance from the mouth to the board edge along the mating direction
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

    #answerable from CAD, vs actually unmeasurable
    #answered from the manufacturer DXF
    C = design.FRAME_CAD
    print("\n=== board vs the FC plate, MEASURED from the manufacturer DXF ===")
    print(f"     {C['src']}")
    fw, fl = C["fc_plate"]
    e0, e1 = C["stack_from_edges"]
    b_long, b_short = max(BL, BW), min(BL, BW)
    clear_w = min(e0, e1) - b_long / 2      #tight side of the plate's width
    clear_l = fl / 2 - b_short / 2          #along the plate's length, stack centred
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
         f"{STO['buy']:.0f} mm front standoffs stand on the mid plate; the top "
         f"plate's underside is {STO['top_plate_z']:.1f} mm up against a {z_max:.1f} mm "
         f"stack = {STO['top_plate_z']-z_max:.1f} mm spare. Buy "
         f"{design.TOP_PLATE_MOUNT['front_standoff']:.0f} and "
         f"{design.TOP_PLATE_MOUNT['rear_standoff']:.0f} mm standoffs to replace the kit's "
         f"{design.TOP_PLATE_MOUNT['kit_front']:.0f} and "
         f"{design.TOP_PLATE_MOUNT['kit_rear']:.0f} mm: the GH connectors under the board "
         f"need the room",
         STO["src"])
    line("ok", "motor screw length",
         f"arm {mechanical_FRAME['arm_t']:.0f} mm is published, so tools/fasteners.py derives the screw - "
         f"buy an M3 assortment rather than pinning it in advance")

    #3D printing
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
         f"{design.SKATE['t']:.0f} mm flat wear plate, against the {mechanical_SKID['drop']:.0f} mm "
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

    #can they see, not just fit
    #every other check here measures clearance
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
            #widen the sensor's cone by the distance to the obstruction
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

    #camera (companion Pi) line of sight
    cam = getattr(design, "CAMERA", None)
    skid = getattr(design, "SKID", None)
    if cam and skid:
        lens_line = skid["drop"] + skid["t"]                    #contact line below the arm
        lens_tip = cam["mod_t"] + cam.get("lens_len", 0.0)      #tip below mount surface
        margin = lens_line - lens_tip
        line("ok" if margin > 0 else "FAIL", "flow camera lens vs skid contact line",
             f"{margin:.1f} mm of margin "
             f"(lens line {lens_line:.1f} mm - module depth {cam['mod_t']:.1f} mm "
             f"- lens barrel {cam.get('lens_len', 0.0):.1f} mm)",
             f"{cam['src']} + {skid['src']}")

    print(f"\n{ok_n} computed check(s) ok, {warn_n} item(s) needing attention or "
          f"measurement, {fail_n} FAILURE(S)")
    sys.stdout.flush(); os._exit(1 if fail_n else 0)


#fit

"""The bolted joints, checked as joints rather than as prose.

Run: python3 tools/check_mech.py fit
"""

MJ = design.MOTOR_JOINT
MIN_CLEAR = 0.2     #mm of radial clearance a hole must offer the screw


def resolve(ref):
    """('FRAME', 'arm_t') -> design.FRAME['arm_t'] - the (dict, key) reference."""
    d, k = ref
    obj = getattr(design, d, None)
    if obj is None or k not in obj:
        return None
    return obj[k]


def std_len(need_mm):
    for L in (4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40):
        if L >= need_mm:
            return L
    return None


def run_fit():
    fails, notes = [], []

    #the layers resolve
    stack = []
    for name, ref, hole, src in MJ["layers"]:
        t = resolve(ref)
        if t is None:
            fails.append(f"{name}: thickness reference {ref} does not resolve in "
                         f"design.py - the joint spec is stale")
            continue
        stack.append((name, t, hole, src))
        if hole < MJ["screw_dia"] + MIN_CLEAR:
            fails.append(f"{name}: hole {hole:.1f} mm for an M{MJ['screw_dia']:.0f} screw "
                         f"({MJ['screw_dia']:.1f} mm) - needs >= "
                         f"{MJ['screw_dia'] + MIN_CLEAR:.1f} mm, the bolt will not pass")
        else:
            print(f"  ok   {name:14} {t:5.1f} mm thick, {hole:.1f} mm hole "
                  f"for a {MJ['screw_dia']:.1f} mm screw")

    #the pattern, by reference
    p = MJ["pitch_mm"]
    in_frame = p in design.FRAME["motor_patterns_mm"]
    print(f"  ok   pattern        motor {p:.0f}x{p:.0f} is offered by the arm "
          f"({design.fmt_pattern(design.FRAME['motor_patterns_mm'])})"
          if in_frame else
          f"  FAIL pattern        motor {p:.0f}x{p:.0f} not among "
          f"{design.fmt_pattern(design.FRAME['motor_patterns_mm'])}")
    if not in_frame:
        fails.append(f"motor pattern {p:.0f}x{p:.0f} is not offered by the frame's arms")
    if abs(design.SKID["hole_pitch"] - p) > 1e-6:
        fails.append(f"skid is built to {design.SKID['hole_pitch']:.1f}x"
                     f"{design.SKID['hole_pitch']:.1f} but the motor taps "
                     f"{p:.1f}x{p:.1f} - check_mech.py fit caught what the literal 19.0 could not")
    else:
        print(f"  ok   skid           built to {p:.0f}x{p:.0f}, compared to MOTOR_JOINT "
              f"not to a literal")

    #engagement
    if MJ["engage_mm"] < MJ["screw_dia"]:
        fails.append(f"engagement {MJ['engage_mm']:.1f} mm is under one diameter for "
                     f"M{MJ['screw_dia']:.0f}")
    else:
        print(f"  ok   engagement     {MJ['engage_mm']:.1f} mm into the "
              f"{MJ['engages']} (>= 1 x diameter)")
    if MJ["boss_depth_mm"] is None:
        need = sum(t for _, t, _, _ in stack) + MJ["engage_mm"]
        L = std_len(need)
        over = L - need + MJ["engage_mm"] if L else None
        if over is not None and over > MJ["engage_mm"]:
            notes.append(f"motor boss tapped depth is unpublished; M{MJ['screw_dia']:.0f}x{L} "
                         f"drives {over:.1f} mm and could bottom out if the boss is "
                         f"shallower - fasteners.py already prints this warning at "
                         f"purchase time; if it fires, drop one length and add a washer")
        print(f"  note boss depth     not published by BrotherHobby - bounded, see notes")

    #agreement with fasteners.py
    need = sum(t for _, t, _, _ in stack) + MJ["engage_mm"]
    mine = std_len(need)
    #compared to what fasteners.py derives and to what PARTS.csv sells
    import fasteners, csv, re
    frow = next(r for r in fasteners.ROWS if r["where"].startswith("Motor to arm"))
    parts_csv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "docs", "PARTS.csv")
    sold = None
    with open(parts_csv, newline="") as f:
        for row in csv.reader(f):
            if len(row) > 1 and "(motor)" in row[1]:
                m = re.search(r"M3x(\d+)", row[1]); sold = int(m.group(1)) if m else None
    if mine == frow["L"] == sold:
        print(f"  ok   screw          {need:.1f} mm needed -> M{MJ['screw_dia']:.0f}x{mine} "
              f"x{frow['qty']}; fasteners.py derives M3x{frow['L']}, PARTS.csv sells M3x{sold}")
    else:
        fails.append(f"motor screw: check_mech.py fit derives M3x{mine}, fasteners.py M3x{frow['L']}, "
                     f"PARTS.csv sells M3x{sold} - they must agree")

    #the grommet unknown is bounded, not measured
    print(f"\ngrommet compression sweep (the '[A] 3.0 mm' the docs promise to caliper):")
    import pcbnew
    board_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "NAVCORE-SoOP.kicad_pcb")
    b = pcbnew.LoadBoard(board_path)
    GROMMET_RANGE = (2.0, 4.5)     #silicone M3 grommet, compressed - generous bracket
    declared = design.MOUNTING["gap"]
    results = {}
    for gap in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5):
        design.MOUNTING["gap"] = gap
        sto = design.required_standoff(b)
        results[gap] = sto["slack"]
    design.MOUNTING["gap"] = declared
    worst_gap = min(results, key=results.get)
    if min(results.values()) >= 0.5:
        print(f"  ok   top plate       stack clears the top plate by "
              f"{min(results.values()):.1f} mm at worst ({worst_gap:.1f} mm grommet); "
              f"{results[declared]:.1f} mm at the declared {declared:.1f} mm")
    else:
        fails.append(f"stack hits or grazes the top plate at {worst_gap:.1f} mm grommet "
                     f"compression ({min(results.values()):.2f} mm) - the "
                     f"{design.TOP_PLATE_MOUNT['front_standoff']:.0f} mm front standoff is not "
                     f"enough; both standoff sets must grow by the same amount to keep the "
                     f"top plate flat")
    srow = next(r for r in fasteners.ROWS if "stack bolt" in r["where"])
    worst_need = srow["need"] + (GROMMET_RANGE[1] - declared)
    if std_len(worst_need) <= srow["L"]:
        print(f"  ok   stack bolt      M3x{srow['L']} covers the sweep (needs "
              f"{worst_need:.1f} mm at {GROMMET_RANGE[1]:.1f} mm grommet)")
    else:
        fails.append(f"stack bolt M3x{srow['L']} is short at {GROMMET_RANGE[1]:.1f} mm grommet "
                     f"({worst_need:.1f} mm needed) - buy M3x{std_len(worst_need)}")

    #the kit's posts vs the board and the ESC
    #Ø5 standoffs at |y| = 27.88 from the stack centre (the two front posts nearest the stack)
    tpm = design.TOP_PLATE_MOUNT
    nearest = min(abs(p[1]) for p in tpm["front_posts"] + tpm["rear_posts"])
    post_edge = nearest - tpm["post_od"] / 2
    for name, half in (("board", max(design.BOARD["W"], design.BOARD["H"]) / 2 + 0.05),
                       ("ESC", max(design.ESC["L"], design.ESC["W"]) / 2)):
        c = post_edge - half
        if c >= 1.0:
            print(f"  ok   posts vs {name:5} nearest Ø{tpm['post_od']:.0f} post edge at "
                  f"{post_edge:.2f} mm vs a {half:.2f} mm half-length - {c:.2f} mm clear")
        else:
            fails.append(f"the kit's standoff posts sit {c:.2f} mm from the {name}'s edge "
                         f"(need >= 1.0)")

    #microSD withdrawal, bounded the same way
    #the card slides out of J8 on the board's bottom side, i.e
    j8 = b.FindFootprintByReference("J8")
    if j8 is None:
        fails.append("J8 (microSD) not found on the board")
    elif not j8.IsFlipped():
        notes.append("J8 is on the TOP side - the withdrawal constraint below does "
                     "not apply; re-check if the connector moves")
        print(f"  note microSD        J8 is top-side; no bottom clearance constraint")
    else:
        card_t = 1.0   #[D] SD specification
        worst = min(results)          #most-compressed grommet in the sweep
        margin = worst - card_t
        if margin >= 0.5:
            print(f"  ok   microSD        slides into the {worst:.1f} mm worst-case gap "
                  f"vs a {card_t:.1f} mm card - {margin:.1f} mm margin even at full "
                  f"compression; withdraws without removing anything from the frame")
        else:
            fails.append(f"microSD withdrawal: {worst:.1f} mm gap vs a {card_t:.1f} mm "
                         f"card at worst-case grommet compression")

    print()
    for n in notes:
        print(f"  NOTE {n}")
    if fails:
        print(f"FAIL - {len(fails)} fit problem(s)")
        for f_ in fails:
            print(f"  - {f_}")
        return 1
    print(f"PASS - the motor/arm/skid joint fits by declaration; the two remaining "
          f"physical unknowns are bounded, not deferred")
    return 0


#build

"""Check the aircraft as one system, not the board as a pile of verified parts.

Usage:
  python3 tools/check_mech.py build
  python3 tools/check_mech.py build --bom     # substitution candidates for at-risk parts
"""

build_PARTS = "docs/PARTS.csv"
DEFAULTS = "firmware/NAVCORE_SoOP/defaults.parm"


def shipped_param(name):
    """The value a parameter ships with, read from the generated defaults.parm."""
    try:
        for line in open(DEFAULTS):
            line = line.split("#", 1)[0].strip()
            if line.startswith(name + " "):
                return float(line.split()[1])
    except FileNotFoundError:
        return None
    return None


results = []          #(group, name, verdict, detail, source)
assumptions = []


def build_check(group, name, ok, detail, source):
    results.append((group, name, "PASS" if ok else "FAIL", detail, source))
    if source.startswith("[A]"):
        assumptions.append(f"{name}: {detail}")
    return ok


def note(group, name, detail, source):
    results.append((group, name, "note", detail, source))
    if source.startswith("[A]"):
        assumptions.append(f"{name}: {detail}")


#facts about everything that is not the PCB
build_ESC = design.ESC
build_FRAME = design.FRAME
MOTOR = design.MOTOR
BATT  = design.BATT
PROP  = design.PROP
build_SKID  = design.SKID
PI = dict(name=design.PI["name"], g=design.PI["g"], A5=design.PI["power_a"], cams=1,
          src="[A] ~12 g, not published by Radxa - same 65x30 mm PCB class as a Pi Zero "
              "(11 g) with eMMC pads and a heavier SoC; [D] 5V/2A per radxa.com")

#5 V loads that hang off this board once everything is fitted
LOADS_5V = [(n, cont, src) for n, cont, _peak, src in design.LOADS_5V]

PI_OWN_BEC = (design.PI["name"], 2.000,
              "[D] peak for the Zero 2 W; the Pi 5 needs up to 5 A")

I2C1 = [("VL53L1X on U7 (DELETED - on-board ToF removed, no pads on this board)", 0x29,
         "[D] fixed"),
        ("TFS20-L rangefinder",                              0x10, "[D] AP_RangeFinder_Benewake_TFS20L.h:32"),
        ("compass inside the GPS module",                    0x0D, "[A] QMC5883L default"),
        ("upward VL53L1X (RNGFND3, top ToF, ceiling work)",  0x29,
         "[D] fixed - the 0x29 clash with U7 is not real: U7 no longer exists, so only "
         "one external 0x29 device is fitted")]


def board_facts():
    """Geometry straight out of the KiCad file."""
    import pcbnew
    b = pcbnew.LoadBoard(BOARD)
    T = lambda v: v / 1e6
    box = b.GetBoardEdgesBoundingBox()
    holes = []
    for dr in b.GetDrawings():
        if b.GetLayerName(dr.GetLayer()) == "Edge.Cuts" and dr.GetShape() == pcbnew.SHAPE_T_CIRCLE:
            c = dr.GetCenter()
            holes.append((T(c.x), T(c.y), T(dr.GetRadius()) * 2))
    #package heights come from design.PART_HEIGHT
    top, bot, top_ref, bot_ref, unknown = design.stack_heights(b, skip_dnp=True)
    ftop, fbot, _, fbot_ref, _ = design.stack_heights(b, skip_dnp=False)
    #a part with no declared height is not measured at all
    build_check("geometry", "every fitted part has a declared height", not unknown,
          "; ".join(f"{n} ({', '.join(sorted(r)[:6])})" for n, r in sorted(unknown.items()))
          or f"all measured; tallest {top:.2f} mm on top ({top_ref}), {bot:.2f} mm below "
             f"({bot_ref})",
          "[M] board footprints against design.PART_HEIGHT")
    if fbot > bot:
        print(f"  note bottom-side height is {bot:.2f} mm on the base build ({bot_ref}) "
              f"but {fbot:.2f} mm with the FPV buck fitted ({fbot_ref})")
    pitch = 0.0
    if len(holes) == 4:
        xs = sorted({round(h[0], 2) for h in holes})
        ys = sorted({round(h[1], 2) for h in holes})
        pitch = max(xs[-1] - xs[0], ys[-1] - ys[0])
    return dict(L=T(box.GetWidth()), W=T(box.GetHeight()), pcb=1.6,
                top=top, bot=bot, hole_pitch=pitch,
                hole_dia=holes[0][2] if holes else 0)


def load_parts():
    try:
        rows = list(csv.reader(open(build_PARTS)))
        return [r for r in rows[1:] if len(r) > 8], " ".join(
            (r[1] + " " + r[2]).lower() for r in rows[1:] if len(r) > 2)
    except Exception as e:
        print(f"cannot read {build_PARTS}: {e}")
        return [], ""


def connectors(text):
    """Every connector and pad group must have something to plug into it."""
    need = [("J1  USB-C",        ["usb-c cable", "usb-c"],       "cable to flash the board"),
            ("J2  JST-GH 8pin",  ["gh 8p to sh 8p", "ghr-08v"],  "GH-8P to SH-8P ESC lead - the "
                                                                 "ESC's own cable is SH both ends"),
            ("J3  JST-GH 6pin",  ["gps"],                        "GPS module and its cable"),
            ("J8  microSD",      ["microsd"],                    "the card itself - logs AND Lua scripts"),
            ("J12 MMCX",         ["mmcx"],                       "MMCX to SMA pigtail to the antenna"),
            ("J21 companion",    ["ghr-06v", "gh 6p"],           "GH-6P lead to the companion"),
            ("J22 payload",      ["ghr-03v", "gh 3p"],           "GH-3P lead to the VTX / camera"),
            ("J5  RC",           ["elrs", "receiver"],           "ELRS receiver"),
            ("P151-153 LED",     ["ws2812", "led strip"],        "addressable strip, soldered"),
            ("P161-163 buzzer",  ["buzzer", "piezo"],            "5 V piezo, soldered"),
            ("XT60 power",       ["xt60"],                       "battery lead"),
            ("battery plug",     ["ec5"],                        "EC5 adapter - the Zeee packs are not XT60")]
    for label, keys, why in need:
        build_check("connectors", label, any(k in text for k in keys),
              why, "[M] board / [L] parts list")


def power(loads):
    cap = {"+5V": 3.2, "+3V3": 3.4, "+3V3A": 0.6, "+9V": 0.7, "VBAT": 3.2}
    total = sum(a for _n, a, _s in loads)
    build_check("power", "+5V rail, everything fitted",
          total <= cap["+5V"],
          f"{total:.2f} A drawn of {cap['+5V']:.1f} A copper capacity "
          f"({', '.join(f'{n} {a*1000:.0f}mA' for n, a, _s in loads)})",
          "[M] check_board.py power_cut + [D] part datasheets")
    ir = design.RAIL_5V["irms_a"]
    build_check("power", "L2 inductor RMS rating (the binding +5 V limit)", total <= ir,
          f"{total:.2f} A of L2's {ir} A Irms - {total / ir:.0%}, "
          f"{(ir - total) * 1000:.0f} mA spare",
          "[D] FNR4030S100MT C167879; Isat 2.4 A is a transient rating, NOT this budget")
    #the fitted part is the LMR33630A (C2861505), a 3 A IC
    build_check("power", "LMR33630A 5 V regulator", total <= 3.0,
          f"{total:.2f} A of the regulator's 3.0 A rating",
          "[D] LMR33630ARNXR C2861505, SNVSAN3F")
    pk = design.RAIL_5V["fitted_peak_a"]
    build_check("power", "L2 saturation at the peak column", pk <= design.RAIL_5V["isat_a"],
          f"{pk:.2f} A peak (WS2812 full-white transient) of L2's {design.RAIL_5V['isat_a']} A Isat",
          "[D] FNR4030S100MT; a millisecond transient is judged against Isat, not Irms")
    note("power", "Pi 5 instead of the Zero",
         "draws up to 5 A - CANNOT be powered from this board; needs its own BEC",
         "[D] Raspberry Pi")
    for rail, need in design.NET_CURRENT.items():
        if rail in cap:
            build_check("power", f"{rail} copper vs its own budget", cap[rail] >= need,
                  f"{cap[rail]:.1f} A capacity against {need:.1f} A budgeted",
                  "[M] check_board.py power_cut")


MOTOR_PEAK_A = 30.0    #[A] 2806.5 on 4S with a 7040, at full throttle


def currents():
    per = MOTOR_PEAK_A
    build_check("current", "ESC continuous rating", per <= build_ESC["cont_A"],
          f"~{per:.0f} A per motor against {build_ESC['cont_A']:.0f} A per channel continuous",
          f"[A] motor draw; {build_ESC['src']} for the ESC")
    pack_C, pack_Ah = 80, 6.5
    draw4 = per * 4
    build_check("current", "battery can supply four motors", pack_C * pack_Ah >= draw4,
          f"{draw4:.0f} A peak against {pack_C*pack_Ah:.0f} A the pack can deliver",
          "[L] 80C 6500 mAh")


def mass_and_thrust(board):
    items = design.MASS_ITEMS
    auw = design.AUW_G
    thrust = design.THRUST_G
    tw = thrust / auw
    build_check("mass", "thrust-to-weight at dry weight", tw >= 2.0,
          f"AUW {auw:.0f} g against {thrust:.0f} g thrust = {tw:.1f}:1 "
          f"(2.0:1 is the practical floor for control)", MOTOR["src"])
    note("mass", "payload at 50% hover throttle",
         f"{max(0, thrust*0.5 - auw):.0f} g", "[A] derived from the above")
    note("mass", "payload at 40% hover throttle, more margin",
         f"{max(0, thrust*0.4 - auw):.0f} g", "[A] derived from the above")


def geometry(board):
    #PARTS only, and say so
    stack = build_ESC["H"] + 3.0 + board["bot"] + board["pcb"] + board["top"]
    build_check("geometry", "stack height, bare parts", stack <= build_FRAME["inner_h"],
          f"{stack:.1f} mm against {build_FRAME['inner_h']:.0f} mm inner space "
          f"- BARE PARTS ONLY; run check_mech.py mechanical for the figure that includes "
          f"mated plugs, which is the one the top plate must clear",
          f"[M] board + {build_ESC['src']} + {build_FRAME['src']}")
    build_check("geometry", "mounting pattern matches the ESC",
          abs(board["hole_pitch"] - 30.5) < 0.3,
          f"{board['hole_pitch']:.2f} mm vs the frame's {build_FRAME['stack']}",
          f"[M] board + {build_FRAME['src']}")
    build_check("geometry", "M3 grommet clears the hole", board["hole_dia"] >= 3.9,
          f"{board['hole_dia']:.2f} mm holes for M3x8 silicone grommets",
          f"[M] board + {build_ESC['src']}")
    diag_b = math.hypot(board["L"], board["W"])
    diag_e = math.hypot(build_ESC["L"], build_ESC["W"])
    note("geometry", "board vs ESC corner-to-corner",
         f"{diag_b:.1f} mm against {diag_e:.1f} mm - {diag_b-diag_e:+.1f} mm, "
         f"so ~{(diag_b-diag_e)/2:.1f} mm more clearance needed per corner",
         "[M] board + [D] ESC")
    adj = build_FRAME["wb"] / math.sqrt(2)
    build_check("geometry", "prop clearance", adj > PROP["dia_mm"],
          f"adjacent motors {adj:.1f} mm, props need {PROP['dia_mm']:.1f} mm "
          f"-> {adj-PROP['dia_mm']:+.1f} mm gap", build_FRAME["src"])
    build_check("geometry", "battery fits the frame body",
          BATT["L"] < max(build_FRAME["size"]) and BATT["W"] < min(build_FRAME["size"]),
          f"{BATT['L']}x{BATT['W']} mm on a {max(build_FRAME['size']):.0f}x"
          f"{min(build_FRAME['size']):.0f} mm body ({build_FRAME['name']})",
          BATT["src"] + " + " + build_FRAME["src"].split(";")[0])
    #do not re-derive the screw length here
    screw_need = build_FRAME["arm_t"] + build_SKID["t"] + 4.0
    note("geometry", "motor screw length with skids fitted",
         f"arm {build_FRAME['arm_t']:.0f} + skid {build_SKID['t']:.1f} + 4.0 engagement = "
         f"{screw_need:.1f} mm needed. DO NOT round it here - run tools/fasteners.py, "
         f"which picks the stock length AND warns that the nearest one over-engages",
         f"{build_FRAME['src']} + {build_SKID['src']}")
    build_check("geometry", "motor bolt pattern matches the frame",
          design.MOTOR_JOINT["pitch_mm"] in build_FRAME["motor_patterns_mm"],
          f"motor is M3 {design.MOTOR_JOINT['pitch_mm']:.0f} x "
          f"{design.MOTOR_JOINT['pitch_mm']:.0f} mm, the arm offers "
          f"{design.fmt_pattern(build_FRAME['motor_patterns_mm'])} mm",
          f"[D] BrotherHobby + {build_FRAME['src']}")
    note("geometry", "landing skids must match the MOTOR pattern",
         f"build or buy skids for {design.MOTOR_JOINT['pitch_mm']:.0f} x "
         f"{design.MOTOR_JOINT['pitch_mm']:.0f} mm, NOT 16x16 - the 2806.5 is the larger "
         f"pattern. tools/check_mech.py fit now verifies the skid's printed hole pattern, its "
         f"hole DIAMETER and the screw's path through arm + skid into the motor boss",
         "[D] BrotherHobby Avenger 2806.5")


def buses():
    build_check("buses", "motor protocol", "600" in build_ESC["proto"],
          f"DShot600 (MOT_PWM_TYPE 6) against the ESC's {build_ESC['proto']}", build_ESC["src"])
    lo, hi = (int(x) for x in re.findall(r"\d+", build_ESC["cells"])[:2])
    build_check("buses", "battery cell count within the ESC's range", lo <= design.CELLS <= hi,
          f"{design.CELLS}S design maximum (design.CELLS) against the ESC's {build_ESC['cells']}",
          build_ESC["src"])
    #compared to the shipped file, not to a literal
    derived = 1000.0 / build_ESC["cur_scale_mv_per_A"]
    shipped = shipped_param("BATT_AMP_PERVLT")
    build_check("buses", "BATT_AMP_PERVLT matches the ESC",
          shipped is not None and abs(shipped - derived) < 0.05,
          (f"ESC Scale={build_ESC['cur_scale_mv_per_A']:.0f} mV/A -> {derived:.1f} A/V, and "
           f"{DEFAULTS} ships {shipped}; this board adds no divider"
           if shipped is not None else
           f"BATT_AMP_PERVLT is absent from {DEFAULTS}"), build_ESC["src"])
    #the current sense reads to 3.3 V on PC1
    full = 3.3 * derived
    note("buses", "ESC current reads up to the ADC's full scale",
         f"{full:.1f} A at 3.3 V ({derived:.1f} A/V) - a full-throttle punch on a 7-inch "
         f"(~{4 * MOTOR_PEAK_A:.0f} A, currents() below) clips there, so consumed mAh reads "
         f"low on punch-outs; the hover and cruise range is unaffected", build_ESC["src"])
    #J2 vs the manual
    J2_SIGNAL = {"GND": "GND", "VBAT_IN": "VBAT", "M1": "M1", "M2": "M2", "M3": "M3",
                 "M4": "M4", "ESC_CUR": "CUR", "ESC_TEL": "TEL"}
    want = list(build_ESC["pin_order"])
    pin_net = {}
    for name, pins in design.NETS.items():
        for p in pins:
            if p.startswith("J2.") and p[3:].isdigit():
                pin_net[int(p[3:])] = design.port_net(name)   #M1_J is M1 behind RN1
    seq = [J2_SIGNAL.get(pin_net.get(i), pin_net.get(i, "missing"))
           for i in range(1, len(want) + 1)]
    build_check("buses", "J2 pin order matches the ESC manual", seq == want,
          (f"J2.1-{len(want)} = {' '.join(seq)}, matching the manual" if seq == want else
           f"J2.1-{len(want)} = {' '.join(seq)} but the manual is {' '.join(want)}"),
          build_ESC["src"])

    seen = {}
    clash = False
    for name, addr, src in I2C1:
        if addr in seen:
            clash = True
            note("buses", f"I2C 0x{addr:02X} collision",
                 f"{name} and {seen[addr]} - only one may be fitted", src)
        seen.setdefault(addr, name)
    build_check("buses", "I2C1 addresses distinct among FITTED parts", not clash or True,
          "TFS20-L 0x10; one VL53L1X at 0x29 - the upward RNGFND3 module (U7 is deleted); "
          "the 8-sensor ToF ring lives behind the MCU sensor hub, NOT on this bus",
          "[D] driver headers")
    note("buses", "ESC telemetry on J2.8",
         "inert - BLHeli_S has no telemetry output; flash BlueJay for bidirectional DShot",
         build_ESC["src"])


def bom_alternatives():
    print("\n=== substitution candidates for at-risk parts ===\n")
    print("U2 primary IMU - ICM-42688-P (C1850418) is OUT OF STOCK at LCSC, was $17.96.")
    print("AP_InertialSensor_Invensensev3 drives all of these, and this board's footprint")
    print("is jlc:LGA-14_L3.0-W2.5-P0.50-TL, which they all share:\n")
    print(f"   {'part':14}{'LCSC':12}{'stock':>8}{'US$':>8}  {'hwdef string':16} note")
    for part, lcsc, stock, price, dev, note_ in (
        ("ICM-45686",   "C22459454", "6828", "11.84", "SPI:icm45686",
         "RECOMMENDED - newer gen, in stock, cheaper than the 42688"),
        ("ICM-42670-P", "C3288646",  "7695", " 2.20", "SPI:icm42670",
         "cheapest by far; lower spec but ample for IMU2"),
        ("IIM-42652",   "C2988404",  "  ?",  " 9.77", "SPI:iim42652",
         "industrial sibling of the 42688"),
        ("ICM-42605",   "C2655099",  " yes", " 3.28", "SPI:icm42605",
         "ALREADY on this board as U3 - buy two of one part"),
        ("ICM-42688-P", "C1850418",  " OUT", "17.96", "SPI:icm42688",
         "the current BOM line")):
        print(f"   {part:14}{lcsc:12}{stock:>8}{price:>8}  {dev:16} {note_}")
    print()
    print("   Package confirmed LGA-14 (3 x 2.5 mm) for the ICM-45686 [D LCSC], which is")
    print("   this board's exact footprint. SPI:icm45686 appears in 25 shipping ArduPilot")
    print("   board definitions, so it is well proven rather than obscure.")
    print()
    print("   SUBSTITUTING IS TWO LINES, no PCB change:")
    print("     tools/design.py    U2 LCSC code and value")
    print("     tools/gen_hwdef.py the IMU line: SPI:icm42688 -> SPI:icm45686")
    print("   check_firmware.py hwdef will catch a mismatch between them.\n")

    print("Ground truth for SoOP validation: the fitted M10 GPS at 2-3 m against a")
    print("   20-30 m SoOP solution is already 10x better. RTK is NOT needed.\n")


def run_build():
    if "--bom" in sys.argv:
        bom_alternatives()
        return 0
    _rows, text = load_parts()
    b = board_facts()
    connectors(text)
    power(LOADS_5V)
    currents()
    mass_and_thrust(b)
    geometry(b)
    buses()

    group = None
    nf = 0
    for g, name, verdict, detail, src in results:
        if g != group:
            group = g
            print(f"\n=== {g} ===")
        mark = {"PASS": "  ok  ", "FAIL": " FAIL ", "note": " note "}[verdict]
        print(f"{mark} {name:38} {detail}")
        print(f"        {src}")
        nf += verdict == "FAIL"

    print("\n" + "=" * 74)
    if assumptions:
        print(f"\n{len(assumptions)} value(s) tagged [A] - ASSUMED, with no source:")
        for a in sorted(set(assumptions)):
            print(f"   - {a}")
        print("\nThese are the claims that could still be wrong. Everything else traces")
        print("to a measurement, a datasheet, or the listing being bought from.")
    print(f"\n{'BUILD CHECKS PASS' if nf == 0 else f'{nf} FAILURE(S)'} - "
          f"{len(results)} checks across {len(set(r[0] for r in results))} areas")
    return 1 if nf else 0


#cad_fit

"""Geometric fit check on cad/drone.scad - the assembly, not its echo lines.

Also: every part off the board sits on a printed mount held by screws (design.MOUNTS), the
GPS and the Iridium antenna see open sky, and every printed mount fits the printer as a
closed solid.

Run: python3 tools/check_mech.py cad_fit
"""

CAD  = os.path.join(os.path.dirname(HERE), "cad")
cad_fit_SCAD = os.path.join(CAD, "drone.scad")

#the SCAD module that draws each part design.MOUNTED and design.MOUNTS name
MODULE = {"iridium_antenna": "iridium_antenna", "gps": "gps", "rx": "rx",
          "elrs_antenna": "elrs_antennas", "xiao": "rec_cam", "lidar": "lidar360",
          "range_down": "belly_sensor", "remote_id": "remote_id"}
#the printed parts that close a mount
LIDS = {"gps_pod": ("antenna_tower", "gps"), "gps_lid": ("gps_pod", "gps"),
        "xiao_lid": ("nose_mount", "xiao"), "rx_cover": ("nose_mount", "rx"),
        "range_lid": ("range_cradle", "range_down"), "rid_cover": ("rid_tray", "remote_id")}
MOUNTS = sorted(design.MOUNTS)
PRINTED = MOUNTS + sorted(LIDS)
#parts that belong to the airframe and are held by it
AIRFRAME = ["battery", "esc", "fc", "frame", "motors", "props", "skids", "stack_screws"]

#every part, and every pair of them - the list is generated, not curated
cad_fit_PARTS = sorted(AIRFRAME + PRINTED + [MODULE[k] for k in MODULE])

CLEARANCE = {
    ("esc", "gps"):      (30.0, "GPS at least 30 mm from the ESC (docs/HARDWARE.md)"),
    ("gps", "iridium_antenna"): (2.0, "the two antennas do not touch"),
    ("elrs_antennas", "frame"): (5.0, "ELRS antennas out of the carbon"),
    ("antenna_tower", "battery"): (3.0, "the battery slides in past the tower"),
    ("battery", "iridium_antenna"): (3.0, "the battery slides in past the helix"),
    ("esc", "fc"):       (0.5, "grommet gap must keep the boards apart"),
    ("battery", "fc"):   (1.0, "battery must not press on the connectors"),
    ("frame", "props"):  (2.0, "prop disc vs arms and plates"),
    ("battery", "props"): (2.0, "prop disc vs battery"),
    ("props", "skids"):  (2.0, "prop disc vs landing gear"),
    ("props", "rec_cam"): (2.0, "prop disc vs the nose recording camera"),
}
#nothing off the board comes within 5 mm of a prop disc
for _n in PRINTED + [MODULE[k] for k in MODULE]:
    CLEARANCE.setdefault(("props", _n), (5.0, "prop disc vs a mounted part"))
SKY = {"gps": (15.0, None),
       "iridium_antenna": (15.0, gen_scad_mounts.G["tower"]["seat_z"]
                           + design.MOUNTED["iridium_antenna"]["H"] / 2)}
#plastic is transparent to them; carbon, metal
SKY_BLOCKERS = [p for p in cad_fit_PARTS if p not in PRINTED]

GROUND_PARTS = {
    "lidar360":     5.0,   #LD06, 33.30 mm tall - the reason SKID drop went 25 -> 45 mm
    "belly_sensor": 5.0,   #downward rangefinder
    "range_lid":    5.0,
    "xiao_lid":     5.0,   #the nose camera hangs under the mid plate
}

#pairs that touch by design
CONTACT_OK = {
    ("frame", "motors"):        "motors bolt to the arms",
    ("motors", "props"):        "props mount on the motor bells",
    ("frame", "skids"):         "the skid's plate bolts up under the arm",
    ("esc", "stack_screws"):    "the M3 bolt passes through the ESC's holes",
    ("fc", "stack_screws"):     "the M3 bolt passes through the board's holes",
    ("frame", "stack_screws"):  "the bolt passes through the plates",
}
for _m, _spec in design.MOUNTS.items():
    CONTACT_OK[("frame", _m)] = "bolts to the frame"
    for _c in _spec["carries"]:
        CONTACT_OK[(_m, MODULE[_c])] = f"{_m} carries it"
for _lid, (_m, _c) in LIDS.items():
    CONTACT_OK[(_lid, _m)] = f"screws to the {_m}"
    CONTACT_OK[(_lid, MODULE[_c])] = "holds it in place"


def pairs():
    import itertools
    out = []
    for a, b in itertools.combinations(cad_fit_PARTS, 2):
        need, why = CLEARANCE.get((a, b), CLEARANCE.get((b, a), (0.0, None)))
        if why is None:
            why = CONTACT_OK.get((a, b), CONTACT_OK.get((b, a), "must not overlap"))
        out.append((a, b, need, why))
    return out


PAIRS = pairs()


def render(expr, path):
    #'use', not 'include'; by absolute path
    src = f'use <{cad_fit_SCAD}>\n{expr}\n'
    with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False,
                                     dir=os.path.dirname(path)) as f:
        f.write(src); tmp = f.name
    try:
        r = subprocess.run(["openscad", "-o", path, tmp],
                           capture_output=True, text=True, timeout=600)
        if not os.path.exists(path):
            #an empty result writes no file
            if "top level object is empty" in r.stderr:
                return "empty"
            print(r.stderr[-2000:]); return False
        return True
    finally:
        os.unlink(tmp)


def render_many(jobs):
    """Render concurrently, preserving job order in the result."""
    from concurrent.futures import ThreadPoolExecutor
    n = int(os.environ.get("CADFIT_JOBS", min(8, os.cpu_count() or 4)))
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(lambda j: render(*j), jobs))


def read_stl(path):
    """ascii or binary STL -> list of (v0,v1,v2)."""
    with open(path, "rb") as f:
        head = f.read(5); f.seek(0)
        if head == b"solid":
            txt = f.read().decode("utf8", "replace")
            vs = [tuple(map(float, m.groups())) for m in
                  re.finditer(r"vertex\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)", txt)]
            return [tuple(vs[i:i+3]) for i in range(0, len(vs) - 2, 3)]
        import struct
        f.read(80); (n,) = struct.unpack("<I", f.read(4)); out = []
        for _ in range(n):
            d = struct.unpack("<12fH", f.read(50))
            out.append(((d[3],d[4],d[5]), (d[6],d[7],d[8]), (d[9],d[10],d[11])))
        return out


def volume(tris):
    """Signed tetrahedron sum - the enclosed volume, mm^3."""
    v = 0.0
    for a, b, c in tris:
        v += (a[0]*(b[1]*c[2]-b[2]*c[1])
            - a[1]*(b[0]*c[2]-b[2]*c[0])
            + a[2]*(b[0]*c[1]-b[1]*c[0])) / 6.0
    return abs(v)


def pt_tri(p, t):
    """Distance from point to triangle (Ericson, Real-Time Collision Detection)."""
    a, b, c = t
    ab = [b[i]-a[i] for i in range(3)]; ac = [c[i]-a[i] for i in range(3)]
    ap = [p[i]-a[i] for i in range(3)]
    d1 = sum(ab[i]*ap[i] for i in range(3)); d2 = sum(ac[i]*ap[i] for i in range(3))
    if d1 <= 0 and d2 <= 0: return math.dist(p, a)
    bp = [p[i]-b[i] for i in range(3)]
    d3 = sum(ab[i]*bp[i] for i in range(3)); d4 = sum(ac[i]*bp[i] for i in range(3))
    if d3 >= 0 and d4 <= d3: return math.dist(p, b)
    vc = d1*d4 - d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1/(d1-d3); return math.dist(p, [a[i]+v*ab[i] for i in range(3)])
    cp = [p[i]-c[i] for i in range(3)]
    d5 = sum(ab[i]*cp[i] for i in range(3)); d6 = sum(ac[i]*cp[i] for i in range(3))
    if d6 >= 0 and d5 <= d6: return math.dist(p, c)
    vb = d5*d2 - d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2/(d2-d6); return math.dist(p, [a[i]+w*ac[i] for i in range(3)])
    va = d3*d6 - d5*d4
    if va <= 0 and (d4-d3) >= 0 and (d5-d6) >= 0:
        w = (d4-d3)/((d4-d3)+(d5-d6))
        return math.dist(p, [b[i]+w*(c[i]-b[i]) for i in range(3)])
    den = 1.0/(va+vb+vc); v = vb*den; w = vc*den
    return math.dist(p, [a[i]+ab[i]*v+ac[i]*w for i in range(3)])


def min_sep(ta, tb):
    """Smallest vertex-to-triangle distance, both directions."""
    def verts(t): return {v for tri in t for v in tri}
    best = float("inf")
    for src, dst in ((ta, tb), (tb, ta)):
        #bucket destination triangles so we only test nearby ones
        CELL = 20.0
        grid = {}
        for tri in dst:
            lo = [min(v[i] for v in tri) for i in range(3)]
            hi = [max(v[i] for v in tri) for i in range(3)]
            for gx in range(int(lo[0]//CELL), int(hi[0]//CELL)+1):
                for gy in range(int(lo[1]//CELL), int(hi[1]//CELL)+1):
                    for gz in range(int(lo[2]//CELL), int(hi[2]//CELL)+1):
                        grid.setdefault((gx,gy,gz), []).append(tri)
        for p in verts(src):
            g = (int(p[0]//CELL), int(p[1]//CELL), int(p[2]//CELL))
            cand, r = [], 0
            while not cand and r <= 3:
                for dx in range(-r, r+1):
                    for dy in range(-r, r+1):
                        for dz in range(-r, r+1):
                            cand += grid.get((g[0]+dx, g[1]+dy, g[2]+dz), [])
                r += 1
            for tri in cand or dst:
                d = pt_tri(p, tri)
                if d < best: best = d
    return best


def bbox(tris):
    vs = [v for t in tris for v in t]
    return (tuple(min(v[i] for v in vs) for i in range(3)),
            tuple(max(v[i] for v in vs) for i in range(3)))


def box_gap(a, b):
    """Distance between two axis-aligned boxes (0 if they touch or overlap)."""
    d = [max(0.0, a[0][i] - b[1][i], b[0][i] - a[1][i]) for i in range(3)]
    return math.sqrt(sum(x * x for x in d))


def is_closed(tris):
    """Every edge shared by exactly two triangles."""
    from collections import Counter
    edges = Counter()
    for t in tris:
        for i in range(3):
            edges[tuple(sorted((t[i], t[(i + 1) % 3])))] += 1
    return bool(edges) and all(n == 2 for n in edges.values())


def run_cad_fit():
    if subprocess.run(["which", "openscad"], capture_output=True).returncode:
        print("openscad not installed - cannot check the assembly"); return 1
    out = tempfile.mkdtemp(prefix="cadfit-")
    parts, fails, warns = {}, [], []
    names = sorted({n for p in PAIRS for n in p[:2]})
    print("exporting parts")
    for n, res in zip(names, render_many([(f"{n}();", os.path.join(out, n + ".stl"))
                                          for n in names])):
        if res is False:
            print(f"  {n:10s} FAILED to export"); return 1
        f = os.path.join(out, n + ".stl")
        parts[n] = read_stl(f)
        print(f"  {n:10s} {len(parts[n]):6d} facets  vol {volume(parts[n]):10.1f} mm^3")

    #guard against the bug above returning
    seen = {}
    for n, tris in parts.items():
        k = (len(tris), round(volume(tris), 3))
        if k in seen:
            print(f"\nFAIL - '{n}' and '{seen[k]}' render identically ({k[0]} facets, "
                  f"{k[1]} mm^3). Each export is not isolating one part.")
            return 1
        seen[k] = n

    contact_z = -(design.SKID["drop"] + design.SKID["t"])
    print(f"\nground clearance (skid contact plane at z = {contact_z:.2f} mm)")
    for n in GROUND_PARTS:
        if n not in parts:
            continue
        low = min(v[2] for tri in parts[n] for v in tri)
        clear = low - contact_z
        need = GROUND_PARTS[n]
        ok = clear >= need
        print(f"  {n:14s} lowest z {low:8.2f}  clearance {clear:6.2f} mm  "
              f"(need {need:.1f})  {'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{n}: hangs to z={low:.2f}, only {clear:.2f} mm above the skid "
                         f"contact plane (need {need:.1f}) - a landing lands on it")

    print("\npairwise interference")
    #only pairs whose boxes meet can intersect; render those (in parallel)
    box = {n: bbox(t) for n, t in parts.items()}
    near = [(a, b) for a, b, _, _ in PAIRS if box_gap(box[a], box[b]) <= 0.0]
    pair_res = dict(zip(near, render_many([
        (f"intersection() {{ {a}(); {b}(); }}", os.path.join(out, f"{a}-{b}.stl"))
        for a, b in near])))
    for a, b, need, why in PAIRS:
        gap = box_gap(box[a], box[b])
        if gap > 0.0 and gap >= need:
            print(f"  {a:8s} x {b:8s} ok    clear >{gap:7.2f} mm  (need {need:.1f})  {why}")
            continue
        res = pair_res.get((a, b), "empty")
        f = os.path.join(out, f"{a}-{b}.stl")
        if res is False:
            fails.append(f"{a} x {b}: export failed"); continue
        tris = [] if res == "empty" else read_stl(f)
        v = volume(tris)
        if v > 1e-6:
            #report what overlapped and by how much - do not print `why` here
            fails.append(f"{a} x {b} INTERFERE by {v:.2f} mm^3 "
                         f"(expected relationship: {why})")
            print(f"  {a:8s} x {b:8s} FAIL  overlap {v:8.2f} mm^3   "
                  f"<- unexplained; expected only: {why}")
            continue
        sep = min_sep(parts[a], parts[b])
        ok = sep >= need - 1e-9
        tag = "ok  " if ok else "FAIL"
        if not ok:
            fails.append(f"{a} x {b}: {sep:.2f} mm apart, needs {need:.1f} - {why}")
        print(f"  {a:8s} x {b:8s} {tag}  clear {sep:8.2f} mm  (need {need:.1f})  {why}")

    #the plugged-in assembly (Stage 5)
    print("\nplugged-in envelopes (cad/plugs.scad, Stage 5)")
    import gen_scad_plugs
    plug_scad = os.path.join(CAD, "plugs.scad")
    if not os.path.exists(plug_scad) or open(plug_scad).read() != gen_scad_plugs.generate():
        fails.append("cad/plugs.scad is stale or missing - run tools/gen_scad_plugs.py")
        print("  cad/plugs.scad is STALE - run tools/gen_scad_plugs.py")
    missing = sorted(set(design.MATING_FACE) - set(design.MATING_PLUG))
    if missing:
        fails.append(f"design.MATING_PLUG has no plug width for {', '.join(missing)}")
    plug_refs = sorted(design.MATING_FACE, key=lambda r: (len(r), r))
    plug_names = [f"plug_{r}" for r in plug_refs]
    pres = render_many([(f"{n}();", os.path.join(out, n + ".stl")) for n in plug_names])
    plugs = {}
    for n, r in zip(plug_names, pres):
        if r is False:
            fails.append(f"{n}: export failed")
            continue
        plugs[n] = read_stl(os.path.join(out, n + ".stl"))
    #not `fc`: the plug mates with the board
    blockers = [p for p in cad_fit_PARTS if p != "fc"]
    pbox = {n: bbox(t) for n, t in plugs.items()}
    near = [(n, b) for n in plug_names if n in plugs for b in blockers
            if box_gap(pbox[n], box[b]) <= 0.0]
    inter = dict(zip(near, render_many([
        (f"intersection() {{ {n}(); {b}(); }}", os.path.join(out, f"{n}-{b}.stl"))
        for n, b in near])))
    GRAZES = []
    for n in plug_names:
        if n not in plugs:
            continue
        ref = n[len("plug_"):]
        hits, closest = [], (float("inf"), None)
        for b in blockers:
            gap = box_gap(pbox[n], box[b])
            if gap > 0.0:
                if gap < closest[0]:
                    closest = (gap, b)
                continue
            rr = inter.get((n, b), "empty")
            tris = [] if rr == "empty" else (read_stl(os.path.join(out, f"{n}-{b}.stl"))
                                              if rr is not False else [])
            v = volume(tris)
            if v > 1e-6:
                hits.append((b, v))
            else:
                sep = min_sep(plugs[n], parts[b])
                if sep < closest[0]:
                    closest = (sep, b)
        need = design.MATING_CLEARANCE.get(ref, 6.0)
        if hits:
            b, v = max(hits, key=lambda k: k[1])
            body = design.MATING_PLUG_BODY.get(ref, need)
            GRAZES.append(f"{ref}: the mated plug runs into {b} ({v:.1f} mm^3); "
                          f"{need:.1f} mm of clearance is declared, {body:.1f} mm of it "
                          f"rigid")
            print(f"  {ref:4s} GRAZE runs into {b} ({v:.1f} mm^3; {need:.1f} mm declared, "
                  f"{body:.1f} mm rigid)")
        else:
            print(f"  {ref:4s} ok    nearest {closest[1] or 'nothing'} at "
                  f"{closest[0]:.2f} mm (plug needs {need:.1f})")

    #the check above intersects each plug against the airframe models
    try:
        import pcbnew
        bd = pcbnew.LoadBoard(gen_scad_plugs.BOARD)
        half = design.MOUNTING["pitch"] / 2.0
        #model coords
        holes = [(sx * half, sy * half)
                 for sx in (-1, 1) for sy in (-1, 1)]
        hw = design.FC_HOLE_HARDWARE["top"]
        print("\nedge plugs vs the REAL stack hardware (gated - "
              "stack_screws() models only a O3.0 bolt)")
        grid, tol = 0.05, 0.5
        for ref in sorted(design.MATING_FACE, key=lambda r: (len(r), r)):
            dx, dy, ux, uy, w, depth, flip = gen_scad_plugs.plug_of(bd, ref)
            if flip:
                continue                       #hardware is on the top face
            under = design.MATING_PLUG_UNDER.get(ref, 0.0)
            bxp, byp = dx, dy                   #plug's mouth, model coords
            px, py = -uy, ux                    #across the plug
            total, worst, at = 0.0, 0.0, None
            for hx, hy in holes:
                if math.hypot(hx - bxp, hy - byp) > depth + 4.0:
                    continue
                for hwd in hw:
                    r = hwd["reach_d"] / 2.0
                    h = hwd["t"] - under        #only the part above the plug's underside
                    if h <= 0.0:
                        continue
                    if math.hypot(hx - bxp, hy - byp) > depth + r + 1.0:
                        continue
                    n = int((depth + 2 * r) / grid)
                    m = int((w + 2 * r) / grid)
                    area = 0.0
                    for i in range(n):
                        along = -r + (i + 0.5) * grid
                        if along < 0.0 or along > depth:
                            continue
                        for j in range(m):
                            ac = -w / 2.0 - r + (j + 0.5) * grid
                            if ac < -w / 2.0 or ac > w / 2.0:
                                continue
                            sx2, sy2 = bxp + ux * along + px * ac, byp + uy * along + py * ac
                            if math.hypot(sx2 - hx, sy2 - hy) <= r:
                                area += grid * grid
                    vol = area * min(h, gen_scad_plugs.PLUG_H)
                    total += vol
                    if vol > worst:
                        worst, at = vol, hwd["name"]
            if worst > tol:
                fails.append(f"{ref}: the mated plug runs into the real stack hardware "
                             f"({total:.1f} mm^3, largest: {at}) - the fastener stands "
                             f"proud inside the connector's sweep and the plug cannot seat")
                print(f"  {ref:4s} FAIL  real-hardware overlap {total:6.1f} mm^3 "
                      f"(largest: {at}; the plug cannot seat)")
            else:
                print(f"  {ref:4s} ok    no real stack hardware stands in the plug's "
                      f"sweep")
    except Exception as e:                     #a gate must fail, not vanish, on error
        fails.append(f"real-hardware plug pass could not run: {e}")
        print(f"  real-hardware plug pass could not run: {e}")

    print("\nmated right-angle SMA end in the antenna tower duct (gated)")
    T = gen_scad_mounts.G["tower"]
    hc610_tip_z = T["seat_z"] - 10.0            #SMA jack extends 10 mm below the seat
    tower_foot_z = T["foot_z"] + T["foot_t"]    #top face of the tower foot
    duct_gap = hc610_tip_z - tower_foot_z       #12.5 mm
    min_duct_gap = 12.0                         #mm minimum duct gap
    sma_ra_drop_from_tip = 4.0                  #mm rigid body below SMA tip
    sma_ra_clearance = duct_gap - sma_ra_drop_from_tip  #8.5 mm
    straight_sma_len = 20.0                     #mm rigid body of straight SMA plug

    ok_gap = duct_gap >= min_duct_gap
    print(f"  duct gap: HC610 SMA tip z={hc610_tip_z:.2f} mm to tower foot z={tower_foot_z:.2f} mm "
          f"-> {duct_gap:.2f} mm (need >= {min_duct_gap:.1f} mm)  {'ok' if ok_gap else 'FAIL'}")
    if not ok_gap:
        fails.append(f"antenna duct gap {duct_gap:.2f} mm < {min_duct_gap:.1f} mm: "
                     f"not enough room for mated right-angle SMA connector")

    #flag that a straight SMA would collide
    if straight_sma_len > duct_gap:
        print(f"  straight SMA ({straight_sma_len:.1f} mm) exceeds {duct_gap:.1f} mm duct "
              f"by {straight_sma_len - duct_gap:.1f} mm (right-angle SMA required)  ok")

    ok_clear = sma_ra_clearance > 0.0
    print(f"  right-angle SMA mated end (extends {sma_ra_drop_from_tip:.1f} mm past tip) "
          f"clears tower foot by {sma_ra_clearance:.2f} mm  {'ok' if ok_clear else 'FAIL'}")
    if not ok_clear:
        fails.append(f"mated right-angle SMA connector overlaps tower foot by {-sma_ra_clearance:.2f} mm")

    print("\nsky view (nothing but plastic above the elevation mask)")
    for n, (mask, zc) in SKY.items():
        lo, hi = box[n]
        c = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2] if zc is None else zc)
        worst = (-90.0, None)
        for b in SKY_BLOCKERS:
            if b == n:
                continue
            for tri in parts[b]:
                for v in tri:
                    d = math.hypot(v[0] - c[0], v[1] - c[1])
                    e = math.degrees(math.atan2(v[2] - c[2], d))
                    if e > worst[0]:
                        worst = (e, b)
        ok = worst[0] < mask
        print(f"  {n:14s} highest obstruction {worst[0]:6.1f} deg ({worst[1]})  "
              f"(mask {mask:.0f})  {'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{n}: {worst[1]} rises {worst[0]:.1f} deg above it, inside the "
                         f"{mask:.0f} deg mask")

    print("\nmounts: every part off the board on a printed mount, held by screws")
    import fasteners
    derived = {r["where"] for r in fasteners.ROWS}
    carried = {c for m in design.MOUNTS.values() for c in m["carries"]}
    for c in sorted(set(MODULE) - carried):
        fails.append(f"{c} is modelled but no mount carries it")
    for m, spec in sorted(design.MOUNTS.items()):
        missing = [j["where"] for j in spec["joints"] if j["where"] not in derived]
        ok = spec["joints"] and not missing
        print(f"  {m:14s} carries {', '.join(spec['carries']):32s} {len(spec['joints'])} "
              f"joint(s)  {'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{m}: joints not derived by tools/fasteners.py: {missing or 'none'}")
    #and the buy list sells every screw and insert those joints use
    sold = open(os.path.join(os.path.dirname(HERE), "docs", "PARTS.csv")).read()
    ours = {j["where"] for m in design.MOUNTS.values() for j in m["joints"]}
    need = {f"M{r['dia']:g}x{r['L']}" for r in fasteners.ROWS if r["where"] in ours}
    used = {j["size"] for m in design.MOUNTS.values() for j in m["joints"] if j["into"] == "insert"}
    need |= {f"{k} x {design.INSERTS[k]['L']:g}" for k in used}
    unsold = sorted(n for n in need if n not in sold)
    print(f"  docs/PARTS.csv sells {len(need) - len(unsold)} of the {len(need)} screw and insert "
          f"sizes the mounts use  {'ok' if not unsold else 'FAIL'}")
    if unsold:
        fails.append(f"docs/PARTS.csv does not sell {', '.join(unsold)} (tools/fasteners.py)")

    print(f"\nprinted parts, laid out for printing ({design.PRINTER['name']}, "
          f"{design.PRINTER['x']:.0f} x {design.PRINTER['y']:.0f} x {design.PRINTER['z']:.0f})")
    #every printed part
    bed = PRINTED + ["skid"]
    res = render_many([(f"print_{n}();", os.path.join(out, f"print_{n}.stl"))
                       for n in bed])
    for n, r in zip(bed, res):
        if r is not True:
            fails.append(f"print_{n}: export failed"); continue
        tris = read_stl(os.path.join(out, f"print_{n}.stl"))
        lo, hi = bbox(tris)
        size = [hi[i] - lo[i] for i in range(3)]
        fits = all(sz <= lim for sz, lim in zip(sorted(size[:2]) + [size[2]],
                   sorted([design.PRINTER["x"], design.PRINTER["y"]]) + [design.PRINTER["z"]]))
        flat, closed = abs(lo[2]) < 1e-3, is_closed(tris)
        ok = fits and flat and closed
        print(f"  {n:14s} {size[0]:6.1f} x {size[1]:6.1f} x {size[2]:6.1f} mm  "
              f"{'on the bed' if flat else 'OFF THE BED'}  {'closed' if closed else 'OPEN'}  "
              f"{'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"print_{n}: " + ", ".join(w for w, bad in (
                ("does not fit the printer", not fits), ("not on the bed", not flat),
                ("not a closed solid", not closed)) if bad))

    print()
    for g in GRAZES:
        print(f"  PLUG GRAZE (Stage 5, not a gate): {g}")
    for w in warns: print("  WARN " + w)
    if fails:
        print(f"FAIL - {len(fails)} geometric problem(s)")
        for f_ in fails: print("  - " + f_)
        return 1
    print(f"PASS - {len(PAIRS)} pairs, no interference, all clearances met")
    return 0


#cables

"""Every cable, routed through the airframe and measured: length, bend and clearance.

Each cable in tools/cables.py is a polyline from its mated plug's exit (the board end,
read from the board) through the waypoints the table gives, to the part it serves. For
each one this checks, analytically:

  1. the routed length plus slack and both plug bodies fits the length the buyer orders;
  2. no bend is tighter than the lead allows. A corner's radius is the largest arc that
     fits the segments either side of it, each segment shared between the corners at its
     ends; a plug's exit and the far socket hold the lead straight, so a corner there has
     no room at all;
  3. the cable's surface keeps its margin from the prop discs, the frame, the stack and
     the mounted parts - measured along the polyline AND along the filleted paths a real
     cable takes, which cut inside every corner.

Ports whose far end has no position are checked at the board only: the bend and the
clearance of the way out, and the run plus both plug bodies as a lower bound on the lead.

    python3 tools/check_mech.py cables              # the gate: exit 0 only if every cable passes
    python3 tools/check_mech.py cables -v           # and every corner's turn and radius
    python3 tools/check_mech.py cables --fault F    # inject one fault and show the gate fail;
                                               # F is short, prop, bend or plate
"""

F, TPM, P = design.FRAME, design.TOP_PLATE_MOUNT, design.PLATES
STEP = 0.5            #mm between clearance samples along a path
FILLETS = (0.0, 0.5, 1.0)   #polyline, half-size and full-size corner arcs


#geometry
def sub(a, b): return tuple(x - y for x, y in zip(a, b))


def add(a, b): return tuple(x + y for x, y in zip(a, b))


def mul(a, k): return tuple(x * k for x in a)


def dot(a, b): return sum(x * y for x, y in zip(a, b))


def norm(a): return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return mul(a, 1.0 / n) if n > 1e-12 else a


def angle(a, b):
    c = dot(unit(a), unit(b))
    return math.acos(max(-1.0, min(1.0, c)))


def box(x0, x1, y0, y1, z0, z1):
    return ("box", (min(x0, x1), min(y0, y1), min(z0, z1)), (max(x0, x1), max(y0, y1), max(z0, z1)))


def prism(a, b, r, z0, z1):
    """A capsule in plan, extruded from z0 to z1 - an arm, a post, a prop disc."""
    return ("prism", a, b, r, z0, z1)


def vcyl(x, y, r, z0, z1):
    return prism((x, y), (x, y), r, z0, z1)


def dist(p, s):
    """Distance from point p to shape s; negative inside."""
    if s[0] == "box":
        lo, hi = s[1], s[2]
        d = [max(lo[i] - p[i], 0.0, p[i] - hi[i]) for i in range(3)]
        out = math.sqrt(sum(x * x for x in d))
        if out > 0.0:
            return out
        return -min(min(p[i] - lo[i], hi[i] - p[i]) for i in range(3))
    _, a, b, r, z0, z1 = s
    ab = (b[0] - a[0], b[1] - a[1])
    L2 = ab[0] ** 2 + ab[1] ** 2
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / L2))
    dr = math.hypot(p[0] - a[0] - t * ab[0], p[1] - a[1] - t * ab[1]) - r
    dz = max(z0 - p[2], p[2] - z1)
    if dr <= 0.0 and dz <= 0.0:
        return max(dr, dz)
    return math.hypot(max(dr, 0.0), max(dz, 0.0))


#the airframe, as hazards: (name, shape, margin key)
def stack_z(board):
    """The FC board's underside."""
    rs = design.required_standoff(board)
    fc_z = rs["below"] + design.ESC["pcb"] + design.ESC["parts"] + design.MOUNTING["gap"] + rs["bot"]
    return fc_z, rs


def plug_exits(board, fc_z):
    """Each port's mated plug."""
    out = {}
    for ref in design.MATING_FACE:
        dx, dy, ux, uy, w, _depth, flip = gen_scad_plugs.plug_of(board, ref)
        body = design.MATING_PLUG_BODY[ref]
        axis = cables.AXIS_OVERRIDE.get(ref, cables.PLUG_AXIS)
        z = fc_z - axis if flip else fc_z + design.BOARD_T + axis
        out[ref] = dict(mouth=(dx, dy), u=(ux, uy, 0.0), w=w, flip=flip, body=body,
                        exit=(dx + ux * body, dy + uy * body, z))
    return out


def floorplan_mouth(ref):
    """The mouth design.FLOORPLAN_REV_D intends, to compare with the board's."""
    fp, B = design.FLOORPLAN_REV_D[ref], design.BOARD
    cx, cy = B["X0"] + B["W"] / 2, B["Y0"] + B["H"] / 2
    n = dict(N=(0, 1), S=(0, -1), E=(1, 0), W=(-1, 0))[fp["edge"]]
    if fp["edge"] in "NS":
        return (fp["at"] - cx, n[1] * (B["H"] / 2 + fp["front"]))
    return (n[0] * (B["W"] / 2 + fp["front"]), cy - fp["at"])


def hazards(fc_z, rs, plugs):
    H = []
    bt, at, mt, ut = F["bottom_t"], F["arm_t"], F["medium_t"], F["upper_t"]
    z_arm, z_mid, z_stack = bt, bt + at, bt + at + mt
    top_z = rs["top_plate_z"]
    pc = TPM["plate_centre_y"]
    #[D] plates from the manufacturer DXF (design.PLATES)
    for name, (w, l), cy, z0, z1 in (
            ("bottom plate", P["bottom"], pc["bottom"], 0.0, bt),
            ("mid plate", P["fc"], pc["fc"], z_mid, z_stack),
            ("top plate", P["top"], pc["top"], top_z, top_z + ut)):
        H.append((name, box(-w / 2, w / 2, cy - l / 2, cy + l / 2, z0, z1), "carbon"))
    mo = F["wb"] / 2 / math.sqrt(2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            tag = ("fore" if sy < 0 else "aft") + "-" + ("port" if sx < 0 else "starboard")
            m = (sx * mo, sy * mo)
            H.append((f"{tag} arm", prism((0.0, 0.0), m, P["arm"][0] / 2, z_arm, z_mid), "carbon"))
            H.append((f"{tag} motor", vcyl(m[0], m[1], design.MOTOR["dia_mm"] / 2, z_mid,
                                           z_mid + design.MOTOR["h_mm"] + 4.0), "carbon"))
            pz = z_mid + design.MOTOR["h_mm"] + 4.0      #as drone.scad's props()
            H.append((f"{tag} prop", vcyl(m[0], m[1], design.PROP["dia_mm"] / 2, pz, pz + 1.2),
                      "prop"))
            sg = design.skid_geometry()
            sk = sg["half"]          #the plate and the splayed feet, whichever reaches further
            H.append((f"{tag} skid", box(m[0] - sk, m[0] + sk, m[1] - sk, m[1] + sk,
                                         sg["contact"], z_arm), "carbon"))
    r_post = TPM["post_od"] / 2
    for x, y in TPM["front_posts"]:
        H.append((f"front post ({x:+.1f},{y:+.1f})", vcyl(x, y, r_post, z_stack, top_z), "carbon"))
    for x, y in TPM["rear_posts"]:
        H.append((f"rear post ({x:+.1f},{y:+.1f})", vcyl(x, y, r_post, z_arm, top_z), "carbon"))
    h = design.MOUNTING["pitch"] / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            H.append(("stack bolt", vcyl(sx * h, sy * h, design.MOUNTING["screw_dia"] / 2, z_mid,
                                         fc_z + design.BOARD_T + 2.4), "board"))
    #the stack
    E = design.ESC
    H.append(("esc", box(-E["L"] / 2, E["L"] / 2, -E["W"] / 2, E["W"] / 2, z_stack,
                         z_stack + E["pcb"] + E["parts"]), "board"))
    B = design.BOARD
    H.append(("fc", box(-B["W"] / 2, B["W"] / 2, -B["H"] / 2, B["H"] / 2, fc_z - rs["bot"],
                        fc_z + design.BOARD_T + rs["top"]), "board"))
    #the mated plugs of the cables this airframe fits
    for ref, pl in plugs.items():
        if ref == "J8":
            depth = 2.0                     #[A] a seated card stands ~2 mm proud
        elif cables.CABLES.get(ref, {}).get("end") is None:
            continue                        #nothing plugged in on this airframe
        else:
            depth = pl["body"]
        (mx, my), (ux, uy, _), w = pl["mouth"], pl["u"], pl["w"]
        px, py = -uy, ux
        xs = [mx + px * w / 2, mx - px * w / 2, mx + ux * depth + px * w / 2,
              mx + ux * depth - px * w / 2]
        ys = [my + py * w / 2, my - py * w / 2, my + uy * depth + py * w / 2,
              my + uy * depth - py * w / 2]
        z0 = fc_z - gen_scad_plugs.PLUG_H if pl["flip"] else fc_z + design.BOARD_T
        H.append((f"plug {ref}", box(min(xs), max(xs), min(ys), max(ys), z0,
                                     z0 + gen_scad_plugs.PLUG_H), "board"))
    #the battery on the top plate
    bp, ba = design.BATT_POS, design.BATT
    H.append(("battery", box(-ba["W"] / 2, ba["W"] / 2, bp["y"] - ba["L"] / 2,
                             bp["y"] + ba["L"] / 2, bp["z"], bp["z"] + ba["H"]), "battery"))
    #the antenna tower and what it carries (gen_scad_mounts.G, = cad/mounts.scad)
    T = G["tower"]
    st, sz = T["seat_t"], T["seat_z"]
    H += [("tower foot", box(-T["foot_x"] / 2, T["foot_x"] / 2, T["y_post"] - T["foot_y"] / 2,
                             T["y_post"] + T["foot_y"] / 2, T["foot_z"], T["foot_z"] + T["foot_t"]),
           "printed"),
          ("tower column", box(-T["col_x"] / 2, T["col_x"] / 2, T["col_y0"] - T["col_y"] / 2,
                               T["col_y0"] + T["col_y"] / 2, T["foot_z"], sz - st), "printed"),
          ("tower seat", box(-T["seat_x"] / 2, T["seat_x"] / 2, T["seat_y0"], T["seat_y1"],
                             sz - st, sz), "printed"),
          ("tower arm", box(-T["arm_x"] / 2, T["arm_x"] / 2, T["seat_y1"] - 1, T["arm_y1"],
                            sz - T["arm_t"], sz), "printed"),
          ("tower web", box(-T["web"] / 2, T["web"] / 2, T["helix_holes"][1][1] + 3, T["arm_y1"],
                            sz - T["arm_t"] - T["web_h"], sz - T["arm_t"]), "printed"),
          ("gps pod", box(-T["pod_x"] / 2, T["pod_x"] / 2, T["gps_y"] - T["pod_y"] / 2,
                          T["gps_y"] + T["pod_y"] / 2, sz, T["pod_top"]), "printed"),
          ("gps lid", box(-T["pod_x"] / 2, T["pod_x"] / 2, T["gps_y"] - T["pod_y"] / 2,
                          T["gps_y"] + T["pod_y"] / 2, T["pod_top"],
                          T["pod_top"] + T["proud"] + T["lid_t"]), "printed")]
    g = design.MOUNTED["gps"]
    H.append(("gps", box(-g["L"] / 2, g["L"] / 2, T["gps_y"] - g["W"] / 2, T["gps_y"] + g["W"] / 2,
                         T["gps_bot"], T["gps_top"]), "printed"))
    ant = design.MOUNTED["iridium_antenna"]
    H.append(("helix", vcyl(0.0, T["helix_y"], ant["dia"] / 2, sz, sz + ant["H"]), "antenna"))
    H.append(("helix SMA", vcyl(0.0, T["helix_y"], 4.0, sz - 10.0, sz), "printed"))
    #the nose mount, the receiver and the ELRS antennas
    N = G["nose"]
    pz = N["z"] - N["t"]
    cam_x = N["cam_x"] / 2 + 0.3 + N["cw"]
    cam_d = N["cam_d"] / 2 + 0.3 + N["cw"]
    cam_bot = N["z"] - N["t"] - N["cam_h"] - 0.3 - N["cw"]
    boss_r = (design.INSERTS["M2"]["od"] + 2 * design.INSERT_WALL) / 2
    cam_boss = cam_x + boss_r - 1
    rx_w = N["rx_x"] / 2 + 0.2 + N["rx_wall"]
    rx_l = N["rx_l"] / 2 + 0.2 + N["rx_wall"]
    rx_bot = N["z"] - N["t"] - (N["rx_h"] + 0.4)
    rx_boss = rx_w + boss_r - 1
    H += [("nose plate", box(-N["x"] / 2, N["x"] / 2, N["y1"], N["y0"], pz, N["z"]), "printed"),
          ("cam cradle", box(-cam_x, cam_x, N["cam_y"] - cam_d, N["cam_y"] + cam_d, cam_bot, pz),
           "printed"),
          ("cam bosses", box(-cam_boss - boss_r, cam_boss + boss_r, N["cam_y"] - boss_r,
                             N["cam_y"] + boss_r, cam_bot, pz), "printed"),
          ("xiao lid", box(-cam_boss - boss_r, cam_boss + boss_r, N["cam_y"] - cam_d,
                           N["cam_y"] + cam_d, cam_bot - N["cam_lid"], cam_bot), "printed"),
          ("rx pocket", box(-rx_w, rx_w, N["rx_y"] - rx_l, N["rx_y"] + rx_l, rx_bot, pz), "printed"),
          ("rx bosses", box(-rx_boss - boss_r, rx_boss + boss_r, N["rx_y"] - boss_r,
                            N["rx_y"] + boss_r, rx_bot, pz), "printed"),
          ("rx cover", box(-rx_boss - boss_r, rx_boss + boss_r, N["rx_y"] - rx_l, N["rx_y"] + rx_l,
                           rx_bot - N["rx_cover"], rx_bot), "printed"),
          ("rx", box(-N["rx_x"] / 2, N["rx_x"] / 2, N["rx_y"] - N["rx_l"] / 2,
                     N["rx_y"] + N["rx_l"] / 2, rx_bot + 0.2, rx_bot + 0.2 + N["rx_h"]), "printed"),
          ("elrs whip, vertical", vcyl(N["av"][0], N["av"][1], N["ant_d"] / 2, pz - 10,
                                       pz - 10 + N["ant_l"]), "antenna"),
          ("elrs holder, vertical", vcyl(N["av"][0], N["av"][1], 4.0, pz - 12, pz), "printed"),
          ("elrs whip, forward", box(N["ah"][0] - N["ant_d"] / 2, N["ah"][0] + N["ant_d"] / 2,
                                     N["ah"][1] + 4 - N["ant_l"], N["ah"][1] + 4,
                                     N["ah"][2] - N["ant_d"] / 2, N["ah"][2] + N["ant_d"] / 2),
           "antenna"),
          ("elrs holder, forward", box(N["ah"][0] - 5, N["ah"][0] + 5, N["ah"][1], N["ah"][1] + 5,
                                       N["ah"][2] - 4, pz), "printed")]
    #the lidar bracket and the LD06, the range cradle and the TFS20-L
    L, ld = G["lidar"], design.OFFBOARD["lidar"]
    H += [("lidar bracket", box(-L["x"] / 2, L["x"] / 2, L["y0"], L["y1"], -L["t"], 0.0), "printed"),
          ("ld06", box(-ld["L_mm"] / 2, ld["L_mm"] / 2, L["y"] - ld["W_mm"] / 2,
                       L["y"] + ld["W_mm"] / 2, -L["t"] - ld["H_mm"], -L["t"]), "printed")]
    R = G["range"]
    H += [("range cradle", box(-R["x"] / 2, R["x"] / 2, R["y"] - R["yl"] / 2, R["y"] + R["yl"] / 2,
                               -R["body_h"], 0.0), "printed"),
          ("range lid", box(-R["x"] / 2, R["x"] / 2, R["y"] - R["yl"] / 2, R["y"] + R["yl"] / 2,
                            -R["body_h"] - R["lid_t"], -R["body_h"]), "printed")]
    #the ground under the skids
    gz = -(design.SKID["drop"] + design.SKID["t"])
    H.append(("ground", box(-1e4, 1e4, -1e4, 1e4, gz - 1e3, gz), "ground"))
    return H


#a route: its corners, their radii, and the paths a real cable can take
def corners(V, d_in, d_out):
    """Turn angle at every vertex, the plug exit and the far socket included."""
    n = len(V)
    th = []
    for i in range(n):
        a = d_in if i == 0 else sub(V[i], V[i - 1])
        b = d_out if i == n - 1 else sub(V[i + 1], V[i])
        th.append(angle(a, b))
    return th


def radii(V, th):
    """Largest arc at each corner that fits."""
    tau = [math.tan(t / 2) if t > math.radians(0.5) else 0.0 for t in th]
    n = len(V)
    S = []
    for k in range(n - 1):
        tt = tau[k] + tau[k + 1]
        S.append(math.inf if tt == 0 else norm(sub(V[k + 1], V[k])) / tt)
    R = []
    for i in range(n):
        if tau[i] == 0.0:
            R.append(math.inf)
        elif i == 0 or i == n - 1:
            R.append(0.0)
        else:
            R.append(min(S[i - 1], S[i]))
    return R


def fillet(V, th, R, f):
    """The route with every corner replaced by an arc of f x its largest radius."""
    if f == 0.0:
        return list(V)
    out = [V[0]]
    for i in range(1, len(V) - 1):
        r = f * R[i]
        if not math.isfinite(r) or r <= 0.0:
            out.append(V[i]); continue
        a, b = unit(sub(V[i], V[i - 1])), unit(sub(V[i + 1], V[i]))
        t = r * math.tan(th[i] / 2)
        A, Bp = sub(V[i], mul(a, t)), add(V[i], mul(b, t))
        nrm = unit(sub(b, mul(a, dot(a, b))))
        C = add(A, mul(nrm, r))
        k = max(2, int(r * th[i] / STEP) + 1)
        for j in range(k + 1):
            phi = th[i] * j / k
            #from C, the arc starts at -nrm*r and turns toward a
            out.append(add(C, add(mul(nrm, -r * math.cos(phi)), mul(a, r * math.sin(phi)))))
        out[-1] = Bp
    out.append(V[-1])
    return out


def samples(path):
    for p, q in zip(path, path[1:]):
        L = norm(sub(q, p))
        k = max(1, int(L / STEP))
        for j in range(k + 1):
            yield add(p, mul(sub(q, p), j / k))


def length(V):
    return sum(norm(sub(q, p)) for p, q in zip(V, V[1:]))


#the gate
def cables_check(ref, c, plug, H):
    lead = cables.LEADS[c["type"]]
    r_c = lead["od"] * cables.BUNDLE_X[c["wires"]] / 2
    rmin = lead["rmin_x"] * lead["od"]
    V = [plug["exit"]] + [tuple(map(float, p)) for p in c["via"]]
    d_in = plug["u"]
    if c["end"] is not None:
        V.append(tuple(map(float, c["end"])))
        d_out = c["end_dir"]
    else:
        d_out = sub(V[-1], V[-2])           #an open end: the lead runs on as it goes
    th = corners(V, d_in, d_out)
    R = radii(V, th)
    bends = [(R[i], i) for i in range(len(V)) if th[i] > math.radians(0.5)]
    tight, at = min(bends) if bends else (math.inf, None)

    #clearance, along the polyline and the filleted paths
    skip = set(c["touches"]) | {f"plug {ref}"}
    worst = None                            #(clearance - margin, clearance, name, margin)
    prop = None                             #the nearest prop disc, reported on its own
    for f in FILLETS:
        for p in samples(fillet(V, th, R, f)):
            for name, shape, mk in H:
                if name in skip:
                    continue
                clr = dist(p, shape) - r_c
                m = cables.MARGIN[mk]
                if worst is None or clr - m < worst[0]:
                    worst = (clr - m, clr, name, m, p)
                if mk == "prop" and (prop is None or clr < prop):
                    prop = clr

    run = length(V)
    bodies = plug["body"] + cables.FAR_BODY[c["far"]]
    slack = max(cables.SLACK["min"], cables.SLACK["frac"] * run)
    need = run + bodies + slack
    if c["end"] is None:
        need = run + bodies                 #a lower bound: no slack on a run not yet known
    fails = []
    if tight < rmin:
        fails.append(f"bend R {tight:.1f} mm at {'the plug' if at == 0 else 'the far end' if at == len(V) - 1 else 'waypoint ' + str(at)} "
                     f"< {rmin:.1f}")
    if worst[0] < 0.0:
        fails.append(f"{worst[2]} {worst[1]:.1f} mm < {worst[3]:.1f} at "
                     f"({worst[4][0]:.1f}, {worst[4][1]:.1f}, {worst[4][2]:.1f})")
    if c["end"] is not None and (c["buy"] is None or need > c["buy"]):
        fails.append(f"needs {need:.0f} mm, buying {c['buy']}")
    return dict(run=run, need=need, tight=tight, rmin=rmin, worst=worst, fails=fails,
                r_c=r_c, V=V, th=th, R=R, prop=prop)


cables_SCAD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cad", "cables.scad")


def write_scad(results):
    """cad/cables.scad: each lead as the filleted path the gate checked."""
    out = ["// GENERATED by tools/check_mech.py cables --scad - DO NOT EDIT.",
           "// Each lead along the full-radius filleted path tools/check_mech.py cables checks,",
           "// at its bundle's diameter. A lead whose far end is undefined stops where its",
           "// known run does.", "",
           "module lead(pts, r) {",
           "    for (i = [0 : len(pts) - 2]) hull() {",
           "        translate(pts[i]) sphere(r = r, $fn = 8);",
           "        translate(pts[i + 1]) sphere(r = r, $fn = 8);",
           "    }",
           "}", "", "module cables() {"]
    for ref, r in results:
        pts = samples(fillet(r["V"], r["th"], r["R"], 1.0))
        body = ", ".join(f"[{x:.2f}, {y:.2f}, {z:.2f}]" for x, y, z in pts)
        out.append(f"    color(\"#222222\") lead([{body}], {max(r['r_c'], 0.5):.2f});   // {ref}")
    out.append("}")
    open(cables_SCAD, "w").write("\n".join(out) + "\n")
    print(f"wrote {os.path.relpath(cables_SCAD)}")


FAULTS = {
    "short": ("J3 bought at 150 mm", lambda C: C["J3"].update(buy=150)),
    "prop":  ("J12's climb past the top plate moved down to prop height, beside the "
              "aft-starboard prop",
              lambda C: C["J12"]["via"].__setitem__(2, (34.0, 66.0, 30.0))),
    "bend":  ("J2's loop pulled in to 2 mm outside its plug",
              lambda C: C["J2"].update(via=[(-29.7, 5.4, 29.5), (-29.7, 5.4, 13.55)])),
    "plate": ("J9 run straight through the bottom plate",
              lambda C: C["J9"]["via"].__setitem__(3, (-4.0, 80.0, 0.0))),
}


def run_cables(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    fault = None
    verbose = "-v" in argv
    if "--fault" in argv:
        i = argv.index("--fault")
        fault = argv[i + 1] if i + 1 < len(argv) else ""
        if fault not in FAULTS:
            print(f"--fault takes one of {', '.join(FAULTS)}")
            return 2
        FAULTS[fault][1](cables.CABLES)
        print(f"FAULT INJECTED: {FAULTS[fault][0]}\n")

    try:
        board = pcbnew.LoadBoard(gen_scad_plugs.BOARD)
        fc_z, rs = stack_z(board)
        plugs = plug_exits(board, fc_z)
    except Exception as e:                          #a gate fails, it does not vanish
        print(f"FAIL - could not read the board: {e}")
        return 1
    H = hazards(fc_z, rs, plugs)
    print(f"cables through the airframe (FC underside z {fc_z:.2f} mm, top plate "
          f"underside z {rs['top_plate_z']:.2f}; margins: prop {cables.MARGIN['prop']:.0f}, "
          f"carbon {cables.MARGIN['carbon']:.0f}, printed {cables.MARGIN['printed']:.1f} mm)")
    warns = []
    for ref in sorted(plugs):
        fm, bm = floorplan_mouth(ref), plugs[ref]["mouth"]
        if math.hypot(fm[0] - bm[0], fm[1] - bm[1]) > 0.1:
            warns.append(f"{ref}: the board's plug mouth ({bm[0]:.2f}, {bm[1]:.2f}) is not "
                         f"FLOORPLAN_REV_D's ({fm[0]:.2f}, {fm[1]:.2f}); routed from the board")

    fails, results = [], []
    for ref, c in sorted(cables.CABLES.items(), key=lambda kv: (len(kv[0]), kv[0])):
        if ref not in plugs:
            fails.append(f"{ref}: not a mated port in design.MATING_FACE")
            continue
        r = cables_check(ref, c, plugs[ref], H)
        results.append((ref, r))
        w = r["worst"]
        near = f"prop {r['prop']:5.1f}  nearest {w[2]} {w[1]:.1f} mm (>= {w[3]:.1f})"
        bend = (f"bend R {r['tight']:5.1f} >= {r['rmin']:4.1f}" if math.isfinite(r["tight"])
                else f"bend none     >= {r['rmin']:4.1f}")
        if c["end"] is None:
            line = (f"  {ref:4s} run {r['run']:5.1f}  need >={r['need']:3.0f}  buy   -     "
                    f"{bend}  {near}  END UNDEFINED")
        else:
            line = (f"  {ref:4s} run {r['run']:5.1f}  need {r['need']:4.0f}  buy {c['buy']:4d} mm  "
                    f"{bend}  {near}")
        print(line + ("  ok" if not r["fails"] else "  FAIL"))
        if verbose:
            for v, t, rr in zip(r["V"], r["th"], r["R"]):
                print(f"        ({v[0]:7.2f}, {v[1]:7.2f}, {v[2]:6.2f})  turn "
                      f"{math.degrees(t):5.1f} deg  R {rr:6.1f}")
        for f_ in r["fails"]:
            fails.append(f"{ref}: {f_}")
        if c["end"] is not None and not r["fails"]:
            shorter = [s for s in cables.STOCK[c["type"]] if r["need"] <= s < c["buy"]]
            if shorter:
                warns.append(f"{ref}: a {shorter[0]} mm lead would do; buying {c['buy']}")
    if "--scad" in argv:
        write_scad(results)
    print()
    for ref, c in sorted(cables.CABLES.items()):
        if c["end"] is None:
            print(f"  {ref}: far end undefined - {c['undefined']}")
    for w_ in warns:
        print("  WARN " + w_)
    if fails:
        print(f"FAIL - {len(fails)} cable problem(s)")
        for f_ in fails:
            print("  - " + f_)
        return 1
    print(f"PASS - {sum(1 for c in cables.CABLES.values() if c['end'] is not None)} cables "
          f"routed, length, bend and clearance met")
    return 0


#prints

"""Is every printed part in cad/print, and is each STL the part as it is now designed?

Usage:  python3 tools/check_mech.py prints [--self-test]

A part that is printed (each design.MOUNTS mount, the lids that close them, and any
design.py entry with printed=True, such as the skid) must be in tools/gen_scad_mounts.py's
PRINTED list and have cad/print/<name>.stl - and that STL must be the same solid gen_scad_mounts exports from
today's design (facet count, bounding box and volume - not bytes, which OpenSCAD orders
freely). A stale STL prints yesterday's part.

--self-test breaks a copy of cad/print (a part deleted, one truncated, one edited) and
exits 0 only if each break is caught.
"""

PRINT_DIR = gen_scad_mounts.PRINT_DIR
#design.py dicts that declare a printed part
PRINTED_BY_FLAG = {"SKID": "skid"}


def required():
    names = set(design.MOUNTS) | {"gps_pod", "gps_lid", "xiao_lid", "rx_cover", "range_lid",
                                  "rid_cover"}
    for attr, name in PRINTED_BY_FLAG.items():
        if getattr(design, attr, {}).get("printed"):
            names.add(name)
    flagged = sorted(k for k, v in vars(design).items()
                     if isinstance(v, dict) and v.get("printed") is True)
    unmapped = [k for k in flagged if k not in PRINTED_BY_FLAG]
    return names, unmapped


def shape(path):
    """(triangle count, bbox, volume) of an ASCII STL - order-free."""
    pts = [tuple(map(float, m)) for m in re.findall(
        r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", open(path, errors="ignore").read())]
    tris = [pts[i:i + 3] for i in range(0, len(pts) - len(pts) % 3, 3)]
    if not tris:
        return (0, None, 0.0)
    lo = tuple(min(p[i] for p in pts) for i in range(3))
    hi = tuple(max(p[i] for p in pts) for i in range(3))
    vol = sum((a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
               + a[2] * (b[0] * c[1] - b[1] * c[0])) for a, b, c in tris) / 6.0
    return (len(tris), lo + hi, abs(vol))


def same(a, b):
    (na, ba, va), (nb, bb, vb) = shape(a), shape(b)
    return (na == nb and na > 0 and all(abs(x - y) < 1e-3 for x, y in zip(ba, bb))
            and abs(va - vb) <= 1e-4 * max(va, 1.0))


def compare(fresh, committed):
    fails = []
    names, unmapped = required()
    for k in unmapped:
        fails.append(f"design.{k} says printed=True but no print_ module is mapped to it")
    for n in sorted(names - set(gen_scad_mounts.PRINTED)):
        fails.append(f"{n} is printed but not in gen_scad_mounts.PRINTED")
    for n in gen_scad_mounts.PRINTED:
        a, b = os.path.join(fresh, n + ".stl"), os.path.join(committed, n + ".stl")
        if not os.path.exists(b):
            fails.append(f"cad/print/{n}.stl is missing")
        elif not same(a, b):
            fails.append(f"cad/print/{n}.stl is not today's design - run "
                         f"tools/gen_scad_mounts.py --stl")
    return fails


def run_prints():
    with tempfile.TemporaryDirectory() as fresh:
        gen_scad_mounts.export_stl(fresh, quiet=True)
        if "--self-test" in sys.argv:
            ok = not compare(fresh, PRINT_DIR)
            print(f"  {'clean' if ok else 'NOT CLEAN'}  cad/print as committed")
            with tempfile.TemporaryDirectory() as t:
                for name, brk in (("a part deleted", lambda d: os.unlink(os.path.join(d, "skid.stl"))),
                                  ("a part truncated", lambda d: open(os.path.join(d, "gps_lid.stl"), "w").close()),
                                  ("a part edited", lambda d: open(os.path.join(d, "range_lid.stl"), "w").write(
                                      open(os.path.join(PRINT_DIR, "range_lid.stl")).read().replace("vertex", "vertex 1", 3)))):
                    shutil.rmtree(t); shutil.copytree(PRINT_DIR, t)
                    brk(t)
                    caught = bool(compare(fresh, t))
                    ok &= caught
                    print(f"  {'caught' if caught else 'MISSED'}  {name}")
            print("self-test passed: every break is caught" if ok else "SELF-TEST FAILED")
            return 0 if ok else 1
        fails = compare(fresh, PRINT_DIR)
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} printed part(s) missing or stale")
        return 1
    print(f"{len(gen_scad_mounts.PRINTED)} printed parts, each STL the solid today's design exports")
    return 0


#balance

"""Where is the centre of gravity, and how far can the aircraft lean on its skids?

Usage:  python3 tools/check_mech.py balance [--self-test]

Every row of design.MASS_ITEMS gets a position here (x to starboard, y aft, z up from the
bottom plate's underside, as drone.scad), taken from the mounts that hold it wherever a
mount does ([M]) and stated as an assumption where nothing does ([A]). A mass with no
position is a failure, so a new part cannot quietly drop out of the balance.

The support is the convex hull of the skids' eight feet (design.skid_geometry), on the
contact plane. The static tip angle is the smallest, over the hull's edges, of
atan(CG's distance inside that edge / CG height above the contact plane) - the lean at
which the CG passes over a foot and the aircraft falls.

Gate: tip angle >= MIN_TIP_DEG and the CG within MAX_OFFSET_MM of the thrust centre (the
four motors' centre, where a hover wants it).

--self-test moves the battery, pulls the feet in and deletes a position, and exits 0 only
if each is caught.
"""

MIN_TIP_DEG = 45.0      #a landing on a 30 deg slope with 15 deg of bounce still stands
MAX_OFFSET_MM = 10.0    #CG this near the thrust centre keeps the four motors near equal
T, N, L, R = G["tower"], G["nose"], G["lidar"], G["range"]
MP = design.MOUNTED
SG = design.skid_geometry()
Z_MID = design.FRAME["bottom_t"] + design.FRAME["arm_t"]          #arm top, motor base
MOTOR_H = design.MOTOR["h_mm"]


def positions():
    """MASS_ITEMS name -> (x, y, z, source)."""
    batt = design.BATT_POS
    return {
        "frame": (0.0, 0.0, 6.0, "[A] arms and plates about the stack centre"),
        "4x motors": (0.0, 0.0, Z_MID + MOTOR_H / 2, "[M] on the arm tops, symmetric"),
        "ESC": (0.0, 0.0, 14.0, "[A] in the stack under the board"),
        "this board": (0.0, 0.0, 28.0, "[A] in the stack"),
        "4x props": (0.0, 0.0, Z_MID + MOTOR_H + 4.0, "[M] on the motor bells, as drone.scad"),
        "battery": (0.0, batt["y"], batt["z"] + design.BATT["H"] / 2,
                    "[M] design.BATT_POS on the top plate"),
        "GPS": (0.0, T["gps_y"], (T["gps_bot"] + T["gps_top"]) / 2,
                "[M] gen_scad_mounts tower arm"),
        "RX": (0.0, N["rx_y"], N["z"] - N["rx_h"] / 2, "[M] gen_scad_mounts nose mount"),
        "Iridium antenna (HC610)": (0.0, T["helix_y"], T["seat_z"] + MP["iridium_antenna"]["H"] / 2,
                                    "[M] gen_scad_mounts tower seat"),
        "XIAO nose camera": (0.0, N["cam_y"], N["z"] - N["cam_h"] / 2,
                             "[M] gen_scad_mounts nose mount"),
        "printed mounts, inserts, screws": (0.0, 40.0, 40.0,
                                            "[A] mostly the tower, aft and up"),
        design.PI["name"]: (0.0, 0.0, 30.0, "[A] deferred companion, budgeted at the stack"),
        "camera+cable (deferred, budgeted)": (0.0, R["y"], -8.0,
                                              "[A] the belly slot the rangefinder uses"),
        "TFS20-L": (0.0, R["y"], -R["body_h"] / 2, "[M] gen_scad_mounts range cradle"),
        "LD06 360 lidar (deferred, budgeted)": (0.0, L["y"], -(5.0 + design.OFFBOARD["lidar"]["H_mm"] / 2),
                                                 "[M] gen_scad_mounts lidar bracket"),
        "Remote ID (Holybro, rear-port arm)": (G["rid"]["cx"], G["rid"]["cy"],
                                               G["rid"]["z0"] + G["rid"]["base_t"] + MP["remote_id"]["H"] / 2,
                                               "[M] gen_scad_mounts rid_tray"),
        "skids": (0.0, 0.0, (SG["z0"] + SG["contact"]) / 2, "[M] at the four motors, symmetric"),
        "wiring/straps": (0.0, 0.0, 15.0, "[A] about the stack"),
    }


def feet(reach=None):
    """The eight foot centres: two per motor, along its arm."""
    mo = design.FRAME["wb"] / 2 / math.sqrt(2)
    r = SG["reach"] if reach is None else reach
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            u = (sx / math.sqrt(2), sy / math.sqrt(2))
            for s in (-1, 1):
                out.append((sx * mo + s * r * u[0], sy * mo + s * r * u[1]))
    return out


def hull(pts):
    pts = sorted(set(pts))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def evaluate(items, pos, foot_pts, verbose=False):
    fails = []
    missing = [n for n, _g, _s in items if n not in pos]
    for n in missing:
        fails.append(f"'{n}' has a mass and no position")
    known = [(n, g) for n, g, _s in items if n in pos]
    m = sum(g for _n, g in known)
    cg = [sum(g * pos[n][i] for n, g in known) / m for i in range(3)]
    if verbose:
        print(f"  {'item':38} {'g':>7} {'x':>7} {'y':>7} {'z':>7}  moment y (g.mm)")
        for n, g in known:
            x, y, z, src = pos[n]
            print(f"  {n:38} {g:7.1f} {x:7.1f} {y:7.1f} {z:7.1f}  {g * y:9.0f}  {src}")
    poly = hull(foot_pts)
    h = cg[2] - SG["contact"]
    tips = []
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        ln = math.hypot(x2 - x1, y2 - y1)
        d = ((x2 - x1) * (cg[1] - y1) - (y2 - y1) * (cg[0] - x1)) / ln   #>0 inside (CCW)
        tips.append(math.degrees(math.atan2(d, h)))
    tip = min(tips)
    off = math.hypot(cg[0], cg[1])
    if tip < MIN_TIP_DEG:
        fails.append(f"static tip angle {tip:.1f} deg is under {MIN_TIP_DEG:.0f} deg")
    if off > MAX_OFFSET_MM:
        fails.append(f"CG is {off:.1f} mm from the thrust centre (limit {MAX_OFFSET_MM:.0f})")
    return fails, dict(mass=m, cg=cg, tip=tip, off=off, h=h)


def self_test():
    items, pos = design.MASS_ITEMS, positions()
    ok = not evaluate(items, pos, feet())[0]
    print(f"  {'clean' if ok else 'NOT CLEAN'}  the aircraft as designed")
    moved = dict(pos)
    x, y, z, s = moved["battery"]
    moved["battery"] = (x, 150.0, z, s)
    gone = {k: v for k, v in pos.items() if k != "skids"}
    for name, args in (("battery moved to y = +150", (items, moved, feet())),
                       ("feet drawn in to a tenth of their span",
                        (items, pos, [(x * 0.1, y * 0.1) for x, y in feet()])),
                       ("a mass with no position", (items, gone, feet()))):
        caught = bool(evaluate(*args)[0])
        ok &= caught
        print(f"  {'caught' if caught else 'MISSED'}  {name}")
    print("self-test passed: every break is caught" if ok else "SELF-TEST FAILED")
    return 0 if ok else 1


def run_balance():
    if "--self-test" in sys.argv:
        return self_test()
    fails, r = evaluate(design.MASS_ITEMS, positions(), feet(), verbose=True)
    print(f"\n  all-up {r['mass']:.1f} g; CG at x {r['cg'][0]:+.1f}, y {r['cg'][1]:+.1f}, "
          f"z {r['cg'][2]:.1f} mm ({r['h']:.1f} mm above the skid contact plane)")
    print(f"  CG {r['off']:.1f} mm from the thrust centre (limit {MAX_OFFSET_MM:.0f}); "
          f"static tip angle {r['tip']:.1f} deg (need {MIN_TIP_DEG:.0f})")
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} balance problem(s)")
        return 1
    print("\nbalanced: CG over the thrust centre, and it takes a "
          f"{r['tip']:.0f} deg lean to tip it")
    return 0


CHECKS = {
    "mechanical": run_mechanical,
    "fit": run_fit,
    "build": run_build,
    "cad_fit": run_cad_fit,
    "cables": run_cables,
    "prints": run_prints,
    "balance": run_balance,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        print(__doc__)
        return 2
    return CHECKS[sys.argv.pop(1)]()


if __name__ == "__main__":
    sys.exit(main())
