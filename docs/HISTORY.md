# NAVCORE-SoOP — the record of superseded decisions

**Nothing here is current. Do not act on any of it.**

This file exists because the *reasoning* behind a superseded decision is often worth more
than the decision — it is why this project stopped trusting reseller spec tables, why it
stopped assuming a part number, and why several checks exist at all. Keeping it inline in
the live documents was the problem: those are read to make decisions, and superseded
research sitting next to current guidance is how a settled question gets reopened.

Each section says what replaced it and where the live answer now lives.

## Terminology: "Rev A" and "Rev B" were retired on 2026-09-04

Text below this line still uses them. Read it with the following in mind, because the
labels were **ambiguous, not merely old**:

- **"Rev A"** meant the board itself. There is only ever one board, so it is now just
  *the board*, or *the default configuration* when the contrast is with firmware.
- **"Rev B"** meant **two incompatible things at once**. `docs/PINMAP.md` defined it as a
  *firmware* change costing nothing — five pins repurposed, every one already reaching a
  pad. Sixteen other places used it for a **future fabrication run** costing ~$190 and a
  lead time. The same word therefore covered a free reflash and a respin, which
  systematically understated cost wherever the second sense was meant.
- **"Rev C"** appeared briefly for the respin sense, which only added a third label to a
  problem caused by having labels at all.

The live answer is `docs/MODULES.md`: **one board**, plus a map of what attaches to it and
which two items would genuinely need another fabrication run. The firmware sense is now
called **the SoOP configuration**; the silicon sense is called **a respin**.

| superseded | replaced by |
|---|---|
| GEPRC Mark4 frame research | **TBS Source One V5 7in DC**, geometry from the manufacturer DXF — `design.FRAME`, generated table in `docs/HARDWARE.md` |
| Orange Pi Zero 2W companion | **Radxa Zero 3W**, currently deferred — `docs/SENSORS.md` |
| LCSC stock snapshots, 2026-08-26 and 2026-08-28 | **`tools/check_lcsc_stock.py`** — live, all 48 codes |
| 8 × VL53L1X ToF ring + TCA9548A mux | **LDROBOT LD06 360° lidar**, `PRX1_TYPE 16` — `docs/SENSORS.md` |

---

# Superseded: LCSC stock snapshots

These were dated captures, taken before `tools/check_lcsc_stock.py` existed. That tool
now checks every BOM code against JLCPCB's own parts library and reports live stock, so
these numbers are not merely old — they are a duplicate of something answered better.

They are kept for one reason: the 2026-08-28 entry recorded **two critical parts moving**,
which is the evidence that stock is volatile enough to be worth re-checking before every
order. That lesson is why the tool exists.

### Stock re-check — 2026-08-26

Re-verified the parts that were thinnest or most expensive. Three days on from the
original capture:

| Part | LCSC | 2026-08-23 | 2026-08-26 | US$ then → now | |
|---|---|---|---|---|---|
| PMW3901MB-TXQT | C43496881 | 596 | **424** | 4.96 → **5.98** | **falling ~57/day** |
| STM32H743VIT6 | C114409 | 1742 | 1546 | 9.41 → **6.21** | price down, fine |
| MS5611-01BA03 | C15639 | 1224 | 1224 | 5.15 | unchanged |
| ICM-42688-P | C1850418 | 3920 | 3920 | 17.01 | unchanged |
| VL53L1CXV0FY/1 | C190004 | 5732 | 5732 | 4.92 | unchanged |

**Only the PMW3901 is a real risk.** It lost 172 units in three days at a rising
price; at that rate the line runs dry in roughly a week. Two ways out, and the board
needs no change for either:

1. **Buy the flow sensor now**, separately from the PCB order, and sit on it.
2. **Fit the PAW3902JF instead.** The 28-pin PixArt footprint accepts both - that
   was the point of choosing it. The PAW3902 is the better part anyway (9 lux vs
   60 lux, 6 mA vs 9 mA); it was not the default only because of stock at the time.

Worth remembering what this part is actually for. It is **not** the primary flow
source - the plan is explicit that neither PMW3901 nor PAW3902 fixes grass, because
the failure is texture self-similarity through a 30x30 pixel sensor, not low light.
It earns its place as a zero-compute fallback over tarmac, concrete and indoors, and
as redundancy if the companion computer drops out. If it is unobtainable when you
order, **the board still works without it** - leave it unpopulated and rely on the
camera flow path over the companion port.


