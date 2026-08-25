# NAVCORE-SoOP — what to buy and how to order it

The order sheet, what to check before paying, verified LCSC part numbers, the three
BOM/CPL variants, and the frame/companion research that led to the current choices.
Merged from BUYING.md, BUYING.md, BUYING.md, BUYING.md and
BUYING.md.
**Contains a generated block - see `tools/gen_doc_tables.py`.**

## Everything to do before ordering


Work top to bottom. The board and the drone parts are two separate orders with different
lead times, and one of them has a stock problem that will not wait.

### Blockers — all resolved 2026-09-03

**1. `R6`'s LCSC code: `C25888`.** 37.4 kΩ ±1 % 0402, UNI-ROYAL `0402WGF3742TCE`,
62.5 mW, **6,810 in stock**. LCSC's own search is unreachable from the build
environment; the way in was the **jlcparts dataset** (`yaqwsx.github.io/jlcparts`),
which mirrors JLCPCB's parts library. Confirmed twice — the mirror and
`lcsc.com/product-detail/C25888.html` agree on all five fields.

**2. `BUCK9_PH`: the 9 V buck is DNP.** `POPULATE_VTX = False`.

The decision is not a compromise. The comment that set it to `True` said *"the 9 V buck
used to be DNP because the rail was unrouted; **it is routed now**"* — and that premise is
false. `BUCK9_PH` cannot be closed on this placement (see `docs/ROUTING-TODO.md` for the
measurements). Populating would put **12 parts** onto a regulator whose switch node
reaches nothing: a rail that looks built and cannot work.

Nothing in this build wants it. The FPV camera and VTX are status `LATER` at $0 in
`docs/PARTS.csv` — *"You said no goggles yet"* — and `+9V`'s only other consumer is the
`PV1` test pad. **Today's cost is zero.** Placements go 107 → 95.

**3. 35 mm standoffs, not the kit's 30 mm** — on the order sheet above. With the 9 V buck
DNP, `L5` (3.00 mm, the tallest underside part) comes off and the stack drops 30.3 → 29.6
mm, so the kit's 30 mm would clear by 0.4 mm. That is not room for a cable to leave `J3`.
Buy 35 mm.

### And a stock check that found something

Every one of the **48 LCSC codes** on the BOM was checked against JLCPCB's own library.
All 48 resolve to the right manufacturer part — no wrong codes. Two things came out of it:

- **`C17`/`C18` changed: `C70462` → `C16195875`.** The old part was down to **7 pieces**
  against 2 needed. The replacement is 10 µF **35 V** X7R 1206, 126,626 in stock — and it
  also clears a standing `check_ratings.py` warning, since 25 V on a 16.8 V rail was only
  1.5× and an X7R MLCC loses much of its value near rating. 35 V puts it at 2.1×.
- **`C51940119` (`J3`) is fine.** It is absent from the jlcparts mirror, which looked like
  a problem, but JLCPCB's own part page says *"JLCPCB supports PCB assembly for the
  XY-SM06B-GHS-TB"* — an Extended part, Economic and Standard compatible. The mirror is
  incomplete; JLC is the authority.

### The order

Generated from `docs/PARTS.csv` — this table and the CSV cannot disagree, which is the
point. A hand-written list drifts: two landing-gear rows went on citing the old frame's
16×16 pattern and 3.0 mm bottom plate for a whole pass after the frame changed.

<!-- BEGIN GENERATED ORDER -->
**Tier 1 — Minimum to fly** — 15 lines, ~GBP 487

| # | item | qty | ~GBP | price | source | spec |
|---|---|---:|---:|---|---|---|
| 1 | NAVCORE-SoOP PCB + assembly | 1 order | 190 | quoted | JLCPCB | [M] |
| 2 | TBS Source One V5 7in DC | 1 | 36 | quoted | HobbyRC UK | [D] |
| 3 | Motors 2806.5 1300KV | 4 | 60 | quoted | AliExpress | [D] |
| 4 | Props 7040 or 7042 | 4 sets | 14 | ~est | AliExpress | **[A]** |
| 5 | SpeedyBee BLS 60A 4-in-1 ESC | 1 | 48 | quoted | AliExpress | [D] |
| 6 | RadioMaster Pocket ELRS transmitter | 1 | 68 | quoted | AliExpress | **[A]** |
| 7 | ELRS 2.4GHz receiver | 1 | 15 | quoted | AliExpress | **[A]** |
| 8 | XT60 pigtails + silicone wire + heatshrink | 1 kit | 12 | ~est | AliExpress | **[A]** |
| 9 | EC5 to XT60 adapter | 2 | 6 | ~est | AliExpress | **[A]** |
| 10 | Landing gear - TPU/nylon skids, BOUGHT (backup for the printed set) | 1 set | 8 | ~est | AliExpress | [M] |
| 11 | M3x14 socket screws (motor) | 16 | 3 | ~est | AliExpress | **[A]** |
| 12 | microSD card, 32GB | 1 | 8 | ~est | AliExpress / anywhere | **[A]** |
| 13 | M3 aluminium standoffs 35 mm | 4 | 3 | ~est | AliExpress | [M] |
| 14 | XIAO ESP32S3 Sense (recording camera) | 1 | 14 | ~est | AliExpress | [D] |
| 15 | Camera power: thin silicone wire + 2-pin JST pigtails | 1 kit | 2 | ~est | AliExpress | [M] |

**Tier 2 — Sensors - optional for first flight** — 4 lines, ~GBP 76

| # | item | qty | ~GBP | price | source | spec |
|---|---|---:|---:|---|---|---|
| 16 | M10 GNSS + QMC5883L compass (antenna INTEGRATED) | 1 | 24 | quoted | AliExpress | [D] |
| 17 | Benewake TFS20-L lidar | 1 | 32 | quoted | AliExpress (or 3DXR UK GBP35.70) | [D] |
| 18 | VL53L1X ToF module (GY-53-L1X) | 1 | 6 | quoted | AliExpress | **[A]** |
| 19 | LDROBOT LD06 360 lidar (INDOOR USE ONLY) | 1 | 14 | quoted | eBay - Okdo Lidar Hat kit (use the LIDAR UNIT only) | [D] |

**Tier 3 — Tools and bench kit - buy once** — 6 lines, ~GBP 31

| # | item | qty | ~GBP | price | source | spec |
|---|---|---:|---:|---|---|---|
| 20 | 5V PASSIVE piezo buzzer | 1 | 3 | ~est | AliExpress | [M] |
| 21 | WS2812B LED strip | 1 | 6 | ~est | AliExpress | [M] |
| 22 | ST-Link V2 programmer | 1 | 4 | ~est | AliExpress | **[A]** |
| 23 | Pogo pins or 0.1mm enamelled wire | 1 | 5 | ~est | AliExpress | **[A]** |
| 24 | Smoke stopper (XT60) | 1 | 10 | ~est | AliExpress | **[A]** |
| 25 | USB-C cable, data-capable | 1 | 3 | ~est | anywhere | **[A]** |

