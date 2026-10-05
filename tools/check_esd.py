#!/usr/bin/env python3
"""Does every signal that leaves the board on a cable have a clamp at its connector?

Usage:  python3 tools/check_esd.py [--self-test]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design  # noqa: E402

BOARD = os.path.join(os.path.dirname(HERE), "NAVCORE-SoOP.kicad_pcb")
SUPPLY = {"GND", "+5V", "+5V_PAYLOAD", "+3V3", "+3V3A", "VBAT", "VBAT_IN", "VBUS"}


def positions():
    import pcbnew
    b = pcbnew.LoadBoard(BOARD)
    T = pcbnew.ToMM
    pads, parts = {}, {}
    for f in b.GetFootprints():
        p = f.GetPosition()
        parts[f.GetReference()] = (T(p.x), T(p.y))
        for q in f.Pads():
            c = q.GetPosition()
            pads[f"{f.GetReference()}.{q.GetNumber()}"] = (T(c.x), T(c.y))
    return pads, parts


def evaluate(nets, series, pads, parts):
    E = design.ESD
    fails, n = [], 0
    owner = {}
    for name, pins in nets.items():
        for p in pins:
            owner[p] = name
    for p, name in sorted(owner.items()):
        ref = p.split(".")[0]
        if not (ref.startswith("J") and ref[1:].isdigit()) or ref in E["exempt"]:
            continue
        if name in SUPPLY or name.startswith(("GND", "+")) or name in E.get("exempt_nets", {}):
            continue
        n += 1
        clamps = [q for q in nets[name] if q.split(".")[0] in E["clamps"]]
        if not clamps:
            fails.append(f"{p} ({name}) has no clamp on its net")
            continue
        if p in pads:
            #pin to the clamp's own pad on this net: the length the surge runs along
            d = min(math.dist(pads[p], pads.get(c, parts[c.split(".")[0]])) for c in clamps)
            lim = E.get("port_max_mm", {}).get(ref, (E["max_mm"],))[0]
            if d > lim:
                fails.append(f"{p} ({name}): nearest clamp {d:.1f} mm away (limit {lim:.0f})")
    for mcu_net, (part, jn) in series.items():
        if any(q.startswith("U1.") for q in nets.get(jn, [])):
            fails.append(f"{jn}: the MCU is on the connector's net - {part} is bypassed")
        if not any(q.startswith(part + ".") for q in nets.get(mcu_net, [])):
            fails.append(f"{mcu_net}: {part} does not reach the MCU's side")
    return fails, n


def self_test(pads, parts):
    import copy
    ok = not evaluate(design.NETS, design.SERIES, pads, parts)[0]
    print(f"  {'clean' if ok else 'NOT CLEAN'}  the board as designed")
    a = copy.deepcopy(design.NETS)
    a["M1_J"] = [q for q in a["M1_J"] if not q.startswith("U26.")]
    far = dict(pads)
    for k in [k for k in far if k.startswith("U28.")]:
        x, y = far[k]
        far[k] = (x + 25.0, y)
    c = copy.deepcopy(design.NETS)
    mcu = next(q for q in design.NETS["M2"] if q.startswith("U1."))
    c["M2_J"].append(mcu)
    for name, args in (("a clamp taken off M1", (a, design.SERIES, pads, parts)),
                       ("U28 moved 25 mm away", (design.NETS, design.SERIES, far, parts)),
                       ("RN1 bridged on M2", (c, design.SERIES, pads, parts))):
        caught = bool(evaluate(*args)[0])
        ok &= caught
        print(f"  {'caught' if caught else 'MISSED'}  {name}")
    print("self-test passed: every break is caught" if ok else "SELF-TEST FAILED")
    return 0 if ok else 1


def main():
    pads, parts = positions()
    if "--self-test" in sys.argv:
        return self_test(pads, parts)
    fails, n = evaluate(design.NETS, design.SERIES, pads, parts)
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} unprotected or bypassed line(s)")
        return 1
    print(f"{n} off-board signal pin(s), each clamped within its port's limit "
          f"({design.ESD['max_mm']:.0f} mm unless design.ESD says why); "
          f"{len(design.SERIES)} behind a series resistor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
