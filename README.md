# NAVCORE-SoOP

A 45 × 46 mm STM32H743 flight controller that drops into a SpeedyBee F405 V4 BLS 60A
30×30 stack. The aircraft navigates on its real GPS outdoors (IMU / compass / baro),
with ToF rangefinders for indoor altitude and obstacle avoidance.

**The GNSS-denied SoOP chain is split, and the two halves have different statuses.**
This paragraph used to say the whole chain was "DEFERRED", which contradicted
`docs/PARTS.csv` — where all four receiver lines are marked **`TO BUY`, qty 1** — and
`docs/BUYING.md`, which counts them as **Tier 4, ~£90, inside the active £676 total**.
Both readings were defensible and the repo held both at once. Precisely:

- **The receiver is an active purchase.** SAWbird+ IR, a 1620 MHz Iridium patch, an
  RTL-SDR and `gr-iridium` — ~£90, **no board respin**, and it is the only thing that
  turns the 180 m accuracy figure from `[L]` (literature) into `[M]` (measured on this
  hardware). It is bench work: it needs a laptop and a clear sky, not an aircraft.
- **The in-flight path is deferred**, because it needs the companion computer (Radxa
  Zero 3W) that publishes `GPS_INPUT`, and the optical flow camera is deferred with it.

So the board flies today on its real GPS. The board keeps every provision for the rest —
the RF pads `TP9`–`TP11`, the SERIAL1 companion link, and the `sitl/` harness — so
reviving the in-flight half is a companion-and-module change, not a redesign.

**Status: 6-layer, 0 DRC errors, firmware builds against ArduPilot Copter-4.7.0.**
`tools/preflight.py` reports **READY TO ORDER — 65 checks, 0 blocking**.

One connection is unrouted — `BUCK9_PH`, the 9 V VTX buck's switch node. It cannot be
closed on this placement without stranding `U18`'s ground, so **the whole 9 V block is
DNP for Rev A** (`POPULATE_VTX = False`) and nothing unrouted is manufactured. The full
measurement is in `docs/ROUTING-TODO.md`. 95 parts are placed.

## Which document answers which question

| question | document |
|---|---|
| What do I buy, from where, and what must I check first? | **`docs/BUYING.md`** — generated order sheet, blockers, pre-order checks |
| Will it physically fit? What are the dimensions? | **`docs/HARDWARE.md`** — generated frame, stack and fastener tables |
| How do I go from parts to first flight? | **`docs/BUILD.md`** — T1–T5 bring-up, in order |
| What can I hang off it, and how accurate is the navigation? | **`docs/SENSORS.md`** — payload provisions, the GNSS-denied chain, the accuracy ceiling |
| Can I add FPV / optical flow / the RF front end later? | **`docs/MODULES.md`** — one board, and everything that bolts onto it |
| How does this compare to a Pixhawk, or to open-source GPS-denied projects? | **`docs/BENCHMARK.md`** — FMUv6X, the SLAM/VIO field, and the SoOP literature |
| What is actually proven, and what is not? | **`docs/VERIFICATION.md`** |
| Which pin does what? | **`docs/PINMAP.md`** |
| Why was a superseded decision made that way? | **`docs/HISTORY.md`** — nothing there is current |

Verify everything with one command:

```bash
export JLC_LIB=/home/krystian/Code/Hardware/.libraries/jlc.pretty
python3 tools/preflight.py
```

**`tools/preflight.py` says READY TO ORDER.** `fab/ORDER.md` has the exact JLCPCB
settings, and `docs/PARTS.csv` lists everything else the aircraft needs.

Ready to **order** is not ready to **fly**, and the two are gated separately:

```bash
python3 tools/check_rf.py     # T3b bench results - computes nothing, cannot be
                              # satisfied by a board that has never been switched on
```

It fails until the four RF self-interference measurements in `docs/BUILD.md` T3b exist.
That is expected before the hardware arrives, and it is deliberately **not** an order
blocker.

Power copper is now measured by **cut capacity** — every piece of a net's copper crossing
a line between its regulator and its loads (`tools/check_power_cut.py`). That needed a
plane corridor down the east edge for `+5V`, where only 0.7 A of copper crossed between
the buck and twelve loads, and a bridge around the `+9V` island for `VBAT`, whose two
plane groups had left the 9 V buck on an island of its own.

