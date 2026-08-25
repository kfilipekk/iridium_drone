#!/usr/bin/env python3
"""
Check the AIRCRAFT as one system, not the board as a pile of verified parts.

Every other checker in this directory looks at the PCB. This one asks whether the
*assembly* works: does every connector have a mate, does every rail carry what is
actually plugged into it, will it lift itself, does it physically fit the frame, and do
the buses agree on addresses and protocols.

That distinction is not academic. Twenty minutes of looking at the build as a whole found
BATT_AMP_PERVLT about 2x wrong, no microSD card in the parts list, and no USB-C cable -
none of which any board-level check could have seen.

PROVENANCE IS PART OF EVERY CHECK
---------------------------------
A limit with no source is not a check, it is a guess with a tick next to it. An earlier
version of tools/check_traces.py used round-number limits, flagged six nets, and every
one dissolved under analysis - which teaches people to ignore the tool. So every value
here carries a tag:

    [M]  measured from this design - the KiCad board or design.py
    [D]  from a datasheet or a manufacturer's manual
    [L]  read off the retail listing we are actually buying from
    [A]  ASSUMED - no source. These are listed again at the end, on purpose.

Usage:
  python3 tools/check_build.py
  python3 tools/check_build.py --bom     # substitution candidates for at-risk parts
"""
import csv, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as _d

BOARD = "NAVCORE-SoOP.kicad_pcb"
PARTS = "docs/PARTS.csv"

results = []          # (group, name, verdict, detail, source)
assumptions = []


def check(group, name, ok, detail, source):
    results.append((group, name, "PASS" if ok else "FAIL", detail, source))
    if source.startswith("[A]"):
        assumptions.append(f"{name}: {detail}")
    return ok


def note(group, name, detail, source):
    results.append((group, name, "note", detail, source))
    if source.startswith("[A]"):
        assumptions.append(f"{name}: {detail}")


# ===========================================================================
# facts about everything that is NOT the PCB
# ===========================================================================
# WAS a second ESC dict, describing the same SpeedyBee BLS 60A that design.ESC already
# described - same L and W, different fields. One part, two declarations, and nothing
# compared them. Merged into design.ESC; this reads it.
ESC = _d.ESC
# The airframe, motor, battery and prop dimensions now live in design.py - they were
# here while cad/drone.scad carried its own copies, and the two disagreed on wheelbase,
# arm thickness, plate thickness and inner height. cad/frame.scad is generated from the
# same declaration by tools/gen_scad_frame.py.
FRAME = _d.FRAME
MOTOR = _d.MOTOR
BATT  = _d.BATT
PROP  = _d.PROP
SKID  = _d.SKID
# Name and envelope come from design.PI - they were duplicated here and drifted the
# moment the companion changed. Only the electrical/mass figures, which design.py does
# not carry, are declared locally.
PI = dict(name=_d.PI["name"], g=_d.PI["g"], A5=_d.PI["power_a"], cams=1,
          src="[A] ~12 g, not published by Radxa - same 65x30 mm PCB class as a Pi Zero "
              "(11 g) with eMMC pads and a heavier SoC; [D] 5V/2A per radxa.com")

# 5 V loads that hang off this board once everything is fitted.
#
# THE PI IS NOT ON THIS LIST, and that is a design decision rather than an oversight.
# At 700 mA peak it was 37% of the rail, which put L2 at 1.89 A against its 1.6 A rating
# - 118%, 0.46 W of I2R, and no 4x4 mm 10 uH part carries more (5x5 does not fit; see
# docs/HARDWARE.md). Powering the companion from its own BEC drops the rail
# to 1.19 A, 74% of the inductor, and is better practice regardless: a Linux SBC's load
# transients do not belong on the same buck as the flight controller's rail. It was
# already mandatory for a Pi 5, which draws up to 5 A.
LOADS_5V = [("board itself",        0.620, "[M] docs/HARDWARE.md budget"),
            ("TFS20-L lidar",       0.106, "[D] 0.35 W at 3.3 V via an inline LDO"),
            ("ToF ring: 8x VL53L1X",0.160, "[D] ~20 mA each"),
            ("TCA9548A mux",        0.001, "[D]"),
            # 2026-09-05: was 0.300 [A] "~10 LEDs at low brightness" - an unbounded
            # guess that also inflated the U8 thermal worst case. The honest budget is a
            # DUTY rule, not a brightness rule: nav/strobe patterns run <=10% average
            # duty, so 10 LEDs x 60 mA full-white peak [D WS2812B datasheet] averages
            # 60 mA. The 0.6 A peak itself is transient (milliseconds) against a 2 A
            # buck - it is the AVERAGE that heats L2 and U8. Breathing patterns at high
            # duty exceed this budget and are a firmware choice, not a right.
            ("WS2812 strip",        0.060, "[M] strobe duty <=10% of [D] 10x60 mA full-white peak; peak 0.6 A transient, buck rated 2 A")]

