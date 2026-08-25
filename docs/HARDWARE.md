# NAVCORE-SoOP — physical hardware

Board and airframe dimensions, fasteners, which way every connector faces, and the
part-by-part audit. Merged from HARDWARE.md, HARDWARE.md and
HARDWARE.md. **Contains generated blocks - see `tools/gen_doc_tables.py`.**

## NAVCORE-SoOP — exact dimensions


Measured from `NAVCORE-SoOP.kicad_pcb`. **[M] = measured from the board file, exact.**
Anything else carries its source, and the two are kept apart on purpose — only one of
them is a fact.

> **Do not run `tools/dimensions.py --md > docs/HARDWARE.md`.** That command was
> written here as the way to refresh this file, and it destroys it: the generator emits
> 85 lines of tables, this document is 170+, and everything below "Buy these to these
> numbers" — the frame-fit reasoning, the purchase requirements, the notes on what still
> needs measuring — is hand-written and is not regenerated. To refresh the numbers, run
> `python3 tools/dimensions.py --md`, read the output, and update the tables in place.

### Buy these to these numbers

| what | requirement | why |
|---|---|---|
| clear space around the stack | **45.10 × 46.10 mm**, centred on the 30.5 mm pattern | see below — this is *not* a plate opening |
| frame stack mounting | **30.50 × 30.50 mm, M3** | matches the ESC exactly |
| frame inner height | **≥ 22.80 mm** | bottom plate to the top of `J3` |
| M3 grommets | flange OD **≤ 5.9 mm** | `R21` is 2.98 mm from one hole — a 6.0 mm flange touches it, a 7 mm washer overlaps by 0.52 mm |
| motor screws | **M3×14** | arm 6 + skid 3.5 + 4 engagement; stock M3×8–10 is too short |
| landing skids | **19×19 mm** pattern | the BrotherHobby 2806.5 is the larger pattern, not 16×16 |

Clear space the frame must leave beyond the board edges, at the heights given below:

| edge | clear space | at height above the bottom plate |
|---|---|---|
| **top** — `J1` USB-C | **6.5 mm** | 17.9 – 21.1 mm |
| **left** — `J2` ESC | **3.6 mm** | 17.9 – 20.8 mm |
| **bottom** — `J8` microSD | **10.4 mm**, on the *bottom* side | 13.8 – 16.3 mm |
| right | nothing | — |

`J1`'s mouth is **flush with the board edge**, zero slack, and it is the only way to
flash the board. Anything crossing that edge — a plate lip, a standoff, the battery
strap — makes the port unusable.

### How to tell whether a frame fits, without owning it

A 30×30 stack does **not** sit inside a hole in a plate. It bolts to four standoffs at
30.5 mm centres and overhangs them by 7–8 mm a side, exactly as the ESC does. So there is
no "opening" to measure, and the fit question is only ever: *does a corner foul an arm
root or one of the frame's own standoffs?*

That makes the ESC the reference, because it is bought with the frame and must already
clear it:

| | X | Y | corner-to-corner |
|---|---|---|---|
| SpeedyBee BLS 60A ESC | 45.60 | 44.00 | 63.37 mm |
| **NAVCORE-SoOP** | **45.10** | **46.10** | **64.49 mm** |
| difference | **−0.50** (we are smaller) | **+2.10** | **+1.13 mm** |

**So the entire question is 1.05 mm per side on one axis**, and 0.56 mm per corner. In X
this board is *narrower* than the ESC and cannot be the limiting part.

The single measurement that settles it, on a frame you own: with the ESC mounted, is
there **≥ 1.1 mm of clear space beyond each of its two long edges**, at 17.9–22.2 mm
above the bottom plate? If yes, this board fits.

#### The frame, from the manufacturer's own CAD

