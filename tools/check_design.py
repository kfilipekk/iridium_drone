#!/usr/bin/env python3
"""Validate tools/design.py before anything is generated from it."""
import os, sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symlib, design
from hwdef_pinmap import parse

STOCK = "/usr/share/kicad/symbols"

def load_all_symbols():
    syms = symlib.load()
    for libfile in ("Device","Switch","Connector","Connector_Generic","power"):
        p = f"{STOCK}/{libfile}.kicad_sym"
        if os.path.exists(p):
            for k, v in symlib.load(p).items():
                syms[f"{libfile}:{k}"] = v
    return syms

def resolve(syms, ref, pinspec):
    symname = design.COMPONENTS[ref][0]
    key = symname.split(":", 1)[1] if symname.startswith("jlc_parts:") else symname
    pins = syms.get(key) or syms.get(symname)
    if pins is None:
        return None, f"symbol not found: {symname}"
    for p in pins:
        if p['num'] == pinspec:
            return p['num'], None
    named = [p for p in pins if p['name'] == pinspec]
    if len(named) == 1:
        return named[0]['num'], None
    if len(named) > 1:
        return None, f"pin name '{pinspec}' is ambiguous on {symname} ({len(named)} matches)"
    # allow "PC15" to match a pin named "PC15-OSC32_OUT"
    pre = [p for p in pins if p['name'].split('-')[0] == pinspec]
    if len(pre) == 1:
        return pre[0]['num'], None
    return None, f"no pin '{pinspec}' on {symname}"

def main():
    syms = load_all_symbols()
    errors, warnings = [], []
    owner, resolved = {}, {}

    for netname, pins in design.NETS.items():
        for spec in pins:
            if "." not in spec:
                errors.append(f"{netname}: malformed pin spec '{spec}'"); continue
            ref, pin = spec.split(".", 1)
            if ref not in design.COMPONENTS:
                errors.append(f"{netname}: unknown component '{ref}'"); continue
            num, err = resolve(syms, ref, pin)
            if err:
                errors.append(f"{netname}: {spec} -> {err}"); continue
            key = (ref, num)
            if key in owner and owner[key] != netname:
                errors.append(f"SHORT: {ref}.{num} on both '{owner[key]}' and '{netname}'")
            owner[key] = netname
            resolved.setdefault(netname, []).append((ref, num))

    # unconnected pins
    for ref, (symname, *_rest) in design.COMPONENTS.items():
        key = symname.split(":", 1)[1] if symname.startswith("jlc_parts:") else symname
        pins = syms.get(key) or syms.get(symname)
        if not pins: continue
        unconn = [p['num'] for p in pins
                  if (ref, p['num']) not in owner and p['name'] not in ("NC", "DNC", "RESV")]
        if unconn:
            warnings.append(f"{ref} ({design.COMPONENTS[ref][2]}): unconnected {','.join(unconn)}")

    # MCU vs hwdef
    hw, _alts = parse("firmware/reference/MatekH743-hwdef.dat")
    sym_h7 = syms.get("STM32H743VIT6_C114409", [])
    num2name = {p['num']: p['name'] for p in sym_h7}
    used = {num2name[n] for (r, n) in owner if r == "U1" and n in num2name}
    gpio_used = {u for u in used if re.match(r'^P[A-H]\d', u)}
    gpio_used = {u.split('-')[0] for u in gpio_used}
    hwdef_pins = set(hw)
    missing = sorted(hwdef_pins - gpio_used)
    OUTSIDE_HWDEF = {"PH0","PH1",          # HSE crystal - hwdef declares OSCILLATOR_HZ, not pins
                     "PB2","PE15","PC2_C","PC3_C"}   # spare pins broken out to test pads
    extra   = sorted(gpio_used - hwdef_pins - OUTSIDE_HWDEF)

    print(f"components : {len(design.COMPONENTS)}")
    print(f"nets       : {len(design.NETS)}")
    print(f"connections: {sum(len(v) for v in resolved.values())}")
    print(f"\nMCU vs MatekH743 hwdef:")
    print(f"  hwdef assigns {len(hwdef_pins)} pins; design uses {len(gpio_used)}")
    print(f"  in hwdef but NOT wired : {len(missing)}  {missing if missing else ''}")
    print(f"  wired but NOT in hwdef : {len(extra)}  {extra if extra else ''}")

    # ---- board value fields vs design.py -------------------------------------
    try:
        import pcbnew
        _b = pcbnew.LoadBoard(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "NAVCORE-SoOP.kicad_pcb"))
        # ---- the set comparison -------------
        board_refs = {fp.GetReference() for fp in _b.GetFootprints()}
        fitted = {r for r, c in design.COMPONENTS.items() if not c[4] and c[1]}
        placed = {r for r, c in design.COMPONENTS.items() if c[1]}   # incl. DNP: DNP
                                                                     # means no part, the
                                                                     # pads still exist
        missing_from_board = sorted(fitted - board_refs)
        stale_on_board     = sorted(board_refs - placed)
        if missing_from_board:
            errors.append(f"BOARD IS BEHIND design.py: {len(missing_from_board)} fitted "
                          f"part(s) have no footprint on the artwork - "
                          f"{', '.join(missing_from_board)}")
        if stale_on_board:
            errors.append(f"BOARD IS AHEAD OF design.py: {len(stale_on_board)} footprint(s) "
                          f"on the artwork are in no longer in the design - "
                          f"{', '.join(stale_on_board)}")

        for fp in _b.GetFootprints():
            ref = fp.GetReference()
            comp = design.COMPONENTS.get(ref)
            if not comp or not comp[2]:
                continue
            if fp.GetValue() != comp[2]:
                errors.append(f"{ref}: board says {fp.GetValue()!r}, "
                              f"design.py says {comp[2]!r}")
    except ImportError:
        warnings.append("pcbnew unavailable - board value fields NOT checked")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings: print("  ", w)
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors: print("  ", e)
        return 1
    print("\nno errors.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