**Tier 4 — SoOP receiver - proves the thesis, needs no board respin** — 4 lines, ~GBP 90

| # | item | qty | ~GBP | price | source | spec |
|---|---|---:|---:|---|---|---|
| 26 | Nooelec SAWbird+ IR (1620MHz LNA+SAW) | 1 | 35 | quoted | Nooelec | [D] |
| 27 | Nooelec 1620MHz Iridium patch antenna | 1 | 25 | quoted | Nooelec | [D] |
| 28 | RTL-SDR (R820T2 tuner) | 1 | 30 | quoted | AliExpress / RTL-SDR Blog | [D] |
| 29 | gr-iridium + iridium-toolkit (software) | 1 | 0 | quoted | GitHub (muccc) | [D] |

**TOTAL 29 lines, ~GBP 684.** Tier 1 ~GBP 487. Tier 2 ~GBP 76. Tier 3 ~GBP 31. Tier 4 ~GBP 90.

**Cheapest path to a flying aircraft is Tier 1 alone: ~GBP 487.** Tier 2 is the ToF/lidar sensor suite, which nothing in Tier 1 depends on - `PRX1_TYPE` and every `RNGFNDn_TYPE` ship at 0, so the aircraft flies without them and does not even notice they are absent. Tier 3 you buy once and keep.

Two separate columns, because they are two separate questions. **price** `quoted` means the link goes to a real product listing; `~est` means it goes to a search page and the number beside it is an estimate nobody has checked. **spec** **[A]** means the part's specification is assumed rather than sourced. A line can be quoted-but-assumed or estimated-but-datasheeted; conflating them hides which number to go and verify.

`tools/check_purchase.py` asserts every interface between two of these parts and names the ones still resting on an assumed source.

Held back (10): Radxa Zero 3W (1GB) (~GBP 18), 3.3V LDO, SOT-23 (~GBP 1), Global-shutter camera (OV9281) (~GBP 0), 22-pin CSI camera cable (~GBP 0), VL53L1X ToF modules x8 (~GBP 24), TCA9548A I2C multiplexer (~GBP 2), MCU sensor hub (RP2040 or Arduino Nano) (~GBP 4), Landing gear - carbon rod legs for payload (~GBP 10), FPV camera + VTX + UVC receiver (live video to laptop) (~GBP 38), Soft-case 4S drone LiPo (~GBP 45)

Generated from `docs/PARTS.csv` by `tools/gen_doc_tables.py`; do not edit it here. Change a part's `Status` in the CSV to move it in or out.
<!-- END GENERATED ORDER -->

---

### 0. What has already been verified — 2026-09-02

The full record, including what each check *cannot* prove, is in
**[VERIFICATION.md](VERIFICATION.md)**. In short:

- **479/479 connections, 0 blocking DRC errors, 0 unconnected pads, 0 ERC violations, 0 schematic-parity issues.** Full-severity DRC still reports 22 accepted/documented findings; do not describe that as literal zero violations.
- **0 rating failures across all 50 BOM lines** — every capacitor rated for its net,
  dielectrics checked, inductor currents checked, terminals verified to land on their pads.
- **Eight checks gated** in `tools/preflight.py`; `check_placement` reports without blocking.
- **56.11 mm of orphaned copper removed**, connectivity proven unchanged — including an
  8.84 mm `VBAT` orphan, a `BUCK_PH` switch-node stub, and the `USB_DM` via that made the
  USB pair asymmetric.
- **Silk violations 42 → 7**; every movable reference designator is legible.
- **Every 3D model now resolves** — 95 footprints pointed at files that do not exist on
  this machine, so both power inductors were missing from every STEP and GLB export.
- **`U6`'s exposed pad windowpaned** to 65.8% paste coverage; verified paste-only.

What remains open, and what needs parts in hand, is in VERIFICATION.md §7.

---

### Board status — READY TO ORDER, 2026-08-31

`tools/preflight.py`: **0 blocking failures, 1 warning.** It gates 0 blocking DRC errors, fitted-net connectivity, ERC and schematic parity. Full-severity DRC has accepted/documented findings; BOM and CPL were regenerated from the final board.

Five defects were found and fixed since the last revision of this section, all of them
things that would have reached the fab:

| defect | fix |
|---|---|
| `J1` and `J2` fitted facing INTO the board — `J1` fatally, no cable could be plugged in | both rotated; verified facing off-board and confirmed on a render |
| `L2`/`L5` on 1210 lands holding a 4.0 × 4.0 × 3.0 mm part — neither fitted | `L2` moved to the top on a 4 × 4 land, 4.39 mm from `U8`'s PH pin and on the same side, so the switch node no longer crosses the board |
| `U1.49` (an MCU VSS pin) and `C25.2` not connected to the ground plane | `U1.49` via-in-pad; the whole buck south side re-planned, all three COMP/FB ground pads now have a via within 0.6 mm |
| six capacitors with the wrong package or under-rated for their net, incl. 16 V parts on 16.8 V VBAT | `PASSIVE_LCSC` re-keyed on (value, footprint); correctly rated parts sourced and verified |
| the 9 V VTX buck documented DNP but all 17 parts populated — and listed in the CPL | marked DNP in `design.py`; `gen_bom.py` now excludes DNP parts from the CPL |

**Two deliberate design decisions came out of this:**

- **The Pi runs from its own BEC.** At 700 mA it was 37 % of the 5 V rail and put `L2` at
  118 % of its current rating, and no 4 × 4 mm 10 µH part carries more. The rail is now
  1.19 A, 74 % of the inductor. It is better practice regardless — a Linux SBC's load
  transients do not belong on the flight controller's own buck — and was already
  mandatory for a Pi 5.
- **The 9 V VTX buck IS populated by default** as of this revision. It was DNP while the
  rail was unrouted; `+9V` is routed now and `L5`'s FNR4030 fits its 1210 land. The
  default `fab/BOM-NAVCORE-SoOP.csv` and its CPL include all 17 parts; use
  `python3 tools/gen_bom.py --no-fpv` for a build without video. The underside goes
  2.30 → **3.00 mm** (`L5`), which still clears the ESC.

  **The rail carries 0.30 A, measured — a 200–250 mW VTX, not a 500 mW one.** Raising it
  was attempted and failed: the artery is a 12.85 mm run at 0.15 mm on In3.Cu, boxed in
  by a `VBAT` via at 0.20 mm and GND vias at 0.32–0.48 mm, so it cannot exceed 0.189 mm;
  no parallel corridor exists at any x from 124–134 mm on either outer layer; and a
  rip-and-reroute reverted at 43–48 violations twice. A 500 mW carrier needs the region
  around x≈129.7, y=104–117 relaid — a job for any future respin. See `design.NET_CURRENT` for the
  full evidence.

