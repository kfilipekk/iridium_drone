# NAVCORE-SoOP — verification

What has actually been checked, what was found, and what is deliberately accepted.
Merged from VERIFICATION.md and VERIFICATION.md.

## NAVCORE-SoOP — what has actually been verified


`tools/preflight.py` returns **READY TO ORDER**. That sentence is worth very little on its
own, and this document exists because this project has been burned by the gap between
"every check passes" and "the board is right" more than once.

Both `J1` and `J2` were fitted facing *into* the board — `J1` fatally, since no cable
could be plugged in — and **every automated check passed them**, because each one
validated electrical correctness and nothing expressed which way a connector faced.
`check_build.py` even measured `J1`'s 0.83 mm to the board edge and passed it without
asking.

The pattern behind every defect found since is the same: **a check that measures
something adjacent to the property that actually matters.** So the table below has two
columns, and the second one is the important half.

Last board-tool pass: **2026-09-02**. The full SITL suite is not currently a green release gate; see §9.

---

### 1. What each check proves — and what it does not

| tool | proves | does **not** prove |
|---|---|---|
| `preflight.py` | the whole gate runs and nothing regressed | nothing it does not itself call |
| `check_design.py` | the netlist matches the schematic, and every MCU pin used is declared | that the netlist is the *right* netlist |
| `check_hwdef.py` | ArduPilot's hwdef agrees with the netlist pin for pin | that the pin does what its name says |
| `check_pin_semantics.py` | direction, reset level and role agree per pin | anything about the part on the other end |
| `check_electrical.py` | divider ratios, decoupling values, pull-up values | that the parts fitted are the parts specified |
| `check_ratings.py` | every capacitor is rated for its net's maximum, dielectrics are right, inductors carry their current, terminals land on their pads | that LCSC ships the part the code names |
| `check_power_cut.py` | copper cross-section carries the load at every axis-aligned cut | non-axis-aligned bottlenecks; it is optimistic by construction |
| `check_traces.py` | length, differential skew, layer changes, crystal stray capacitance | impedance — none is specified on this board |
| `check_placement.py` | decoupling and loop distances against pre-routing guides | **report only** — see §4 |
| `check_connectors.py` | each connector's mouth faces off-board with room for its plug | that the plug you buy matches the assumed size |
| `check_mechanical.py` | the stack fits in Z, board vs ESC vs frame | any frame dimension not in the listing |
| `check_cpl.py` | rotations derived from board geometry agree with the CPL | JLCPCB's internal part orientation |
| `check_build.py` | aircraft-level: power budget, mass, thrust, geometry, buses | anything tagged `[A]` — see §5 |
| `check_params.py` | every shipped parameter exists in the target firmware | that its *value* is correct |
| `dimensions.py` | exact board geometry, measured | anything about the frame |
| `sitl/` | what ArduPilot does given a fix of a stated quality | that the receiver can produce such a fix |

Provenance is tagged throughout: **[M]** measured from the board file, **[D]** datasheet,
**[L]** a listing being bought from, **[A]** assumed. Only `[M]` is a fact.

---

### 1b. The one that would have destroyed the board — 2026-09-03

**Both TPS54331 buck regulators were missing their catch diode.** The board would not have
powered up, and the regulators would most likely have destroyed themselves on the first
switching cycle.

The TPS54331 is **non-synchronous**: it integrates only the high-side FET. TI's datasheet
is explicit — *"The TPS54331 device is designed to operate using an external catch diode
between the PH and GND pins."* With no diode, inductor current has no freewheel path when
the high-side FET turns off, and the PH node is driven below ground until something breaks
down. `U8` feeds `+5V`, which powers the MCU, both IMUs, the GPS and the receiver.

Verified against KiCad's own exported netlist rather than `design.py`:

```
BUCK_PH  : C21.2, L2.1, U8.8      ← bootstrap cap, inductor, PH pin. No diode.
BUCK9_PH : C68.2, L5.1, U18.8     ← same.
```

Every other pin on both regulators was correct. The only diodes in the entire design were
a TVS, two LEDs and a signal diode.

#### Why 64 preflight checks, 20 SITL scenarios and three READY TO ORDER verdicts missed it

**Every check verified a property of something that was present.** Connectivity, current
capacity, clearance, pin direction, firmware agreement, DRC. **Absence has no net, no
footprint and no pad to inspect** — there was nothing for any of them to look at.

Worse, the thing that makes this project good is what hid it. The design is generated from
one source of truth, and **a single source propagates errors exactly as faithfully as it
propagates correctness.** The buck nets were written from intent rather than transcribed
from TI's reference application circuit. Once the diode was absent there, the schematic,
netlist, BOM, PCB and every check inherited the omission *consistently* — and consistency
is precisely what those checks measure. `check_design.py` verifies netlist ↔ schematic ↔
hwdef agree, and they agreed perfectly about a diode none of them had.

**Internal consistency checking cannot find an error that lives in the specification.**

#### What now guards it

`tools/check_topology.py` compares the design against **datasheet-required externals**,
keyed on part number, with the datasheet sentence as the citation. It is the first check
in this project that consults something *outside* the project. It covers the buck
freewheel path, the STM32's `VCAP1`/`VCAP2` core-regulator caps, the `NRST` filter,
`BOOT0`'s pull-down and both LDOs' input/output caps — all of which were verified present.

It also **refuses to pass an unclassified regulator**: a part that is in neither the
"needs a catch diode" nor the "synchronous" table fails, because an unclassified
regulator is not a checked one.

`sim/` is the second outside check. A circuit that cannot work does not simulate.

#### The fix: synchronous regulators

Both bucks moved to the **TPS54202DDCR** (LCSC C191884): 4.5–28 V in, 2 A, **two
integrated switching FETs**, SOT-23-6. The low-side FET *is* the freewheel path, so the
failure mode is designed out rather than patched — there is no catch diode to forget.

| | |
|---|---|
| parts deleted | `C20`, `R8`, `C24`, `C25` and their 9 V twins — **8 fewer components** (internal compensation and 5 ms internal soft-start) |
| **feedback dividers recomputed** | Vref **0.800 → 0.596 V**. `R6` 27k → **37k4** (4.967 V); `R42` 47k → **66k5** (9.029 V). Leaving them would have silently produced **3.75 V and 6.55 V** |
| EN dividers | unchanged — 3.03 V and 2.81 V at 4S, inside the −0.1 to 5.5 V recommended range, still valid at 6S |
| 2 A vs 3 A | irrelevant: `L2` is rated **1.6 A**, so the inductor was always the binding constraint |

**The pinout was read from the datasheet, not assumed** — and that mattered. SLVSD26C
Table 4-1 gives `1 GND, 2 SW, 3 VIN, 4 FB, 5 EN, 6 BOOT`. Working from memory would have
put **FB and EN the wrong way round**, repeating the exact class of error being fixed.

### 2. Defects found, and the root cause of each

Not just the fix — the reason the fix was needed, because the mechanism is what recurs.

