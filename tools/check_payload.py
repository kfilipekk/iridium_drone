#!/usr/bin/env python3
"""Assert that the payload provisions design.PAYLOAD claims are ACTUALLY still spare.

WHY THIS EXISTS. "The board is reasonably modular" is the kind of claim that is true when
written and quietly false a month later, because nothing enforces it. A future change that
needs one more servo output or one more UART will take the last free one, the sentence in
the documentation will not change, and the next person plans a gimbal around a channel
that is gone.

So this checks three things against the artefacts rather than the prose:

  1. every PWM channel PAYLOAD claims is free has no SERVOn_FUNCTION in defaults.parm;
  2. every serial PAYLOAD claims is free has no SERIALn_PROTOCOL in defaults.parm;
  3. the pins behind them still exist in hwdef.dat as the peripheral claimed.

It deliberately does NOT check that a payload fits mechanically - nothing here knows what
the payload is. It checks that the ELECTRICAL door is still open.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design

REPO = os.path.dirname(HERE)
PARM = os.path.join(REPO, "firmware/NAVCORE_SoOP/defaults.parm")
HWDEF = os.path.join(REPO, "firmware/NAVCORE_SoOP/hwdef.dat")

fails = []


def check(ok, name, detail):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:34} {detail}")
    if not ok:
        fails.append(name)


def main():
    parm = open(PARM).read()
    hwdef = open(HWDEF).read()
    P = design.PAYLOAD

    print("=== free actuator channels ===")
    for name, pin, pad, param in P["pwm"]:
        claimed = re.search(rf'^{param}\s', parm, re.M)
        check(claimed is None, f"{name} ({pin}) at {pad}",
              f"{param} not set - free for a payload" if claimed is None
              else f"CONSUMED: {param} is set in defaults.parm")
        n = re.search(rf'^{re.escape(pin)}\s+\S+\s+\S+\s+PWM\((\d+)\)', hwdef, re.M)
        check(n is not None, f"{name} exists in hwdef",
              f"{pin} is PWM({n.group(1)})" if n else f"{pin} is NOT a PWM output in hwdef")

    print("\n=== free serial links ===")
    for idx, periph, pads, note in P["serial"]:
        claimed = re.search(rf'^SERIAL{idx}_PROTOCOL\s', parm, re.M)
        check(claimed is None, f"SERIAL{idx} ({periph}) at {pads}",
              f"unclaimed - {note}" if claimed is None
              else f"CONSUMED: SERIAL{idx}_PROTOCOL is set")

    for idx, who in P.get("serial_earmarked", []):
        print(f"  note  SERIAL{idx} is EARMARKED{'':16} for the {who}. Unclaimed in "
              f"defaults.parm today, so it passes above - but a payload and that cannot "
              f"both have it")

    print("\n=== declared but NOT reachable - stated so nobody plans around them ===")
    for idx, periph in P["serial_unrouted"]:
        print(f"  note  SERIAL{idx} ({periph}){'':18} in hwdef but routed to NO pad - "
              f"real to the firmware, unreachable with a soldering iron")

    print("\n=== power for a payload ===")
    print(f"  note  5 V pads{'':26} {', '.join(P['power_5v'])}")
    print(f"  note  GND pads{'':26} {', '.join(P['gnd'])}")
    print(f"  note  current{'':27} {P['power_note']}")
    print(f"  note  mass budget{'':23} {P['mass_budget_g']:.0f} g at 40% hover throttle")

    print()
    if fails:
        print(f"FAIL - {len(fails)} payload provision(s) no longer available: "
              f"{', '.join(fails)}")
        return 1
    print(f"payload provisions intact: {len(P['pwm'])} free PWM channel(s), "
          f"{len(P['serial'])} free routed UART, {P['mass_budget_g']:.0f} g budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
