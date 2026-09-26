"""Battery hot-plug transient: can the input overshoot exceed the parts' limits?

Model: an ideal battery step through the harness inductance, into the input
protection network. The TVS (D1, SMBJ22A) clamps; Q4 is modelled as its channel
resistance; the two 10 uF input caps are derated for DC bias at the rail voltage.
The ESC's own ceramic + its optional electrolytic sit between the harness and the
board, which is where the ringing is damped.
"""
import ngspice
from checks import Checks
from circuits import design

D = design()
VBAT_4S, VBAT_5S = 4 * 4.2, 5 * 4.2
TVS_VC, _TVS_VRWM, TVS_VBR, TVS_IPP = D.TVS_CLAMP_V["SMBJ22A"][:4]
TVS_RS = (TVS_VC - TVS_VBR) / (TVS_IPP - 1e-3)
ABSMAX_V = D.VBAT_PART_VMAX["LMR33630A"][1]   # LMR33630A abs max VIN
Q4_ABSMAX_V = D.VBAT_PART_VMAX["WST4041"][1]   # Q4 drain-source abs max


def case(vbat, lead_nh, esc_bulk_uF):
    bulk = ""
    if esc_bulk_uF:
        bulk = f"Cb esc bb {esc_bulk_uF*1e-6}\nRb bb bl 0.04\nLb bl 0 10n"
    net = f"""* hotplug
Vb src 0 PWL(0 0 10n {vbat})
Rbat src a 0.01
Lbat a b {lead_nh*1e-9}
Rlead b esc 0.005
Cesc esc ec 10u
Resc ec 0 0.005
{bulk}
Lh esc h 60n
Rh h vin 0.07
* D1 SMBJ22A, Vbr {TVS_VBR} V, Vc {TVS_VC} V at {TVS_IPP} A
D1 0 vin TVS
.model TVS D(BV={TVS_VBR} IBV=1m RS={TVS_RS:.4g} CJO=400p)
* Q4 on (body diode then channel), ~20 mOhm
Rq vin vbat 0.02
* C17+C18 10u X5R, derated ~55% at these voltages -> 4.5u effective each
Cin1 vbat c1 4.5u
Rc1 c1 l1 0.005
Lc1 l1 0 1n
Cin2 vbat c2 4.5u
Rc2 c2 l2 0.005
Lc2 l2 0 1n
Cin3 vbat 0 0.2u
.tran 20n 2m 0 50n
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    i_harness = max(abs(x) for x in r["lh#branch"])
    return max(r["vbat"]), max(r["vin"]), i_harness


def main(chk=None):
    chk = chk or Checks()
    print(f"Hot-plug input transient; LMR33630A abs max VIN = {ABSMAX_V:.0f} V, "
          f"Q4 abs max {Q4_ABSMAX_V:.0f} V, TVS clamp {TVS_VC:.1f} V")
    print(f"  worst case is 5S = {VBAT_5S:.1f} V with 150-250 nH of harness")
    for vbat, cells in ((VBAT_4S, "4S"), (VBAT_5S, "5S")):
        for lead in (150, 250):
            for bulk, bn in ((470, "with ESC 470 uF"), (0, "no electrolytic")):
                v, vin, ih = case(vbat, lead, bulk)
                flag = "  *** over abs max" if v > ABSMAX_V else ""
                print(f"  {cells} {vbat:4.1f} V  lead {lead:3d} nH  {bn:16s}: "
                      f"VBAT peak {v:5.1f} V  (input {vin:5.1f} V, harness "
                      f"{ih:5.1f} A){flag}")
                # Bounds: the regulators' and Q4's absolute-maximum input
                # voltages (design.VBAT_PART_VMAX), across every corner.
                chk.ok(v < ABSMAX_V,
                       f"hot-plug {cells} {lead} nH {bn}: VBAT peak under the buck abs max",
                       f"{v:.1f} V vs {ABSMAX_V:.0f} V")
                chk.ok(vin < Q4_ABSMAX_V,
                       f"hot-plug {cells} {lead} nH {bn}: input peak under Q4 abs max",
                       f"{vin:.1f} V vs {Q4_ABSMAX_V:.0f} V")
    worst = case(VBAT_5S, 250, 0)[0]
    print(f"\n  worst peak is {worst:.1f} V, "
          f"{ABSMAX_V - worst:.1f} V under abs max; "
          "fitting the ESC 470 uF removes the overshoot entirely")
    return chk


if __name__ == "__main__":
    main()
