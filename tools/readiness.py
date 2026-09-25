#!/usr/bin/env python3
"""Every prerequisite for ordering this board, what proves it, and what cannot be proven
here.
"""
import os

GATED, ADVISORY, ORDER_CHECK, ORDER_ACTION, BENCH, FLY, BUILD = (
    "GATED", "ADVISORY", "ORDER_CHECK", "ORDER_ACTION", "BENCH", "FLY", "BUILD")

# ---------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------
PREREQUISITES = [
    # -- the board is the design it claims to be ------------------------------------
    dict(id="design.netlist", cls=GATED, tool="check_design.py",
         claim="the netlist matches the schematic, and every MCU pin used is declared"),
    dict(id="design.hwdef", cls=GATED, tool="check_hwdef.py",
         claim="ArduPilot's hwdef agrees with the netlist pin for pin"),
    dict(id="design.symbols", cls=GATED, tool="check_symbol_pinout.py",
         claim="every active part's symbol pinout matches KiCad's library or its datasheet"),
    dict(id="design.library", cls=GATED, tool="check_libraries.py",
         claim="the vendored library is complete and its footprints equal the board's"),

    # -- the board is physically manufacturable -------------------------------------
    dict(id="fab.drc", cls=GATED, check="DRC errors",
         claim="no blocking DRC errors"),
    dict(id="fab.erc", cls=GATED, check="ERC clean",
         claim="schematic ERC is clean"),
    dict(id="fab.routed", cls=GATED, check="all nets routed (fitted parts)",
         claim="every net with a fitted part on it is routed"),
    dict(id="fab.gerbers", cls=GATED, check="gerbers match the board",
         claim="the gerbers on disk are newer than the board file"),
    dict(id="fab.outline", cls=GATED, check="board outline",
         claim="the board outline is a closed, well-formed contour"),
    dict(id="fab.planes", cls=GATED, check="planes carry no routing",
         claim="no signal copper sits on the In1/In4 plane layers"),
    dict(id="fab.limits", cls=GATED, check="JLCPCB 6-layer limits",
         claim="track, via and drill sizes are inside JLCPCB's free-tier capability"),
    dict(id="fab.backside", cls=GATED, tool="check_backside.py",
         claim="no through-hole pin or post lands under a part on the other side"),
    dict(id="fab.silkowner", cls=GATED, tool="check_silk_owner.py",
         claim="every printed label sits nearer the part it names than any other part"),
    dict(id="fab.bundle", cls=GATED, tool="check_order_bundle.py",
         claim="the bundle you upload matches the verified BOM, CPL and gerbers"),

    # -- absence detection: the class that hid the catch diode ----------------------
    dict(id="topology.externals", cls=GATED, tool="check_topology.py",
         claim="every datasheet-required external component is PRESENT "
               "(this is the only check that can see an absent part)"),
    dict(id="topology.connections", cls=GATED, tool="check_module_wiring.py",
         claim="modules plug in without splicing cables"),
    dict(id="topology.pins", cls=GATED, tool="check_pin_semantics.py",
         claim="each pin's direction, reset level and role agree with its function"),

    # -- electrically sound ---------------------------------------------------------
    dict(id="elec.values", cls=GATED, tool="check_electrical.py",
         claim="dividers, decoupling and pull-ups are the right values"),
    dict(id="elec.ratings", cls=GATED, tool="check_ratings.py",
         claim="every part is rated for the net it sits on"),
    dict(id="elec.current", cls=GATED, tool="check_power_cut.py",
         claim="copper carries each rail's current at every axis-aligned cut"),
    dict(id="elec.traces", cls=GATED, tool="check_traces.py",
         claim="trace lengths, differential skew and crystal stray capacitance are in limit"),

    # -- mechanically sound --------------------------------------------------------
    dict(id="mech.connectors", cls=GATED, tool="check_connectors.py",
         claim="every connector's mouth faces off-board with room for its plug"),
    dict(id="mech.stack", cls=GATED, tool="check_mechanical.py",
         claim="the board, ESC and frame fit in Z"),
    dict(id="mech.interference", cls=GATED, tool="check_cad_fit.py",
         claim="no two placed parts overlap in the assembly"),
    dict(id="mech.joints", cls=GATED, tool="check_fit.py",
         claim="every bolted joint fits by declaration: pattern, hole, screw length, "
               "stack under the kit's top plate, standoff posts clear of the boards"),
    dict(id="mech.frame", cls=GATED, check="CAD frame matches design.FRAME",
         claim="the CAD frame is generated from design.FRAME, not stale"),
    dict(id="mech.screwhead", cls=GATED, check="no copper under a screw head",
         claim="no copper sits under a screw head"),
    dict(id="mech.mounting", cls=GATED, check="mounting holes",
         claim="the 30.5 mm 4-hole mounting pattern is present"),

    # -- assemblable by the fab ----------------------------------------------------
    dict(id="assy.cpl", cls=GATED, tool="check_cpl.py",
         claim="CPL rotations derived from board geometry agree with the CPL"),
    dict(id="assy.bom", cls=GATED, check="BOM matches the board",
         claim="every BOM line matches what is on the board"),
    dict(id="assy.codes", cls=GATED, check="every line has an LCSC code",
         claim="every BOM line carries a real LCSC part number"),
    dict(id="assy.paste", cls=GATED, check="exposed pads windowpaned",
         claim="every thermal slug has a vented paste array"),
    dict(id="assy.twosided", cls=GATED, check="two-sided assembly",
         claim="the bottom-side placement is stated, so you order the right stencil"),
    dict(id="assy.variants", cls=GATED, tool="check_variants.py",
         claim="every BOM/CPL variant - including the Economic pair the ordering "
               "document recommends at the checkout - matches the board, and no variant "
               "moves a part rather than omitting it"),
    dict(id="assy.padcount", cls=GATED, tool="check_footprints.py",
         claim="each footprint's pad count, package family and pitch match JLCPCB's own "
               "package string for that part, from the live parts API"),

    # -- the aircraft, as a whole --------------------------------------------------
    dict(id="build.aircraft", cls=GATED, tool="check_build.py",
         claim="power budget, mass, thrust, geometry and buses, with every value "
               "tagged [M]easured / [D]atasheet / [L]isting / [A]ssumed"),
    dict(id="build.modules", cls=GATED, tool="check_modules.py",
         claim="every module the documents claim has landing pads on the board"),
    dict(id="build.payload", cls=GATED, tool="check_payload.py",
         claim="the payload provisions the docs claim are still spare"),
    dict(id="build.purchase", cls=GATED, tool="check_purchase.py",
         claim="every buy-to-buy interface mates"),

    # -- firmware ------------------------------------------------------------------
    dict(id="fw.params", cls=GATED, tool="check_params.py",
         claim="every shipped parameter exists in the pinned firmware"),
    dict(id="fw.drivers", cls=GATED, tool="check_firmware_features.py",
         claim="every parameter's DRIVER is compiled into this board's binary, "
               "measured by linked symbol size"),
    dict(id="fw.docs", cls=GATED, check="generated doc tables match the code",
         claim="generated tables in the docs are derived from the code, not typed"),
    dict(id="fw.figures", cls=GATED, tool="check_doc_figures.py",
         claim="no retired figure is presented as current in the live documentation"),
    dict(id="fw.defaults", cls=GATED, check="default parameters shipped",
         claim="the defaults.parm that ships is the one this board needs"),

    dict(id="adv.decoupling", cls=ADVISORY, tool="check_placement.py",
         why="a PRE-routing placement guide whose limits relax once routing forces a part "
             "further from its pin. It measures distance to a pin, not electrical "
             "behaviour, so it cannot fail a board that passes check_power_cut."),
    dict(id="adv.thermal", cls=ADVISORY, tool="check_thermal.py",
         why="the junction figures are BRACKETS between the datasheet's JEDEC and EVM "
             "copper, and this board is between them. No desk calculation narrows it; "
             "T3a measures it. U19 logs the board beside U9 every flight in the meantime."),
    dict(id="adv.silk", cls=ADVISORY, check="pad silkscreen labels",
         why="an unlabelled pad costs a bench session, not a board, and a label is left off "
             "rather than printed where it would read as another part's."),
    dict(id="adv.in4rails", cls=ADVISORY, check="In4.Cu rails not fragmented",
         why="separate pours around separate pad groups, each tied to its rail - a note "
             "about shape, not a defect in connectivity."),

    dict(id="order.stock", cls=GATED, tool="check_stock.py",
         claim="every BOM line is in stock at JLCPCB in the quantity ordered, the code "
               "resolves to the manufacturer part number the design intends, and the "
               "snapshot is no older than 7 days"),
    dict(id="bench.bounds", cls=GATED, check="no bench item can change what is ordered",
         claim="every bench-only item confirms a design-side bound, sets a firmware "
               "constant, or records a bought part's property - none can require "
               "different copper"),


    # -- performed at the checkout, so they cannot be done earlier ------------------
    dict(id="act.copper", cls=ORDER_ACTION,
         claim="select 1 oz outer copper",
         why="half-ounce halves every trace's current rating and invalidates "
             "check_power_cut.py. It is a checkout setting, not a design property."),
    dict(id="act.dfm", cls=ORDER_ACTION,
         claim="accept JLCPCB's free DFM review",
         why="it is the only thing that checks pad LAND SIZE and paste apertures; "
             "check_footprints.py verifies pad count, package and pitch but not those."),
    dict(id="act.impedance", cls=ORDER_ACTION,
         claim="leave impedance control OFF",
         why="none is specified. USB is a plain differential pair, and the 1.62 GHz "
             "J12 -> U13 run is 0.10 mm track across four layers, roughly 60-90 ohm on "
             "JLC's default stack: at worst ~1.5 dB of mismatch behind the SAWbird+'s "
             "~40 dB of gain, which moves the system noise figure by ~0.02 dB. Ordering "
             "impedance control would not change the drawn geometry."),
    dict(id="act.quantity", cls=ORDER_ACTION,
         claim="5 bare PCBs / 2 assembled, BOTH sides",
         why="5 is the multilayer minimum and 2 the SMT minimum; both sides are populated "
             "so two stencils are needed."),
    dict(id="act.panel", cls=ORDER_ACTION,
         claim="Panel by JLCPCB, 2 x 2 (not a committed panel file)",
         why="Standard assembly requires a single PCB of at least 70 x 70 mm and this is "
             "45.1 x 47.3 mm, so the board must be panelled to be assembled at all. "
             "2 x 2 gives roughly 93 x 95 mm. Do NOT commit a panelised .kicad_pcb: the "
             "board files stay exactly as verified, so nothing has to be re-checked."),

    dict(id="bench.u8", cls=BENCH, bound="87 C worst case against 125 C - 38 C of margin",
         claim="U8's junction temperature under load",
         why="BOUND. The fitted LMR33630A RNX carries ONE theta_JA (72.5 C/W) rather than "
             "the old part's JEDEC-EVM bracket, so 87 C is the corner and not the top of "
             "a range. U8 was swapped for exactly this and the swap is already on the "
             "board; a reading can confirm it and cannot un-fit it.",
         refresh="runbook T3 (docs/navcore-runbook.tex Part 9)"),
    dict(id="bench.u9", cls=BENCH,
         bound="104 C peak on good copper against 150 C - 46 C of margin",
         claim="U9's board-to-junction offset",
         why="BOUND. Only the datasheet's '(No Heatsink)' corner is over, and that corner "
             "describes a 2-layer board - this one has "
             "at 7443 mm2 of GND plane and 5 vias on the output pad. What the bench sets "
             "is the offset between TEMP[0] and the junction, a constant U19 then carries "
             "forward every flight.",
         refresh="runbook T3a (docs/navcore-runbook.tex Part 10)"),
    dict(id="bench.flowyaw", cls=BENCH, bound="one of four cardinal values in defaults.parm",
         claim="FLOW_ORIENT_YAW, against the camera's actual mount",
         why="PARAM. Flow arrives as MAVLink from the off-board companion, so the board "
             "cannot encode the sign and has no pin to change. Set it from CAD, confirm "
             "it in position hold.",
         refresh="check the sign before position hold, runbook Part 14"),
    dict(id="bench.rf", cls=BENCH,
         bound="Pr >= -110 dBm at 2 dB system NF, met by the bought SAWbird+ IR",
         claim="that this antenna and front end can produce a usable Iridium fix",
         why="MODULE. sitl/ proves what ArduPilot does with a fix of a GIVEN quality; it "
             "cannot prove the receiver can produce one. But the receiver IS a bought "
             "part - the Nooelec SAWbird+ IR, >=30 dB gain with the SAW at the antenna - "
             "and a desense result is fixed by placement, ferrites and shielding. The one "
             "board-side lever, an on-board LNA+SAW, was DELETED in favour of that module, "
             "so it is not a lever any more.",
         refresh="runbook T3b (docs/navcore-runbook.tex Part 11)"),
    dict(id="bench.cameraflow", cls=BENCH,
         bound="an off-board camera's property; J4 was cut",
         claim="flow quality over real grass",
         why="MODULE. Simulated flow is perfect flow, so this needs recorded footage from "
             "the actual camera over actual ground. The camera is off-board and J4 was cut "
             "from this board, so poor flow selects a different camera.",
         refresh="record a flight, then replay it"),

    # Flies the way the firmware says it does; an ordering prerequisite ---------- not classified as FLY.
    dict(id="sitl.scenarios", cls=GATED, check="SITL scenarios pass",
         claim="defaults.parm flies the full scenario suite against simulated truth, "
               "with every prearm fault resolved"),

    # Ready to FLY only.
    dict(id="fly.rfbench", cls=FLY, tool="check_rf.py",
         bound="recorded data; asserts nothing about the board",
         claim="the T3b bench measurements are recorded and within the link budget"),

    dict(id="solver.ephemeris", cls=GATED,
         check="real Iridium ephemeris inverts the geometry",
         claim="the solver propagates real TLEs with SGP4 and recovers a known position"),
    dict(id="solver.burst", cls=GATED,
         check="burst detection and carrier estimation meet the 5 Hz target",
         claim="I/Q gives a carrier estimate inside the solver's 5 Hz target"),
    # The solve is ported to C and gated (solver.c below). What remains is not the
    # arithmetic - it is the aircraft around it.
    dict(id="build.firmware", cls=BUILD,
         claim="the flight firmware: I/Q capture, SGP4-to-ECEF framing, and the EKF hand-off on the H743",
         why="the solve and SGP4 are ported to C (solver.c, build.sgp4), but nothing yet "
             "samples the MAX2112 or hands a fix to the EKF on the aircraft."),
    dict(id="solver.c", cls=GATED,
         check="the C solver agrees with the Python reference and builds for the target",
         claim="the Doppler solve is ported to C, matches the Python reference and "
               "cross-compiles for the H743"),
    dict(id="build.sgp4", cls=GATED,
         check="C SGP4 propagator agrees with Python reference and builds for the target",
         claim="SGP4 is ported to C, tested on 80 real Iridium TLEs at ±3 days, and "
               "cross-compiled for the H743 (fpv5-d16 FPU, 4.7 kB .text)"),
    dict(id="build.ekf", cls=GATED,
         check="SoOP fix reaches the EKF",
         claim="the solved fix reaches the EKF end-to-end in SITL"),
    dict(id="ekf.backend", cls=GATED,
         check="the SoOP GPS backend is registered and compiled into the firmware",
         claim="an in-process AP_GPS backend carries the on-board Doppler fix, so the "
               "EKF route does not depend on an external computer"),
]