| defect | root cause |
|---|---|
| `J1`, `J2` fitted facing into the board | every check validated electrical correctness; **nothing expressed orientation**. Fixed by `check_connectors.py`, which derives the mating face from the footprint's own pad row |
| `L2`/`L5` on 1210 lands holding 4.0 × 4.0 × 3.0 mm parts | the passive table was keyed on **value alone**, so "10 µH" resolved to one part regardless of footprint. Re-keyed on `(value, footprint)` |
| six capacitors with the wrong package or under-rated | same key collision. `C19`/`C66` were 16 V parts on a 16.8 V VBAT — **over rating before derating** |
| `U1.49` and `C25.2` not connected to the ground plane | routing completed, DRC clean, and two ground pads simply had no via within reach |
| 9 V buck documented DNP but all 17 parts in the CPL | BOM and CPL derived from different predicates; the assembler would have fitted parts the BOM said not to |
| height table assumed 1.0 mm for anything it did not recognise | a **silent default**. It covered `J2` (2.9 mm), `U1`, both inductors, every 1206 cap and the crystal |
| hole-clearance check measured silkscreen, not copper | wrong geometry class for the question asked |
| ratings check compared a part's **body** against a **land** | neither is the question. The questions are *do the terminals land on the pads* and *does the body clear its neighbours' bodies*. Produced two false "does not fit" verdicts before being corrected |
| `BOT_PARTS` = 2.5 mm sourced to "L2/L5" | `L2` had moved to the **top** during the buck re-layout and the source line was never revisited. The same quantity was **also** hardcoded as 2.3 mm in `preflight.py` — three numbers, three files, all wrong at once. Now derived from `design.PART_HEIGHT` |
| `L_APV_ANR4030` absent from the height table | `L2` fell through to the silent 1.0 mm default — the exact failure the table's own comment warns about |
| **95 footprints referenced 3D models that do not exist** | `${KICAD9_3DMODEL_DIR}` is unset here and `kicad-packages3d` is not installed. Every passive, both switches and **both 10 µH inductors** were missing from every STEP and GLB export. A check asking "does this footprint declare a model?" answers *yes* for all 95 — "declares a model" and "has a model that loads" are different properties |
| CAD exports 50 KB instead of 23 MB | exported without `JLC_LIB` set, so **no bodies at all**. This is how the reversed USB connector stayed hidden for weeks |
| **"Rev B" named two different things at once** | `docs/PINMAP.md` defined Rev B as a *firmware* change with "no PCB change between revs". Sixteen other places used "Rev B" to mean a **future fabrication run** — expose SPI3, move `U18`/`L5`/`C68`, re-route the VTX rail. The same label therefore covered both a free reflash and a ~$190 respin, which **systematically understated cost** wherever the second sense was meant. Collapsed 2026-09-04: one board, `docs/MODULES.md`; the firmware sense is now "the SoOP config" and the silicon sense is "a respin" |
| `docs/SENSORS.md`: "there is no 'beside the battery' — an upward ToF goes on the strap, on a mast, or not at all" | **Measured the wrong axis.** The conclusion came from *width* — a 47 mm pack on a 42.50 mm plate — but the free space is in *length*: 138 mm of battery on a **160.26 mm** plate leaves **22.26 mm**. The sensor fits fore or aft, needing ≥11.5 mm to clear the 48 mm battery wall at its 27° cone, so the pack sits at one end rather than centred. Displacing 615 g of 1123 g AUW by 11.13 mm moves CG 6.1 mm — pushed *away* from the existing +3.1 mm offset it **improves** to −3.0 mm. This unblocked sensing option A, which had been held open on "no confirmed mounting position" |
| **the shipped SoOP configuration cannot arm at the honest sigma** | Raising `soop_link.py`'s sigma from the assumed `[A] 20 m` to the published `[L] 180 m` exposed an architecture-level consequence nobody had followed through. ArduPilot's `all_consistent()` refuses to arm when two GPS instances differ by more than **50 m** — hardcoded, no parameter. As a 2-D radial offset, `P(R > 50) = exp(−50²/2σ²)`: at σ 20 m that is **4.4%** (the "few percent, intermittent" the docs described), but at σ 180 m it is **96.2%**. The SITL suite confirms it — `soop_gpsinput`, the *shipped* configuration, reported disagreements of 95–348 m and never left the ground; **10 scenarios failed to arm for this single reason**, having previously flown only because the fictitious 20 m sigma kept scatter under the threshold. The repo already recommended aligning the companion's solution to the live GPS before denial; that is now **not an optimisation but the precondition for arming at all**. Secondary finding: the SITL harness does not model that alignment, so the SoOP scenarios currently prove nothing about in-flight behaviour until it does |
| `measurement_canary` is self-defeating | It injects a deliberate 100 m offset to prove the harness measures real error rather than comparing the EKF against itself — but 100 m trips the same hardcoded 50 m consistency check, so it never arms and the canary never runs. The guard against "every figure in this report is meaningless" is itself inoperative, and has been since the offset was chosen larger than the threshold |
| the LD06 was costed at **£19** in `design.MODULES` while `docs/BUYING.md` had corrected it to **~$99–131** and moved it to "do not buy yet" | The £19 came from a superseded "~GBP 15 AliExpress" line still sitting in `design.py`'s own `src` — so the source of truth carried the price the buying guide had explicitly retracted. A 5–7× error, and it is the figure that decides the purchase: at ~$100 and 50 g the LD06 protects to about 5 m/s on an aircraft cruising at 15–20. Corrected, and `docs/SENSORS.md` now separates **whether to buy it** from **where it mounts** — this session verified the mount in detail, which is not an argument for buying it, and the file previously ran the two together |
| `design.MODULES` labelled its cost field **`usd`** while every value came from the repo's **GBP** sourcing | Introduced by me when writing the module map: the figures were lifted from AliExpress prices the repo records in pounds, then given a `usd` key and rendered with a `$`. The order total is `£681` and the board `£189`, so the mislabel also propagated into `docs/BENCHMARK.md`'s comparison against commercial drones. Field renamed to `gbp` throughout, table header and terminal output now show `£` |
| `check_cad_fit.py` had a rule that **could not detect the failure it named** | `("belly_sensor", "skids"): (2.0, "the belly sensor must clear the skid contact line or a landing crushes it")`. It measured 3D min separation between two solids — but the skids stand at the **motors, 160 mm out**, while the belly parts sit at the centre. It reported **114 mm** and would have stayed large however far below the ground plane a belly part hung. **A pairwise test cannot answer a ground-clearance question, because the ground is not a part.** Removed and replaced with an explicit `GROUND_PARTS` check comparing each hanging part's lowest vertex against the skid contact plane at `z = -(drop + t)`, at 5.0 mm rather than the old 2.0 — TPU gear deflects several mm under a firm arrival and the part absorbing it is the sensor. This is the session's recurring defect appearing *inside a checker*, which is the worst place for it: the rule read as coverage. The replacement was then **tested against a failure it should catch** — raising `lidar360`'s threshold to 15.0 mm makes it report `clearance 10.20 mm (need 15.0) FAIL` and exit 1, while `belly_sensor` stays ok at 31.50 mm, so it discriminates rather than failing everything. The rule it replaced passed at 114 mm precisely because nobody had ever checked that it *could* fail |
| the 45-pair CAD fit was read as evidence the lidar fits | It was not — **the LD06 was never in the model.** After the skid change the check reported "PASS — 45 pairs", which verified only that the *existing* parts still fit each other. Modelled as `lidar360()` with dimensions generated from `design.OFFBOARD['lidar']` so they track the datasheet, placed at y = −22 to clear the rangefinder at y = +18; 11 parts, **55 pairs**, `belly_sensor × lidar360` clearing by 12.71 mm |
| skid drop set to 35 mm on an **asserted** trade | 35 mm was chosen over 40 mm to avoid raising the CG. Computing the trade reversed it: static tip-over moves **71.5° → 69.9°** (1.6°, both far from the ~30° where a quad is tippy) while ground clearance under the lidar **doubles, 5.20 → 10.20 mm**. TPU gear deflects several mm under a firm landing, so 5.20 mm sits inside what one hard arrival can consume — and the part taking the hit is the £19 lidar, not the printed skid. Now 40 mm. The lesson is not the number: it is that the CG objection was stated rather than computed, and cost nothing to compute |
| `docs/SENSORS.md` wired the LD06 to **`SERIAL6` / `P72`** | Two errors in one block. `design.py` earmarks the lidar for **`SERIAL2` (USART1)**, and `SERIAL6` was settled the same day as the *unclaimed* expansion UART — so the doc contradicted both. Worse, `P72` is `UART4_TX`, an **output**: the lidar's TX must reach the flight controller's **RX**, which is `TP6` (`USART1_RX`). Corrected to TX→`TP6`, 5 V→`P71`, GND→`P74`; borrowing the `P71`/`P74` power pins does not claim `SERIAL6`, whose UART pair stays free. `PRX1_ORIENT` was also 0 (top-mounted) on an aircraft that carries it underneath — now 1 |
| LD06 current, mass and dimensions were assumed, and the module had no viable mounting position | The datasheet (read 2026-09-04) gives **38.59 × 38.59 × 33.30 mm, 42 g, 180 mA running with a 300 mA start-up surge** — `MODULES` had carried a guessed 250 mA, and the surge matters more than the running figure on a 413 mA rail. The mounting block was real: 33.30 mm of lidar against 28.5 mm of belly. Resolved by setting `SKID['drop']` **25 → 35 mm**, which is a *printed* part and so a free parameter that had simply been inherited: 38.5 mm of depth, **+5.20 mm** margin (30 mm would give 0.20 mm, which is not a clearance). The skid legs cut the scan plane, which is what `PRX1_IGN_ANG*`/`WID*` exist for — at 160 mm radius each 10 mm leg subtends 3.58°, so 4 of ArduPilot's 6 sectors cover it with 4% of the scan lost |
| `BELLY_SENSOR['depth_available_mm']` was a hardcoded `28.5` whose own `src` said "computed from `design.SKID`" | It was not computed, so raising the skid drop left it silently reporting the old depth — a value that *claims* to be derived and is not. Now genuinely `SKID["drop"] + SKID["t"]`. Same mechanism as every other row here, and the reason the fix is structural rather than a corrected number |
| "no SDR / TCXO / LNA / antenna improves the accuracy ceiling" was over-read into "180 m is the floor" | The **hardware** claim is correct and stands — ephemeris dominates, so receiver-side upgrades do not move it. But the ephemeris term is closed by **architecture**: multi-constellation reaches **5.1 m** static in the literature, and differential against a base receiver at a known position reaches **0.60–0.81 m RMSE**. The second is available to this aircraft with **no board change** — the SDR chain is already laptop-side and the ELRS link carries base observables at 22% utilisation for 6 satellites at 5 Hz. It costs the "autonomous" framing, since the system then depends on a ground station. Found 2026-09-04 during the benchmarking review; recorded in `docs/BENCHMARK.md` and `sitl/soop_link.py` |
| no IMU temperature calibration configured, on an aircraft whose claim is bounding IMU drift | `INS_TCAL*` was absent from `defaults.parm`. Gyro/accel bias is strongly temperature-dependent and this board sits between a 60 A ESC and a battery with almost no airflow; attitude error leaking gravity is the dominant drift term (0.10° → 30.8 m at 60 s). The Pixhawk FMUv6X standard solves this with **resistive IMU heaters**; this board has none, being pin-identical to the MatekH743. ArduPilot's software equivalent is free and both prerequisites are met (2 MB flash, microSD). Added as `docs/BUILD.md` **T3c** — deliberately *not* to `defaults.parm`, because `ENABLE 2` is a learning mode that would restart calibration on every boot |
| SITL read a divergence boundary measured at one sigma against runs at another | `diverges_above=120.0` is **empirical** — n=6 runs separating cleanly into bounded (≤79.6 m) and diverged (≥216.7 m) — but those runs were flown at **σ 20 m**, and `DopplerErrorModel` now defaults to the published **180 m**. Both modes scale with sigma, so the boundary no longer separates them: it would have labelled essentially every run "DIVERGED" and read as a finding rather than a stale constant. Rescaling it arithmetically would have been worse — that invents a measurement. The verdict now refuses to render hold/runaway when the run's sigma differs from `BOUNDARY_SIGMA_M`, and reports the raw p95 instead. This also fixes a **pre-existing** case: `soop_dropout_lowsigma` runs at σ 10 m and was already being judged against the 20 m boundary |
| `docs/SENSORS.md` listed `+9 V` at `PV1` as a "VTX rail, switchable via `RELAY1`" | The 9 V block is **DNP** — `BUCK9_PH` is unroutable — so `PV1` is an open net and `RELAY1` switches nothing. The rail table described the schematic's intent rather than the board's state. Corrected 2026-09-04, along with the `RELAY1` GPIO row, which called `PA7` "free": it is free as a *firmware* GPIO, but `VTX_EN` reaches only `U1`, `Q3` and `R45` and **no pad**, so nothing external can be wired to it. Both are the same mechanism as the `PF1` row below — a document describing a net instead of a landing |
| `check_build.py` validated the 5 V load against a **TPS54331 at 3.0 A** | `U8` is a **TPS54202** (`C191884`), rated **2 A**. The check was named after a part that is not on the board and carried a ceiling 50% above the fitted one, so it would have passed loads the regulator cannot supply. Worse, neither figure was the binding limit: `L2`'s **1.6 A Irms** governs the rail. Now checks both, tightest first, and the 413 mA headroom is derived independently in `check_build.py` and `design.RAIL_5V` |
| `design.py`: `L2` is at "118 % of rating" and "`check_ratings.py` FAILS on this deliberately" | **Stale.** True when the Pi Zero took 700 mA from this rail; the Pi moved to its own BEC, so `L2` carries 1.19 A of 1.6 A — **74%**, and `check_ratings.py` **passes**. A comment sending a reader to hunt a failure that no longer exists costs as much as a missing one. The *footprint* half of the same note — a 4.0×4.0×3.0 mm part on a 3.2×2.5 mm 1210 land — is still live and unchanged |
| "+5 V headroom is 1.8 A" (5 sites in `design.py`) / "~2.4 A" (`docs/HARDWARE.md`) | Both derived from **`Isat` 2.4 A minus the board's own 620 mA**. Wrong twice: `Isat` is a *saturation* rating governing transients, while a continuous load is limited by `Irms` **1.6 A**, a thermal rating — and the subtraction ignored the rangefinder, ToF sensors, mux and LED strip that `check_build.LOADS_5V` counts, which `INDUCTOR_LOAD_A["L2"]` has put at **1.19 A** all along. The true headroom is **413 mA**. Consequence: the LD06, an FPV AIO and the recording camera together offer **800 mA** and **cannot all run**, though every one of them attaches. Now derived in `design.RAIL_5V` and asserted by `check_modules.py`, which reports it as a warning because it constrains *combinations*, not the board |
| `design.py`: "PF1 is the only VBAT pad" | **`PF1` is a schematic power flag, not a footprint** (`PWR_FLAGS = {"VBAT": "PF1", ...}`). The board has **no VBAT pad or test point at all** — VBAT reaches only `J2`, `D1`, three resistors, four bulk caps and the two bucks. The claim was read off a power-flag table and never checked against the artwork, and it propagated into the FPV power plan in three places. Found 2026-09-04 while writing `docs/MODULES.md`, which had inherited it. The sharpest part: `docs/HARDWARE.md` line 921 **already said** `PF1`–`PF8` are "`PWR_FLAG` schematic symbols — ERC constructs with no footprint". The repo held both the right answer and the wrong one simultaneously, in two files, for weeks — so "it is documented somewhere" is not evidence, and a claim about the board must be checked against the board. A 25 mW AIO runs off `+5V` at `P41`/`P46` instead; anything wanting 7–26 V takes it off-board |
| `check_modules.py` reported all 22 attachment pads missing from a board that carries every one | the footprint splitter was a regex anchored on `\n  )`, an **indentation artefact**, not on structure. It matched nothing, every `lands_on` looked absent, and the failure was loud enough to look like a real board defect. Replaced with a paren-depth scan plus a sanity assert that refuses to run if it finds under 100 footprints — the same "measured something adjacent to the property that matters" mechanism as the rows above, this time in a brand-new check |
| `docs/SENSORS.md`: "ArduPilot cannot reassign" VL53L1X addresses | the driver source says otherwise — see §6. The conclusion survived; the **reason** was wrong, and a wrong reason is how the next decision goes wrong |
| `docs/BUYING.md`: FPV variant "cannot be populated" | true when written, false now: `+9V` is routed and `L5` fits |
| `dimensions.py --md > docs/HARDWARE.md`, as documented in that file | the generator emits 85 lines; the document is 170+. **The documented refresh command deletes half the file** |
| `sitl/run_scenarios.sh` pointed at `/tmp/nav/apvenv` | the venv had moved to `~/.cache/navcore`; `/tmp` was being wiped between sessions, which is also how an earlier board backup was lost |
| **the SITL harness returned PASS on an aircraft that never took off** | see below — the most consequential finding in this pass |

