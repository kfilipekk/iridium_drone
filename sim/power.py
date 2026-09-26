"""Power-stage simulations: battery inrush, and both buck output filters.

Deck values come from tools/design.py. The buck is modelled open-loop: the
switch node is a square wave 0 <-> Vin at D = Vout/Vin, into the fitted inductor
and output caps. That is the right model for *the output filter* (inductor peak
current, output ripple); it says nothing about the regulator's own loop, which is
internally compensated and not modelled here.
"""
import ngspice
from circuits import design

D = design()

# Fitted parts (see design.py): both rails are LMR33630A @ 400 kHz.
FSW = D.BUCK_THERMAL["LMR33630A"]["fsw"]
# Output-cap ESR: a 22 uF 1206 X5R MLCC is a few mOhm. 3 mOhm is the value the
# earlier hand analysis used; it is an assumption, not a datasheet number.
ESR = 0.003
# Battery: 4S and 5S full charge, from design.NET_VMAX (`CELLS * 4.2`).
VIN_4S, VIN_5S = 4 * 4.2, 5 * 4.2


def _kick(vin, vout, fsw, L, C, esr, iout, tstop=8e-3):
    ton = (vout / vin) / fsw
    period = 1.0 / fsw
    net = f"""* buck output filter
Vsw sw 0 PULSE(0 {vin} 0 5n 5n {ton:.6g} {period:.6g})
L1  sw out {L}
C1  out n1 {C}
R1  n1 0 {esr}
Rload out 0 {vout / iout:.6g}
.ic v(out)={vout} v(n1)={vout}
.tran 5n {tstop} uic
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    t = r["time"]
    # Measure over the last switching period, once the LC tank has settled.
    k0 = next(i for i in range(len(t)) if t[i] >= t[-1] - period)
    il = r["l1#branch"][k0:]
    vo = r["out"][k0:]
    return max(il), min(il), max(vo), min(vo)


def out_filter(name, vin, vout, L, C, iout):
    """Hand analysis vs ngspice for one rail at one input voltage."""
    ripple = (vin - vout) * (vout / vin) / (FSW * L)
    i_pk, i_valley = iout + ripple / 2, iout - ripple / 2
    i_rms = (iout ** 2 + ripple ** 2 / 12) ** 0.5
    v_ripple = ripple / (8 * FSW * C) + ripple * ESR
    sim_pk, sim_valley, sim_vmax, sim_vmin = _kick(vin, vout, FSW, L, C, ESR, iout)
    return {
        "name": name, "vin": vin, "vout": vout,
        "hand_i_pk": i_pk, "hand_i_valley": i_valley, "hand_i_ripple": ripple,
        "hand_i_rms": i_rms, "hand_v_ripple": v_ripple,
        "sim_i_pk": sim_pk, "sim_i_valley": sim_valley,
        "sim_v_ripple": sim_vmax - sim_vmin,
        "i_rated": D.RAIL_5V["irms_a"], "i_sat": D.RAIL_5V["isat_a"],
    }


def inrush():
    """VBAT applied at the XT60: C17 + C18 + C19, real MLCC ESR, a lead model."""
    c1, c2, c3 = D.COMPONENTS["C17"][2], D.COMPONENTS["C18"][2], D.COMPONENTS["C19"][2]
    net = f"""* VBAT inrush
Vbat src 0 PWL(0 0 1u 0 1.05u {VIN_5S})
Lw src a 300n
Rw a vin 0.020
C17 vin n17 {c1}
R17 n17 0 0.005
C18 vin n18 {c2}
R18 n18 0 0.005
C19 vin 0 {c3}
Rload vin 0 1e6
.tran 10n 400u uic
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    return max(abs(i) for i in r["vbat#branch"]), r["vin"][-1]


def main():
    print("Battery inrush at the XT60 (C17/C18/C19, lead 300 nH / 20 mOhm):")
    i_pk, v_fin = inrush()
    print(f"  peak inrush current: {i_pk:5.1f} A, settles to {v_fin:.3f} V\n")

    print(f"Buck output filters, LMR33630A @ {FSW/1e3:.0f} kHz, worst case 5S = {VIN_5S:.1f} V:")
    for name, L, C, iout, vout in (
        ("+5V        (U8, L2, C22+C23)", D.COMPONENTS["L2"][2], 22e-6 + 22e-6,
         D.INDUCTOR_LOAD_A["L2"], 5.016),
        ("+5V_PAYLOAD(U20,L5, C69+C70+C80)", D.COMPONENTS["L5"][2], 22e-6 + 22e-6 + 1e-6,
         D.INDUCTOR_LOAD_A["L5"], 5.016),
    ):
        Lh = {"10uH": 10e-6}[L]
        r = out_filter(name, VIN_5S, vout, Lh, C, iout)
        print(f"  {name}")
        print(f"    load {iout:.3f} A, switch D = {vout/VIN_5S:.3f}")
        print(f"    inductor ripple   hand {r['hand_i_ripple']:.3f} A   ngspice "
              f"{r['sim_i_pk']-r['sim_i_valley']:.3f} A")
        print(f"    peak inductor I   hand {r['hand_i_pk']:.3f} A   ngspice {r['sim_i_pk']:.3f} A"
              f"   (Isat {r['i_sat']:.1f} A)")
        print(f"    inductor I(rms)   hand {r['hand_i_rms']:.3f} A"
              f"   (rated {r['i_rated']:.1f} A)")
        print(f"    output ripple     hand {r['hand_v_ripple']*1e3:.2f} mV  ngspice "
              f"{r['sim_v_ripple']*1e3:.2f} mV")
        if r["sim_i_pk"] > r["i_sat"]:
            print("    *** peak exceeds inductor saturation")
        if r["hand_i_rms"] > r["i_rated"]:
            print("    *** RMS exceeds inductor rating")


if __name__ == "__main__":
    main()