- **`U6` (PMW3901 flow) and `U7` (VL53L1X ToF) are NOT populated.** Both are on the
  underside with the ESC 3.0 mm below them, so neither can see the ground —
  `check_mechanical.py` now proves this. Neither was ever enabled: `FLOW_TYPE 5` is
  MAVLink (the Pi camera), and both `RNGFND*_TYPE` ship 0. Leaving them off saves ~$9.88
  a board, drops the BOM's only real supply risk (PMW3901, 424 units falling ~57/day) and
  its X-ray inspection requirement, and frees I2C 0x29 for the upward-facing module
  `docs/PARTS.csv` already depends on. Flip `design.POPULATE_BLIND_SENSORS` to fit them.

Known and accepted: `J3` has 5.30 mm of plug clearance against a 6.0 mm nominal — measure
the real plug. (This used to also list `C25` at 3.81 mm from `U8.6`; that part **no longer
exists** — the COMP network was deleted because the TPS54202 compensates internally.)
The full list, with reasons, is in [VERIFICATION.md](VERIFICATION.md).

Run `python3 tools/preflight.py` to reproduce all of this.

#### Electrical and connectivity
| | |
|---|---|
| Connections | **479/479**, no unrouted nets (re-verified after the connector rotation) |
| DRC | **0 errors**, 0 schematic-parity issues |
| Every pad has a net, every net two endpoints | checked; the 40 unconnected pads are all genuine NC |
| Power copper vs current | IPC-2221 cut analysis, tightest is `VBUS` at 0.5 A |
| Dividers, decoupling, pull-ups, crystal load | `check_electrical.py` |
| Pin direction / reset level / peripheral role | `check_pin_semantics.py` |
| Parameters exist in the target firmware | 55/55 against Copter-4.7.0, plus a live read-back from a running build |

#### Signal integrity — checked, and the limits were re-derived
`tools/check_traces.py`. A first version used round-number limits and flagged six nets;
every one dissolved under analysis, so the limits are now derived from signal physics
(~150 mm/ns in FR4, and a trace matters when its delay nears a sixth of the rise time).

| net | length | verdict |
|---|---|---|
| USB D+/D− skew | 4.55 mm | **30 ps — 0.03 % of a 12 Mbps bit.** Irrelevant at full speed |
| `I2C1_SDA` | 62.0 mm | ~6 pF against a 400 pF bus limit. Irrelevant |
| `SWCLK` | 53.5 mm | 0.36 ns against a ~5 ns edge. Irrelevant |
| `SPI3_SCK` | 36.0 mm | 0.24 ns against a ~2 ns edge. Fine |
| **`OSC_IN` / `OSC_OUT`** | **13.3 / 11.6 mm** | the only one worth watching — ~1.8 pF stray against the 5.0 pF budget already assumed for the 20 pF crystal. **Inside budget**, but longer than the <10 mm ideal. Watch at bring-up |

**0 nets over limit.** No trace is misrouted or the long way round.

#### Mechanical — measured against a 30×30 stack
| | |
|---|---|
| Mounting holes | **30.50 × 30.50 mm**, 4 off, **4.00 mm** diameter — standard 30×30, sized for M3 with silicone grommets |
| Board outline | 45.10 × 46.10 mm, rounded corners, closed |
| Bottom-side height | **2.30 mm max** (`D1` TVS) on the base build; **3.00 mm** (`L5`) with the FPV buck populated — both clear the ESC below with normal standoffs |
| Top-side height | 4.4 mm (`J3` JST-GH), then USB-C at 3.2 mm |
| USB-C | 0.80 mm from the top edge — plug inserts from outside the stack |
| ESC connector `J2` | 0.80 mm from the left edge |
| GPS `J3` | 3.64 mm inboard, but it is a **top-entry** connector, so that is fine |
| microSD `J8` | bottom side, slot faces the bottom edge, **1.62 mm inboard** |

**Checking this against a frame — and a correction.** An earlier version of this document
said "the centre plate must accept 46.1 mm". **That framing was wrong.** A 30×30 stack does
not sit inside a plate; it bolts to four standoffs at 30.5 mm centres and overhangs them:

| | size | overhang per side |
|---|---|---|
| SpeedyBee FC | 41.6 × 39.4 | 5.6 / 4.4 mm |
| SpeedyBee ESC | 45.6 × 44.0 | 7.6 / 6.8 mm |
| **NAVCORE-SoOP** | **45.1 × 46.1** | **7.3 / 7.8 mm** |

So the real question is whether a **corner** fouls an arm root or a standoff — and the
frame must already clear the ESC, since the two are bought together. Corner to corner our
board is **64.5 mm against the ESC's 63.4 mm: 1.1 mm larger**, or 0.55 mm per corner.

That is a small demand, not the show-stopper implied earlier. Still worth a look:

- [ ] with the ESC in place, is there ~1 mm of spare clearance at each corner?

**Two frames whose specs were actually read, not assumed:**

| | wheelbase | weight | stack mounting | prop gap |
|---|---|---|---|---|
| **TBS Source One V5 7″ DC** | 320 mm | 143.5 g | **30.5×30.5 + 20×20** | +48.5 mm |
| **MARK7 V2 7″ true-X** | 295 mm | 148 g | **30.5×30.5 + 20×20 (M3)** | +30.8 mm |

Both: 2.5 mm bottom plate, 2 mm top and middle, 6 mm arms. Both clear 7-inch props
comfortably, and both publish the 30.5 × 30.5 M3 pattern this board is drilled for.

The AliExpress listing originally linked here was **never verified** — those pages render
entirely in JavaScript and return an empty shell to any fetch, with bot-detection markers.
It may well be fine; it simply was not checked, and should not have been presented as if
it had been.
- [ ] nothing blocks the **bottom edge**, or you will have to unstack the board to change
      the SD card — and the SD card holds both your logs and any Lua scripts

#### Fabrication outputs
14 gerbers, all metric and properly terminated; 6 copper layers in L1→L6 order; drill file
889 holes across 6 tools, **smallest 0.200 mm** against JLCPCB's 0.15 mm 6-layer minimum.

---

### 0b. What the whole-aircraft pass changed — 2026-08-28

`tools/check_build.py` checks the build as an assembly rather than as a pile of verified
parts: connectors, power budget, current path, mass and thrust, geometry, buses. **38
checks, 6 areas, all passing**, with every value tagged for where it came from.

It found four things no board-level check could see:

| finding | consequence |
|---|---|
| **`BATT_AMP_PERVLT` was ~2x wrong** | ESC publishes `Scale=400` = 40 mV/A → **25.0**, not the 52.7 taken from a different SpeedyBee stack. This board feeds the ADC with no divider, so the ESC's figure governs. Battery failsafe and consumed-mAh would have read half the truth |
| **No microSD card in the list** | it holds the logs *and* every Lua script |
| **No USB-C cable in the list** | the only way to flash the board |
| **Motor bolt pattern is M3 19×19, not 16×16** | **buy 19×19 landing skids**, and M3×14 screws to clear the 6 mm arm plus a 3.5 mm skid |

#### The IMU shortage turned into an upgrade

`ICM-42688-P` is out of stock. `AP_InertialSensor_Invensensev3` drives eight parts sharing
this board's exact footprint (`LGA-14_L3.0-W2.5-P0.50-TL`):