### The crystal: this table used to name the wrong CLASS of part

This row previously read `SX3M8.000M20F30TNN` (**C2901556**), and `design.py` was changed
to match it. **That part is an active oscillator, not a passive crystal.**

It matters far more than a sourcing nit, because the substitution is invisible: an XO
shares the SMD3225-4P land pattern, so it drops into the same footprint. But in that
package an oscillator is pin 1 OE, pin 2 GND, pin 3 OUT, pin 4 VDD — and this board ties
pins 2 and 4 to ground and runs `OSC_IN`/`OSC_OUT` to pins 1 and 3. The oscillator's
supply would be grounded. The board would not start, and nothing about the symptom would
point at the BOM.

The correct part is the one the design was drawn for, `X32258MSB4SI` (**C2682774**): a
passive crystal, **CL 20 pF**, 120 Ω ESR — and cheaper and better stocked than the part
that briefly replaced it ($0.093 with 52 080 in stock, against $0.41 and 40 699).

`C15`/`C16` at 30 pF are correct for a 20 pF part: matched caps present C/2 plus ~5 pF of
stray. `design.py` now derives them from `Y1_CL_PF`, and `tools/check_electrical.py`
enforces three things — that the caps match the declared CL, that `Y1`'s LCSC code is on
the `Y1_PASSIVE_LCSC` allowlist, and that pins 1/3 carry `OSC_IN`/`OSC_OUT` with 2/4 on
ground. Any of those failing is now an error rather than a surprise on the bench.


### Stock re-check — 2026-08-28  ⚠ TWO CRITICAL PARTS MOVED

Checked live, two days after the 2026-08-26 capture above. **Both of the parts the board
cannot be built without have moved against us**, which is exactly why this gets re-checked
at order time rather than trusted from a spreadsheet.

| Part | LCSC | 08-26 | **08-28** | action |
|---|---|---|---|---|
| STM32H743VIT6 | C114409 | 1546 | **out of stock / thin** | **substitute `C5271084`** |
| ICM-42688-P | C1850418 | 3920 | **out of stock** | see below |

#### The MCU has a clean substitute

`C5271084` is **STM32H743VIT6TR** — the same silicon in tape-and-reel packaging rather
than tray. In stock, and *cheaper* at about $7.66 against $10-12 for the tray part. Same
LQFP-100 footprint, no design change. There is no reason to prefer the tray code.

#### The IMU does not, and this one matters

`C1850418` is the genuine TDK part and it is out. The relabels noted above — `-HXY`
(C46550687) and `TOKMAS` (C54308212) at around a fifth of the price — are unverified
silicon, and **an IMU is the one part where a counterfeit costs an airframe**, so that
recommendation stands: genuine on the board that flies.

Options, in order of preference:

1. **Check JLCPCB's own parts library, not LCSC.** Assembly draws on JLCPCB inventory,
   which is stocked separately. A part can be out at LCSC and available for assembly.
   This could not be confirmed from here - their search is JavaScript-rendered - so check
   it when you upload the BOM. **JLCPCB flags unavailable parts at upload**, which is the
   authoritative answer.
2. **Fly on `U3` alone.** The board carries a second IMU, the ICM-42605 (`C2655099`) on
   SPI4, and ArduPilot flies happily on one. That was already the argument for hand-fitting
   `U3` first as hot-air practice; it doubles as insurance here.
3. Wait for restock, or accept a relabel on a spare board that is not going to fly.

**Neither of these is a design problem.** The footprints are unchanged and the hwdef
already supports both IMUs. It is purely a purchasing question, and it is the reason the
"cannot be checked offline" list in `preflight.py` has always led with LCSC stock.

### The IMU substitution — researched 2026-08-28, and it is an upgrade

`ICM-42688-P` (`C1850418`) went out of stock at LCSC. It is the primary IMU, so this was
the one part on the critical path. It turns out not to be a problem at all.

`AP_InertialSensor_Invensensev3` drives **eight** parts, and this board's footprint —
`jlc:LGA-14_L3.0-W2.5-P0.50-TL` — is common to the family:

