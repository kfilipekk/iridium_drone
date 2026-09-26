"""Tuner baseband: the OPA2374 difference amplifier between the MAX2112 and the
STM32 ADC.

U14 is a dual op-amp wired as two difference amplifiers:
  I channel: IOUT+/- through R36/R37 (4k7), feedback R50 (10k), R51 (10k) to
  BB_VREF; Q channel identical with R47/R31/R48/R49. So the differential gain is
  Rf/Rin = 10k/4k7 = 2.13, referenced to BB_VREF (R52/R53 halve +3V3A).

The datasheet says to AC-couple IOUT/QOUT with 47 nF to the demodulator. This
board DC-couples them into the difference amp instead. The difference amp rejects
the *common-mode* DC, so the question is only about differential DC offset, which
the tuner's own IDC/QDC correction loop (C61/C63) is meant to null. This sim
measures the gain, the DC range at the ADC, and the common-mode rejection.
"""
import math

import ngspice
from checks import Checks
from circuits import design, value

D = design()
RIN = value(D.COMPONENTS["R36"][2])    # 4k7
RF = value(D.COMPONENTS["R50"][2])     # 10k
C76 = value(D.COMPONENTS["C76"][2])    # 100p
VREF = 3.3 * value(D.COMPONENTS["R53"][2]) / (
    value(D.COMPONENTS["R52"][2]) + value(D.COMPONENTS["R53"][2]))
VCM = 1.65                             # tuner output common mode (assumed ~VCC/2)
VADC_MIN, VADC_MAX = 0.0, 3.3
OPAMP_OPEN_LOOP = 1e6


def _netlist(vd_dc, vd_ac, common_ac):
    """Difference amp; Vd drives differentially, the common term moves both sides."""
    return f"""* baseband difference amplifier
Vd   d   0 dc {vd_dc} ac {vd_ac}
Vcm  c   0 dc {VCM}  ac {common_ac}
Bp   iout_p 0 V = V(c) + V(d)/2
Bn   iout_n 0 V = V(c) - V(d)/2
R36 iout_p opa_p {RIN}
R51 opa_p vref {RF}
R37 iout_n opa_n {RIN}
R50 opa_n adc {RF}
C76 opa_n adc {C76}
E1  adc 0 opa_p opa_n {OPAMP_OPEN_LOOP}
Vref vref 0 {VREF}"""


def dc_transfer():
    r, log = ngspice.run(_netlist(0, 0, 0) + "\n.dc Vd -1.6 1.6 0.02\n.end")
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    return r["v-sweep"], r["adc"]


def ac_analysis():
    r, log = ngspice.run(_netlist(0, 1, 0) + "\n.ac dec 200 10 100Meg\n.end")
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    f = [x.real for x in r["frequency"]]
    mag = [abs(x) for x in r["adc"]]
    gain = mag[0]
    k = next(i for i in range(len(mag) - 1)
             if mag[i] >= gain / math.sqrt(2) > mag[i + 1])
    r2, log2 = ngspice.run(_netlist(0, 0, 1) + "\n.ac dec 200 10 100Meg\n.end")
    if ngspice.errors(log2):
        raise RuntimeError("\n".join(ngspice.errors(log2)))
    return gain, f[k], abs(r2["adc"][0])


def main(chk=None):
    chk = chk or Checks()
    vd, vout = dc_transfer()
    # gain from the two points either side of zero
    z = min(range(len(vd)), key=lambda i: abs(vd[i]))
    gain = (vout[z + 1] - vout[z - 1]) / (vd[z + 1] - vd[z - 1])
    at_zero = vout[z]
    span = min(at_zero - VADC_MIN, VADC_MAX - at_zero)
    lo, hi = min(vout), max(vout)
    print(f"Baseband difference amp: Rin {RIN/1e3:.1f}k, Rf {RF/1e3:.0f}k, "
          f"Vref {VREF:.3f} V (R52/R53)")
    print(f"  differential gain: {gain:.3f}  (Rf/Rin = {RF/RIN:.3f})")
    print(f"  output at zero differential input: {at_zero:.3f} V")
    print(f"  output range over +/-1.6 V differential: {lo:.2f} to {hi:.2f} V; "
          f"ADC is {VADC_MIN:.0f}-{VADC_MAX:.0f} V")
    print(f"  usable differential input before the ADC clips: "
          f"+/-{span/gain:.3f} V")
    g, corner, cm_gain = ac_analysis()
    print(f"  AC differential gain {g:.3f}, -3 dB corner {corner/1e3:.1f} kHz")
    cMRR = 20 * math.log10(gain / max(cm_gain, 1e-12))
    print(f"  common-mode gain {cm_gain*1e3:.4f} mV/V -> CMRR {cMRR:.0f} dB")
    print("\n  datasheet: AC-couple IOUT/QOUT with 47 nF. This board DC-couples.")
    print("  The common-mode DC is rejected by the difference amp, but any")
    print(f"  differential DC offset is amplified by {gain:.2f} with no high-pass,")
    print(f"  so the tuner's IDC/QDC loop must null it: {gain:.2f} x 10 mV offset")
    print("  costs 21 mV of ADC range. The 47 nF coupling in the datasheet is")
    print("  the app note's demodulator input, not this op-amp stage.")
    # Bounds: the four-resistor difference amp's own arithmetic (gain must equal
    # Rf/Rin), a reference that centres the ADC, enough headroom for the tuner's
    # 1 Vpp differential output, common-mode rejection, and the anti-alias corner
    # chosen to sit below the H743's sample rate but above the burst bandwidth.
    chk.ok(abs(gain - RF / RIN) / (RF / RIN) < 0.02,
           "baseband gain equals Rf/Rin",
           f"sim {gain:.3f} vs Rf/Rin {RF/RIN:.3f}")
    chk.ok(abs(at_zero - (VADC_MIN + VADC_MAX) / 2) < 0.1,
           "baseband output quiescent at ADC mid-scale",
           f"{at_zero:.3f} V vs {(VADC_MIN+VADC_MAX)/2:.3f} V")
    chk.ok(span / gain >= 0.5,
           "baseband headroom covers the tuner's 1 Vpp output",
           f"+/-{span/gain:.3f} V vs +/-0.5 V")
    chk.ok(cMRR >= 80.0, "baseband common-mode rejection above 80 dB",
           f"{cMRR:.0f} dB")
    chk.ok(100e3 <= corner <= 250e3,
           "baseband anti-alias corner between 100 and 250 kHz",
           f"{corner/1e3:.1f} kHz")
    return chk


if __name__ == "__main__":
    main()