def evaluate(results, tool_results, today=None):
    """Walk the manifest against what actually ran. Returns a report dict."""
    import datetime
    today = today or datetime.date.today()

    by_name = {}
    for g, name, verdict, _ in results:
        by_name.setdefault(name, []).append(verdict)

    blocking, advisory, order_actions, bench, fly, build = [], [], [], [], [], []
    for p in PREREQUISITES:
        cls = p["cls"]
        if cls == GATED:
            bad = None
            if "tool" in p:
                t = p["tool"]
                if t not in tool_results:
                    bad = f"{t} was never run"
                elif tool_results[t] != 0:
                    bad = f"{t} exited {tool_results[t]}"
            else:
                marks = by_name.get(p.get("check"))
                if marks is None:
                    bad = f"check {p.get('check')!r} is not in the run"
                elif "FAIL" in marks:
                    bad = f"check {p.get('check')!r} failed"
            if bad is None and p.get("max_age_days") is not None:
                st = p.get("state")
                if not st:
                    bad = "no dated result recorded"
                else:
                    held = datetime.date.fromisoformat(st["date"])
                    age = (today - held).days
                    if age > p["max_age_days"]:
                        bad = (f"recorded {held.isoformat()}, {age} days old "
                               f"(max {p['max_age_days']})")
            if bad:
                blocking.append((p, bad))
        elif cls == ORDER_CHECK:
            if not p.get("state"):
                blocking.append((p, "not confirmed yet"))
        elif cls == ADVISORY:
            advisory.append(p)
        elif cls == ORDER_ACTION:
            order_actions.append(p)
        elif cls == BENCH:
            bench.append(p)
        elif cls == BUILD:
            build.append(p)
        elif cls == FLY:
            bad = None
            if "tool" in p:
                t = p["tool"]
                if t not in tool_results:
                    bad = f"{t} was never run"
                elif tool_results[t] != 0:
                    bad = f"{t} exited {tool_results[t]}"
            else:
                marks = by_name.get(p.get("check"))
                if marks is None or "FAIL" in marks or "WARN" in marks:
                    bad = "not passing"
            fly.append((p, bad))
        else:
            blocking.append((p, f"unclassified class {cls!r} - every prerequisite must "
                                f"be classified"))

    return dict(blocking=blocking, advisory=advisory, order_actions=order_actions,
                bench=bench, fly=fly, build=build,
                n_gated=sum(1 for p in PREREQUISITES if p["cls"] == GATED),
                n_total=len(PREREQUISITES))