Note before bench work: **USB does not power this board.** `VBUS` reaches only the ESD
part and a bypass cap, so `J2.2` needs a pack or a bench supply even to configure it.

**The pick-and-place file was wrong for every bottom-side part.** `gen_bom.py` wrote
KiCad's orientation straight into the CPL, but KiCad flips a footprint about its local Y
axis while JLCPCB rotates about X — so 82 of 118 parts, including both IMUs and every
sensor, were 180° out. Fixed, and verified from board geometry by `tools/check_cpl.py`,
which is deliberately separate code so a shared assumption cannot pass itself. A pin-1
overlay per side is generated for eyeballing before upload.

A full-severity DRC and `--schematic-parity` were run for the first time. That cleared 23
hole-to-hole violations (`route.HOLE_CLEAR` was looser than the board's own rule), 199
footprint/symbol mismatches, and **8 stale `Value` fields** — the board's fab drawing
still labelled `R7` as `3k24` and `R6` as `10k2`, the divider values that made a 3.32 V
rail instead of 5 V. The BOM ordered the right parts; the drawing named the wrong ones.
`docs/VERIFICATION.md` records what was fixed and what is deliberately accepted.

Two earlier blockers were found and cleared. Every power rail had been routed at 4 mil — the
battery input `J2.2` sat on no plane region at all, so every amp entered through signal
copper; `VBAT` now runs on the In4.Cu pour end to end. And `Y1` had been changed to a
part that is an **active oscillator** sharing the passive crystal's footprint, whose VDD
pin this board grounds: it would never have started.

Routing is by freerouting 2.3.0 via `tools/route_freerouting.sh`, then a closing chain
(`tools/finish.sh`) that stitches pours, escapes stranded pads and routes the
remainder. The last handful of connections needed tools that move copper already on the
board rather than only adding more — shoving traces aside, ripping and rerouting, and
in one case nudging a part 0.20 mm. See *How the last five connections were actually
closed* in `docs/LAYOUT.md`; the short version is that four of the five were blocked by
a bug in the obstacle model, not by the board.

`tools/preflight.py` is the single go/no-go gate.

**The firmware side is verified too.** `tools/build_firmware.sh` builds real ArduPilot
(bootloader + arducopter) against this board's hwdef — the only test that proves the pin
assignments, DMA allocation and flash layout are actually workable. Two defects that
every topology check had passed were found and fixed this way:

- the VL53L1X rangefinder was **held in shutdown by its own firmware** — `R13` pulls
  `TOF_XSHUT` up, and the hwdef drove it `LOW` from boot;
- **ESC telemetry was wired to a transmit pin** (`UART8_TX`) and so could never be read.

`tools/check_pin_semantics.py` now enforces pin *direction*, reset level and peripheral
role against `design.PIN_INTENT`, and `tools/check_electrical.py` checks regulator
dividers, decoupling, pull-ups and ADC scaling. Both are gates in `preflight.py`.
`docs/BUILD.md` is the function-by-function matrix, and
`firmware/NAVCORE_SoOP/defaults.parm` now ships the parameters that turn the hardware on.

A second audit pass pinned the firmware target to **Copter-4.7.0**, because ArduPilot
silently ignores a default parameter whose name it does not recognise and those names
move between releases. `tools/check_params.py` validates every shipped parameter against
that exact tree's own metadata. It also found that `RNGFND1_ADDR` defaults to 0 and is
passed straight to the I²C driver — without setting it to 0x29 the VL53L1X is never
detected.

The 9 V VTX rail is now switchable from firmware (`Q3`/`R45`/`C73`, `RELAY1_PIN 83`),
added surgically with `tools/add_part.py` rather than by regenerating the board.

Verify the offline-unverifiable list that `preflight.py` prints before paying — it
includes `Y1`'s load capacitance, which is the one open item that could stop a board
booting outright.

The stackup is the reason it routes at all:

```
F.Cu    signal      In1.Cu  GND plane     In2.Cu  signal
In3.Cu  signal      In4.Cu  power rails   B.Cu    signal
```

U1 is a 100-pin 0.5 mm pitch package: no trace can pass between its pads at any
purchasable rule (0.200 mm gap against 0.3048 mm needed), so every pin escapes outward
to a via. On four layers — two of them planes — the inner pins had nowhere to go and
the board stalled at 89%. Six layers took it to 97% in a quarter of the router time.

![top](docs/img/board-top.png)

The whole design is generated from `tools/design.py`. See `docs/LAYOUT.md` for the
current state and `docs/BUYING.md` for verified part numbers.

**The Rev B RF front end had to move off this board** — measured at 67.5% courtyard for
Rev A alone versus a ~60–65% routable ceiling. Details and consequences in `docs/LAYOUT.md`.

## Layout

```
docs/BUILD.md          ORDER TO FIRST FLIGHT - bring-up, readiness matrix, and an
                       honest answer to "will it work first time"
docs/BUYING.md         WHAT TO BUY - tiered order sheet, LCSC part numbers, BOM
                       variants, and the frame/companion research behind the choices
docs/HARDWARE.md       PHYSICAL - board and airframe dimensions, fasteners, which
                       way every connector faces, part-by-part audit
docs/SENSORS.md        SENSORS AND EXPANSION - every pad and test point, altitude
                       source, the MAVLink contract a companion must satisfy, Lua applets
docs/VERIFICATION.md   WHAT WAS ACTUALLY CHECKED - defects found, root causes, and
                       what is deliberately accepted
docs/MODULES.md        ONE BOARD - the modularity map: every later addition, what it
                       attaches to, and the two that would need a second fab run
docs/BENCHMARK.md      AGAINST THE FIELD - FMUv6X, open-source GNSS-denied projects,
                       and where the SoOP literature actually stands
docs/PINMAP.md         GENERATED - the pin-level spec the schematic must match
docs/LAYOUT.md         GENERATED - board state, design rules, what is left to do
docs/ROUTING-TODO.md   GENERATED - remaining connections
sim/                   ngspice power-stage decks and results
cad/                   3D models - GLB and STEP of the board, OpenSCAD of the whole drone
```

Eight documents, down from twenty. The merge is recorded at the top of each file so the
old names are still findable.

## The core idea

Rev A is **bit-identical to ArduPilot's `MatekH743` pinout across all 75 assigned pins**, so
stock ArduPilot binaries fly the board on day one with no firmware porting. Rev B reassigns
**5 pins** — all of them functions this airframe doesn't have (second battery, airspeed,
analogue RSSI, UART7 CTS) — to the L-band receiver. **There is no PCB change between revs.**

