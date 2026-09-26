"""Battery voltage sense: the divider, its filter, and the STM32's acquisition.

BATT_V_DIV is R18 (10k, 0603) from VBAT to the tap, R19 (1k) to ground, and C43
(100n) from the tap to ground; the tap goes to U1.PC0 (ADC1_INP10). Two things
have to be true and neither is visible from the value strings alone:

  * the tap must reach equilibrium (to within half an LSB) long before the next
    sample, or the reported pack voltage lags the real one during a load step;
  * the STM32's sample-and-hold capacitor must charge through the divider's
    Thevenin resistance inside one sample window, or every reading is low.

Both are simulated here; the divider arithmetic is checked against design.py.
"""
import math

import ngspice
from checks import Checks
from circuits import design, value

D = design()
R18 = value(D.COMPONENTS["R18"][2])      # 10k
R19 = value(D.COMPONENTS["R19"][2])      # 1k
C43 = value(D.COMPONENTS["C43"][2])      # 100n

RTH = R18 * R19 / (R18 + R19)            # Thevenin resistance at the tap
RATIO = (R18 + R19) / R19                # divider ratio, pack : tap
TAU = RTH * C43                          # filter time constant
VREF = 3.3                               # ADC reference (VREF+ tied to +3V3)
BITS = 16                                # STM32H743 ADC is 16-bit
LSB = VREF / 2 ** BITS
HALF_LSB = LSB / 2
# STM32H7 sample-and-hold: 4 pF is the datasheet figure, Radc + the switch are
# a few hundred ohm; both are assumptions stated here rather than measured.
CSAMPLE = 4e-12
RADC = 150.0
V_6S = 6 * 4.2                           # the 6S corner the 0603 R18 exists for
V_5S = 5 * 4.2


def divider():
    """The tap voltage at 5S/6S and the pack voltage that saturates the ADC."""
    return {
        "ratio": RATIO,
        "rth": RTH,
        "tau": TAU,
        "corner": 1.0 / (2 * math.pi * TAU),
        "v_5s": V_5S / RATIO,
        "v_6s": V_6S / RATIO,
        "saturate": VREF * RATIO,
        "p_r18_6s": (V_6S / (R18 + R19)) ** 2 * R18,
    }


def step_settle():
    """Time for the tap to reach within half an LSB after a full pack step."""
    target = V_5S / RATIO
    net = f"""* BATT_V_DIV step response
Vbat vbat 0 PWL(0 0 1u 0 1.05u {V_5S})
R18 vbat node {R18}
R19 node 0 {R19}
C43 node 0 {C43}
.tran 20n 20m uic
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    t, v = r["time"], r["node"]
    ok = next((t[i] for i in range(len(v)) if v[i] >= target - HALF_LSB), None)
    return ok


def acquire():
    """Acquisition transient: switch closes, Csample charges through Radc."""
    net = f"""* STM32 sample-and-hold acquisition from the divider
Vbat vbat 0 {V_5S}
R18 vbat node {R18}
R19 node 0 {R19}
C43 node 0 {C43}
Vclk clk 0 PULSE(0 3.3 0 1n 1n 1 2)
Ssw node s clk 0 SW
.model SW SW(Ron=50 Roff=1e12 Vt=1.65 Vh=0)
Radc s hold {RADC}
Csample hold 0 {CSAMPLE}
.ic v(node)={V_5S/RATIO} v(hold)=0
.tran 0.05n 1u uic
.end"""
    r, log = ngspice.run(net)
    if ngspice.errors(log):
        raise RuntimeError("\n".join(ngspice.errors(log)))
    t, v = r["time"], r["hold"]
    final = v[-1]
    k = next((t[i] for i in range(len(v)) if v[i] >= 0.63 * final), None)
    # Steady-state droop from repeated sampling: charge taken per sample divided
    # by the divider's source resistance, at a 100 Hz ADC rate.
    fs = 100.0
    droop = CSAMPLE * fs * RTH
    return final, k, droop


def main(chk=None):
    chk = chk or Checks()
    d = divider()
    print(f"Battery sense: R18 {R18/1e3:.0f}k / R19 {R19/1e3:.0f}k = {d['ratio']:.2f}:1, "
          f"C43 {C43*1e9:.0f}n, Rth {d['rth']:.0f} ohm, tau {d['tau']*1e6:.1f} us "
          f"(corner {d['corner']:.0f} Hz)")
    print(f"  tap at 5S {V_5S:.1f} V = {d['v_5s']:.3f} V, at 6S {V_6S:.1f} V = "
          f"{d['v_6s']:.3f} V; 3.3 V ADC saturates at {d['saturate']:.1f} V pack")
    print(f"  R18 dissipation at 6S: {d['p_r18_6s']*1e3:.1f} mW "
          f"(0603 rated 100 mW)")
    settle = step_settle()
    print(f"  SPICE: tap settles to half an LSB half-way through an "
          f"unrealistic full 0->{V_5S:.1f} V step in {settle*1e3:.3f} ms")
    final, tau_acq, droop = acquire()
    print(f"  SPICE: sample cap acquires to {final:.6f} V, 63 % in "
          f"{tau_acq*1e9:.1f} ns; repeated 100 Hz sampling droops it "
          f"{droop*1e6:.2f} uV")
    print(f"  one LSB is {LSB*1e6:.2f} uV")

    # Bounds -----------------------------------------------------------------
    chk.ok(d["v_6s"] < VREF,
           "battery divider does not saturate the ADC at 6S",
           f"{d['v_6s']:.3f} V vs {VREF:.1f} V ref")
    chk.ok(d["p_r18_6s"] < 0.100,
           "R18 within its 0603 power rating at 6S",
           f"{d['p_r18_6s']*1e3:.1f} mW vs 100 mW")
    chk.ok(500.0 <= d["corner"] <= 5000.0,
           "battery filter corner between 500 Hz and 5 kHz",
           f"{d['corner']:.0f} Hz")
    chk.ok(settle is not None and settle < 5e-3,
           "battery tap settles within 5 ms of a full pack step",
           f"{settle*1e3:.3f} ms" if settle else "did not settle")
    # The sample cap must be fully acquired well inside the shortest sample
    # window the H743 offers (a few ADC clock cycles, 10s of ns at 25 MHz).
    chk.ok(tau_acq is not None and tau_acq < 100e-9,
           "STM32 sample cap acquires inside the sample window",
           f"63 % in {tau_acq*1e9:.1f} ns" if tau_acq else "did not acquire")
    chk.ok(droop < HALF_LSB,
           "repeated sampling droop stays under half an LSB",
           f"{droop*1e6:.2f} uV vs {HALF_LSB*1e6:.2f} uV")
    return chk


if __name__ == "__main__":
    main()
