# NAVCORE-SoOP — build, bring-up and first flight

Order to first flight, the T1-T5 power-on checklist, and the function-by-function
readiness matrix. Merged from BUILD.md, BUILD.md and BUILD.md.

## NAVCORE-SoOP — order to first flight


Written 2026-09-02. Answers one question honestly: **order everything today, build it,
fly it — what happens?**

The short version is at the bottom. Read it first if you only read one thing.

This document does not repeat what other documents prove. It says, at each step, *what
has been verified, by what, and what has not.* Every figure is tagged
**[M]**easured / **[D]**atasheet / **[L]**isting / **[A]**ssumed / **[U]**nknown.

---

### Stage 1 — Ordering the PCB

**Status: ready. This is the most verified part of the project.**

| | |
|---|---|
| DRC errors | **0** blocking, 0 unconnected pads |
| Gerbers | 16 files, 6 layers, `fab/gerbers/` |
| BOM / CPL | 3 variants, 118 designators each, no duplicates |
| Board | 45.10 × 46.10 mm, 30.50 mm M3 pattern |

Three BOM/CPL variants exist because the assembly choice changes what is placed:

| variant | places | for |
|---|---|---|
| `NAVCORE-SoOP` | 115 parts | everything including FPV |
| `NAVCORE-SoOP-economic` | 114 parts | JLC Economic assembly |
| `NAVCORE-SoOP-nofpv` | 99 parts | no VTX rail populated |

**What cannot be checked from here, and will cost money if wrong:**

1. **JLCPCB's own upload preview.** Outline, panel size, CPL orientation, stackup, drills.
   No local tool substitutes for looking at their render.
2. **1 oz outer copper.** Every current-capacity figure in `check_build.py` assumes it.
   Order 0.5 oz by accident and the margins in Stage 4 are halved.
3. **LCSC stock**, captured 2026-08-23 and stale by now. Check all 50 lines.
4. **The 1620 MHz SAW filter is not stocked at LCSC.** This is why the RF front end is
   the SoOP config / a separate board. It is not on this order.
5. **ArduPilot board ID 9001 is unregistered.** Request it upstream before flashing, or
   accept that a future firmware could collide.

---

### Stage 2 — What arrives, and what to measure before spending more

> **The plates are now parsed from the DXF — see `design.PLATES`.** What is left is
> confirmation, not discovery:
>
> | check with calipers | parsed value | why it matters |
> |---|---|---|
> | top plate width | **42.50 mm** | the battery is 47 mm and already overhangs by 2.25 mm each side — there is no room for an upward ToF beside it |
> | bottom plate M3 positions | x = ±14.60 and ±11.00, **no 30.5 mm pattern** | so the FC *cannot* bolt under the bottom plate; that idea is closed |
> | which plate is top vs bottom | **inferred**, not labelled in the DXF | the 160.26 mm plate is the only one long enough for the 138 mm battery |
>
> Only the last row is genuinely open. Correct `design.PLATES` if the calipers disagree.


**The frame is now the manufacturer's own CAD, not a listing.** It was a Mark4 clone
specified from three reseller spec tables that disagreed with each other, with GEPRC's own
pages 404 — which is why this section used to be a list of things to measure on arrival.

