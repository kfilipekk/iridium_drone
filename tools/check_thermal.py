#!/usr/bin/env python3
"""Thermal check for the switching regulators and the 3V3 rail.

WHY THIS EXISTS. tools/check_ratings.py checks RESISTOR dissipation and nothing else.
Nothing looked at the two bucks, the H743, or the fact that this stack sits between a
60 A ESC and a battery with essentially no airflow. That is a gap in a board whose +5 V
rail steps 16.8 V down to 5 V at 1.19 A through a SOT-23-6.

WHAT IT FOUND. At first run - 85-90 % efficiency and a GUESSED theta_JA of 120 C/W -
the +5 V buck's junction bracketed 119-165 C against the TPS54202's 150 C absolute
maximum, with a 40 C in-stack ambient. Entirely unexamined before that. Two closures
since (2026-09-05): theta_JA was said to be read from SLVSD26, and the WS2812 load is
budgeted at strobe duty (60 mA average, not 300 mA).

CORRECTED 2026-09-05 (later the same day), against the vendored datasheet at
docs/datasheets/TPS54202-SLVSD26.pdf. The "89.2 C/W from SLVSD26" was not in SLVSD26 -
section 5.4 gives 118.6 C/W (JEDEC) and 57.2 C/W (EVM), and 89.2 is roughly their
average, matching neither. AND the 150 C it was judged against is the ABSOLUTE MAXIMUM;
section 5.3 puts the recommended operating junction limit at 125 C. Both errors ran the
same way - the comfortable "114 C with 36 C of margin" was the product of an optimistic
theta_JA and a destruct limit used as a design limit. The honest bracket is 70-139 C for
U8 against 125 C, which is a MEASURE-IT, not a pass. U18 reaches 158 C worst case if the
VTX rail is ever populated, past the 160 C thermal shutdown at the JEDEC corner.

HONESTY ABOUT THE INPUTS. RDS(on) IS now datasheet-confirmed - SLVSD26 5.5 gives
R(HSD) 148 mOhm and R(LSD) 78 mOhm, exactly the values used below. The edge rate remains
[A]. They bracket the answer rather than pin it:

    component-level with the [A] RDS(on):  202 mW  -> implies ~97 % efficiency
    datasheet-class efficiency 85-90 %:    660-880 mW

97 % is optimistic for this part class, so the truth is nearer the second. This check
therefore reports a RANGE and fails on the WORST case, because a thermal check that
quotes one number it cannot justify is worse than one that admits the bracket.

TO CLOSE IT: read RDS(on) and theta_JA from SLVSD26C, and put a thermocouple on U8 at
T3 in docs/BUILD.md with the aircraft powered and the stack assembled.

Run: python3 tools/check_thermal.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

VIN_4S = 16.8               # [M] 4S fully charged, design.BATT
F_SW = 500e3    # [D] SLVSD26 5.5, Fsw centre 500 kHz (390-630)                # [M] sim/outfilter.cir models the TPS54202 at 500 kHz

# [D] TI TPS54202: "integrated 148-mOhm high-side MOSFET and 78-mOhm low-side MOSFET",
# switching frequency "fixed to 500 kHz" - which also confirms sim/outfilter.cir's model.
# T_EDGE remains [A]: the datasheet does not give a single edge rate, and switching loss
# in a 16.8 V buck also includes gate charge, dead-time body-diode conduction and Coss
# losses that this simple model does not capture. That is why the bracket below is wide.
# [D] SLVSD26 5.5: R(HSD) 148 mOhm, R(LSD) 78 mOhm at TA=25 C. T_EDGE is [A].
RDS_HS, RDS_LS, T_EDGE = 0.148, 0.078, 10e-9
# [L] efficiency band for a 2 A synchronous buck at this step-down ratio
EFF_LO, EFF_HI = 0.85, 0.90
# THETA_JA WAS 89.2 C/W HERE, CITED AS "[D] TI SLVSD26 section 6.4". That number is not
# in the datasheet. SLVSD26 section 5.4 Thermal Information, DDC (SOT23) 6 PINS, gives
# RthetaJA = 118.6 C/W on the JEDEC board and RthetaJA_EVM = 57.2 C/W on TI's own EVM.
# 89.2 is roughly the average of the two and matches neither; it was 33% optimistic
# against the headline figure and it is what produced the comfortable "36 C of margin".
# The datasheet is vendored at docs/datasheets/TPS54202-SLVSD26.pdf - check it, do not
# take this comment's word for it.
#
# BOTH figures are kept because the spread is the finding. JEDEC is a 2-layer board with
# minimal copper; the EVM is a real 4-layer power layout. THIS board is 6-layer with GND
# and power planes, so the truth sits between them and much nearer the EVM - but "much
# nearer" is an opinion until a thermocouple says otherwise, which is what T3 is for.
THETA_JA_JEDEC = 118.6      # [D] SLVSD26 5.4, RthetaJA, JEDEC standard test board
THETA_JA_EVM   = 57.2       # [D] SLVSD26 5.4, RthetaJA_EVM, TI's official EVM board
#
# T_JUNCTION_MAX WAS 150.0, TAGGED "absolute maximum" - and designing against an absolute
# maximum is designing with zero margin, because it is a DESTRUCT limit, not an operating
# one. SLVSD26 5.3 Recommended Operating Conditions gives TJ -40 to 125 C; 5.1 Absolute
# Maximum gives 150 C; 5.5 gives thermal shutdown at 160 C rising. The design limit is
# 125 C. This is the same substitution as Isat-for-Irms that design.RAIL_5V exists to
# prevent, in the opposite direction.
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
        # Four corners: best = most efficient on the best-copper board, worst = least
        # efficient on the JEDEC board. The old code used ONE theta_JA and so reported a
        # spread that was only the efficiency band, hiding the much larger layout term.
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

        # A FAIL is reserved for "no plausible layout saves this": if even TI's own EVM
        # copper at the better efficiency runs hot, no amount of pouring fixes it. When
        # only the JEDEC corner is over, the answer genuinely depends on this board's
        # copper and the honest verdict is "measure it", not a number dressed as a fact.
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
    # This file's docstring has always claimed to cover "the switching regulators and
    # the 3V3 rail". The 3V3 rail appeared NOWHERE in the code. Both LDOs are linear and
    # both hang off +5V, so every milliamp they pass dissipates 1.7 V - and U9 carries
    # the MCU, the flash, the card and the CAN transceiver in a SOT-23-5 with no thermal
    # pad. It is very likely the hottest part on this board and it had never been
    # computed, let alone measured.
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
        # Four corners, exactly as for the bucks. Quoting only the "no heatsink" end
        # would be the single-theta_JA error this file was fixed for, sign-flipped.
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

        # FAIL only when no plausible copper saves it - the good-copper corner over the
        # limit. When only the minimal-copper corner is over, the answer depends on this
        # board's copper, and tools/thermal_vias.py measures that rather than assuming it.
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
                 f"not smoke. MEASURE IT at T3a", theta_src)
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
    line("note", "MEASURE IT",
         "thermocouple on U8 AND U9 at docs/BUILD.md T3a, powered, stack assembled, "
         "logging to the card so U9 sees its real duty, 10 minutes")

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