**TBS Source One V5 7″ DC, £35.90** ([HobbyRC UK](https://www.hobbyrc.co.uk/tbs-source-one-v5-7-dc-frame),
in stock). It replaced a Mark4 clone, and the reason is **provenance, not geometry**.

TBS Source One is **open-source hardware**: the frame's own DXF and DWG are published at
[tbs-trappy/source_one](https://github.com/tbs-trappy/source_one)
(`So1-V6-7inDC-2025-JUL-07.dxf`, 69 MB). Every dimension is answerable in CAD *before*
ordering, instead of with calipers afterwards. The 30.50 mm and 20.00 mm stack patterns
in the table below were **parsed directly out of that DXF**, independently of anything a
retailer claims.

The Mark4 could not offer that: three reseller spec tables disagreed with each other and
with the original listing, GEPRC's own product and download pages 404, and the honest
consequence was a row of "measure it on arrival" items — including the standoff spacing,
which is the number that decides whether this board physically fits.

<!-- BEGIN GENERATED FRAME -->
| | value | 
|---|---|
| structure / wheelbase | X-type, 320 mm |
| overall size | 200.0 x 230.0 mm - the **frame footprint, not the centre plate** |
| plates | bottom 2.5, medium 2.0, upper 2.0, camera side 2.0 mm |
| arms | 6.0 mm |
| **FC mounting** | **30.5x30.5 M3 and 20x20 - VERIFIED from the manufacturer DXF** |
| **inner space height** | **30 mm** (what the kit ships) |
| **standoff to BUY** | **35 mm** - the kit's 30 mm is 2.6 mm short |
| motor mounting | 16x16 / 19x19 mm |
| included | frame kit + one 20 x 300 mm battery strap |
| mass / price | 144 g / GBP 35.90 |

Source: [D] github.com/tbs-trappy/source_one So1-V6-7inDC-2025-JUL-07.dxf, stack patterns parsed directly 2026-09-02; [L] hobbyrc.co.uk for standoffs 30/22 mm, plates and 143.5 g; [A] plate outline 200x230 mm - overall footprint only, not load-bearing on any check

Generated from `FRAME` in `tools/design.py` by `tools/gen_doc_tables.py`; do not edit it here. Two earlier frames were specified from listings that disagreed with each other - the arm thickness and standoff height feed real outputs (motor screw length and stack clearance), so both were wrong downstream. This frame's numbers come from the manufacturer's published DXF.
<!-- END GENERATED FRAME -->

**The centre-plate opening and the standoff positions are still the numbers that decide
fit** — but they are now *answerable*, not unknown. Open the 45.1 × 46.1 mm board outline
in the published DXF and look. `tools/check_mechanical.py` lists this under **"ANSWER
THESE FROM THE PUBLISHED CAD, before ordering"** rather than under "measure on arrival",
and that distinction is the whole point of the frame change.

**Standoff length is a purchase, not a frame property.** Treating it as something to
discover on arrival was an error in the document this replaces. M3 standoffs cost a few
pounds in 25 / 30 / 35 / 40 mm — if the kit's are wrong, buy others. The kit ships 30 mm
and 22 mm, and at 30 mm the 22.3 mm stack has **7.7 mm spare**.

**The battery strap.** 20 × 300 mm, over the *top* plate at **30 mm** above the mounting
plate, while `J1` sits at 17.9–21.1 mm — below it, and reached from the side. It does not
cross the USB edge, and clears by **8.9 mm** rather than the 3.9 mm the old 25 mm
standoffs gave.

**What the frame does NOT include: landing legs.** The repo publishes `SO1-V6-skate.stl`,
measured at 76.0 × 102.2 × 6.0 mm — a **flat underside wear plate, not a leg**. This
design's clearance checks assume a **40 mm** drop to clear the belly lidar, so real legs
are still an open item. `design.SKID` (assumed leg) and `design.SKATE` (measured plate) are
deliberately separate: the thickness feeds the motor screw length, and confusing them
means ordering M3×16 instead of M3×14.


### Board
| dimension | value | source |
|---|---|---|
| outline | 45.10 x 46.10 mm | [M] |
| thickness | 1.60 mm | [D] 6-layer stackup ordered from JLCPCB |
| corner radius | 4.00 mm | [M] |
| overall height, board + parts | 8.30 mm | [M] + [D] part heights, base build |
|   same, with the FPV buck fitted | 9.00 mm | [M] + [D] `L5` is 3.00 mm on the underside |

### Mounting
| dimension | value | source |
|---|---|---|
| hole pattern | 30.50 x 30.50 mm | [M] |
| hole diameter | 4.00 mm | [M] M3 + silicone grommet |
| screw | M3 | [D] standard 30x30 stack |
|   hole 1, from board centre | X -15.25  Y -15.25 mm | [M] |
|   hole 2, from board centre | X -15.25  Y +15.25 mm | [M] |
|   hole 3, from board centre | X +15.25  Y -15.25 mm | [M] |
|   hole 4, from board centre | X +15.25  Y +15.25 mm | [M] |
| nearest copper to a hole centre | 2.98 mm (R21.2) | [M] pads only |
|   vs M3 cap head (5.5 mm dia) | +0.23 mm | [M] + [D] |
|   vs silicone grommet flange (6.0 mm dia) | -0.02 mm   OVERLAPS - do not use | [M] + [A] |
|   vs M3 washer (7.0 mm dia) | -0.52 mm   OVERLAPS - do not use | [M] + [A] |

### Connectors — position and the space each one needs
| connector | value | source |
|---|---|---|
| J1 USB-C | 11.53 x 7.04 mm footprint, top side | [M] |
|   faces | top edge, mouth -0.05 mm inboard | [M] |
|   body height above the PCB | 3.16 mm | [D] TYPE-C 16P 2MD(073) |
|   clear space needed beyond that edge | 6.5 mm | [D] TYPE-C 16P 2MD(073); [A] plug overmould |
| J2 ESC JST-SH 8P | 6.55 x 12.69 mm footprint, top side | [M] |
|   faces | left edge, mouth 0.36 mm inboard | [M] |
|   body height above the PCB | 2.90 mm | [D] JST SH series |
|   clear space needed beyond that edge | 3.6 mm | [D] JST SH series; [A] plug + wire exit |
| J3 GPS JST-GH 6P | 13.41 x 6.13 mm footprint, top side | [M] |
|   faces | bottom edge, mouth 12.20 mm inboard | [M] |
|   body height above the PCB | 4.40 mm | [D] JST GH series |
|   clear space needed beyond that edge | 0.0 mm | [D] JST GH series; [A] plug + wire exit |
| J8 microSD | 18.45 x 16.25 mm footprint, BOTTOM side | [M] |
|   faces | bottom edge, mouth 1.60 mm inboard | [M] |
|   body height above the PCB | 1.85 mm | [D] TF-01A |
|   clear space needed beyond that edge | 10.4 mm | [D] TF-01A; [M] a microSD card is 15 mm long |

## Physical layout — what goes where, and why

Written 2026-09-04 once the plate geometry was actually parsed (`design.PLATES`), against
published build practice rather than intuition. Before that, layout rested on a 50 mm
plate-width placeholder that turned out to be 42.50 mm.

### The measured constraint

| plate | size | carries |
|---|---|---|
| top | **42.50 × 160.26 mm** | the battery — which **overhangs it by 2.25 mm per side** |
| FC / mid | 48.50 × 106.59 mm | the 30×30 stack: ESC then FC |
| bottom | 48.50 × 107.62 mm | belly sensor bracket; accessory holes |

The battery is 138 mm of a 160.26 mm plate, so **22.3 mm of plate length is free and the
width is negative**. Nothing else mounts flat on top.

### Centre of gravity

| | value | tolerance |
|---|---|---|
| longitudinal | **+3.1 mm** of the prop centroid | ±15 mm — *"15 mm forward makes the rear motors work 8–12 % harder"* |
| vertical | **+14.9 mm above the rotor plane** | 61 % of mass (the battery) sits above it |

Longitudinal is comfortable and the accessories are too light to move it — the battery is
55 % of AUW, so it is the only real lever. The **vertical** figure is the one to know:
published guidance warns that *"too much weight above the rotor plane can cause tipping or
oscillation"*. Top-mounting is normal on 7-inch long-range builds — it protects the pack
and keeps ground clearance — but it is a trade, not a free choice, and it is why this
aircraft will feel less planted in slow manoeuvres than a bottom-mounted one.

### Antennas — the rules with hard numbers

Three things want sky view and distance from the ESC, and **none of them fits on the plate**:

- **GPS patch** — mast it. Published minimum is **30 mm above the frame** and **≥30 mm
  from the ESC**, patch skyward with nothing above it. A 30 mm mast puts it at z ≈ 67 mm,
  which is **49 mm above the ESC's tallest parts** — comfortably clear.
- **Iridium patch** — same rules, harder. **ESC switching noise is documented as landing
  in the 1–2 GHz band**, and Iridium is 1.616–1.6265 GHz. This is not a hypothetical
  overlap; it is the known problem band, and it is exactly what `BUILD.md` T3b measures.
  Mast it as high as the airframe tolerates.
- **ELRS ×2** — **90° to each other**: one vertical at the rear, one horizontal along an
  arm, so one is well-oriented whatever the attitude.

Two rules that catch people:

1. **Carbon fibre blocks and detunes antennas.** Nothing radiating may sit under a plate
   or behind an arm.
2. **Mast hardware must be non-magnetic** — nylon, brass, aluminium or titanium. The GPS
   module carries the compass, and steel screws beside it bias the heading.

### Cable routing

Along the frame edge, **away from the four motor phase leads** — those act as antennas for
the ESC's broadband noise. On an ordinary quad that is hygiene; here it is the difference
between hearing Iridium bursts and not. The harness plan is in `docs/BUILD.md`.

### What is on each board edge
| edge | value | source |
|---|---|---|
| top | J1 | [M] |
| left | J2 | [M] |
| bottom | J3 (GPS) and J8 (microSD) | [M] |
| right | nothing | [M] |

### Stack, measured up from the frame's bottom plate

<!-- BEGIN GENERATED STACK -->
| level | height | source |
| --- | --- | --- |
| top of the bottom plate | 2.50 mm | [D] github.com/tbs-trappy/source_one So1-V6-7inDC-2025-JUL-07.dxf, stack patterns parsed directly 2026-09-02 |
| top of the arms | 8.50 mm | [D] github.com/tbs-trappy/source_one So1-V6-7inDC-2025-JUL-07.dxf, stack patterns parsed directly 2026-09-02 |
| top of the mid plate - **the stack bolts here** | 10.50 mm | [D] github.com/tbs-trappy/source_one So1-V6-7inDC-2025-JUL-07.dxf, stack patterns parsed directly 2026-09-02 |
| top of the ESC's PCB | 12.10 mm | [D] SpeedyBee BLS 60A manual |
| top of the ESC's tallest part | 18.30 mm | [D] SpeedyBee BLS 60A manual |
| bottom of this board's tallest bottom part (`D1`) | 21.30 mm | [A] M3 silicone grommet compressed to 3.0 mm; [M] 30.5 mm pitch and 4.0 mm holes from design.BOARD |
| underside of this board's PCB | 23.60 mm | [M] board |
| top surface of this board | 25.20 mm | [D] 6-layer stackup from JLCPCB |
| top of the tallest part (`J3`) | 29.60 mm | [M] board |
| **standoff to buy - 35 mm** | 35.00 mm | [M] computed from the board + FRAME + ESC + MOUNTING |
| **SPARE** | 5.40 mm | [M] derived |
<!-- END GENERATED STACK -->

This table was hand-written and had drifted onto the *superseded* frame: it said the
bottom plate was 3.00 mm, the inner space 35.00 mm and the spare 12.20 mm, all from an
AliExpress listing replaced by the manufacturer's DXF. Worse, it started the ESC on the
bottom plate, omitting the 6.0 mm arms and the 2.0 mm mid plate between them — the same
8.0 mm error `cad/drone.scad` and `tools/check_mechanical.py` both carried. It is now
generated by `tools/gen_doc_tables.py`; do not edit it here.

### What the frame must provide
| requirement | value | source |
|---|---|---|
| clear rectangle around the 30.5 mm pattern | 45.10 x 46.10 mm | [M] |
| stack mounting | 30.50 x 30.50 mm M3 | [M] |
| inner height, at least | 22.80 mm | [M] + [D] |
| clear beyond the TOP edge (USB) | 6.5 mm | [A] plug |
| clear beyond the LEFT edge (ESC) | 4.0 mm minus 0.40 inboard | [A] plug |
| clear below the BOTTOM edge (card) | 12 mm on the bottom side | [M] card length |

### Compared with the ESC it stacks on
|  | value | source |
|---|---|---|
| ESC outline | 45.60 x 44.00 mm | [D] SpeedyBee BLS 60A manual |
| this board | 45.10 x 46.10 mm | [M] |
| corner to corner | 64.49 vs 63.37 mm  ->  +1.13 mm | [M] + [D] |
| extra clearance needed per corner | 0.56 mm | [M] derived |

### Mounting the companion computer

Nothing in this project said where the Pi goes. `docs/HARDWARE.md` argues about
*which* Pi to fly; no document said how it is held. These are the numbers.

|  | Radxa Zero 3W (1GB) | source |
|---|---|---|
| board | **65.0 × 30.0 mm**, 1.2 mm thick | [D] radxa.com |
| mounting holes | **PATTERN NOT PUBLISHED — measure the board** | [U] Radxa publishes only the envelope |
| camera | **J7, 22-pin 0.5 mm FPC, 4-lane MIPI CSI** | [D] `radxa_zero_3w_v1.12_schematic.pdf` |
| SoC | RK3566 quad Cortex-A55 @ 1.6 GHz | [D] |
| mass | ~12 g | [A] not published; same PCB class as a Pi Zero (11 g) |
| power | 5 V / 2 A, **from its own BEC** | [D] radxa.com; see `docs/HARDWARE.md` |

> **Why this board.** The Raspberry Pi Zero 2 W is £14.40 RRP but sold out at The Pi Hut
> *and* Pimoroni, with the open market at £70. The Radxa is ~£18, the same 65 × 30 mm
> footprint, and carries **the same 22-pin CSI socket** — so the flow camera can be added
> later without changing boards, and switching back to a Pi Zero if one restocks costs
> only software. The **Orange Pi Zero 2W (£25) was rejected**: it has no MIPI CSI
> connector at all — the 24-pin "function" connector in that position carries Ethernet,
> USB, TV-out, audio and IR, confirmed from the vendor's own 176-page manual, which
> documents USB (UVC) cameras only.
>
> **Do not cut a tray to a guessed hole pattern.** Resellers claim "same holes as the Pi
> Zero", but the only figure any of them quotes — 61 mm diagonal — does not match the Pi
> Zero's `hypot(58, 23) = 62.4 mm`.

**It does not fit the 30 × 30 stack.** At 65 mm long it overhangs this 45.1 mm board by
10 mm at each end, and its M2.5 pattern shares no dimension with the 30.5 mm M3 pattern.
So it does not bolt into the stack — it mounts separately:

- **On the frame's top plate**, standing off the stack, with the camera looking down
  through the centre-plate cutout. The Source One V5's top plate is 2.0 mm and takes M2.5
  self-tappers directly.
- **Wiring** — six ways to `P41`–`P46`: 5 V, TX, RX, PPS, RTS, GND. Note `P41` supplies
  5 V from this board's rail, and the audit's conclusion is that the Pi should **not**
  draw from it: at 700 mA it was 37 % of the rail and put `L2` at 118 % of its rating.
  Feed the Pi from its own BEC and use `P41` only if you have re-checked the budget.
- **A Pi 5 cannot be powered from this board at all** — it needs 5 A.

**Not yet measured, because it needs the parts:** the standoff height that clears `J3`
(4.40 mm) and the plug on it, and whether the camera ribbon reaches the centre plate.


### Fastener schedule

Generated by `python3 tools/fasteners.py --md`. A screw length is a **derived** quantity —
the sum of what it passes through plus thread engagement — so it is computed from the
thickness stack rather than written down. Only one joint was ever computed before this
(the motor screws), and that is exactly the one where a stock M3x8 does not reach.

<!-- BEGIN GENERATED FASTENERS -->
| joint | screw | qty | passes through | engagement | order |
|---|---|---|---|---|---|
| Motor to arm, skid sandwiched | M3 | 16 | frame arm 6.0 + TPU skid 3.5 = 9.5 mm | 4.0 mm | **M3x14** &#9888; |
| FC to ESC, through the 30.5 mm stack | M3 | 4 | ESC PCB 1.6 + grommet gap 3.0 + FC PCB 1.6 = 6.2 mm | 4.0 mm | **M3x12** &#9888; |

- **Motor to arm, skid sandwiched** &#9888; rounding 13.5 -> M3 x14 puts 4.5 mm into the thread, not 4.0. MEASURE THE TAPPED DEPTH before fitting: if it is shallower than 4.5 mm the screw bottoms out and clamps nothing. A 12 mm screw plus a washer is the usual fix.
- **FC to ESC, through the 30.5 mm stack** &#9888; rounding 10.2 -> M3 x12 puts 5.8 mm into the thread, not 4.0. MEASURE THE TAPPED DEPTH before fitting: if it is shallower than 5.8 mm the screw bottoms out and clamps nothing. A 10 mm screw plus a washer is the usual fix.

| joint | screw | why it is not derived |
|---|---|---|
| Frame assembly - top plate to standoffs | M3 | the listing gives neither the standoff length nor the spacing; measure the kit |
| Camera module to its mount | M2 or M2.5 | no camera mount exists yet - position, plate and hole pattern all undecided |
| Camera mount to frame | M3 | depends where it lands; see the ground-clearance question in docs/HARDWARE.md |
| Radxa Zero 3W (1GB) - DEFERRED, not fitted - mounting location UNDECIDED | M2.5 | hole PATTERN NOT PUBLISHED by the vendor - measure the board; 2.8 mm holes, self-tapping into a 2.0 mm plate; standoff height unmeasured |

Generated by `tools/gen_doc_tables.py` from `tools/fasteners.py`; do not edit it here.
<!-- END GENERATED FASTENERS -->

Engagement is 1 × diameter into soft material (4.0 mm for M3), which suits both aluminium
motor bells and nylon standoffs.

**The 3.5 mm skid thickness is an `[A]` and it sets the motor screw length.** Measure the
skid you actually buy before ordering screws: a 2 mm skid wants M3x12, a 5 mm skid wants
M3x16, and stock motor screws are M3x8–10 and reach none of them.

---

## The reversed connectors — what was wrong, what was fixed, what is left


*Written 2026-08-29. The board is fully routed again — 479/479, 0 DRC errors.*

### The fault

**Both `J1` (USB-C) and `J2` (ESC, JST-SH 8) were fitted with their mating faces pointing
into the board.** `J1` was spotted by eye on a 3D render; `J2` was found by checking the
other connectors afterwards.

Every automated check had passed them. `check_design`, `check_hwdef`, `check_electrical`,
`check_traces`, `check_placement`, `check_build` and DRC all validate *electrical*
correctness. Connector orientation is mechanical intent, and nothing in the toolchain had
any concept of "this opening must face off-board". `check_build.py` even measured `J1`'s
distance to the board edge — 0.83 mm, passed — without ever asking which way it faced.

**Root cause:** `gen_pcb.py:68-72` assigns connectors to edge zones (`J1 -> "T_N"`) but
nothing ever sets their rotation from the edge they land on. The placer knows *where*,
never *which way round*.

#### How each was proved, from footprint geometry

`J1` — `USB-C-SMD_TYPE-C-16PIN-2MD-073`:

| | |
|---|---|
| courtyard (body) | local y −3.24 … +3.71, 6.95 mm deep |
| the 12 SMD contacts | all at local y −2.375 — only **0.87 mm** from the −3.24 face |
| silkscreen beyond the body | local y +3.35 … +4.97, drawn *outside* the courtyard |

Contacts leave a USB-C receptacle at the **rear**, 6–7 mm from the mouth. Pads 0.87 mm
from the −3.24 face make that face the rear, so the mouth is at +3.71, and the silkscreen
past it is the plug keep-out. At rotation 0° on this board, +y pointed inboard.

`J2` — `CONN-TH_SM08B-SRSS-TB-LF-SN`. Three independent features agree:

| | |
|---|---|
| body outline (`Cmts.User`) | local y −1.601 … +2.649 |
| 8 signal pads | local y −1.9375 — *outside* the body at −y, so −y is the rear |
| 2 mounting tabs | local y +1.9375, flush with the body's +2.649 front face |
| silkscreen front marker | a line at y +2.859, spanning the plug width |

So the mouth is at +y, which at rotation 90° pointed **inboard**.

#### Why `J2` mattered as much as `J1`

`J1` was obviously fatal — no cable could be plugged in, so the board could not be flashed
or talked to. `J2` looked survivable: a JST-SH cable could in principle bend back over the
board.

It could not. **`U1`, the STM32 itself, sits 3.28 mm in front of `J2`'s mouth.** A JST-SH
plug plus the fingers to insert and remove it do not fit in 3.28 mm, and this is the cable
carrying VBAT and all four motor signals. Both had to be rotated.

### The fix

| | before | after |
|---|---|---|
| `J1` | rot 0°, at y 104.01 | **rot 180°, at y 103.66** — mouth flush with the top edge at y 99.95 |
| `J2` | rot 90° | **rot 270°**, unmoved — mouth 1.19 mm inboard of the left edge |

`J1` was shifted 0.35 mm so the mouth lands flush with the board outline. `J2` was not
moved: its courtyard already sits 0.40 mm from the edge and has nowhere to go.

Verified by transforming each footprint's mating face into board coordinates and checking
it against the nearest board edge — both now score +1.00 (pointing straight out), and the
3D render shows both openings clear of the board.

**A happy side effect:** after rotation `J1`'s contacts land at y 106.035, directly above
`U12`, the USB ESD protection, whose pads are at y 106.012 on the bottom. The protection
is now 0.26 mm from the connector instead of 5 mm away — which is where it belongs.

### The surgery

The board was at 479/479 connections with 0 DRC errors, built over many sessions, so it
was corrected locally rather than regenerated. In order:

1. Ripped the 11 affected nets and the GND stitching inside the two connector windows —
   240 objects.
2. Rotated and moved both footprints.
3. Removed 15 objects left clashing with the rotated pads (`+5V`, `IMU1_CS`, `SPI1_MOSI`,
   `SPI1_SCK`, `USB_DM`) and refilled the zones.
4. Restored the long-haul In2/In3 routing east of `J2` — the expensive part, and not
   reproducible with the tools available (see below).
5. Re-routed the rest, net by net, each one judged by whole-board DRC and reverted if it
   raised a violation.

#### Result

**479 of 479 connections, 0 DRC errors, 0 schematic-parity issues** — back to where the
board was before the surgery, with both connectors now usable.

### Why the first re-route stalled at 471/479, and what fixed it

Four pads across three nets (`M2`, `M3`, `CC2`) would not route, and it was tempting to
conclude the board was too full and that push-and-shove — or a full re-route from a
stripped board with freerouting — was the only way out.

**It was the routing model, not the board.** `tools/route.py` was refusing legal paths for
three separate reasons, each of which the file already argues against itself somewhere
else:

| | what it did | what the rules say |
|---|---|---|
| `TRK_KEEP` | adds **0.15 mm** around every track | the board's clearance is **0.1016** |
| `_mark_via_legal` | pads as **circumscribed circles** — 0.775 mm on `J2`'s 1.55 × 0.60 pads | pads are **rectangles** |
| `route_to_any` | changes layer with `other = 1 - li` | there are **four** signal layers |

The first inflates every track's no-go corridor from 0.41 mm to 0.63 mm; where two such
corridors overlap the cells are marked "contested" and block a third net outright, which
is what appeared to seal `J2`'s pads in from the east. The second hides every escape
between `J2`'s pads — the row is 1.0 mm pitch with 0.6 mm pads, so the 0.4 mm gaps do fit
a 0.1016 mm track at real clearance, but not under a 0.775 mm disc. The third is a
two-layer leftover that can only ever hop `F.Cu` ↔ `In2.Cu`, silently unable to reach
`In3.Cu` or `B.Cu`.

`tools/route_final.py` uses the real design rules, real pad rectangles and all four
layers. It routed `M2` and `M3` in ten seconds each, and `CC2` — the 12.6 mm run that had
no copper at all — in thirteen.

It also samples everything **point-wise on a grid** rather than testing segment against
segment. That is not only simpler, it removes a bug class: segment-to-segment distance
has to special-case crossing, because two segments that cross have every endpoint far
from the other and a true distance of zero. A grid cell sitting on another net's track is
simply blocked.

Two further faults were found and fixed in the same tool:

- **Window sizing latched onto the source pad.** The window is meant to span the pad and
  the nearest copper of its net — but the pad *is* copper of its net, at distance 0. So
  `CC2` got a ±9 mm window around its own start, putting the only other `CC2` pad 12.6 mm
  away outside it, and the search reported "no reachable copper" for a net whose two ends
  were simply further apart than the window.
- **Five nets were split, not unrouted.** Removing the 15 objects that clashed with `J1`'s
  rotated pads cut `SPI1_SCK`, `SPI1_MOSI` (twice), `IMU1_CS` and `USB_DM` in half — each
  had been relying on a via that had to go. DRC reports these as unconnected *track to
  track*, never as an unconnected pad, so a pad-driven router never sees them. They need
  the two named pieces as start and goal specifically: "any copper of this net" makes the
  start piece its own goal and returns a zero-length route.

### Tooling lessons from this work

Three bugs were found in the checking code during the surgery, all of which had been
silently passing bad geometry. They are worth knowing because the same mistakes are easy
to make again:

1. **`kicad-cli pcb drc` reads the design rules from the `.kicad_pro` beside the board.**
   Checking a copy in `/tmp` silently falls back to KiCad's defaults — 0.2 mm clearance
   instead of this board's 0.1016 — and invented ~1100 violations that were purely an
   artifact of where the file was sitting. **Always DRC in the project directory.**

2. **Segment-to-segment distance must handle crossing.** The endpoint-only form reports
   two segments that cross as comfortably clear, because every endpoint-to-segment
   distance can be large while the true distance is 0. This cleared `M2` to cross
   `SD_D2`, `SD_D3` and `BUZZER`.

3. **Pads are rectangles, not circumscribed circles.** `route.py` makes this point about
   `_stamp_rect` and then leaves the same bug in `_mark_via_legal`. On `J2`'s 1.55 × 0.60
   mm pads a circumscribed disc is 0.775 mm, which swallows the 0.4 mm gaps between
   neighbours and hides every escape route between them.

Also: **a through via pierces every layer.** Two `VBUS` routes were rejected for shorting
nets that were invisible on the two layers being looked at — `IMU1_CS` on B.Cu and
`SPI1_SCK` on In3.Cu. Via positions here are now searched for as points clear of every
other net on *all* layers, not eyeballed on one.

### The generator, so this cannot recur — done

Surgery alone left `gen_pcb.py` able to reproduce the defect the next time anyone
regenerated the board. Three changes close that:

**`design.MATING_FACE`** gives each connector's outward direction in footprint-local
coordinates, with the evidence for each written beside it, plus `MATING_CLEARANCE` for how
much straight space the plug needs.

**`gen_pcb.ZONE_FACING` and `required_rotation()`** supply the half of `zone_of()` that was
missing. A connector's rotation is now decided by the edge it sits on, and the footprint is
reserved the right way round so the packer cannot hand back a slot that only fits the other
orientation. The rotation is solved by trying all four quarter turns through the same
transform `check_connectors.py` verifies with, rather than a hand-written table of cases,
so the two cannot disagree.

**`tools/check_connectors.py`** checks three things on the board itself, and is gated in
`preflight.py`:

1. the mating face derived from the footprint agrees with the declared one — catches a
   footprint swap silently invalidating the table;
2. the mouth points off the board — the `J1` failure;
3. there is clear space in front of it for the plug — the `J2` failure, and the reason 2
   alone is not enough, because `J2`'s mouth sat 0.82 mm from the board edge and passed
   every clearance rule in the project while facing inboard into `U1`.

It fails hard below **half** the connector's declared allowance and warns below the
allowance itself. That split matters: a flat threshold let `J2` through as a mere warning at
2.50 mm from the MCU, and failing a board on a hand-picked constant is how this project
talked itself into inventing 0.15 mm clearances elsewhere.

#### Verified three ways

| board | expected | result |
|---|---|---|
| the fixed board | pass | 0 failures, 1 warning (`J3`, below) |
| a board **freshly generated** by the fixed `gen_pcb.py` | pass | 0 failures, 0 warnings |
| the board with `J1` and `J2` put **back** as they were | fail on both | 2 failures |

The third is the one that matters — a check never seen to fail is not a check. The solver
also independently reproduces all four rotations the corrected board actually has
(`J1` 180°, `J2` 270°, `J3` 0°, `J8` 180° flipped).

`gen_pcb.py` also takes `GEN_PCB_OUT` now, so the generator can be exercised without
overwriting a routed board — it rebuilds the PCB from scratch, so testing a placement
change used to mean throwing away every trace first.

#### The one warning left

`J3` (GPS) has **5.30 mm** of clear space in front of its mouth, against a nominal 6.0 mm
allowance, with `R21` nearest. This is pre-existing and not caused by the rotation. The
6.0 mm is a written-down plug-plus-bend figure, not a measurement — check it against the
JST-GH plug when it arrives.

Two bottom-side notes found while writing the checker: a flipped footprint mirrors in local
**y** under this transform, not x (checked against `J8`, whose slot must face the bottom
edge where the card comes out) — `J1`/`J2`/`J3` never exposed it because none is flipped.
And the plug corridor is sampled starting 0.3 mm in *front* of the mouth, because at 0 it
lies in the connector's own face plane where its neighbours legitimately sit shoulder to
shoulder.

### Frame checks this creates — for `docs/BUILD.md`

All four board edges now carry something, which constrains how the board sits in the frame:

| edge | what is on it | clearance needed |
|---|---|---|
| top | `J1` USB-C, **flush with the edge** | horizontal plug insertion |
| left | `J2` ESC cable | cable drops to the ESC below |
| bottom | `J8` microSD | ~15 mm to withdraw the card |
| right | `J3` GPS | cable exits toward the bottom edge |

- [ ] **Battery strap route.** On the Source One V5 it runs over the top plate, 30 mm up. If it crosses the
      USB edge, the port is unusable with a battery fitted — and the mouth is now flush
      with that edge, so there is no slack.
- [ ] **Top plate overhang** past the board edges, especially over the USB.
- [ ] **microSD withdrawal** with the stack assembled.
- [ ] **Board rotation within the frame.** With four live edges there may be only one
      orientation that works. Decide it before cutting looms.

---

## Buck re-layout and the floating grounds — 2026-08-30

### Why the inductors had to move

`L2` and `L5` were **1210 chip lands (3.2 × 2.5 mm) holding LCSC C167879, an FNR4030
whose body is 4.0 × 4.0 × 3.0 mm.** Neither part fitted its land. `L2` was additionally
carrying **1.89 A on a 1.6 A RMS rating**.

### What was changed, and what was not

**`L2` is fixed.** It now sits on the **top side at (130.79, 106.43)** on an
`L_APV_ANR4030` land (4.65 × 4.55 mm), **4.39 mm from `U8`'s PH pin and on the same side
as it**, so the switch node no longer crosses the board through a via. That is better
than the layout it replaced, not merely a repair. `C22` moved to the bottom to make room;
`C23` stays at the output so the output loop keeps a close bulk cap.

**`L5` was deliberately left on its wrong land.** It was placed and routed, then taken
back out. The only nearby 4 × 4 position that displaced a single part sits on top of
`U1`'s escape routing; clearing the copper it lands on cuts `M1`, `M2` and `VTX_EN`, and
**no legal via exists within 1.2 mm of any of the three afterwards** — their vias were
legal exactly where they already were. `docs/BUYING.md` records the 9 V VTX buck as
"DNP by default", so `L5` is not fitted on this build. Cutting three working nets to fix
a land for a part nobody solders was the wrong trade. **Deferred to any future respin.**

### Two floating grounds, found by chasing the last unrouted nets

Neither was visible to `route_gnd.py` or `route_to_plane.py`. Both look for pads with no
net copper at all; these pads had copper — copper that went nowhere.

**`U1.49` — an MCU VSS pin — was not connected to the ground plane.** Its local F.Cu pour
sliver (1.85 × 0.59 mm) reached no via. There was GND on In3.Cu **0.03 mm away** and no
legal 0.6 mm via within 1.6 mm, because `I2C2_SDA` occupies the escape. Fixed with a
**0.45 mm via in the pad** — the board's stated minimum, and already the size of 167 other
vias on it. **Assembly note: via-in-pad can wick solder during reflow.** On a ground pin
that is the right trade against a floating VSS, but it is a real manufacturing caveat.

**`C25.2` — the 5 V buck's COMP network ground — was floating** (resolved 2026-09-04 by
deleting the network; the TPS54202 compensates internally — see the boxed note below).
Same failure at the time: a
B.Cu pour sliver with no via. It resisted four separate attempts:

- a via in the pad connects it but is a **through** via, so it appears on F.Cu too and
  shorts to `CC1` and `L2`'s BUCK_PH pad. A blind via would work; JLCPCB's free tier does
  not offer them;
- every route out is blocked by `BUCK_COMP2`, which wraps around the part;
- moving `C25` works geometrically, but the only positions clearing all copper are
  **7.9 mm from `U8.6`** against its 3.0 mm adjacency limit. COMP is the buck's feedback
  compensation — a high-impedance node that long traces destabilise. Worse than the
  problem;
- shifting `L2` 0.25 mm east to free the via cascaded into new clashes with `L2`'s own
  `+5V` pad.

**This is a genuine open defect, not cosmetic.** A floating ground on the compensation
network means the loop compensation is not referenced. It needs deliberate layout of the
COMP cluster, which is the same conclusion the inductors reached.

### State

**Superseded — this recorded 476 of 479 with three open: `C25.2` ground and two `+9V`
breaks.** Current state is **all nets routed for fitted parts, with a single unconnected
item — `BUCK9_PH`, on a DNP-only net.** `C25.2` went away with the COMP network; the two
`+9V` breaks collapsed into the one `BUCK9_PH` item when the 9 V block was set DNP.

### The COMP cluster — why it cannot be fixed in isolation

> **Read the next two sections as history, not state (noted 2026-09-04).** `R8`, `C24` and
> `C25` — and the `BUCK_COMP` / `BUCK_COMP2` nets — **no longer exist on the board.** The
> network was deleted outright once the regulator was settled as a **TPS54202, which
> compensates internally** (`design.py`: *"R8/C24/C25 COMP network DELETED"*). Verified
> against the artwork: zero footprints and zero nets for any of them.
>
> The narrative is kept because the *method* is reusable — ripping competing copper before
> searching, and costing a placement by how far it exceeds its own limit rather than by raw
> distance. The *parts* are gone, so do not plan a respin around this cluster, and do not
> go hunting `C25.2`'s floating ground: it was removed with the part.

`C25.2`'s floating ground is a symptom. The cause is that the whole compensation network
is scattered, every part of it outside its own adjacency limit:

| | now | limit | net |
|---|---|---|---|
| `R8` | **5.49 mm** from `U8.6` | 2.0 | BUCK_COMP ↔ BUCK_COMP2 |
| `C24` | 3.60 mm | 3.0 | BUCK_COMP2 ↔ GND |
| `C25` | 5.49 mm | 3.0 | BUCK_COMP2 ↔ GND |

A deliberate arrangement exists on paper and is a large improvement — `R8` at
(131.14, 108.53) is **1.70 mm** from the COMP pin, with both caps getting real ground vias
on their actual GND pads. It fails on copper, not courtyards: `R8`'s BUCK_COMP pad lands
on the `+5V` via at (131.60, 108.90).

Relocating that via has 55 legal positions, but the B.Cu leg to `C23` then crosses the
space the caps need. Searching with copper properly accounted for collapses the whole
problem: **`R8`, `C24` and `C25` have 4, 6 and 6 valid positions and every one of them is
the same small pocket at ~(130.8, 107.8)** — one part's worth of space for three parts.

**So this is not a COMP-cluster problem, it is a buck-south-side problem.** Four groups
compete for that pocket: the compensation network, the FB divider (`R6`, `R7`), the +5 V
output path (`C22`, `C23` and its via), and `L2`'s connection. Any of them can be placed
well; not all four at once. Fixing it means planning that whole area together, which is a
layout task for any future respin rather than a repair.

Two search bugs were found and fixed getting to that conclusion, both worth remembering:
keeping the **nearest** N candidates makes every combination overlap and reports "no
arrangement" on a board with hundreds of valid positions — candidates must be spread; and
testing a ground via against "either pad" put it on pad 1, which is BUCK_COMP2, and would
have shorted the compensation node to the plane.

### The buck south side, re-planned as one job — and it worked

Ripping the copper for the competing nets FIRST was the unlock. With it in place the
three COMP parts had 4, 6 and 6 valid positions, all the same pocket. With it ripped they
had 284, 268 and 268, and the FB divider 731 and 412.

| part | was | now | limit | |
|---|---|---|---|---|
| `R8` | 5.54 mm | **1.63** | 2.0 | ok |
| `C24` | 3.40 mm | **2.82** | 3.0 | ok |
| `C25` | 5.49 mm | **3.81** | 3.0 | over by 0.81 |
| `R6` | 5.34 mm | **0.57** | 2.5 | ok |
| `R7` | 0.70 mm | 2.35 | 2.5 | ok |

Four of five inside their limits where none was before, and **`C24.2`, `C25.2` and `R7.2`
each now have a ground via within 0.6 mm** — the floating-ground defect is closed and the
5 V loop compensation is referenced to the plane.

One correction to the method: the first arrangement minimised TOTAL distance and moved
`R7` from 0.70 mm out to 2.83 mm - past its limit - to buy fractions of a millimetre for
parts already inside theirs. Cost is now how far a part EXCEEDS its own limit, with raw
distance only as a tie-break.

### What is left, and why

**477 of 479 at the time. Two unconnected, both on `+9V`** — now a single `BUCK9_PH`
item, the 9 V block having been set DNP. They were `C70`'s stub and the
`R42`/`C69` group, both sitting in the band at `U1`'s left edge that has now defeated
five separate attempts this session: `L5`'s 4x4 land, `M1`, `M2`, `VTX_EN`, and these.

The gap between `C70`'s stub and `L5.2` is 2.1 mm and contains `C19`, `R11` and four vias
(`VBAT`, `I2C2_SCL`, `PPS_SYNC`, `UART7_RX`). There is a channel between `C19` and `R11`
at y = 118.75-118.85 that is clear to `L5.2` — **by 0.038 mm** — but reaching it from the
stub crosses `I2C2_SCL`. Margins of hundredths of a millimetre are not a route worth
committing.

**The right answer for this rail is not routing.** `docs/BUYING.md` records the 9 V VTX
buck as "DNP by default; populate only for an analogue-FPV build", and **none of its 14
parts is marked DNP in `design.py`** — `U18`, `L5`, `C68`-`C72`, `R41`-`R45`, `Q3`, `PV1`
all ship populated. That is a real BOM defect in its own right: fourteen parts bought and
placed for a feature this build does not use. Marking them DNP is the fix; the two
unrouted connections then carry no fitted component.

### The +9V rail is routed after all — 479/479

I reported this rail as unroutable and that was wrong. Every attempt had been on the
outer layers or straight lines through the band at `U1`'s left edge. Two things worked:

- **`R42`/`C69` group** — In3.Cu has a channel at **y = 119.68, 0.070 mm wide** between
  `VBAT` below and `BUCK9_PH` above, and the existing In3 `+9V` run at x = 129.66 extends
  south to meet it. Four legs: B.Cu out of `R42.1`, a via at (132.25, 120.28), In3 down
  to the channel, across, and north into the main run.
- **`C70`'s stub** — a B.Cu dogleg via (124.00, 118.80), threading between `C19`, `R11`
  and the `UART7_RX` via with 0.079 mm of margin. Nine such corners exist; earlier
  searches centred their box on the midpoint and never reached them.

Two lessons from getting it wrong the first time. A search box centred between the
endpoints does not cover the space a real route uses. And **endpoints must be the
tracks' exact coordinates** — rounding to 0.01 mm left the new copper microns clear of
what it was meant to join, so it committed cleanly and connected nothing.

The new copper then stranded a B.Cu ground island containing **`C19.2`**, a fitted VBAT
cap's ground pad; a 0.45 mm via at (123.74, 118.02) rescued it.

**479/479 connections, 0 DRC errors, 0 schematic-parity issues.**

#### Populating the analogue-FPV variant still needs one thing

The rail is electrically complete, but `L5`'s land is a 1210 and the part is 4.0 x 4.0 mm.
The **pads are not the problem** - they are 1.25 x 2.65 mm on 2.80 mm centres, which the
FNR4030's terminals match. The problem is the body: the gap between `C18` and `C69` is
**3.55 mm** and the body needs 4.0, so it overhangs each by ~0.22 mm. Neither cap can move
(no position clears it), and no 10 uH part at the 0.6 A this rail needs is small enough:
`CKCS3010` is 3 x 3 mm but only 550 mA, `CY43-10UH` is 1 A but 4.5 x 4.0 mm.

So populating it means either accepting 0.22 mm of body contact with two 1206 caps, or a
a respin that moves `C18` and `C69`. That is a much smaller obstacle than an unrouted rail.

---

## NAVCORE-SoOP — component audit


What is on the board, what is deliberately absent, and what is genuinely missing.

### Present and correct

| Block | Part | Notes |
|---|---|---|
| MCU | STM32H743VIT6 | 8 MHz crystal, BOOT + RESET buttons, SWD test points |
| IMU ×2 | ICM-42688-P (SPI1), ICM-42605 (SPI4) | at the board centroid, on the bottom |
| Barometer | MS5611 @ I²C2 0x77 | matches the MatekH743 hwdef exactly |
| Logging | microSD (SDMMC1 4-bit) + W25Q128 on SPI3 | flash also holds the TLE catalogue |
| Flow / range | PMW3901 (SPI3), VL53L1X (I²C1) | bottom side, looking down |
| Power | TPS54202 5 V/2 A synchronous, AP2112 3V3, TLV75533 3V3-analog | TVS + bulk on VBAT |
| Comms | CAN (SN65HVD230), USB-C + USBLC6 ESD | |
| Sense | battery divider (11:1), ESC current, ESC telemetry on `UART8_RX` | |
| I/O | GPS JST-GH, ESC 8-pin JST-SH, solder pads for TELEM/RC/CAN/rangefinder | |

### Deliberately absent

- **Magnetometer.** 15 mm from a 60 A 4-in-1 ESC a compass is worthless. I²C1 is on the
  GPS connector — use the compass inside the GPS module, where it belongs.
- **L-band RF front end.** Moved off-board: the flight controller alone is 67.5% courtyard against a
  ~60–65% routable ceiling, and an LNA belongs at the antenna anyway. See LAYOUT.md.

### Previously missing — all four now fitted

The four gaps this audit originally listed were batched into one edit and added; the
table is kept because the reasoning still matters, not because the work is outstanding.

| Was missing | Consequence | Fitted as |
|---|---|---|
| Buzzer driver | `BUZZER` was a bare MCU pin — no lost-model alarm | `Q1` AO3400A + `D4` 1N4148W, `R38`/`R39`, pads `PZ1`/`PZ2` |
| 9 V VTX BEC | No analogue FPV supply | `U18` TPS54202 + `L5`, pads `PV1`/`PV2` |
| WS2812 level shift | 3.3 V into a 5 V strip needing ≥3.5 V — marginal | `U17` 74LVC1G17 on +5V, pads `PL1`–`PL3` |
| SWD ground reference | SWDIO/SWCLK were isolated pads with no probe ground | `TP20` (GND) and `TP21` (+3V3) |

One consequence of the 9 V BEC as built is worth repeating here: its enable comes from a
100k/22k divider off VBAT, not from a GPIO, so **the VTX rail cannot be switched off in
firmware**. See `docs/BUILD.md`.

### Still genuinely missing

| Gap | Consequence | Fix |
|---|---|---|
| **Reverse-polarity protection** | `D1` is a TVS. It clamps a reversed pack at −0.7 V until it dies, taking the board with it. | P-FET in the VBAT path — Rev B |
| **VTX power control** | 9 V is always on; no failsafe video cut, no pit mode | route `BUCK9_EN` to a spare GPIO — needs a respin |
| **`FLOW_MOTION` endpoint** | `U6.15` goes nowhere; the MCU cannot be woken by motion | spare GPIO to `U6.15` — needs a respin, harmless (the driver polls) |

### Crystal: the BOM and the sourcing note disagree

`design.py` orders `X32258MSB4SI` (**C2682774**) for `Y1`. `docs/BUYING.md` line 25
researched and vetted `SX3M8.000M20F30TNN` (**C2901556**). Those are different parts, and
only one of them was checked for stock and price.

It matters beyond bookkeeping: `C15`/`C16` are 30 pF, which with ~5 pF of stray presents
a **20 pF load** to the crystal. If the part actually fitted specifies a 12 pF load — very
common in a 3225 package — the oscillator runs hundreds of ppm slow and may not start
reliably over temperature. **Confirm the fitted crystal's CL against the 30 pF caps
before ordering.** This is the one open item that could stop a board booting.

### Companion computer: power and mounting

**There is no mechanical mounting for a companion computer on this board, by necessity.**
A Radxa Zero 3W is 65 × 30 mm and its 2×20 header alone is 50.8 mm; the board is 45.1 mm
wide. It connects through six solder pads (`P41`–`P46`: 5 V, TX, RX, PPS, RTS, GND) and
mounts separately in the airframe — a 3D-printed tray on the top plate, with a six-wire
loom to those pads.

5 V budget, from a TPS54202 rated 2 A (L2's 1.6 A rating is the real limit):

| Load | Current |
|---|---|
| STM32H743 + sensors (through the 3V3 LDOs) | 250 mA |
| microSD peak | 100 mA |
| GPS module | 50 mA |
| ELRS receiver | 100 mA |
| PMW3901 + VL53L1X | 50 mA |
| CAN transceiver | 70 mA |
| **board subtotal** | **620 mA** |
| TFS20-L rangefinder | 106 mA |
| ToF sensors | 160 mA |
| TCA9548A mux | 1 mA |
| WS2812 strip (strobe duty) | 60 mA |
| **fully-fitted load** | **947 mA** |
| **real headroom** | **653 mA** |

**Corrected 2026-09-05 — the WS2812 row was a 300 mA guess.** The honest budget is a
duty rule, not a brightness rule: nav/strobe patterns run ≤10 % average duty, so 10
LEDs × 60 mA full-white **peak** averages **60 mA**, and the 0.6 A peak itself is a
millisecond transient against a 2 A buck. A firmware pattern that breathes at high duty
circle exceeds this budget — that is a choice, not a right. (Same date: the buck's
thermal worst case dropped to **114 °C** once `theta_JA` was read from SLVSD26 as
**89.2 °C/W** instead of a guessed 120 — see `tools/check_thermal.py`.)

**Corrected 2026-09-04 — this row used to say "headroom for a companion ~2.4 A".** That
figure was `Isat 2.4 A − board-only 620 mA`, which is wrong twice: `Isat` is the
*saturation* limit, a transient rating, while a continuous load is governed by `Irms`
**1.6 A**, a thermal one; and it ignored every load beyond the board's own, which
`check_build.py`'s `LOADS_5V` has counted all along. `design.RAIL_5V` now holds the
derivation and `tools/check_modules.py` asserts against it.

- **Radxa Zero 3W** (~0.7 A peak) — powers fine from `P41`.
- **Pi 5** (needs 5 A) — **cannot be powered from this board.** It needs its own BEC off
  the battery, sharing only ground and the UART with the FC.

That is the practical argument for the Zero 2 W over the Pi 5 in the airframe, on top of
the size and weight. Develop the DSP on the Pi 5 at a desk; fly the Zero 2 W.

#### Which one actually flies — decide by measurement, not now

|  | Radxa Zero 3W | Pi 5 |
|---|---|---|
| power | 0.7 A peak | up to **5 A (25 W)** |
| **powered by this board** | **yes**, from `P41` | **no** — needs its own BEC |
| camera ports | **1** — flow *or* forward | **2** — flow *and* forward |
| CPU / RAM | 4× A53 @ 1.0 GHz / 512 MB | 4× A76 @ 2.4 GHz / 4–8 GB |
| weight | **11 g** | ~46 g + ~20 g BEC |

**The deciding question is whether the SoOP DSP fits on the Zero, and that cannot be
answered until the receiver exists.** The published Iridium work sampled at 2.4 Msps and
post-processed offline; doing it live is continuous FFT and correlation on a complex
stream. A 1 GHz A53 with 512 MB is unlikely to keep up. A 2.4 GHz A76 with 4 GB probably
can. But it depends entirely on the receiver's sample rate and how much decimation happens
before the Pi sees anything — which is a question for any future respin.

So the staging is:

1. **Now — Radxa Zero 3W.** One camera, downward, for optical flow. Powers from `P41`, weighs
   11 g, proves the whole MAVLink chain in `docs/SENSORS.md`.
2. **When the receiver exists** — measure the DSP load on the Pi 5 at a desk. If it fits on
   a Zero, keep flying the Zero. If it does not, the Pi 5 flies and needs **its own BEC off
   the battery**, sharing only ground and the UART with this board.

Budget for that possibility now: a 5 V 5 A BEC is ~£8 and ~20 g. Do not design it out.

### The cost of adding anything

Placement and routing are **generated** from `tools/design.py`. Adding a part means
re-running `gen_pcb.py`, which re-places everything from scratch and **discards the
current routing**. At 67.5% courtyard the board is also near its packing limit, so new
parts may not fit without removing something.

So: batch the additions. Decide on buzzer / VTX BEC / level shifter / SWD pads together,
add them in one edit, and regenerate once.

### Full part-by-part audit — 2026-08-26 (6-layer board)

Every entry in `design.py` checked against the PCB, the BOM and the CPL, every pad
checked for a net, and every net checked for a second endpoint.

**Components: clean.** 161 entries, 153 footprints, 115 CPL placements. The gap is
accounted for and correct:

| not in CPL / no LCSC | what they are |
|---|---|
| `TP1`-`TP21` | test points - copper, nothing to place |
| `P41`-`P74`, `PL1`-`PL3`, `PV1`-`PV2`, `PZ1`-`PZ2` | solder pads for the companion, RC, CAN, spare UART, WS2812 and buzzer looms |
| `PF1`-`PF8` | `PWR_FLAG` schematic symbols - ERC constructs with no footprint, correctly absent from the PCB |

**Unconnected pads: all genuine NC.** 40 pads carry no net, across 11 parts, and each
is a real no-connect: U2/U3 (ICM-42688-P / ICM-42605 LGA-14 spares), U6 (PMW3901
COB-28, 17 NC pins), J1 A8/B8 (USB-C SBU1/SBU2, unused on USB 2.0), U4.6, U7.8, U9.4,
U10.4, U11.5, U17.1.

`U1` pin 8 was worth confirming rather than assuming, since an unconnected MCU power
pin would be serious. It is **PC14/OSC32_IN**, the 32.768 kHz LSE input. This board
carries no LSE crystal and neither does MatekH743, so it is correctly left open. The
neighbours confirm the pinout is right: pin 6 VBAT tied to +3V3 (standard with no
backup cell), pin 7 PC13 = IMU3_CS, pin 9 PC15 = IMU1_CS.

**Single-endpoint nets: 20, and 19 are expected.** `SPI2_*`, `USART3_*`, `PWM7`-`PWM12`,
`IMU3_CS`, `MAX7456_CS`, `SPARE_ADC`, `PE1_SPARE` and the other `*_SPARE` pins are MatekH743
features this board does not populate - they exist so the hwdef namespace stays
pin-identical, and an unconnected MCU GPIO is harmless. `VCC_RF` is the SoOP RF rail,
DNP.

#### The one real gap: FLOW_MOTION

`FLOW_MOTION` (`U6.15`, the PMW3901's MOTION interrupt output) **goes nowhere** - it
has no MCU endpoint. Worth stating plainly rather than burying.

It is not a blocker. ArduPilot's PixArt driver polls the sensor over SPI and does not
use the motion interrupt, so the flow sensor works without it. The cost is that the
MCU cannot be woken by motion and must poll regardless, which on this board is what
it does anyway. Fixing it needs a spare GPIO routed to U6.15 and would need a respin; the
pin is an output, so leaving it open is electrically safe.

---
