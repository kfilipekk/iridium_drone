#!/usr/bin/env python3
"""Thermal check for the switching regulators and the 3V3 rail.

Run: python3 tools/check_thermal.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

VIN_4S = 16.8               # [M] 4S fully charged, design.BATT
F_SW = 500e3

RDS_HS, RDS_LS, T_EDGE = 0.148, 0.078, 10e-9
# [L] efficiency band for a 2 A synchronous buck at this step-down ratio
EFF_LO, EFF_HI = 0.85, 0.90
THETA_JA_JEDEC = 118.6      # [D] SLVSD26 5.4, RthetaJA, JEDEC standard test board
THETA_JA_EVM   = 57.2       # [D] SLVSD26 5.4, RthetaJA_EVM, TI's official EVM board
T_JUNCTION_MAX    = 125.0   # [D] SLVSD26 5.3 Recommended Operating Conditions
T_JUNCTION_ABSMAX = 150.0   # [D] SLVSD26 5.1 Absolute Maximum Ratings
T_SHUTDOWN        = 160.0   # [D] SLVSD26 5.5, thermal shutdown rising
T_AMBIENT_STACK = 40.0      # [A] inside a stack between an ESC and a battery, no airflow

fails, notes = [], []


def line(status, name, detail, src=""):
    print(f"  {status:5s} {name:38s} {detail}")
    if src:
        print(f"        {src}")


def main():
    print("=== switching regulator dissipation ===")
    print(f"      Vin {VIN_4S} V (4S), fsw {F_SW/1e3:.0f} kHz, ambient "
          f"{T_AMBIENT_STACK:.0f} C [A]")
    print(f"      theta_JA {THETA_JA_EVM} C/W (EVM board) to {THETA_JA_JEDEC} C/W "
          f"(JEDEC board) [D SLVSD26 5.4]")
    print(f"      limits: {T_JUNCTION_MAX:.0f} C recommended operating, "
          f"{T_JUNCTION_ABSMAX:.0f} C absolute max, {T_SHUTDOWN:.0f} C thermal "
          f"shutdown [D SLVSD26 5.1/5.3/5.5]\n")

    rails = [("U8", "+5V", 4.967, design.INDUCTOR_LOAD_A["L2"], False),
             ("U18", "+9V", 9.361, design.INDUCTOR_LOAD_A["L5"], not design.POPULATE_VTX)]

    for ref, rail, vout, iout, dnp in rails:
        pout = vout * iout
        D = vout / VIN_4S
        p_comp = iout**2 * RDS_HS * D + iout**2 * RDS_LS * (1 - D) \
            + 0.5 * VIN_4S * iout * T_EDGE * F_SW * 2
        p_lo = pout * (1 / EFF_HI - 1)      # 90 % efficiency
        p_hi = pout * (1 / EFF_LO - 1)      # 85 % efficiency
        tj_lo = T_AMBIENT_STACK + p_lo * THETA_JA_EVM       # best case
        tj_hi = T_AMBIENT_STACK + p_hi * THETA_JA_JEDEC     # worst case
        tj_mid_hi = T_AMBIENT_STACK + p_hi * THETA_JA_EVM   # good copper, poor efficiency

        tag = " (DNP on this build)" if dnp else ""
        print(f"  {ref} {rail}{tag}")
        print(f"      Pout {pout:.2f} W at D={D:.3f}")
        print(f"      Pd: {p_comp*1e3:.0f} mW component-level [D RDS(on), A edges]  vs  "
              f"{p_lo*1e3:.0f}-{p_hi*1e3:.0f} mW at {EFF_HI*100:.0f}-{EFF_LO*100:.0f}% "
              f"efficiency [L]")
        print(f"      junction {tj_lo:.0f} C best (EVM copper, {EFF_HI*100:.0f}%) .. "
              f"{tj_mid_hi:.0f} C (EVM copper, {EFF_LO*100:.0f}%) .. "
              f"{tj_hi:.0f} C worst (JEDEC copper, {EFF_LO*100:.0f}%), against "
              f"{T_JUNCTION_MAX:.0f} C")
        print(f"      the spread IS the finding - it needs measuring, not more arithmetic")

        if dnp:
            line("note", f"{ref} not fitted",
                 f"DNP - no dissipation on this build, but if the VTX rail is ever "
                 f"populated this part reaches {tj_hi:.0f} C worst case "
                 + ("(over the "
                    f"{T_SHUTDOWN:.0f} C thermal shutdown - it would hiccup)"
                    if tj_hi >= T_SHUTDOWN else
                    f"({'over' if tj_hi >= T_JUNCTION_MAX else 'under'} the "
                    f"{T_JUNCTION_MAX:.0f} C limit)"))
        elif tj_lo >= T_JUNCTION_MAX:
            fails.append(f"{ref}: even the best-case junction {tj_lo:.0f} C exceeds "
                         f"{T_JUNCTION_MAX:.0f} C")
            line("FAIL", f"{ref} junction temperature",
                 f"{tj_lo:.0f} C BEST case exceeds the {T_JUNCTION_MAX:.0f} C limit - "
                 f"no layout fixes this")
        elif tj_hi >= T_JUNCTION_MAX:
            notes.append(f"{ref}: worst-case junction {tj_hi:.0f} C exceeds "
                         f"{T_JUNCTION_MAX:.0f} C on JEDEC copper - MEASURE IT at T3")
            line("warn", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case EXCEEDS the {T_JUNCTION_MAX:.0f} C limit on "
                 f"JEDEC copper; {tj_mid_hi:.0f} C on EVM-class copper. This board is "
                 f"6-layer with planes, so the truth is nearer the low end - but that is "
                 f"an opinion until T3 measures it")
        elif tj_hi >= T_JUNCTION_MAX - 30:
            notes.append(f"{ref}: {tj_hi:.0f} C leaves under 30 C of margin")
            line("warn", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case - under 30 C of margin. MEASURE IT at T3")
        else:
            line("ok", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case, {T_JUNCTION_MAX-tj_hi:.0f} C of margin")
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
                         f"- run tools/thermal_vias.py for what this board actually has, "
                         f"and measure at T3a")
            line("warn", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C peak on good copper ({tj_max-tj_peak:.0f} C margin) "
                 f"but {tj_peak_bad:.0f} C on the datasheet's 'no heatsink' figure. This "
                 f"board measures 7443 mm2 of GND plane and 5 vias on the output pad "
                 f"(tools/thermal_vias.py), so the good end is the honest expectation - "
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
         "RDS(on) is CONFIRMED [D] SLVSD26 5.5 (148/78 mOhm); T_EDGE is still [A] and "
         "gate-charge, dead-time and Coss losses are not modelled at all - which is why "
         "the efficiency-band figure, not this one, drives the verdict")
    line("note", "theta_JA is JEDEC-board, not THIS board",
         f"{THETA_JA_JEDEC} C/W is SLVSD26's RthetaJA (JEDEC standard test board) and "
         f"{THETA_JA_EVM} C/W is its EVM figure. The copper under U8 here differs from "
         f"both, so treat the bracket as the range the T3 measurement "
         f"validates, not as gospel")
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
