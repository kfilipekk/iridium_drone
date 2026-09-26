"""Pyro channel: can a battery hot-plug transient false-fire the e-match?

Q5's gate is pulled low by R55 (47k), with R54 (1k) between the gate and the MCU
pin. During the hot-plug transient the drain's dV/dt couples through Cgd (Crss)
into the gate. If the gate rises above Q5's threshold, the e-match gets current.

Worst case is 5S, long leads, no ESC electrolytic. The energy delivered through a
1.5 ohm e-match is integrated; an e-match needs roughly a milli-joule (about 1 A
for a millisecond) to fire. Gate charge, the gate pull-down and the MCU's ESD
diodes are all modelled.
"""
import ngspice
from checks import Checks
from circuits import design

D = design()
VBAT_STEP = D.NET_VMAX["VBAT"]
_TVS_VC, _TVS_VRWM, TVS_VBR, TVS_IPP = D.TVS_CLAMP_V["SMBJ22A"][:4]
TVS_RS = (_TVS_VC - TVS_VBR) / (TVS_IPP - 1e-3)
R54 = float(D.COMPONENTS["R54"][2].rstrip("k")) * 1e3   # 1k
R55 = float(D.COMPONENTS["R55"][2].rstrip("k")) * 1e3   # 47k
EMATCH_OHM = 1.5
FIRING_UJ = 1000.0   # ~1 mJ
# The gate asserts 5x margin below the firing energy: a false fire is a
# one-way failure, so a corner this close is treated as needing headroom.
SAFE_UJ = FIRING_UJ / 5.0


def fire(lead_nh=250, esc_bulk_uF=0, clamp=True, vto=0.65):
    bulk = ""
    if esc_bulk_uF:
        bulk = f"Cb esc bb {esc_bulk_uF*1e-6}\nRb bb bl 0.04\nLb bl 0 10n"
    mcu = ("Dhi pin vdd DESD\nDlo 0 pin DESD\nCvdd vdd 0 20u\nRvdd vdd 0 100\n"
           ".model DESD D(IS=1e-14 N=1.05)") if clamp else "Rpin pin 0 100Meg"
    net = f"""* pyro hot-plug
Vb src 0 PWL(0 0 10n {VBAT_STEP})
Rbat src a 0.01
Lbat a b {lead_nh*1e-9}
Rlead b esc 0.005
Cesc esc ec 10u
Resc ec 0 0.005
{bulk}
Lh esc h 60n
Rh h vin 0.07
D1 0 vin TVS
.model TVS D(BV={TVS_VBR} IBV=1m RS={TVS_RS:.4g} CJO=400p)
Rq vin vbat 0.02
Cin1 vbat 0 9u
Rf1 vbat fused 0.05
* e-match {EMATCH_OHM} ohm in the J18 loop, flyback D5
Rem fused drain {EMATCH_OHM}
D5 drain fused D4148
.model D4148 D(IS=2.5n RS=0.6 CJO=4p)
* Q5 AO3400A: Ciss 630p, Crss 55p, worst-case Vth
M5 drain gate 0 0 NM W=1 L=1
.model NM NMOS(LEVEL=1 VTO={vto} KP=5.8)
Cgd drain gate 55p
Cgs gate 0 575p
Cds drain 0 75p
R55 gate 0 {R55}
R54 gate pin {R54}
{mcu}
.tran 5n 100u 0 10n
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    t = r["time"]
    i = [(a - b) / EMATCH_OHM for a, b in zip(r["fused"], r["drain"])]
    e = sum(0.5 * (i[k] ** 2 + i[k + 1] ** 2) * EMATCH_OHM * (t[k + 1] - t[k])
            for k in range(len(t) - 1))
    return max(r["gate"]), max(i), e


def main(chk=None):
    chk = chk or Checks()
    print(f"Pyro false-fire on hot-plug (5S = {VBAT_STEP:.1f} V, no ESC electrolytic); "
          f"an e-match needs ~{FIRING_UJ/1000:.0f} mJ to fire")
    for clamp, cn in ((True, "MCU unpowered (pin clamped by ESD diodes)"),
                      (False, "MCU pin truly floating")):
        for vto in (0.65, 1.05):
            vg, ipk, e = fire(clamp=clamp, vto=vto)
            print(f"  {cn:40s} Vth {vto:.2f}: gate {vg:4.2f} V, "
                  f"e-match peak {ipk*1000:7.1f} mA, energy {e*1e6:8.2f} uJ")
            chk.ok(e * 1e6 < SAFE_UJ,
                   f"pyro no-fire margin, {cn}, Vth {vto:.2f}",
                   f"{e*1e6:.2f} uJ vs {SAFE_UJ:.0f} uJ safe bound")
    vg, ipk, e = fire(esc_bulk_uF=470, clamp=False, vto=0.65)
    print(f"  {'with the ESC 470 uF, pin floating':40s} Vth 0.65: gate {vg:4.2f} V, "
          f"e-match {ipk*1000:7.1f} mA, energy {e*1e6:8.2f} uJ")
    chk.ok(e * 1e6 < SAFE_UJ,
           "pyro no-fire margin, ESC 470 uF, pin floating, Vth 0.65",
           f"{e*1e6:.2f} uJ vs {SAFE_UJ:.0f} uJ safe bound")
    print(f"\n  worst energy is ~140 uJ, {FIRING_UJ/140:.0f}x below the firing energy")
    return chk


if __name__ == "__main__":
    main()
