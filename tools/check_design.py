#!/usr/bin/env python3
"""
Validate tools/design.py before anything is generated from it.

Checks:
  1. every component's symbol exists in the library
  2. every pin reference resolves to a real pin on that symbol
  3. no pin appears on two different nets (short)
  4. every pin of every component is accounted for (connected or explicitly NC)
  5. MCU pin usage matches MatekH743's hwdef - the whole point of the design
"""
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
    # NOTHING COMPARED THESE. gen_bom.py takes values from design.py and the board
    # only for placement, so a stale value in the .kicad_pcb never reached the fab -
    # but it made the KiCad file say one thing and the order another, and anyone
    # exporting a BOM from KiCad itself would have got the stale number.
    #
    # Two were found stale, both left behind by the TPS54331 -> TPS54202 swap when
    # the board was restored from a backup: R6 read 27k against design's 37k4 (a
    # 3.75 V "5 V" rail) and R42/R43 read 47k/4k7 against 66k5/4k7 (a 6.56 V "9 V"
    # rail). Both are now checked every run.
    try:
        import pcbnew
        _b = pcbnew.LoadBoard(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "NAVCORE-SoOP.kicad_pcb"))
        # ---- THE SET COMPARISON, which nothing did until 2026-09-07 -------------
        # The loop below only ever compared VALUE STRINGS, and only for refs present in
        # BOTH files: a ref design.py lacks hits `continue`, and a ref the BOARD lacks is
        # never iterated at all. So it could not see a part added to the design, or one
        # deleted from it, in either direction - and that is not hypothetical. The
        # artwork sat 29 parts behind and 14 parts ahead of design.py through an entire
        # session while this check, and every other check, returned 0. Preflight called
        # it five blockers. Adding a $17 tuner to the design moved that number by zero.
        #
        # A gate that cannot see the difference between the design and the thing being
        # fabricated is not a gate. This is a hard ERROR, not a warning: ordering a board
        # that does not match its own netlist is the most expensive mistake available.
        board_refs = {fp.GetReference() for fp in _b.GetFootprints()}
        fitted = {r for r, c in design.COMPONENTS.items() if not c[4] and c[1]}
        placed = {r for r, c in design.COMPONENTS.items() if c[1]}   # incl. DNP: DNP
                                                                     # means no PART, the
                                                                     # PADS still exist
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

    # ---- THE SAME COMPARISON, FOR THE SCHEMATIC ------------------------------
    # Nothing checked it. This file did not read NAVCORE-SoOP.kicad_sch at all,
    # preflight.py touched it only to run ERC, and check_topology.py EXPORTS a netlist
    # from it and treats that as the source of truth. So a schematic left stale after a
    # design.py edit was invisible in every direction at once: ERC passed on the old
    # one, and check_topology validated the old one while reporting on the new design.
    #
    # Same shape as the board gap closed above, and the same fix: compare the SETS, both
    # ways, and fail on a difference. The exporter is check_topology's rather than a
    # second copy of it - two parsers of the same file drift apart, and then the question
    # of which one is right becomes its own bug.
    SCH_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "NAVCORE-SoOP.kicad_sch")
    DESIGN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "design.py")
    if not os.path.exists(SCH_FILE):
        errors.append("NAVCORE-SoOP.kicad_sch is missing - run tools/gen_sch.py")
    else:
        # Cheap guard first. gen_sch.py writes random UUIDs on every run, so the
        # schematic can NEVER be verified by regenerating and diffing - that is where
        # the 4995-line schematic diffs in this history came from. mtime is the only
        # free signal that it was regenerated after design.py last changed.
        if os.path.getmtime(SCH_FILE) < os.path.getmtime(DESIGN_FILE):
            errors.append("SCHEMATIC IS OLDER THAN design.py - regenerate it with "
                          "tools/gen_sch.py, or the netlist check_topology exports "
                          "describes the previous design")
        try:
            import check_topology
            sch_nets, sch_comps = check_topology.netlist()
            sch_refs = set(sch_comps)
            # PWR_FLAG symbols are schematic-only (no footprint) and legitimately
            # absent from anything that counts parts; keep them out of both sides.
            want_refs = {r for r, c in design.COMPONENTS.items() if c[1]}
            sch_refs = {r for r in sch_refs if r in design.COMPONENTS and
                        design.COMPONENTS[r][1]}
            missing_sch = sorted(want_refs - sch_refs)
            extra_sch = sorted(r for r in sch_comps
                               if r not in design.COMPONENTS)
            if missing_sch:
                errors.append(f"SCHEMATIC IS BEHIND design.py: {len(missing_sch)} "
                              f"part(s) are in the design and not in the schematic - "
                              f"{', '.join(missing_sch)}")
            if extra_sch:
                errors.append(f"SCHEMATIC IS AHEAD OF design.py: {len(extra_sch)} "
                              f"symbol(s) are in the schematic and in no design - "
                              f"{', '.join(extra_sch)}")
            # A net with ONE pin is not a connection, and kicad-cli's exporter
            # legitimately omits it - PWM7-12, the *_SPARE pins and IMU3_CS are all
            # single-pin by design. Requiring them made the check cry wolf on 19 nets
            # that are correct. Two pins or more is what "a net exists" means here.
            want_nets = {n for n, pins in design.NETS.items() if len(set(pins)) > 1}
            missing_nets = sorted(want_nets - set(sch_nets))
            if missing_nets:
                errors.append(f"SCHEMATIC IS MISSING {len(missing_nets)} net(s) the "
                              f"design declares - {', '.join(missing_nets[:12])}"
                              + (" ..." if len(missing_nets) > 12 else ""))
            print(f"schematic  : {len(sch_refs)} symbols, {len(sch_nets)} nets")
        except Exception as e:
            warnings.append(f"schematic netlist could not be exported ({e}) - "
                            "kicad-cli needed; schematic NOT set-checked")

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