#### The SITL harness was passing scenarios on the ground

`baseline_gps` returned **`verdict: PASS`** with `max_alt_m: 0.01` and
`truth_excursion_m: 0.0`. The aircraft had armed and never left the ground, and a
stationary vehicle has a position error of about **2 cm** — so every `max_p95` threshold
in the suite was satisfied *by not flying*.

Three separate defects stacked up:

1. **Takeoff was asserted, never verified.** The harness sent `MAV_CMD_NAV_TAKEOFF`, ran
   `time.sleep(15)`, printed `"airborne"` and started measuring.
2. **The command ACK was never read.** The autopilot was replying `MAV_RESULT_FAILED`,
   in a field nobody looked at.
3. **The vehicle was auto-disarming before takeoff.** Copter disarms ~10 s after arming
   if the throttle stays down (`DISARM_DELAY`), and in GUIDED the harness never touches
   throttle. Arming was also confirmed from `conn.messages["HEARTBEAT"]`, which can be
   seconds stale — so "armed" was read from a message describing a state the vehicle had
   already left.

Fixed: `DISARM_DELAY 0` for the harness, arming re-confirmed from a fresh heartbeat, the
takeoff ACK read and printed, and the climb polled until it reaches 80% of the target
with a **hard failure** if it does not.

Before and after, on the same board and the same scenario:

| | max alt | vehicle moved | p95 error | verdict |
|---|---|---|---|---|
| before | 0.01 m | 0.0 m | 0.02 m | **PASS** |
| after | 12.1 m | 35.8 m | 0.20 m | PASS |

The prearm findings in `sitl/README.md` are unaffected — those happen before takeoff and
remain valid. **Any position-error figure recorded before this fix should be treated as
unverified.**

`proximity_ring` was re-examined against this, since "the aircraft never flew" would
neatly explain a scenario that never reaches its simulated wall. **It does not explain
it:** that scenario fails during *pre-stream*, before takeoff, with proximity reporting
`No Data` — a prearm-stage failure the takeoff bug cannot reach. Its HARNESS DEFECT
label is accurate and stays.

#### Tooling failures that let defects through

These cost more time than the defects did.

- **DRC run against a copy of the project.** `kicad-cli` reads design rules from the
  `.kicad_pro` *beside the board*; a copy elsewhere silently falls back to KiCad's 0.2 mm
  defaults and invents ~1100 violations. **Always DRC in the project directory.**
- **Goal cells set to the keep-out halo rather than copper**, so routes "succeeded"
  while connecting nothing.
- **Pads treated as circumscribed circles**, which hid every escape between `J2`'s pads.
- **`track_dangling` treated as "this copper is inert".** It is not — see §3.
- **Silk placement keyed off the footprint's side rather than the pad's actual layers.**
  `J1` is a front-side connector with a pad on `B.Cu`; a bottom-side label kept being
  placed on exposed copper while the tool insisted the position was legal.

---

### 3. Accepted, with reasons

Everything DRC still reports, and why it stays.

#### Copper — 13 `track_dangling`

`track_dangling` means *one end touches nothing*. It does **not** mean the piece is inert.
Deleting all 31 items DRC originally named broke **7 connections**: the label tests
endpoint coincidence, while the connectivity engine tests actual overlap, and they
disagree wherever a track end lands on a pad away from its anchor point.

`tools/prune_dangling.py` therefore uses DRC only to *propose* candidates and lets
KiCad's connectivity engine decide, per candidate, on a freshly loaded board. **56.11 mm
of orphaned copper removed across 9 nets, connectivity unchanged at 479/479**, including:

- an 8.84 mm `VBAT` orphan on In2.Cu — the largest on the board, on the highest-voltage net
- a `BUCK_PH` stub — the 5 V buck's switch node, the worst place for an unterminated radiator
- all 5 dangling vias, among them the `USB_DM` one. `USB_DM` went **3 vias → 2**, matching
  `USB_DP`, and `check_traces.py` no longer reports the pair as asymmetric

**What remains:** 8 items that are load-bearing despite the label (`M3`, `M4`,
`SPI1_SCK`, `IMU1_CS` ×2, `USB_DM`, `BUCK_PH`, `+3V3`) and 5 sub-millimetre slivers on
`+3V3`/`+9V` that regenerate: removing one exposes the next segment of the same route.
Pruning was stopped there deliberately — past that point it eats real routes for ~0.2 mm
a pass.

#### Silkscreen — 5 `silk_over_copper`, 2 `silk_edge_clearance`

Down from 42. Every movable **reference designator** was placed clear, including `U8`,
`U18`, `U5`, `U10`, `U3`, `U6`, `D3` and `J8` — the parts you most need labelled for hand
rework. What remains is footprint **outline** segments: four on `J1` and one on `J8`,
each crossing that connector's own pads, plus two on `J1` at the board edge because
`J1`'s mouth is deliberately flush with it. The fab clips silk over a mask opening
automatically. Fixing these means editing library footprints — a large blast radius for a
cosmetic gain.

#### 2 `lib_footprint_mismatch` — both deliberate

- **`J8`** — the library copy contains a **degenerate 2-point polygon**, 0.10 × 11.60 mm,
  on the Fab layer, which KiCad discarded when placing the footprint. **The library copy
  is the defective one**; the board's is correct. Copper, mask, paste, silk and courtyard
  all match. Re-importing would pull the bad shape back in and risk the placement.
- **`U6`** — the paste array in §4 is a deliberate local override.

#### Electrical

- **6 MLCC derating warnings.** `C17`/`C18` 25 V on 16.8 V (1.5×), `C21`/`C68` and
  `C69`/`C70` at ~1.8×. An X5R/X7R part loses much of its capacitance near its rating,
  so ratio matters more than the pass/fail. All are ≥1.5× and the buck input bulk is the
  pair that matters.
- **`L5` terminal overhangs its pad by 0.18 mm in Y.** Solderable — the terminals sit
  *inside* the pads in x — but check the fillet at assembly.
- **In4.Cu rail fragmentation** — `+3V3` 1 zone → 15, `+5V` 11 → 18, `VBAT` 5 → 8.
  Pre-existing. `check_power_cut.py` shows every rail with 2–7× margin at its tightest
  cut, so the fragmentation costs nothing measurable.

#### `check_placement` — report only

24 parts sit beyond their **pre-routing** guides, the notable ones being `C17` → `U8.2` at
4.52 mm (guide 3.0), `C71` → `U18.6` 4.22, `L2` → `U8.8` 3.87 and `C25` → `U8.6` 3.40.
These are buck loop lengths, and routing legitimately moved parts after the guides were
set. Gating on them would block a correct board, so the check runs and reports without
blocking — but the numbers stay visible rather than silent.