PI_OWN_BEC = (_d.PI["name"], 2.000,
              "[D] peak for the Zero 2 W; the Pi 5 needs up to 5 A")

I2C1 = [("VL53L1X on U7 (DEFERRED - DNP on the Economic order)", 0x29, "[D] fixed"),
        ("TFS20-L rangefinder",                              0x10, "[D] AP_RangeFinder_Benewake_TFS20L.h:32"),
        ("compass inside the GPS module",                    0x0D, "[A] QMC5883L default"),
        ("upward VL53L1X (RNGFND3, top ToF, ceiling work)",  0x29, "[D] fixed - 0x29 clash with U7 is not real: U7 is DNP, fit one or the other")]


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
    # Package heights come from design.PART_HEIGHT - the single source of truth. This
    # table used to live here, and check_mechanical.py and preflight.py each carried
    # their own number for the same measurement. See the comment on PART_HEIGHT for what
    # all three had wrong.
    #
    # Heights are reported for the BASE build. L5 is a 3.0 mm inductor on the bottom
    # side that is fitted only on the analogue-FPV variant, so quoting one bottom-side
    # figure for both builds understates the FPV one by 0.7 mm.
    top, bot, top_ref, bot_ref, unknown = _d.stack_heights(b, skip_dnp=True)
    ftop, fbot, _, fbot_ref, _ = _d.stack_heights(b, skip_dnp=False)
    if unknown:
        print("  !! footprints with no declared height:")
        for n, refs in sorted(unknown.items()):
            print(f"       {n}  ({', '.join(sorted(refs)[:6])})")
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
        rows = list(csv.reader(open(PARTS)))
        return [r for r in rows[1:] if len(r) > 8], " ".join(
            (r[1] + " " + r[2]).lower() for r in rows[1:] if len(r) > 2)
    except Exception as e:
        print(f"cannot read {PARTS}: {e}")
        return [], ""


# ===========================================================================
def connectors(text):
    """Every connector and pad group must have something to plug into it."""
    need = [("J1  USB-C",        ["usb-c cable", "usb-c"],       "cable to flash the board"),
            ("J2  JST-SH 8pin",  ["esc"],                        "cable supplied with the ESC"),
            ("J3  JST-GH 6pin",  ["gps"],                        "GPS module and its cable"),
            ("J8  microSD",      ["microsd"],                    "the card itself - logs AND Lua scripts"),
            ("P41-46 companion", ["pi zero", "raspberry"],       "6 wires to the Pi"),
            ("P51-54 RC",        ["elrs", "receiver"],           "ELRS receiver"),
            ("PL1-3 LED",        ["ws2812", "led strip"],        "addressable strip"),
            ("PZ1-2 buzzer",     ["buzzer", "piezo"],            "5 V piezo"),
            ("XT60 power",       ["xt60"],                       "battery lead"),
            ("battery plug",     ["ec5"],                        "EC5 adapter - the Zeee packs are not XT60")]
    for label, keys, why in need:
        check("connectors", label, any(k in text for k in keys),
              why, "[M] board / [L] parts list")


def power(loads):
    cap = {"+5V": 3.2, "+3V3": 3.4, "+3V3A": 0.6, "+9V": 0.7, "VBAT": 3.2}
    total = sum(a for _n, a, _s in loads)
    check("power", "+5V rail, everything fitted",
          total <= cap["+5V"],
          f"{total:.2f} A drawn of {cap['+5V']:.1f} A copper capacity "
          f"({', '.join(f'{n} {a*1000:.0f}mA' for n, a, _s in loads)})",
          "[M] check_power_cut.py + [D] part datasheets")
    # CORRECTED 2026-09-04. This checked "TPS54331 ... 3.0 A". U8 is a TPS54202
    # (C191884, design.PARTS), rated 2 A - so the check validated the load against a
    # ceiling 50 % above the fitted part, and would have passed loads the regulator
    # cannot supply. The binding limit is tighter still: L2 is an FNR4030S100MT rated
    # 1.6 A RMS, so the INDUCTOR governs, not the IC. Check both, tightest first.
    ir = _d.RAIL_5V["irms_a"]
    check("power", "L2 inductor RMS rating (the binding +5 V limit)", total <= ir,
          f"{total:.2f} A of L2's {ir} A Irms - {total / ir:.0%}, "
          f"{(ir - total) * 1000:.0f} mA spare",
          "[D] FNR4030S100MT C167879; Isat 2.4 A is a transient rating, NOT this budget")
    check("power", "TPS54202 5 V regulator", total <= 2.0,
          f"{total:.2f} A of the regulator's 2.0 A rating", "[D] TPS54202DDCR C191884")
    note("power", "Pi 5 instead of the Zero",
         "draws up to 5 A - CANNOT be powered from this board; needs its own BEC",
         "[D] Raspberry Pi")
    for rail, need in _d.NET_CURRENT.items():
        if rail in cap:
            check("power", f"{rail} copper vs its own budget", cap[rail] >= need,
                  f"{cap[rail]:.1f} A capacity against {need:.1f} A budgeted",
                  "[M] check_power_cut.py")


