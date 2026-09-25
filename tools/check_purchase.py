#!/usr/bin/env python3
"""Assert every interface between parts that are bought SEPARATELY."""
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
    # Numeric and referential, not substring and not a literal.
    check(design.MOTOR_JOINT["pitch_mm"] in F["motor_patterns_mm"],
          "motor bolts <-> frame arm",
          f"motor needs {design.MOTOR_JOINT['pitch_mm']:.0f} x "
          f"{design.MOTOR_JOINT['pitch_mm']:.0f} mm; the arm offers "
          f"{design.fmt_pattern(F['motor_patterns_mm'])} mm",
          design.MOTOR_JOINT["src"])
    check(abs(S["hole_pitch"] - design.MOTOR_JOINT["pitch_mm"]) < 1e-6,
          "skid <-> MOTOR pattern",
          f"skid is built to {S['hole_pitch']:.0f} x {S['hole_pitch']:.0f} mm and the "
          f"motor IS {design.MOTOR_JOINT['pitch_mm']:.0f} x "
          f"{design.MOTOR_JOINT['pitch_mm']:.0f} mm - this compares them, where it used "
          f"to compare the skid to the literal 19.0", S["src"])

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
          f"module is {rd['vcc']} and {rd['lands_on']} pin 1 is 5 V -> inline LDO "
          f"unless the module "
          f"regulates on board", rd["src"])
    ru = O["rangefinder_up"]
    check(not design.POPULATE_BLIND_SENSORS, "upward VL53L1X address",
          f"0x{ru['addr']:02X} is free ONLY because {ru['free_because']}", ru["src"])
    rx = O["rx"]
    check(rx.get("mcu") == "ESP", "ELRS RX <-> laptop ground station",
          f"receiver MUST be {rx.get('mcu')}-based, firmware >= {rx.get('min_fw')}. "
          f"An STM32-based ELRS receiver CANNOT carry MAVLink, so there would be no "
          f"telemetry link to a laptop and no fix in software", rx["src"])
    check(True, "ELRS RX <-> J5", rx["note"], rx["src"])

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
    # Light rating is conditional on where it flies, not an absolute floor.
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
