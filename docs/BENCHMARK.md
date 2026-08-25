# NAVCORE-SoOP against the field

Researched 2026-09-04; §2c (indoor sensor suite vs commercial and DIY platforms) added
2026-09-05. Three comparisons: the **hardware standard** commercial autopilots
follow, what **open-source GNSS-denied projects** actually do, and where the **SoOP
literature** has got to. Every claim here is sourced; where a source changes something in
this repository, the change is named.

---

## 1. Against the Pixhawk FMUv6X standard

FMUv6X is the current open hardware standard behind the Holybro Pixhawk 6X, CUAV V6X and
RaccoonLab FMUv6X. It runs the **same STM32H7 at 480 MHz with 2 MB flash** this board does,
so the processor is not the difference. The difference is entirely in the sensor front end.

| | FMUv6X | NAVCORE-SoOP | does it matter here? |
|---|---|---|---|
| IMUs | **triple redundant**, on **separate buses**, each with an **independent LDO and independent power control** | two — `U2` ICM-42688-P, `U3` ICM-42605 | Redundancy is for *fault detection*, not accuracy. Two IMUs cannot vote; three can. Relevant to reliability, not to the drift claim |
| Barometer | double redundant | single | same category |
| **IMU heating** | resistive heaters hold the IMUs at a set point | **none** | **This one does matter.** See below |
| Vibration isolation | isolation system on the IMU module itself | grommets isolate the **stack**, not the sensors | Already a recorded gap in `VERIFICATION.md` |
| Architecture | modular — FMU, IMU and Base separate, joined by 100-pin + 50-pin bus | single board | Ours is a 45.1 × 46.1 mm board that drops into a 30×30 stack. Different problem |
| Fault handling | PX4 switches sensor sets on detected failure | ArduPilot EKF3 lane switching, two lanes | fewer lanes, same mechanism |

**The heating gap is the one worth acting on, and it has a free software answer.**

This aircraft's claim is that Doppler *bounds* inertial drift. That drift is dominated by
attitude error leaking gravity into the horizontal channel — **0.10° of tilt gives 30.8 m at
60 s and 123.3 m at 120 s** — and gyro/accel bias is strongly temperature-dependent. A board
sandwiched between a 60 A ESC and a battery in a 30×30 stack with almost no airflow does not
hold a constant temperature.

FMUv6X solves it in hardware. **ArduPilot solves it in software with `INS_TCAL*`, which
costs nothing and was not configured here.** Prerequisites are both met: a 2 MB autopilot
(STM32H743) and a microSD for logging (`J8`). Now a bring-up step — **`docs/BUILD.md` T3c**.
It is deliberately *not* in `defaults.parm`: `ENABLE 2` is a learning mode, and shipping it
would restart calibration on every boot.

---

## 2. Against open-source GNSS-denied projects

The dominant open-source approach is **VIO / SLAM on a companion computer**, feeding
ArduPilot or PX4 over the MAVLink external-navigation interface
(`VISION_POSITION_ESTIMATE`, fused by EKF3). Typical stacks pair a Raspberry Pi with ROS 2,
optical flow, lidar and a camera.

**This project is genuinely differentiated, and the honest framing is complementary rather
than superior:**

| approach | bounded? | needs | fails when |
|---|---|---|---|
| VIO / SLAM | **no** — drift is unbounded, though slow | camera + companion + compute | featureless scenes, darkness, motion blur |
| optical flow | no — unbounded | downward camera + good light + texture | over grass, low light, high altitude |
| **SoOP Doppler** | **yes** — bounded, absolute | RF front end + sky view | indoors, under canopy |
| terrain-referenced | yes, bounded | rangefinder + prior DEM | flat terrain |

The distinction that matters: **VIO and flow are precision-but-drifting; SoOP is
coarse-but-bounded.** They are complementary, which is exactly why `EK3_SRC*` is arranged
to switch between them rather than to pick one. Positioning the project as "more accurate
than SLAM" would be wrong; positioning it as "bounded where SLAM is not" is correct and
defensible.

Also worth knowing: the **SPRIN-D Challenge** winner (2025) navigated **9 km** GNSS-denied
by matching **LiDAR-derived local heightmaps against a prior geo-data heightmap**, real time,
**CPU-only**. It is a reminder that terrain-referenced navigation is live and cheap in
compute — but it needs a *scanning* sensor building a local surface. Our LD06 scans the
**horizontal** plane and the TFS20-L is single-point, so this is not a drop-in; a
single-point downward profile (classic TERCOM) would bound along-track drift only over
terrain with relief, and gives nothing over a flat field or indoors.