| part | LCSC | stock | US$ | hwdef string | |
|---|---|---|---|---|---|
| **ICM-45686** | `C22459454` | **6,828** | **11.84** | `SPI:icm45686` | **recommended** |
| ICM-42670-P | `C3288646` | 7,695 | **2.20** | `SPI:icm42670` | cheapest; lower spec |
| IIM-42652 | `C2988404` | ? | 9.77 | `SPI:iim42652` | industrial sibling |
| ICM-42605 | `C2655099` | yes | 3.28 | `SPI:icm42605` | **already fitted as `U3`** |
| ICM-42688-P | `C1850418` | **OUT** | 17.96 | `SPI:icm42688` | the current line |

**The ICM-45686 is the pick.** It is a newer generation with lower noise than the 42688,
it is in stock, and at $11.84 it is **cheaper than the part it replaces**. LCSC lists its
package as `LGA-14 (3x2.5)` — this board's exact footprint. `SPI:icm45686` appears in
**25 shipping ArduPilot board definitions**, so the driver path is well travelled.

#### Substituting is two lines and no PCB change

```
tools/design.py      U2: "C1850418" -> "C22459454", value ICM-42688-P -> ICM-45686
tools/gen_hwdef.py   IMU Invensensev3 SPI:icm42688 -> SPI:icm45686
```

Both must move together, and `check_hwdef.py` fails if they disagree. The rotation
(`ROTATION_ROLL_180`) is a property of how the part sits on the board, not of which part
it is, so it does not change.

#### Why this has not been applied yet

`C1850418` is out at **LCSC**. JLCPCB assembly draws on **JLCPCB's** inventory, which is
stocked separately and can only be checked at BOM upload. If they have the 42688, nothing
needs to change. If they do not, the line above is the fix — and it is worth considering
on the merits regardless, since the ICM-45686 is a better part for less money.

#### Also verified while looking

- **Motor: 41 g, M3 19×19 mm bolt pattern** (BrotherHobby Avenger 2806.5). Earlier notes
  assumed 45 g and 16×16 — **landing skids must be the 19×19 pattern.**
- **Ground truth for SoOP validation needs no purchase.** The fitted M10 GPS at 2–3 m
  against a 20–30 m SoOP solution is already an order of magnitude better. RTK would only
  be justified if SoOP accuracy improved past ~5 m.

---


---

# Superseded: frame and companion order research

The frame research below concluded on the **GEPRC Mark4**. That was replaced by the
**TBS Source One V5 7in DC** for a reason worth remembering: three reseller spec tables
disagreed with each other and with the original listing, and GEPRC's own product pages
404'd. The Source One is open-source hardware whose DXF is published, so every dimension
became answerable in CAD before ordering rather than with calipers afterwards.

The companion research concluded on the **Orange Pi Zero 2W**. That was rejected on a
hard fact found late: **it has no MIPI CSI connector at all**, so the camera plan it was
chosen for could not work.

## Frame and companion order research


**Date:** 2026-09-02 — **BOTH conclusions superseded the same day.** The companion is not the Orange Pi and the frame is not a Mark4; see the two notes below. Kept as the record of what was researched and why it was insufficient.  
**Purpose:** identify the cheapest frame that is sufficiently documented for the NAVCORE-SoOP aircraft, and record the first ordering step without pretending that missing dimensions are verified.

