# NAVCORE-SoOP Verification & Tooling

This directory contains the verification suites, hardware design models, generators, and production gating framework for the **NAVCORE-SoOP** flight controller.

The complete production gate is executed via:
```bash
python3 tools/preflight.py
```
See `CONTRIBUTING.md` for developer workflow and commit constraints.

---

## Architecture Overview

The tooling is divided into two distinct layers:

```
+-----------------------------------------------------------------------------------+
|                            NAVCORE-SoOP (This Directory)                          |
|  - Preflight Production Gate (preflight.py, readiness.py, fault_injection.py)     |
|  - Flight Controller Checks (check_board, check_circuit, check_mech, check_fw...)  |
|  - Drone Model & Harness (design.py, cables.py, fasteners.py, dimensions.py)       |
|  - SoOP Doppler Navigation Engine (firmware/soop, soop_solver, soop_scenario...) |
+-----------------------------------------+-----------------------------------------+
                                          | imports via tools/kt.py
                                          v
+-----------------------------------------------------------------------------------+
|                        kicad-tools (Generic kiCad 9 Suite)                        |
|  - Production Gate Engine (kicadtools.gate)                                        |
|  - Board Verification (check.py: geometry, backside, cpl, models, footprints)     |
|  - Fabrication & Order Bundle (fab.py: bom, cpl, stock, renders, step export)     |
|  - DC IR-Drop & Current Density Mesh Solver (irdrop.py: check, solve, export)     |
|  - Copper Adjustments & Routing (copper.py, route.py, silk.py)                   |
+-----------------------------------------------------------------------------------+
```

- **Generic Layer (`kicad-tools`)**: Found at `$KICAD_TOOLS` or `~/Code/kicad-tools`. Operates on any KiCad board reading from `tools/design.py`.
- **Board-Specific Layer (`tools/`)**: Contains physics, electronics, mechanical fit, firmware, and navigational assertions tailored specifically to this aircraft.

---

## 1. The Production Gate

The production gate enforces zero-defect manufacturing readiness before any PCB order is placed:

- **`preflight.py`**: Runs the complete verification suite (~80 seconds) and outputs a definitive `READY TO ORDER` or `NOT READY TO ORDER` verdict.
- **`readiness.py`**: The authoritative manifest of 99 prerequisites categorized into:
  - `GATED` (83 items): Hard blockers that MUST pass before sending the board to fabrication.
  - `ORDER_ACTION` (5 items): Settings that must be selected at checkout on the JLCPCB portal.
  - `BENCH` (7 items): Physical hardware and RF measurements verified during bringup.
  - `ADVISORY` (3 items): Documented engineering trade-offs (e.g. accepted decoupling capacitor distances).
- **`fault_injection.py`**: Mutation testing framework that injects deliberate faults to prove every single gated check is capable of failing if violated.

---

## 2. Check Suites

Each module contains a domain-specific group of checks. You can run individual checks during development:
```bash
# Run a specific check
python3 tools/check_circuit.py esd

# List all checks in a module
python3 tools/check_circuit.py
```

### Module Reference

| Module | Checks & What They Assert |
|---|---|
| **`check_board.py`** | **`connectors`**: Pin 1 orientations, locking tab clearances, and mating directions.<br>**`floorplan`**: Subsystem zoning (RF, power, digital, analogue separation).<br>**`placement`**: Component proximity to mounting holes, edge clearances.<br>**`traces`**: Critical high-speed net lengths, crystal stray capacitance, differential pair skew. |
| **`check_circuit.py`** | **`design`**: Schematic vs `design.py` pin and net consistency.<br>**`topology`**: Mandatory external circuitry per IC datasheet (pull-ups, bypass, bootstrap).<br>**`electrical`**: Analogue divider ratios, logic thresholds, decoupling networks.<br>**`esd`**: Clamping diodes and series resistors on all off-board cable pins.<br>**`ratings`**: Voltage, current, and ripple derating on every capacitor, diode, and FET.<br>**`symbol_pinout`**: Symbol pinout comparison against trusted upstream libraries.<br>**`pin_semantics`**: STM32 alternate function multiplexing and reset states.<br>**`thermal`**: Junction temperatures of switching bucks (U8, U20) and LDOs under full load. |
| **`check_mech.py`** | **`mechanical`**: Fastener grip lengths, thread engagements, and hole countersinks.<br>**`fit`**: 3D assembly interference detection across 350+ component pairs.<br>**`build`**: Physical assembly order, screwdriver access, and connector clearances.<br>**`cad_fit`**: Mating interfaces between printed mounts and the carbon fiber frame.<br>**`cables`**: Wiring harness route paths, bend radii, and connector terminations.<br>**`prints`**: 3D printed STL solid integrity and print-bed fit.<br>**`balance`**: Center of gravity (CG) relative to center of thrust and 45° tip-over lean angle. |
| **`check_firmware.py`** | **`hwdef`**: ArduPilot `hwdef.dat` agreement with schematic netlist pin-for-pin.<br>**`params`**: Parameter existence and sanity in ArduCopter firmware build.<br>**`features`**: Verification that enabled features link into the compiled `.apj` binary.<br>**`bdshot`**: Bidirectional DShot timer channel assignments, DMA streams, and RPM telemetry.<br>**`soop_backend`**: AP_SoOP GPS backend registration and byte footprint.<br>**`sitl`**: Validation of SITL simulated flight scenarios against shipped defaults.<br>**`soop_sitl`**: Verification that 3D SoOP Doppler fixes fuse into the ArduPilot EKF. |
| **`check_soop.py`** | **`max2112`**: MAX2112 tuner register images, PLL loop filter, and baseband bandwidth.<br>**`antenna`**: Active antenna bias-T feed monitor and current limit trip points.<br>**`dsp`**: On-board Cortex-M7 Doppler burst detector meeting the 5 Hz accuracy target.<br>**`burst`**: Synthetic burst detection and carrier estimation from raw I/Q samples.<br>**`ephemeris`**: Real Iridium TLE ephemeris propagation and constellation visibility.<br>**`sgp4`**: Agreement between Python SGP4 reference and embedded C propagator.<br>**`solver`**: Differential Doppler positioning solver accuracy against ground truth.<br>**`nav`**: GPS-denied navigation hold performance over simulated flight profiles.<br>**`gain`**: Antenna-to-ADC gain plan from the parts, with the DSP gated at both ends of its spread.<br>**`spurs`**: Board clock harmonics folded through the ADC against the Ring Alert search window.<br>**`spice`**: SPICE deck simulation of front-end analogue filter stages. |
| **`check_order.py`** | **`purchase`**: Availability and manufacturer links for every bought part.<br>**`links`**: Documentation hyperlinks and datasheet references.<br>**`modules`**: Off-board module footprint landings and connector compatibility.<br>**`module_wiring`**: Cable pinout mapping between flight controller and modules.<br>**`payload`**: Spare PWM channels, free UARTs, and payload weight budget.<br>**`bench_bounds`**: Verification of empirical bench bounds that cannot change ordering.<br>**`rf`**: RF link budget calculations for the HC610 antenna and front-end NF.<br>**`doc_figures`**: Verification that documentation diagrams match current source files. |