`docs/PINMAP.md` is generated from the vendored upstream hwdef plus `tools/navcore_deltas.json`,
so the schematic is checked against machine-readable truth rather than a hand transcription.

```bash
python3 tools/check_design.py && python3 tools/gen_sch.py \
  && python3 tools/gen_pcb.py && python3 tools/route.py        # rebuild everything
python3 tools/gen_pinmap.py                                    # regenerate the pin map
./tools/hwdef_pinmap.py firmware/reference/MatekH743-hwdef.dat # inspect upstream
./tools/hwdef_pinmap.py A.dat --diff B.dat                     # compare two hwdefs
```

## Mechanical

| | |
|---|---|
| Outline | 41.600 × 39.400 mm, R4 corners *(verified against Edge.Cuts geometry)* |
| Mounting | 30.500 mm pitch, Ø4.0 mm, M3 + silicone grommet |
| Stack-up | 6-layer, 1.6 mm, ENIG, 4 mil trace/space (JLCPCB free tier) |
| Layers | F signal, In1 **solid GND**, In2 signal, In3 signal, In4 power, B signal |
| Assembly | top side stencil + hotplate; bottom-side connectors by hot air |

## Library setup

Uses the shared `../.libraries` populated by `../add_jlc_part.sh`. `sym-lib-table` and
`fp-lib-table` are already committed here. In KiCad, add the path variable:

| Name | Path |
|---|---|
| `JLC_LIB` | `${KIPRJMOD}/../.libraries/jlc.pretty` |

> Note: the repo's `HOWTO.txt` previously documented `.libraries/footprints/jlc.pretty` and
> `JLC_LIB = .libraries` — both wrong. `add_jlc_part.sh` writes footprints to
> `.libraries/jlc.pretty/` and nests 3D models *inside* it. Fixed in `HOWTO.txt`/`README.md`;
> all 21 footprints now resolve their STEP models.