---

## 2b. Against commercial GNSS-denied drones

The reference point is the **Skydio X10D**: visual-inertial odometry off **six 4K stereo
cameras** and an **NVIDIA Jetson**, reporting sub-metre localisation and autonomous return
in GNSS-denied or spoofed conditions at altitudes up to several kilometres. Flyability,
Spleenlab and OKSI's OMNInav occupy the same technical space.

**They are more accurate than this aircraft by two orders of magnitude, and that is the
wrong axis to compete on.** The differences that actually matter:

| | Skydio-class VIO | NAVCORE-SoOP |
|---|---|---|
| accuracy | **sub-metre** | 180 m single-receiver (literature, unmeasured on this hardware) |
| bounded? | **no** — VIO drifts; sub-metre is *per-interval*, and long-term accuracy comes from re-anchoring against mapped visual references | **yes** — Doppler is an absolute fix; error does not grow with time |
| darkness / fog / featureless terrain | **fails** — no features, no odometry | **unaffected** — RF does not care |
| sensing hardware | 6 × 4K stereo cameras | one L-band antenna |
| compute | NVIDIA Jetson | STM32H743, or a laptop-side SDR |
| cost | enterprise, five figures | **£684 airframe, £189 board** |
| what defeats it | darkness, smoke, blank walls, motion blur | no sky view — indoors, under canopy |

**The honest claim is about failure modes, not precision.** VIO is precision-but-drifting
and vision-dependent; Doppler SoOP is coarse-but-bounded and light-independent. An
interviewer who knows this field will not be impressed by "GPS-denied navigation" — every
enterprise drone does that — but will engage with *"my error is bounded and does not depend
on seeing anything, and here is the measured sigma"*.

That framing also makes the sensor suite coherent rather than a shopping list: the lidar and
rangefinder handle the indoor case where SoOP has no sky, and the EKF source-switching in
`docs/MODULES.md` is the mechanism for moving between the two regimes.

### 2c. The indoor sensor suite, against who actually flies indoors (added 2026-09-05)

This aircraft's indoor sensor plan is: one LD06 scanning lidar (`PRX1_TYPE 16`) for the
obstacle ring, a downward VL53L1X for close-range altitude, an optional upward VL53L1X for
ceilings, and PMW3901 optical flow on-board (deferred). How that compares, by platform:

| platform | indoor position | obstacle sensing | what ours does differently |
|---|---|---|---|
| **Crazyflie 2.1 + decks** (Bitcraze) | Flow deck v2 = **PMW3901 + VL53L1X**, exactly the two parts on this board (`U6`/`U7`) | **Multi-ranger: 5 × VL53L1X, 4 m, fixed beams** — blind between beams | same sensors, more coverage: the LD06 sweeps 360° continuously at 12 m instead of 5 pencil beams at 4 m |
| **DJI Avata 2 / Neo** | downward **ToF + binocular visual positioning** (closed VIO) | forward binocular only — no lateral sensing | no visual system at all (deliberately — see §2), so darkness-proof; but no indoor position hold either without flow fitted |
| **ArduPilot indoor builds** (forum consensus, Dec 2024) | flow + rangefinder is the standard recipe for non-GPS position hold | usually none, or a front sonar | ours ships avoidance *and* the full non-GPS source matrix (`EK3_SRC*`) pre-arranged |
| **PX4 + LD06** (community thread, Aug 2025) | — | LD06 integration still **not native** in PX4 | ArduPilot has a native `AP_Proximity_LD06` driver — the choice of ArduPilot for this sensor is what makes it drop-in |

Three conclusions the table earns:

1. **The LD06 is the right indoor obstacle sensor, not a compromise.** The ToF ring it
   replaced (8 × VL53L1X at 45° spacing) leaves ~40 % of the horizon blind between 27°
   cones (see the quantified comparison in `docs/SENSORS.md`); Crazyflie's five-beam deck
   has the same geometry problem in miniature. A scanning lidar is what every serious
   indoor platform converges on once size allows — and at 38.59 mm square, size allows
   here. Now £14, it also costs less than the 8-sensor ring + mux + hub it replaced
   (~£30).
