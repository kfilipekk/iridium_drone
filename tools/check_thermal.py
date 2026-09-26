#!/usr/bin/env python3
"""Thermal check for the switching regulators and the 3V3 rail.

Run: python3 tools/check_thermal.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

VIN_4S = 16.8               # [M] 4S fully charged, design.BATT

T_EDGE = 10e-9
# [L] efficiency band for a 2-3 A synchronous buck at this step-down ratio
EFF_LO, EFF_HI = 0.85, 0.90
T_AMBIENT_STACK = 40.0      # [A] inside a stack between an ESC and a battery, no airflow

fails, notes = [], []


def line(status, name, detail, src=""):
    print(f"  {status:5s} {name:38s} {detail}")
    if src:
        print(f"        {src}")


def main():
    print("=== switching regulator dissipation ===")
    print(f"      Vin {VIN_4S} V (4S), ambient {T_AMBIENT_STACK:.0f} C [A]")
    print(f"      every part-specific number comes from design.BUCK_THERMAL, keyed on the "
          f"fitted part,")
    print(f"      and every rail voltage from design.BUCK_RAILS (asserted against the "
          f"fitted divider by\n      check_electrical.py section 2) - this file no longer "
          f"carries a copy of either\n")

    for ref, rail, vout, _rt, _rb, ind in design.BUCK_RAILS:
        part = design.COMPONENTS[ref][2]
        spec = design.BUCK_THERMAL.get(part)
        if not spec:
            fails.append(f"{ref}: {part} has no entry in design.BUCK_THERMAL - an "
                         f"unclassified regulator is not a checked one")
            line("FAIL", f"{ref} unclassified", f"{part} is not in design.BUCK_THERMAL")
            continue
        iout, dnp = design.INDUCTOR_LOAD_A[ind], design.buck_dnp(ref)
        fsw = spec["fsw"]
        rds_hs, rds_ls = spec["rds_hs"], spec["rds_ls"]
        theta_jedec = spec["theta_jedec"]
        theta_evm = spec["theta_evm"] or theta_jedec
        tj_max = spec["tj_max"]

        pout = vout * iout
        D = vout / VIN_4S
        p_comp = iout**2 * rds_hs * D + iout**2 * rds_ls * (1 - D) \
            + 0.5 * VIN_4S * iout * T_EDGE * fsw * 2
        p_lo = pout * (1 / EFF_HI - 1)      # 90 % efficiency
        p_hi = pout * (1 / EFF_LO - 1)      # 85 % efficiency
        # Corners: best = most efficient on the best-copper board, worst = least efficient on the JEDEC board.
        tj_lo = T_AMBIENT_STACK + p_lo * theta_evm       # best case
        tj_hi = T_AMBIENT_STACK + p_hi * theta_jedec     # worst case
        tj_mid_hi = T_AMBIENT_STACK + p_hi * theta_evm   # good copper, poor efficiency

        tag = " (DNP on this build)" if dnp else ""
        print(f"  {ref} {rail} {part}{tag}")
        print(f"      Pout {pout:.2f} W at {vout:.3f} V x {iout:.2f} A, D={D:.3f}, "
              f"fsw {fsw/1e3:.0f} kHz")
        print(f"      theta_JA {theta_evm:.1f}-{theta_jedec:.1f} C/W (good copper to JEDEC "
              f"board), limits {tj_max:.0f} C recommended / {spec['tj_absmax']:.0f} C "
              f"absolute / {spec['t_shutdown']:.0f} C shutdown")
        print(f"      Pd: {p_comp*1e3:.0f} mW component-level [D RDS(on), A edges]  vs  "
              f"{p_lo*1e3:.0f}-{p_hi*1e3:.0f} mW at {EFF_HI*100:.0f}-{EFF_LO*100:.0f}% "
              f"efficiency [L]")
        if theta_evm == theta_jedec:
            print(f"      junction {tj_lo:.0f} C best ({EFF_HI*100:.0f}%) .. {tj_hi:.0f} C "
                  f"worst ({EFF_LO*100:.0f}%) against {tj_max:.0f} C - the datasheet "
                  f"gives ONE theta_JA, so the spread here is the efficiency band alone")
        else:
            print(f"      junction {tj_lo:.0f} C best (EVM copper, {EFF_HI*100:.0f}%) .. "
                  f"{tj_mid_hi:.0f} C (EVM copper, {EFF_LO*100:.0f}%) .. "
                  f"{tj_hi:.0f} C worst (JEDEC copper, {EFF_LO*100:.0f}%), against "
                  f"{tj_max:.0f} C")
            print(f"      the spread IS the finding - it needs measuring, not more "
                  f"arithmetic")

        if dnp:
            line("note", f"{ref} not fitted",
                 f"DNP - no dissipation on this build, but if the VTX rail is ever "
                 f"populated this part reaches {tj_hi:.0f} C worst case "
                 + ("(over the "
                    f"{spec['t_shutdown']:.0f} C thermal shutdown - it would hiccup)"
                    if tj_hi >= spec['t_shutdown'] else
                    f"({'over' if tj_hi >= tj_max else 'under'} the "
                    f"{tj_max:.0f} C limit)"))
        elif tj_lo >= tj_max:
            fails.append(f"{ref}: even the best-case junction {tj_lo:.0f} C exceeds "
                         f"{tj_max:.0f} C")
            line("FAIL", f"{ref} junction temperature",
                 f"{tj_lo:.0f} C BEST case exceeds the {tj_max:.0f} C limit - "
                 f"no layout fixes this")
        elif tj_hi >= tj_max:
            notes.append(f"{ref}: worst-case junction {tj_hi:.0f} C exceeds "
                         f"{tj_max:.0f} C on JEDEC copper - MEASURE IT at T3")
            line("warn", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case EXCEEDS the {tj_max:.0f} C limit on "
                 f"JEDEC copper; {tj_mid_hi:.0f} C on EVM-class copper. This board is "
                 f"6-layer with planes, so the truth is nearer the low end - but that is "
                 f"an opinion until T3 measures it", spec["src"])
        elif tj_hi >= tj_max - 30:
            notes.append(f"{ref}: {tj_hi:.0f} C leaves under 30 C of margin")
            line("warn", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case - under 30 C of margin. MEASURE IT at T3",
                 spec["src"])
        else:
            line("ok", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case, {tj_max-tj_hi:.0f} C of margin", spec["src"])
        print()

    # ------------------------------------------------------------------ the LDOs ---
    print("=== linear regulator dissipation ===")
    print(f"      both LDOs drop {design.LDO_DROP_V:.1f} V from +5V, ambient "
          f"{T_AMBIENT_STACK:.0f} C [A]\n")

    for ref, rail, loads in (("U9", "+3V3", design.LOADS_3V3),
                             ("U10", "+3V3A", design.LOADS_3V3A)):
        part = design.COMPONENTS[ref][2]
        spec = design.LDO_SPEC.get(part)
        if not spec:
            fails.append(f"{ref}: {part} has no entry in design.LDO_SPEC - an "
                         f"unclassified regulator is not a checked one")
            line("FAIL", f"{ref} unclassified", f"{part} is not in design.LDO_SPEC")
            continue
        pkg, theta_min, theta_good, theta_src, tj_max, i_max, spec_src = spec
        i_cont = sum(x[1] for x in loads)
        i_peak = sum(x[2] for x in loads)
        p_cont, p_peak = i_cont * design.LDO_DROP_V, i_peak * design.LDO_DROP_V
        # Four corners, exactly as for the bucks.
        tj_cont = T_AMBIENT_STACK + p_cont * theta_good     # best case
        tj_peak = T_AMBIENT_STACK + p_peak * theta_good     # good copper, peak load
        tj_cont_bad = T_AMBIENT_STACK + p_cont * theta_min
        tj_peak_bad = T_AMBIENT_STACK + p_peak * theta_min  # worst case

        print(f"  {ref} {rail}  {part} in {pkg}")
        for name, ic, ip, src in loads:
            print(f"      {name:34} {ic*1e3:6.0f} mA cont {ip*1e3:6.0f} mA peak  {src}")
        print(f"      {'TOTAL':34} {i_cont*1e3:6.0f} mA cont {i_peak*1e3:6.0f} mA peak")
        print(f"      Pd {p_cont*1e3:.0f} mW cont / {p_peak*1e3:.0f} mW peak at "
              f"{design.LDO_DROP_V:.1f} V drop")
        print(f"      theta_JA {theta_good} C/W (good copper) to {theta_min} C/W "
              f"(minimal copper)")
        print(f"      junction, good copper : {tj_cont:.0f} C cont / {tj_peak:.0f} C peak")
        print(f"      junction, min  copper : {tj_cont_bad:.0f} C cont / "
              f"{tj_peak_bad:.0f} C peak      against {tj_max:.0f} C")

        if i_peak > i_max:
            fails.append(f"{ref}: peak {i_peak*1e3:.0f} mA exceeds the part's "
                         f"{i_max*1e3:.0f} mA rating")
            line("FAIL", f"{ref} output current",
                 f"{i_peak*1e3:.0f} mA peak against a {i_max*1e3:.0f} mA part")
        else:
            line("ok", f"{ref} output current",
                 f"{i_peak*1e3:.0f} mA peak of {i_max*1e3:.0f} mA "
                 f"({i_peak/i_max*100:.0f}%)", spec_src)

        # Fail only when no plausible copper saves it - the good-copper corner over the limit.
        if tj_cont >= tj_max:
            fails.append(f"{ref}: CONTINUOUS junction {tj_cont:.0f} C exceeds "
                         f"{tj_max:.0f} C even on good copper")
            line("FAIL", f"{ref} junction temperature",
                 f"{tj_cont:.0f} C at the CONTINUOUS load on GOOD copper exceeds "
                 f"{tj_max:.0f} C - that is the steady state, not a transient, and no "
                 f"pour fixes it", theta_src)
        elif tj_peak >= tj_max:
            fails.append(f"{ref}: peak junction {tj_peak:.0f} C exceeds {tj_max:.0f} C "
                         f"on good copper")
            line("FAIL", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C at PEAK load on GOOD copper exceeds {tj_max:.0f} C",
                 theta_src)
        elif tj_peak_bad >= tj_max:
            notes.append(f"{ref}: peak junction reaches {tj_peak_bad:.0f} C on MINIMAL "
                         f"copper against {tj_max:.0f} C, {tj_peak:.0f} C on good copper "
                         f"- measure at T3a")
            line("warn", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C peak on good copper ({tj_max-tj_peak:.0f} C margin) "
                 f"but {tj_peak_bad:.0f} C on the datasheet's 'no heatsink' figure. This "
                 f"board measures 7443 mm2 of GND plane and 5 vias on the output pad "
                 f", so the good end is the expected one - "
                 f"but the AP2112 has OTSD, so being wrong means a mid-flight BROWNOUT, "
                 f"not smoke. U19 (TMP119) sits 3.9 mm away in the same GND pour and "
                 f"logs this neighbourhood every flight - see TEMP_LOG in defaults.parm",
                 theta_src)
        elif tj_peak >= tj_max - 25:
            notes.append(f"{ref}: {tj_peak:.0f} C peak leaves under 25 C of margin")
            line("warn", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C peak - under 25 C of margin. MEASURE IT at T3",
                 theta_src)
        else:
            line("ok", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C peak, {tj_max-tj_peak:.0f} C of margin", theta_src)
        print()

    print("=== what this check cannot do ===")
    line("note", "RDS(on) and edge rate are [A]",
         "the component figure implies ~97% efficiency, optimistic for this part. "
         "RDS(on) is CONFIRMED [D] per part in design.BUCK_THERMAL (the fitted "
         "LMR33630A: SLVSD26 5.5 gives 148/78 mOhm, SNVSAN3F 7.5 gives 75/50 typ); "
         "T_EDGE is still [A] and "
         "gate-charge, dead-time and Coss losses are not modelled at all - which is why "
         "the efficiency-band figure, not this one, drives the verdict")
    line("note", "theta_JA is JEDEC-board, not THIS board",
         "the fitted LMR33630A carries ONE theta_JA from its own datasheet (72.5 C/W, "
         "RNX on a 4-layer JEDEC board - no EVM figure, so one honest number rather "
         "than a bracket invented from two). The copper under U8 and U20 here differs "
         "from that JEDEC board, so treat the figure as what the T3 measurement "
         "validates, not gospel")
    line("note", "airflow is assumed to be NONE",
         "the stack sits between the ESC and the battery. A hovering quad moves air "
         "downward past it, which helps, but by an amount nobody here has measured")
    line("note", "U19 watches U9, and ONLY U9",
         "U19 is 3.9 mm from U9 and 17.2 mm from U8, so it is a U9 sensor and not a "
         "board-wide one. It also reads the BOARD, not the junction: it cannot see "
         "through a package. What it gives is a logged trend from every flight instead "
         "of one bench reading, which is what turns this from an open question into a "
         "number that would have to get worse in front of you")
    line("note", "what still wants a thermocouple",
         "U8 has no sensor near it, and the board-to-junction offset at U9 is still "
         "unmeasured. Both are one bench session at runbook T3a - powered, stack "
         "assembled, logging to the card so U9 sees its real duty, 10 minutes. After "
         "that the offset is known and U19 carries it forward on its own")

    print()
    if fails:
        print(f"FAIL - {len(fails)} thermal problem(s)")
        for f in fails:
            print("  - " + f)
        return 1
    if notes:
        print(f"{len(notes)} margin warning(s) - measure before trusting:")
        for n in notes:
            print("  - " + n)
    print("no thermal limit exceeded on the stated assumptions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