| part | LCSC | stock | US$ | |
|---|---|---|---|---|
| **ICM-45686** | `C22459454` | **6,828** | **11.84** | **newer, lower noise, cheaper than the part it replaces** |
| ICM-42670-P | `C3288646` | 7,695 | 2.20 | cheapest; lower spec |
| ICM-42688-P | `C1850418` | **OUT** | 17.96 | the current BOM line |

`SPI:icm45686` appears in 25 shipping ArduPilot board definitions. Substituting is two
lines — `design.py` and the hwdef `IMU` line — and no PCB change. Full detail in
`docs/BUYING.md`.

#### Two things are NOT verified, and are marked so

- **The indoor ToF ring's software path is UNTESTED, not broken.** An earlier draft of
  this document marked it `BLOCKED` on the strength of `PRX1_TYPE 2` reporting `PRX1: No
  Data`. That conclusion was wrong. The decisive test was `PRX1_TYPE 10` — the **SITL
  backend, which generates its own data and needs no incoming messages** — and it fails
  identically. Proximity cannot be exercised in this SITL setup by any route, so none of
  the failures said anything about the hardware or the MAVLink encoding.

  **A test that cannot pass is not evidence of failure.** The ring is back to `CONSIDER`:
  the parts are verified, the path is simply unproven here. Prove it on the bench with one
  sensor before buying eight.
- **The flow altitude ceiling behaves differently than first described.**
  `AC_Avoid.cpp:459` is its only enforcer, so `AVOID_ENABLE 0` means *no ceiling at all*,
  and a `GUIDED` command bypasses it entirely. See `docs/SENSORS.md`.

#### Provenance

`docs/PARTS.csv` now carries a **Provenance** column: `MEASURED` from this design,
`DATASHEET`, `LISTING`, `OWNED`, or `ASSUMED`. Twelve lines are verified against a real
source; the rest are commodities where the spec barely matters — wire, screws, a buzzer.
It makes visible exactly which claims rest on something checkable.

---

### 1. Order the PCB first — two parts are running out

**This is the one time-critical item.** Checked 2026-08-28, two days after the previous
capture:

| Part | Then | Now | Do |
|---|---|---|---|
| STM32H743VIT6 `C114409` | 1546 | **out of stock** | **switch the BOM to `C5271084`** (same silicon, tape-and-reel, in stock, *cheaper* at ~$7.66) |
| ICM-42688-P `C1850418` | 3920 | **out of stock** | check JLCPCB's own library at upload; if out, fly on `U3` alone |

JLCPCB assembly draws on **JLCPCB inventory, not LCSC**, and their BOM upload flags
unavailable parts authoritatively. That check is the real answer, and you can only do it by
uploading.

#### Files to upload

| | |
|---|---|
| Gerbers | `fab/gerbers/` — zip the whole folder |
| BOM | `fab/BOM-NAVCORE-SoOP-economic.csv` |
| CPL | `fab/CPL-NAVCORE-SoOP-economic.csv` |

Order settings: **6 layer, 1.6 mm, ENIG, 1 oz outer copper, 5 PCBs, 2 assembled, Economic**.
The `-economic` files already mark `U3`/`U6`/`U7` as DNP.

#### Check these at upload, on screen

- [ ] **Board renders at 45.1 × 46.1 mm** with four mounting holes and rounded corners
- [ ] **CPL orientation preview** — this is the third independent check on rotations, after
      the formula and `tools/check_cpl.py`. Spot-check `U1` pin 1, `J1` USB-C, and any
      polarised part against `docs/img/pin1-top.svg` / `pin1-bottom.svg`
- [ ] **No unavailable parts flagged.** If `C114409` or `C1850418` are flagged, apply the
      substitutions above before paying
- [ ] Confirm **1 oz outer copper** — the current-capacity analysis assumes it, and 0.5 oz
      would halve the margin
- [ ] Smallest drill is 0.200 mm; confirm their 6-layer minimum is 0.15 mm as expected

---

### 2. Order the drone parts

All links are in `docs/PARTS.csv`. Lead times from AliExpress run 2–4 weeks, so place this
at the same time as the board.

#### Decide these three before ordering

**Rangefinder — do you want the TFS20-L (~£25–36)?**
Yes if you want optical flow to work outdoors over grass at all. The fitted VL53L1X manages
3.6 m and about a third useful returns over pasture. See `docs/SENSORS.md`. It is 3.3 V
and `J3.1` is 5 V, so add the inline LDO.

**Upward ToF (~£5)?** Yes if you will fly indoors. 4 m is adequate at the 2–3 m/s you fly in
a room, and ceilings are what a downward-looking aircraft is blindest to. Works *only*
because `U7` is unpopulated, freeing I²C address 0x29.

**Camera (~£40)?** Needed for the Pi optical-flow path. **Get a 60–90° lens, not the 130°
fisheye** that comes up first — the distortion has to be modelled or your flow vectors are
wrong at the edges, and a wrong flow vector flies the aircraft away. The M12 mount means
the lens is swappable if you get it wrong.

#### Do not buy yet

- ~~**LD06 lidar.**~~ **RESOLVED 2026-09-05 — move it to the buy list.** The price was
  corrected to ~$99–131 on 2026-09-04, but the Okdo Lidar Hat + Bracket Development Kit on
  eBay (**£13.99**, item 395159855374, >1000 sold) contains the genuine LD06 as a separate
  module plus a Pi HAT and bracket. The value objection dies at £14; the physics objections
  do not: 12 m at 10 Hz still only protects to ~5 m/s on a 15–20 m/s aircraft, and 25 klux
  still bans outdoor use (swap to LD19/STL-19P for that). Buy the kit, use the LIDAR UNIT
  only, and leave the HAT off the aircraft — see the resolved line in `docs/PARTS.csv`.
- **Any sideways ToF ring.** See `docs/SENSORS.md` — six sensors leave 25–55 % of the
  horizon blind, and commercial machines use cameras for this, not ToF.
- **VL53L5CX.** ArduPilot has no driver for it.

---

### 3. Before the parts arrive — free, and it is the highest-value work

**Run the SITL suite.** `sitl/run_scenarios.sh` flies the board's own `defaults.parm`
against simulated truth. It has already found five faults that would have grounded or
misled the real aircraft. Nothing here needs hardware.

- [ ] `./run_scenarios.sh` — one clean post-fix full run; targeted canary, SoOP GPS, DR and RC-loss runs now pass, but the full-suite gate remains pending
- [ ] `./run_scenarios.sh --params` — every shipped parameter real and settable
- [ ] Write the Pi-side MAVLink bridge against `docs/SENSORS.md` and test it in SITL
- [ ] Read `docs/BUILD.md` end to end **before** the board arrives, not after

**The three hard requirements on the Pi**, all measured, all in `docs/SENSORS.md`:

1. Publish `GPS_INPUT` at **5 Hz**, interpolated up from the ~1 Hz Doppler solution
2. Use **`gps_id = 1`** and **`GPS2_TYPE 14`** — not `GPS_TYPE2`, which does not exist
3. Agree with the live GPS to within **50 m** on the ground, or it will not arm