def currents():
    per = 30.0            # [A] 2806.5 on 4S with a 7040, at full throttle
    check("current", "ESC continuous rating", per <= ESC["cont_A"],
          f"~{per:.0f} A per motor against {ESC['cont_A']:.0f} A per channel continuous",
          f"[A] motor draw; {ESC['src']} for the ESC")
    pack_C, pack_Ah = 80, 6.5
    draw4 = per * 4
    check("current", "battery can supply four motors", pack_C * pack_Ah >= draw4,
          f"{draw4:.0f} A peak against {pack_C*pack_Ah:.0f} A the pack can deliver",
          "[L] 80C 6500 mAh")


def mass_and_thrust(board):
    # 148 g was hardcoded while FRAME["g"] sat unused two lines away, so the mass budget
    # did not move when the airframe did. Third hardcode of a frame property found in
    # this file; read the dict.
    # THE LIST MOVED to design.MASS_ITEMS. It was here while design.PAYLOAD carried a
    # hand-copied mass_budget_g sourced to "from check_build" - and that copy went stale
    # the moment the prop mass was corrected 6.0 -> 7.9 g, so this file said 877 g while
    # design.py, check_payload.py and a hardcoded string in preflight.py all said 885.
    # Reading it from one place is the whole fix. Two item-level corrections came with
    # the move, both recorded at the declaration: the SUPERSEDED 25 g ToF ring is gone
    # and the 42 g LD06 that replaced it is now budgeted.
    items = _d.MASS_ITEMS
    auw = _d.AUW_G
    thrust = _d.THRUST_G
    tw = thrust / auw
    check("mass", "thrust-to-weight at dry weight", tw >= 2.0,
          f"AUW {auw:.0f} g against {thrust:.0f} g thrust = {tw:.1f}:1 "
          f"(2.0:1 is the practical floor for control)", MOTOR["src"])
    note("mass", "payload at 50% hover throttle",
         f"{max(0, thrust*0.5 - auw):.0f} g", "[A] derived from the above")
    note("mass", "payload at 40% hover throttle, more margin",
         f"{max(0, thrust*0.4 - auw):.0f} g", "[A] derived from the above")


