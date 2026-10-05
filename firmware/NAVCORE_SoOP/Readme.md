# NAVCORE_SoOP

ArduPilot hardware definition for the NAVCORE-SoOP flight controller.

## Introduction

NAVCORE-SoOP is a 46.5 x 47.2 mm, 6-layer STM32H743 flight controller built to test
navigation without GPS. It works out position from the Doppler shift of Iridium satellite
signals, which is a rough but *absolute* fix, so the error stays bounded instead of growing
with time the way a camera or flow-based estimate does.

The pinout follows the MatekH743 wherever the layout allowed, so stock ArduPilot MatekH743
binaries boot on it for bring-up, on one IMU (see IMU Orientation). This hwdef gives the
board its own ID, reaches both IMUs with the right rotations, and describes only the hardware
that is actually populated.

Project repository: <https://github.com/kfilipekk/iridium_drone>

## Features and Specifications

* Processor: STM32H743VIT6, 480 MHz, LQFP-100
* Flash for logging: microSD (SDMMC1, 4-bit) and a W25Q128 16 MB SPI flash used for the
  Iridium TLE catalogue
* IMUs: ICM-42688-P (SPI1) and ICM-42605 (SPI4), both on their own 3.3 V analogue rail
* Barometer: MS5611 (I2C, address 0x77)
* Compass: none on board, external I2C compass on the GPS connector
* SoOP receiver: MAX2112 L-band tuner (I2C2) and OPA2374 baseband amplifiers into ADC1/ADC2,
  with a current-limited, monitored 5 V feed to the active antenna on the MMCX port
* Power: 3S to 5S input, reverse-polarity protected; a 5 V buck for the board, a second
  switchable 5 V buck for payloads, and 3.3 V regulators
* Protection: every cable-facing signal is clamped at its connector
* Physical: 46.5 x 47.2 mm, 30.5 mm stack pattern, 1.6 mm, 6 layers

There is no on-board compass and no analogue OSD chip by design.

## Where to Buy

Not commercially available. NAVCORE-SoOP is an open-source hardware project; the design
files are in the repository linked above and there is no vendor.

## Pinout

### Connectors

Every cable port is a latching JST-GH 1.25 mm connector.

| Reference | Type | Function |
| --- | --- | --- |
| J1 | USB-C | USB, ESD protected |
| J2 | JST-GH 8P | 4-in-1 ESC: power, motors, current, telemetry |
| J3 | JST-GH 6P | GPS and external compass: 5 V, TX, RX, SCL, SDA, GND |
| J5 | JST-GH 4P | RC receiver: 5 V, TX, RX, GND |
| J6 | JST-GH 4P | CAN1: 5 V payload, CANH, CANL, GND |
| J8 | microSD | Logging |
| J9 | JST-GH 4P | I2C1: 5 V, SCL, SDA, GND |
| J11 | JST-GH 4P | SERIAL2: 5 V payload, TX, RX, GND |
| J12 | MMCX | SoOP antenna, with 5 V for its LNA |
| J14 | JST-GH 6P | SPI3 optical flow: 3.3 V, SCK, MISO, MOSI, CS, GND |
| J17 | 1x3 2.54 mm header | Servo 1: PWM7, 5 V payload, GND |
| J19 | Tag-Connect TC2030 | SWD: 3.3 V, SWDIO, NRST, SWCLK, GND |
| J21 | JST-GH 6P | SERIAL1 (UART7), Pixhawk TELEM order: 5 V, TX, RX, CTS, RTS, GND |
| J22 | JST-GH 3P | Payload 5 V for a camera or VTX |
| J23 | 1x3 2.54 mm header | Servo 2: PWM8, 5 V payload, GND |

The LED strip and the buzzer are on solder pads (5 V, data or drain, GND).

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
| SERIAL1 | Telem1 | UART7 | J21, with CTS/RTS |
| SERIAL2 | Spare | USART1 | J11 |
| SERIAL3 | GPS1 | USART2 | Default GPS, on J3 |
| SERIAL4 | Spare | USART3 | Not brought out on this board |
| SERIAL5 | ESC telemetry | UART8 | RX only, pin 8 of J2 |
| SERIAL6 | | EMPTY | Unassigned: UART4's pins carry PWM5 and PWM7 |
| SERIAL7 | RCin | USART6 | CRSF/ELRS, on J5 |
| SERIAL8 | OTG2 | Not connected | |