2. **What the commercial indoor drones have that this does not is a *position estimate*,
   not sensors.** Avata 2 holds position indoors via visual odometry; this aircraft without
   flow fitted flies manual/AltHold indoors (recorded in `docs/PARTS.csv`). The improvement
   worth adopting is already on the board and deferred for the right reason: **fit PMW3901
   (`U6`) + the downward VL53L1X** — the identical Crazyflie pairing — to gain indoor
   position hold (`VELXY 5` ↔ `FLOW_TYPE`). Note the coupling: flow competes with the
   downward rangefinder for the ONE belly slot (`design.BELLY_SENSOR`) — on this airframe
   the correct indoor pairing is flow in the belly slot + the LD06 feeding avoidance, with
   barometer altitude, or swap the belly slot between flights.
3. **Where this aircraft is genuinely ahead of all of them:** it carries a *bounded,
   radio-based absolute fix* (SoOP Doppler) no consumer drone has, and — unique among the
   DIY field — it was verified by flying the pipeline in SITL before any hardware was
   bought.

---

## 3. Against the SoOP literature — and the two things it changes

| configuration | reported error | receiver | reachable with this £90 chain? |
|---|---|---|---|
| single Iridium satellite, Doppler only | 656 m | static | yes |
| single satellite + azimuth DOA | 289.5 m | static | yes |
| **Iridium NEXT, no elevation aiding** — what `sitl/soop_link.py` models | **180 m** | — | **yes** |
| 4 Iridium + 1 Orbcomm, static | 22.7 m | static | **yes, + a VHF antenna** |
| 4 Starlink + 2 OneWeb + 1 Orbcomm + 1 Iridium | 5.1 m 2-D | **static** | **NO — Ku-band** |
| 3 Starlink + 2 Orbcomm + 1 Iridium, LEO-aided INS | 18.4 m RMSE / 27.1 m final | **moving** (car) | **NO — Ku-band** |
| 4 Starlink + 1 OneWeb + 2 Orbcomm + 1 Iridium, LEO-aided INS | 9.5 m RMSE / 4.4 m final | **moving** (car) | **NO — Ku-band** |
| differential, base station at a known position | 0.60–0.81 m RMSE **(UNVERIFIED)** | — | see 3a.3 |

### 3a. The accuracy ceiling — three corrections after reading the primary sources

**Sources re-read 2026-09-05.** An earlier draft of this section took two figures from
these papers and drew a conclusion the papers do not support. Corrected:

**1. The 5.1 m result is real, and it is unreachable with this aircraft's radio.**
It is genuine measured data — Ohio State, blind receiver, initial estimate 3,600 km from
truth. But Table I of that paper gives the bands:

| | Starlink | OneWeb | Orbcomm | Iridium |
|---|---|---|---|---|
| downlink | **10.7–12.7 GHz** | **10.7–12.7 GHz** | 137 MHz | 1.616–1.626 GHz |
| bandwidth | **240 MHz** | **230 MHz** | 4.8 kHz | 31.5 kHz |
| band | Ku, Ka | Ku | VHF | L |

This aircraft's specified chain is a **1620 MHz patch**, a **SAWbird+ IR** whose SAW is a
60 MHz bandpass at 1620 MHz, and an **RTL-SDR with 2.4 MHz of bandwidth**. Starlink and
OneWeb are off by a factor of ~7 in frequency and ~100 in bandwidth. They are not a
firmware change or a "more complex receiver" — they need a Ku-band dish and LNB and a
wideband SDR. **The previous wording, "the cost is receiver complexity, not a better
antenna", was exactly backwards.**

What *is* reachable: **Iridium + Orbcomm**. Orbcomm is 137 MHz VHF, inside the RTL-SDR's
tuning range, needing only a second cheap antenna — and the same literature already gives
that configuration a figure in the table above: **22.7 m, static**. That is the honest
multi-constellation target for this hardware, not 5.1 m.

**2. 5.1 m is a STATIONARY figure, and this is an aircraft.** The same paper reports
moving-receiver results, which this repo had never cited: **18.4 m RMSE / 27.1 m final**
and **9.5 m RMSE / 4.4 m final** — on a *ground vehicle*, with an **industrial-grade IMU
and an altimeter**, running a LEO-aided INS (STAN), i.e. tightly-coupled inertial fusion
rather than standalone Doppler. Both runs also had GNSS for the first part of the drive
(2.33 km of 4.15 km; 0.11 km of 1.03 km) — which is *architecturally the same* as this
project's mirror-until-denial design, and is the one part that transfers cleanly.