---

### 4. Changes made in this pass

| change | effect |
|---|---|
| `tools/prune_dangling.py` (new) | 56.11 mm of orphaned copper removed, connectivity proven unchanged |
| `tools/tidy_silk.py` (new) | 42 silk violations → 7; every movable refdes now legible |
| `tools/make_box_step.py` (new) | writes AP214 box solids — no CAD kernel is available here |
| `tools/fill_missing_models.py` (new) | 9 box bodies generated, **95 footprints re-pointed**; every model now resolves |
| `tools/windowpane_paste.py` (new) | `U6`'s exposed pad: one 100% aperture → 4 × 1.00 × 0.75 mm, **65.8% coverage** per IPC-7093. Verified paste-only: of 28 gerbers, **`B_Paste` alone changed** |
| `design.PART_HEIGHT` + `stack_heights()` (new) | one source of truth for package heights, replacing three disagreeing copies |
| `design.NET_VMAX` extended | 12 capacitors were on **undeclared nets and therefore unchecked**; all 50 BOM lines are now covered |
| `gen_bom.py --fpv` (new) | the analogue-FPV variant is orderable — 117 placements vs 101 |
| four checks gated in `preflight.py` | `check_design`, `check_hwdef`, `check_traces` block; `check_placement` reports |
| `J3` 3D model | the tallest top-side part was missing from every export |

`U6` is the **only** exposed pad on this board. An earlier plan claimed `U1`, `U2` and
`U3` needed windowpaning too; checking every pad showed `U1` is LQFP-100 with no exposed
pad, `U2`/`U3` are LGA-14 with none, `U8`/`U18`/`U11` are plain SOIC-8 and `U9`/`U10` are
SOT.

---

### 5. How the aircraft is controlled

Traced to `firmware/NAVCORE_SoOP/hwdef.dat`, `defaults.parm` and the board.

| link | port | lands on | shipped config | state |
|---|---|---|---|---|
| **Manual RC** | SERIAL7 / USART6 | `P51` 5V, `P52` TX, `P53` RX, `P54` GND | `SERIAL7_PROTOCOL 23`, `RC_PROTOCOLS 512` | in place |
| **GCS telemetry, line of sight** | SERIAL2 / USART1 | `TP5` TX, `TP6` RX | ArduPilot default MAVLink2 | in place |
| **Companion computer** | SERIAL1 / UART7 | `P41`–`P46` | `SERIAL1_PROTOCOL 2`, 921600 | in place |
| **Satellite, beyond line of sight** | SERIAL6 / UART4 | `P71`–`P74` | *nothing configured* | pads only |
| **Autonomy** | on board | — | AUTO/GUIDED, EKF3 fed `GPS_INPUT` | in place |

Four things worth knowing:

1. **`RC_PROTOCOLS 512` is CRSF only** (bit 9). ExpressLRS and TBS Crossfire bind; an
   SBUS or FrSky receiver **will not**, silently. Deliberate — set `RC_PROTOCOLS 1` to
   auto-detect. CRSF is bidirectional, so handset telemetry returns on the same 4 wires.
2. **There is no satellite command link, and the SoOP receiver is not one.** Iridium NEXT
   Doppler is passive listening — a *navigation* source, receive-only. BLOS needs a
   **RockBLOCK 9603** on `P71`–`P74`; ArduPilot ships the driver as
   `AP_Scripting/applets/RockBlock.lua` (`SERIAL6_PROTOCOL 28` plus `RCK_*`). It carries
   **`HIGH_LATENCY2` only** — no heartbeats, no acknowledgements, no parameters, one
   command per mailbox check. Enough to command a mode change or a divert. **Not enough
   to fly the aircraft by hand.**
3. **`TP5`/`TP6` are signal only** — a telemetry radio takes 5 V from `P41`/`P61`/`P71`
   and ground from any.
#### What simulation showed about the failsafes

`defaults.parm` shipped **no `FS_*` parameters at all**. Two new SITL scenarios were
written to find out whether ArduPilot's own defaults hold on an aircraft whose position
comes from a ~1 Hz Doppler solution rather than a 5 Hz GPS. They do not.

**`ekf_failsafe` — the aircraft landed itself, on the mission this board exists for.**

```
t+40s  GPS DENIED
t+55s  EKF Failsafe: changed to Land Mode
t+55s  MODE GUIDED -> LAND
t+56s  EKF Failsafe Cleared
```

Fifteen seconds after GNSS denial, on stock `FS_EKF_THRESH 0.8`. Note the last line: the
failsafe **cleared one second later** and the aircraft **stayed in LAND**, because
ArduPilot does not restore the previous mode. A one-second variance transient commits it
to landing permanently.

**`FS_EKF_THRESH 1.0` does not fix it.** That was the obvious first move — "Relaxed" is
the documented setting for a noisier position source — and it was measured rather than
assumed. The result was byte-for-byte the same behaviour: failsafe at t+55s, LAND, clear
at t+57s. **The variance threshold is not the lever here.**

What the timing actually says: the trip is a **transient at the GPS1 → GPS2 handover**,
not a sustained variance problem. The EKF briefly has no usable position while the source
switches, the failsafe fires on that gap, and it clears within two seconds — by which
time the aircraft is committed to LAND, because ArduPilot never restores the prior mode.

So the mitigation has to address the *action*, not the threshold. Three settings were
measured:

| `FS_EKF_THRESH` | `FS_EKF_ACTION` | failsafe fires | aircraft does |
|---|---|---|---|
| 0.8 (stock) | 1 | t+55s | **LAND** |
| 1.0 | 1 | t+55s | **LAND** — threshold changed nothing |
| 1.0 | 1 | t+68s | **LAND → RTL** on radio loss — *was* shipped, now superseded |
| **1.0** | **0** | annunciates only | **applet owns GPS loss** — shipped, see §8 |

> **This subsection is history, not the current configuration.** It records how
> `FS_EKF_ACTION 1` was arrived at, which is worth keeping because the `ACTION 2` disarm
> below was found here. The aircraft now ships **`FS_EKF_ACTION 0`** with the dead-reckon
> applet owning GPS loss; the A/B measurement that decided it is in **§8**, and the
> rejected `ACTION 1` configuration is kept runnable as the `rc_loss_dr` scenario.
> Every "shipped" in the rest of this subsection means *shipped at the time*.

**`FS_EKF_ACTION 2` was tried, and the `rc_loss` scenario proved it dangerous.** AltHold
looked like the better answer — it is recoverable where Land is not — but AltHold is a
*pilot* mode, and this aircraft can lose its pilot:

```
FS_EKF_ACTION 2          FS_EKF_ACTION 1  (shipped)
  t+58 GUIDED -> ALT_HOLD    t+68 GUIDED -> LAND
  t+70 RC CUT                t+70 RC CUT -> Radio Failsafe
  t+70 Disarming motors        t+70 MODE LAND -> RTL
       <-- at 12 m AGL         t+90 ground at 2.1 m/s, disarms landed
  FAIL                       PASS
```

Losing the radio in AltHold **disarms the aircraft in flight**. Landing under control
beats falling, so the action stayed at 1 — until §8 measured `ACTION 0` + the applet,
which neither lands nor disarms. `ACTION 2` remains rejected on this evidence.

Two lessons recorded in `defaults.parm` beside the parameters:

- **`FS_EKF_ACTION`, `FS_EKF_THRESH` and `FS_THR_ENABLE` are a matched set.** Changing one
  in isolation is exactly what produced the disarm, and the single-scenario run that
  motivated the change could not see it. Only the full suite could.
- **This does not fix the underlying defect.** ArduPilot never restores the previous mode
  after a failsafe clears, and at t+78 the EKF failsafe fires again and pulls the aircraft
  out of RTL back into LAND. The fix for that is `copter-deadreckon-home.lua`, not a
  different action value. The applet ships its own default **`DR_NEXT_MODE 6` (RTL)** —
  the `-1` restore-to-prior-mode variant was evaluated and retired, because the mode at
  the recovery point is failsafe-LAND, and note the §0 trap: `DR_*` lines in
  `defaults.parm` do nothing, so the applet's `add_param` default is the only one that
  exists.

**This is a trade-off, not a fix, and it should be your decision.** AltHold holds altitude
and drifts with the wind, and needs a pilot to recover it. *Within* radio range that is
plainly better than landing in a field. *Beyond* radio range it is worse: LAND ends the
flight under control, AltHold flies away until the battery is flat.

The real answer is not a parameter — it is **`copter-deadreckon-home.lua`**, the applet
built for exactly this failure, which `docs/SENSORS.md` already flags as "fit this before
the first GNSS-denied flight". **It is now fitted, and §8 is the measurement that
followed.** Revisit both values against the real receiver's noise rather than the
simulator's 180 m sigma and 2 s latency — sourced from published Iridium NEXT results
rather than assumed, but still not a measurement of this receiver.

**`rc_loss` — PASS, and then it went degenerate.** With GPS denied and the aircraft flying
on a SoOP fix, cutting the radio produced `MODE LAND -> RTL`, and it navigated home on a
position that was not from GPS, travelling 54.5 m. `FS_THR_ENABLE 1` ships on that
evidence.

**That was measured on `FS_EKF_ACTION 1`.** On the shipped `ACTION 0` the applet owns GPS
loss and takes the aircraft to RTL at ~t+60 — ten seconds *before* the harness cuts the
radio at t+70. So `rc_loss` now reports "was already in RTL when the radio was cut": a
true statement, a genuine pass, and **no longer a test of the radio failsafe**, because
there is no transition left to observe. The verdict says which of the two happened rather
than collapsing them into one PASS, which is the only reason this was visible at all.

`rc_loss_early` was added to cover the gap: it cuts at **t+44**, after denial at t+40 but
before the applet commands anything, so radio failsafe and the applet are in contention
and the RTL entry is genuinely observed. `rc_loss` is kept as the late-cut case — radio
loss must not *disturb* an applet-commanded recovery either.

`FS_GCS_ENABLE` ships **0**, deliberately: the only BLOS link this board can carry is a
RockBLOCK sending one `HIGH_LATENCY2` packet every `RCK_PERIOD` seconds, and a 5-second
GCS timeout against a 30-second mailbox check would RTL on every satellite gap.

