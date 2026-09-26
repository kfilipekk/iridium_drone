# tools

Everything that checks, generates and orders the board. Run the gate with
`python3 tools/preflight.py`; see `CONTRIBUTING.md` for the workflow. The pcbnew scripts
used to place, route and tidy the board are kept separately, in `kicad-tools`.

## The gate

- `preflight.py` – Production readiness gate for NAVCORE-SoOP
- `readiness.py` – Every prerequisite for ordering this board, what proves it, and what cannot be proven here
- `prove_readiness.py` – Prove the readiness manifest blocks, instead of trusting its docstring
- `audit_gate_patterns.py` – Every regex in the gate, tested against the text the tools actually print
- `fault_injection.py` – Prove every gated check can FAIL: one injected fault per tool, plus declared inline faults

## Checks

- `check_backside.py` – Does anything with a pin through the board land under a part on the other side?
- `check_bench_bounds.py` – Every "measure it at the bench" item, answered two ways: closed, or bounded
- `check_build.py` – Check the aircraft as one system, not the board as a pile of verified parts
- `check_cad_fit.py` – Geometric fit check on cad/drone.scad - the assembly, not its echo lines
- `check_connectors.py` – Every connector's opening must face off the board, with room for the plug
- `check_cpl.py` – Verify the pick-and-place rotations from board geometry, independently of what wrote them
- `check_design.py` – Validate tools/design.py before anything is generated from it
- `check_doc_figures.py` – A retired figure may not appear in a live document unless the text says it is retired
- `check_electrical.py` – Check the analogue reality: decoupling, dividers, pull-ups, protection
- `check_firmware_features.py` – Assert that the features defaults.parm enables are actually in the binary
- `check_fit.py` – The bolted joints, checked as joints rather than as prose
- `check_footprints.py` – Every footprint's pad count, against JLCPCB's own joint count for that part number
- `check_hwdef.py` – Cross-check the generated hwdef against the netlist it is supposed to describe
- `check_lcsc_stock.py` – Check every LCSC code on the BOM against JLCPCB's own parts library
- `check_libraries.py` – The vendored JLC library is present, complete, and identical to the board it rebuilds
- `check_links.py` – Buying links: recoverability offline, liveness online
- `check_mechanical.py` – Mechanical fit of the board in the stack and the frame
- `check_model_alignment.py` – Check that every component's 3D body sits on its own footprint, measured in the exported GLB - the thing the 3D viewer and the renders actually draw
- `check_module_wiring.py` – Can each module be plugged in without modifying another module's cable?
- `check_modules.py` – Assert design.MODULES against the real board
- `check_order_bundle.py` – The order bundle matches the board that was verified
- `check_params.py` – Check that every parameter this board ships actually exists in the firmware it targets
- `check_payload.py` – Assert that the payload provisions design.PAYLOAD claims are actually still spare
- `check_pin_semantics.py` – Check that every MCU pin is wired to the right end of the thing it talks to
- `check_placement.py` – Gate 1: is the placement electrically correct, before any routing time is spent?
- `check_power_cut.py` – How much copper actually crosses between a rail's regulator and its loads
- `check_purchase.py` – Assert every interface between parts that are bought SEPARATELY
- `check_ratings.py` – Is every part actually rated for the net it is soldered to?
- `check_rf.py` – Gate ready-to-FLY on the T3b RF self-interference measurements
- `check_silk_owner.py` – Does every label on the silkscreen sit nearer its own part than any other part?
- `check_sitl.py` – The SITL suite is green, and it is green against the firmware that actually ships
- `check_soop_backend.py` – Gate the SoOP GPS backend: registered in the tree, and really in the firmware
- `check_soop_burst.py` – Gate the burst DSP: detection and carrier-frequency estimation from I/Q
- `check_soop_c.py` – Prove the on-board C solver agrees with the Python reference, and compiles for the H743
- `check_soop_ephemeris.py` – Gate the real Iridium ephemeris: SGP4 + TLE, with the TEME->ECEF frame conversion
- `check_soop_sgp4.py` – tools/check_soop_sgp4.py - Gate: C SGP4 agrees with Python sgp4.api.Satrec
- `check_soop_sitl.py` – Gate the SoOP backend's fix reaching the EKF in SITL
- `check_stock.py` – Every BOM line is buyable, and each LCSC code resolves to the part the design intends
- `check_symbol_pinout.py` – Compare every active part's symbol pinout against an authority that is not this project
- `check_thermal.py` – Thermal check for the switching regulators and the 3V3 rail
- `check_topology.py` – Assert that each IC has the external components its datasheet requires
- `check_traces.py` – Signal-integrity review of the routed copper: length, layer changes, and pair matching
- `check_variants.py` – Every BOM/CPL variant describes this board, or it does not ship

