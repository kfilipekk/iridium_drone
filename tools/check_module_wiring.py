#!/usr/bin/env python3
"""
Can each module be plugged in without modifying another module's cable?

WHY THIS EXISTS. tools/check_modules.py already asserts that every module's `lands_on`
resolves to real footprints on the board, so nothing can claim a pad that does not exist.
That is necessary and it is not the same question as whether the thing is WIRABLE. A
landing point can be entirely real and still be:

  - SHARED, so fitting this module means splicing into a cable that already belongs to
    another one, or
  - SOLDER PADS, so fitting it means a soldering iron rather than a plug.

Both are true on this board today and neither was measured anywhere. I2C1 is brought out
ONLY on J3.4/J3.5, which is the GPS connector - so fitting the TFS20-L rangefinder means
cutting into the GPS loom. PWM5/PWM6 are bare signal pads at TP3/TP4 with no local 5 V or
ground, so one servo is three wires from three different places on the board.

TWO PROPERTIES, REPORTED SEPARATELY, because conflating them would hide which fix each
module needs. "Dedicated" is about ownership and is fixed by adding a connector.
"Pluggable" is about the landing being a connector at all and is fixed the same way, but
a module can be dedicated and still need soldering (the LD06 on TP5/TP6), or pluggable
and still shared (both rangefinders on J3).

CONVENTION: a reference beginning J is a connector; P and TP are pads. That is the
board's own naming and check_connectors.py relies on it too.

    python3 tools/check_module_wiring.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

# Modules that deliberately share a landing point and are NOT a splice, with the reason.
# Kept explicit so that "shared" never becomes a silent category: an entry here is a
# decision someone made and signed, not an exception the checker invented.
SHARED_BY_DESIGN = {
    # J3 CARRIES I2C BY STANDARD, NOT BY ACCIDENT. The Pixhawk connector standard DS-009
    # defines the GPS port as a 6-pin JST-GH carrying VCC/TX/RX/SCL/SDA/GND, which is
    # exactly this board's J3. Pixhawk 4/5/6 and the Matek H743 series all do the same,
    # and 3DR sell a GPS-port-to-I2C splitter as a catalogue product. Calling this a
    # wiring fault was wrong - the first version of this check did, and it mislabelled
    # standard practice.
    #
    # The gap this entry exists for is closed: J9 is a DEDICATED 4-pin I2C port
    # (VCC/SCL/SDA/GND) exactly like the Matek H743-WLite's, so the rangefinders land
    # there and no longer share the GPS loom. NO_DEDICATED_BUS was removed with it.
    ("gps_compass", "J3"): "DS-009 defines the GPS port as carrying I2C; this is standard",
    # The dedicated I2C port J9 is a BUS - sharing it is what the port is FOR, exactly
    # like a Pixhawk's. The two rangefinders use different addresses (0x10 / 0x29) and
    # are fitted one at a time (outdoor TFS20-L vs indoor VL53L1X), so this is not a
    # cable belonging to somebody else; it is one socket with two possible occupants.
    ("rangefinder_down", "J9"): "I2C bus - 0x10; the other rangefinder (0x29) is a "
                                  "different-address alternative, never fitted together",
    ("rangefinder_up", "J9"): "I2C bus - 0x29; the other rangefinder (0x10) is a "
                                "different-address alternative, never fitted together",
}

# Landing points that are pads by nature and will never be connectors, so counting them
# as "not pluggable" would be noise rather than a finding.
PAD_BY_NATURE = {
    "soop_tuner": "an analogue I/Q pair, RSSI and PPS - coax and short leads, not a plug",
    "fpv":        "+5V/GND tap for a VTX; it has its own harness",
    "rec_camera": "two wires, +5V and GND",
}


# Rails every module is entitled to tap. Sharing these is not a splice - it is what a
# power pad IS. Counting them as contention was the first version of this check, and it
# reported 6 splices where there are 3: it measured "shares a reference" when the property
# that matters is "shares a SIGNAL". A +5V pad and a GPS connector are both references and
# only one of them is a cable belonging to somebody else.
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
    """Does this landing point carry anything but power? A pad that is only +5V and GND
    is a tap; a connector carrying USART2 and I2C1 is somebody's cable."""
    n = nets_on(ref)
    return bool(n - POWER_NETS)


def main():
    # MODULES carries a trailing `src` string alongside the dicts; skip anything that
    # is not a module rather than assuming the table is homogeneous.
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