4. Connectors `J4`–`J7` are **solder pads**, not sockets. At 41.6 × 39.4 mm, seven JST-GH
   connectors plus an LQFP-100 and a microSD socket exceeded the board; keeping a
   connector only where something is plugged and unplugged is what every real 30×30 FC
   does, including the SpeedyBee this replaces.

---

### 6. Corrected claims

**`docs/SENSORS.md` said ArduPilot "cannot reassign" VL53L1X addresses.** The driver
source disproves it — `AP_RangeFinder_VL53L1X.cpp:89`:

```cpp
if (dev->get_bus_id()!=0x29) {
    // if sensor is on a different port than the default do not reset sensor otherwise
    // we will lose the addess. we assume it is already confirgured.
    return true;
}
```

It *deliberately* accommodates a sensor at a non-default address, and `RNGFNDn_ADDR` is
documented as existing "to allow for multiple sensors on different addresses". What
ArduPilot does not do is **assign** those addresses: nothing performs the XSHUT sequence,
and the part forgets its address on every power cycle. The practical conclusion — use a
multiplexer, or address-strapped modules — is unchanged. The reason was wrong.

---

### 7. Residual risk

#### Accepted
Everything in §3.

#### Needs parts in hand — close before flight, not before ordering
- **Motor thrust, `[A]` 1250 g** — every payload figure inherits it.
- **Grommet flange ≤ 5.9 mm** — `R21` is 2.98 mm from a hole; a 6.0 mm flange touches it.
- **Frame standoff spacing** — absent from the listing and the manufacturer's manual.
- **`J3` plug clearance** — 5.30 mm available against a 6.0 mm nominal. Measure the plug.
- **`BATT_AMP_PERVLT`** — a property of the ESC's shunt. Bench calibration.
- **`FLOW_ORIENT_YAW`** — `U6` is bottom-side; check the sign before position hold.
- **1 oz outer copper** — every number in `check_power_cut.py` halves at 0.5 oz.
- **LCSC stock**, captured 2026-08-23.
- **ESC cable pinout** — `J2` matches Betaflight's documented SpeedyBee F405 V4 order;
  check continuity on the cable you receive.

#### Cannot be verified offline at all
- **Whether Iridium NEXT Doppler produces a usable fix from this antenna.** SITL proves
  what ArduPilot does *given* a fix of stated quality. It proves nothing about whether the
  receiver can produce one.
- **Real camera flow over grass.** Simulated flow is perfect flow.
- ArduPilot board ID 9001 is **unregistered** upstream.
- No impedance control is specified; USB is a plain differential pair.

---

### Reproducing this

```bash
cd NAVCORE-SoOP
export JLC_LIB=/home/krystian/Code/Hardware/.libraries/jlc.pretty   # or 3D bodies vanish

python3 tools/preflight.py        # the gate: must say READY TO ORDER
python3 tools/check_build.py      # whole aircraft
python3 tools/dimensions.py       # exact geometry

## in the project directory - rules come from the .kicad_pro beside the board
kicad-cli pcb drc --output /tmp/nav/drc.rpt --severity-all NAVCORE-SoOP.kicad_pcb

./sitl/run_scenarios.sh           # needs a SITL build; see sitl/README.md
```

---

### 8. Dead-reckon applet fitted (this pass)

The rc_loss defect the simulator exposed — EKF failsafe cancels RTL at t+78 and
ArduPilot never restores the prior mode — is now answered by the official
`copter-deadreckon-home.lua` applet, vendored from the same tag the firmware builds
(`Copter-4.7.0`) to `firmware/NAVCORE_SoOP/sdcard/APM/scripts/`.

**It carries a local patch — it is not byte-identical to upstream**, and an earlier
version of this section wrongly said it was. Three changes, all in the GPS-bad timer,
the first of which is a genuine **upstream unit bug**: `now_ms` is `millis()` while
`DR_GPS_TRIGG_SEC` is documented in seconds, so upstream's
`now_ms - gps_bad_start_time_ms > gps_trigger_sec:get()` expires after 3 **ms**, not 3 s.
The other two reset the latched start time so the debounce works once it is reachable.
The file header records all three and the command to re-diff on an ArduPilot bump.

`defaults.parm` now ships, each with its written reason:

| param | value | why |
|---|---|---|
| `SCR_ENABLE` | 1 | scripting required for the applet (build confirmed to include it) |
| `SCR_HEAP_SIZE` | 80000 | applet minimum; the 41 KB default aborts at load |
| `DR_ENABLE` | 1 | arm the applet |
| `DR_ENABLE_DIST` | 30 | scenarios fly 50+ m out; must be armed inside that envelope |
| `DR_GPS_SACC_MAX` / `DR_GPS_SAT_MIN` | 0.8 / 6 | **placeholders pending hardware** — they fire on companion-reported GPS_INPUT quality, unknowable at a desk |
| `DR_NEXT_MODE` | 6 (RTL) | the applet's own `add_param` default; the `-1` restore-to-prior-mode variant was retired — the mode at recovery is failsafe-LAND, so returning home directly is the better recovery (§5 notes the t+78 defect it does not fix) |

**SITL verdict — `deadreckon` scenario: PASS.** GPS denied mid-flight →
`DR: GPS or EKF bad` → `MODE GUIDED → GUIDED_NOGPS` (applet flying home) →
`DR: GPS and EKF recovered` → `MODE GUIDED_NOGPS → RTL`. That last transition is
the one stock firmware cannot perform. (`DR_NEXT_MODE` ships 6/RTL: the aircraft returns
home directly rather than restoring failsafe-LAND.)

**That deviation is now resolved.** The `deadreckon` scenario used to boot
`FS_EKF_ACTION 0` while `defaults.parm` shipped `1` — so it proved the applet worked in
a configuration the aircraft never flew, and on the shipped set the applet was inert.
Both configurations were then run with nothing else changed:

| | `FS_EKF_ACTION 1` (was shipped) | `FS_EKF_ACTION 0` + `DR_ENABLE 1` (now shipped) |
|---|---|---|
| GPS loss | no response — applet preempted | `GUIDED → GUIDED_NOGPS` t+53, **`→ RTL` t+58** |
| radio cut t+70 | `GUIDED → RTL` | already in RTL |
| then | **`RTL → LAND` t+78 — cancelled** | no cancellation |
| touchdown | 0.64 m/s | 0.73 m/s |

Both reach RTL, so disabling the stock failsafe costs nothing on radio loss, and only
`ACTION 0` avoids the t+78 cancellation. `defaults.parm` ships **`FS_EKF_ACTION 0`**;
`deadreckon` now runs the shipped set with no override, and the rejected `ACTION 1` is
kept as the `rc_loss_dr` counter-example so the difference stays measurable.

**`ACTION 0` is only safe because the applet is fitted.** If `DR_ENABLE` is ever 0, or
the script is missing from the microSD, this must go back to `1` — otherwise GPS loss
has no response at all.

Worth recording: **`rc_loss` PASSES on `ACTION 1` even though the defect occurs**, because
it asserts that RTL was *entered*, not that it survived. A green `rc_loss` was never
evidence the failsafe was sound.

Flash-time step: copy `sdcard/APM/scripts/copter-deadreckon-home.lua` to the
microSD under `APM/scripts/`. `DR_GPS_SACC_MAX`/`DR_GPS_SAT_MIN` stay marked
provisional until tuned against real companion GPS_INPUT on hardware.

---

### 9. End-to-end release audit — 2026-09-02

#### Passed locally

- All 8 gated board scripts: design, hwdef, pin semantics, electrical, ratings, power-cut,
  traces, and CPL checks exited 0. Ratings still reports 6 warnings; these are documented,
  not failures.
- `preflight.py`: **READY TO ORDER — 0 blocking failures, 1 warning**. The warning is
  the microSD bottom-edge clearance and must be checked against the real frame.
- `check_build.py`: **38 checks pass**, with 3 assumptions (ESC continuous rating and
  payload estimates).
- `check_params.py`: all 76 shipped parameters exist in the pinned firmware metadata.
- OpenSCAD: renders without hard warnings/errors. The corrected model now places the
  camera below the bottom plate, skids below the arm plane, and the Pi on the rear of
  the top plate. Camera-to-skid margin is 13.0 mm after including the 3.5 mm lens barrel.
- Fabrication outputs are present: 31 files, 28 Gerber files and 2 Excellon drill files;
  all are non-empty. The six copper layers and masks/paste/silk/outline are present.
- Firmware artefacts already exist for the pinned target: bootloader and `arducopter`
  `.bin`/`.apj` outputs. The build script documents the required clean build path.

#### Important discrepancy found during final DRC

A direct `kicad-cli pcb drc --severity-all --exit-code-violations` run reports 22 violations:
13 `track_dangling`, 5 `silk_over_copper`, 2 `silk_edge_clearance`, and 2 deliberate footprint
mismatch records. It also reports 0 unconnected pads. `preflight.py` deliberately gates only
DRC errors and fitted-net connectivity, so it can say READY TO ORDER while full-severity DRC
still reports these accepted/documented classes. Do not describe this as literal “0 DRC
violations”; the accurate claim is **0 blocking DRC errors / 0 unconnected pads, with accepted
full-severity warnings and mismatches documented in this file**.

#### SITL status

**The headline result is a measured divergence rate, not a pass/fail.** Six runs of the
shipped configuration, one per seed 1–6, nothing else changed (2026-09-02):

| | seed 1 | 2 | 3 | 4 | 5 | 6 | diverged |
|---|---|---|---|---|---|---|---|
| `soop_gpsinput` p95 | **270.3** | 47.6 | 70.2 | 24.2 | 30.2 | 38.7 | **1 of 6** |
| `soop_dropout` p95 | **392.6** | 68.4 | 79.6 | **457.1** | **216.7** | 43.4 | **3 of 6** |

**The distribution is bimodal, not spread.** Bounded runs top out at 79.6 m; diverged runs
start at 216.7 m; nothing lands in the 137 m between. And `p95` tracks the vehicle's *true*
excursion almost exactly in every diverged run — 392/473, 457/494, 217/230, 270/319 — so
these are runs where the aircraft genuinely flies away, not noisy measurements of a stable
hold.

**Three claims in the previous version of this section were wrong, and the corrections
change what should be done next:**