---

### 4. Known-good but unverifiable until hardware exists

Recorded so they are decisions rather than surprises:

- **1 oz outer copper, confirmed at order** — every current current figure halves at 0.5 oz; the `+9V` rail is already at its 0.30 A ceiling, so a 0.5 oz ship would halve that headroom
- **Skid drop (25 mm) and camera module depth (12 mm)** — both `[A]` figures; together they decide whether the camera lens sits above the skid contact line. The carbon-rod legs (~60 mm) remove the depth question entirely if the TPU skids are shallow
- **Skid thickness (`[A]` 3.5 mm)** — sets the motor screw length: M3×14 today; M3×12 or M3×16 if it differs. `tools/fasteners.py` derives this from the stack
- **Camera mount and ribbon reach** — no mount exists yet; the 22-pin CSI bend radius is unmeasured
- **Frame standoff spacing** — absent from the listing and the manual
- **Radxa Zero 3W mounting holes and connector keep-outs** — Radxa publishes the 65 x 30 mm envelope and NOTHING else. The hole pattern is unknown: resellers claim it matches the Pi Zero, but their one figure (61 mm diagonal) does not match the Pi Zero's 62.4 mm. MEASURE THE BOARD before cutting a tray. Camera and CSI cable are DEFERRED - optical flow is not fitted in this build (see docs/BUILD.md Stage 5)
- **`J3` plug against 5.30 mm clearance** — the one connector warning left; measure the plug before ordering
- **ESC cable continuity** — `J2` matches Betaflight's documented SpeedyBee F405 V4 order; verify the cable you get
- **`BATT_AMP_PERVLT`, `FLOW_ORIENT_YAW`** — bench calibration items
- **Motor thrust (`[A]` 1250 g)** — the only `[A]` every payload figure inherits
- **LCSC stock, captured 2026-08-23** — Standard drops Economic's 100%-in-stock rule, but a missing part still stops the order
- **ArduPilot board ID 9001** — unregistered upstream; harmless in SITL, but register before flashing
- IMU orientations — asserted in the hwdef, never measured
- Grommet flange diameter, USB differential impedance
- **The board arrives with only 14 of 38 pads labelled.** Print `docs/img/padmap.svg`

---

### Assembly tier and panelisation — decided

**Standard PCBA, panelised 2 × 2.**

This board is **45.1 × 46.1 mm** and JLCPCB Standard assembly has a **70 × 70 mm minimum**
(Economic is 10 × 10). A 2 × 2 panel is roughly **93 × 95 mm**, comfortably over it.

**Specify "panel by JLCPCB", 2 × 2 — do not commit a panelised board file.** The board
files stay exactly as verified, so nothing has to be re-checked. A hand-panelised
`.kicad_pcb` would have to go through DRC, connectivity and the whole gate again for no
benefit.

Standard places **everything**, including `U3` (LGA-14) — so nothing is left for you to
hand-solder. That is the main reason to pay for it: an LGA-14 has no accessible leads and
genuinely needs hot air or a stencil, which is a much harder proposition than the 0402s.

**Confirm with JLC before paying:**

| question | why it matters |
|---|---|
| Does the 70 × 70 minimum apply to the **panel** or the individual board? | If the individual board, Standard is not available at all and the tier decision reopens. |
| Does JLC add **edge rails**, and are they included in the panel size? | Rails change the panel dimensions and the price. |
| Is **1 oz outer copper** what ships? | Every current figure in `check_power_cut.py` halves at 0.5 oz — including the `+9V` rail already at its 0.30 A ceiling. |
| Are all 52 BOM lines **in stock**? | Captured 2026-08-23. Standard drops Economic's 100%-in-stock rule, but a missing part still stops the order. |

---

## Before you spend money


Researched 2026-08-28. Stock, prices and JLCPCB's terms move; re-check the starred items.

### The finding that changes the order

**Three parts are flagged "Standard Only" on JLCPCB and cannot go on an Economic
assembly order:**

| part | ref | why it matters |
|---|---|---|
| `ICM-42605` (C2655099) | U3 | second IMU |
| `PMW3901` (C43496881) | U6 | optical flow — X-ray inspection also required |
| `VL53L1CXV0FY/1` (C190004) | U7 | rangefinder |

Everything else is "Economic and Standard", including the STM32H743, the ICM-42688-P,
the MS5611 and the W25Q128.

**And Standard PCBA has a 70 × 70 mm minimum board size.** This board is 45.1 × 46.1 mm,
so Standard needs the board **panelised with breakaway rails** to clear 70 × 70. JLCPCB's
own capabilities page gives Standard as "70×70mm – 460×500mm" single or panelised, with
edge rails marked necessary; Economic is "10×10mm – 470×500mm" with no rails needed.
Minimum order is 2 for both.

### What it costs, in GBP

Two assembled boards, USD→GBP at 0.732. Parts are **$59.01/board**, of which **$19.85**
is the three Standard-only parts.

| | A — panelise, Standard | B — Economic + hand-fit | C — Economic, omit all three |
|---|---|---|---|
| parts | £86 | £57 | £57 |
| the three parts, bought separately | — | £29 | — |
| LCSC separate shipping | — | £11 | — |
| extended-part feeder fees | **none** | £46 | £40 |
| 6-layer PCB, 5 pcs | £48 (70×70 panel) | £29 | £29 |
| assembly setup / labour | ~£37 * | £6 | £6 |
| shipping | £18 | £18 | £18 |
| **order total** | **£189** | **£197** | **£150** |
| reusable tools needed | none | +£85 | none |
| **first-time total** | **£189** | **£282** | **£150** |

\* the one real estimate in the table. JLCPCB's quote tool is the arbiter — upload and check.

**Economic is not cheaper.** It charges ~£46 in per-part feeder fees ($3 per extended BOM
line, ~21 lines) that Standard does not, and it forces a second order from LCSC with its
own shipping for the three parts. Option C is genuinely cheapest, but it gives you one
IMU, no optical flow and no rangefinder — no GNSS-denied work, which is what the board
is for.

### Recosted, and the thing that resolves it

The tool estimate above was too high — a hot air station is ~£30, paste ~£3, flux ~£4, so
**£37, not £85**. And only **one** board needs the three parts fitted, not two.

**JLCPCB's minimum is 2 assembled and 5 bare PCBs, so you get a spare assembled board and
three bare ones whatever you do.** That is not waste — it is the practice piece and the
insurance, and it is already paid for.

| | cost |
|---|---|
| Economic order, three parts left off | £150 |
| three parts × 2 sets (one spare of each) | £29 |
| LCSC shipping | £11 |
| hot air, paste, flux | £37 |
| **hand-fit route, first time** | **£227** |
| option A, panelised, everything placed | £189 |
| never fit them at all | £150 |

#### On ruining parts

Worth being specific, because the fear is doing more work here than the risk deserves:

