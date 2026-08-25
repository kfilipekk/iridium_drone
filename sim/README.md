# ngspice power-stage simulation

Run with KiCad's bundled `libngspice.so.0` via ctypes — the `ngspice` CLI is not
installed on this machine and does not need to be. `sim/run.py` drives it.

```bash
python3 sim/run.py sim/inrush.cir
python3 sim/run.py sim/outfilter.cir
```

## Why this exists

`tools/check_topology.py` was written after both buck regulators were found to be missing
their catch diode — a fault that survived 64 preflight checks because **every other check
verifies a property of what is present, and absence has no net to inspect.** Simulation is
the other way of catching that class of fault: a circuit that cannot work does not
simulate, whatever the netlist says.

## Results, against hand analysis

Component values come from `tools/design.py`; nothing here is invented.

### `inrush.cir` — VBAT applied at the XT60

C17 10 µF + C18 10 µF + C19 100 nF, 5 mΩ MLCC ESR each, lead modelled at 300 nH / 20 mΩ.

| | |
|---|---|
| **peak inrush** | **89.7 A** at 12.4 µs |
| settles to | 16.800 V |

That is the number behind the smoke stopper, and it had never been quantified. It also
sets the surge duty on the XT60 and on C17/C18 — MLCCs with real ESR are doing the
damping here.

### `outfilter.cir` — +5 V ripple and peak inductor current

TPS54202 switch node, 500 kHz, D = 0.296 at 4S worst case (16.8 V in, 4.967 V out),
L2 10 µH, C22 + C23 = 44 µF, load 1.19 A.

| | hand analysis | ngspice |
|---|---|---|
| inductor ripple | 0.700 A p-p | **0.702 A** |
| **peak inductor current** | **1.54 A** | **1.551 A** |
| output ripple | 3.98 mV | **4.08 mV** |
| Vout | 4.967 V | 5.010 V |

**The agreement is the point** — two independent methods on the same circuit. And the
result is a finding: **peak inductor current is 1.55 A against L2's 1.6 A rating, 97 %.**
At 4S worst case the inductor, not the regulator, is the binding constraint. A 22 µH part
would halve the ripple and restore margin.

## A trap worth recording

The first `outfilter` run reported 3.7 A peak and 400 mV ripple — nonsense. The cause was
the **LC tank ringing at 7.6 kHz** from the t=0 step, still decaying when the measurement
window opened. An open-loop power stage has no feedback to damp that; the real device
does. Fixed by starting at the operating point (`.ic`) and running to 8 ms. **An
open-loop model tells you about the filter, not about the converter** — do not read
transient ripple off one without checking it has settled.
