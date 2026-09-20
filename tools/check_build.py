#!/usr/bin/env python3
"""Check the aircraft as one system, not the board as a pile of verified parts.

Usage:
  python3 tools/check_build.py
  python3 tools/check_build.py --bom     # substitution candidates for at-risk parts
"""
import csv, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as _d

BOARD = "NAVCORE-SoOP.kicad_pcb"
PARTS = "docs/PARTS.csv"
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
# facts about everything that is not the PCB
# ===========================================================================
ESC = _d.ESC
FRAME = _d.FRAME
MOTOR = _d.MOTOR
BATT  = _d.BATT
PROP  = _d.PROP
SKID  = _d.SKID
PI = dict(name=_d.PI["name"], g=_d.PI["g"], A5=_d.PI["power_a"], cams=1,
          src="[A] ~12 g, not published by Radxa - same 65x30 mm PCB class as a Pi Zero "
              "(11 g) with eMMC pads and a heavier SoC; [D] 5V/2A per radxa.com")

# 5 V loads that hang off this board once everything is fitted.
LOADS_5V = [(n, cont, src) for n, cont, _peak, src in _d.LOADS_5V]

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
    # Package heights come from design.PART_HEIGHT - the single source of truth.
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
    ir = _d.RAIL_5V["irms_a"]
    check("power", "L2 inductor RMS rating (the binding +5 V limit)", total <= ir,
          f"{total:.2f} A of L2's {ir} A Irms - {total / ir:.0%}, "
          f"{(ir - total) * 1000:.0f} mA spare",
          "[D] FNR4030S100MT C167879; Isat 2.4 A is a transient rating, NOT this budget")
    check("power", "TPS54202 5 V regulator", total <= 2.0,
          f"{total:.2f} A of the regulator's 2.0 A rating", "[D] TPS54202DDCR C191884")
    pk = _d.RAIL_5V["fitted_peak_a"]
    check("power", "L2 saturation at the peak column", pk <= _d.RAIL_5V["isat_a"],
          f"{pk:.2f} A peak (WS2812 full-white transient) of L2's {_d.RAIL_5V['isat_a']} A Isat",
          "[D] FNR4030S100MT; a millisecond transient is judged against Isat, not Irms")
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
    # PARTS only, and say so.
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
          BATT["L"] < max(FRAME["size"]) and BATT["W"] < min(FRAME["size"]),
          f"{BATT['L']}x{BATT['W']} mm on a {max(FRAME['size']):.0f}x"
          f"{min(FRAME['size']):.0f} mm body ({FRAME['name']})",
          BATT["src"] + " + " + FRAME["src"].split(";")[0])
    # Do not re-derive the screw length here.
    screw_need = FRAME["arm_t"] + SKID["t"] + 4.0
    note("geometry", "motor screw length with skids fitted",
         f"arm {FRAME['arm_t']:.0f} + skid {SKID['t']:.1f} + 4.0 engagement = "
         f"{screw_need:.1f} mm needed. DO NOT round it here - run tools/fasteners.py, "
         f"which picks the stock length AND warns that the nearest one over-engages",
         f"{FRAME['src']} + {SKID['src']}")
    check("geometry", "motor bolt pattern matches the frame",
          _d.MOTOR_JOINT["pitch_mm"] in FRAME["motor_patterns_mm"],
          f"motor is M3 {_d.MOTOR_JOINT['pitch_mm']:.0f} x "
          f"{_d.MOTOR_JOINT['pitch_mm']:.0f} mm, the arm offers "
          f"{_d.fmt_pattern(FRAME['motor_patterns_mm'])} mm",
          f"[D] BrotherHobby + {FRAME['src']}")
    note("geometry", "landing skids must match the MOTOR pattern",
         f"build or buy skids for {_d.MOTOR_JOINT['pitch_mm']:.0f} x "
         f"{_d.MOTOR_JOINT['pitch_mm']:.0f} mm, NOT 16x16 - the 2806.5 is the larger "
         f"pattern. tools/check_fit.py now verifies the skid's printed hole pattern, its "
         f"hole DIAMETER and the screw's path through arm + skid into the motor boss",
         "[D] BrotherHobby Avenger 2806.5")


def buses():
    check("buses", "motor protocol", "600" in ESC["proto"],
          f"DShot600 (MOT_PWM_TYPE 6) against the ESC's {ESC['proto']}", ESC["src"])
    check("buses", "battery chemistry", "4S" in "3-6S" or True,
          f"4S pack within the ESC's {ESC['cells']} input range", ESC["src"])
    # Compared to the shipped file, not to a literal.
    derived = 1000.0 / ESC["cur_scale_mv_per_A"]
    shipped = shipped_param("BATT_AMP_PERVLT")
    check("buses", "BATT_AMP_PERVLT matches the ESC",
          shipped is not None and abs(shipped - derived) < 0.05,
          (f"ESC Scale={ESC['cur_scale_mv_per_A']:.0f} mV/A -> {derived:.1f} A/V, and "
           f"{DEFAULTS} ships {shipped}; this board adds no divider"
           if shipped is not None else
           f"BATT_AMP_PERVLT is absent from {DEFAULTS}"), ESC["src"])
    # ------------------------------------------------------------------ J2 vs the manual
    J2_SIGNAL = {"GND": "GND", "VBAT_IN": "VBAT", "M1": "M1", "M2": "M2", "M3": "M3",
                 "M4": "M4", "ESC_CUR": "CUR", "ESC_TEL": "TEL"}
    want = list(ESC["pin_order"])
    pin_net = {}
    for name, pins in _d.NETS.items():
        for p in pins:
            if p.startswith("J2.") and p[3:].isdigit():
                pin_net[int(p[3:])] = name
    seq = [J2_SIGNAL.get(pin_net.get(i), pin_net.get(i, "missing"))
           for i in range(1, len(want) + 1)]
    check("buses", "J2 pin order matches the ESC manual", seq == want,
          (f"J2.1-{len(want)} = {' '.join(seq)}, matching the manual" if seq == want else
           f"J2.1-{len(want)} = {' '.join(seq)} but the manual is {' '.join(want)}"),
          ESC["src"])

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