- **A set is £15.** Two spare sets is £29. That is the whole exposure, and it is bounded.
- **LGA parts survive repeated reflow.** The usual outcome of a bad attempt is *not
  soldered*, not *destroyed* — you clean, re-paste and go again. Both `U3` and `U7` are in
  that category.
- **Only `U6` is genuinely fragile**: the PMW3901 is chip-on-board with a plastic lens.
  `docs/LAYOUT.md` already said to fit it last by hand with Sn42Bi58 low-temp paste, for
  exactly this reason. That advice predates this discussion and still stands.
- **Practise on `U3` first.** The second IMU is optional — ArduPilot flies on `U2` alone —
  so if you destroy it you have lost £6 and nothing you previously had.

#### The order you can place today

**Recommended: Economic assembly with U3, U6 and U7 DNP.** Upload the matching
`fab/BOM-NAVCORE-SoOP-economic.csv` and `fab/CPL-NAVCORE-SoOP-economic.csv` together.
If JLCPCB rejects the selected parts or the quote is materially worse, use the unsuffixed
Standard/panelised BOM/CPL pair instead.

**`B` and `C` need identical files.** Both are an Economic order with `U3`, `U6` and `U7`
left off; the only difference is whether you later fit them by hand. So ordering does not
commit you to the soldering. Place the £150 order, get the boards, practise hot air on the
spare, and decide about the sensors when you have a feel for it — the board flies GPS-only
in the meantime, and the flow and rangefinder are for low-altitude hold, not for getting
airborne.

`fab/BOM-NAVCORE-SoOP-economic.csv` and `fab/CPL-NAVCORE-SoOP-economic.csv` are the
recommended files. The full-assembly pair without the `-economic` suffix is what the
Standard/panelised route would use.

### Cutting the cost further

| lever | worth | notes |
|---|---|---|
| **New-customer coupons** | up to ~£19 | JLCPCB gives new accounts a $123 pack; the ones that apply here are **$6 PCB**, **$10 SMT**, **$10 shipping** (min $15 shipping). Their help page says coupons cannot be merged and are "once per batch", so assume **one per order** — take the $10 SMT. |
| **Monthly SMT coupon** | ~£7 | $6 and $9 SMT coupons are issued at the start of each month for orders over $1. Don't order on the 28th if a fresh one lands on the 1st. |
| **6-layer promotion** | up to ~£22 | JLCPCB run a recurring $30-off 6-layer offer. Worth waiting for if you are not in a hurry. |
| **Shipping choice** | ~£10 | Global Standard Direct Line instead of DHL. Slower, and the board is not urgent. |
| **Drop the second IMU** | ~£13 | `U3` ICM-42605 is genuinely optional — ArduPilot flies on one IMU. This is the only part you could omit without losing a capability, since IMU1 (ICM-42688-P) is the better sensor anyway. Costs you redundancy. |

Realistically **£150–165 for option A** with a coupon and economy shipping.

### The cost not in the table: UK import VAT

An order at this value attracts **20% UK import VAT**, and above £135 the courier collects
it on delivery and adds a handling fee (typically £8–12). Budget roughly **+£45 on option
A**. This is unavoidable and is not JLCPCB's charge — but it is real money and it is easy
to forget when comparing against a UK-stocked alternative.

### Still to do before ordering

**Blocking**

1. **Decide A / B / C**, then produce the matching outputs. Option A needs a panelised
   gerber set — board plus breakaway rails to ≥70 × 70 mm. Options B and C need `U3`,
   `U6`, `U7` marked DNP in the assembly BOM while staying on the board.
2. **Upload to JLCPCB's quote tool and read back the real numbers** — the Standard
   setup/labour figure above is my estimate, and their tool also previews CPL orientation.

**Worth doing, not blocking**

3. **Look at the gerbers as gerbers.** Everything so far has checked the board through
   KiCad's own model. Render each exported layer and eyeball it — a wrong layer mapping in
   the export is invisible to every check in `tools/`.
4. **Confirm the BOM and CPL column headers** match what JLCPCB's importer expects.
5. **Register `APJ_BOARD_ID 9001`** with ArduPilot. Not needed to order, but needed before
   sharing the design, and the request takes time.

**Verified, no action**

- Stock is stable: PMW3901 424 (unchanged in five days), ICM-42688-P 3920, VL53L1X 5732.
  PMW3901's price rose from $4.96 to $5.98.
- Solder paste apertures are complete on every fine-pitch part. The only pads without
  paste are `J1`'s four through-hole shield tabs and two NPTH mounting holes — correct.
- Only one part has through-hole pads at all (`J1`), so nothing needs hand-soldering for
  that reason.

### On the bench, after it arrives

