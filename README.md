# NAVCORE-SoOP

A 45 x 46 mm, 6-layer STM32H743 flight controller for testing navigation without GPS.

| top | bottom |
|---|---|
| ![top](docs/img/board-top.png) | ![bottom](docs/img/board-bottom.png) |

## The idea

Drones stop being autonomous the moment GPS does. The usual answer is cameras and SLAM,
which is accurate frame to frame but drifts further the longer you fly.

This board tests a different approach: working out position from the Doppler shift on
Iridium satellite signals. They cover the whole planet, they transmit continuously, and
they were never intended for navigation. A fix from them is rough, somewhere around
100-200 m in the published literature, but it is absolute, so the error stays bounded
rather than growing over time. That makes it a reasonable complement to the camera
methods, which is the thing I wanted to try.

It fits a normal 30 x 30 mm stack on a 7-inch quad and runs stock ArduPilot, because the
pinout matches the MatekH743 across all 75 assigned pins.

![assembled view](docs/img/render-iso.png)

| | |
|---|---|
| MCU | STM32H743VIT6, 480 MHz, LQFP-100 on 0.5 mm pitch |
| IMU | ICM-42688-P and ICM-42605, LGA-14, on their own 3.3 V analogue rail |
| Sensors | MS5611 baro, W25Q128 flash, microSD |
| Power | two synchronous bucks (16.8 V to 5 V and 9 V), two 3.3 V LDOs |
| I/O | USB-C, CAN, 8 UARTs, 4 x DShot, addressable LED, SWD |
| Payload | analogue I/Q pair, RSSI and PPS brought out to pads |

It ended up on six layers because of the H743. Nothing fits between its pads at any design
rule you can actually buy, so every pin has to escape outward to a via. On four layers the
inner pins had nowhere to go and the router stalled around 89%. Six layers took it to 97%.

## Status

The board is ready to order but has not been built, so nothing here has been measured on
real hardware.

```
tools/preflight.py   READY TO ORDER - 0 blocking failures, 5 warnings
tools/check_rf.py    NOT READY TO FLY - the bench measurements don't exist yet
```

The layout side is finished: no DRC errors, no ERC violations, all 479 connections on
fitted parts routed, gerbers checked against the board file, and all 48 part numbers
confirmed in stock. The thermal and RF figures are all calculated rather than measured,
which is what the second gate is about.

A couple of things that are easy to misread. The GNSS-denied part is provisioned rather
than working: the pads are on the board, but the receiver is off-board and I haven't
bought it yet. And as built this is an ordinary GPS quadcopter with room to expand, since
every optional sensor ships disabled. ArduPilot refuses to arm if something is configured
but not physically fitted, so that is deliberate.

## Verification

The design is generated from a single Python file and gated by 21 checks. Most of what I
learned came from checks that passed while the thing they were supposed to catch was
still there:

- Both buck regulators were missing their catch diode. All 64 checks passed at the time,
  because each one tested a property of something present, and a missing part has no net
  and no footprint to inspect.
- 82 of 118 parts were 180 degrees out in the pick-and-place file. KiCad flips a footprint
  about its Y axis and the assembler rotates about X.
- A clearance rule reported 114 mm of margin on a ground clearance question. It could never
  have failed, because the skids are out at the motors and the ground isn't a part in the
  model.
- A TVS diode sitting in front of two 30 V regulators clamped at 53 V. It had been chosen
  on cell count, which isn't really the question a TVS answers.

In each case the check was measuring something adjacent to the property that mattered. I
now try to break every check on purpose before trusting it, and put it back afterwards.

```bash
export JLC_LIB=/path/to/jlc.pretty
python3 tools/preflight.py     # the go/no-go gate
python3 tools/check_rf.py      # ready-to-fly; computes nothing by design
```

## Ordering

`fab/NAVCORE-SoOP-order-bundle.zip` has the gerbers, BOM and CPL for all three build
variants, plus the fab settings. `tools/make_order_bundle.sh` rebuilds it, and refuses to
run if the export doesn't contain six copper layers.

```
tools/design.py          single source of truth: board, airframe, buying list
tools/preflight.py       the gate, with 21 checkers behind it
firmware/NAVCORE_SoOP/   ArduPilot hwdef and shipped defaults
sitl/                    SITL harness for the GNSS-denied scenarios
cad/                     OpenSCAD airframe model, generated from design.py
```

The written docs are being rewritten and will go up here once they're in better shape.