---

## 3. Generic Checks from `kicad-tools`

These checks are provided by `kicad-tools` and run automatically during preflight:

- **`check.py geometry`**: Flags acute corners (<90°), dangling stubs, dead copper, and micro-segments.
- **`check.py backside`**: Flags through-hole pins/leads landing underneath opposite-side SMD bodies.
- **`check.py silk_owner`**: Ensures every silkscreen label sits nearest to its own component.
- **`check.py model_alignment`**: Checks every 3D model body sits squarely on its footprint pads.
- **`check.py footprints`**: Compares board pad counts to manufacturer joint counts.
- **`check.py libraries`**: Compares project footprints to vendored library standards.
- **`irdrop.py check`**: Finite-difference 2D DC IR-drop analysis for all 9 power rails.
- **`fab.py check_bundle`**: Verifies that the order ZIP matches current Gerbers, BOM, and CPL.

---

## 4. Hardware Models & Generators

The hardware configuration is defined in single-source-of-truth Python models:

- **`design.py`**: The authoritative design definition (components, nets, outline, pinout, power budgets).
- **`cables.py`**: Cable harness lengths, wire gauges, and routing paths across the airframe.
- **`fasteners.py`**: Threaded joints, bolt lengths, standoffs, and nut stacks.
- **`dimensions.py`**: Physical frame dimensions and mounting hole spacings.

### Code & Asset Generators

- **`gen_hwdef.py`**: Generates ArduPilot `hwdef.dat` from the reference MatekH743 definition.
- **`gen_sch.py`**: Generates `NAVCORE-SoOP.kicad_sch` from `design.py`.
- **`gen_pinmap.py`**: Generates `docs/PINMAP.md` from the hwdef and `navcore_deltas.json`.
- **`gen_padmap.py`**: Generates `docs/img/padmap.svg` showing every solder pad and test point.
- **`gen_scad_frame.py`**, **`gen_scad_mounts.py`**, **`gen_scad_plugs.py`**: Generates OpenSCAD 3D models for frame plates, printed mounts, and connector plugs.
- **`parse_frame_dxf.py`**: Extracts carbon fiber frame geometry from flat DXF drawings.
- **`gen_doc_tables.py`**: Synchronizes documentation tables in `docs/HARDWARE.md` and `sitl/README.md`.

---

## 5. SoOP (Signals of Opportunity) Navigation Engine

NAVCORE-SoOP features an integrated passive radar receiver for GPS-denied navigation using Iridium satellite burst Doppler shifts:

- **`iridium_sig.py`**: Iridium simplex broadcast channel specification and capture plan.
- **`soop_scenario.py`**: Simulated satellite constellation passes and aircraft trajectories.
- **`soop_burst.py`**: Burst detection, matched filtering, and carrier frequency estimation.
- **`soop_solver.py`**: Python reference implementation of the differential Doppler positioning solver.
- **`install_soop_backend.py`**: Installs the custom `AP_GPS_SoOP` driver into the ArduPilot source tree.
- **`soop_sitl_test.py`**: End-to-end integration test confirming Doppler fixes reach the ArduPilot EKF.
- **`soop_bench.py`**: Replays captured RF bench recordings through the embedded C DSP algorithms.