**3. The 0.60–0.81 m differential figure could not be verified and should not be quoted.**
The cited paper is arXiv 2409.05026 (3DPose). Its abstract claims only *"an average
reduction of 90% in 3-dimensional positioning errors compared to the existing differential
Doppler approach"* — **no absolute RMSE in metres, no constellation, no baseline length,
and no statement of whether the receiver moves.** A 90% reduction from a differential
Doppler baseline that other surveys put at *tens of metres within 10 km, under 200 m within
50 km* lands at metres, not decimetres. Until someone reads the results tables and records
the conditions, this row stays marked UNVERIFIED. It is the single most load-bearing number
in the old version of this section and it is the one with the least behind it.

### 3b. Differential SoOP is architecturally available here, and the link can carry it

The differential result needs a second receiver at a **known** position. That rules it out
for a lone aircraft — but **not for this one**, because a ground station is already in the
architecture and the SDR chain is already laptop-side.

The base station's observables have to reach the aircraft. The ELRS 2.4 GHz MAVLink link
carries **1470 B/s**, and a Doppler observable is small — satellite id, Doppler as a float,
a time offset and SNR is about 8 bytes:

| | raw | framed (+35% MAVLink) | share of the link |
|---|---|---|---|
| 4 satellites @ 1 Hz | 32 B/s | 43 B/s | 2.9% |
| 6 satellites @ 2 Hz | 96 B/s | 130 B/s | 8.8% |
| 6 satellites @ 5 Hz | 240 B/s | 324 B/s | 22.0% |

**Bandwidth is not the obstacle.** Six satellites at 5 Hz uses under a quarter of the link
that already exists. This is the single highest-value architectural finding in this review:
it needs **no board change**, and it targets the error term the project had written off.

**What it costs, stated honestly:** it makes the system *differential*, so it depends on a
ground station — which weakens "autonomous GNSS-denied navigation" as a claim. That is a
real trade, not a free win. The defensible framing is that the aircraft degrades to
single-receiver 180 m when the base is out of range, exactly as RTK degrades to
single-point GNSS.

**None of the figures above is a measurement of this hardware.** They are literature, and
they replaced an earlier `[A] 20 m` assumption that flattered the system roughly tenfold.
The ground test in the plan's Phase 1 is what turns 180 m from `[L]` into `[M]`.

---

## 5. Cost, cross-referenced against what you could buy instead

Prices verified 2026-09-05. The board figures come from JLCPCB's own parts library via
the `yaqwsx/jlcparts` mirror (`tools/check_lcsc_stock.py`, 48/48 codes resolved); the
retail comparisons from UK stockists.

### 5a. The flight controller

| | price | what you get |
|---|---|---|
| **this board** | **£189** | 2 assembled + 3 spare bare, panelised Standard. ≈ **£95 per assembled board**, and the spares are already paid for |
| BOM components alone | **USD 63.23/board** | measured from the live library, not a snapshot |
| Matek H743 Slim V4 30×30 | **£84.90** | finished, tested, supported, in stock today |
| Matek H743 Mini V3 20×20 | £93.60 | same |
| SpeedyBee F405 V3 | ~£50 | F4, not H7 — the budget floor |

**A bespoke 6-layer H743 costs about the same per unit as buying the mass-produced
equivalent.** That is the honest headline, and it is a genuinely good result: JLCPCB's
2-assembled/5-bare minimum amortises a one-off run down to retail parity.

**It is not, however, the same value, and the comparison should not be used that way.**
The Matek is a finished product with firmware support, an RMA path and a community that
has already found its bugs. This board is unproven silicon with a five-stage bring-up
procedure, an ArduPilot board ID that is **still unregistered**, and a thermal question on
`U9` that only a thermocouple settles. What the £189 buys that £84.90 cannot is the
`TP9`–`TP11` I/Q pads, the PPS input, the TLE flash and a pinout deliberately identical to
MatekH743 so stock binaries fly it — i.e. the SoOP provisions and the exercise. Bought as
a flight controller it is a wash; bought as the thing the project is *about*, the £104
delta over a Matek is the whole point.

### 5b. The aircraft