> ## SUPERSEDED: the frame is not a Mark4 either
>
> This document's frame conclusion has also been replaced, and for the reason the document
> itself keeps circling: **it could never obtain a manufacturer drawing.** It settled on
> the GEPRC Mark4 as "the best documented candidate", cross-checked three reseller spec
> tables that disagreed, and still ended with "the listing does not give the standoff
> spacing — the one number that would settle FC fit outright", plus a seller questionnaire
> to send before buying.
>
> The frame is now the **TBS Source One V5 7″ DC (£35.90,
> [HobbyRC UK](https://www.hobbyrc.co.uk/tbs-source-one-v5-7-dc-frame), in stock)**, which
> is **open-source hardware**: its DXF and DWG are published at
> [tbs-trappy/source_one](https://github.com/tbs-trappy/source_one). Every dimension is
> answerable in CAD before ordering. The 30.50 mm and 20.00 mm stack patterns were parsed
> straight out of `So1-V6-7inDC-2025-JUL-07.dxf`, independently of any retailer.
>
> It also improves every margin that mattered: stack clearance **2.7 → 7.7 mm**, motor
> screw engagement **5.5 → 4.5 mm** into the boss, prop gap **+30.8 → +48.5 mm**.
>
> **The lesson worth keeping from this document is the one it demonstrates by failing:**
> a frame chosen from listings cannot be verified, however many listings you cross-check.
> Choose one that publishes CAD. The comparison table below is still a fair record of what
> was available and what each source claimed — read it as history.

> ## SUPERSEDED: the Orange Pi Zero 2W is not the companion
>
> This document researched the Orange Pi Zero 2W and correctly listed its camera
> interface as **unconfirmed**. It has since been confirmed — and the answer is that the
> **Orange Pi Zero 2W has no MIPI CSI connector at all.** The 24-pin "function" connector
> sitting where the Pi Zero's CSI socket would be carries 10/100 Ethernet, 2× USB 2.0,
> TV-out, audio, IR and button lines, and **no CSI lanes**
> ([CNX Software](https://www.cnx-software.com/2023/09/09/orange-pi-zero-2w-raspberry-pi-zero-2w-alternative-4gb-ram/),
> [Hackster](https://www.hackster.io/news/orange-pi-launches-its-zero-2w-single-board-computer-offering-faster-clocks-and-eight-times-the-ram-07f6aa4e0284);
> orangepi.org was unreachable when this was checked, so both sources are secondary — but
> they agree, and they agree about an absence).
>
> The OV9281 global-shutter camera feeding optical flow is the first link in this
> aircraft's navigation chain. A companion that cannot take it on its native interface
> cannot do the job, so the companion is **back to the Raspberry Pi Zero 2 W** — which
> also gains a published 58.0 × 23.0 mm mounting pattern from Raspberry Pi's own drawing,
> replacing the "hole coordinates still required" gap below.
>
> A USB UVC camera on the Orange Pi's USB 2.0 remains *electrically* possible. It is not
> a substitution: different camera part, USB bandwidth and CPU cost where libcamera would
> have used hardware, and a flow pipeline scoped against Raspberry Pi OS moved to another
> kernel. If it is ever revisited it must be revisited as a design decision.
>
> **The frame research below is unaffected and still current.** Only the companion
> sections are superseded.

---

> # SUPERSEDED FROM HERE TO "Spatial verification"
>
> Everything between this line and the **Spatial verification** heading below is the
> *research record* for two decisions that have since been made, and it is kept for
> that reason only. **It is not instruction — do not act on it.** It was still written
> as live guidance ("buy the frame only after the seller confirms…", "do not yet order
> a custom Orange Pi tray"), which is how a settled question gets re-opened.
>
> | this section says | what is actually true now |
> |---|---|
> | the GEPRC Mark4 is the frame baseline | the frame is the **TBS Source One V5 7in DC**, and its geometry comes from the manufacturer's own DXF rather than reseller listings — `design.FRAME` |
> | measure the Orange Pi hole centres | the companion is the **Radxa Zero 3W**, and it is **deferred and not fitted**; it also does not fit on the top plate beside the battery — `docs/SENSORS.md` |
> | 25 mm / 35 mm of inner space | the stack is **30.3 mm** and needs a **35 mm** standoff — the generated tables in this file and in `docs/HARDWARE.md` |
>
> The live numbers are all generated now: the **order sheet** above, the **Spatial
> verification** table below, and the frame and stack tables in `docs/HARDWARE.md`.

### Executive conclusion

The best documented candidate found is the **GEPRC GEP-Mark4 HD7 / Mark4-7 7-inch frame**. It is not the cheapest listing, but multiple independent sellers agree on the geometry and the official GEPRC search result agrees with the key dimensions.

The cheapest AliExpress Mark4-style listings are approximately **US$8–25** in search results, but their exact seller, revision, contents, plate geometry, and standoff dimensions are not independently confirmed. The safer AliExpress price target for a specification-matching Mark4 is approximately **US$30–42**, depending on seller and shipping.

**Recommendation:** buy the frame only after the seller confirms the specification block below. Do not buy a custom Orange Pi tray or final fit-sensitive fasteners until the frame and Orange Pi are measured.

### Required aircraft dimensions

The frame must provide:

- 7-inch propeller compatibility.
- Approximately 295 mm motor-to-motor wheelbase.
- 30.5 × 30.5 mm M3 flight-controller/ESC mounting.
- Enough clear space for the NAVCORE board: 45.1 × 46.1 mm.
- Enough clear space for the SpeedyBee ESC: 45.6 × 44.0 mm.
- 19 × 19 mm motor mounting holes for the 2806.5 motors.
- At least 22.8 mm of usable vertical clearance for the FC stack.
- Space for a 138 × 47 × 48 mm, 615 g battery.
- ~~A top plate suitable for a separate 65 × 30 mm companion tray.~~ **Dropped.** The companion is deferred, and the top plate cannot hold it beside the battery (50 mm plate, 47 mm battery, 65 × 30 mm board) — see `docs/SENSORS.md`.
- A camera mount or enough clearance to fabricate one.
- Landing gear/skid attachment compatible with 19 × 19 mm motor hardware or a known alternative.

The companion requirements are separate (now Raspberry Pi Zero 2 W, see the note above):

- Board envelope: 65 × 30 mm, 1.2 mm thick.
- Four mounting holes, 2.75 mm dia, on a **58.0 × 23.0 mm** pattern — inset 3.5 mm from
  every edge, per Raspberry Pi mechanical drawing RP-008358-DS-1. **Resolved**; this was
  the open item that killed the Orange Pi.
- Camera: **22-pin 0.5 mm mini CSI**. Order the 22-to-15-pin Zero cable — an OV9281
  module ships with the 15-pin cable, which does not fit a Zero.
- Connector heights and the CSI ribbon exit are still undimensioned: measure the board
  before cutting a tray.
- Use a separate 5 V BEC rated for at least 3 A.

### Candidate comparison

| Candidate | Available source | Published information | Approx. search price | Confidence |
|---|---|---|---:|---|
| **GEPRC GEP-Mark4 HD7 / Mark4-7** | [official GEPRC](https://www.geprc.com/product/gep-mark4-frame/), [NewBeeDrone](https://newbeedrone.com/a/p/products/geprc-gep-mark4-hd7-dji-fpv-freestyle-frame), [Ready Made RC](https://www.readymaderc.com/products/details/86988-geprc-mark4-7-multirotor-frame) | 295 mm, 193×223 mm, 30.5/20 mm stack, 16/19 mm motor holes, 5 mm arms, 2.5 mm plates, 25 mm standoffs | US$30–42 on AliExpress search; US$47.99 at NewBeeDrone; US$50.27 at RMRC | **Highest** |
| Mark4 7-inch AliExpress listing | [item 1005005927527241](https://www.aliexpress.com/item/1005005927527241.html) | Search result says 295 mm, 5 mm arms, carbon, TPU, 30.5 mm stack; complete plate/standoff geometry not exposed | Search result did not provide a stable final price | Medium-low |
| Mark4 7-inch AliExpress listing | [item 1005006407123777](https://www.aliexpress.com/i/1005006407123777.html) | Search result says 295 mm, 193×223 mm, 121 g, 5 mm arms, 2.5 mm top/bottom/side plates | Approximately US$30–31 in search results | Medium; likely geometry match, seller details still need confirmation |
| Mark4 7-inch AliExpress listing | [item 1005006782478315](https://www.aliexpress.com/item/1005006782478315.html) | Search result says 295 mm and supports 2807/2806.5 motors; full geometry not available | Approximately US$12.43 | Low |
| Mark4 7-inch AliExpress listing | [item 1005010144247053](https://www.aliexpress.com/item/1005010144247053.html) | Search result says 295 mm and 2.5 mm top plate; other required details absent | Approximately US$21.16 | Low |
| Mark4 V2 style AliExpress listing | [item 1005010550800988](https://www.aliexpress.com/item/1005010550800988.html) | Search result says 295 mm, 5 mm arms, carbon, 7-inch | Approximately US$24.44 | Low-medium |
| MARK4 V2 style AliExpress listing | [item 1005012191958802](https://www.aliexpress.com/i/1005012191958802.html) | Search result says 295 mm and 230.35×278.52 mm, but this conflicts with the 193×223 mm GEPRC geometry | Not stable in search result | **Reject unless seller clarifies** |
| YSIDO Tiger Bee 7-inch | [item 1005006458251575](https://www.aliexpress.com/i/1005006458251575.html) | Search result says 2 mm top/bottom, 5 mm arms, 20/30.5 mm FC mounting; exact plate/standoff dimensions absent | Not stable in search result | Medium-low |
| TBS Source One V5 7-inch | Manufacturer/retailer sources found in project research | 320 mm, larger frame; 30.5 mm stack; published frame geometry varies by revision | Usually more expensive | Medium; not an exact 295 mm replacement |

### Why the GEPRC frame is the baseline

The GEPRC listing at NewBeeDrone gives the most complete consistent block:

- Frame type: H-type.
- Propeller: 7-inch.
- Motor-to-motor: 295 mm.
- Overall size: 193 × 223 mm.
- Mounting holes: 30.5 × 30.5 mm and 20 × 20 mm.
- Motor holes: 16 × 16 mm and 19 × 19 mm.
- Arms: 5 mm.
- Top plate: 2.5 mm.
- Bottom plate: 2.5 mm.
- Side plates: 2.0 mm.
- Standoffs: 25 mm.
- Frame mass: 140 g on that listing; GEPRC/RMRC search data also reports 121 g for another version.

The 121/140 g difference should be treated as a revision or kit-content difference, not silently averaged.

The Ready Made RC listing additionally says the 30.5/20 mm stack can be installed centrally or toward the rear, which is useful for the Orange Pi and battery layout.

### Orange Pi Zero 2W evidence — SUPERSEDED, kept as the record of what was checked

Authoritative Orange Pi documentation:

- [Official product page](http://www.orangepi.org/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-Zero-2W.html)
- [Official wiki](http://www.orangepi.org/orangepiwiki/index.php?title=Orange_Pi_Zero_2W)

Confirmed:

- PCB: 65 × 30 × 1.2 mm.
- Mass: 12.5 g.
- Four positioning holes, 3.0 mm diameter.
- 5 V/2 A or 5 V/3 A supply guidance.
- microSD/TF storage.
- USB-C, mini HDMI, 40-pin, and 24-pin interfaces.

Not confirmed from the official text:

- Hole centre coordinates.
- Exact connector coordinates/heights.
- A mechanically compatible camera connector and cable for the selected OV9281 module.

**That last line is the one that mattered, and the answer came back negative: there is no
CSI connector to be compatible with.** See the superseded note at the top. This is the
correct outcome of flagging it rather than assuming it — the gap was recorded honestly and
then closed, which is why the aircraft did not get built around a companion that cannot
see the ground.

The project CAD now models the Raspberry Pi Zero 2 W envelope **and** its published
58.0 × 23.0 mm hole pattern. Connector keep-outs remain omitted rather than invented.

### Battery and size assessment

The 295 mm GEPRC frame is suitable in plan view for the 138 × 47 × 48 mm, 615 g Zeee battery. The battery is not proven safe merely because its footprint fits. The following must be measured or checked in the assembly:

- Strap path and strap length.
- Battery sliding toward a prop disc.
- Battery-to-top-plate support and flex.
- Battery-to-Orange-Pi clearance.
- Battery-to-GPS/antenna/camera-ribbon clearance.
- Centre of gravity relative to the 295 mm motor square.

The 7-inch frame is preferable to a compact frame for this battery because it offers a longer central body and rear stack position. The 615 g battery will still dominate the centre of gravity and payload calculation.

### Seller message to send before purchase

> Please confirm this exact 7-inch frame variant has: 295 mm motor-to-motor wheelbase; overall plate size approximately 193 × 223 mm; 5 mm independent arms; 2.5 mm top and bottom plates; 25 mm standoffs; 30.5 × 30.5 mm M3 and 20 × 20 mm stack holes; 16 × 16 mm and 19 × 19 mm motor holes; and the complete standoff/screw hardware kit. Please also provide a dimensioned top-plate and centre-plate drawing or a photo with all hole spacings marked. Confirm whether the listed dimensions apply to the exact 7-inch variant selected.

Do not accept a generic “yes” if the seller cannot identify the exact variant.

### First ordering step

1. Order **one frame only**, preferably the documented GEPRC Mark4 HD7 variant.
2. Do not yet order a custom Orange Pi tray, final camera mount, or final motor screw length.
3. When the frame arrives, photograph and measure:
   - all plate outlines;
   - all standoff centres;
   - standoff height and diameter;
   - top-plate hole coordinates;
   - battery strap slots;
   - camera side-plate holes;
   - usable clearance around the FC/ESC stack.
4. Measure the Orange Pi hole centres and connector envelopes.
5. Update `cad/drone.scad`, `tools/design.py`, and this document.
6. Only then order custom fit-sensitive hardware.

