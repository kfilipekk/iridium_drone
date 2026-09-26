"""MAX2112 PLL loop-filter stability: phase margin across the charge-pump
current and VCO-gain range.

The loop filter is third-order passive: C81 at CPOUT, then R34 + C57 in series,
then R57 + C56 to VTUNE. Its impedance Z(s) is found with an AC analysis by
injecting 1 A into CPOUT. The open-loop gain is G = Icp * Kv * Z / (s / (2*pi) * N),
with Kv the LO-referred gain in Hz/V and N the divider. The unity-gain crossing
gives the loop bandwidth and phase margin.

Loop values come from design.py; Icp, Kv and N from the MAX2112 datasheet.
"""
import cmath
import math

import ngspice
from circuits import design

D = design()
C81 = D.COMPONENTS["C81"][2]
R34 = D.COMPONENTS["R34"][2]
C57 = D.COMPONENTS["C57"][2]
R57 = D.COMPONENTS["R57"][2]
C56 = D.COMPONENTS["C56"][2]

LO_HZ = 1626e6          # Iridium downlink, inside the MAX2112's 925-2175 MHz range
FREF_HZ = 25e6          # Y2 TCXO
N = LO_HZ / FREF_HZ
# Icp from Table 8 (600 uA or 1200 uA). Kv LO-referred, from the VCO KV vs VTUNE
# plot: sub-band 0 is ~25 MHz/V, the sub-band covering 1626 MHz (sub-band ~13) is
# 100-200 MHz/V, the top sub-bands reach 400 MHz/V.
ICP_OPTIONS = (600e-6, 1200e-6)
KV_OPTIONS = (25e6, 50e6, 100e6, 150e6, 200e6)


def loop_impedance():
    r, log = ngspice.run(f"""* pll loop filter
Icp 0 cp AC 1
C81 cp 0 {C81}
R34 cp loop {R34}
C57 loop 0 {C57}
R57 cp vt {R57}
C56 vt 0 {C56}
.ac dec 400 100 100Meg
.end""")
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    f = [x.real for x in r["frequency"]]
    return f, r["vt"]


def analyse():
    f, Z = loop_impedance()
    rows = []
    for icp in ICP_OPTIONS:
        for kv in KV_OPTIONS:
            G = [icp * kv * z / (1j * f[k] * N) for k, z in enumerate(Z)]
            k = next(i for i in range(len(G) - 1) if abs(G[i]) >= 1 > abs(G[i + 1]))
            pm = 180 + math.degrees(cmath.phase(G[k]))
            rows.append((icp, kv, f[k], pm))
    return rows


def main():
    print(f"MAX2112 PLL at LO {LO_HZ/1e6:.0f} MHz, Fref {FREF_HZ/1e6:.0f} MHz, N = {N:.2f}")
    print(f"  loop filter: C81 {C81} / R34 {R34} + C57 {C57} / R57 {R57} + C56 {C56}")
    print("  (stable above ~30 deg; good design 45-70; bandwidth must stay "
          f"well under Fref/10 = {FREF_HZ/10e6:.1f} MHz)")
    worst = 180.0
    for icp, kv, bw, pm in analyse():
        print(f"  Icp {icp*1e6:5.0f} uA  Kv {kv/1e6:4.0f} MHz/V: "
              f"bandwidth {bw/1e3:7.1f} kHz, phase margin {pm:5.1f} deg"
              + ("   *** below 30 deg" if pm < 30 else ""))
        worst = min(worst, pm)
    print(f"\n  worst phase margin {worst:.1f} deg. The default registers leave "
          "CPS = VAS (charge-pump current chosen by the VCO autoselect), which\n"
          "  avoids the 1200 uA corner; forcing ICP = 1 (1200 uA) at high Kv is "
          "the case that goes marginal.")


if __name__ == "__main__":
    main()