| | price | notes |
|---|---|---|
| **this build, Tier 1 (flies)** | **£487** | TBS Source One V5 7in DC, 2806.5 1300 KV, SpeedyBee BLS 60A, 4S 6500 mAh |
| **all four tiers** | **£684** | adds the ToF/lidar suite, tools, and the ~£90 SoOP receiver |
| GEPRC MARK4 LR7 kit | ~$294 | frame + motors + F4 FC only |
| typical 7in long-range build, realistic total | ~$410–490 (≈£330–390) | incl. battery, ELRS, goggles |

**£487 is above a budget 7-inch build, and the reasons are deliberate**: a Source One V5
frame at £35.90 rather than a £25 clone, 2806.5 motors, a 6500 mAh 4S pack, and a custom
FC instead of a £50 SpeedyBee. None of that is waste, but none of it is *cheap* either —
this is a mid-range 7-inch airframe carrying a research payload, not a budget build, and
`docs/BUYING.md` is right to keep Tier 1 separable so the sensor suite can wait.

### 5c. Supply risk, which the price does not show

`tools/check_lcsc_stock.py` now judges **sole-source** parts on an absolute floor rather
than a multiple of this order's need — because "enough for my two boards" is the property
next to the one that matters for a part that cannot be swapped without a respin. Two lines
fail that test while passing the old one:

| part | stock | why it matters |
|---|---|---|
| **STM32H743VIT6** (`C5271084`) | **314** | the MCU. A different package or family is a respin, and this family hit 52-week lead times in 2021–23 |
| **MS5611** (`C15639`) | **1216** | the hwdef and its I²C address assume this exact part |

Neither is a blocker — 314 is 157× this order's need — but both are one modest buyer away
from gone, and neither is substitutable. **Buy spares with the boards, or re-check the
count on the day you order.** Everything else on the BOM is a jellybean.

---

## Sources

- [Holybro Pixhawk 6X (FMUv6X), PX4 Guide](https://docs.px4.io/main/en/flight_controller/pixhawk6x)
- [CUAV Pixhawk V6X, PX4 Guide](https://docs.px4.io/main/en/flight_controller/cuav_pixhawk_v6x)
- [RaccoonLab FMUv6X, PX4 Guide](https://docs.px4.io/main/en/flight_controller/raccoonlab_fmu6x)
- [ArduPilot IMU temperature calibration](https://ardupilot.org/copter/docs/common-imutempcal.html)
- [Iridium NEXT LEO satellites as alternative PNT, Inside GNSS](https://insidegnss.com/iridium-next-leo-satellites-as-an-alternative-pnt-in-gnss-denied-environments-part-1/)
- [Navigation with multi-constellation LEO signals of opportunity, Inside GNSS](https://insidegnss.com/a-look-at-the-stars-navigation-with-multi-constellation-leo-satellite-signals-of-opportunity/)
- [Double-difference Doppler positioning with ephemeris error correction (arXiv 2409.05026)](https://arxiv.org/abs/2409.05026)
- [Positioning using Iridium signals of opportunity in weak signal environments (MDPI)](https://www.mdpi.com/2079-9292/9/1/37)
- [Kilometer-scale GNSS-denied UAV navigation via heightmap gradients, SPRIN-D (arXiv 2510.01348)](https://arxiv.org/abs/2510.01348)
- [gps-denied projects, GitHub topic](https://github.com/topics/gps-denied)
- [Skydio X10D](https://www.skydio.com/x10d)
- [Matek H743 Slim V4, Flying Tech UK](https://www.flyingtech.co.uk/product/matek-h743-slim-v4-30x30-flight-controller/) — £84.90, the direct comparator
- [Matek H743 Mini V3, Flying Tech UK](https://www.flyingtech.co.uk/product/matek-h743-mini-20x20-flight-controller/)
- [Building a $150 7-inch FPV drone, Oscar Liang](https://oscarliang.com/150-dollar-7inch-fpv-drone/)
- [FPV build cost breakdown 2026, UAVMODEL](https://blog.uavmodel.com/fpv-drone-build-cost-breakdown-budget-builds-that-fly-well-in-2026-2026-guide/)
- [jlcparts library mirror](https://yaqwsx.github.io/jlcparts/) — the BOM price and stock source
- [How Skydio 2/2+ Enterprise uses GPS](https://support.skydio.com/hc/en-us/articles/14781375152923-How-does-Skydio-2-2-Enterprise-use-GPS)
- [SLAM technology for GPS-denied UAV navigation (GreyB)](https://xray.greyb.com/drones/slam-gps-denied-navigation)
- [GPS-denied drones (Flyability)](https://www.flyability.com/blog/gps-denied-drone)
