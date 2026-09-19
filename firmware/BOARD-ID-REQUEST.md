# ArduPilot board ID request — NAVCORE_SoOP

Ready to submit. Everything below was derived from the registry itself, not from memory.

## The short version

**Request `7180`.** It is free, it is inside the range ArduPilot asks you to use, and it
sits in an existing gap rather than extending the range.

The board currently ships `APJ_BOARD_ID 9001`, which is **free but wrong to ask for**: it is
above `#7199`, and `Tools/AP_Bootloader/board_types.txt` explicitly says *"please fill gaps
in the above ranges rather than adding past ID #7199"*. There are **4544 free IDs below
7199**, so asking for 9001 invites a back-and-forth for no reason.

## What the registry actually says

Checked 2026-09-19 by fetching `Tools/AP_Bootloader/board_types.txt` from ArduPilot master.

| fact | value |
| --- | --- |
| 9001 allocated? | **No** — and no `NAVCORE`/`SoOP` entry exists |
| the range rule | 1000–19999 is **reserved for the ArduPilot bootloader**; an ID in it is allocated *"via a PR against this file"* |
| the placement rule | *"please fill gaps in the above ranges rather than adding past ID #7199"* |
| highest `AP_HW_*` ID today | **7171** (`AP_HW_TYKHO_TLS7-Wing`) |
| free IDs in 1000–7199 | **4544** |
| allocation granularity | *"if you want to reserve a block of IDs, please limit that allocation to 10 IDs at a time"* |

## Why 7180

The free runs immediately below the ceiling are **7160–7169** and **7180–7199**. Both are
legitimate gaps. `7180` is preferred because it is the gap directly below `#7199`, so it
needs no comment block and does not push the used region higher — the two vendor blocks
around it (`7170–7179` Tykho, and the next allocation) stay intact.

Requesting **one** ID is deliberate: the file asks for a maximum of 10 per allocation, and
`7180–7199` is wide enough to host two vendors, so taking one leaves room rather than
consuming the gap.

### If a different number suits them better

Any of these is equally free and the request can simply say so:

| candidate | why you might prefer it |
| --- | --- |
| **7160** | the other nearby gap, immediately below the Tykho block |
| **1241** | lowest convenient gap, if they would rather not approach the ceiling |
| **2025** | a large gap (2025–2500), first of the block, if they want room for later boards |

**Do not** propose anything above 7199, including 9001.

## The change to make in the registry

One line, added after the Tykho block:

```diff
 # IDs 7170-7179 reserved for Tykho Electronics
 AP_HW_TYKHO_TLS7V2 7170
 AP_HW_TYKHO_TLS7-Wing 7171
+AP_HW_NAVCORE_SOOP 7180
 # please fill gaps in the above ranges rather than adding past ID #7199
```

## The one-line change on this side

`BOARD_ID` in `tools/gen_hwdef.py`, which owns the generated `hwdef.dat` and `hwdef-bl.dat`
header. Change it only **after** the ID is granted, so the local bring-up ID and the
allocated one never disagree about which is which:

```diff
-BOARD_ID = 9001
+BOARD_ID = 7180
```

Then:

```bash
python3 tools/gen_hwdef.py       # regenerates hwdef.dat and hwdef-bl.dat
python3 tools/check_hwdef.py     # must print "hwdef is consistent with the netlist"
```

The project builds its firmware with `tools/build_firmware.sh`, pinned to
`Copter-4.7.0`, so the APJ is rebuilt from that.

## What else the PR and issue need

1. **The issue**, posted on `ArduPilot/ardupilot` (and on ArduPilot Discuss for initial
   feedback first — that is what the other recent board requests did). Text below.
2. **The hwdef directory**, `firmware/NAVCORE_SoOP/` here, which becomes
   `libraries/AP_HAL_ChibiOS/hwdef/NAVCORE_SoOP/` upstream. It contains `hwdef.dat`,
   `hwdef-bl.dat`, `defaults.parm` and — required, and it was missing until 2026-09-19 —
   `Readme.md`.
3. **The registry line**, as above.
4. **A build proof** — the issue body should say the hwdef builds, and this repo can back
   that with `tools/build_firmware.sh` producing a working `arducopter.apj`
   (`tools/check_hwdef.py` and `tools/check_firmware_features.py` gate it).

## Issue text

> **Request for new board ID: NAVCORE_SoOP**
>
> Hello ArduPilot team,
>
> We would like to request a new Board ID for a custom flight controller.
>
> **Board name:** NAVCORE_SoOP
>
> **MCU:** STM32H743VIT6
>
> **Target vehicles:** Copter
>
> **Sensors:**
>
> * IMU: ICM-42688-P (SPI1) and ICM-42605 (SPI4)
> * Barometer: MS5611 (I2C, 0x77)
> * Compass: external I2C compass on the GPS connector, no on-board compass
> * Logging: microSD and W25Q128 SPI flash
>
> **Intended usage:** open-source hardware / research. The board is a test platform for
> navigation without GPS, using Iridium Doppler as an absolute position source. It is not
> a commercial product.
>
> **Current status:**
>
> * Hardware: designed, fabricated files checked (DRC clean, 6 layers), boards on order
> * ArduPilot: hwdef completed and builds successfully (`Copter-4.7.0`)
> * Basic testing: not yet powered — bring-up is next
>
> **Pin compatibility:** the pinout matches the MatekH743 across all 72 assigned pins, so
> stock MatekH743 binaries run on it unmodified for bring-up. This hwdef exists to give the
> board its own ID and to describe only the hardware that is actually populated.
>
> **Requested ID:** 7180, which is free in `Tools/AP_Bootloader/board_types.txt` and fills
> a gap below #7199. Happy to take any other ID you prefer.
>
> We plan to upstream the hwdef and maintain support for this board.
>
> Thank you.