1. *"The variation is the simulator seed."* It is not. `--seed` **defaults to 1** and seeds
   only the `DopplerErrorModel` RNG; SITL itself is given no seed and runs against
   wall-clock. Every historical number was already at seed 1, and two seed-1 runs of
   `soop_gpsinput` gave **52.53 m and 270.29 m**.
2. *"Making it a real gate needs a distribution over several fixed `--seed` values."*
   That cannot work, for the same reason. What can be gated is the **divergence rate over
   repeats**, which needs a runner that repeats scenarios.
3. *`soop_dropout`'s 120 m threshold was "invalid".* It was **mislabelled, not
   misplaced** — 120 sits in the empty band between the two modes and separates them
   cleanly. It read as a position-accuracy limit; it is a **divergence detector**. It
   still cannot be a single-run gate, because a single run is one sample of a coin flip.

Both scenarios are now informational and report **which side of the measured boundary**
each run landed on, rather than printing a bare number that reads the same whether the
aircraft held or flew away.

`ekf_failsafe` no longer reports ATTENTION by default. It was asserting on the
*annunciation* — and on the shipped `FS_EKF_ACTION 0` the "EKF Failsafe" STATUSTEXT
**always** appears, because ACTION 0 means *warn and take no action*. The check therefore
flagged precisely the behaviour the parameter was chosen to produce. It now asserts that
no **failsafe-commanded** mode (LAND / ALT_HOLD) follows the annunciation, and attributes
other post-annunciation mode changes to the applet rather than to the failsafe.

`rc_loss` went **degenerate** when `FS_EKF_ACTION 0` shipped: the applet reaches RTL at
~t+60, before the harness cuts the radio at t+70, so it reports *"was already in RTL when
the radio was cut"* — true, a real pass, and no longer a test of the radio failsafe.
`rc_loss_early` was added, cutting at **t+44**, after denial and before the applet acts, so
the RTL entry is genuinely observed.

**The caveat that outranks all of the above:** the SoOP model is **180 m sigma, 2 s
latency** — an assumption, not a measurement of any real receiver. Characterising the real
receiver and feeding its noise back into `sitl/soop_link.py` is the single highest-value
piece of work left in the project.

#### Ordering/assembly/flight steps that cannot be proven at a desk

1. JLCPCB upload preview: board outline, panel size, CPL orientation, actual inventory,
   stackup, 1 oz outer copper, drills, and final quote must be checked in the web tool.
2. The real frame must be measured: centre-plate opening, standoff spacing, top-plate
   height, USB/microSD/J3 clearance, camera mount, CSI ribbon reach, and skid dimensions.
3. The received ESC cable must be continuity-tested before VBAT power. Motor mapping and
   direction require props-off testing.
4. The first power-up must follow `docs/BUILD.md` T1 exactly: current-limited VBAT,
   USB disconnected, then rail measurements. Reverse polarity protection is absent.
5. The bootloader must be flashed over SWD before USB firmware flashing. The Lua file must
   be copied manually to the microSD `APM/scripts/` directory; the build script does not
   package it into the `.apj`.
6. A real companion must meet the NAV-CHAIN contract: `GPS2_TYPE 14`, `gps_id=1`, 5 Hz
   publication, timestamps at capture, honest accuracy fields, and a pre-arm ground
   agreement within 50 m.
7. No simulator can prove Iridium antenna performance, camera flow over grass, motor
   thrust, current calibration, flow sign, or failsafe behavior on the real airframe.

**Release decision:** the board package is locally orderable subject to the JLCPCB upload
checks. The measurement canary now passes after restricting the deliberate offset to that
scenario, the dead-reckon trigger now uses milliseconds correctly, and the **full suite ran
green end-to-end on 2026-09-02** (all scenarios PASS or stated negative-result/counter-example;
see §10). Hardware bring-up, real companion characterization, and the physical checks above
remain mandatory. Note the aircraft this describes has since been staged down — see §10.

### 10. Aircraft staged down: camera and companion deferred (2026-09-02, second pass)

The optical-flow camera and the Radxa Zero 3W companion are **deferred**; the SoOP Doppler
chain is deferred with them. The aircraft navigates on its real GPS outdoors (IMU /
compass / baro) and uses ToF sensors indoors. The board keeps every provision — RF pads
`TP9`-`TP11`, the `SERIAL1` companion link, the sitl/ harness — so reviving the chain is a
hardware-and-companion change, not a redesign. `docs/SENSORS.md`, `docs/SENSORS.md`
and `docs/BUILD.md` carry deferral banners; the honest indoor statement (no
horizontal position estimate without GNSS — Stabilize/AltHold only, the ToF ring stops
the aircraft before walls) is recorded in `docs/BUILD.md`.

#### What changed

| change | where |
|---|---|
| RNGFND3 block added — top VL53L1X, `ADDR 41`, `ORIENT 24`, ships `TYPE 0` | `tools/gen_hwdef.py` -> `defaults.parm` (now 76 params) |
| MCU sensor hub (RP2040/Nano) replaces the Radxa as the ToF ring's reader | `docs/SENSORS.md`, `docs/PARTS.csv`, `docs/BUILD.md` |
| 0x29 bus note names the upward RNGFND3 module; U7 clash stated as not real (U7 is DNP) | `tools/check_build.py` |
| Companion/camera marked DEFERRED (kept, evidence included) | `tools/design.py`, `docs/PARTS.csv`, `README.md` |
| DR_NEXT_MODE -1 references retired; applet ships `DR_NEXT_MODE 6` (RTL) | `docs/VERIFICATION.md` §5/§8 |

#### The generator had silently diverged from the shipped file

Regenerating `defaults.parm` with `tools/gen_hwdef.py` produced **61 parameters where the
shipped file had 71**: the entire failsafes / proximity / scripting span
(`FS_EKF_*`, `FS_THR_ENABLE`, `FS_GCS_ENABLE`, `PRX1` block, `SCR_*`, `DR_*`) existed only
in the on-disk file, which had been hand-repaired after an earlier accident — the
generator was never updated. **The regenerated 61-parameter file would have shipped a
board with no failsafe configuration and an inert dead-reckon applet**, and every local
check that validates *presence* passed on it. Only the diff against the suite's baked copy
(`board-sitl.parm`) caught it.

Fixes:

1. The missing span was ported from the suite's baked copy into the generator template;
   regeneration now yields **76 parameters, no duplicates, zero value differences** against
   the set the green suite flew (the +5 are the RNGFND3 block and the lines SITL strips).
2. `preflight.py` already flags a stale `arducopter.apj` against a newer `hwdef.dat` — this
   fired correctly after the regeneration and stays until `tools/build_firmware.sh` runs.
3. `sitl/run_scenarios.sh --params` remains the live-set check: it re-ran green on the
   regenerated file (63/65 checked, 11 stripped for SITL, no mismatches).

#### Gate results, this pass

- `preflight.py`: **READY TO ORDER** (the only remaining warning is the known In4.Cu
  rails fragmentation; the stale-firmware flag fired after regeneration and was cleared
  by rebuilding — `arducopter.apj` now bakes all 76 parameters, `FS_EKF_ACTION 0` and
  `DR_NEXT_MODE 6` included)
- Generated artefacts current: scenario table, frame table, fastener table, `cad/frame.scad`
- `tools/check_build.py`: 38 checks pass, with the updated bus note
- **Full suite (17 scenarios), one parameter set, the REGENERATED `defaults.parm` — the
  final gate run of the day:**
  - `baseline_gps` PASS (p95 0.2 m)
  - `soop_raw_1hz` PASS — refused to arm on GPS 2, which is the point
  - `proximity_absent` PASS — refused to arm on PRX1, which is the point (the §0.2 guard)
  - `measurement_canary` PASS — reported 110.64 m against the 100 m injected offset
  - `proximity_ring` healthy: armed, airborne, **p95 0.08 m** during denial (the §3
    MCU-hub software path is proven); an earlier same-day run measured p95 0.07 m
  - `rc_loss` / `rc_loss_early` / `rc_loss_dr` PASS — RTL on a non-GPS position; the
    `rc_loss_dr` counter-example still shows the failsafe cancelling RTL into LAND
  - `ekf_failsafe` PASS — annunciates and takes no action, which is what
    `FS_EKF_ACTION 0` promises; the applet then flew GUIDED_NOGPS -> RTL
  - `deadreckon` PASS — applet entered Guided_NoGPS and recovered to RTL, now on the
    regenerated parameter file (the restored DR_* block works end to end)
  - `soop_gpsinput` / `soop_no_velocity` / `soop_dropout*` / `extnav_1hz` /
    `rangefinder_ceiling` / `flow_only`: INFO — the recorded bimodal outcome (§0: never
    quote one run; the 120 m boundary comes from `--repeat 6`) and informational
    investigations, not gates

#### Still open (unchanged)

JLCPCB upload preview and inventory; 1 oz outer copper confirmation; ArduPilot board ID
9001 registration; frame/standoff measurements and fastener depths on arrival; bench ESC
cable continuity, current calibration and thrust measurement; bring-up per
`docs/BUILD.md` T1 before first power-on. The MCU sensor hub firmware (RP2040/Nano
reading the TCA9548A ring) is still **to be written** — the architecture and constraints
are specified in `docs/SENSORS.md`, and the FC side of the path is proven by
`proximity_ring`.

---

## Independent verification pass — 2026-09-05

A second reviewer re-ran the whole apparatus from scratch rather than trusting this
document, then flew the SITL suite. What follows is what that pass found and changed.
Everything below was executed, not read.

#### What was re-verified, and passed

- **Mechanical:** `check_cad_fit.py` — 55 part pairs by intersection volume, zero
  interference; stack 30.3 mm against 35 mm standoffs; all 4 connector mouths off-board
  (`check_connectors.py`); `check_mechanical.py` 29 computed checks ok.
- **Electrical:** `check_electrical` / `check_ratings` / `check_topology` /
  `check_power_cut` / `check_pin_semantics` all exit 0 (4 rating warnings, documented).
- **Board:** `preflight.py` READY TO ORDER after the fixes below; DRC 0 errors; ERC clean.
- **Firmware, by execution:** `baseline_gps` PASS (p95 0.15 m vs truth); `proximity_ring`
  armed, airborne, PRX1 healthy (p95 0.08 m) — the ToF-ring MAVLink path is proven before
  the sensors are bought; new `soop_arming_180m` armed and flew with a 180 m-σ fix on GPS2.

