# NAVCORE-SoOP — sensors, expansion and the navigation chain

Every pad and test point, what can be added, how the altitude source was chosen, the
MAVLink contract a companion must satisfy, and the Lua applets this board can run.
Merged from SENSORS.md, SENSORS.md, SENSORS.md and SENSORS.md.

## What you can hang off this board


Every pad and test point, what it is, and what it can be repurposed for. Written for the
question "can I add X later" — including the deployable-mechanism kind of project, where
the answer turns out to be yes.

> **Deferred configuration (2026-09-02).** The Radxa companion and the optical-flow
> camera are both DEFERRED; the aircraft navigates on its real GPS outdoors and on ToF
> indoors. Everything below about the companion stays true for a revived companion, and
> the SERIAL1 link (`P41`–`P46`) remains provisioned. The one architecture that changed
> is the ToF ring's reader: with the companion gone, an **MCU sensor hub** (RP2040 or
> Nano, ~£4) drives the mux and publishes OBSTACLE_DISTANCE — see "How to wire it".
>
> **RETRACTED 2026-09-04 — a "geometric reason to keep it deferred" stated here was not
> founded.** It claimed the top plate is 50 mm wide and therefore cannot hold the Radxa
> beside the battery. **That 50 mm was a placeholder, not a measurement.** Only the *FC*
> plate had been parsed from the frame DXF — 48.50 × 106.59 mm, `design.FRAME_CAD` —
> and `cad/drone.scad` set `bottom_plate_w = 50` for *all three* plates, chosen solely
> to exceed the board's 46.1 mm. `FRAME["size"]` is tagged
> `[A] plate outline 200x230 mm - overall footprint only, not load-bearing on any check`.
>
> The 1165 mm³ overlap `check_cad_fit.py` measured was therefore real *against the model*
> and says nothing about the real frame, whose footprint is 200 × 230 mm.
>
> **CLOSED 2026-09-05 — the model now draws the real plates.** `design.PLATES` had held
> all three outlines, flattened from the manufacturer DXF, since 2026-09-04 and nothing
> used them: **fc 48.50 × 106.59, top 42.50 × 160.26, bottom 48.50 × 107.62 mm.**
> `cad/drone.scad`'s `plate()` took a single `w` and drew a *square*, so every
> `frame × …` clearance the checker reported was measured against an airframe that does
> not exist. It now takes `(w, l, t)` and each plate is drawn at its own size.
>
> Two figures moved once it did: **`frame × props` 19.00 → 11.56 mm** and
> **`frame × rec_cam` 36.01 → 11.50 mm**. Both still pass. The arm mattered more than the
> plates here — `arm_w` was 12 mm and commented *"cosmetic … no check uses it"*, which was
> wrong twice: `arm()` is inside `frame()`, which **is** exported and measured, and the
> DXF gives **31.08 mm** across. It now uses the bounding-box width, which over-states a
> tapered arm and so can only under-report clearance.
>
> **The companion stays deferred for the reasons at the top of this note — not for a
> mounting reason, which is currently unknown either way.** `show_pi` is `false` and
> `"pi"` is out of `check_cad_fit.py`'s `PARTS` because the model has no founded position
> for it, not because none exists.
>
> **SETTLED 2026-09-04 by parsing the DXF properly.** An intermediate note here claimed
> the geometry was unreachable because the file is full of ACIS solids. That was wrong
> twice over: `ezdxf.acis` parses ACIS, and more simply **the plates were 2D polylines all
> along** — the first parser could not see them because it compared block-local
> coordinates against top-level ones. Flattening INSERT transforms fixed it, and the
> method is trusted because it reproduces the already-known FC plate to two decimals.
>
> | plate | size | holes |
> |---|---|---|
> | FC / mid | 48.50 × 106.59 mm | both stack patterns + the 10 mm centre hole |
> | **top** | **42.50 × 160.26 mm** | 8 × M3 only, at x = ±14.60 and ±11.00 |
> | bottom | 48.50 × 107.62 mm | 29 holes incl. 4.3 / 6.0 / 2.0 / 2.2 mm accessory sizes |
>
> **The companion fits the top plate dimensionally** — a Radxa Zero 3W is 65 × 30 mm on a
> 42.50 mm-wide plate, 6.25 mm clear each side. So the original claim was withdrawn
> correctly: the *reasoning* (a 50 mm placeholder) was invalid. What actually blocks it is
> the **battery**, which is a placement conflict rather than a size one.
>
> And a consequence in one axis: **the top plate is 42.50 mm wide while the battery is
> 47 mm**, so the pack overhangs it by 2.25 mm each side. There is no "beside the battery"
> *across* the plate.
>
> **Corrected 2026-09-04 — that measured the wrong axis.** An earlier version of this note
> concluded from the width alone that an upward ToF "goes on the strap, on a mast, or not
> at all". The free space is in **length**: the battery is 138 mm on a **160.26 mm** plate,
> leaving **22.26 mm**. See the mounting note below — it fits, fore or aft.

### Pad labelling: 14 anchors printed, the rest on the pad map

Every pad reference originally sat on **`F.Fab`**, which is not printed. The board would
have arrived with 38 identical unlabelled gold squares.

`tools/silk_labels.py` fixes as much of this as the board has room for. It tries eight
directions at four distances per label, then **measures the real rendered text extents**
and withdraws any that still collide — because an unreadable label is worse than a blank
pad, since it will be trusted. At the board's own 0.80 mm minimum printable height, on
1.5 mm pads at a 2.84 mm pitch, **14 fit cleanly**:

`P41` · `P54` · `P62` · `P72` · `PL1` · `PL2` · `PL3` · `PV1` · `PV2` · `PZ1` · `TP3` ·
`TP4` · `TP20` · `TP21`

That is not everything, but it is the useful subset: **one anchor per loom group** — `P41`
for the companion, `P54` for RC, `P62` for CAN, `P72` for the spare UART — plus both spare
servo outputs and both SWD reference pads. Find the anchor, count from it.

DRC is unaffected: 0 errors, and `silk_overlap` actually fell from 23 to 20 because the
tool also repositioned six labels that were already on silkscreen into clearer spots.

**Print `docs/img/padmap.svg`** for the rest — a top-view map with every pad's *function*
rather than just its designator. Keep it with the board when wiring.

Any future respin should carry fewer, better-grouped pads rather than smaller text.

### The power pads are interchangeable — this makes the layout make sense

The pad groups look alarmingly scattered: CAN spans 26.8 mm, the spare UART 28.9 mm, the
VTX pair 30.9 mm. Measured, that turns out not to matter, because **only the power and
ground pads are displaced**:

| group | signal pair | spacing |
|---|---|---|
| companion | `P42` TX / `P43` RX | 2.84 mm |
| RC | `P52` TX / `P53` IN | 2.84 mm |
| CAN | `P62` H / `P63` L | 4.59 mm |
| spare UART | `P72` TX / `P73` RX | 2.84 mm |

**Every signal pair is adjacent.** And the power pads are all on the same nets, so any one
substitutes for any other:

- **+5 V**: `P41`, `P51`, `P61`, `P71`, `PL2`, `PZ1`
- **GND**: `P46`, `P54`, `P64`, `P74`, `PL3`, `PV2`, `TP20`

So the rule is: **take the signal pair from its own group, take +5 V and GND from
whichever of those pads is physically nearest.** The scatter is a convenience — power is
available all over the board — rather than a defect. The same applies to `PV2`: the VTX
ground is 31 mm from `PV1`, so use a closer GND pad instead.

### Servo / PWM outputs — you have two spare

| Output | MCU pin | Where | Notes |
|---|---|---|---|
| M1–M4 | PB0, PB1, PA0, PA1 | `J2.3`–`J2.6` | the motors, DShot600 |
| **PWM5** | PA2 | **`TP3`** | **free** — `SERVO5_FUNCTION` |
| **PWM6** | PA3 | **`TP4`** | **free** — `SERVO6_FUNCTION` |
| PWM7–PWM12 | PD12–PD15, PE5, PE6 | **nowhere** | in the hwdef, not routed to any pad |
| PWM13 | PA8 | `PL1` via `U17` | WS2812 strip, 5 V buffered |

**Two free PWM channels at `TP3` and `TP4`** — enough for a gimbal, a dropper, a parachute,
a deployable arm. Set `SERVO5_FUNCTION` / `SERVO6_FUNCTION` (e.g. 51–58 for RC passthrough,
so an RC channel drives it directly).

**This is now asserted, not just written down.** `tools/check_payload.py` verifies against
`defaults.parm` and `hwdef.dat` that these channels really are unclaimed, and `preflight.py`
gates it. The failure it exists to catch is the ordinary one: something later needs an
actuator channel, takes the last free one, and this paragraph goes on saying the board is
extensible. It also states which serial links are reachable. **`SERIAL4` (USART3) is the only one
that is not** — `PD8`/`PD9` stop at the MCU with no pad, real to the firmware and
unreachable with a soldering iron.

**`SERIAL6` (UART4) IS routed**, to `P71`–`P74`. `tools/design.py` claimed otherwise in
three places until 2026-09-04, and that error also supplied the stated reason for
choosing the I²C TFS20-L variant. This file, `docs/VERIFICATION.md` and `docs/PINMAP.md`
all had it right; `design.py` was the outlier. Corrected.

**`SERIAL6` is the general-purpose expansion UART — settled 2026-09-04, and unclaimed.**

This was ambiguous for a long time: the pads are named `RF_*` and this file called them
"earmarked for the SoOP receiver", while `docs/PINMAP.md` labels the same `PB8`/`PB9` a
*rangefinder* port. Writing out `docs/MODULES.md` dissolved it — **neither claimant wants
the port**:

- the **SoOP tuner is analogue**. I/Q into `PC4`/`PA4`, RSSI on `PC5`, PPS on `PE10`,
  landing on `TP9`/`TP10`/`TP11`/`P44`. It needs no UART. The `RF_*` names are a fossil of
  an earlier design in which the receiver was a smart serial module.
- the **rangefinder is the I²C TFS20-L**, which lands on `J3.4`/`J3.5` — as the paragraph
  directly above this one records.

So `SERIAL6` is free, and "expansion" is the honest label. The strongest future claimants
are a UART optical-flow module or a serial rangefinder variant. The `RF_*` **net names are
deliberately left alone**: they appear nowhere on silkscreen, so the fossil is invisible on
the physical board, and renaming nets days before a fabrication order buys nothing.

Budget for a payload: **860 g at 40% hover throttle** (1360 g at 50%), and the 5 V rail has
**653 mA** of headroom — which a stalled hobby servo eats on its own, so give a high-current
actuator its own BEC. (Both figures moved 2026-09-05: the mass budget is now derived from
`design.MASS_ITEMS` rather than hand-copied, and that list had been carrying a superseded
25 g ToF ring while budgeting nothing for the 42 g LD06 that replaced it. The 413 mA was
frozen before the WS2812 row was corrected from a 300 mA guess to a 60 mA strobe budget.)