It is now the **TBS Source One V5 7″ DC (£35.90, in stock UK)**, which is *open-source
hardware*: the frame's own DXF and DWG are published at
[tbs-trappy/source_one](https://github.com/tbs-trappy/source_one). The 30.50 mm and
20.00 mm stack patterns were parsed straight out of that file, independently of the
retailer's claims.

What the change bought, all measured:

| | Mark4 (was) | Source One V5 (now) |
|---|---|---|
| stack clearance | 2.7 mm | **7.7 mm** |
| motor screw into the boss | 5.5 mm (designed 4.0) | **4.5 mm** |
| prop gap | +30.8 mm | **+48.5 mm** |
| standoffs | unpublished | **30 mm and 22 mm** |
| dimensions from | 3 resellers, disagreeing | **manufacturer DXF** |

**Standoff length was never a frame constraint**, and treating it as one was an error.
M3 standoffs are a few pounds in any length — 25 / 30 / 35 / 40 mm. Same for the motor
screws: a £4 M3 assortment removes the arm-thickness question entirely.

**The frame does not include landing legs.** The repo publishes `SO1-V6-skate.stl` —
measured at 76.0 × 102.2 × 6.0 mm, a **flat wear plate, not a leg**. The clearance checks
assume a **40 mm** drop — set from the LD06's 33.30 mm height plus margin, see
`docs/SENSORS.md` — so real printed legs remain an open item.

**3D printing:** every published accessory fits an Ultimaker 2+ (223 × 223 × 205 mm) with
room to spare — skate, camera mounts, GoPro, antenna and SMA mounts. **The plates would
fit too, but do not print the arms.** They carry motor thrust, absorb landings and see
continuous prop vibration; printed plastic fails in fatigue with 4 × 1250 g of thrust
behind it.

**Answer these from the published DXF before ordering** — `check_mechanical.py` lists
them under "ANSWER THESE FROM THE PUBLISHED CAD":

- **centre-plate opening** — must clear 45.1 × 46.1 mm plus plug protrusions. The one that
  decides fit, and the reason the frame was changed
- **standoff positions relative to the board corners**
- the USB edge: `J1`'s mouth is **flush with the board outline, zero slack**. Any standoff,
  plate lip or strap crossing that edge makes the port unusable
- **board rotation** — all four edges carry a connector; there may be exactly one
  orientation that works. Decide before cutting looms

**Settled, do not go measuring:** top plate height (7.7 mm spare at 30 mm standoffs) and
motor screw length (arm thickness is published).

**Genuinely physical, no drawing can answer:** microSD withdrawal clearance, which depends
on how *you* mount it; and grommet compression under load, which is a property of the
rubber.

---

### Stage 3 — Bring-up

Follow `docs/BUILD.md` T1 exactly. The order is not stylistic:

1. **Current-limited VBAT first, USB disconnected.** There is **no reverse-polarity
   protection** on this board.
2. Rail measurements before anything else is connected.
3. **Bootloader over SWD before USB flashing.** A board with no bootloader will not
   enumerate.
4. Copy `copter-deadreckon-home.lua` to the microSD at `APM/scripts/` **by hand** — the
   build script does not package it into the `.apj`. Without it, `FS_EKF_ACTION 0` ships
   with no GPS-loss response at all. That is stated in `defaults.parm` beside the value.
5. **Continuity-test the ESC cable before applying VBAT.** `J2` matches Betaflight's
   documented SpeedyBee F405 V4 order, but the cable you receive is [A] until you buzz it.
6. **Test-fit the GPS pigtail at `J3` before headers are soldered.** The board gives the
   plug **5.30 mm** of clear run before `R21` — inside the old 6.0 mm class nominal, but
   above the **3.6 mm** derived allowance (a pre-wired JST-GH pigtail exits its wires
   already parallel to the board at ~2–3 mm altitude; nothing 0.55 mm tall needs bend
   room — see `MATING_CLEARANCE['J3']` in `tools/design.py`). The residual risk is a
   bulky moulded boot or heatshrink on the pigtail: if the received cable will not sit in
   5.30 mm, remove the boot or swap the pigtail — **do not** move `R21`; the corridor
   behind it is saturated by `TP20` and a GND via fence and was mapped on 2026-09-05.

---

### Stage 4 — Mechanical assembly

#### The stack

`22.3 mm against 25 mm of inner space — 2.7 mm spare` [M]. Two different figures exist
for this and both are correct about different things:

- `check_build.py` → **19.8 mm**, bare parts
- `check_mechanical.py` → **22.3 mm**, including `J3`'s mated plug — **this is the one the
  top plate must clear**

#### Fasteners

`tools/fasteners.py` derives 2 joints and warns on both. **Read the warnings, they are
the point:**

- **Motor to arm, skid sandwiched: 12.5 mm needed → M3×14.** M3×13 is not a stock length,
  so the nearest stock screw drives **5.5 mm into the thread where 4.0 was designed.**
  A motor boss is often only ~4 mm deep. A bottomed-out screw feels tight while clamping
  nothing — the failure that throws a motor in flight. **Measure the tapped depth.** A
  12 mm screw plus a washer is the usual fix.
- **FC to ESC: 10.2 mm needed → M3×12**, same trap, 5.8 mm engagement.
- The **3.5 mm skid thickness is [A]** and it is what sets the motor screw length. Measure
  the skid you buy.

#### Landing legs

- Skids must match the **19 × 19 mm motor pattern**, not 16 × 16. The 2806.5 is the
  larger one, and the frame offers both — buying the wrong pair is easy.
- The skid sandwiches between motor and arm, which is why it lands in the screw
  calculation above.
- Modelled as four vertical legs at the motor pattern. That proves the **contact height**
  and the lens-protection relationship and nothing else: **the real TPU gear's shape,
  hole pattern, arm clearance and strength are all unverified** [A].
- **Ground clearance is what protects the camera you have not bought yet** — 13.0 mm of
  margin between the lens line and the skid contact line, on [A] skid dimensions.

#### The companion

**Radxa Zero 3W (1GB), ~£18.** Chosen after the Raspberry Pi Zero 2 W turned out to be
unbuyable: RRP £14.40, sold out at The Pi Hut *and* Pimoroni, £70 on the open market.

- 65 × 30 mm [D], same Pi Zero footprint
- **mounting hole pattern is NOT published** [U]. Resellers claim "same as the Pi Zero",
  but the only figure any of them gives — 61 mm diagonal — does not match the Pi Zero's
  `hypot(58, 23) = 62.4 mm`. **Measure the board. Do not cut a tray to a guess.**
- It mounts **separately on the top plate**, not in the 30 × 30 stack: at 65 mm long it
  overhangs this 45.1 mm board by 10 mm at each end.
- Runs from **its own 5 V BEC**, never this board's rail. At 0.7 A peak it was 37 % of
  the 5 V rail and put `L2` at 118 % of its 1.6 A rating.

**The Orange Pi Zero 2W was rejected: it has no MIPI CSI connector at all.** Confirmed
from the vendor's own 176-page manual, which documents USB (UVC) cameras only and contains
no occurrence of "CSI" anywhere. Not relevant to this build — see Stage 5 — but it is why
the £25 board is not on the list.

---

### Stage 5 — Optical flow is deferred, and that is a real decision

**No flow camera and no companion computer are fitted — both deferred (2026-09-02), with the SoOP chain.** The reasoning, including the half of it that was wrong:

**Right:** flow is not the position source. **SoOP is.** The IMU only bridges between SoOP
updates, and at 5 Hz that is 0.2 s — **0.3 mm** of accumulated error at a realistic 0.1°
tilt. The estimator does not need flow while an absolute fix is arriving.

**Wrong:** *"two good IMUs won't drift."* Every IMU drifts, **quadratically**, and the
dominant term is not accelerometer bias — it is attitude error leaking gravity into the
horizontal axes, `a = g·sin θ`:

| tilt error | 10 s | 30 s | 60 s | 120 s | 300 s |
|---|---|---|---|---|---|
| 0.05° | 0.4 m | 3.9 m | 15.4 m | 61.6 m | 385 m |
| **0.10°** | **0.9 m** | **7.7 m** | **30.8 m** | **123 m** | **771 m** |
| 0.30° | 2.6 m | 23.1 m | 92.5 m | 370 m | 2311 m |

**A second IMU does not help this.** Averaging two units improves white *noise* by √2 and
does nothing for bias or tilt error, which is what that table is made of. Redundancy
protects against an IMU *failing*, not against physics.

Flow would not have fixed it either — `flow_only` measures **p95 446 m**, because flow is
a *velocity* aid. What it buys is turning quadratic drift into roughly linear drift during
a SoOP outage.

**Why deferring is acceptable:** the dead-reckon applet's response to SoOP loss is to fly
**home immediately**, not to hold, so the unaided window is tens of seconds; and first
flights are on real GPS anyway.

**What is given up, plainly:** without flow the aircraft has **no independent opinion about
its own motion**. If the SoOP solution is confidently wrong, nothing contradicts it.

**What the aircraft cannot do today, said plainly.** With no GNSS, no flow and no external
nav, there is **no horizontal position estimate indoors**. ArduPilot has exactly three
non-GNSS horizontal position sources — optical flow, external navigation, and beacons —
and none is fitted. Indoors there is therefore **no Loiter, PosHold, RTL or Auto**: the
pilot flies Stabilize/AltHold, the downward TFS20-L holds altitude, and the ToF ring (MCU
sensor hub, `PRX1_TYPE 2` once fitted) only *stops the aircraft before walls* — it is
obstacle avoidance, not position hold.

**No parameter changes.** `FLOW_TYPE 5` still ships and that is correct with no camera:
the arming check tests the *parameter*, not sensor health, so it arms fine and is ready
the moment a companion publishes. Setting it to `0` while `EK3_SRC2_VELXY` and
`EK3_SRC3_VELXY` are `5` is what would **ground the aircraft**.

> **Operational rule while no flow is fitted:** source sets 2 and 3 both use flow for
> `VELXY` and therefore have **no velocity source**. They are reachable only by the RC9
> switch (`RC9_OPTION 90`). **Do not select source set 2 or 3 in flight.** Set 1 — GPS,
> which is also how the SoOP fix arrives — is the only one with data behind it.

Adding flow later costs a Radxa kernel rebuild plus a device-tree overlay with
`pwdn-gpios = <&gpio3 RK_PC6>`. That GPIO is **corroborated by Radxa's own schematic**
(J7 pin 18 = `CAMERAB_PDN_L` = `GPIO3_C6`), not just by the forum post it came from.

---

### Stage 5b — What a future payload can have

Kept deliberately generic: a gimbal, a dropper/winch, a parachute and a deployable arm all
want the same three things, and none of them is decided yet.

| | provision | verified by |
|---|---|---|
| actuator channels | **PWM5 / PWM6** at `TP3` / `TP4` — set `SERVO5_FUNCTION` / `SERVO6_FUNCTION` | `check_payload.py` |
| serial link | **`SERIAL2` (USART1)** at `TP5` / `TP6` | `check_payload.py` |
| power | 5 V at `P71` `P61` `P51` `PL2` `P41`; GND at `P74` `P64` `P54` `PL3` `P46` | `check_build.py` |
| mass | **885 g** at 40% hover throttle, 1385 g at 50% | `check_build.py` |

Three things worth knowing before designing against this:

- **`SERIAL4` and `SERIAL6` exist in the hwdef but are routed to no pad.** Real to the
  firmware, unreachable with a soldering iron. Do not plan around them.
- **Give a high-current actuator its own BEC.** The 5 V rail runs 1.19 A of a 3.0 A
  regulator with everything fitted; a stalled hobby servo can eat the remaining headroom
  on its own. Signal is 3.3 V logic, which every hobby servo accepts as a valid PWM high.
- **This is asserted, not asserted-once.** `preflight.py` gates `check_payload.py`, which
  checks the channels are still unclaimed in `defaults.parm` and still exist in
  `hwdef.dat`. The failure it exists to catch is something later quietly taking the last
  free channel while the documentation goes on promising it.

### Stage 6 — Will it work first time?

Split the question, because the honest answers differ.

#### Will it fly? — **Probably yes.**

Thrust-to-weight **4.5 : 1** at 1120 g AUW [A on thrust]. Power, copper, connectors,
protocol, chemistry and current-sense scaling all check out. 38 build checks pass.

#### Will it fly *GNSS-denied*, first time? — **No, and you should not try.**

This is the finding that matters most, and it is measured rather than feared.

Six SITL runs of the shipped configuration, one per seed, nothing else changed:

| | seed 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| `soop_gpsinput` p95 | **270 m** | 48 m | 70 m | 24 m | 30 m | 39 m |
| `soop_dropout` p95 | **393 m** | 68 m | 80 m | **457 m** | **217 m** | 43 m |

**The outcome is bimodal — it holds, or it runs away.** Bounded runs top out at 79.6 m;
diverged runs start at 216.7 m; nothing lands in between. And `p95` tracks the vehicle's
*true* excursion almost exactly in every diverged case (393/473, 457/494, 217/230) — the
aircraft genuinely flies away, these are not noisy measurements of a stable hold.

**`soop_dropout` diverged on 3 of 6 runs. `soop_gpsinput` on 1 of 6.**

Two caveats, both cutting toward "unknown" rather than "fine":

- The SoOP model (**180 m sigma, 2 s latency**) is **[L]iterature**, not a measurement of
  any real receiver. The real thing could be better or worse.
- Variation **survives a fixed seed** — `--seed` defaults to 1 and seeds only the error
  model; SITL itself gets no seed. Two runs at seed 1 gave 52.5 m and 270.3 m.

#### What does work, and is regression-guarded

- **`FS_EKF_ACTION 0` + the dead-reckon applet**, measured against the rejected
  `ACTION 1`, which cancels RTL into LAND at t+78. Both configurations are kept runnable.
- **`FS_EKF_ACTION 2` is dangerous here** — it disarmed the aircraft in flight at 12 m when
  the radio was cut in AltHold.
- Radio failsafe → RTL on a non-GPS position.
- 76 parameters, all existing in the firmware this board targets.

#### The order to do things in

1. Fly it **on GPS**, props off first, then hover. Confirm motor mapping, direction,
   `BATT_AMP_PERVLT`, and thrust against the [A] 1250 g figure.
2. **Characterise the real SoOP receiver** before denying GPS. Feed its actual noise and
   latency back into `sitl/soop_link.py` and re-run the sweep. The **180 m / 2 s** model is
   the single biggest assumption in the project — 180 m is `[L]`, from the literature, not
   a measurement of this receiver. (This step said "20 m / 2 s" until 2026-09-05, which was
   the retracted `[A]` figure.)
3. Only then fly GNSS-denied, **high, over open ground, with the applet fitted and RTL
   ready** — and expect the bimodal behaviour above until the real receiver says otherwise.

---

### Stage 5c — The SoOP receiver, and why it no longer needs a board respin

**This is the part that makes the project's headline claim true rather than assumed**, and
until now it was blocked on the wrong thing.

The RF front end was kept off-board because the **1620 MHz SAW filter is not stocked at
LCSC**. That framed the receiver as a board-design problem. It is not: the Iridium
reception community solved this chain years ago and every piece is off the shelf.

| part | what it is | ~£ |
|---|---|---|
| [Nooelec SAWbird+ IR](https://nooelec.com/store/sawbird-plus-ir.html) | **dual ultra-low-noise LNA around a 1620 MHz SAW**, 60 MHz bandpass, ≥30 dB gain, 180 mA, EMI-shielded | 35 |
| [Nooelec 1620 MHz Iridium patch](https://www.nooelec.com/store/sdr/iridium-antenna.html) | 1.620 GHz centre, 80 MHz BW, 3.0 dBi+ | 25 |
| RTL-SDR (R820T2) | tunes to ~1.75 GHz, so 1616–1626.5 MHz is in range | 30 |
| [`gr-iridium`](https://github.com/muccc/gr-iridium) + `iridium-toolkit` | FFT burst detect → QPSK demod → frames | 0 |

**The SAWbird+ IR *is* the stage that could not be sourced.** Built, shielded, £35.

**A GPS patch antenna will not substitute.** GPS L1 is 1575.42 MHz; Iridium is
1616–1626.5 MHz — about 45 MHz away and outside a GPS patch's bandwidth.

#### Why this matters more than "the receiver works"

`iridium-toolkit` reports **per-burst frequency**, so the Doppler shift is directly
measurable on the ground with a clear view of the sky. That replaces the **`[A]` 20 m
sigma / 2 s latency model** in `sitl/soop_link.py` — the single largest assumption in the
project, which every SITL figure inherits — with measured numbers.

Until that is done, `sitl/` characterises a **model**, not the aircraft. Doing it converts
every number in the GNSS-denied section from a simulation result into a claim about
hardware. It is a weekend of work and about £90, against a board respin.

### Before you pay — what is asserted, and what is not

`tools/check_purchase.py` asserts **every interface between two separately-bought parts**,
and `preflight.py` gates it. That is the only error class that cannot be fixed in software
once the money has moved. It covers: motor shaft ↔ prop mount, prop ↔ frame clearance,
motor bolts ↔ arm, skid ↔ **motor** pattern (19×19, not the frame's 16×16), battery plug ↔
airframe, battery ↔ ESC chemistry, GPS cable ↔ `J3` pin order, ESC cable ↔ `J2`, the
TFS20-L **variant**, its 3.3 V supply, the upward VL53L1X address, the ELRS pads, and the
lidar's UART and sunlight rating.

**Three of those would have cost real money:**

- **The prop mount was modelled nowhere.** `PROP` had no bore and no mount type, so nothing
  could have caught props that do not screw onto the motors. Now `M5`/5 mm, asserted.
- **The TFS20-L comes in I²C and UART variants.** The I²C part works on `J3` at `0x10`. The
  UART part needs `SERIAL6`, which exists in the hwdef but is **routed to no pad** — a £32
  lidar with nowhere to plug in, and no software fix.
- **The battery is EC5 and everything else is XT60.** An adapter, not an incompatibility —
  but forgetting it grounds the aircraft on the day everything else arrives.

**Two interfaces still rest on an ASSUMED source** and the check names them every run:
the prop bore, and the skid bolt pattern. **Confirm both on the listing before paying.**

#### Genuinely unprovable at a desk

- **ESC cable continuity** — buzz the cable you receive before applying VBAT.
- **Grommet compression under load** — a property of the rubber, not of any dimension.
- **USB edge and board rotation in the assembly** — the frame DXF is a nested sheet, not
  an assembly, so it cannot show whether a standoff on a *different* plate fouls `J1`. The
  measured **1.04 mm end margin** on the FC plate is the number to watch.
- **Motor thrust** — `[A] 1250 g`. Every payload figure inherits it.
- **Landing-leg drop** — `[A] 25 mm`. The frame's published skate is a 6 mm wear plate.

### Summary

| stage | verdict |
|---|---|
| PCB order | **Ready.** 0 DRC errors, 16 gerbers, 3 BOM/CPL variants |
| Parts order | **Ready**, subject to LCSC stock and 1 oz copper confirmation |
| Frame fit | **7.7 mm spare**; centre-plate opening answerable in the published DXF |
| Fasteners | M3×14 at **4.5 mm into the boss** (designed 4.0) — buy an M3 assortment |
| Landing legs | **Still open.** The published skate is a 6 mm wear plate, not a 25 mm leg |
| 3D printing | Every published accessory fits an Ultimaker 2+; **do not print the arms** |
| Payload provisions | **2 free PWM + 1 routed UART + 885 g**, gated by `check_payload.py` |
| Purchase interfaces | **All asserted** by `check_purchase.py`; **2 still on an assumed source** — confirm on the listing |
| Proximity | **360 lidar replaces the ToF ring.** Buy ≥60 klux — *not* the 25 klux LD06 |
| Companion | **Deferred** with the SoOP chain; `SERIAL1` stays provisioned |
| Optical flow | **Deferred by decision.** No parameter change, one operational rule |
| First flight on GPS | **Expected to work** |
| First flight GNSS-denied | **Not yet.** Diverges on 1/6 to 3/6 simulated runs |
| SoOP receiver | **Unblocked.** ~£90 of off-the-shelf SDR, no board respin — see Stage 5c |

**The board is the finished part. The navigation claim is not.**

---

## The harness — seven runs, and how not to make a nest of them

Written because "cables everywhere" is a real build problem and the answer is mostly
*planning*, not tidying afterwards.

| run | wires | note |
|---|---|---|
| `J2` → ESC | 8-pin JST-SH | **comes with the ESC**; stays inside the stack, 3 mm long |
| `J3` → **GPS *and* both ToF** | 6-pin JST-GH | one cable, split at a junction — see below |
| `TP5`/`TP6` → LD06 lidar | 3 | **TX only**, plus 5 V and GND; the PWM input stays unconnected |
| `P41`/`P46` → ESP32 camera | 2 | 5 V and GND, nothing else |
| `P51`–`P54` → ELRS receiver | 4 | solder pads, no connector |
| `PZ1`/`PZ2` → buzzer | 2 | |
| `PL1`–`PL3` → LED strip | 3 | optional, cosmetic — drop it if you want one fewer |

**The trick that removes two runs:** the downward TFS20-L (`0x10`) and the upward VL53L1X
(`0x29`) sit on the **same I²C bus as the GPS's compass, on the same connector**. They are
not two extra cables — they are two taps off the `J3` cable that has to exist anyway. One
6-way JST-GH leaves the board and splits at a junction near the stack: GPS up, two
rangefinders out.

So realistically **five** runs leave the board, one of which is the ESC's own short cable.

### Attaching the downward ToF — the holes are known

The frame's DXF gives **two 4.00 mm holes at (±8.00, −19.75)** from the stack centre, on
the underside. A printed bracket takes two M3-with-washer bolts there, or VHB tape
straight to the plate — tape also damps vibration, which a laser rangefinder appreciates.
With the skid drop at **40 mm** (raised for the LD06), depth to the skid contact line is
**43.5 mm** and the module is ~12 mm, so **31.5 mm spare** — the position is modelled as
`belly_sensor()` in `cad/drone.scad` and gated by `check_cad_fit.py`'s ground-clearance
check (lowest vertex 31.50 mm above the contact plane).

### Attaching the upward ToF — settled 2026-09-04

An upward sensor needs a clear view of the ceiling, so it lives on top — where the
**138 × 47 mm battery already is**. The top plate **was** parsed (see the Stage-2 table:
42.50 × 160.26 mm), and the free space is in **length**: 160.26 − 138 = **22.26 mm**, fore
or aft of the pack. Full resolution with the CG math in `docs/SENSORS.md` ("Mind the
address" section): the battery sits at **one end, not centred**, so the sensor's 27° cone
clears the battery wall (needs ≥11.5 mm of standoff), and displacing the pack away from
the existing CG offset *improves* balance to −3.0 mm. Address note: `U7` (the on-board
VL53L1X at 0x29) is DNP on the Economic order, which is exactly what frees 0x29 for the
upward module — `RNGFND3_ADDR 41`.

### Routing rules, and one of them is specific to this aircraft

1. **Keep signal cables away from the four motor leads.** Those carry kilowatts switched
   at tens of kHz and are the aircraft's dominant radiator. On a normal quad that is
   good practice; on this one it is the difference between hearing Iridium bursts and
   not — see **T3b**.
2. Route along the arms and plate edges, zip-tied every 40–50 mm. Slack belongs in a
   single service loop near the stack, not distributed along a run.
3. Leave the **USB edge clear** — `J1`'s mouth is flush with the board edge and the end
   margin is 1.04 mm.
4. Antennas (ELRS 2.4 GHz, and the Iridium patch) get separation from everything else and
   from each other.

## Bringing up NAVCORE-SoOP


A checklist to work through with the board in hand, in this order. Each tier assumes the
one before it passed. The ordering is not arbitrary — every step is placed so that a
failure costs as little as possible.

Nothing here is optional. A board that skips T1 and goes straight to USB can destroy the
MCU on a rail fault that a current-limited supply would have caught for nothing.

---

### T1 — Power, before the MCU sees anything

**Do not connect USB yet. Do not connect a battery yet.**

Bench supply on `VBAT` (`J2.2` / the XT60 pads), **current limit 100 mA**, 16.8 V.

| # | Check | Expect | If wrong |
|---|---|---|---|
| 1.1 | Current draw at power-on | < 80 mA | Over the limit: something is shorted. Kill it, inspect `U8` / `U18` and the bulk caps |
| 1.2 | `+5V` rail | **4.97 V** ±0.2 | Check `U8` TPS54202, `L1`, feedback divider |
| 1.3 | `+3V3` rail | 3.3 V ±0.1 | Check `U9` AP2112 |
| 1.4 | `+3V3A` rail | 3.3 V ±0.1 | Check `U10` TLV75533 |
| 1.5 | `+9V` rail | **9.03 V** ±0.5 | Check `U18` TPS54202, `L5` |
| 1.6 | `+9V` with `PA7` floating | rail **ON** | Fails safe toward video-on by design — `R45` holds `Q3` off |

Raise the limit to 500 mA only once all five rails are correct.

> **Reverse polarity will destroy this board.** `D1` is a TVS, not a series diode: it
> clamps a reversed pack at −0.7 V until it dies, taking everything with it. The board has no
> reverse-polarity FET. Use the XT60's keying and check twice.

### T2 — MCU alive

| # | Check | Expect |
|---|---|---|
| 2.1 | USB-C connected, `lsusb` | a new device appears |
| 2.2 | Hold `BOOT`, tap `RESET`, release | `0483:df11` STM32 BOOTLOADER in DFU |
| 2.3 | Flash the bootloader | `Tools/bootloaders/NAVCORE_SoOP_bl.bin` via `dfu-util` |
| 2.4 | Flash the firmware | `arducopter.apj` |
| 2.5 | Connect a GCS | board reports `APJ_BOARD_ID 9001` |
| 2.6 | Read the boot messages | every fitted sensor probes; nothing unfitted is claimed |

Build both with `tools/build_firmware.sh` (pinned to `Copter-4.7.0`).

**USB cannot power this board.** `VBUS` runs the USB PHY only; the rails come from
`VBAT`. Bench work needs the supply connected as well. That would need a respin.

### T3 — Sensors on the bench, props OFF

| # | Check | How | Notes |
|---|---|---|---|
| 3.1 | IMU 1 (`U2`) orientation | roll/pitch the board, watch the horizon | `ROTATION_ROLL_180` is **asserted in hwdef, not measured**. Verify it |
| 3.2 | IMU 2 (`U3`) orientation | same, `INS_USE2` | only if `U3` was hand-fitted |
| 3.3 | Barometer | altitude tracks a lift of 1 m | |
| 3.4 | Battery voltage | compare against a meter | `BATT_VOLT_MULT 11.000` is derived from the 10k/1k divider and should be close |
| 3.5 | **Battery current** | draw a known load, compare | **`BATT_AMP_PERVLT 52.7` is a starting point, not a calibration.** It is a property of the ESC's shunt, not of this board |
| 3.6 | RC input | `RC_PROTOCOLS 512` (CRSF) | set back to 1 for SBUS/FPort |
| 3.7 | ESC telemetry | RPM appears with `SERIAL5_PROTOCOL 16` | receive-only on `J2.8` |
| 3.8 | Motor order and direction | **props off**, motor test | `J2.3`–`J2.6` = M1–M4 |
| 3.9 | Buzzer, LEDs | arming tone, strip lights | |

#### If the optional parts were fitted

| # | Check | Then set |
|---|---|---|
| 3.10 | TFS20-L reads correctly against a tape measure at 1 m, 5 m, 10 m | `RNGFND1_TYPE 46` (I²C @ 0x10) or `27` (serial) |
| 3.11 | VL53L1X (`U7`) reads at 0.5 m and 3 m | `RNGFND2_TYPE 16` |
| 3.12 | Take both outside into sunlight over grass and repeat | this is the measurement that matters — see `docs/SENSORS.md` |

**Everything optional ships disabled in `defaults.parm` and must be turned on here.** A
rangefinder that is configured but not present fails prearm and the aircraft will not
arm. That is deliberate: a bare board arms out of the box.

### T3a — Thermocouple on U8 **and U9**, and it is not optional

Two parts, and the second one is the hotter.

**`U8`, the +5 V buck.** `tools/check_thermal.py` brackets its junction at
**70–139 °C against a 125 °C recommended operating limit**. Both halves of that sentence
were wrong until 2026-09-05: θ_JA was cited as "89.2 °C/W from SLVSD26" and that number
is not in SLVSD26 — §5.4 gives **118.6 °C/W (JEDEC)** and **57.2 °C/W (EVM)** — and the
150 °C it was judged against is the **absolute maximum**, a destruct limit, where §5.3
puts the recommended operating junction maximum at **125 °C**. Both errors ran the same
way, and together they turned a measure-me into a comfortable "36 °C of margin". The rail
steps **16.8 V down to 5 V at 0.95 A** through a SOT-23-6 with no thermal pad, in a
sandwich between a 60 A ESC and a battery. This board is 6-layer with planes, so the
truth should sit near the EVM end — but that is an opinion until a thermocouple says so.

**`U9`, the 3.3 V LDO — which nothing had ever checked.** It is a **linear** regulator
dropping **1.7 V** from +5 V in a SOT-23-5 with no thermal pad, and it carries the
STM32H743, the config flash, the microSD card and the CAN transceiver. Its dissipation is
set by the load and the drop — there is no efficiency to improve, only copper:

| load | current | dissipation | junction, good copper | junction, minimal copper |
|---|---|---|---|---|
| continuous, in flight (logging, CAN recessive) | 311 mA | 529 mW | **93 °C** | 137 °C |
| peak (card write + CAN dominant + flash program) | 445 mA | 757 mW | **116 °C** | 179 °C |

against a **150 °C** operating junction maximum.

The two columns are θ_JA **100.8 °C/W** and **184 °C/W**. The high one is the AP2112
datasheet's own figure and it is explicitly labelled *"(No Heatsink)"* — a minimal-copper
bound, not this board. The low one is TI's measured EVM figure for the same SOT-23-5
package (SBVS293 §5.4), used here by analogy because θ_JA for a leadframe package with no
thermal pad is a property of the board, not the die.

**Which end this board sits at is measured, not assumed.** `tools/thermal_vias.py` reports
what each thermal pad is actually attached to: `U9.2` reaches **7443 mm² of GND plane**
across five layers, and `U9.5` reaches **739 mm² of +3V3 plane through five vias** (three
of which were added 2026-09-05; the search found no legal position for more without
disturbing existing routing, and DRC is clean). For scale, a JEDEC 2s2p "high-K" test
board is about 8700 mm². So the good-copper column is the honest expectation.

Note the continuous row **includes the microSD card**. ArduPilot logs for the whole
flight, so "idle between logs" describes the bench, not the aircraft.

Measure it anyway. The AP2112 has over-temperature shutdown, so if the estimate is wrong
**the failure mode is the flight controller browning out mid-flight, not smoke** — which
is worse, because it looks like a software fault.

**Measure it:** thermocouple or IR thermometer on `U8` **and on `U9`**, board powered at
4S, **stack assembled** (not on the bench in free air — the assembly is the thermal
problem), rails loaded as they will be in flight, **logging to the microSD card** so U9
sees its real duty, for **10 minutes** to reach steady state. Readings below are CASE
temperatures; the models bracket junction, and case sits roughly 10–15 °C below junction
on these packages.

| reading | verdict |
|---|---|
| **< 85 °C** case | comfortable — the optimistic end of the model was right |
| **85–105 °C** | acceptable but thin; check it again after a hover with the battery warm |
| **> 105 °C** case | stop. Junction is meaningfully above case; you are near the limit with no airflow margin |

If `U8` runs hot the fixes are, in order: trim the LED pattern's duty (free — it is a
firmware choice, and the budget already assumes strobe duty), move a load off the rail,
or pour more copper under `U8` (θ_JA is dominated by it — a respin change).

If `U9` runs hot the fixes are different from `U8`'s, because a linear regulator's
dissipation is set by the load and the drop, not by efficiency — spreading heat is all
copper can do. In order: cut the 3.3 V load (the CAN transceiver is 70 mA dominant and CAN
is unused on this airframe today — `CAN1_SILENT` is already on a GPIO, so holding it in
standby is a firmware change and costs nothing), or replace the LDO with a 3.3 V
**switcher**, which is the only fix that *removes* the 529 mW rather than spreading it.
Adding copper is already done as far as this layout allows.

### T3b — Can the SoOP receiver hear anything? Do this before T4.

**This is the least-verified risk in the project and the one most likely to end it.**
Nothing in `tools/` checks it: greps for `EMI`, `desense`, `noise floor`, `1620` and
`SAWbird` across every checker return nothing.

The aircraft is a hostile RF environment for a 1616–1626.5 MHz receiver working at
roughly −110 to −120 dBm:

| source | why it matters |
|---|---|
| two TPS54202 buck converters | ~500 kHz–1 MHz switching; harmonics reach into GHz |
| SpeedyBee BLS 60 A ESC | kilowatts switched at tens of kHz with fast edges, on four long motor leads that act as antennas |
| ELRS at 2.4 GHz | a strong transmitter centimetres away — front-end desense |
| STM32H743 at 480 MHz | broadband digital noise, harmonics near 1.6 GHz |
| a 5.8 GHz VTX, if fitted later | another transmitter |

**Measure it in four steps.** Each step that degrades the burst count names its own
culprit, which is the whole point of doing them in this order:

1. **Baseline.** SAWbird+ IR + RTL-SDR + patch antenna, outdoors, clear sky, **aircraft
   off**. Record `gr-iridium` bursts per minute and the noise floor. This is the reference
   and it needs no aircraft at all — it can be done the week the parts arrive.
2. **Board powered, motors off**, same position and same sky. Any drop is the flight
   controller: its switchers and the H7.
3. **Motors spinning, props off, tethered.** Any further drop is the ESC and the motor
   leads.
4. **ELRS transmitting.** Isolates receiver desense from the control link.

**Record the four numbers in a file.** They are the only evidence that the payload works
on the aircraft rather than on a bench, and every later accuracy claim rests on the
receiver actually hearing bursts.

Mitigations, cheapest first: antenna placement and separation → ferrites on the motor
leads → shielding the SAWbird → keeping the SDR off the airframe entirely for early
flights, which this board allows anyway because the receive chain is laptop-side.

### T3c — IMU temperature calibration. Free, and it attacks the dominant error.

**Do this before T4, and understand why it matters more here than on an ordinary quad.**

This aircraft's whole claim is that Doppler *bounds* inertial drift. That drift is
quadratic and dominated by attitude error leaking gravity into the horizontal channel — a
0.10° tilt error gives 30.8 m at 60 s and 123.3 m at 120 s. Gyro and accelerometer bias is
strongly temperature-dependent, and a flight controller sandwiched between a 60 A ESC and a
battery, in a 30×30 stack with almost no airflow, does not run at a constant temperature.

Commercial autopilots address this in **hardware**: the Pixhawk FMUv6X standard puts
resistive heaters on the IMUs and holds them at a set point. This board does not have one —
it is pin-identical to the MatekH743, which does not either. **ArduPilot's software
equivalent costs nothing and is available today**, and it is not configured:
`INS_TCAL*` is absent from `defaults.parm`.

Prerequisites are both satisfied here: temperature calibration needs a **2 MB** autopilot
(the STM32H743 has 2 MB) and a **microSD** for logging (`J8` is fitted).

| # | Step |
|---|---|
| 3c.1 | Run a full 6-axis accelerometer calibration first — this sets `INS_ACC*_CALTEMP` and `INS_GYR*_CALTEMP`, which the temperature fit is referenced to |
| 3c.2 | Cool the board below its minimum operating temperature. The documented method is domestic: a kitchen freezer, in a sealed bag against condensation |
| 3c.3 | Set `INS_TCAL1_ENABLE 2` (**2 = start learning**, not 1) and `INS_TCAL1_TMAX` to the target. Repeat for `INS_TCAL2_*` — there are two IMUs, `U2` (ICM-42688-P) and `U3` (ICM-42605) |
| 3c.4 | Power it up in a warm room and **do not let it move until the run completes.** Movement invalidates the fit silently |
| 3c.5 | Let the temperature rise through **at least 25 °C** of range — freezer to desk is the documented span. Allow 10 minutes minimum per temperature point |

**Do not put `INS_TCAL*_ENABLE 2` in `defaults.parm`.** It is a *learning* mode, not a
flight setting, and shipping it enabled would start a calibration on every boot. This is
the same rule the rest of this project follows for sensors: nothing uncalibrated and
nothing unfitted ships enabled.

**Verify it took** before trusting it: the offline tool plots bias against temperature, and
a good fit leaves the corrected traces near zero across the whole range. An uncorrected plot
is itself the useful artefact — it shows how much drift this specific board has, which is a
number this project currently only assumes.

### T4 — Tethered, props on

| # | Check |
|---|---|
| 4.1 | Arm in Stabilize, tethered, minimum throttle. Confirm all four spin the right way |
| 4.2 | Short hover. Land. Pull the log |
| 4.3 | Tune `INS_HNTCH_FREQ` and `INS_HNTCH_BW` from that log's FFT |

`INS_HNTCH_*` ships **conservative, not optimal** — the right values depend on props and
KV, which the board cannot know. Mode 3 tracks RPM from ESC telemetry, which is the
single biggest flight-quality win available here, but only once it is tuned.

### T5 — Flight, strictly in this order

Every step assumes the RC switch on `RC_OPTION 90` is assigned and you know which way is
back to GPS.

| # | Step | Watching for |
|---|---|---|
| 5.1 | GPS hover, Loiter | position holds; this is the baseline |
| 5.2 | **On the ground**, cycle the source-set switch through all three | no EKF errors, no mode drop |
| 5.3 | Low hover over **tarmac**, switch to SRC2 (flow) | holds position; note the drift rate |
| 5.4 | Same over **grass** | expect it to be worse — this is the measurement the project exists to improve |
| 5.5 | Enable the companion GPS: **`GPS2_TYPE 14`** (not `GPS_TYPE2`) | and the Pi must send `gps_id = 1` |
| 5.5b | **Start the Pi and confirm it is streaming, THEN arm** | anything judged healthy by data arrival must be arriving first |
| 5.5c | Confirm the Pi publishes at **5 Hz**, not at its solution rate | 1 Hz and 2 Hz both fail `PreArm: GPS 2: Bad fix` |
| 5.5d | Confirm the Pi's solution agrees with the live GPS on the ground | instances must agree within **50 m**, hardcoded, or it will not arm |
| 5.6 | On the ground, `SIM`-style denial: unplug the GPS antenna or shield it | `GPS_AUTO_SWITCH 1` should move to instance 2 on its own — watch the GCS say so |
| 5.7 | Low hover, deny the real GPS | **no switch needed** — failover is automatic. Watch position hold |
| 5.8 | Increase altitude, then range | |

> **The SoOP fix is a GPS, not ExternalNav.** `AP_VISUALODOM_TIMEOUT_MS` is 300 ms, so
> visual odometry needs better than 3.3 Hz; an Iridium Doppler solution arrives at about
> 1 Hz, so VisOdom health flaps — the aircraft arms intermittently and then quietly dead
> reckons on optical flow, which drifts. `GPS_TIMEOUT_MS` is 4000 ms. Measured in SITL —
> see `docs/SENSORS.md`.

> **The pairing rule.** An `EK3_SRCn_*` entry and its backend's enable parameter always
> move together (`VELXY 5` ↔ `FLOW_TYPE`, `POSZ 2` ↔ `RNGFND1_TYPE`). ArduPilot validates
> every configured source set at arm time, not just the active one, so a mismatch in a set
> you never select still grounds the aircraft.

> **Never test a new source set where you cannot switch back.** Low, over a clear area,
> with the switch in your hand.

### Before any of this: run it in the simulator

`sitl/run_scenarios.sh` flies the whole GNSS-denied sequence against simulated truth and
costs nothing. Every prearm interaction documented above was found there rather than in a
field. Do that first.

### Calibrations that cannot be derived

Three values are properties of your airframe, not of this board, and no amount of design
review can supply them:

- `BATT_AMP_PERVLT` — the ESC's shunt and amplifier
- `INS_HNTCH_FREQ` / `_BW` — props and KV, from a hover log
- `FLOW_ORIENT_YAW` — the flow source's mounting. **Get the sign wrong and the aircraft
  accelerates away from where it should hold.** Verify by hand-translating it, both axes,
  before trusting it in the air

---

## T0 — mechanical fit, before any soldering

Do this the day the frame arrives and **before** cutting a single loom. Everything below
is a number to check with calipers, not a "does it look right".

Run `python3 tools/check_mechanical.py` for the current values; they are recomputed from
the board, so this table can go stale and that tool cannot.

### What is already computed and needs no measuring

| | |
|---|---|
| Board | 45.10 × 46.10 mm, 30.50 mm M3 pattern, 4.00 mm holes |
| Stack, bottom plate to tallest part | **22.3 mm** against **25 mm** of inner space — 2.7 mm spare |
| Board underside sits at | 16.3 mm; its bottom parts hang to 13.8 mm |
| Clearance, ESC's parts to this board's | 3.0 mm |
| Tallest top-side part | `J3` GPS JST-GH, 4.40 mm |
| Tallest bottom-side part | `D1` TVS, **2.30 mm** — or `L5` at **3.00 mm** if the FPV buck is populated. (`L2` is on the *top* side.) |

The board is only **1.1 mm larger corner-to-corner than the ESC** (64.5 vs 63.4 mm), so
about 0.6 mm more clearance per corner. If the SpeedyBee stack fits the frame, this
almost certainly does — but it is 45 × 46 mm where a typical 30×30 flight controller is
36 × 36, so check rather than assume.

### Measure these

- [ ] **Centre-plate opening** clears 45.1 × 46.1 mm, plus the plug protrusions below.
- [ ] **Top plate** sits more than 22.2 mm above the bottom plate.
- [ ] **`J1` USB-C — the tight one.** Its mouth is **flush with the board edge**, zero
      slack, and the plug needs **6.5 mm clear beyond the top edge** at z 17.9–21.1 mm.
      Any frame standoff, plate lip, or the battery strap crossing that edge makes the
      port unusable, and it is the only way to flash the board.
- [ ] **`J2` ESC cable** needs 3.6 mm clear beyond the left edge at z 17.9–20.8 mm. Its
      body already sits **1.02 mm** from the nearest M3 grommet — the tightest clearance
      on the board — so route the cable away from that corner, not over it.
- [ ] **`J3` GPS** plug stays inside the board outline, but the body is 1.40 mm from a
      grommet. Nominal allowance is 6.0 mm and there is 5.30 mm to `R21`; measure the
      actual JST-GH plug, since 6.0 is a written-down figure, not a measurement.
- [ ] **microSD.** The card leaves on the **bottom** side, toward the bottom edge, and
      needs ~12 mm of travel through a gap only **3.0 mm tall** between the ESC's parts
      and this board. It fits — a card is 1 mm thick — but getting fingers or tweezers
      into a 3 mm slot is another matter. **Assume you will pull the board to change the
      card**, and decide now whether that is acceptable.
- [ ] **Board rotation in the frame.** All four edges carry a connector, so there may be
      only one orientation that works. Decide it before cutting looms.
- [ ] **Grommet standoff** holds 3.0 mm between the ESC's parts and this board's under
      compression. This is the one `[A]` in the stack — measure the grommets you get.
- [ ] **Grommet flange OD ≤ 5.9 mm.** `R21` sits **2.98 mm** from the hole at
      (+15.25, +15.25) on the **top** side. An M3 cap head (5.5 mm) clears by 0.23 mm; a
      6.0 mm grommet flange touches it; a 7 mm washer overlaps by 0.52 mm. **Do not fit
      washers on that corner.** Nearest copper at the other three holes is 3.11–4.65 mm.
- [ ] **Motor screws.** Arm 6 mm + skid 3.5 mm + 4 mm engagement = **M3×14**; the stock
      screws are M3×8–10 and will be too short once skids are fitted.
- [ ] **Landing skids must match the 19×19 mm MOTOR pattern**, not 16×16 — the
      BrotherHobby 2806.5 is the larger one.

---

## NAVCORE-SoOP — will it actually fly?


The layout being finished (472/472 connections, 0 DRC errors) says the copper is
manufacturable. It says nothing about whether the aircraft works. This is the other
half: every function a flying quad needs, where it lives, and the parameter that turns
it on.

Judged against the aircraft as it now ships — a quad on the SpeedyBee F405 V4 BLS 60A 4-in-1
ESC, GPS and external compass, ELRS/CRSF receiver, downward TFS20-L and upward VL53L1X
ToF, an 8-sensor ToF ring behind an MCU sensor hub (RP2040/Nano), a 9 V analogue VTX, a
WS2812 strip and a buzzer. **The optical-flow camera and the Radxa Zero 3W companion are
both deferred (2026-09-02)**; the pads, drivers and parameters that served them are kept
provisioned.

Verified by building real ArduPilot firmware for this board (`tools/build_firmware.sh`),
not by reading the hwdef and hoping.

### The matrix

| Function | Where it lives | Status | Parameter |
|---|---|---|---|
| MCU | `U1` STM32H743VIT6, 8 MHz xtal | on board | — |
| IMU 1 | `U2` ICM-42688-P, SPI1, bottom | on board | `ROTATION_ROLL_180` (hwdef) |
| IMU 2 | `U3` ICM-42605, SPI4, bottom | on board | `ROTATION_ROLL_180_YAW_270` (hwdef) |
| Barometer | `U4` MS5611, I²C2 @ 0x77 | on board | `BARO MS5611` (hwdef) |
| Compass | inside the GPS module, I²C1 on `J3` | **external, deliberate** | auto-probe; `ALLOW_ARM_NO_COMPASS 1` |
| GPS | `J3` (JST-GH 6P), USART2 | external | `SERIAL3_PROTOCOL 5` |
| RC receiver | pads `P51`–`P54`, USART6 | external | `SERIAL7_PROTOCOL 23` |
| Motors ×4 | `J2.3`–`J2.6`, DShot | on board | `MOT_PWM_TYPE 6`, `FRAME_CLASS 1`, `FRAME_TYPE 1` |
| Battery voltage | `J2.2` → 10k/1k → PC0 | on board | `BATT_VOLT_MULT 11.000` (derived) |
| Battery current | `J2.7` ESC shunt → PC1 | on board | `BATT_AMP_PERVLT` — **bench calibration** |
| ESC telemetry | `J2.8` → PE0 `UART8_RX` | wired, but **inert with a BLHeli_S ESC** | `SERIAL5_PROTOCOL 16` |
| Rangefinder (outdoor) | Benewake TFS20-L, I²C1 @ 0x10, **off-board** | to buy | `RNGFND1_TYPE 46` — **ships disabled** |
| Rangefinder (landing) | `U7` VL53L1X, I²C1, bottom | **not populated on the Economic order** | `RNGFND2_TYPE 16` — **ships disabled** |
| Rangefinder (ceiling) | VL53L1X module (GY-53-L1X), I²C1 @ 0x29, **off-board, top** | to buy | `RNGFND3_TYPE 16` — **ships disabled** (`ADDR 41`, `ORIENT 24`) |
| ToF ring (indoor avoidance) | 8 × VL53L1X → TCA9548A → **MCU sensor hub** on a spare UART | to buy, hub firmware to be written | `PRX1_TYPE 2` — **ships disabled** |
| Optical flow | camera on the companion, over MAVLink | **deferred with the companion** | `FLOW_TYPE 5` — `FLOW_ORIENT_YAW` **bench calibration** |
| Optical flow (fallback) | `U6` PMW3901, SPI3, bottom | **not populated on the Economic order, deferred** | `FLOW_TYPE 2` to use it instead |
| Logging | `J8` microSD, SDMMC1 4-bit | on board | `HAL_OS_FATFS_IO 1` (hwdef) |
| TLE catalogue | `U5` W25Q128, SPI3 | on board | `SPIDEV tle_flash` (hwdef) |
| USB config | `J1` USB-C + `U12` ESD, 5k1 CC | on board | — |
| Companion / telem | pads `P41`–`P46`, UART7 + 5 V | on board, **companion deferred** | `SERIAL1_PROTOCOL 2`, `SERIAL1_BAUD 921` |
| Spare UART | pads `P71`–`P74`, UART4 | on board | `SERIAL6_*` unset |
| CAN | `U11` SN65HVD230, pads `P61`–`P64` | on board | `CAN_P1_DRIVER` unset |
| 9 V VTX supply | `U18` TPS54202 → pads `PV1`/`PV2` | on board, **switchable** | `RELAY1_PIN 83`, `RELAY1_DEFAULT 0` |
| Addressable LEDs | `U17` 74LVC1G17 → pads `PL1`–`PL3` | on board | `NTF_LED_TYPES 257`, `SERVO13_FUNCTION 120` |
| Buzzer | `Q1` AO3400A + `D4` → pads `PZ1`/`PZ2` | on board | `ALARM` on PA15 (hwdef) |
| Safety switch | — | **absent** | `BRD_SAFETY_DEFLT 0` |
| Airspeed / OSD / 2nd battery | — | **absent, deliberate** | pins freed for the SoOP config |
| Reverse-polarity protection | — | **absent** | see below |

Everything in the "Parameter" column that is not marked `(hwdef)` now ships in
`firmware/NAVCORE_SoOP/defaults.parm`, which ArduPilot bakes into ROMFS. Before this
audit that file did not exist and the build said so on every run — a freshly flashed
board had no idea it had a rangefinder, a flow sensor, an ESC telemetry link or a DShot
ESC.

### Things that are true and worth knowing before you fly it

**The 9 V VTX rail is now switchable — and fails safe towards video-on.** `Q3` pulls
`BUCK9_EN` to ground when `PA7` is driven high; `R45` holds the gate down otherwise, so
the rail is enabled unless something deliberately disables it. `C73` filters the enable
node at the pin, because the nearest place a SOT-23 fits is 23 mm from `U18`.

`PA7` was chosen for a specific reason: MatekH743 uses it as `BATT2_CURRENT_SENS`, an ADC
**input**. A stock MatekH743 binary therefore cannot assert it and cannot cut your video.
The two pins that looked like better spares — `PE15` and `PB2` — turned out to be walled
into ~1 mm² pockets inside the LQFP pad ring with nowhere to put a via.
`tools/scan_spare_pins.py` measures that for every spare pin.

**Motors 1 and 2 share a DMA stream with every UART transmitter.** The generated DMA map
puts `TIM8_UP` — the DShot engine for PB0/PB1 — on DMA2 stream 3, shared with
`USART1_TX`, `USART2_TX`, `USART3_TX`, `UART4_TX`, `UART7_TX` and `UART8_TX`. Motors 3–6
on `TIM5_UP` share only with SPI2, which is unpopulated, so they are effectively
private. This is inherited from MatekH743's pin assignment, which is the entire point of
the pin-identity constraint, and MatekH743 flies fine — but it is a real asymmetry and
worth knowing if DShot telemetry ever looks jittery on motors 1–2 specifically.

**Battery current scaling is a guess until you measure it.** `BATT_AMP_PERVLT 40.0` is
the common SpeedyBee figure. The shunt and amplifier belong to the ESC, not to this
board, so nothing here can derive it. Fly it once with a clamp meter or a known load.

**Flow orientation is unverified.** `U6` is on the bottom of the board, so its X/Y axes
are not automatically the vehicle's. `FLOW_ORIENT_YAW` ships as 0. Check the sign of the
flow output on the bench before trusting position hold — a wrong sign flies the aircraft
away from where it should hold, accelerating.

**No reverse-polarity protection on VBAT.** `D1` is a TVS: it clamps transients, and it
clamps a reversed pack at −0.7 V until it dies. A reversed connector kills the board. A
P-FET in the VBAT path would fix it and would need a respin.

**Pack voltage limits — THIS BOARD IS 4S ONLY.** `D1` was an **SMBJ33A**, which starts
conducting around 37 V and clamps at **53.3 V**. The TPS54202's absolute maximum input is
**30 V** (SLVSD26 §5.1), so that part could not protect the regulators it sits in front
of: any surge large enough to make it conduct arrived at `U8` more than 20 V over its
destruct limit. It was chosen on cell-count headroom, which is not the question a TVS
answers.

`D1` is now an **SMBJ18A** (LCSC `C19077573`, same DO-214AA package): 18 V standoff clears
a full 4S pack (16.8 V), 20.0 V minimum breakdown keeps it off through regenerative
braking, and **29.2 V clamping is under the regulator's 30 V limit** — so it protects
what it is there to protect.

The cost is real: **5S and 6S are now out**. 5S full is 21 V, past the 18 V standoff. The
ESC accepts 3–6S, so the board is the limit, not the ESC. This is not fixable by picking a
different TVS — nothing that stands off 25.2 V clamps under 30 V — it needs a
higher-voltage regulator. The 10k/1k divider still saturates the 3.3 V ADC at 36.3 V, so
the ADC was never the binding constraint.

**Flash headroom is 10%.** `arducopter.bin` is 1 530 396 bytes against 1 703 936
available after the 128 KB bootloader reserve and the 256 KB storage pages. Enough, but
adding large features (scripting, OSD fonts) will need checking.

**Board ID 9001 is not registered.** It is free in ArduPilot's `board_types.txt` today
and `tools/build_firmware.sh` registers it locally so the build resolves. Request it
upstream before sharing or selling the design.

### Power delivery: was the blocker, now resolved

Every power rail was routed at 4 mil, the same width as a signal, because `route.py`
lays everything at `TRACK_W` and nothing checked it against current. That is fixed:

| rail | narrowest feed to a trace-fed pad | needs | verdict |
|---|---|---|---|
| `VBAT` | — every pad now sits on the In4.Cu pour | 1.7 A (4S) | plane carries it |
| `+5V` | ~11.1 A (1.00+1.00+0.80 mm at `J3.1`) | 3.0 A | clear |
| `+9V` | ~9.5 A at `PV1.1` | 0.6 A | clear |
| `+3V3` | ~0.60 A at `U1.50` | 0.6 A | exactly meets |
| `VBUS` | ~1.2 A at `J1.A4B9` | 0.5 A | clear |

Three things got it there. `tools/widen_net.py` grew every rail to the widest its own
surroundings allow, segment by segment — which took the rails from 0.45 A to 0.60 A and
no further, because the bottlenecks were hemmed in. `tools/extend_pour.py` then gave
`VBAT` a corridor on In4.Cu reaching the battery connector and `+5V` a patch reaching the
companion pad, since **`J2.2` sat on no plane region at all** and every amp the aircraft
draws was entering through 4 mil copper. Both connector pads are now stitched into their
plane with 0.5 mm copper.

`tools/check_electrical.py` judges this on the **feed to each pad that is not on a
plane**, not on the narrowest trace anywhere on the net. That distinction matters: after
the fix every rail still has thin segments — decoupling stubs and fanout — while the load
path runs through the plane. Capacitor and resistor pads are exempt by design; a bypass
cap carries ripple and a divider tap carries microamps, and judging a rail on those stubs
is what made a healthy net look failed.

Copper is now measured by **cut capacity** — draw a line separating a regulator from its
loads and add up every piece of that net's copper crossing it. That needs no connectivity
model, so unlike a path search it cannot quietly disagree with the board:

| rail | tightest cut | needs |
|---|---|---|
| `VBAT` | ~3.2 A | 1.7 A |
| `+5V` | ~3.2 A | 3.0 A |
| `+3V3` | ~3.4 A | 0.6 A |
| `+9V` | ~0.7 A | 0.6 A — thin, and the VTX is optional |

Getting `+5V` there took a plane corridor down the east edge: the buck sits at y≈110 and
twelve loads sit south of y=118, and only **0.7 A of copper crossed between them**.
`VBAT` needed its two plane groups bridged around the `+9V` island — the 9 V buck was on
a separate island from the battery.

**One assumption to check when ordering: 1 oz outer copper.** All of the above halves on
0.5 oz.

### The board cannot be powered over USB

`VBUS` reaches the USBLC6's reference pin and a bypass capacitor and nothing else — no
component bridges it to `+5V`, which comes only from the 5 V buck's inductor. So plugging
in USB gets you the data lines and no power.

For bench work that means **supply VBAT even to configure it**: a 4S pack through the
smoke stopper, or a current-limited bench supply at 14–16 V on `J2.2`. It is not a fault,
but it is not how most flight controllers behave, and it is easy to waste an afternoon
on. A diode-OR from `VBUS` into `+5V` would fix it and would need a respin.

### Bring-up order

1. **Flash the bootloader over SWD first — USB does nothing until you do.** A freshly
   assembled board has empty flash and will not enumerate. You need an ST-Link V2 and
   fine wires or pogo pins on `SWDIO`/`SWCLK`, with `TP20` (GND) and `TP21` (+3V3) as the
   probe's reference. Only then does the `.apj` go on over USB.
2. Confirm on USB: two IMUs, one barometer, the microSD mounting.
3. `RNGFND1` should now report a distance — if it does not, the XSHUT fix did not take.
4. Check the ESC telemetry link reports RPM before trusting the harmonic notch.
5. Calibrate `BATT_AMP_PERVLT` against a known load.
6. Verify flow sign on the bench, then set `FLOW_ORIENT_YAW`.
7. Props off, motor test each output, confirm the mapping before arming.


### What running it in the simulator changed — 2026-08-28

Everything above was verified by *building* firmware. That proves the hwdef compiles; it
does not prove the aircraft arms. `sitl/run_scenarios.sh` flies the board's own
`defaults.parm` against simulated truth, and it found three ways the shipped parameter
set would have stopped a freshly built aircraft from arming.

**1. `VISO_TYPE 1` needs a companion that is actually streaming.** Without one:
`PreArm: VisOdom: not healthy`. The board would not have armed until the Pi was running.

**2. `EK3_SRCn_POSXY 6` needs `VISO_TYPE 1` — and the failure blocks GPS flight too.**
(Since superseded: ExternalNav was dropped entirely — see below — but the *rule* it
taught is what now governs every optional parameter on this board.)
`PreArm: AHRS: EK3 sources require VisualOdom`. ArduPilot validates **every configured
source set** at arm time, not only the active one, so a GNSS-denied source set that
referenced ExternalNav made the aircraft unarmable *on SRC1, under GPS*. This is the one
that would have cost a day in a field.

**3. A configured-but-absent rangefinder blocks arming.** `U7` is not populated on the
Economic assembly order, so `RNGFND2_TYPE 16` alone would have grounded the board.

The rule now applied throughout `defaults.parm`: **nothing that is not soldered to the
board ships enabled.** A bare board arms, flies on GPS, and every optional capability is
one documented parameter away. `docs/BUILD.md` T3 lists the opt-ins, and
`VISO_TYPE` / `EK3_SRC3_POSXY` are flagged everywhere as a pair that moves together.

**4. And then the architecture itself was wrong.** With the parameter set fixed, the
ExternalNav scenario still misbehaved. The cause is a constant:
`AP_VISUALODOM_TIMEOUT_MS` is **300 ms**, so visual odometry is healthy only above about
3.3 Hz. An Iridium Doppler solution needs an observation arc across a satellite pass and
arrives at roughly **1 Hz** — it can never satisfy that. `GPS_TIMEOUT_MS` is **4000 ms**,
more than 13× the tolerance.

So the SoOP fix now enters as a **second GPS** (`GPS2_TYPE 14`, `GPS_INPUT`), not as
ExternalNav. That is simpler in every direction — no EKF origin to track on the Pi, no NED
conversion, absolute position so RTL works — and `GPS_AUTO_SWITCH 1` makes failover
**automatic** when the real receiver is denied, with no pilot action. `sitl/` keeps
`extnav_1hz` as a recorded measurement, so the decision stays visible.

The EKF source ladder as shipped:

| Set | Position | Velocity | Armable bare? |
|---|---|---|---|
| SRC1 | GPS — real receiver **or** SoOP | GPS | yes — normal flight *and* the GNSS-denied mode |
| SRC2 | none | optical flow | yes — a hold, drifts in XY |
| SRC3 | none | optical flow | yes — spare position on the switch |

Position needs no source switching at all now: SRC1 covers both GNSS sources, and the
ladder is about losing GNSS entirely.


### Measured in the simulator — 2026-08-28

The whole GNSS-denied chain flown against simulator truth, with a Doppler model of
σ 20 m white noise **plus** a correlated random-walk bias capped at ±40 m per axis, 2 s
latency, and outages. *This run described that model as "deliberately pessimistic". It
was not — σ 20 m was an `[A]` assumption, and the published Iridium NEXT figure is
**180 m**. The results below stand as a record of what was flown that day; see the
2026-09-05 re-measurement further down for what the model says now.*

| Scenario | Result |
|---|---|
| GPS baseline | mean 0.05 m, p95 0.17 m — the floor |
| **SoOP after GPS denial, 70 s** | **mean 20 m, p95 38 m** |
| **SoOP after GPS denial, 300 s** | **mean 31 m, p95 56 m — bounded, no drift** |
| SoOP with repeated dropouts | mean 20 m, p95 40 m through 9 outages — recovers cleanly |
| SoOP published at the raw 1 Hz | **will not arm** — `GPS 2: Bad fix` |
| ExternalNav at 1 Hz | arms *intermittently*; ends up dead reckoning on flow |
| Flow + baro only, no position | p95 ~9 m over 300 s, but **unbounded** — it drifts |
| Measurement canary (100 m injected offset) | reported 106 m — the rig measures truth |

**The error is bounded and roughly equals the receiver's own accuracy.** That is the
answer to "will it work": the flight controller is not adding to the error, so the
remaining question is the receiver, not ArduPilot.

> **Superseded as an expectation, kept as a measurement (2026-09-05).** This table was
> flown at σ 20 m; the model now ships at the published **σ 180 m**, and 8 repeat runs at
> that sigma put denial-phase p95 at **279–476 m** with all runs recovered by the
> dead-reckon applet (table in `sitl/README.md`). "Bounded" still holds; "≈ 30 m" does
> not. Plan around the 180 m numbers until the receiver is measured — or until the
> differential-SoOP path (docs/BENCHMARK.md) closes the gap.

#### Where the error actually comes from

√(20² + 30²) ≈ 36 m, which matches the observed ~31 m. **The random-walk bias contributes
more than the white noise**, and unlike noise it does not average out. So the highest-value
work on the companion is **estimating and removing that bias against the live GPS before
denial** — which is also what the 50 m consistency check below requires, so one piece of
work serves both.

Tested and found NOT to help: sending velocity in `GPS_INPUT` (30.7 m mean with, 30.9 m
without, over four seeds). Send it because it is what a Doppler receiver measures, not for
accuracy.

#### Hard requirements on the companion

1. **Publish at 5 Hz**, interpolating up from the ~1 Hz Doppler solution, with `h_acc`
   growing between true fixes. 1 Hz and 2 Hz will not arm.
2. **Agree with the live GPS on the ground to within 50 m.** `AP_Arming.cpp:741` enforces
   it (`AP_GPS::all_consistent`, threshold hardcoded in `AP_GPS.cpp:1520`) and the
   threshold is NOT configurable. At the σ 20 m the harness once used, a breach was a
   ~2.5σ event - an intermittent arming refusal. At the σ 180 m the model now ships
   (`DopplerErrorModel.SIGMA_IRIDIUM_NO_ELEV`), **roughly half of ground arming attempts
   breach it**: measured 2026-09-05, `soop_dropout` refused to arm with
   `Arm: GPS positions differ by 129.2m` / `211.8m`. The companion answer is not to
   disable the GPS arming check (that also disables the real receiver's Bad-fix check):
   while GPS1 is healthy the aircraft is not GNSS-denied, so the companion should publish
   the live GPS position on instance 2 and switch to the Doppler solution only when GPS
   degrades. That keeps arming consistent AND is what the sensor is for.
3. **Start streaming before arming.** Anything ArduPilot judges healthy by data arrival
   must be arriving first.
4. **`gps_id` must be 1**, matching `GPS2_TYPE`. `AP_GPS_MAV.cpp:51` silently discards
   messages whose `gps_id` does not match the instance.

---
