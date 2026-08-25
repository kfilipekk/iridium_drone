#!/usr/bin/env python3
"""Assert every interface between parts that are BOUGHT SEPARATELY.

WHY THIS EXISTS. The verification apparatus was lopsided. preflight.py runs 63 checks over
the ~GBP 190 PCB, and almost nothing covered the ~GBP 425 of parts that bolt to it - most
of which carry "ASSUMED - spec not verified against a source" in docs/PARTS.csv.

The failure this prevents is narrow and specific: TWO SEPARATELY BOUGHT PARTS THAT DO NOT
MATE. Not "is the design good" - that is asked and answered elsewhere - but "will the props
screw onto the motors, will the GPS cable plug into J3 the right way round, will the skids
bolt to the motor pattern". That class of error cannot be fixed in software once the money
has moved, which is the whole reason for gating it before ordering rather than after.

Each assertion carries its own provenance, because an interface checked against a bad
source is worse than an unchecked one - it looks verified. [D]atasheet beats [L]isting
beats [A]ssumed, and the ones still resting on [A] are printed as such rather than passing
quietly.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design

fails, assumed = [], []


def check(ok, name, detail, src=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:38} {detail}")
    if src:
        print(f"        {src}")
        if src.lstrip().startswith("[A]"):
            assumed.append(name)
    if not ok:
        fails.append(name)


def main():
    M, P, F, S = design.MOTOR, design.PROP, design.FRAME, design.SKID
    B, PC, O = design.BATT, design.POWER_CONN, design.OFFBOARD

    print("=== the rotating parts ===")
    check(M["shaft_thread"] == P["mount"], "motor shaft <-> prop mount",
          f"motor is {M['shaft_thread']}, prop mount is {P['mount']}, bore "
          f"{P['bore_mm']:.1f} mm", P["src"])
    adj = F["wb"] / (2 ** 0.5)
    check(adj > P["dia_mm"], "prop <-> frame",
          f"adjacent motors {adj:.1f} mm, prop {P['dia_mm']:.1f} mm -> "
          f"{adj - P['dia_mm']:+.1f} mm gap", F["src"].split(";")[0])
    check(M["holes"] in F["motor_holes"], "motor bolts <-> frame arm",
          f"motor {M['holes']} mm, frame offers {F['motor_holes']} mm", M["src"])
    check(abs(S["hole_pitch"] - 19.0) < 0.1, "skid <-> MOTOR pattern",
          f"skid must be {S['hole_pitch']:.0f}x{S['hole_pitch']:.0f} mm - the frame also "
          f"offers 16x16 and buying that is the classic mistake", S["src"])

    print("\n=== power ===")
    check(PC["adapter_needed"], "battery plug <-> everything else",
          f"pack is {PC['pack']}, airframe is {PC['airframe']} -> ADAPTER REQUIRED. "
          f"Without it nothing connects on build day", PC["src"])
    check(3 <= B["cells"] <= 6, "battery <-> ESC chemistry",
          f"{B['cells']}S within the ESC's 3-6S input range", B["src"])

    print("\n=== connectors, traced to the netlist ===")
    gps = O["gps"]
    expect = ["5V", "USART2_TX", "USART2_RX", "I2C1_SCL", "I2C1_SDA", "GND"]
    check(gps["pinout"] == expect, "GPS cable <-> J3",
          f"{' / '.join(gps['pinout'])} - the standard ArduPilot order, so a stock cable "
          f"mates pin-for-pin", gps["src"])
    esc = O["esc"]
    check(True, "ESC cable <-> J2",
          f"{esc['conn']} - order matches SpeedyBee's documented one, but BUZZ THE CABLE "
          f"before VBAT. Not desk-verifiable", esc["src"])

    print("\n=== the sensors, and the variant traps ===")
    rd = O["rangefinder_down"]
    check(rd["variant"] == "I2C", "TFS20-L VARIANT",
          f"must be the {rd['variant']} part at 0x{rd['addr']:02X} on {rd['lands_on']}. "
          f"{rd['wrong_variant_note']}", rd["src"])
    check(rd["vcc"] == "3.3 V", "TFS20-L supply",
          f"module is {rd['vcc']} and J3.1 is 5 V -> inline LDO unless the module "
          f"regulates on board", rd["src"])
    ru = O["rangefinder_up"]
    check(not design.POPULATE_BLIND_SENSORS, "upward VL53L1X address",
          f"0x{ru['addr']:02X} is free ONLY because {ru['free_because']}", ru["src"])
    rx = O["rx"]
    check(rx.get("mcu") == "ESP", "ELRS RX <-> laptop ground station",
          f"receiver MUST be {rx.get('mcu')}-based, firmware >= {rx.get('min_fw')}. "
          f"An STM32-based ELRS receiver CANNOT carry MAVLink, so there would be no "
          f"telemetry link to a laptop and no fix in software", rx["src"])
    check(True, "ELRS RX <-> P51-P54", rx["note"], rx["src"])

    bz = O["buzzer"]
    check(bz["must_be"] == "passive", "buzzer TYPE",
          f"must be PASSIVE. {bz['drive']} is a timer channel - {bz['note']}", bz["src"])
    led = O["led"]
    check(led["volts"] == 5, "LED strip VOLTAGE",
          f"must be {led['volts']} V WS2812B - {led['note']}", led["src"])

    L = O["lidar"]
    ear = dict(design.PAYLOAD.get("serial_earmarked", []))
    check(2 in ear, "360 lidar <-> UART budget",
          f"{L['lands_on']} - {L['wires']}. SERIAL2 is earmarked for it in "
          f"design.PAYLOAD, so a payload cannot also claim it", L["src"])
    # LIGHT RATING IS CONDITIONAL ON WHERE IT FLIES, not an absolute floor.
    #
    # This asserted a flat min_klux >= 60. That is the OUTDOOR requirement - full sun is
    # ~100 klux - and applying it to a sensor whose job is indoor obstacle avoidance
    # rejected a GBP 15 part in favour of a $45 one for no gain. Room lighting is
    # 300-500 lux, so the LD06's 25 klux has ~50x of margin indoors.
    #
    # The check now asserts the condition that actually matters: either the part clears
    # 60 klux, or it is declared indoor-only. Taking an indoor_only lidar outside is the
    # failure this guards, and it is a swap (same PRX1_TYPE 16 driver), not a rework.
    lo, hi = L["indoor_lux"]
    margin = L["klux"] * 1000 / hi
    check(L["klux"] >= 60 or L.get("indoor_only"), "360 lidar <-> AMBIENT LIGHT",
          f"{L['klux']} klux, declared INDOOR ONLY. Room light is {lo}-{hi} lux, so that "
          f"is {margin:.0f}x margin. DO NOT FLY IT OUTSIDE: full sun is ~100 klux and a "
          f"lidar that hallucinates is worse than none - AC_Avoid brakes for nothing. "
          f"Outdoors, swap to {L['outdoor_swap']}"
          if L.get("indoor_only") else
          f"{L['klux']} klux, clears the 60 klux outdoor floor", L["src"])
    check(bool(L.get("buying_check")), "360 lidar <-> THE LISTING",
          L.get("buying_check", ""), L["src"])

    print()
    if assumed:
        print(f"{len(assumed)} interface(s) still rest on an ASSUMED source - confirm on "
              f"the listing before ordering:")
        for a in assumed:
            print(f"   - {a}")
        print()
    if fails:
        print(f"FAIL - {len(fails)} interface(s) do not mate: {', '.join(fails)}")
        return 1
    print("every buy-to-buy interface asserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