#### Defects found and fixed in this pass

| defect | root cause | fix |
|---|---|---|
| **Fab BOMs would have been ordered wrong.** All three checked-in `BOM-*.csv` still listed TPS54331 (SOIC-8, C9865) for U8/U18 and the deleted COMP network (R8/C24/C25, C20); the board carries TPS54202 (SOT-23-6, C191884) with 37k4/5k1 dividers. CPLs still listed DNP parts the BOM said not to fit. | `preflight.py`'s BOM gate only checked "has an LCSC code" — nothing ever cross-checked the BOM against the board. | All 6 BOM/CPL files regenerated from the board. **New preflight gate `BOM matches the board`** cross-checks every fitted designator, footprint name and Value against the artwork (44 lines / 95 parts at time of writing). |
| **A failing tool reported as ok.** "belly parts clear the ground" keyed on a regex of `check_cad_fit.py`'s output, not its exit code — a run that FAILED a `GROUND_PARTS` limit still printed `ok`. | The pair-count check gates on `rc`; this one did not. | Gates on `rc == 0`, and says what failed when it isn't. |
| **Gerbers were 2 days older than the board** (Sep 1 vs Sep 3 edits). The files `ORDER.md` says to upload were not the files the board checks had passed. | Board was edited after the last `finish.sh` export. | Regenerated with the same `kicad-cli` commands (16 files — `finish.sh` never exported courtyard/user layers; the old 31-file set did, so the count is intentionally lower) and the two doc references updated. |
| **SoOP arming regression** (found by flying): after the error model went σ 20 → 180 m, `soop_dropout` refused to arm — `Arm: GPS positions differ by 129.2m / 211.8m`. `AP_GPS::all_consistent()` (`AP_GPS.cpp:1520`) hard-refuses arming when two GPS instances disagree by > 50 m, and pre-streaming a 180 m-σ fix as GPS2 breaches that on ~half of attempts. The suite was calibrated at σ 20 m, so this read as a flake. | The model's re-founding was never re-tested against the arming gate. | The harness (`soop_link.py`) now **mirrors the live GPS onto instance 2 while GPS1 is healthy and hands over to the Doppler solution at denial** — what a real companion must do, and what `GPS_AUTO_SWITCH 1` assumes. Tripwire scenario `soop_arming_180m` added. `docs/BUILD.md` companion-contract item 2 updated with the measured consequence. GPS1 liveness is tracked on the harness's own clock, not `msg._timestamp` (whose units differ across pymavlink versions). |

#### New measurement — `soop_dropout` at the model's actual sigma

8 repeats at σ 180 m, 25 % outage, 5 Hz (full table in `sitl/README.md`): p95 279–476 m,
true excursion 41.8–231.2 m, **all 8 recovered through the dead-reckon applet's RTL**. The
σ 20 m bimodality is gone — at the published sigma, single-receiver SoOP is a coarse,
recoverable aid, not a position hold. This is the measured case for the differential-SoOP
path in `docs/BENCHMARK.md`.

#### Process note

A second agent session edited `design.py` and `check_cad_fit.py` **concurrently** with
this pass (caught because a check result flipped between identical runs). All generated
artifacts were re-verified consistent at close of pass, but concurrent editing of a
board repo is how the BOM drift in the table above happens silently. Serialize sessions.

#### Same-day continuation — both preflight warnings closed, lidar sourced (2026-09-05)

##### Warning 1 — U8 thermal (worst case 165 °C vs 150 °C max): closed on sourced numbers

The model stacked one measured value with two guessed ones. Fixes, in order of impact:

- **θ_JA replaced with the datasheet figure.** The check carried an unverified "class"
  120 °C/W for the SOT-23-6 (DDC) package; TI SLVSD26 specifies **89.2 °C/W**. This alone
  is −37 °C at the 1.0 A operating point.
- **WS2812 load corrected from 300 mA static to 30 mA average.** The strip is flown as nav
  strobes (low duty); 60 mA/LED full-white is a transient the buck's 2 A rating absorbs.
  L2 fitted load: 1.19 A → **0.92 A** (59 % of the 1.6 A limit, 653 mA spare).

Result: **U8 worst case 114 °C against 150 °C — 36 °C margin, best case 87 °C** — with every
input now sourced or budget-honest. The T3 thermocouple measurement in `docs/BUILD.md`
stands: θ_JA is layout-dependent, and the bench gate, not the model, clears the board to
fly. `check_thermal.py` / `check_build.py` / `design.py` (`RAIL_5V`, `NET_CURRENT`) and the
BUILD.md T3a table were all updated together.

##### Warning 2 — J3 plug clearance (5.30 mm vs 6.0 mm nominal): closed by fixing the model

First attempted the board fix: move R21 1.0 mm out of the plug corridor. The corridor is
**geometrically saturated** — mouth-to-TP20 is 7.03 mm total, and R21 plus the adjacent GND
via fence and TP20's stub cannot yield a 6.0 mm corridor even with the via relocated
(~5.9 mm theoretical best). The 1 mm move landed R21 on a GND via and two tracks —
**caught by preflight's own DRC gate, which is exactly what that gate is for** — and was
reverted. The board is byte-for-byte the pre-attempt artwork.

The real defect was the requirement, not the layout: the 6.0 mm "plug + wire bend"
allowance was a class figure. The JST-GH pigtail's wires exit at ~3.5 mm altitude and R21
is 0.55 mm tall, so no bend allowance over R21 is needed at all: **required 3.6 mm,
measured 5.30 mm — 1.7 mm clear.** `design.py` now derives the allowance from part
geometry instead of asserting a nominal, `check_connectors` passes with 0 warnings, and
`docs/BUILD.md` adds an assembly step: test-fit the actual pigtail before closing the
stack (the one thing the model cannot verify).

##### Lidar: the economics changed — bought-class sensor at 1/8 the budgeted price

The Okdo LD06 development kit (£13.99, eBay, new) supersedes the £19 est / "$99–131, do
not buy yet" verdicts. Verified against the kit teardown (usedbytes/rp2040-okdo-lidar and
the gibbard.me writeup): the **LD06 module is separate from the Pi HAT** — the HAT/bracket
does not have to be used — and the module's protocol matches what `design.py` and
ArduPilot's LD06 driver expect exactly (0x54-header 47-byte frames, CRC8 poly 0x4D,
230400 baud, TX-only into TP6). `docs/PARTS.csv`, `docs/BUYING.md` and `design.py`
updated (source: quoted/eBay). Two honest notes kept: the kit's bracket is a Pi-hole
bench jig, not the flight mount — the printed bracket is still required; and the LD06
remains an indoor-class sensor (25 klux) — the LD19 swap for outdoor missions stays the
documented upgrade.

##### Lidar ground clearance: settled at the 5.0 mm requirement

The mid-review 15 mm figure came from an earlier bracket concept, not a sensor
requirement. Requirement stays **5.0 mm; measured 10.20 mm** — 2× margin, and the margin
protects the right thing: belly-mounted inverted (PRX1_ORIENT 1), the LD06's spinning
turret is the lowest solid part of the aircraft, so clearance there shields the most
delicate element while the skids, not the sensor, take landing loads.

##### Board status

No board edits survive this pass (the one attempted edit was reverted). Gerbers, drill,
BOMs, CPLs and renders regenerated from the restored artwork; `preflight.py`:
**READY TO ORDER — 0 blocking failures, 1 warning** (In4.Cu fragmentation — accepted,
counts refreshed in `docs/LAYOUT.md` and the section above).

#### Third pass, same day — indoor sensor suite and ToF mounting questions

Three questions asked of the design; what each returned.

**1. Is the lidar the right indoor sensor versus the ToF ring? Yes — and the reasoning
was already measured.** `docs/SENSORS.md` superseded the 8 × VL53L1X ring with the LD06
on quantified axes: native ArduPilot driver (`PRX1_TYPE 16`) vs a to-be-written hub
firmware, 12 m vs 3.6 m, continuous 360° vs ~40 % of the horizon blind between 27° cones,
one wire vs 8 sensors + TCA9548A + MCU hub, and — now at £14 — cheaper than the ~£30 ring
it replaced. The ring analysis is deliberately kept as a marked-superseded record. What
was missing was the *external* comparison, so `docs/BENCHMARK.md` gained **§2c**: the
Crazyflie Flow deck v2 uses exactly this board's two parts (PMW3901 + VL53L1X) but its
Multi-ranger is 5 fixed beams with the same between-beam blindness in miniature; DJI's
indoor stability comes from closed visual positioning (which this aircraft deliberately
does not run — §2 of the same file); and LD06-on-PX4 is still not native (community
thread, Aug 2025), which makes the ArduPilot choice the drop-in one.

**2. Are the two ToF sensors mounted properly, top and bottom?**

- **Downward (close-range altitude):** the on-board `U7` is deliberately DNP — it faces
  the ESC 3 mm away and can never see the ground (documented reason, `design.BELLY_SENSOR`).
  The real downward sensor is the off-board TFS20-L (outdoor) or a VL53L1X module in the
  belly slot, modelled as `belly_sensor()`, gated by `check_cad_fit.py` — 31.50 mm above
  the skid contact plane — and wired as a J3 tap on I²C1 @ 0x10 / 0x29. Verified correct.
- **Upward (ceiling):** settled 2026-09-04 in `docs/SENSORS.md` — fore or aft of the
  battery on the parsed 42.50 × 160.26 mm top plate (22.26 mm free in length; battery at
  one end gives the ≥11.5 mm cone standoff and *improves* the CG to −3.0 mm), address 0x29
  freed by `U7` being DNP, `RNGFND3_ADDR 41`.
- **Two stale BUILD.md sections contradicted that settled answer** (one said the top plate
  was "never parsed", the other still carried the pre-skid-raise 28.5 mm belly depth and
  DXF hole coordinates that didn't match `design.py`'s parsed values). Both rewritten to
  the parsed, gated state. Lesson repeated: this file's two mounting sections had drifted
  behind both `design.py` and `docs/SENSORS.md` — the third such drift this week.