def bound_fmt(p):
    """The design-side bound beside a bench item, or nothing if it has not been stated."""
    b = p.get("bound")
    return f"\n         bound: {b}" if b else ""


def render(rep, width=72):
    """The verdict, derived. Never printed without its breakdown."""
    out = ["\n" + "=" * width]
    nb = len(rep["blocking"])
    if nb:
        out.append(f"NOT READY TO ORDER - {nb} of {rep['n_total']} prerequisite(s) "
                   f"unresolved:")
        for p, why in rep["blocking"]:
            out.append(f"   x {p['id']:22} {why}")
    else:
        out.append(f"READY TO ORDER - all {rep['n_gated']} gated prerequisite(s) proven, "
                   f"0 order-checks outstanding")

    out.append(f"\n   {rep['n_total']} prerequisites: "
               f"{rep['n_gated']} gated, {len(rep['order_actions'])} order-time actions, "
               f"{len(rep['bench'])} bench-only, {len(rep['advisory'])} advisory, "
               f"{len(rep['build'])} to build")

    if rep["order_actions"]:
        out.append("\n  Do these AT THE CHECKOUT - they cannot be done before it:")
        for p in rep["order_actions"]:
            out.append(f"     - {p['claim']}")

    failed_fly = [p for p, bad in rep["fly"] if bad]
    out.append("")
    if failed_fly or rep["bench"]:
        out.append(f"NOT READY TO FLY - {len(failed_fly) + len(rep['bench'])} "
                   f"item(s) need hardware.")
        out.append("     None can change what is ORDERED - each confirms a bound, sets a")
        out.append("     parameter, or records a bought part (tools/check_bench_bounds.py).")
        for p, bad in rep["fly"]:
            if bad:
                out.append(f"     - {p['claim']}  [{bad}]" + bound_fmt(p))
        for p in rep["bench"]:
            out.append(f"     - {p['claim']}" + bound_fmt(p))
    else:
        out.append("READY TO FLY - every bench item is recorded")

    if rep["build"]:
        out.append(f"\n  NOT BUILT YET - {len(rep['build'])} item(s) are code, not "
                   f"measurements (gates the project, not ordering):")
        for p in rep["build"]:
            out.append(f"     - {p['claim']}")

    out.append(f"\n  Advisory (report-only, reasons in tools/readiness.py): "
               f"{', '.join(p['id'].split('.', 1)[1] for p in rep['advisory'])}")
    return "\n".join(out)
