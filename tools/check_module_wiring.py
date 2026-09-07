#!/usr/bin/env python3
"""Can each module be plugged in without modifying another module's cable?"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

SHARED_BY_DESIGN = {
    # J3 carries I2C by standard, not by ACCIDENT.
    ("gps_compass", "J3"): "DS-009 defines the GPS port as carrying I2C; this is standard",
    # The dedicated I2C port J9 is a bus - sharing it is what the port is for, exactly like a Pixhawk's.
    ("rangefinder_down", "J9"): "I2C bus - 0x10; the other rangefinder (0x29) is a "
                                  "different-address alternative, never fitted together",
    ("rangefinder_up", "J9"): "I2C bus - 0x29; the other rangefinder (0x10) is a "
                                "different-address alternative, never fitted together",
}

PAD_BY_NATURE = {
    "soop_tuner": "an analogue I/Q pair, RSSI and PPS - coax and short leads, not a plug",
    "fpv":        "+5V/GND tap for a VTX; it has its own harness",
    "rec_camera": "two wires, +5V and GND",
}


# Rails every module is entitled to tap.
POWER_NETS = {"+5V", "+3V3", "+3V3A", "GND", "VBAT", "+9V", "VSERVO"}


def is_connector(ref):
    return ref.startswith("J")


def nets_on(ref):
    """Every net that reaches this reference, from design.NETS."""
    out = set()
    for net, pins in design.NETS.items():
        if any(p.split(".")[0] == ref for p in pins):
            out.add(net)
    return out


def carries_signal(ref):
    """Does this landing point carry anything but power? A pad that is only +5V and GND is
    a tap; a connector carrying USART2 and I2C1 is somebody's cable.
    """
    n = nets_on(ref)
    return bool(n - POWER_NETS)


def main():
    mods = {k: v for k, v in design.MODULES.items() if isinstance(v, dict)}
    # who else lands on each ref
    owners = {}
    for name, m in mods.items():
        for ref in m.get("lands_on") or []:
            if not carries_signal(ref):
                continue          # a power tap is shared by definition
            owners.setdefault(ref, []).append(name)

    shared, soldered, ok = [], [], []
    print("=== module wiring ===")
    print(f"{'module':22} {'lands on':22} {'dedicated':10} {'pluggable':10}")
    for name in sorted(mods):
        m = mods[name]
        refs = m.get("lands_on") or []
        if not refs:
            continue
        co = sorted({o for r in refs for o in owners.get(r, []) if o != name})
        dedicated = not co or all((name, r) in SHARED_BY_DESIGN for r in refs)
        pluggable = all(is_connector(r) for r in refs)
        exempt = name in PAD_BY_NATURE

        if not dedicated:
            shared.append((name, refs, co))
        if not pluggable and not exempt:
            soldered.append((name, refs))
        if dedicated and (pluggable or exempt):
            ok.append(name)

        print(f"  {name:20} {','.join(refs)[:20]:22} "
              f"{'yes' if dedicated else 'SHARED':10} "
              f"{('yes' if pluggable else ('n/a' if exempt else 'SOLDER')):10}"
              + (f"  <-- shares with {', '.join(co)}" if not dedicated else ""))

    print()
    if shared:
        print("SHARED LANDING POINTS - not a fault where SHARED_BY_DESIGN says otherwise,")
        print("but each one needs a splitter or a Y-lead rather than a plug:")
        for name, refs, co in shared:
            why = next((SHARED_BY_DESIGN[(name, r)] for r in refs
                        if (name, r) in SHARED_BY_DESIGN), None)
            print(f"  {name}: lands on {','.join(refs)}, shared with {', '.join(co)}")
            if why:
                print(f"      {why}")
    if soldered:
        print("\nSOLDER-ONLY LANDING POINTS - real and reachable, but not a plug:")
        for name, refs in soldered:
            print(f"  {name}: {','.join(refs)}")
    for name, why in sorted(PAD_BY_NATURE.items()):
        if name in mods:
            print(f"  note {name} exempt from the plug test - {why}")

    print(f"\n{len(ok)} module(s) wire cleanly, {len(shared)} need a cable splice, "
          f"{len(soldered)} need soldering")
    return 1 if shared else 0


if __name__ == "__main__":
    sys.exit(main())