## PWM Outputs

Four motor outputs on J2, DShot capable. `MOT_PWM_TYPE` defaults to 6 (DShot600) and the
frame is `FRAME_CLASS 1`, `FRAME_TYPE 1`. Motors 1-2 are on TIM3 and 3-4 on TIM5, each
timer with DMA of its own, so bidirectional DShot works on all four: flash Bluejay to the
ESC, then set `SERVO_BLH_BDMASK` to 15.

PWM 5 and 6 are on test pads TP3 and TP4. PWM 7 and 8 (TIM4) are on the servo headers J17
and J23. PWM 11 and 12 are not brought out.

PWM(13) on PA8 drives an addressable LED strip through a buffer, and `SERVO13_FUNCTION`
defaults to 120 for that purpose.

## RC Input

Connect the RC receiver to J5, which is a JST-GH 1.25 mm 4-pin connector carrying 5 V,
TX, RCin and GND. `SERIAL7_PROTOCOL` defaults to 23, which is CRSF, so CRSF and ELRS
receivers work with no parameter change.

For uni-directional protocols such as SBUS and FPort, set `RC_PROTOCOLS` to 1 to return to
auto-detection. This board provides no dedicated SBUS inverter or RCin pad; all RC input
arrives on the J5 UART.

## Payload Power

A second 5 V buck feeds the payload connectors (J6, J11, J17, J22, J23) and the LED strip
pad. GPIO 83 switches it and is `RELAY1_PIN` with `RELAY1_DEFAULT 0`. The switch is inverted: pin low
leaves the rail on, so the payload is powered from boot. Setting the relay turns it off.

## GPIOs

| GPIO | Pin | Function |
| --- | --- | --- |
| 83 | PA7 | Payload 5 V rail, low = on, `RELAY1_PIN` |
| 84 | PC5 | Antenna 5 V feed enable, high = on from boot |
| 85 | PD10 | Antenna feed fault, from the load switch |
| 86 | PD11 | Not wired, pulled down (reserved for a flow sensor's motion line) |

## CAN

CAN1 is on J6 through an SN65HVD230 transceiver, with `GPIO_CAN1_SILENT` on PD3. The bus
is not terminated on the board. Fit R15 (120 ohm) if the board is at one end of the bus.

## IMU Orientation

Both IMUs are on the bottom of the board. The hwdef declares `ROTATION_YAW_180` for the
ICM-42688-P and `ROTATION_YAW_90` for the ICM-42605, worked out from the footprint pads,
with forward as marked by the silkscreen arrow.

The ICM-42605's chip select is PE11, the pin MatekH743 gives its ICM-20602, so stock
MatekH743 firmware finds only the ICM-42688-P. Check the attitude on the bench before
flying stock firmware, and set `AHRS_ORIENTATION` if it is off.

## RSSI, Airspeed and Analog Pins

There are no user analog inputs and no airspeed pin on this board. RSSI arrives over CRSF
and requires no analog pin. ADC1/ADC2 sample the SoOP receiver's I and Q, and ADC3 the
battery and the antenna feed current.

## Battery Monitoring

The board has an internal voltage sensor and takes current from the ESC's shunt on J2,
pin 7. It is rated for 3S to 5S packs.

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

This board does not ship with firmware. Hold BOOT while pressing RESET to start the
STM32's built-in DFU loader (USB ID 0483:df11), then flash the `_with_bl.hex` build following
<https://ardupilot.org/copter/docs/common-loading-firmware-onto-chibios-only-boards.html>.
J19 (SWD) is the fallback if DFU never appears.

## Other Links

* Project repository: <https://github.com/kfilipekk/iridium_drone>
* Board pin map and assembly notes: in the repository under `docs/`
