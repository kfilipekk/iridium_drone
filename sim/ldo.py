"""Linear regulators: U9 (AP2112K-3.3 -> +3V3), U10 (TLV75533 -> +3V3A) and
U21 (XC6206P332MR -> +3V3_CAN).

`tools/check_thermal.py` already computes each LDO's dissipation and junction,
and `tools/check_topology.py` checks that an input and an output capacitor
exist. Neither can see the *dynamic* side, which is where a linear regulator
actually fails:

  * the datasheet-required output capacitance, and whether DC-bias derating
    leaves an effective value above the part's stability floor (the TLV755P
    states that floor explicitly: > 0.47 uF EFFECTIVE);
  * whether a load step stays inside the tolerance of what the rail feeds - on
    +3V3A that is the MAX2112, which is a +3.3 V +/-5 % part (3.13-3.47 V);
  * whether there is dropout margin at peak current.

The circuit models the LDO as an ideal regulator behind its datasheet load
regulation R_o, driving the capacitor bank the board actually fits on that net
(read from design.NETS, not typed in here). The ESL/ESR per package are
assumptions (stated below), and the loop's own transient recovery is bounded
separately rather than modelled - see the note at the end of `main`.
"""
import ngspice
from checks import Checks
from circuits import design, value

D = design()

# Per-package parasitics for a ceramic cap: ESR and ESL. 0402/0805/1206 are
# package-typical figures, not datasheet numbers for these exact parts.
PARASITIC = {
    "0402": (0.020, 0.6e-9),
    "0805": (0.010, 0.8e-9),
    "1206": (0.008, 1.0e-9),
}
# The +5 V buck feeds every LDO; allow +/-3 % for its own accuracy and load
# regulation, which is the input every dropout figure is measured against.
VIN_5V_MIN = 5.016 * 0.97
# A conservative upper bound on how long the LDO's loop may take to answer a
# load step. The code does not model the loop, so the deck alone would show the
# steady-state droop only; this brackets the transient the cap has to cover
# alone. 1 us is the slow end of what a small LDO's loop bandwidth implies.
T_LOOP = 1e-6

# Datasheet figures per rail. Every number is quoted at its point of use:
#   AP2112K-3.3   docs/datasheets/AP2112-DiodesInc.pdf
#   TLV75533      docs/datasheets/TLV755P-SBVS293.pdf
#   XC6206P332MR  docs/datasheets/XC6206-Torex-ETR0305.pdf
RAILS = (
    dict(ref="U9", part="AP2112K-3.3", vin="+5V", vout="+3V3", v=3.3,
         # [D] 600 mA minimum guaranteed output; Vdo 200 mV max at 300 mA;
         # load regulation 1 %/A max -> 0.033 V/A; output accuracy +/-1.5 %.
         i_rated=0.600, vdo=0.200, vdo_at=0.300, r_o=0.033, acc=0.015,
         cin_ref="C26", cout_ref="C27",
         cin_min=1e-6, cout_min=1e-6, cout_eff_min=None,
         v_lo=3.135, v_hi=3.465, psrr="65 dB at 1 kHz",
         loads=D.LOADS_3V3),
    dict(ref="U10", part="TLV75533", vin="+5V", vout="+3V3A", v=3.3,
         # [D] 500 mA output; COUT 1-200 uF nominal and > 0.47 uF EFFECTIVE;
         # load regulation 0.060 V/A; PSRR 46 dB at 100 kHz; dropout of the
         # 3.3 V option taken as <= 250 mV at 500 mA from Figure 5-13.
         i_rated=0.500, vdo=0.250, vdo_at=0.500, r_o=0.060, acc=0.010,
         cin_ref="C28", cout_ref="C29",
         cin_min=1e-6, cout_min=1e-6, cout_eff_min=0.47e-6,
         v_lo=3.13, v_hi=3.47, psrr="46 dB at 100 kHz",
         loads=D.LOADS_3V3A),
    dict(ref="U21", part="XC6206P332MR", vin="+5V_PAYLOAD", vout="+3V3_CAN", v=3.3,
         # [D] maximum output current 200 mA (3.0 V type; 500 mA absolute max,
         # 250 mA in SOT-23); Vdo 250 mV at 100 mA; ceramic-capacitor
         # compatible; maximum operating voltage 6.0 V. Load regulation has no
         # clean figure in the table, so R_o is a stated upper estimate.
         i_rated=0.200, vdo=0.250, vdo_at=0.100, r_o=0.300, acc=0.030,
         cin_ref="C80", cout_ref="C67",
         cin_min=1e-6, cout_min=1e-6, cout_eff_min=None,
         v_lo=3.0, v_hi=3.6, psrr="see the datasheet's Ripple Rejection curve",
         loads=(("SN65HVD230 (U11) on +3V3_CAN", D.NET_CURRENT["+3V3_CAN"],
                 D.NET_CURRENT["+3V3_CAN"], "[M] design.NET_CURRENT['+3V3_CAN']"),)),
)


