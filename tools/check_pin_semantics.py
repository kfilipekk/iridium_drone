#!/usr/bin/env python3
"""Check that every MCU pin is wired to the right end of the thing it talks to.

Usage:  python3 tools/check_pin_semantics.py [-v]
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design, symlib
from hwdef_pinmap import parse

HW = "firmware/NAVCORE_SoOP/hwdef.dat"
RAILS = {"+3V3", "+3V3A", "+5V", "+9V", "VBAT", "VDDA", "VBUS"}
# Peripheral labels that are inherently one-way, and which way.
ROLE_DIR = [
    (re.compile(r'^(U(S)?ART\d+)_TX$'), "out"), (re.compile(r'^(U(S)?ART\d+)_RX$'), "in"),
    (re.compile(r'^(U(S)?ART\d+)_RTS$'), "out"), (re.compile(r'^(U(S)?ART\d+)_CTS$'), "in"),
    (re.compile(r'^SPI\d+_MOSI$'), "out"), (re.compile(r'^SPI\d+_MISO$'), "in"),
    (re.compile(r'^SPI\d+_SCK$'),  "out"),
    (re.compile(r'^CAN\d+_TX$'), "out"),  (re.compile(r'^CAN\d+_RX$'), "in"),
]


def mcu_pin_nets():
    """{MCU pin name: [net, ...]} using the same symbol table as check_design.py."""
    h7 = {p['num']: p['name'] for p in symlib.load()["STM32H743VIT6_C114409"]}
    out = {}
    for net, specs in design.NETS.items():
        for sp in specs:
            ref, pin = sp.split(".", 1)
            if ref != "U1":
                continue
            out.setdefault(h7.get(pin, pin).split("-")[0], []).append(net)
    return out


def pulls():
    """{net: [(ref, 'up'/'down', value), ...]} for resistors tying a net to a rail."""
    where = {}
    for net, specs in design.NETS.items():
        for sp in specs:
            ref, pad = sp.split(".", 1)
            where.setdefault(ref, []).append((net, pad))
    out = {}
    for ref, legs in where.items():
        if not ref.startswith("R") or len(legs) != 2:
            continue
        (na, _), (nb, _) = legs
        val = design.COMPONENTS.get(ref, ("", "", "?"))[2]
        for sig, rail in ((na, nb), (nb, na)):
            if rail in RAILS and sig not in RAILS:
                out.setdefault(sig, []).append(
                    (ref, "down" if rail == "GND" else "up", val))
            elif rail == "GND" and sig not in RAILS:
                out.setdefault(sig, []).append((ref, "down", val))
    return out


def devices_on(net):
    """Non-MCU, non-passive endpoints of a net - the things that might drive it."""
    out = []
    for sp in design.NETS.get(net, []):
        ref = sp.split(".", 1)[0]
        if ref == "U1" or ref[0] in "RCL" and ref[1:].isdigit():
            continue
        out.append(sp)
    return out


def main():
    verbose = "-v" in sys.argv
    pins, alts = parse(HW)
    nets_of = mcu_pin_nets()
    pl = pulls()
    intent = design.PIN_INTENT

    errs, warns, notes = [], [], []
    checked = 0

    for pin in sorted(pins):
        e = pins[pin]
        opts = " ".join(e["opts"])
        label, periph = e["label"], e["periph"]
        nets = [n for n in nets_of.get(pin, []) if n not in RAILS]
        if not nets:
            continue
        net = nets[0]
        want = intent.get(net)
        if want is None:
            if devices_on(net):
                notes.append(f"{pin} ({net}) has a device on it but no PIN_INTENT entry")
            continue
        checked += 1
        mcu = want["mcu"]
        is_out = "OUTPUT" in opts or "OUTPUT" in periph
        od = "OPENDRAIN" in opts

        # 1. contention - the firmware drives a pin the board expects to be driven
        if is_out and not od and mcu == "in":
            errs.append(f"{pin} ({net}): hwdef makes it a push-pull OUTPUT but "
                        f"{want['why']} - two drivers on one node")

        # 2. boot level - the reset state is not the state the device needs
        if is_out and want.get("boot"):
            lvl = "high" if re.search(r'\bHIGH\b', opts) else \
                  "low" if re.search(r'\bLOW\b', opts) else None
            if lvl and lvl != want["boot"]:
                errs.append(f"{pin} ({net}): hwdef resets it {lvl.upper()} but it must "
                            f"be {want['boot'].upper()} - {want['why']}")

        for rx, direction in ROLE_DIR:
            if rx.match(label) and mcu in ("in", "out") and direction != mcu:
                errs.append(f"{pin} ({net}): hwdef uses it as {label} ({direction}) but "
                            f"the signal goes {mcu} - {want['why']}")
                break

        # 4. pull fight - driving against a fitted resistor
        for ref, updown, val in pl.get(net, []):
            if not is_out:
                continue
            lvl = "high" if re.search(r'\bHIGH\b', opts) else \
                  "low" if re.search(r'\bLOW\b', opts) else None
            if lvl and ((lvl == "low" and updown == "up") or
                        (lvl == "high" and updown == "down")):
                warns.append(f"{pin} ({net}): driven {lvl.upper()} against {ref} "
                             f"({val} pull-{updown})")
        if verbose:
            print(f"  {pin:5} {net:12} {mcu:6} {label}")

    # 5. intent declared for something that is not wired
    for net in intent:
        if net not in design.NETS:
            notes.append(f"PIN_INTENT names '{net}', which is not a net")

    print(f"pins with declared intent : {checked}")
    print(f"PIN_INTENT entries        : {len(intent)}")
    print(f"nets with a fitted pull   : {len(pl)}")
    for title, items, mark in (("NOTES", notes, "  "), ("WARNINGS", warns, "  "),
                               ("ERRORS", errs, "  ")):
        if items:
            print(f"\n{title} ({len(items)}):")
            for it in items:
                print(f"{mark} {it}")
    if errs:
        print(f"\n{len(errs)} pin(s) are wired or configured the wrong way round.")
        return 1
    print("\nevery declared pin runs the right way.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
