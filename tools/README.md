# tools

Everything that checks, generates and orders the board. Run the gate with
`python3 tools/preflight.py`; see `CONTRIBUTING.md` for the workflow. The pcbnew scripts
used to place, route and tidy the board are kept separately, in `kicad-tools`.

## The gate

- `preflight.py` – runs every check and gives the verdict
- `readiness.py` – every prerequisite for ordering, what proves it, and what can't be proven here
- `fault_injection.py` – proves every gated check can fail, one injected fault each

## Checks

Each module holds a group of checks. Run one with `python3 tools/check_<group>.py CHECK`;
with no check name it lists what it has.

| Module | Checks |
|---|---|
| `check_board.py` | backside, connectors, floorplan, placement, power_cut, silk_owner, traces, model_alignment, cpl, footprints, libraries |
| `check_circuit.py` | design, topology, electrical, esd, ratings, symbol_pinout, pin_semantics, thermal |
| `check_mech.py` | mechanical, fit, build, cad_fit, cables, prints, balance |
| `check_firmware.py` | hwdef, params, features, bdshot, soop_backend, sitl, soop_sitl |
| `check_soop.py` | max2112, antenna, dsp, burst, ephemeris, sgp4, solver, nav, spice |
| `check_order.py` | stock, variants, bundle, purchase, links, modules, module_wiring, payload, bench_bounds, rf, doc_figures |

## Generators

- `gen_bom.py` – BOM and pick-and-place for JLCPCB, from design.py and the placed board
- `gen_doc_tables.py` – the tables in sitl/README.md and docs/HARDWARE.md
- `gen_hwdef.py` – the ArduPilot hwdef, from the vendored MatekH743 reference
- `gen_pinmap.py` – docs/PINMAP.md from the hwdef and `navcore_deltas.json`
- `gen_padmap.py` – docs/img/padmap.svg, every solder pad and test point
- `gen_sch.py` – NAVCORE-SoOP.kicad_sch from design.py
- `gen_scad_frame.py`, `gen_scad_mounts.py`, `gen_scad_plugs.py` – cad/frame.scad, mounts.scad and plugs.scad
- `jlc_orientation.py` – each part's JLCPCB rotation, from JLCPCB's own footprint
- `parse_frame_dxf.py` – the frame's flat pattern into cad/frame-dxf.json
- `record_sitl_result.py` – sitl/sitl-results.json from a fresh scenario run
- `sync_lcsc_props.py` – the LCSC field on every symbol and footprint; `--write` fixes drift
- `windowpane_paste.py` – splits an exposed pad's paste into an aperture array

## Design model and helpers

- `design.py` – components, nets, outline and pinout: the source everything else reads
- `cables.py` – every lead: its route, and the length to buy
- `dimensions.py` – the dimensions needed to buy a frame and hardware, measured from the board
- `fasteners.py` – every threaded joint and the stack its length comes from
- `fplib.py`, `symlib.py` – read footprints and symbol libraries
- `pcbutil.py` – small pcbnew helpers shared by the checks
- `jlcpaths.py` – where the JLC part libraries live
- `hwdef_pinmap.py` – parses an ArduPilot hwdef into {pin: signal}

## Shell scripts

- `make_order_bundle.sh` – the self-contained bundle to upload to JLCPCB
- `render_boards.sh` – the tracked board pictures
- `build_firmware.sh` – real ArduPilot firmware for this board
- `export_3d.sh` – STEP and GLB, with the component models

## SoOP (Iridium Doppler navigation)

- `iridium_sig.py` – the simplex channel and this board's capture plan
- `install_soop_backend.py` – installs the SoOP GPS backend into the pinned ArduPilot tree
- `soop_scenario.py` – a simulated sky, with the truth alongside
- `soop_burst.py` – burst detection and carrier estimation from I/Q
- `soop_solver.py` – Doppler positioning, the Python reference
- `soop_bench.py` – runs a bench recording through the flight code
- `soop_sitl_test.py` – checks the SoOP fix reaches the EKF in SITL