def _parasitic(footprint):
    for pkg, (esr, esl) in PARASITIC.items():
        if pkg in footprint:
            return esr, esl
    return 0.020, 0.6e-9


def _bank(net):
    """(caps, total_C) for the fitted, non-DNP capacitors design.py puts on `net`."""
    caps = []
    for pin in D.NETS.get(net, []):
        ref = pin.split(".")[0]
        comp = D.COMPONENTS.get(ref)
        if not comp or not ref.startswith("C"):
            continue
        _sym, fp, val, _lcsc, dnp = comp
        if dnp:
            continue
        esr, esl = _parasitic(fp)
        caps.append((ref, value(val), esr, esl))
    return caps, sum(c for _, c, _, _ in caps)


def _droop_deck(rail):
    """Load-step transient: ideal regulator + R_o into the fitted cap bank."""
    caps, _total = _bank(rail["vout"])
    lines = [f"* LDO load step: {rail['ref']} {rail['part']} into {rail['vout']}",
             f"Vsrc ideal 0 {rail['v']}",
             f"Ro ideal rail {rail['r_o']}"]
    for ref, c, esr, esl in caps:
        lines += [f"L{ref} rail a{ref} {esl}",
                  f"R{ref} a{ref} b{ref} {esr}",
                  f"C{ref} b{ref} 0 {c}"]
    ipk = sum(x[2] for x in rail["loads"])
    lines += [f"Iload rail 0 PWL(0 0 1u 0 1.01u {ipk:.6g} 20u {ipk:.6g})",
              ".tran 2n 20u",
              ".end"]
    return "\n".join(lines)


def transient(rail):
    """Run the load step; return (settled, worst_droop, cap_total).

    The measurement window opens after the step, so the steady-state load
    regulation (I_peak * R_o) and any capacitor ringing land in the dip; the
    operating point is solved first (no `uic`), so the caps start charged.
    """
    deck = _droop_deck(rail)
    r, log = ngspice.run(deck)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    t, v = r["time"], r["rail"]
    after = [v[i] for i in range(len(t)) if t[i] >= 1.5e-6]
    _caps, total = _bank(rail["vout"])
    return v[-1], rail["v"] - min(after), total


def _window(rail):
    """Worst-case DC window and the peak output current, from the datasheet numbers."""
    i_cont = sum(x[1] for x in rail["loads"])
    i_peak = sum(x[2] for x in rail["loads"])
    lo = rail["v"] * (1 - rail["acc"]) - i_peak * rail["r_o"]
    hi = rail["v"] * (1 + rail["acc"])
    return i_cont, i_peak, lo, hi