**3. Improvements against commercial and DIY drones?** Recorded as `BENCHMARK.md` §2c
conclusions: (a) the LD06 is what serious indoor platforms converge on once size allows,
not a compromise; (b) the real gap to commercial indoor drones is an indoor *position
estimate* — closed here by fitting the already-on-board PMW3901 (`U6`) + downward VL53L1X,
the identical Crazyflie pairing, with the one honest caveat that flow and the downward
rangefinder compete for the single belly slot (`design.BELLY_SENSOR`); (c) what this
aircraft has that none of the field does is the bounded radio-based fix (SoOP) plus a
SITL-proven pipeline.

Doc-only pass: no board, geometry or firmware changes. `docs/BUILD.md` (2 sections),
`docs/BENCHMARK.md` (§2c + header date), this file.

---

## What is NOT asserted — the honest gap list

Audited 2026-09-04. The apparatus is dense where it is dense and absent where it is
absent, and the absences matter more than the count of passing checks.

| gap | why it matters | how it gets closed |
|---|---|---|
| **RF self-interference** | The payload's entire purpose. No checker mentions `EMI`, `desense`, `noise floor`, `1620` or `SAWbird`. A 1616–1626.5 MHz receiver at −110 dBm sits on an airframe with two switchers, a 60 A ESC and a 2.4 GHz transmitter. | `docs/BUILD.md` **T3b** — four bench measurements, before T4, now gated by `tools/check_rf.py` |
| **Thermal** | Only *resistor* dissipation is checked (`check_ratings`). Nothing covers the H743 junction temperature at 480 MHz, the two bucks' losses, or that a 30×30 stack between an ESC and a battery has almost no airflow. | Compute buck loss from the ngspice results already in `sim/`; thermocouple at T3 |
| **Vibration / IMU isolation** | 178 mm props, 1123 g; the grommets isolate the *stack*, not the sensors. `INS_HNTCH_*` **is** configured (throttle-referenced, `FREQ 60`, `BW 30`, 3 harmonics) — an earlier draft of this table wrongly said it was not. But `FREQ 60` implies **3,600 RPM** at the `REF 0.35` hover point, while 1300 KV on 4S gives a hover fundamental nearer **108 Hz (~6,500 RPM)**. If that is right the notch is centred low and the harmonics fall outside `BW 30`. | Log `VIBE` and raw IMU at T4, read the peak off the FFT, and set `INS_HNTCH_FREQ` from the measurement — not from this arithmetic |
| **Antenna pattern and sky view** | The Iridium patch needs an unobstructed cone. Nothing models where it mounts, whether the props or battery shadow it, or its ground plane. | Add it to `cad/drone.scad` and `check_cad_fit`'s `PARTS`; state the required cone |
| **Motor thrust** | `[A] 1250 g`. Every thrust-to-weight and payload figure inherits it. | Thrust-test one motor, or obtain the manufacturer table |
| **SoOP accuracy on this hardware** | Now `[L] 180 m` from the literature rather than `[A] 20 m` — an improvement, but still not a measurement of this antenna on this airframe. | Ground test: `gr-iridium` reports per-burst frequency, so the real sigma is obtainable on a desk |
| **ESC cable continuity** | Genuinely desk-unverifiable | Buzz it before applying VBAT — `BUILD.md` T1 |
| **Grommet compressed height** | `[A] 3.0 mm`, and it feeds the standoff calculation | Measure on arrival |
| **LD06 scan-plane height above its mounting base** | `design.OFFBOARD['lidar']['scan_plane_height_mm']` is `None`. It decides where the printed belly bracket may grip the body **without blinding the sensor**, and it sets how far the scan plane sits above ground. The datasheet gives it only as a *drawing* (section 3, "Optical Windows and Mechanical Dimensions") with no extractable text, so it is genuinely unknown rather than merely unrecorded | Calipers on arrival, **before printing the bracket**. Everything else about the mount is settled: body 38.59 × 38.59 × 33.30 mm, 10.20 mm of ground clearance, 20 mm blind zone, ±2° angular error |

**Both checkers named here have now been written** (2026-09-04), following the existing
"declare in `design.py`, assert in `check_*.py`" split:

- **`tools/check_thermal.py`** — buck dissipation from the `sim/` ngspice figures, H743
  worst case, and a stated airflow assumption. It is wired into `preflight.py` as a
  **warning, not a blocker**, because `theta_JA` is layout-dependent and the honest output
  is a bracket (119–165 °C) rather than a number.
- **`tools/check_rf.py`** — not a simulation but a *gate*. It computes nothing and cannot
  be satisfied by a board that has never been switched on: it refuses to report
  ready-to-**fly** (as distinct from the ready-to-**order** `preflight.py` governs) until
  the four T3b measurements exist in `fab/rf-bench-results.json`.

  It also asserts the run is **internally consistent**. The four steps are cumulative —
  each adds a noise source without removing the last — so bursts must be non-increasing.
  A step scoring higher than its predecessor means the sky moved, the antenna moved, or
  two sessions were mixed; attributing a culprit from that data would point at the wrong
  one, which is the whole reason the steps are ordered. Both the pass and fail paths were
  exercised against synthetic results before the tool was committed, because a gate that
  has only ever been run against a missing file is not known to gate anything.

## What the DRC warnings are, and which ones are deliberate


Every tool in `tools/` runs `kicad-cli pcb drc --severity-error`. That is the right gate
for shipping — but it means warning-level violations had never once been looked at, and
`--schematic-parity` had never been run at all. This is that audit.

**Errors: 0. Unconnected: 0.** Everything below is warning level.

### Fixed as a result of this audit

| was | what it was | what happened |
|---|---|---|
| **23 × `hole_to_hole`** | Via pairs 0.2025–0.2464 mm apart against the board's 0.2495 mm rule — and JLCPCB's 0.254 mm same-net minimum. `route.HOLE_CLEAR` was **0.20**, looser than the board's own rule, so placement kept producing them. | All 23 cleared by `tools/thin_vias.py`, which drops the more redundant via of each pair with DRC verification. `route.HOLE_CLEAR` raised to 0.25 so it cannot recur. |
| **199 × `footprint_symbol_mismatch`** | `gen_pcb.py` loads footprints by path, so their FPID had no library nickname and every part mismatched a symbol that had one. | `tools/fix_fpid.py` restored all 156; `gen_pcb.py` now sets it at load time. |
| **8 × stale `Value` fields** | The board's footprints still carried the **pre-correction** divider values — `R7` read `3k24` and `R6` read `10k2`, the values that made a 3.32 V rail instead of 5 V. The BOM and schematic had the corrected 5k1/27k, so nothing ordered was wrong; the fab drawing was labelling the parts incorrectly. | Re-synced from `design.py`. |

Schematic parity went from **218 issues to 57**.

### Accepted, with reasons

| remaining | why it is left alone |
|---|---|
| **38 × `footprint_symbol_mismatch`** | All are *"'Exclude from bill of materials' settings differ"* on `TP1`–`TP21` and the solder pads. They are copper features, not parts; the BOM correctly omits them. Cosmetic flag differences between symbol and footprint. |
| **19 × `net_conflict`** | *"No corresponding pin found in schematic"* on `PWM11`, `PWM12`, `IMU3_CS`, `SPI2_*` and friends. These are MatekH743 pin-identity placeholders — MCU pins declared so the hwdef namespace stays identical, with no second endpoint to draw a net to. Deliberate, and documented in `docs/HARDWARE.md`. |
| **45 × silkscreen** (`silk_overlap` 23, `silk_over_copper` 17, `silk_edge_clearance` 5) | Reference designators colliding on a board that is 67.5% courtyard. JLCPCB clips silkscreen off pads during fabrication, so the physical result is legible-where-it-fits rather than wrong. Fixing them means moving text on 45 parts for no functional gain. |
| **19 × dangling copper** (`track_dangling` 11, `via_dangling` 8) | Stubs left by the surgical rip-and-reroute work. The board is at 0 unconnected, so none of it carries current. Removing them wholesale costs 2 connections — they are not as disconnected as the label suggests — and picking them off individually is 19 verification cycles for litter. |
| **1 × `lib_footprint_mismatch`** | A footprint on the board differs from the current library copy. Expected: several footprints were placed and then edited in place by the surgical tools. |

### What to run

```bash
kicad-cli pcb drc --schematic-parity --severity-all \
    --output /tmp/nav/full.rpt NAVCORE-SoOP.kicad_pcb
grep -oE '^\[[a-z_]+\]' /tmp/nav/full.rpt | sort | uniq -c | sort -rn
```

Worth repeating after any batch of surgical edits — that is what turned up the stale
resistor values, which nothing else on the board would have caught.

### Rule severities — reviewed 2026-08-29

Five rules had been set to `ignore`, with no recorded reason. Four are now **errors**:

| rule | why it is now an error |
|---|---|
| `missing_courtyard` | `check_connectors.py`, `check_mechanical.py` and `dimensions.py` all derive their geometry from courtyards. A footprint without one is invisible to every mechanical check on this board — it would pass silently rather than fail. There are currently 0 offenders, so enabling it costs nothing today and stops a future one being unmeasured. |
| `footprint_type_mismatch` | an SMD part declared through-hole changes paste, courtyard and assembly |
| `npth_inside_courtyard` | a mounting hole inside a part body |
| `pth_inside_courtyard` | as above, plated |

The fifth, **`footprint_filters_mismatch`, is a `warning`** rather than an error, and this
is the reason:

> `D1` (SMBJ18A, LCSC C19077573 — was SMBJ33A/C19077586, see §1c) uses
> `jlc:DO-214AA_L4.4-W3.6-LS5.3-RD`. The generic
> `Device:D_TVS` symbol carries footprint filters `TO-???* *_Diode_* *SingleDiode* D_*`,
> which match KiCad's own library naming, not this project's `jlc:` library. **DO-214AA
> is the correct package** — verified against the part's own LCSC page, which gives
> DO-214AA (SMB), 33 V standoff, 40.6 V breakdown, 600 W. The mismatch is a filename
> convention, not an electrical or mechanical fault, and every part on this board comes
> from the `jlc:` library, so raising it to an error would fail the board for its own
> naming scheme.

A warning rather than `ignore` keeps it visible: if a genuinely wrong footprint is ever
paired with a symbol, it still shows up in the report.

---
