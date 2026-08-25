# How to order NAVCORE-SoOP

Everything here is generated. Re-run `python3 tools/preflight.py` before ordering — it
must say **READY TO ORDER**, and it prints a short list of things no offline check can
confirm.

## What to upload

| File | Where |
|---|---|
| `fab/gerbers/` (zip the whole folder) | PCB gerbers + Excellon drill |
| `fab/BOM-NAVCORE-SoOP.csv` | JLCPCB assembly BOM — the default build |
| `fab/CPL-NAVCORE-SoOP.csv` | JLCPCB pick-and-place — the default build |
| `fab/*-economic.csv` | Economic assembly variant |
| `fab/*-nofpv.csv` | no-FPV variant, 9 V VTX buck omitted |

Zip `fab/gerbers/` as-is. It contains all **six** copper layers — `F`, `In1`, `In2`,
`In3`, `In4`, `B`. If an upload preview shows four, stop: the power planes are missing
and the board will not work.

## Fabrication settings

| Setting | Value | Why |
|---|---|---|
| Layers | **6** | In1 is a solid ground plane, In4 carries the power rails |
| Dimensions | 45.1 × 46.1 mm | |
| Thickness | 1.6 mm | 30.5 mm stack standard |
| Outer copper | **1 oz** | The current-capacity check assumes it. 0.5 oz halves every trace's rating |
| Surface finish | ENIG | 0402s and LGA parts want a flat finish |
| Min track/spacing | **4 mil (0.1016 mm)** | Should be in the free tier. An upcharge means the rules drifted |
| Min via / drill | 0.45 mm / 0.20 mm | |
| Impedance control | No | USB is a plain differential pair — see the Rev B notes |

## Quantity, and why

**Order 5 bare boards and have 2 assembled.** Five is the multilayer minimum; two is the
usual SMT assembly minimum (confirm in the quote tool). The three spare bare boards cost
almost nothing and give you something to practise rework on.

Assembling 2 rather than 5 is the cheapest route to a working board, **not** the cheapest
per board — the extended-part feeder fee is charged per BOM line **per order**, not per
board, so it does not shrink with quantity:

| | 2 assembled | 5 assembled |
|---|---|---|
| Components (~$62/board) | ~$124 | ~$310 |
| Extended-part fees (~$3 × ~25 lines) | ~$75 | ~$75 |
| Setup | ~$8 (often covered by their monthly $9 SMT coupon) | ~$8 |
| Bare PCBs + shipping | ~$60 | ~$60 |
| **Total** | **~$270** | **~$455** |
| **Per working board** | **~$135** | **~$91** |

## Parts worth checking before you pay

Stock was captured 2026-08-23 and moves. The thin ones:

- **PMW3901** (C43496881) was falling ~57/day. If it is gone, `PAW3902JF` fits the same
  28-pin footprint and is the better part — or leave it unpopulated, since the flow
  sensor is not needed to fly.
- **`Y1` must be `C2682774`** — a *passive crystal*, CL 20 pF. The visually identical
  `C2901556` is an **active oscillator**: same SMD3225-4P land pattern, but pin 4 is VDD,
  which this board grounds. Substituting it gives a board that never starts.

## The ESC connector pinout

`J2` is wired **1 GND, 2 VBAT, 3 M1, 4 M2, 5 M3, 6 M4, 7 CUR, 8 TEL** (pins 9/10 are the
shell tabs). Betaflight's board page for the SpeedyBee F405 V4 gives the same FC-side
order, so this **matches**.

That table needs reading carefully, which is why it is worth writing down: it lists the FC
labels and the ESC labels side by side, and they look mismatched — `GND` against `N/A`,
`BAT` against `CURRENT`. They are the two ENDS of the cable, listed in opposite order,
because the connectors face each other. Reverse the ESC column and every pair lines up:
`GND↔GND`, `BAT↔VBAT`, `M1↔S1`, `M2↔S2`, `M3↔S3`, `M4↔S4`, `CUR↔CURRENT`.

**Confirm it with a continuity check anyway** before first power-up — one automated read
of a wiki table is not the same as measuring the cable you actually received. And if it
ever does disagree: an 8-pin JST-SH cable is re-pinnable. Lift the small metal tab on the
housing with a fine pick, slide the contact out, and reinsert it in the right position. A
pinout mismatch costs a cable rework, not a respin.

## Recommended current order

Use the Economic files unless the JLCPCB quote tool rejects the chosen parts:

```text
Gerbers: fab/gerbers/                 (zip the folder contents)
BOM:     fab/BOM-NAVCORE-SoOP-economic.csv
CPL:     fab/CPL-NAVCORE-SoOP-economic.csv
PCB:     6 layers, 1.6 mm, ENIG, 1 oz outer copper
Quantity: 5 bare boards, 2 assembled
DNP:     U3, U6, U7 in the Economic assembly
```

The Economic BOM/CPL pair must be selected together. Do not mix the default BOM with the
Economic CPL, or vice versa. If you choose Standard/panelised instead, use the unsuffixed
BOM/CPL pair and confirm that JLC's panel preview preserves the board orientation and
breakaway rails.

## After it arrives

The bootloader goes on over **SWD before USB does anything** — see the bring-up order in
`docs/DRONE-READINESS.md`. You need an ST-Link V2 and fine wires or pogo pins on
`SWDIO`/`SWCLK`, with `TP20` (GND) and `TP21` (+3V3) as the probe's reference.


## The `J2` ESC pinout — RESOLVED 2026-08-28

Previously open because SpeedyBee publish the order only as a diagram. Extracted from
their own manual (`speedybee-f405v460a-stack-manual-en.pdf`, "Soldering pads definition"):

| pin | FC side | ESC side |
|---|---|---|
| 1 | `GND` | `GND` |
| 2 | `BAT` | `VBAT` |
| 3 | `M1` | `S1` |
| 4 | `M2` | `S2` |
| 5 | `M3` | `S3` |
| 6 | `M4` | `S4` |
| 7 | `CUR` | `CURRENT` |
| 8 | `TEL` | **`N/A`** |

**This board's `J2` matches the FC side exactly** — `1 GND, 2 VBAT, 3 M1, 4 M2, 5 M3,
6 M4, 7 ESC_CUR, 8 ESC_TEL`. No cable rework needed. Connector is JST-SH 1.0 mm, 8-pin,
and SpeedyBee ship a 25 mm and a 75 mm cable in the box.

Still worth a continuity check on the cable you receive, but the design is confirmed
correct rather than assumed.

### Pin 8 has nothing to talk to on this ESC

The ESC end of pin 8 is **`N/A`**. "BLS" is BLHeli_S, and stock BLHeli_S has no
telemetry output at all. `SERIAL5_PROTOCOL 16` and the `UART8_RX` wire are correct and
cost nothing, but they will receive nothing until a telemetry-capable ESC (BLHeli_32,
AM32) is fitted.

The practical consequence is the harmonic notch: `INS_HNTCH_MODE 3` needs RPM. The board
therefore ships **mode 1 (throttle)**, which works with any ESC. To get RPM-tracked
filtering, flash **BlueJay** or **AM32** onto the ESC (over BLHeli passthrough, which
`SERVO_BLH_AUTO 1` already enables), set `SERVO_BLH_BDMASK 15` for bidirectional DShot on
motors 1-4, then set `INS_HNTCH_MODE 3`.
