# NAVCORE_SoOP

ArduPilot hardware definition for the NAVCORE-SoOP flight controller.

## Introduction

NAVCORE-SoOP is a 45.1 x 46.1 mm, 6-layer STM32H743 flight controller built to test
navigation without GPS. It works out position from the Doppler shift of Iridium satellite
signals, which is a rough but *absolute* fix, so the error stays bounded instead of growing
with time the way a camera or flow-based estimate does.

The board is designed so that the pinout matches the MatekH743 across all 72 assigned pins,
which means stock ArduPilot MatekH743 binaries run on it unmodified for bring-up. This
hwdef exists to give the board its own ID and to describe only the hardware that is
actually populated.

Project repository: <https://github.com/kfilipekk/iridium_drone>

## Features and Specifications

* Processor: STM32H743VIT6, 480 MHz, LQFP-100
* Flash for logging: microSD (SDMMC1, 4-bit) and a W25Q128 16 MB SPI flash used for the
  Iridium TLE catalogue
* IMUs: ICM-42688-P (SPI1) and ICM-42605 (SPI4), both on their own 3.3 V analogue rail
* Barometer: MS5611 (I2C, address 0x77)
* Compass: none on board, external I2C compass on the GPS connector
* Power: 4S input, reverse-polarity protected; internal 5 V buck and 3.3 V regulators
* Physical: 45.1 x 46.1 mm, 30.5 mm stack pattern, 1.6 mm, 6 layers

There is no on-board compass and no analogue OSD chip by design.

## Where to Buy

Not commercially available. NAVCORE-SoOP is an open-source hardware project; the design
files are in the repository linked above and there is no vendor.

## Pinout

### Connectors

| Reference | Type | Function |
| --- | --- | --- |
| J1 | USB-C | USB, ESD protected |
| J2 | JST-SH 1.0 mm 8P | 4-in-1 ESC: power, motors, current, telemetry |
| J3 | JST-GH 1.25 mm 6P | GPS and external compass |
| J4 | JST-GH 1.25 mm 6P | Telemetry |
| J5 | JST-SH 1.0 mm 4P | RC receiver |
| J8 | microSD | Logging |
| J9 | JST-SH 1.0 mm 4P | I2C rangefinders |
| J10 | JST-SH 1.0 mm 4P | Servo |
| J11 | JST-SH 1.0 mm 4P | 360 lidar |
| J12 | U.FL | SoOP antenna |

### J2, the ESC connector

| Pin | Signal |
| --- | --- |
| 1 | GND |
| 2 | VBAT |
| 3 | Motor 1 |
| 4 | Motor 2 |
| 5 | Motor 3 |
| 6 | Motor 4 |
| 7 | Current sense |
| 8 | ESC telemetry (RX only) |

This matches the Betaflight pin order for the SpeedyBee F405 V4.

## UART Mapping

| Serial | Protocol | Port | Notes |
| --- | --- | --- | --- |
| SERIAL0 | OTG1 | USB | |
| SERIAL1 | Telem1 | UART7 | Default MAVLink2, 921600 |
| SERIAL2 | Proximity | USART1 | On test pads TP5/TP6 |
| SERIAL3 | GPS1 | USART2 | Default GPS, on J3 |
| SERIAL4 | Telem2 | USART3 | On J4 |
| SERIAL5 | ESC telemetry | UART8 | RX only, pin 8 of J2 |
| SERIAL6 | Spare | UART4 | Unset by default, on pads P71-P74 |
| SERIAL7 | RCin | USART6 | CRSF/ELRS, on J5 |
| SERIAL8 | OTG2 | Not connected | |

## PWM Outputs

Four motor outputs on J2, DShot capable. `MOT_PWM_TYPE` defaults to 6 (DShot600) and the
frame is `FRAME_CLASS 1`, `FRAME_TYPE 1`.

PWM(13) on PA8 drives an addressable LED strip through a buffer, and `SERVO13_FUNCTION`
defaults to 120 for that purpose. Two PWM channels remain spare for payload use.

## RC Input

Connect the RC receiver to J5, which is a JST-SH 1.0 mm 4-pin connector carrying 5 V,
TX, RCin and GND. `SERIAL7_PROTOCOL` defaults to 23, which is CRSF, so CRSF and ELRS
receivers work with no parameter change.

For uni-directional protocols such as SBUS and FPort, set `RC_PROTOCOLS` to 1 to return to
auto-detection. This board provides no dedicated SBUS inverter or RCin pad; all RC input
arrives on the J5 UART.

## VTX Control

The board has a switchable 9 V VTX supply on pads PV1 and PV2, controlled by GPIO 83,
which is pre-configured as `RELAY1_PIN` with `RELAY1_DEFAULT 0` so it starts off.

Note that the 9 V buck feeding those pads is **not populated** on the standard build. The
rail is routed and the pads are present, but nothing on this aircraft needs 9 V, so a VTX
runs from 5 V instead. If the buck is fitted, this is a software-controlled VTX power
switch.

## GPIOs

| GPIO | Pin | Function |
| --- | --- | --- |
| 83 | PA7 | 9 V VTX supply enable, `RELAY1_PIN` |

## RSSI, Airspeed and Analog Pins

There are no user analog inputs and no airspeed pin on this board. RSSI arrives over CRSF
and requires no analog pin.

## Battery Monitoring

The board has an internal voltage sensor and takes current from the ESC's shunt on J2,
pin 7. It is intended for 4S packs.

The default battery parameters are:

* `BATT_MONITOR` = 4
* `BATT_VOLT_PIN` = 10
* `BATT_CURR_PIN` = 11
* `BATT_VOLT_MULT` = 11.0
* `BATT_AMP_PERVLT` = 25.0

`BATT_AMP_PERVLT` is derived from the ESC's published 40 mV/A scale, with no divider on
this board. It is a property of the current sensor in the ESC and will need to be adjusted
for whichever ESC is attached, or calibrated against a known load.

## Compass

NAVCORE-SoOP does not have a built-in compass, but you can attach an external compass using
I2C on the SDA and SCL pins of the J3 connector, which is the same connector as the GPS.
An external compass is the intended configuration, because a magnetometer placed on this
board would sit within a few millimetres of a 60 A ESC.

## Firmware

Firmware for this board can be found at <https://firmware.ardupilot.org> in the
sub-folder labelled `NAVCORE_SoOP`.

## Loading Firmware

This board does not ship with ArduPilot firmware or a bootloader pre-installed. Load the
bootloader over SWD first, then use the instructions for loading firmware onto ChibiOS-only
boards: <https://ardupilot.org/copter/docs/common-loading-firmware-onto-chibios-only-boards.html>

## Other Links

* Project repository: <https://github.com/kfilipekk/iridium_drone>
* Board pin map and assembly notes: in the repository under `docs/`