Wiring a servo: **signal** from `TP3`/`TP4`, **+5 V** from `P71`/`P61`/`P51`/`PL2`/`P41`,
**GND** from `P74`/`P64`/`P54`/`PL3`/`P46`. The signal is 3.3 V logic; every hobby servo
and ESC accepts that as a valid PWM high. A high-current servo should take its 5 V from
the ESC BEC rather than this board — `docs/HARDWARE.md` has the 5 V budget
(**653 mA** spare once everything in `LOADS_5V` is fitted — see `design.RAIL_5V`; a companion needs its own BEC).

`PWM7`–`PWM12` exist in silicon and in the hwdef but reach no pad. Six more channels are a
wiring change on a future respin, not a silicon limit.

### Buses

| Bus | Where | Free? |
|---|---|---|
| **CAN** | `P61` 5 V, `P62` CANH, `P63` CANL, `P64` GND | **yes** — the best expansion path |
| UART (`SERIAL6`) | `P71`–`P74`, UART4 | **yes — free and unclaimed.** `RF_*` is a vestigial net name, not an earmark |
| UART (`SERIAL2`) | `TP5` TX, `TP6` RX, USART1 | yes — telem2 |
| UART (`SERIAL1`) | `P41`–`P46`, UART7 | the companion computer |
| RC (`SERIAL7`) | `P51`–`P54`, USART6 | the receiver |
| **I²C1** | **`J3` only** (GPS connector) | ⚠ see below |

**CAN is the right way to add things.** DroneCAN gives you servos, sensors, GPS, ESCs,
lights and power monitors on four wires, addressed rather than wired point to point, and
`U11` (SN65HVD230) is already fitted with the pads broken out. Set `CAN_P1_DRIVER 1`.

#### The one real gap: no spare I²C pads

`I2C1` reaches only `J3`, the GPS connector. Adding an I²C device — a second compass, a
VL53L5CX multizone sensor, an ambient sensor — means splicing into the GPS cable or making
a Y-lead. It works (I²C is a bus, and the TFS20-L at 0x10 is exactly this case), but it is
the least tidy expansion on the board.

If you want I²C properly broken out, that is the strongest candidate for a new pad group on any future respin,
alongside `PWM7`–`PWM12`.

### Test points

| TP | Signal | For |
|---|---|---|
| `TP1` | SWDIO | **SWD debug** |
| `TP2` | SWCLK | SWD debug |
| `TP20` | GND | SWD probe ground |
| `TP21` | +3V3 | SWD reference / low-current 3.3 V tap |
| `TP3` | PWM5 | spare servo output |
| `TP4` | PWM6 | spare servo output |
| `TP5` / `TP6` | USART1 TX / RX | spare UART |
| `TP7` | WS2812 (pre-buffer) | LED signal before the level shifter |
| `TP8` | BUZZER | buzzer gate drive |
| `TP9` | `SOOP_I_ADC` | **the L-band receiver I channel** |
| `TP10` | `SOOP_Q_ADC` | the L-band receiver Q channel |
| `TP11` | `SOOP_RSSI` | receiver signal strength |

`TP9`–`TP11` are the interface to the off-board RF front end — the reason the board exists.
They are ADC inputs, so an external receiver's baseband I/Q lands there directly.

### GPIO you can switch

| GPIO | Pin | Currently | Repurpose |
|---|---|---|---|
| 83 | PA7 | `RELAY1`, nominally the VTX 9 V enable. That block is **DNP**, so the function is dormant — but `VTX_EN` reaches only `U1`, `Q3` and `R45` and **no pad**, so nothing external can be wired to it | free as a *firmware* GPIO only; exposing it needs a respin |
| 81 | PD10 | `VL53L1X_INT` | free if no `U7` fitted |
| 82 | PD11 | `VL53L1X_XSHUT` | free if no `U7` fitted |

### Power available to add-ons

| Rail | Pads | Headroom |
|---|---|---|
| +5 V | `P41`, `P51`, `P61`, `P71`, `PL2`, `PZ1` | **653 mA** spare — L2's 1.6 A Irms less the 0.947 A fitted load |
| +9 V | `PV1` | **NOT POPULATED.** `BUCK9_PH` is unroutable (`U18` on F.Cu, `L5`/`C68` on B.Cu), so the whole block is DNP — `design.POPULATE_VTX = False`. `PV1` is an open net. A VTX runs off +5 V instead; see `docs/MODULES.md` |
| +3V3 | `TP21` | probe point — **not** a power feed; use an inline LDO |

### Worked example: a deployable mechanism

Servo on `TP3`, 5 V and GND from `P71`/`P74`:

```
SERVO5_FUNCTION 56     # RC passthrough from channel 6
RC6_OPTION 0           # leave the channel raw
```

Or drive it from a mission command with `SERVO5_FUNCTION 1` (RCPassThru) / a scripting
binding. `SERVO5_MIN` / `_MAX` / `_TRIM` set the travel. No board change needed.

### Obstacle avoidance: don't fit five ToF sensors

Four sensors facing sideways and one up is the obvious way to do avoidance, and on this
aircraft it is the wrong one. Three reasons, in order of how decisive they are.

#### 1. The range does not buy useful warning at cruise

A VL53L1X sees 3.6 m; the VL53L5CX sees 4.0 m. Ideal braking distance is `v²/2a`, so the
fastest you can close on an obstacle and still stop is:

| sensor | range | 0.5 g braking | 1.0 g braking |
|---|---|---|---|
| VL53L1X | 3.6 m | 5.9 m/s | 8.4 m/s |
| VL53L5CX | 4.0 m | 6.3 m/s | 8.9 m/s |
| LD06 | 12 m | 12.1 m/s | 17.2 m/s |

Those are *theoretical minima* — instantaneous detection, perfect braking, no filter delay
and no attitude change. Halve them for reality. A 4 m sensor protects you up to roughly
**3–4 m/s**, and a 7" long-range quad cruises at 15–20 m/s. At 50 m altitude there is also
very little to hit.

#### 2. Five of them will not share the I²C bus

Every VL53L1X powers up at **0x29**, and five of them on one bus is a collision.

The reason is not the one this document used to give. It claimed "ArduPilot's driver has
no address-change support", and the source says otherwise:
`AP_RangeFinder_VL53L1X.cpp:89` opens `reset()` with

```cpp
if (dev->get_bus_id()!=0x29) {
    // if sensor is on a different port than the default do not reset sensor otherwise
    // we will lose the addess. we assume it is already confirgured.
    return true;
}
```

— it *deliberately* accommodates a sensor at a non-default address, and `RNGFNDn_ADDR`
exists, documented as "to allow for multiple sensors on different addresses". ArduPilot
will happily run several VL53L1X as separate `RNGFNDn` instances.

What ArduPilot does **not** do is *assign* those addresses. Nothing in the driver performs
the XSHUT sequence — hold all but one in reset, program the odd one out, repeat — and the
VL53L1X forgets its address on every power cycle. So the sensors must arrive already
addressed, by an external MCU or by address-strapped breakouts, and the practical
conclusion below is unchanged: use a multiplexer, or give the job to the companion.

The distinction matters because a wrong *reason* in a design document is how the next
decision goes wrong. "The driver cannot do it" closes the door on a native `PRX_TYPE 4`
ring; "the driver can, but something else must set the addresses" tells you exactly what
hardware would open it.

`I2C1` is also the board's only exposed I²C bus, and it already carries the GPS, the
compass and possibly the TFS20-L.

#### 3. One sensor does the job better

**LDRobot LD06** — 360° scanning lidar, **12 m**, 4500 samples/s, 30 klux sunlight rating,
IPX4, about £35. ArduPilot supports it natively:

```
SERIAL2_PROTOCOL 11     # Lidar360
SERIAL2_BAUD 230
PRX1_TYPE 16            # LD06
PRX1_ORIENT 1           # 0 = top-mounted, 1 = upside-down on the bottom (this airframe)
BRD_SER2_RTSCTS 0       # LD06 has no flow control
```

**Corrected 2026-09-04 — this block said `SERIAL6` and `P72`.** The lidar is earmarked for
**`SERIAL2` (USART1)** in `design.py`, and `SERIAL6` is the unclaimed expansion UART. The
signal pad was wrong: `P72` is `UART4_TX`, which is an *output*. The lidar's TX must reach
the flight controller's **RX**.

Only the lidar's **TX** pin is used (its PWM motor input is left unconnected and it spins at
a default rate — ArduPilot documents this), so it is three wires:

| LD06 wire | goes to | net |
|---|---|---|
| TX | **`TP6`** | `USART1_RX` — SERIAL2's receive |
| 5 V | `P71` | `+5V` |
| GND | `P74` | `GND` |

Taking 5 V and GND from the `P71`/`P74` pads does **not** claim `SERIAL6` — only its power
pins are borrowed, and `P72`/`P73` stay free.

One part, one connector, no address conflicts, three times the range of five ToF sensors
combined, and full 360° coverage instead of five cones with gaps between them.

**`PRX1_ORIENT 1`, not 0.** ArduPilot's guidance is 0 for top-mounted and 1 for
upside-down underneath, and this airframe mounts it in the belly — a top mount is blocked by
the battery. Arrow **pointing forward**.

#### Whether to buy it at all — read this before the mounting analysis

