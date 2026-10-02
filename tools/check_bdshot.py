#!/usr/bin/env python3
"""Can the four motors run bidirectional DShot on this board, as built?

Usage:  python3 tools/check_bdshot.py [--self-test]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import design  # noqa: E402

HWDEF = os.path.join(REPO, "firmware", "NAVCORE_SoOP", "hwdef.dat")
DEFAULTS = os.path.join(REPO, "firmware", "NAVCORE_SoOP", "defaults.parm")
BUILT = os.path.join(os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot")),
                     "build", "NAVCORE_SoOP", "hwdef.h")
MOTORS = ("M1", "M2", "M3", "M4")


def motor_pins():
    """M1..M4 -> the MCU pin each reaches (design.NETS: J2.3-6 to U1.Pxn)."""
    out = {}
    for m in MOTORS:
        pin = next((p.split(".", 1)[1] for p in design.NETS[m] if p.startswith("U1.")), None)
        out[m] = pin
    return out


def lines(hwdef):
    """Active (uncommented) PWM lines."""
    out = {}
    for ln in hwdef.splitlines():
        ln = ln.split("#", 1)[0].strip()
        m = re.match(r"^(P[A-K]\d+)\s+TIM(\d+)_CH(\d)(N?)\s+TIM\d+\s+PWM\((\d+)\)(.*)$", ln)
        if m:
            out[m.group(1)] = (int(m.group(2)), int(m.group(3)), bool(m.group(4)),
                               int(m.group(5)), "BIDIR" in m.group(6).split())
    return out


def evaluate(hwdef, built, defaults, built_fresh=True):
    fails = []
    pins = motor_pins()
    pwm = lines(hwdef)
    bidir = {(t, (c + 1) // 2) for t, c, n, _, b in pwm.values() if b}
    timers, chans = set(), set()
    mask = 0
    for m, pin in pins.items():
        if pin not in pwm:
            fails.append(f"{m} ({pin}) has no PWM line in hwdef.dat")
            continue
        t, c, comp, n, _ = pwm[pin]
        mask |= 1 << (n - 1)
        timers.add(t)
        if comp:
            fails.append(f"{m} ({pin}) is TIM{t}_CH{c}N - a complementary output cannot "
                         "capture the ESC's reply")
        if (t, (c + 1) // 2) not in bidir:
            fails.append(f"{m} ({pin}) on TIM{t}_CH{c}: no BIDIR on that timer's channel "
                         f"pair {2 * ((c + 1) // 2) - 1}/{2 * ((c + 1) // 2)}")
    for t, c, comp, n, b in pwm.values():
        if b:
            chans.add((t, c))
    if not built_fresh:
        fails.append("the build's hwdef.h is older than hwdef.dat - run tools/build_firmware.sh")
    for t in sorted(timers):
        for what in [f"TIM{t}_UP"] + [f"TIM{t}_CH{c}" for tt, c in sorted(chans) if tt == t]:
            m = re.search(rf"^#define STM32_TIM_{what}_DMA_STREAM\s+\S+(.*)$", built, re.M)
            if not m:
                fails.append(f"{what} has no DMA stream in the build")
            elif "shared" in m.group(1):
                fails.append(f"{what}'s DMA stream is shared:{m.group(1).strip()[2:]}")
    d = dict(re.findall(r"^(\w+)\s+([-\d.]+)", defaults, re.M))
    bd = int(float(d.get("SERVO_BLH_BDMASK", "0")))
    if bd not in (0, mask):
        fails.append(f"SERVO_BLH_BDMASK {bd} is neither off nor the motor mask {mask}")
    if "SERVO_BLH_POLES" not in d:
        fails.append("SERVO_BLH_POLES is not set, so ESC RPM would rest on the default")
    return fails, mask


def self_test(hwdef, built, defaults):
    pin1 = motor_pins()["M1"]
    breaks = [
        ("BIDIR removed", hwdef.replace(" BIDIR", ""), built, defaults, True),
        ("M1 back on TIM8_CH2N",
         re.sub(rf"^{pin1}\s+TIM3_CH3 TIM3", f"{pin1}  TIM8_CH2N TIM8", hwdef, flags=re.M),
         built, defaults, True),
        ("TIM3_CH3 stream missing",
         hwdef, re.sub(r"^#define STM32_TIM_TIM3_CH3_DMA_STREAM.*$", "", built, flags=re.M),
         defaults, True),
        ("TIM5_UP stream shared",
         hwdef, re.sub(r"^(#define STM32_TIM_TIM5_UP_DMA_STREAM\s+\S+).*$",
                       r"\1 // shared SPI1_RX,TIM5_UP", built, flags=re.M), defaults, True),
        ("BDMASK 3", hwdef, built, re.sub(r"^SERVO_BLH_BDMASK .*$", "SERVO_BLH_BDMASK 3",
                                          defaults, flags=re.M), True),
        ("stale build", hwdef, built, defaults, False),
    ]
    ok = True
    for name, h, b, d, fresh in breaks:
        caught = bool(evaluate(h, b, d, fresh)[0])
        ok &= caught
        print(f"  {'caught' if caught else 'MISSED'}  {name}")
    return ok


def main():
    hwdef = open(HWDEF).read()
    defaults = open(DEFAULTS).read()
    built = open(BUILT).read() if os.path.exists(BUILT) else ""
    fresh = bool(built) and os.path.getmtime(BUILT) >= os.path.getmtime(HWDEF)
    if "--self-test" in sys.argv:
        clean = not evaluate(hwdef, built, defaults, fresh)[0]
        print(f"  {'clean' if clean else 'NOT CLEAN'}  the board as built")
        ok = clean and self_test(hwdef, built, defaults)
        print("self-test passed: every break is caught" if ok else "SELF-TEST FAILED")
        return 0 if ok else 1
    fails, mask = evaluate(hwdef, built, defaults, fresh)
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} reason(s) BDShot cannot run on the motors")
        return 1
    print(f"BDShot ready on motors 1-4 (mask {mask}): BIDIR timers with DMA of their own; "
          f"enable after flashing Bluejay")
    return 0


if __name__ == "__main__":
    sys.exit(main())
