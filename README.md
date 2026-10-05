# NAVCORE-SoOP

[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A 46.5 × 47.2 mm, 6-layer STM32H743 flight controller that navigates without GPS using the Doppler shift of Iridium satellites. It runs ArduPilot with a MatekH743-compatible pinout and also carries the avionics for a TVC rocket lander. Made by Krystian Filipek for my GNSS-denied drone and the Cambridge University Spaceflight Lander Challenge.

<div align="center">

![Board Top](docs/img/board-top.png)
![Board Bottom](docs/img/board-bottom.png)

</div>

## Features

### Iridium Navigation
Optical flow and visual-inertial odometry drift without bound over long flights. Iridium NEXT satellites orbit at ~780 km and ~7.5 km/s and transmit continuously at 1616-1626.5 MHz, so the Doppler shift of their bursts gives an absolute position with bounded error (typically 100-200 m) that complements the faster inertial sensors.

- **L-band Receiver** - MAX2112 direct-conversion tuner and OPA2374 baseband filter into the ADCs
- **Antenna Feed** - MMCX port with a current-limited 5 V feed for the active antenna, reported as open, ok or short
- **On-board Navigation** - burst detection, SGP4 orbits and the position solve run on the H743 and feed ArduPilot's EKF as a GPS
- **Spoofing Check** - the real GPS is checked against the Iridium-only fix before it is trusted

### Hardware
| Subsystem | Components |
|-----------|------------|
| MCU | STM32H743VIT6, Cortex-M7 @ 480 MHz, 2 MB flash, 1 MB RAM |
| IMUs | ICM-42688-P (SPI1) and ICM-42605 (SPI4) on a separate low-noise 3.3 V rail |
| Barometer | MS5611 on I2C2 |
| Storage | W25Q128 flash for the orbit catalogue, microSD over SDIO |
| Power | 3S-5S input, TVS and reverse-polarity protection, two LMR33630 bucks (5 V 1.6 A system, 5 V 2.1 A payload) and three 3.3 V LDOs |
| Connectors | Latching JST-GH on every cable port, two servo headers, MMCX, USB-C, TC2030 SWD pads |
| Protection | ESD clamp on every cable-facing signal, series resistors on the motor, telemetry, current, lidar and servo lines |

### Layer Stackup
```
F.Cu:   RF, crystals, MCU fanout
In1.Cu: Continuous ground plane
In2.Cu: SPI, SDIO and I2C
In3.Cu: UARTs, PWM and slow I/O
In4.Cu: Power planes (+5V, +5V_PAYLOAD, +3V3, VBAT)
B.Cu:   Sensors, RF receiver, DroneCAN, bucks
```

### Supported Platforms
- **GNSS-denied Quadcopter** - 30.5 mm stack mount, DShot ESC on `J2`, optical flow on `J14`, lidar on `J11`, companion computer on `J21`, DroneCAN on `J6`
- **TVC Rocket Lander** - two servo outputs (`J17`, `J23`) on the payload rail and 6-DoF logging to microSD

### How It Compares
| | NAVCORE-SoOP | SpeedyBee F405 V4 | Matek H743-SLIM V3 | Pixhawk 6C |
|---|---|---|---|---|
| MCU | STM32H743 | STM32F405 | STM32H743 | STM32H743 + F103 |
| IMUs | ICM-42688-P + ICM-42605 | ICM-42688-P | ICM-42688-P + ICM-42605 | ICM-42688-P + BMI088 |
| Input | 3-5S | 3-6S | 2-8S | power module |
| Port ESD | every cable signal | none stated | none stated | none stated |
| Position without GNSS | Iridium Doppler, 100-200 m | none | none | none |

It has no OSD and no 9-12 V video rail, and it takes 5S at most.

## Getting Started

### Prerequisites
- **KiCad 9** with the `pcbnew` Python module
- **Python 3** with `pip install -r requirements.txt`
- **ArduPilot toolchain** for the firmware (`tools/build_firmware.sh` pins Copter-4.7.0)

### Checking the Board
1. Clone the repository:
   ```bash
   git clone https://github.com/kfilipekk/iridium_drone.git
   cd iridium_drone
   ```

2. Run KiCad's own checks:
   ```bash
   kicad-cli pcb drc --severity-error NAVCORE-SoOP.kicad_pcb
   kicad-cli sch erc NAVCORE-SoOP.kicad_sch
   ```

3. Run the board checks:
   ```bash
   python3 tools/check_design.py
   python3 tools/check_connectors.py
   python3 tools/check_power_cut.py
   python3 tools/check_ratings.py
   ```

4. Build the firmware:
   ```bash
   bash tools/build_firmware.sh
   ```

### Ordering
The JLCPCB files are in `fab/`: the Gerber and drill bundle, BOM, pick-and-place and schematic PDF. Order 6 layers, 1 oz outer copper, no impedance control, epoxy-filled and capped vias, ENIG, and top and bottom assembly.

## Repository Structure

```
├── NAVCORE-SoOP.kicad_pcb   # PCB
├── NAVCORE-SoOP.kicad_sch   # Schematic, generated from tools/design.py
├── fab/                     # JLCPCB order files
├── firmware/                # ArduPilot hwdef, the SoOP backend and the on-board navigation
├── tools/                   # Design model, generators and checks
├── cad/                     # OpenSCAD airframe and clearance models
├── sim/                     # SPICE decks for the analogue blocks
├── sitl/                    # ArduPilot SITL scenarios
└── libraries/               # Footprint and symbol libraries
```

## Applications

I made this project to explore:
- Navigation from signals of opportunity instead of GPS
- Six-layer mixed-signal PCB design with an RF front end
- ArduPilot drivers and EKF integration
- Automated checks for a hardware design

## Future Plans

- Bench-test the Iridium receive chain with the HC610 antenna
- Rev E: a third IMU, 6S input and a 9-12 V video rail

<div align="center">

Developed by [kfilipekk](https://github.com/kfilipekk)

</div>