**`docs/BUYING.md` lists the LD06 under "Do not buy yet."** Its price was corrected to
**~$99–131**, not the ~£15–35 that earlier notes (including `design.py`'s own source line)
carried, and at 50 g fitted it protects to about **5 m/s on an aircraft that cruises at
15–20 m/s**. It earns its place only for deliberate slow indoor work.

Everything below settles **where it goes if you buy it** — the mount is now fully verified,
and that work stands. But the mount being solved is not an argument for buying it. Those are
separate questions and this file previously ran them together.

#### Where it physically goes — settled 2026-09-04

The LD06 had no viable position for a long time, and the reason was real: at prop height the
arms and props block most of the scan, on the top plate it is 38.59 mm wide against 22.26 mm
of free plate, and in the belly it *was* **33.30 mm tall against 28.5 mm of depth** — short
by 4.80 mm at the inherited 25 mm skid drop.

**The belly is the answer once the skids are set deliberately.** They are a *printed* part,
so their drop is a free parameter, and it had simply been left at an inherited 25 mm:

| skid drop | belly depth | margin over the 33.30 mm lidar | |
|---|---|---|---|
| 25 mm (was) | 28.5 mm | **−4.80 mm** | does not fit |
| 30 mm | 33.5 mm | +0.20 mm | not a clearance |
| 35 mm | 38.5 mm | +5.20 mm | tried first — **rejected**, see below |
| **40 mm (now)** | **43.5 mm** | **+10.20 mm** | ✅ |

**Why 40 and not 35.** 35 mm was chosen first, to avoid raising the CG. That trade was
asserted rather than computed, and computing it reversed the decision: static tip-over goes
**71.5° → 69.9°**, a 1.6° change, with both values nowhere near the ~30° where a quad
becomes tippy. The ground clearance beneath the lidar meanwhile **doubles, 5.20 → 10.20 mm**.
TPU landing gear deflects several millimetres under a firm arrival, so 5.20 mm sits inside
the range a single hard landing can consume — and the part taking that hit would be the
£19 lidar, not the printed skid.

`design.SKID['drop']` is now 35 mm and `BELLY_SENSOR['depth_available_mm']` is **derived**
from it rather than hardcoded — it had been a literal 28.5 whose own source line claimed it
was computed.

**The skid legs cut the scan plane, and that is what `PRX1_IGN_*` is for.** With the lidar at
the centre of the belly the legs are 160 mm away (320 mm wheelbase), so each subtends very
little:

| leg width | per leg | 4 legs | with 4° margin each |
|---|---|---|---|
| 10 mm printed | 3.58° | 14.3° (**4.0%**) | `PRX1_IGN_WID* 8` → 30° total |
| 31.08 mm (full arm width) | 11.09° | 44.4° (12.3%) | `PRX1_IGN_WID* 15` → 60° total |

ArduPilot allows **6** exclusion sectors (`PRX1_IGN_ANG1..6` / `PRX1_IGN_WID1..6`) and this
needs **4**. Measure the real blocked angles on the bench with the lidar running — do not
set these from the table above, which is geometry, not observation.

**Two mass notes.** The lidar is 42 g on a 1123 g AUW (3.7%), and it hangs *below* the
plates — vertical CG is currently **+14.9 mm above the rotor plane** with 61% of mass high,
so a belly load pulls it the way it should go. Against that, taller legs add tip-over moment
on an uneven landing. And note `check_mechanical`'s warning: the frame's stock "skate" is a
**6 mm flat wear plate, not landing gear** — 35 mm of clearance means printing real legs.

Cost against the alternative: five VL53L5CX at £3.87 plus a multiplexer plus five looms is
about £22 in parts and a great deal of wiring, for worse coverage and a third of the range.

**Weight is the honest catch**: the LD06 is around 50 g against ~1 g for a bare ToF die.
On a 7" that is real but carryable.

#### Side-facing ToF rings are a real product — and the reason they work is not obvious

`PRX1_TYPE 3` (TeraRangerTower) and `PRX1_TYPE 6` (TeraRangerTowerEvo) are natively
supported by ArduPilot, and the **Terabee TeraRanger Tower Evo** is exactly a ring of ToF
sensors for drone obstacle avoidance. So the idea is sound and it is not exotic.

What makes it work is not the arrangement, it is the **sensors**:

| | TeraRanger Tower Evo | a ring of VL53L1X |
|---|---|---|
| range | **60 m** | 3.6 m |
| sensors | 8 | 6–14 |
| FoV each | ~2° | 27° |
| size | 120 mm ⌀ × 42 mm | small |
| price | **~£290** | ~£30 |
| status | **discontinued May 2024** | available |

It uses **60 m** sensors. That is the entire difference, and it is why the cheap version
does not inherit the result: at 3.6 m the ring protects to roughly 3 m/s however many
sensors you fit.

#### The gap problem, which applies to *both* rings

A ring samples **lines**, not a surface. With a 2° beam every 45°:

| distance | beam width | gap between beams |
|---|---|---|
| 2 m | 0.07 m | 1.6 m |
| 5 m | 0.17 m | 4.0 m |
| 10 m | 0.35 m | 7.9 m |
| 20 m | 0.70 m | 15.9 m |

A **wall** is continuous, so a pencil beam always finds it — which is why Terabee's demos
are indoor rooms and dense vegetation. A **branch, wire, aerial or pole** at 10 m sits in a
7.9 m gap and is completely invisible. Widening the beam (VL53L1X at 27°) closes the gaps
but collapses the range, and there is no cheap sensor that gives both.

Six VL53L1X get the worst of it: 27° each covers 162° of 360°, so **55 % of the horizon is
blind** *and* the range is 3.6 m.

#### What actually removes the gaps: scanning, or a camera

| approach | gaps | range | cost |
|---|---|---|---|
| 6 × VL53L1X ring | 55 % of horizon blind | 3.6 m | ~£30 |
| TeraRanger Tower Evo | samples 8 lines | 60 m | ~£290, discontinued |
| **LD06 scanning lidar** | **none** — continuous 360° sweep | 12 m | ~£80–105 |
| DJI Mavic 3 | none — 8 vision sensors | ~200 m | — |
| Skydio 2 | none — 6 cameras + Jetson TX2 | ~30 m | — |

The **LD06 sweeps** a beam through 360° at 4500 samples/s — about one sample every 0.16 m
of arc at 12 m. Nothing hides between beams. That is why it is better value than a ring
costing the same, and why no commercial autonomous aircraft uses a fixed ToF ring for
primary avoidance.

#### For tight indoor flying, a ToF ring IS the right answer — and it costs about £21

Everything above argues against a ToF ring **at cruise speed outdoors**. Indoors, every
one of those arguments inverts:

| | outdoor cruise | tight indoor |
|---|---|---|
| speed | 15–20 m/s | 1–3 m/s |
| obstacles | branches, wires, poles — *thin* | walls, doorframes, furniture — *large and continuous* |
| distance needed | tens of metres | a room is 3–5 m across |
| sunlight | ruins ToF | none |

At 2 m/s you need well under a metre of stopping distance, so **4 m of range is generous**.
And because indoor obstacles are continuous surfaces, the gap problem largely evaporates —
a wall cannot hide between beams.

**Eight is the right number**, and not arbitrarily: `AP_Proximity_Boundary_3D.h` sets
`PROXIMITY_NUM_SECTORS 8`, so ArduPilot bins all proximity data into **8 sectors of 45°**
regardless. Fitting more gains nothing at the boundary; fitting six leaves a sector empty.

And on gaps, the cheap wide-cone sensor beats the £290 product:

| ring | spacing | beam | gap at 3 m |
|---|---|---|---|
| 8 × VL53L1X | 45° | **27°** | **0.95 m** |
| 6 × VL53L1X | 60° | 27° | 1.78 m |
| TeraRanger Tower Evo | 45° | 2° | **2.36 m** |

The VL53L1X's wide cone fills gaps far better than a pencil beam. It loses on range
(3.6 m against 60 m), which indoors does not matter.

#### How to wire it — the address collision has a £2 answer

All eight VL53L1X power up at **0x29**, and nothing in ArduPilot performs the XSHUT
sequence that would give them distinct addresses (the driver *accepts* a non-default
address, it just never assigns one — see above). A **TCA9548A 8-channel I²C multiplexer**
(~£2) sidesteps the whole problem — eight channels for eight sensors, no addressing.

**SUPERSEDED — a 360° lidar replaces this ring entirely.** The section below is kept as
the record of how the ring was designed and why it was abandoned, not as a plan.

A single LDROBOT lidar beats the eight-sensor ring on every axis: comparable money,
**natively supported** (`PRX1_TYPE 16`), **12 m against 3.6 m**, true 360° against ~40% of
the horizon blind between beams, one wire instead of eight sensors plus a mux plus a
hub — and, decisively, **no firmware to write**. `PRX1_TYPE 16` is a *protocol* driver:
`AP_Proximity_LD06.cpp` validates a 47-byte frame starting `0x54` with CRC8 poly `0x4D`,
the LDROBOT format shared by LD06 / LD19 / STL-19P / STL-06P / LD14P. Wiring is the
lidar's **TX pin only**, PWM motor input left unconnected — it self-spins.

**Buy on ambient light rating, not on price.** Full sun is ~100 klux:

| model | range | **light** | note |
|---|---|---|---|
| **LD06** | 12 m | **25 klux** | **discontinued; avoid for outdoor use** |
| LD19 / STL-19P | 12 m | **60 klux** | same protocol |
| STL-06P | 12 m | **60 klux** | LDROBOT's official LD06 replacement |
| **LD14P** | 8 m | **80 klux** | best light rating; 115200 baud, not 230400 |
| Camsense X1 / LDS02RR / Delta-2A | 6–8 m | 1–50 klux | **no ArduPilot driver** |

Outdoors the failure mode matters more than the range. An unresolved ArduPilot thread
reports an LD06 showing **phantom obstacles in an open field in sunlight and correct
readings at night**, traced to corrupted frames with CRC mismatches. A lidar that
hallucinates makes `AC_Avoid` brake for nothing in flight — **worse than no sensor**.
Useful outdoor speed at 1 g braking plus 100 ms scan latency: **12 m → ~10 m/s**,
**8 m → ~8 m/s**.

The lidar takes `SERIAL2` (USART1) at `TP5`/`TP6`, the only free *routed* UART — earmarked
in `design.PAYLOAD` so a future payload cannot silently claim it too.

<details>
<summary>Historical: how the eight-sensor ring was going to be wired</summary>

ArduPilot does not drive the mux, and the companion is deferred — so a small **MCU
sensor hub reads it**: an RP2040 or Arduino Nano (~£4) driving the TCA9548A, polling the
sensors, and emitting MAVLink OBSTACLE_DISTANCE on a spare UART. This is the hub, not the
flight controller, that would otherwise have to assign addresses; the mature Pololu and
Adafruit VL53L1X libraries plus a trivial TCA9548A driver are all the firmware it needs:

```
8 × VL53L1X ──I²C──▶ TCA9548A ──I²C──▶ MCU sensor hub (RP2040 / Nano)
                                            │
                                    OBSTACLE_DISTANCE
                                            │
                              spare UART (P71–P74 if SERIAL6 is free), MAVLink
                                            │
                                     STM32H743  PRX1_TYPE 2  ──▶ AC_Avoid
```

Why a hub and not the alternatives: the FC side (`PRX1_TYPE 2`) is already proven in this
project — proximity_ring arms and flies at p95 0.08 m; the Lua alternative
(`PRX1_TYPE 15`, `handle_script_distance_msg`) would mean writing ST's ~100-register
VL53L1X init in Lua with no reference driver, on the MCU running the 400 Hz loop; and a
360° lidar (`PRX1_TYPE 16`) is £75.99. The hub also keeps ten I²C devices off `I2C1`,
which is the board's only exposed I²C bus and already carries the GPS and compass.

Two constraints to design against, not discover later:

- **Mux channel discipline.** With a channel open, its 0x29 sensor is visible on the
  main bus and collides with the upward `RNGFND3` module. The hub must close all channels
  when idle.
- **Ten rangefinder slots, zero spare.** `RANGEFINDER_MAX_INSTANCES` is 10 — 8 ring +
  1 up + 1 down fills it exactly. The MAVLink hub consumes **no** slots, which is itself
  an argument for it.

The hub is **not flight-critical**: proximity only enables avoidance. If it stops
publishing, set `PRX1_TYPE 0` and fly without it — do not let it become a position source.

`OBSTACLE_DISTANCE` (#330) carries `distances[72]` in cm plus an `increment` in degrees, so
the Pi sends **8 values with `increment = 45`** — a direct match to ArduPilot's own sector
model. `AP_Proximity_MAV.cpp:120` handles it.

**Proven, and with one real gotcha.** A direct test had **685 messages accepted with no
prearm complaint**, so the path works. But getting there needed firmware instrumentation,
because the failure mode is silent:

```
PRXDBG init inst=0 type=2 driver=yes num=1
PRXDBG AP_Proximity::handle_msg id=330 num_instances=0   <-- dropped
```

**Messages that arrive before `AP_Proximity::init()` has run are discarded without a
word** — the frontend loops over `num_instances`, which is still 0. The symptom is
`PreArm: PRX1: No Data` no matter how correct your messages are.

Two consequences for the hub:

- **Keep publishing.** Do not treat early silence as a failure and back off; just keep
  sending and it starts working.
- **`PRX1_TYPE` is `@RebootRequired`**, so it must be set before boot, not pushed at
  runtime like an ordinary parameter.

Also worth knowing: report a clear sector as a distance **below** `max_distance`, not equal
to it. A reading exactly at the maximum reads as an invalid sample rather than a clear one.

```
PRX1_TYPE 2         # MAVLink - obstacle data from the companion
AVOID_ENABLE 2      # bit 1 = UseProximitySensor
AVOID_BEHAVE 1      # 1 = Stop (0 = Slide) - Stop is right for tight spaces
```

#### Cost

| | qty | each | total |
|---|---|---|---|
| VL53L1X module (GY-53-L1X or CJMCU-531) | 8 | ~£2.50 | £20 |
| TCA9548A 8-channel I²C mux | 1 | ~£1.60 | £1.60 |
| **total** | | | **~£21** |

Against **~£90** for an LD06 and **~£290** for the discontinued TeraRanger. For your stated
use — tight indoor spaces — it is both the cheapest option and, on gap coverage, the best
of the three.

**What you give up:** it is useless outdoors at speed, for all the reasons above. If you
later want avoidance at cruise, that is the camera path, not more ToF.

#### The one ToF that does make sense: upward, for indoors

Your instinct about a top sensor is right, and it is the exception that survives the
maths. Indoors you fly at 2–3 m/s, where 4 m of range **is** adequate warning, and
ceilings are the obstacle a downward-looking aircraft is blindest to.

Three constraints:

1. **Not a VL53L5CX — ArduPilot has no driver for it.** Only `AP_RangeFinder_VL53L0X` and
   `AP_RangeFinder_VL53L1X` exist. The VL53L5CX would need a Lua I²C driver written by
   hand, or handling on the Pi. Use a **VL53L1X** (`RNGFND_TYPE 16`).
2. **Where it mounts — settled 2026-09-04.** Fore or aft of the battery on the top plate.
   The plate is **160.26 mm** long and the battery **138 mm**, leaving **22.26 mm**. The
   sensor's 27° cone must clear the 48 mm battery wall, which needs **≥11.5 mm** of
   standoff — so **the battery sits at one end, not centred** (centred leaves 11.13 mm per
   end, 0.4 mm short). Displacing 615 g of a 1123 g AUW by 11.13 mm moves the CG 6.1 mm;
   push the pack *away* from the existing +3.1 mm offset and the CG **improves** to
   −3.0 mm. Either direction stays inside the ±15 mm tolerance.
3. **Mind the address.** VL53L1X is fixed at 0x29, so an upward one clashes with `U7`. This
   resolves neatly, because `U7` is already unpopulated on the Economic order:

```
RNGFND1_TYPE 46      RNGFND1_ORIENT 25    # TFS20-L, downward, I2C 0x10
RNGFND3_TYPE 16      RNGFND3_ORIENT 24    # VL53L1X, UPWARD, I2C 0x29
RNGFND3_ADDR 41                           # NOT optional - defaults to 0
RNGFND3_MAX 3.60
PRX1_TYPE 4                               # feed the rangefinders to avoidance
```

All of these ship at 0 in `defaults.parm` and are set only when the part is physically
present and publishing — the matched-set rule of §0 (see the project plan).

Two sensors, two addresses, no conflict, ~£4 for the upward one. **Leaving `U7` off turns
out to buy you the upward sensor's address.**

The TCA9548A existed only because *ArduPilot* cannot assign VL53L1X addresses. An MCU hub
**can**, via the standard XSHUT sequence every VL53L1X library implements — so even in the
hub design the mux was redundant. It was inherited from the companion-based version and
never re-examined.

</details>

### Carrying a load — hooks, grippers, winches

Both `AP_Gripper` and `AP_Winch` are **already compiled into this board's firmware**
(4 object files each in the build). Nothing needs enabling at build time.

#### The flight controller side is ready

| Function | `SERVOn_FUNCTION` | Output |
|---|---|---|
| Gripper (servo or EPM magnet) | **28** | `TP3` or `TP4` |
| Winch | 88 | the other one |
| Parachute | 27 | — |
| Landing gear | 29 | — |

`GRIP_ENABLE 1`, `GRIP_TYPE 1` (servo) or `2` (EPM electro-permanent magnet), then
`GRIP_GRAB` / `GRIP_RELEASE` set the two PWM values. Release can be bound to an RC switch
(`RCx_OPTION 19`) or fired from a mission with `DO_GRIPPER`.

Two applets are relevant and shipped: `winch-control.lua`, and **`copter-slung-payload.lua`**,
which damps a swinging load. Read the second one before hanging anything on a line — a
swinging mass is a destabilising input, and it is the reason that applet exists.

#### How much can it actually lift?

Dry all-up weight, using measured figures where we have them (ESC 10.5 g from the manual,
Pi Zero 11 g, TFS20-L 1.35 g) and estimates elsewhere: **~1105 g**.

A 2806.5 1300KV on 4S with a 7040 gives roughly 1100–1400 g per motor at full throttle, so
4400–5600 g total. Payload then depends entirely on how much control margin you keep:

| hover throttle | thrust/weight | payload (at 1250 g/motor) |
|---|---|---|
| 40 % | 2.5:1 | **~895 g** — plenty of margin, good in wind |
| 50 % | 2.0:1 | **~1395 g** — sporty, still controllable |
| 66 % | 1.5:1 | ~2195 g — **do not**; unflyable in any disturbance |

**Design for ~800–900 g of payload** and the aircraft still handles well. Above about
1.4 kg you are trading away the control authority that keeps it upright in gusts.

Note the flight time cost: hovering at 50 % rather than 30 % roughly halves endurance.

#### Powering the servo — mind which rail

| servo | current | take 5 V from |
|---|---|---|
| 9 g micro (SG90 class) | ~250 mA, ~700 mA stall | **this board** — any `+5V` pad |
| standard 20–40 g | 0.5–1.5 A stall | **the ESC's BEC**, not this board |

The board's 5 V has **653 mA** spare over the 0.947 A `LOADS_5V` figure — not the 2.4 A an
earlier draft claimed against `Isat` and a board-only baseline — and that is shared with the
companion computer (a Radxa Zero 3W peaks around 0.7 A). A micro servo fits comfortably; a
larger one should take power from the ESC and share only ground and signal with the FC.

#### The frame side — the bit to check when it arrives

Payload hangs below the **bottom plate**, and generic 7-inch frames vary. Look for:

- through-holes or slots in the bottom plate forward and aft of the battery strap
- enough ground clearance on the landing gear for whatever hangs down
- a mounting point **near the centre of gravity** — a load hung off-centre trims the
  aircraft permanently and eats control authority

If the frame has no useful holes, a carbon or 3D-printed plate bolted to the four 30.5 mm
stack screws is the usual fix, and those screws are M3×30 with spare length already.

---

## Choosing the outdoor altitude source


### Why this matters more than the flow sensor

Optical flow measures *angular* rate. Turning that into a velocity needs a height, and
ArduPilot gets it from the terrain-height estimate that `AP_NavEKF3_OptFlowFusion.cpp`
maintains — line 89 shows fusion degrading when no range data arrives. So the altitude
source sets the ceiling on the whole flow-based velocity chain, whatever produces the
flow.

The fitted `U7` VL53L1X is the weak link:

- `RNGFND1_MAX 3.60` — and that is the optimistic figure
- 27° field of view, a weak 940 nm VCSEL, and poor ambient-light rejection
- field data over pasture: **~33 % useful returns**, against ~89 % for a Benewake-class
  sensor

Over grass in daylight it is close to useless, which is exactly the condition this
aircraft is meant to fly in.

### The candidates, using ArduPilot's own numbers

Vendor range figures are quoted at 90 % reflectivity indoors and are not what you get
over grass in sunlight. The column that matters is what **ArduPilot's own wiki** tells
you to set `RNGFND1_MAX` to, because that is the figure derived from flying them.

| Sensor | `RNGFND1_TYPE` | AP outdoor range | Weight | Size | Price | Verdict |
|---|---|---|---|---|---|---|
| VL53L1X (`U7`, fitted) | 16 | 3.6 m | on board | — | £2 | keep, but landing only |
| **TF-Luna** | 27 | **3 m** | 5 g | 35×21×13 mm | ~£15 | **reject — no gain at all** |
| TFmini-S / Plus | 20 serial, 25 I²C | 6 m | ~5 g | 42×15×16 mm | ~£25 | 2× the VL53L1X, cheap |
| TF-Nova | 27 | 7 m | ~5 g | | ~£30 | little gain over TFmini-S |
| TF02-Pro | 27 | 13.5 m | **50 g** | **69×41×26 mm** | ~£70 | too big and heavy for a 7" |
| **TFS20-L** | 27 | **15 m @ 100 kLux** | **1.35 g** | **21×15×7.9 mm** | £35.70 | **recommended** |

The TF-Luna is worth calling out because it is the obvious thing to reach for and it is
**pointless here** — ArduPilot lists it at 3 m, which is *less* than the VL53L1X already
soldered to the board. Buying one would be spending £15 to gain nothing.

### Recommendation: TFS20-L

- **15 m at 100 kLux.** The spec is quoted *with* sunlight, which is the number that
  actually addresses the failure mode. A 4× improvement on the fitted part outdoors.
- **1.35 g and 21×15×7.9 mm.** Smaller and lighter than the TFmini-S it outperforms —
  a SPAD/dToF module rather than the older triangulation-adjacent parts.
- **3.3 V native, UART or I²C.** Same logic level as the STM32, so no shifting.
- **250 Hz maximum frame rate**, far above what the EKF needs, so it can be slowed for
  averaging.

Stocked in the UK at £35.70 inc VAT (3DXR, 200 in stock), so it does not depend on an
AliExpress lead time landing before the boards do.

### Wiring it — no board change, and the RF pads stay free

The obvious route is the free `SERIAL6` UART on pads `P71`–`P74`. **I²C is better here**,
for a reason worth spelling out.

`AP_RangeFinder.cpp:396` shows `Type::BenewakeTFS20L` (**46**) calling `probe_i2c_buses`
— it is an **I²C-only** driver. The serial path is `27:BenewakeTF03`, which is what
ArduPilot's wiki documents for this module over UART. Both work. But
`AP_RangeFinder_Benewake_TFS20L.h:32` gives `TFS20L_ADDR_DEFAULT 0x10`, and the fitted
VL53L1X sits at 0x29 — **no address clash**, so both sensors share `I2C1` with no
arbitration to arrange.

That matters because `P71`–`P74` are labelled `RF_5V` / `RF_TX` / `RF_RX` / `RF_GND` and
are **earmarked for the SoOP L-band receiver**. Putting the lidar on I²C leaves them
free, so both configurations carry the same loom.

`I2C1` is on `J3` alongside the GPS:

| `J3` pin | Net | Use |
|---|---|---|
| 1 | `+5V` | **not** the module supply — see below |
| 2 / 3 | `USART2_TX` / `_RX` | GPS, already used |
| 4 | `I2C1_SCL` | to the module |
| 5 | `I2C1_SDA` | to the module |
| 6 | `GND` | ground |

**The one thing to get right: the module is 3.3 V and `J3.1` is 5 V.** Do not connect
them. Either buy a retail TFS20-L package that carries its own regulator (several do), or
put a SOT-23 3.3 V LDO in the loom — 150 mA covers the 0.35 W draw and costs about £0.50.
Tapping `TP21` (`SWD_3V3`) works electrically, since the AP2112 uses roughly 250 mA of
600 mA, but that pad is sized as a probe point rather than a power feed.

The I²C logic levels need no attention: the STM32 and the module are both 3.3 V, and
`R9`/`R10` already pull the bus up.

Parameters. **All three rangefinder instances ship DISABLED** (`RNGFND1_TYPE 0`,
`RNGFND2_TYPE 0`, `RNGFND3_TYPE 0`) — a configured but absent rangefinder fails prearm and
the aircraft will not arm (measured, four times in this project). Everything else is
already set, so fitting a sensor is a one-parameter change:

```
RNGFND1_TYPE 46         # BenewakeTFS20L, I2C @ 0x10 - set this once fitted
RNGFND1_MAX 15.00
RNGFND1_MIN 0.20
RNGFND1_ORIENT 25       # down
RNGFND2_TYPE 16         # on-board U7 - only if ever hand-fitted (DNP on Economic)
RNGFND2_ADDR 41
RNGFND2_MAX 3.60
RNGFND2_ORIENT 25
RNGFND3_TYPE 16         # TOP VL53L1X module (GY-53-L1X) - set this once fitted
RNGFND3_ADDR 41         # NOT optional: defaults to 0 and the driver probes address 0
RNGFND3_MAX 3.60
RNGFND3_MIN 0.04
RNGFND3_ORIENT 24       # up - ceiling avoidance
```

The 0x29 clash between the top module and `U7` is not real: `U7` is DNP on the Economic
order, so the address is free — fit one or the other, never both.

**The top sensor only does its job with `PRX1_TYPE 4` set.** Ceiling avoidance works
through proximity, not the rangefinder list: `AC_Avoid.cpp:473` calls
`proximity->get_upward_distance()`, and `AP_Proximity_RangeFinder` supplies that from any
RNGFND instance with orientation 24. Until `PRX1_TYPE 4` is set (which belongs with the
MCU sensor hub publishing ring data), the upward module is fitted and readable but does
nothing.

If the module you receive turns out to be a UART-only variant, the fallback is
`RNGFND1_TYPE 27` on `SERIAL6` with `SERIAL6_PROTOCOL 9` and `SERIAL6_BAUD 115`. Settle
which at bench bring-up — T3 in `docs/BUILD.md` checks the reading against a tape
measure either way.

### At 50 m cruise, neither the flow nor the rangefinder is navigating

> **Deferred-configuration note (2026-09-02).** Optical flow and the SoOP chain are both
> deferred; the aircraft navigates on its real GPS. This section is KEPT UNCHANGED — it is
> the standing record of why flow was never going to be the cruise position source, and it
> is exactly what a revived companion re-inherits.

This is the thing to understand before buying either.

`AP_NavEKF3_Outputs.cpp:110` computes an altitude ceiling whenever optical flow is the
horizontal position source:

```c
height = MAX(rngfnd_max * 0.7f - 1.0f, 1.0f);
```

**70 % of the rangefinder's maximum range, minus a metre.** In a mode needing a position
estimate (Loiter, PosHold) with flow as the only source, the aircraft *will not climb
above it*:

| rangefinder | `RNGFND1_MAX` | flow-nav ceiling |
|---|---|---|
| VL53L1X (`U7`) | 3.6 m | **1.5 m** |
| TFS20-L | 15 m | **9.5 m** |
| TF03 (180 m, 77 g) | 100 m | 69 m |

So at a 50 m cruise, **optical flow cannot be the position source** with any sensibly
sized lidar. That is not a limitation of this board — it is what flow *is*. Flow measures
angular rate, `v/h`; at 50 m the rate is small, the ground resolution is coarse, and the
height it must be divided by is exactly what a short-range lidar can no longer measure.

**The division of labour that follows:**

| altitude | position from | flow + lidar doing |
|---|---|---|
| cruise, ~50 m | **SoOP** (`SRC1`, as a second GPS) | nothing |
| below ~9.5 m | flow (`SRC2`/`SRC3`) | position hold, landing |

At 50 m the SoOP fix carries navigation alone, and it works at any altitude because it is
absolute. The flow and lidar are a **low-altitude safety net** — for holding station near
the ground, and for landing — not for the cruise.

That is a good reason to still fit the TFS20-L, and a good reason not to buy a TF03 to
chase 50 m: at that height you would be paying 77 g and ~£70 for a sensor whose job the
SoOP receiver is already doing.

#### The ceiling is enforced by AC_Avoid — and that has a safety consequence

Traced in source rather than assumed: `AC_Avoid.cpp:459` is the **only** consumer of
`get_hgt_ctrl_limit()`. The ceiling is not applied by the flight mode or the position
controller; it is applied by the avoidance library, as a limit on vertical velocity.

Two consequences worth knowing before flying flow-only:

1. **With `AVOID_ENABLE 0` there is no ceiling at all.** The aircraft will climb out of
   rangefinder range on optical flow and lose its velocity reference, with nothing
   stopping it. If you fly flow-only, `AVOID_ENABLE` is a safety parameter, not an
   obstacle-avoidance convenience.
2. **A `GUIDED` position command bypasses it.** AC_Avoid limits *velocity* in pilot-driven
   modes — Loiter, PosHold. A scripted or GCS-commanded climb is not limited, which was
   confirmed in SITL: with `AVOID_ENABLE 7` set and flow as the only position source, a
   GUIDED climb to 25 m proceeded unimpeded past a 9.5 m ceiling.

So the ceiling protects a *pilot*, not a *mission*. `sitl/scenarios.py` keeps
`rangefinder_ceiling` as a recorded investigation rather than a pass/fail, because
demonstrating it needs RC-driven Loiter rather than a position target.

#### The escape hatch, if you do want flow at altitude

`AP_NavEKF3_Outputs.cpp:98` returns *no limit* when `terrain_srtm_alt_valid` is set —
terrain height taken from the onboard SRTM database instead of a rangefinder. That needs
terrain data on the SD card (`TERRAIN_ENABLE 1`) and a position estimate to look it up,
which in GNSS-denied flight means SoOP. Circular but workable, and it gives terrain
*elevation* rather than height above trees or buildings. Untested here; worth a SITL
scenario before trusting it.

### If you skip it

The board still flies. Flow-based velocity is then bounded to roughly 3 m over
cooperative surfaces, which covers indoor and tarmac bring-up. It does not cover the
GNSS-denied-over-grass case, so the SoOP fix carries navigation alone — which is the
project's actual thesis, so this is a defensible position rather than a broken one.

### Sources

- <https://ardupilot.org/copter/docs/common-benewake-tf02-lidar.html>
- <https://ardupilot.org/copter/docs/common-benewake-tfmini-lidar.html>
- <https://en.benewake.com/TFS20L/index.html>
- <https://www.3dxr.co.uk/sensors-c5/lidar-range-and-flow-sensors-c4/benewake-tfs20-l-p6172>

---

## Indoors: what this configuration does and does not give you

**Decided 2026-09-04: all-round lidar/ToF, no optical flow.** This section records what
that buys, because the difference is easy to assume away.

### Proximity is not a position source. This is architectural, not a tuning problem.

`PRX1_TYPE` feeds `AP_Proximity`, which `AC_Avoid` consumes for **braking and fences**.
It never reaches the EKF. `EK3_SRC*_POSXY` accepts exactly:

| value | source |
|---|---|
| 0 | None |
| 3 | GPS |
| 4 | Beacon |
| 5 | OpticalFlow |
| 6 | ExternalNav |

There is no entry for proximity or rangefinder. A rangefinder is available only as a
**`POSZ`** (altitude) source — which is why `RNGFND1_ORIENT` is `25` (down).

**So indoors, with no GPS and no flow, there is no horizontal position estimate.**
`Loiter` and `PosHold` are unavailable. Indoor flight is **`AltHold` or `Stabilize`,
flown manually**, with the lidar as a safety envelope that stops you reaching a wall.
The aircraft drifts; you correct it on the sticks. That is a normal way to fly indoors —
it is simply not autonomous, and nothing here should later be read as though it were.

The downward rangefinder earns its place in this configuration: it gives precise
`AltHold` indoors, where the barometer drifts as doors open and pressure changes.

### Why ranging off the walls does not hold position

A reasonable idea — hold a fixed range with a PID — and it fails for a geometric reason
rather than a sensor one. The ToF is precise; precision is not the problem.

**One range constrains one axis: the one perpendicular to the surface.** Fly *parallel*
to a wall and the range does not change at all while the position does. Resolving
multiple ranges at multiple bearings into a pose is **scan matching**, i.e. SLAM — a
registration problem, not a control loop. Then: you cannot tell a wall from a person who
just moved; yaw changes every bearing's range at once; and beyond ~12 m or outdoors there
is no return at all.

**SLAM is the real version of that idea**, and ArduPilot documents it — ROS + Cartographer
publishing `VISION_POSITION_ESTIMATE` into `EK3_SRC1_POSXY 6`. Its prerequisites are
recorded in the plan; the short version is a Pi-4-class companion (ArduPilot's own page
used an NVidia TX2; a Pi 3 saturates four cores at 10 Hz), ROS2, and a manual "Set EKF
Origin" before each flight. **And 2D lidar SLAM degrades in exactly the environment this
is for**: it is "susceptible to localization drift and global inconsistency in feature
sparsity, repetitive structures, and dynamic disturbances" — which describes a plain
rectangular room with people in it.

### The optical-flow route, kept resumable

Not fitted, but the firmware side is already in place, so this stays cheap to revisit:

- **`FLOW_TYPE 5` (MAVLink) is already set** in `defaults.parm` — ArduPilot is configured
  to accept `OPTICAL_FLOW` messages from an external computer today.
- **`U6` is a PMW3901 already on the board** and DNP, because it and `U7` face down with
  the ESC 3.0 mm below them (`design.BLIND_SENSORS`). Flow must come from outside.
- **`SERIAL6` (UART4) is free and routed** — `P71`/`P72`/`P73`/`P74`. The lidar takes
  `SERIAL2`; a flow source can take `SERIAL6` with no conflict.
- **Off-the-shelf:** Matek 3901-L0X, ~£28, PMW3901 + VL53L0X over one UART via MSP.
  There is no cheaper option that works here — ThoneFlow-3901U is $27 *flow only*, and
  the £8–12 bare PMW3901 breakouts are SPI, which reaches no pad on this board.
- **DIY:** an ESP32-S3 Sense computing flow and emitting MAVLink `OPTICAL_FLOW`. Prior art
  exists (`tovask/ESP32-CAM`), and `OpticalFlow_MAV` consumes `flow_x`/`flow_y`. It needs
  a *downward* camera — the recording one faces forward — and a rangefinder for scale.
  **Honest risk: custom firmware on the flight-safety path. Bad flow does not degrade
  gracefully; the aircraft flies away.**

#### Which way does the flight controller actually face?

A fair question, because "the FC cannot see down" sounds like an orientation problem and
it is not. **The board is horizontal, component-side up.** `U6` and `U7` are on its
BOTTOM copper, so they genuinely do face downward — the right direction. They are blind
because the ESC's tallest parts sit **3.0 mm** beneath them.

```
  29.60  FC top parts (J3, J1 USB, J8 microSD)   <- FC TOP SIDE, faces UP
  25.20  FC pcb
  23.60  FC underside parts (D1, U6, U7, L5)     <- FC BOTTOM SIDE, faces DOWN
  21.30  ── 3.0 mm compressed grommet gap ──
  18.30  ESC tallest parts                       <- U6 and U7 are looking AT THIS
  12.10  ESC pcb
  10.50  mid plate            <- the 30.5 mm stack pattern bolts here
   8.50  arms
   2.50  bottom plate
   0.00  bottom plate underside
 -12.00  BELLY SENSOR hangs here, looking down, nothing in the way
 -28.50  skid contact line (the ground)
```
*(mm above the bottom plate's top face; generated from `design.required_standoff()`)*

So the fix is not to rotate anything. It is to put the sensor **below the bottom plate**,
where there is **43.5 mm** of clear depth to the ground (`SKID['drop']` 40 + 3.5 mm pad;
this read 28.5 mm, the drop-25 figure, until 2026-09-05). Inverting the stack would not help
either: `U6` is **15.5 mm off the board centre** and the frame's centre pass-through is
only **10 mm** across, so it would still be looking at plate.

#### £28 for a module when the chip is £6 — decomposed, because the question is fair

**The bare `PMW3901MB-TXQT` is ~£6 at LCSC (`C43496881`) and this board already contains
one — `U6`, in the BOM, DNP.** The firmware side exists too: `hwdef.dat` declares
`SPIDEV pixartflow SPI3 DEVID1 EXT_CS1 MODE3`, which is exactly what ArduPilot's Pixart
driver (`FLOW_TYPE 2`) looks for. Chip, wiring and driver are all present.

So the £28 needs justifying, and quoting it without decomposition was sloppy:

| | |
|---|---|
| **£6** | the chip |
| **+ lens assembly** | PixArt specifies a particular lens at a particular working distance. Without it the sensor does not function at all — **this is most of what a module is** |
| **+ SPI→UART bridge** | needed *here* specifically, see below |
| **+ £6 VL53L0X** | flow is an *angular* rate; height converts it to velocity |
| **+ BEC, connector, housing** | |
| **= ~£28** | |

**Why the £6 chip is unusable on this board — and it is not about price:**

1. **`U6` is blind.** It sits on the underside with the ESC 3.0 mm below. Populating the
   chip already in the BOM buys a sensor looking at the top of an ESC.
2. **SPI3 reaches no pad.** `SPI3_SCK`/`MISO`/`MOSI`, `EXT_CS1` and `FLOW_MOTION` all
   terminate at `U6`'s footprint. An £8–12 PMW3901 breakout **cannot be connected.**

That second point is the whole reason an external flow source must speak UART here, and
why a UART module costs what it costs.

#### A respin: five pads make this a £6–12 problem instead of a £28 one

**This is the useful consequence.** A future respin should bring `SPI3_SCK`, `SPI3_MISO`,
`SPI3_MOSI`, `EXT_CS1` and `FLOW_MOTION` out to pads alongside `+3V3` and `GND` — seven
pads, no new silicon, no new nets. Then:

* a **£8–12 PMW3901 breakout** connects directly and works with `FLOW_TYPE 2`;
* the **`SPIDEV pixartflow` entry already in `hwdef.dat` covers it** — no firmware change;
* `SERIAL2` and `SERIAL6` both stay free for the lidar and whatever else;
* and the on-board `U6` can stay DNP forever without wasting the design work already
  done for it.

It also fixes the underlying fault rather than routing around it: the reason flow is
awkward on this board is that the only PMW3901 provision faces a component 3 mm away.
Exposing the bus is how a blind sensor becomes a usable one.

#### Could the ESP32-S3 Sense do BOTH — record to SD *and* provide flow?

**No.** Four independent reasons, any one of which is disqualifying:

1. **One camera cannot face two directions.** Flow must look *down*. Recording is far more
   useful looking *forward*. You would be choosing one job, not doing both — unless
   downward-only footage is acceptable, which for flight video it usually is not.

2. **Rolling shutter disqualifies it for flow regardless of orientation.** This document
   already says why, above: *"Rolling shutter plus prop vibration produces jello that
   corrupts flow — use a global shutter sensor (OV9281-class)."* The XIAO ships an
   **OV2640 or OV3660 — both rolling shutter**. That is precisely why `design.CAMERA` is
   an **OV9281 global-shutter** module and not something cheaper.

3. **The sensor emits one format at a time.** Recording wants JPEG, which the OV2640
   encodes *in-sensor* — that is what keeps the ESP32's CPU load low enough to hit ~20 fps
   to the card. Flow wants raw grayscale. Doing both means either decoding JPEG on the
   ESP32 every frame, or alternating sensor modes and halving the rate of each. Both are
   expensive and both add latency.

4. **SD writes stall.** Cards pause for 100 ms or more during internal wear-levelling.
   A recording pipeline can absorb that; a flow pipeline feeding a *position estimate*
   cannot, because the stall lands in a flight-critical loop as a dropout.

#### So: dedicated flow sensor, or global-shutter camera?

**Dedicated sensor, and it is not close for the money.** The PMW3901 "is an optical flow
ASIC that **computes the flow internally** and provides a difference in pixels between
each frame" — no camera pipeline, no CPU load, no format conflict, and a deterministic
output rate. That is the entire reason the part exists.

| option | ~cost | verdict |
|---|---|---|
| **Matek 3901-L0X** (PMW3901 + VL53L0X, one UART) | **£28** | **works today, stock firmware.** The practical answer |
| OV9281 global shutter + companion | £25 camera + a companion that fits | **better flow**, and the right answer for a research-grade system — but it needs the deferred companion and real code |
| ESP32-S3 Sense computing flow *instead of* recording | £12 | rolling shutter; usable as an experiment, not for flight-grade position hold |
| ESP32-S3 Sense doing **both** | £12 | **not viable** — see the four reasons above |

The honest framing: the ESP32-S3 Sense is a good **recorder**. It is not a flow sensor,
and asking it to be both makes it worse at the job it is actually good at.

**Field note that applies to every option above:** PMW3901-class sensors fail over grass.
They all use that sensor. This is an indoor part.

## The GNSS-denied navigation chain


> **DEFERRED (2026-09-02).** The companion computer and the SoOP Doppler chain are
> deferred; the aircraft navigates on its real GPS outdoors, with ToF indoors. This
> document is kept intact and labelled deferred because it is still the contract a
> future companion must satisfy — and because the sitl/ harness that proved it remains
> the fastest way to revive the work. Nothing here describes hardware that is fitted
> today.

What the companion computer must send the flight controller, and what ArduPilot does
with it. This is the interface contract — the Pi-side implementation can be anything that
satisfies it.

### How accurate can this actually be? — the number that bounds the whole project

**Researched 2026-09-04, and it changed the project's framing.** Published Iridium
Doppler positioning results:

| result | conditions |
|---|---|
| **~180 m** mean eastward error, **~380 m** MAE | Iridium NEXT, **without elevation assistance** |
| **656 m** | Doppler-only, a **single** Iridium NEXT satellite |
| **289.5 m** | single satellite, Doppler **+ azimuth DOA** |
| **400–1200 m** along-track | Iridium-based *instantaneous* positioning |
| **22.7 m** | **4 Iridium + 1 Orbcomm** — five satellites, two constellations, **static** |

`sitl/soop_link.py` modelled **`[A] 20 m sigma`** until this was checked. That is
essentially the *best* published figure — five satellites across two constellations on a
stationary receiver — and it was being applied to single-constellation Iridium on a
moving quadcopter. Optimistic by roughly an order of magnitude, and **every SITL number
in this repository inherited it.** The default is now **180 m**, tagged `[L]`.

Worth noting: the bimodal dead-reckoning results already measured here (bounded ≤79.6 m,
diverged ≥216.7 m) sit much closer to the literature than the 20 m input did. The
simulator was telling the truth while its input flattered it.

#### No hardware purchase raises this ceiling

The dominant error is **ephemeris, not the receiver** — which is true, and is why no
antenna or SDR upgrade *within this band* moves the number. It does **not** mean 180 m is
an absolute floor. But the two escape routes were overstated here until 2026-09-05, and
[BENCHMARK.md](BENCHMARK.md) §3a now carries the corrected reading:

- **Multi-constellation is not free, and the 5.1 m version of it is not reachable.** That
  result needs Starlink and OneWeb, which downlink at **10.7–12.7 GHz with 230–240 MHz of
  bandwidth**. This aircraft's chain is a 1620 MHz patch, a 60 MHz SAW and a 2.4 MHz
  RTL-SDR — wrong by ~7× in frequency and ~100× in bandwidth. What *is* reachable is
  **Iridium + Orbcomm** (137 MHz VHF, inside the RTL-SDR's range, one extra antenna), and
  the same literature puts that at **22.7 m static** — the honest target.
- **5.1 m is also a *stationary* figure.** The same paper's *moving* results are
  **18.4 m RMSE** and **9.5 m RMSE**, on a ground vehicle with an industrial-grade IMU and
  an altimeter running a LEO-aided INS.
- **The sub-metre differential figure is UNVERIFIED.** The cited abstract claims only a
  "90% reduction versus existing differential Doppler" — no absolute RMSE, constellation,
  baseline or receiver dynamics. Do not quote it until someone reads the results tables.

The ELRS-bandwidth finding stands on its own and is unaffected: the link can carry base
observables. What is corrected is how much accuracy that buys.

The receiver-side argument itself:

> TLE orbit error "could be several kilometers and is **considered the main source of
> positioning inaccuracy**". Satellite position and velocity errors of ~3 km and ~3 m/s
> alone induce position errors "of **more than several km**".

So a better SDR, a better TCXO, a better LNA or a better antenna **do not move the
accuracy ceiling**. They raise SNR — which you need to detect bursts at all, and which is
exactly what the SAWbird+ IR is for — but the limit is how well you know where the
satellite was, and TLEs are kilometres wrong.

#### What does improve it, and this aircraft already carries two

1. **Barometric elevation aiding.** The 180 m figure is explicitly *"without elevation
   assistance"*. This aircraft has a barometer; constraining altitude collapses a
   three-unknown solve to two and attacks the worst-conditioned axis. **Free.**
2. **INS coupling** — published as **"up to 180% improvement"** over Doppler alone. Two
   IMUs and an EKF are already fitted. **Free, and already the architecture.**
3. **Ephemeris error as an estimated state**, or double-differencing between satellites.
   Published schemes cut initial satellite position error "from several kilometers to
   hundreds of meters".
4. **More satellites and more constellations** — the 22.7 m result needed five. Orbcomm
   (137–138 MHz) and Starlink are the usual additions.

#### The conclusion that should shape the claim

**Iridium Doppler is not a precision sensor. It is a drift-bounding one.**

An IMU is precise over seconds and diverges quadratically (this repo measured it: the
divergence is dominated by attitude error leaking gravity, `a = g·sin θ`, not accel
bias). Optical flow and VIO are precise *relative* sensors that also drift. Doppler is
coarse — but it is **absolute and does not drift**.

So "ultra precise GNSS-denied" is not one sensor. It is **a precise relative sensor whose
drift is bounded by a coarse absolute one**, which is exactly what the EKF exists to do.
The honest claim for this project is not "position to a few metres from Iridium" — the
literature says that is not available — but **"bounded error indefinitely, with
metre-level short-term precision"**. That is achievable, and it is the stronger claim,
because it is the correct architecture rather than an optimistic number.

**Open consequence:** the precision half of that architecture is not currently fitted.
Indoors the choice was lidar-only, which is fine for manual flight. Outdoors under GNSS
denial there is no precise relative sensor — and the field note that PMW3901-class flow
fails over grass means the obvious candidate may not work in the obvious place. Decide
that deliberately rather than by default.

### Topology

```
  Iridium NEXT L-band  ──▶  RF front end (SoOP config / off-board)
                                    │
  camera (global shutter) ──▶  Radxa Zero 3W ──┬─▶ GPS_INPUT       (position, ~1 Hz)
                                    │          └─▶ OPTICAL_FLOW    (velocity, 10-50 Hz)
                                    │
                              SERIAL1 / UART7, 921600, MAVLink2
                                    │
                              STM32H743  ──▶  EKF3  ──▶  attitude + position
                                    │
                              I2C1: TFS20-L @ 0x10  (height, and the scale for flow)
```

The link is `SERIAL1` on pads `P42`/`P43`, already configured: `SERIAL1_PROTOCOL 2`
(MAVLink2), `SERIAL1_BAUD 921`.

### The SoOP fix is a GPS. It is not ExternalNav.

This was decided by measurement in `sitl/`, and it reversed the obvious choice. The
reasoning is short and it is worth not re-deriving:

| | timeout | implied minimum rate |
|---|---|---|
| `AP_VISUALODOM_TIMEOUT_MS` (`AP_VisualOdom.h:31`) | **300 ms** | **> 3.3 Hz** |
| `GPS_TIMEOUT_MS` (`AP_GPS.cpp:74`) | **4000 ms** | **> 0.25 Hz** |

An Iridium Doppler solution needs an observation arc across a satellite pass. It lands at
roughly **1 Hz** — comfortably inside what a GPS may do, and more than three times too
slow to keep visual odometry healthy.

**What that actually does, measured rather than assumed:** VisOdom health flaps. Arming is
intermittent — it sometimes refuses with `PreArm: VisOdom: not healthy`, and sometimes
succeeds when a message happens to land inside the 300 ms window. Once airborne the
ExternalNav data is largely ignored, so the aircraft is really navigating on optical flow
with baro, which is *dead reckoning* and drifts without bound.

That is worse than an outright refusal, because it looks like it works. An earlier draft
of this document claimed ExternalNav at 1 Hz "can never arm"; that was too strong, and the
truth is less comfortable.

`sitl/scenarios.py` keeps `extnav_1hz` as a recorded measurement rather than a pass/fail.

Choosing GPS turns out to be simpler in every direction:

- no EKF origin to track on the Pi, and no NED conversion
- position is absolute, so RTL and waypoints work natively
- **failover is automatic.** `GPS_AUTO_SWITCH 1` (UseBest) moves to whichever instance
  reports the better fix, so when the real receiver is jammed the SoOP instance takes
  over with no pilot action at all

To force the SoOP instance for testing: `GPS_AUTO_SWITCH 0` and `GPS_PRIMARY 1`.

### Why the rangefinder is part of the *navigation* chain

`AP_OpticalFlow_MAV.cpp` ignores the `ground_distance` field of `OPTICAL_FLOW`. Height
comes from the rangefinder, and `AP_NavEKF3_OptFlowFusion.cpp:89` degrades when no range
data reaches the fusion horizon.

Flow alone gives an angular rate and nothing else. **Flow velocity is only as good as the
height measurement** — which is why `docs/SENSORS.md` exists and why the fitted
VL53L1X was demoted. Send perfect flow with no usable height and the EKF gets no usable
velocity.

### Message 1 — position, `GPS_INPUT` (#232)

Enabled by **`GPS2_TYPE 14`** (MAV). Handled by `AP_GPS_MAV.cpp`.

Two names here are easy to get wrong, and both fail *silently*:

**It is `GPS2_TYPE`, not `GPS_TYPE2`.** ArduPilot renamed the GPS parameters in 4.6 —
`AP_GPS.cpp:280-285` registers the instances as subgroups `"1_"` and `"2_"`. The old
spelling still appears in the generated parameter metadata as a conversion alias for
ground stations, so a metadata-based check passes it while the firmware declines to set
it. `sitl/check_params_live.py` exists because of this: it reads every shipped parameter
back from a running build, which is the only authority on what a build accepts.

**`gps_id` is the zero-based instance index.** `AP_GPS_MAV.cpp:51` is:

```c
if (state.instance != packet.gps_id) { return; }
```

So `GPS2_TYPE` requires **`gps_id = 1`**. Sending `gps_id = 0` targets the real receiver,
whose driver is not `AP_GPS_MAV`, and every message is discarded without a warning — the
second GPS simply never appears.

| Field | Units | Notes |
|---|---|---|
| `time_usec` | µs | shared timebase — see below |
| `gps_id` | | `0`; it maps to the MAV instance |
| `fix_type` | | `3` for a 3D fix. Drop to `1` when the solver has no confidence |
| `lat` `lon` | 1e-7 deg | the Doppler solution, absolute |
| `alt` | m MSL | baro carries height anyway; be honest here regardless |
| `hdop` `vdop` | | used for instance selection under `GPS_AUTO_SWITCH 1` |
| `h_acc` `v_acc` `vel_acc` | m | **The important fields.** The EKF weights on these, and `UseBest` picks between receivers with them. A confident wrong answer is what crashes aircraft |
| `vn` `ve` `vd` | m/s | send `0` and clear the velocity bits in `ignore_flags` unless the solver genuinely produces velocity |
| `satellites_visible` | | breaks ties at equal fix status |

#### Rate: publish at 5 Hz, not at the solution rate

`GPS_TIMEOUT_MS` is 4000 ms, which suggests 0.25 Hz would do. **It will not arm.**
Measured, by sweeping the injection rate against a running build:

| published rate | result |
|---|---|
| 1 Hz — the raw Doppler solution rate | `PreArm: GPS 2: Bad fix` — **will not arm** |
| 2 Hz | `PreArm: GPS 2: Bad fix` — **will not arm** |
| 5 Hz | arms, flies, and holds position through denial |

The 4 s timeout governs when a GPS is declared *lost*. ArduPilot's **arming** check is
stricter, and a fix arriving once a second does not satisfy it.

So the companion must **publish faster than it solves**: hold or interpolate the last
Doppler solution up to 5 Hz, and let `h_acc` grow between true fixes so the EKF weights
the interpolated samples honestly. What you must not do is republish a stale solution with
an unchanged `h_acc` — that claims confidence the receiver has not earned.

`sitl/scenarios.py` keeps `soop_raw_1hz` as a regression test that publishing at the raw
solution rate **fails to arm**.

#### The two GPS instances must agree within 50 m on the ground

`AP_Arming.cpp:741` calls `gps.all_consistent()` and refuses to arm with
`GPS positions differ by %4.1fm` when two instances disagree by more than **50 m**. The
threshold is hardcoded — there is no parameter to relax it. A second check requires AHRS
and GPS to agree within 10 m.

**Recomputed 2026-09-05, and the conclusion changed from "annoying" to "blocking."** This
paragraph used to reason from the assumed σ = 20 m: a 50 m disagreement is 2.5σ, so
intermittent refusals "a few percent of the time". The sigma is now the published **180 m**,
and the same arithmetic gives a very different answer. Treating the offset as 2-D radial
with per-axis σ, `P(R > 50) = exp(−50² / 2σ²)`:

| σ | what it is | 50 m as | P(refuses to arm) |
|---|---|---|---|
| 5.1 m | multi-constellation *including Ku-band Starlink/OneWeb* — **not reachable with this receiver**, and a static figure | 9.8σ | ~0% |
| 20 m | the old **assumed** figure | 2.5σ | 4.4% |
| 22.7 m | best measured multi-constellation, static | 2.2σ | 8.8% |
| **180 m** | **published Iridium NEXT, no elevation aiding** | **0.28σ** | **96.2%** |

**At the honest sigma the aircraft essentially never arms.** This is not a projection — the
SITL suite demonstrates it: `soop_gpsinput`, the *shipped configuration*, reported
`GPS positions differ by 129.4m / 347.9m / 197.7m / 290.8m / 95.1m / 268.6m` and never left
the ground. Ten scenarios failed to arm for this one reason, and they used to fly only
because the old 20 m sigma kept the scatter under the threshold.

**So the companion aligning its solution to the flight controller's GPS while GNSS is
available is not an optimisation — it is the thing that makes the aircraft armable.** It
should be doing this anyway, since a real receiver needs that reference for calibration and
bias estimation. Publish a solution consistent with the live GPS on the ground, and let the
two diverge only after denial, in flight, where the check no longer applies.

**The SITL harness does not model that alignment**, which is why the scenarios now fail to
arm rather than fly. That is a harness gap, not an aircraft defect — but it means the SoOP
scenarios currently prove nothing about in-flight behaviour, and fixing the harness to
publish a GPS-aligned solution before denial is now the prerequisite for any of those
numbers meaning anything again.

Do not work around this by withholding `GPS_INPUT` until airborne: `GPS2_TYPE` is
`@RebootRequired`, and an instance with no data fails its own health check anyway.

#### Send velocity — but do not expect it to buy accuracy

Doppler measures range-rate, so **velocity is what an SoOP receiver observes directly**;
position is what you derive from it across a pass. Sending it costs nothing and reports
what the instrument actually measures, so set `vn`/`ve`/`vd` with an honest
`speed_accuracy` and leave `ignore_flags` at 0.

**It does not measurably reduce position error here, and an earlier draft of this document
claimed it was necessary. That was wrong.** Measured over four seeds, 300 s of denial, with
σ 20 m position and σ 0.3 m/s velocity:

| | mean error | p95 |
|---|---|---|
| velocity sent | 30.7 m | 56.3 m |
| velocity fields ignored | 30.9 m | 59.8 m |

Indistinguishable. The EKF derives velocity perfectly well from successive positions and
the IMU, so a position-only solver is not crippled — `EK3_SRC1_VELXY 3` does not mean the
estimator is helpless without GPS velocity, which is what the earlier claim assumed.

Velocity may matter more when position fixes are sparser or noisier than modelled here.
Worth re-measuring with `sitl/scenarios.py --only soop_no_velocity` if the receiver's real
numbers differ.

### Message 2 — velocity, `OPTICAL_FLOW` (#100)

Enabled by `FLOW_TYPE 5`, consumed when the active source set has `EK3_SRCn_VELXY 5`
(`SRC2` and `SRC3`).

| Field | Units | Notes |
|---|---|---|
| `time_usec` | µs | same timebase |
| `sensor_id` | | any consistent value |
| `flow_rate_x` `flow_rate_y` | **rad/s** | **Preferred.** `AP_OpticalFlow_MAV.cpp:110` uses these whenever either is non-zero |
| `flow_x` `flow_y` | pixels | fallback only, scaled by dt — less precise |
| `quality` | 0–255 | **Be honest.** 0 over featureless ground is correct and useful |
| `ground_distance` | m | **Ignored by ArduPilot.** Height comes from the rangefinder |

**Rate: 10 Hz minimum, 30–50 Hz preferred.** Set `quality` low rather than dropping
messages when the camera loses texture — silence looks like a dead sensor.

Two calibrations that are not optional: `FLOW_ORIENT_YAW` must match the camera's
mounting, and the sign must be verified on the bench. A sign error flies the aircraft
*away* from where it should hold, accelerating.

Rolling shutter plus prop vibration produces jello that corrupts flow — use a **global
shutter** sensor (OV9281-class).

### Timestamps

The commonest way this chain fails quietly. The EKF fuses by timestamp; a constant offset
shows up as a position that lags and oscillates, not as an error.

- Send `SYSTEM_TIME` (#2) from the Pi, or take the FC's, and stick to one.
- `PE10` (`UART7_CTS`) is reserved as `PPS_SYNC_IN` for hardware sync in the SoOP config. The default config has
  no hardware sync, so software agreement is all there is.
- Latency is dominated by the Pi's scheduling, not by 5 cm of wire at 921600 — timestamp
  at **capture**, never at send.

### Startup order is not optional

Anything ArduPilot judges "healthy" by data arrival must be *arriving* before you arm.
Start the companion, confirm the stream, then arm. Out of order you get a prearm failure
that looks like a configuration fault and is really a race.

### What must be true before the first GNSS-denied flight

- [ ] Rangefinder reads correctly against a tape measure (T3 in `docs/BUILD.md`)
- [ ] Flow sign verified by hand-translating the aircraft, both axes
- [ ] Timestamps agree — no growing offset over a 10 minute run
- [ ] `h_acc` genuinely reflects solution quality, and degrades when the solver is unsure
- [ ] `fix_type` drops to 1 on loss rather than holding 3 with a stale position
- [ ] Failover tested **on the ground** by disabling the real GPS, then in the air

---

## What else this board can do


ArduPilot ships **156 example Lua scripts and 49 finished "applets"** in Copter-4.7.0, and
**Lua is already compiled into this board's firmware** — `AP_Scripting.cpp.0.o` is in the
build, because scripting auto-enables above 1 MB of flash and the H743 has 2 MB. Scripts
live on the microSD card (`SDMMC1`, 4-bit, fitted as `J8`) and run sandboxed alongside the
flight code.

Turn it on with `SCR_ENABLE 1`. Nothing else is needed.

Flash headroom is **~172 KB** (1,527,724 bytes used of 1,703,936), which is enough for
scripts but not unlimited — a very large script set may need a trimmed build.

### Directly useful to the GNSS-denied work

These are not novelties; they overlap the reason the board exists.

| Applet | What it does | Hardware needed |
|---|---|---|
| **`copter-deadreckon-home.lua`** | Flies home by dead reckoning when GPS quality collapses or is lost | none — **fit this before the first GNSS-denied flight** |
| **`ahrs-source-extnav-optflow.lua`** | Switches EKF sources from an RC switch, with automatic fallback | none; this is `RCx_OPTION 90` with logic on top |
| `ahrs-set-origin.lua` | Sets the EKF origin without GPS | none — relevant to a cold GNSS-denied start |
| `active_source_set.lua` | Reports which EKF source set is live | none |
| **`RockBlock.lua`** | Iridium **RockBlock** satellite modem for beyond-line-of-sight telemetry | a RockBlock 9603/9704 on the spare UART |

#### The satellite link, in detail

`RockBlock.lua` is worth a second look: it is *Iridium*, the same constellation this board
navigates from. A RockBlock on `SERIAL6` would give real satellite telemetry alongside the
SoOP receiver — the same birds doing two jobs.

**This is the only beyond-line-of-sight link in the design, and the SoOP receiver is not
one.** Iridium NEXT Doppler is passive listening — a *navigation* source, receive-only. It
cannot carry a command.

Wire a **RockBLOCK 9603** to the spare UART pads:

| pad | signal |
|---|---|
| `P71` | 5 V |
| `P72` | RF_TX → modem RX |
| `P73` | RF_RX ← modem TX |
| `P74` | GND |

```
SERIAL6_PROTOCOL 28     # Scripting - the applet owns the port
SERIAL6_BAUD 19         # 19200, the 9603's default
SCR_ENABLE 1
RCK_FORCEHL 2           # enable high-latency mode on GCS link loss
RCK_PERIOD 30           # seconds between mailbox checks
```

The GCS end needs [`rockblock2mav`](https://github.com/stephendade/rockblock2mav).

**Be clear about what this is and is not.** From the applet's own documentation: it sends
**`HIGH_LATENCY2` packets only** — no heartbeats, no command acknowledgements, no
statustexts, no parameters. One packet every `RCK_PERIOD` seconds, and **one** command
per mailbox check; a second command in the same window overwrites the first. That is
enough to see where the aircraft is and to command a mode change or a divert. **It is not
a manual control link, and it never will be.** Manual flying is the CRSF radio on
`P51`–`P54`, and that is line-of-sight.

Iridium SBD is also billed per message, so `RCK_PERIOD` is a running cost, not just a
latency setting.

### Things that work with what is already on the board

| Applet | Uses | Status |
|---|---|---|
| `winch-control.lua` | a servo output | ✅ `TP3`/`TP4` |
| `copter-slung-payload.lua` | damps a swinging slung load | ✅ no extra hardware |
| `LED_matrix_text.lua`, `LED_matrix_image.lua`, `LED_roll.lua`, `LED_poslight.lua` | WS2812 strip | ✅ `PL1`–`PL3`, `U17` level shifter fitted |
| `leds_on_a_switch.lua` | LEDs from an RC switch | ✅ same |
| `SmartAudio.lua` | sets VTX band/power from the FC | ✅ spare UART + the 9 V VTX rail (`PV1`) |
| `follow-target-send.lua` | emits `FOLLOW_TARGET` so another aircraft can follow this one | ✅ MAVLink only |
| `MissionSelector.lua` | picks between stored missions from a switch | ✅ SD card |
| `Script_Controller.lua`, `Param_Controller.lua` | swap script/parameter sets in flight | ✅ SD card |
| `arming-checks.lua` | custom pre-arm checks | ✅ |
| `crash-actions.lua` | scripted response to a crash | ✅ |
| `repl.lua` | interactive Lua prompt over MAVLink — genuinely fun for debugging | ✅ |
| `UniversalAutoLand.lua` | scripted autonomous landing sequence | ✅ |

### Things that need one part you do not have yet

| Applet | Needs |
|---|---|
| `mount-poi.lua` | a gimbal — the servo outputs at `TP3`/`TP4` can drive a simple 2-axis one |
| `Gimbal_Camera_Mode.lua`, `ONVIF_Camera_Control.lua` | a gimbal / ONVIF camera |
| `plane_package_place.lua` | a release servo — `TP3` |
| `SN-GCJA5-particle-sensor.lua` | an I²C air-quality sensor on `I2C1`. **Aerial air-quality mapping is a genuinely good project for a long-range quad** |
| `pelco_d_antennatracker.lua` | a ground antenna tracker, not an airborne part |
| `net_webserver.lua`, `net-ntrip.lua` | networking. `AP_Networking` is built, but only the **PPP** backend applies without an Ethernet PHY — a PPP link over the companion UART is possible and unexplored |

### Things this board cannot do

| | Why |
|---|---|
| Ethernet-based anything | no PHY, and no pins left for one |
| More than two servo/gimbal axes | only `PWM5`/`PWM6` are broken out; `PWM7`–`PWM12` exist in silicon but reach no pad |
| Several I²C accessories tidily | one exposed bus, shared with the GPS — see `docs/SENSORS.md` |

### The deployable-mechanism project

Everything needed is already there: a servo on `TP3`, power from any `+5V` pad, and either
`winch-control.lua` or a mission command through `SERVO5_FUNCTION`. For anything that
changes the aircraft's drag or centre of gravity when it deploys,
`copter-slung-payload.lua` is worth reading first — it exists because swinging loads
destabilise a multirotor, and a deploying canopy is a very large, very sudden one.

### Writing extensions in C/C++ instead of Lua

Lua is the *sandboxed* option, not the only one. ArduPilot is C++ and you already build it
from source with a custom hwdef and board ID, so adding C++ is a small step from where you
are. Four entry points, in increasing order of how much you take on:

| Route | What it is | Cost |
|---|---|---|
| **On the Pi** | The SoOP DSP, camera flow and avoidance all live here already. Any language. MAVSDK is C++; `c_library_v2` is plain C | none — this is the natural home for heavy work |
| **`AC_CustomControl`** | A backend framework for custom attitude controllers. `AC_CustomControl_Empty.cpp/.h` is a fill-in-the-blanks template with parameter registration already wired | build with `AP_CUSTOMCONTROL_ENABLED=1`; set `CC_TYPE` |
| **A new `AP_GPS` backend** | `AP_GPS_SoOP.cpp` alongside `AP_GPS_MAV.cpp`, reading the receiver over a UART in a compact binary protocol instead of MAVLink `GPS_INPUT` | lower latency, and you control the driver's own health logic rather than fighting the arming checks |
| **`AP_ExternalAHRS` backend** | A whole navigation source in C++. Existing backends: VectorNav, MicroStrain, InertialLabs, GSOF, SBG. A SoOP backend slots in as a new type | the most "proper" integration, and the most work |

**The honest trade.** Lua is sandboxed: a bug stops the script, not the aircraft, and it
survives an ArduPilot upgrade untouched. C++ runs inside the flight code with no net, and
every upstream release is a rebase. For anything that must not be able to take the vehicle
down, and for anything you want to still work in a year, Lua is the better tool even though
it is the less powerful one.

The sensible split for this project: **C/C++ on the Pi** for the DSP and vision, **Lua on
the flight controller** for glue and mode logic, and drop to a C++ `AP_GPS` backend only if
the MAVLink transport turns out to be the bottleneck. It is not, at 5 Hz.

---