- Flash the bootloader over **SWD before USB** — USB does not power this board.
- Continuity-check the ESC cable against `J2`'s pin order (`1 GND, 2 VBAT, 3-6 M1-M4,
  7 CUR, 8 TEL`).
- Calibrate `BATT_AMP_PERVLT` (ships at 52.7) and check `FLOW_ORIENT_YAW`'s sign.

---

## NAVCORE-SoOP — verified JLCPCB/LCSC sourcing


Checked against jlcsearch.tscircuit.com on 2026-08-23. Stock/price are point-in-time;
re-check before ordering. `PREF` = JLCPCB Preferred, `BASIC` = Basic (no setup fee).

> **This data is stale and must be re-checked at order time.** Two things it decides that
> nothing else in the repo does: whether a part is in stock at all, and whether it is
> Basic/Preferred or **Extended** — an Extended part carries a per-feeder setup fee, so a
> BOM that quietly drifts toward Extended parts gets more expensive without any warning
> from the design tools. The generated `fab/BOM-*.csv` carries **only** LCSC codes and no
> stock or classification, by design: a number cached in a CSV would look authoritative
> and be wrong. Check the codes against LCSC on the day you order.

### Core board (all confirmed in stock)

| Block | Part | LCSC | Pkg | Stock | US$ | Note |
|---|---|---|---|---|---|---|
| MCU | STM32H743VIT6 | **C114409** | LQFP-100 14x14 | 1742 | 9.41 | 2MB flash / 1MB RAM |
| IMU1 (SPI1) | ICM-42688-P (TDK) | **C1850418** | LGA-14 2.5x3 | 3920 | 17.01 | genuine; see IMU note |
| IMU2 (SPI4) | ICM-42605 (TDK) | **C2655099** | LGA-14 2.5x3 | 9163 | 8.95 | genuine |
| Baro | **MS5611**-01BA03 | **C15639** | QFN-8 | 1224 | 5.15 | **see baro note** |
| Flash | W25Q128JVSIQ | **C97521** | SOIC-8 208mil | 94978 | 2.45 | BASIC |
| Flow | PMW3901MB-TXQT | **C43496881** | COB-28 | 596 | 4.96 | see flow note |
| ToF | VL53L1CXV0FY/1 | **C190004** | LGA-12 2.5x4.9 | 5732 | 4.92 | landing/close range only |
| 5V buck | TPS54202DDCR | **C191884** | SOT-23-6 | 85948 | 0.39 | PREF, hand-solderable |
| 3V3 LDO | AP2112K-3.3TRG1 | **C51118** | SOT-25-5 | 79480 | 0.16 | digital rail |
| 3V3 analog | TLV75533PDBVR | **C404027** | SOT-23-5 | 20831 | 0.15 | IMU + RF rail |
| CAN | SN65HVD230DR | **C12084** | SOIC-8 | 91835 | 0.69 | PREF |
| USB ESD | USBLC6-2SC6 | **C2687116** | SOT-23-6 | 150192 | 0.05 | |
| USB-C | TYPE-C 16PIN 2MD | **C2765186** | SMD | 1171811 | 0.07 | |
| microSD | TF-01A | **C91145** | SMD push-pull | 165996 | 0.19 | |
| TVS | SMBJ18A | **C19077573** | DO-214AA | 36488 | 0.047 | PREF; **4S only** — clamps 29.2 V, under the TPS54202's 30 V abs max. Was SMBJ33A (C19077586), which clamped at 53.3 V and protected nothing |
| Xtal 8MHz | X32258MSB4SI (YXC) | **C2682774** | SMD3225-4P | 52080 | 0.093 | passive crystal, **CL 20 pF**, 120 Ω ESR; matches `OSCILLATOR_HZ 8000000` |
| ESC conn | SM08B-SRSS-TB | **C160407** | JST-SH 1.0mm 8P | 267231 | 0.32 | exact SpeedyBee mate |
| JST-GH 4P | XY-SM04B-GHS-TB | **C51940118** | 1.25mm | 11452 | 0.06 | genuine JST has only 6 in stock |
| JST-GH 6P | XY-SM06B-GHS-TB | **C51940119** | 1.25mm | 11511 | 0.08 | |

### SoOP RF section (DNP as fabricated)

| Block | Part | LCSC | Pkg | Stock | US$ | Note |
|---|---|---|---|---|---|---|
| LNA x2 | PSA4-5043+ | **C5240848** | SOT-343 | 1227 | 2.28 | Mini-Circuits, ~19dB, 0.7dB NF, easy to hand-solder |
| LNA alt | TQP3M9037 | C415712 | DFN-8-EP 2x2 | 3120 | 2.64 | 0.5dB NF, harder package |
| LNA alt | MAX2659ELT+T | C28043 | DFN-6 1x1.5 | 7644 | 1.40 | GNSS-optimised, cheapest |
| Tuner | MAX2112ETI+T | C596391 | TQFN-28-EP 5x5 | **20** | 16.86 | **buy from Mouser/Digikey** |
| 27MHz ref | SX3M27.000M20F30TNN | **C2901577** | SMD3225-4P | 21160 | 0.30 | plain xtal; footprint also takes a 3225 TCXO |
| AA filter | OPA2374M/TR | **C444392** | SOP-8 | 5289 | 0.33 | 6.5MHz GBW, right for a 400kHz LPF |
| SAW | *(none at 1620MHz)* | — | SMD3030-6P | — | — | **see SAW note** |
| SAW (GPS variant) | TA1575IG | C498206 | SMD3030-6P | 722 | 1.15 | 1575.42MHz — for Variant D |

---

### Deviations from plan, and why

#### Baro: DPS310 → **MS5611**
DPS310 is **not stocked at LCSC in any package**. DPS368 (C3232508) exists but is not
declared in the MatekH743 hwdef. MS5611 **is** (`BARO MS5611 I2C:0:0x77`), is a better
sensor than BMP280, and is in stock. **Address moves 0x76 → 0x77.** This preserves
day-one stock-firmware compatibility, which was the whole point of the Matek-clone strategy.

#### Flow: PAW3902JF → **PMW3901**
PAW3902 is **not stocked at LCSC at all**. PMW3901MB-TXQT is (596 units). Since the
plan already concluded neither part fixes grass, this changes nothing strategically — the
COB-28 land pattern is shared, so a PAW3902 bought from Mouser/AliExpress still drops in.
The real flow answer remains Phase 4b camera flow.

#### SAW: no 1620MHz part exists at LCSC — **as the plan predicted**
Confirmed by searching `TA1573`, `SAW 1626`, `SAW filter L band 1600`, `SAW filter 1620MHz`
— all zero results. The planned mitigation is now the actual design:
- **SMD3030-6P land pattern** (validated by TA1575IG, which uses it) with a 0R bypass option
- Iridium build: hand-place a TAI-SAW TA1573A / Qorvo 885030 from Mouser
- GPS-L1 build (Variant D): populate TA1575IG, C498206 — a real, stocked part
- Fallback: Nooelec SAWbird+ IR module inline

#### MAX2112 + 27MHz TCXO: order from Mouser/Digikey, not JLC
MAX2112 has **20 units** at $16.86; 27MHz TCXOs have **8–10 units**. Both are SoOP-config parts and DNP,
so this blocks nothing — but do not plan on LCSC for them. The 27MHz **crystal** (C2901577,
21160 in stock) shares the SMD3225-4P footprint with a TCXO, so one land pattern takes either.

#### JST-GH: use the XY clones
Genuine `SM04B-GHS-TB` (C189895) has **6 units**. The XY equivalents have 11k+ and mate
fine with standard Pixhawk JST-GH cables.

#### IMU cost note
Genuine TDK ICM-42688-P is $17.01. The `-HXY` (C46550687, $3.53) and `TOKMAS`
(C54308212, $3.28) relabels are ~5x cheaper but unverified silicon.
**Recommendation: genuine on the board that flies, relabels on the spares** — an IMU is the
one part where a counterfeit costs you an airframe.

### Stock re-checks — moved to `docs/HISTORY.md`

Two dated snapshots (2026-08-26 and 2026-08-28) lived here. **They are superseded by a
tool**, not by a later document: `tools/check_lcsc_stock.py` verifies every LCSC code on
the BOM against JLCPCB's own parts library and reports live stock — currently 48/48 in
stock, 0 low. A dated snapshot of something a tool answers live is a stale duplicate, so
the narrative moved to `docs/HISTORY.md` and the numbers are no longer maintained here.

```bash
python3 tools/check_lcsc_stock.py    # live, all 48 codes, with stock
```

## NAVCORE-SoOP — BOM variants


JLCPCB's 5-board minimum is the reason this board is designed as **one PCB with four
populate-lists** rather than four PCBs. Every optional block has a 0R jumper / DNP strategy
and its own power gate, so a variant is a soldering decision, not a respin.

| # | Variant | Populate | Leave off | Use |
|---|---|---|---|---|
| A | **SoOP navigator** | everything | — | this project, SoOP config |
| B | **Plain 30×30 autopilot** | all but RF | SAW, LNA×2, MAX2112, OPA2374, 27MHz ref, U.FL | any other ArduPilot drone |
| C | **Robotics controller** | all but RF and motor drive | above + 8-pin ESC conn, TVS | rover / boat / gimbal, powered from the 5V rail |
| D | **L-band receiver** | MCU, power, USB, RF, microSD | IMUs, baro, flow, ToF, PWM, ESC conn, CAN | standalone SoOP / Inmarsat / GPS-L1 receiver |

### The retunable RF chain

The SAW footprint is the generic **SMD3030-6P** land pattern, validated against a real
stocked part (TA1575IG, C498206). One component sets the band:

| Band | Centre | SAW | Sourcing |
|---|---|---|---|
| Iridium (this project) | 1620 MHz | TAI-SAW TA1573A / Qorvo 885030 | **Mouser/Digikey — nothing at LCSC** |
| GPS L1 | 1575.42 MHz | TA1575IG | LCSC C498206, 722 in stock |
| Inmarsat STD-C / AERO | 1542 MHz | equivalent 3030-6P part | Mouser |
| Wideband / bring-up | — | 0R across pads 1–4 | bypass, rely on LNA + tuner selectivity |

### DNP notes

- **MAX7456 OSD (`PB12`, SPI2)** — never populated. Keep `PB12` pulled up so stock MatekH743
  firmware's OSD probe fails cleanly instead of hanging the SPI2 bus.
- **9 V VTX buck** — **populated by default** as of this revision (`design.POPULATE_VTX`).
  Use `gen_bom.py --no-fpv` to leave it off. The rail carries **0.30 A measured**, which
  is a 200–250 mW VTX; 500 mW needs a relayout on a future respin, see `design.NET_CURRENT`.
- **`U6` PMW3901 and `U7` VL53L1X** — **not populated**, and not merely optional: both sit
  on the underside with the ESC 3.0 mm below, so neither can see the ground.
  `check_mechanical.py` proves it from `design.GROUND_FACING`. Flow comes from the Pi
  camera over MAVLink (`FLOW_TYPE 5`) and height from the TFS20-L on I2C1, so nothing that
  flies depends on either. `design.POPULATE_BLIND_SENSORS` fits them if the stack is ever
  inverted.
- **27 MHz reference** — the SMD3225-4P footprint takes either a plain crystal (C2901577,
  well stocked) or a ±0.5 ppm TCXO (poorly stocked at LCSC, order elsewhere). Same pads.
- **HSE source jumper** — 0R option to drive the H743's HSE from the 27 MHz reference instead
  of the 8 MHz crystal. **Leave it at 8 MHz** — changing it breaks stock-firmware
  compatibility (`OSCILLATOR_HZ 8000000`). An experiment for a future respin only.

---

## Frame and companion order research — moved to `docs/HISTORY.md`

212 lines of research into the **GEPRC Mark4** frame and the **Orange Pi Zero 2W**
companion lived here. Both decisions were superseded: the frame is the **TBS Source One
V5 7in DC**, with its geometry parsed from the manufacturer's own DXF rather than reseller
listings, and the companion is a **Radxa Zero 3W** which is currently deferred.

The record is kept in `docs/HISTORY.md` because the *reasoning* is worth having — it is
why this project stopped trusting reseller spec tables. It is not kept here because this
document is read to make purchasing decisions, and superseded research sitting inline is
how a settled question gets reopened.

Live frame numbers are in the generated table in `docs/HARDWARE.md`.

### Spatial verification performed on the current 3D model

<!-- BEGIN GENERATED SPATIAL -->
| feature | value | note |
|---|---|---|
| stack height | **29.6 mm** (10.5 frame + 19.1 stack) | needs a **35 mm** standoff; the kit's 30 mm is 2.6 mm short |
| clearance above the FC | 5.4 mm | to the top plate, tallest part `J3` |
| FC/ESC mounting | 30.5 x 30.5 mm | shared pattern, boards concentric |
| board envelope | 45.10 x 46.10 mm | 1.70 mm clear per side, 1.04 mm at the nearer end |
| motor pattern | 19x19 | [D] BrotherHobby product data |
| propeller diameter | 178.4 mm | 7 in |
| adjacent propeller gap | **47.8 mm** | 320 mm wheelbase, discs 226.3 mm apart |
| camera lens to skid contact | 28.0 mm | 40 mm drop + 3.5 mm pad - 12 mm module - 3.5 mm barrel; drop and thickness are [A] |
| battery envelope | 138 x 47 x 48 mm | plan view only - restraint and CG are physical checks |
| companion board | NOT FITTED | 65 x 30 mm Radxa vs a 47 mm battery on a 50 mm plate - see docs/SENSORS.md |

Interference is not asserted here: `tools/check_cad_fit.py` exports every part of `cad/drone.scad` and measures the **intersection volume** of all 55 pairs, plus their minimum separation.
<!-- END GENERATED SPATIAL -->

Generated by `tools/gen_doc_tables.py` from `tools/design.py` and the placed board; do
not edit it here. It replaced a hand-written table that had gone stale **twice** — the
version before this one still quoted 25 mm of inner space, a 30.8 mm propeller gap and
an "Orange Pi", none of which survived the move to the TBS Source One and the Radxa. The
note below is the record of the *first* correction and is kept as history.

> **The two stack rows above were corrected.** They previously read "19.3 / 22.8 mm
> against nominal 35 mm listing clearance" and "12.7 mm", from a `FRAME` dict that carried
> `inner_h = 35.0`. That 35 mm came from a single AliExpress listing and did not survive
> cross-checking: Ready Made RC, NewBeeDrone and Rotorama all give **25 mm standoffs**.
> `tools/check_mechanical.py` also held its own second copy of `FRAME`, so it and
> `check_build.py` reported different clearances for the same stack; it now reads
> `design.FRAME` and both agree. **The real margin is 2.7 mm, not 12.2 mm** — comfortable
> becomes tight, and the standoff height is now a measurement to take on arrival rather
> than a number to trust.

The landing legs are currently represented as four simple vertical cylindrical legs at the
19 × 19 mm motor pattern. This proves the contact height and lens protection relationship,
but it does **not** prove that the chosen TPU/carbon landing gear has the same shape, mounting
holes, arm clearance, or strength. The real leg must be checked for motor-screw length,
crush thickness, prop clearance, and ground stability.

The mechanical checker reports:

```text
14 computed checks ok
9 attention/measurement items
camera lens above skid contact line: 13.0 mm
```

The model renders with OpenSCAD hard warnings enabled and exits successfully.

### Current repository verification

The Orange Pi model update was checked with:

```text
python3 -m py_compile tools/design.py tools/check_build.py   PASS
python3 tools/check_build.py                                 38 checks pass
openscad --hardwarnings -o /tmp/nav/orange-pi-drone.png cad/drone.scad   PASS
```

Current CAD echoes:

```text
stack height:                         19.3 mm
FC-to-top-plate clearance:            12.7 mm
camera-lens-to-skid margin:           13.0 mm
```

### Honest status

- GEPRC Mark4 HD7: best documented candidate found.
- Cheapest AliExpress Mark4-style listings: potentially usable but not mechanically verified.
- Orange Pi envelope: verified.
- Orange Pi hole coordinates: unverified.
- Exact selected AliExpress frame plate/standoff coordinates: unverified.
- Complete aircraft physical fit: not yet proven until the frame arrives or the seller supplies a proper drawing.

---