def main(chk=None):
    chk = chk or Checks()
    for rail in RAILS:
        caps, total_c = _bank(rail["vout"])
        i_cont, i_peak, v_lo, v_hi = _window(rail)
        print(f"{rail['ref']}  {rail['part']}  {rail['vin']} -> {rail['vout']} "
              f"({rail['v']:.1f} V, {rail['i_rated']*1e3:.0f} mA rated)")
        print(f"  load {i_cont*1e3:.0f} mA cont / {i_peak*1e3:.0f} mA peak; "
              f"dropout {rail['vdo']*1e3:.0f} mV at {rail['vdo_at']*1e3:.0f} mA; "
              f"PSRR {rail['psrr']}")
        print(f"  datasheet caps: CIN >= {rail['cin_min']*1e6:.2f} uF, "
              f"COUT >= {rail['cout_min']*1e6:.2f} uF"
              + (f", effective > {rail['cout_eff_min']*1e6:.2f} uF"
                 if rail["cout_eff_min"] else ""))
        print(f"  fitted {rail['vout']} bank: {len(caps)} caps, {total_c*1e6:.2f} uF")

        # --- datasheet component requirements --------------------------------
        cin_ref, cout_ref = rail["cin_ref"], rail["cout_ref"]
        cin = value(D.COMPONENTS[cin_ref][2])
        cout = value(D.COMPONENTS[cout_ref][2])
        print(f"  fitted CIN {cin*1e6:.2f} uF, COUT {cout_ref} {cout*1e6:.2f} uF")
        chk.ok(cin >= rail["cin_min"],
               f"{rail['ref']} input capacitor meets the datasheet minimum",
               f"{cin*1e6:.2f} uF vs {rail['cin_min']*1e6:.2f} uF")
        chk.ok(cout >= rail["cout_min"],
               f"{rail['ref']} output capacitor meets the datasheet minimum",
               f"{cout_ref} {cout*1e6:.2f} uF vs {rail['cout_min']*1e6:.2f} uF")
        if rail["cout_eff_min"]:
            eff = cout * 0.5      # the datasheet's own blanket 50 % derating
            print(f"  effective COUT at the datasheet's 50 % derating: {eff*1e6:.2f} uF")
            chk.ok(eff >= rail["cout_eff_min"],
                   f"{rail['ref']} output capacitor above its effective stability floor",
                   f"{eff*1e6:.2f} uF vs {rail['cout_eff_min']*1e6:.2f} uF")
        chk.ok(i_peak <= rail["i_rated"],
               f"{rail['ref']} peak output current within the part rating",
               f"{i_peak*1e3:.0f} mA vs {rail['i_rated']*1e3:.0f} mA")

        # --- dropout and the DC rail window ----------------------------------
        margin = VIN_5V_MIN - rail["v"] - rail["vdo"]
        chk.ok(margin > 0,
               f"{rail['ref']} dropout margin at peak current",
               f"{VIN_5V_MIN:.2f} V in - {rail['v']:.1f} V out - "
               f"{rail['vdo']*1e3:.0f} mV = {margin:.2f} V")
        print(f"  dropout margin: {margin:.2f} V "
              f"({VIN_5V_MIN:.2f} V input, {rail['vdo']*1e3:.0f} mV needed)")
        print(f"  DC window over accuracy +/-{rail['acc']*100:.1f} % and peak load: "
              f"{v_lo:.3f} to {v_hi:.3f} V  (rail limit {rail['v_lo']:.2f}-"
              f"{rail['v_hi']:.2f} V)")
        chk.ok(rail["v_lo"] <= v_lo and v_hi <= rail["v_hi"],
               f"{rail['ref']} DC output stays inside the fed parts' tolerance",
               f"{v_lo:.3f}-{v_hi:.3f} V vs {rail['v_lo']:.2f}-{rail['v_hi']:.2f} V")

        # --- load step --------------------------------------------------------
        settled, droop, cap_total = transient(rail)
        loop = i_peak * T_LOOP / cap_total
        total_droop = droop + loop
        headroom = rail["v"] - rail["v_lo"]
        print(f"  SPICE load step 0 -> {i_peak*1e3:.0f} mA: settles to "
              f"{settled:.4f} V, dips {droop*1e3:.2f} mV; "
              f"loop-delay bracket +{loop*1e3:.2f} mV")
        chk.ok(total_droop < headroom,
               f"{rail['ref']} load step stays inside the rail tolerance",
               f"dip {total_droop*1e3:.2f} mV vs {headroom*1e3:.0f} mV of headroom")
        print()

    print("  The deck models the LDO as an ideal regulator behind its datasheet")
    print("  load regulation; it does NOT model the loop. The load-step transient")
    print(f"  above brackets the cap-alone response with a {T_LOOP*1e6:.0f} us loop-delay")
    print("  term, which dominates it. Real loop bandwidths are faster, so this is")
    print("  pessimistic. The DC window, dropout and cap checks do not need the loop.")
    return chk


if __name__ == "__main__":
    main()