## Generators

- `gen_bom.py` – BOM and pick-and-place for JLCPCB, straight from design.py and the placed board
- `gen_doc_tables.py` – Regenerate the tables in sitl/README.md and docs/HARDWARE.md from the code
- `gen_hwdef.py` – Generate the ArduPilot hwdef for this board from the vendored MatekH743 reference
- `gen_pinmap.py` – Merge MatekH743 hwdef + NAVCORE-SoOP deltas -> docs/PINMAP.md (single source of truth)
- `gen_scad_frame.py` – Generate cad/frame.scad from design.py, so the model and the checks cannot disagree
- `gen_sch.py` – Generate NAVCORE-SoOP.kicad_sch from tools/design.py
- `jlc_orientation.py` – Solve each part's JLCPCB rotation and centre from JLCPCB's own footprint, not a table
- `record_sitl_result.py` – Record sitl/sitl-results.json from a fresh scenario run
- `parse_frame_dxf.py` – Parse the tbs Source One V6 7in DC flat pattern into cad/frame-dxf.json
- `make_box_step.py` – Emit a minimal AP214 STEP solid for a rectangular part body

## Design model and helpers

- `design.py` – NAVCORE-SoOP — single source of truth for components and nets
- `dimensions.py` – Every dimension needed to buy a frame and hardware for this board, measured from the board file rather than restated from memory
- `fasteners.py` – Every threaded joint in the aircraft, with the thickness stack each length comes from
- `fplib.py` – Read .kicad_mod footprints: body text, pad list, and courtyard extent
- `symlib.py` – Parse a .kicad_sym library into {symbol: [(number, name, type, x, y, rot), ...]}
- `pcbutil.py` – Small pcbnew helpers shared by the checks: units, design rules and zone filling
- `jlcpaths.py` – Where the JLC (LCSC/EasyEDA) part libraries live
- `hwdef_pinmap.py` – Parse an ArduPilot hwdef.dat into a canonical {pin: signal} map
- `navcore_deltas.json`

## Editing the schematic and the board in place

- `sync_lcsc_props.py` – Rewrite the LCSC property of every symbol and footprint from design.py; reports drift, `--write` fixes it. Gated: preflight runs it and blocks the order when any field disagrees (`design.lcscprops` in readiness.py).


## Silkscreen and 3D


## Shell scripts

- `make_order_bundle.sh` – Build a single self-contained bundle you can upload to JLCPCB from a phone
- `render_boards.sh` – Render the board the way the tracked pictures are made
- `build_firmware.sh` – Build real ArduPilot firmware for this board
- `export_3d.sh` – Export the board to STEP and GLB, with the component 3D models

## Routing pipeline (used by finish.sh)

- `install_soop_backend.py` – Install the SoOP GPS backend into the pinned ArduPilot tree
- `windowpane_paste.py` – Split an exposed thermal pad into a paste aperture array instead of one solid opening

## SoOP (Iridium Doppler navigation)

- `soop_burst.py` – Burst detection and carrier-frequency estimation from I/Q: the DSP the solver requires
- `soop_sitl_test.py` – Prove the SoOP backend's fix actually reaches the EKF, in SITL
- `soop_solver.py` – Doppler positioning from signals of opportunity: the solver, and proof it works