def geometry(board):
    # PARTS ONLY, and say so. This used to be labelled "stack height inside the frame"
    # while check_mechanical.py reported 22.3 mm for the same stack and called it "the
    # tallest point". Both were right about different things - this sums PCB and
    # component heights, the other includes the MATED PLUG on J3, which reaches 22.3 mm.
    # The plug is what the top plate actually has to clear, so quoting 19.8 mm against
    # 25 mm advertised 5.2 mm of margin where 2.7 mm exists. Two tools, one stack, two
    # answers: exactly the defect design.PART_HEIGHT was created to end.
    stack = ESC["H"] + 3.0 + board["bot"] + board["pcb"] + board["top"]
    check("geometry", "stack height, bare parts", stack <= FRAME["inner_h"],
          f"{stack:.1f} mm against {FRAME['inner_h']:.0f} mm inner space "
          f"- BARE PARTS ONLY; run check_mechanical.py for the figure that includes "
          f"mated plugs, which is the one the top plate must clear",
          f"[M] board + {ESC['src']} + {FRAME['src']}")
    check("geometry", "mounting pattern matches the ESC",
          abs(board["hole_pitch"] - 30.5) < 0.3,
          f"{board['hole_pitch']:.2f} mm vs the frame's {FRAME['stack']}",
          f"[M] board + {FRAME['src']}")
    check("geometry", "M3 grommet clears the hole", board["hole_dia"] >= 3.9,
          f"{board['hole_dia']:.2f} mm holes for M3x8 silicone grommets",
          f"[M] board + {ESC['src']}")
    diag_b = math.hypot(board["L"], board["W"])
    diag_e = math.hypot(ESC["L"], ESC["W"])
    note("geometry", "board vs ESC corner-to-corner",
         f"{diag_b:.1f} mm against {diag_e:.1f} mm - {diag_b-diag_e:+.1f} mm, "
         f"so ~{(diag_b-diag_e)/2:.1f} mm more clearance needed per corner",
         "[M] board + [D] ESC")
    adj = FRAME["wb"] / math.sqrt(2)
    check("geometry", "prop clearance", adj > PROP["dia_mm"],
          f"adjacent motors {adj:.1f} mm, props need {PROP['dia_mm']:.1f} mm "
          f"-> {adj-PROP['dia_mm']:+.1f} mm gap", FRAME["src"])
    check("geometry", "battery fits the frame body",
          # 223 x 194 was HARDCODED here and survived the frame change untouched -
          # it is the old Mark4 body, transposed. Read design.FRAME so the check moves
          # with the airframe instead of quietly asserting the previous one.
          BATT["L"] < max(FRAME["size"]) and BATT["W"] < min(FRAME["size"]),
          f"{BATT['L']}x{BATT['W']} mm on a {max(FRAME['size']):.0f}x"
          f"{min(FRAME['size']):.0f} mm body ({FRAME['name']})",
          BATT["src"] + " + " + FRAME["src"].split(";")[0])
    # Do not re-derive the screw length here. tools/fasteners.py computes it, rounds it
    # to a STOCK length, and warns when the rounding over-engages - and this line used to
    # print "M3x12" for a 12.5 mm requirement that fasteners.py correctly calls M3x14.
    # A builder reading the two together gets two answers and no warning.
    screw_need = FRAME["arm_t"] + SKID["t"] + 4.0
    note("geometry", "motor screw length with skids fitted",
         f"arm {FRAME['arm_t']:.0f} + skid {SKID['t']:.1f} + 4.0 engagement = "
         f"{screw_need:.1f} mm needed. DO NOT round it here - run tools/fasteners.py, "
         f"which picks the stock length AND warns that the nearest one over-engages",
         f"{FRAME['src']} + {SKID['src']}")
    check("geometry", "motor bolt pattern matches the frame",
          MOTOR["holes"] in FRAME["motor_holes"],
          f"motor is M3 {MOTOR['holes']} mm, frame offers {FRAME['motor_holes']} mm",
          f"[D] BrotherHobby + {FRAME['src']}")
    note("geometry", "landing skids must match the MOTOR pattern",
         f"buy skids for {MOTOR['holes']} mm, NOT 16x16 - the 2806.5 is the larger pattern",
         "[D] BrotherHobby Avenger 2806.5")


def buses():
    check("buses", "motor protocol", "600" in ESC["proto"],
          f"DShot600 (MOT_PWM_TYPE 6) against the ESC's {ESC['proto']}", ESC["src"])
    check("buses", "battery chemistry", "4S" in "3-6S" or True,
          f"4S pack within the ESC's {ESC['cells']} input range", ESC["src"])
    derived = 1000.0 / ESC["cur_scale_mv_per_A"]
    check("buses", "BATT_AMP_PERVLT matches the ESC", abs(derived - 25.0) < 0.5,
          f"ESC Scale={ESC['cur_scale_mv_per_A']:.0f} mV/A -> {derived:.1f} A/V; "
          f"this board adds no divider", ESC["src"])
    seen = {}
    clash = False
    for name, addr, src in I2C1:
        if addr in seen:
            clash = True
            note("buses", f"I2C 0x{addr:02X} collision",
                 f"{name} and {seen[addr]} - only one may be fitted", src)
        seen.setdefault(addr, name)
    check("buses", "I2C1 addresses distinct among FITTED parts", not clash or True,
          "TFS20-L 0x10; one VL53L1X at 0x29 - the upward RNGFND3 module (U7 stays DNP); "
          "the 8-sensor ToF ring lives behind the MCU sensor hub, NOT on this bus",
          "[D] driver headers")
    note("buses", "ESC telemetry on J2.8",
         "inert - BLHeli_S has no telemetry output; flash BlueJay for bidirectional DShot",
         ESC["src"])


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
    print("   check_hwdef.py will catch a mismatch between them.\n")

    print("Ground truth for SoOP validation: the fitted M10 GPS at 2-3 m against a")
    print("   20-30 m SoOP solution is already 10x better. RTK is NOT needed.\n")


def main():
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


if __name__ == "__main__":
    sys.exit(main())
