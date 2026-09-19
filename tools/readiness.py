#!/usr/bin/env python3
"""Every prerequisite for ordering this board, what proves it, and what cannot be proven here.

THE DEFECT THIS EXISTS TO CLOSE.

preflight.py used to print its verdict as `not nf`, where nf counted hard FAILs, and then
print a hand-typed list of "cannot be checked offline" items BELOW it. Those were two
separate mechanisms with no link between them: the list could not affect the verdict, so
the verdict could only ever OVERCLAIM - it could say READY TO ORDER no matter how much of
that list was unresolved.

Measured 2026-09-18, that was not theoretical. Four checks existed that preflight never
ran at all, including `check_topology.py` - the ONLY thing in this repo that can notice a
REQUIRED PART IS ABSENT, which is how both buck regulators once shipped with no catch
diode through 64 checks and three "ready to order" verdicts. Meanwhile a check could print
"NOT CHECKED" and be counted as a warning rather than as an absence of evidence.
"Could not verify" is not "verified".

So the claim is now DERIVED from this manifest instead of restated beside it. The verdict
walks this list. Anything unclassified is a failure. A prerequisite whose evidence names a
tool that no longer exists or no longer runs is a failure, so the manifest cannot silently
shrink either.

CLASSES, and exactly what each does to the verdict:

  GATED         Proven by a named tool or an inline preflight check, which must have RUN
                (an unrun check is a failure, not a pass) and passed. Blocks ordering.
  ADVISORY      A named check that is deliberately report-only, with the reason recorded
                here rather than hidden in a `hard=False` argument at the call site.
                Named and counted, never blocks.
  ORDER_CHECK   A fact that must be confirmed before money moves. BLOCKS until the `state`
                field records it with a date and a source.
  ORDER_ACTION  Performed DURING checkout (choose the copper weight, accept the DFM
                review). Named and counted. It cannot block, because it cannot be done
                before you are at the checkout.
  BENCH         Only knowable with the hardware in hand. Named and counted. Blocks
                READY TO FLY, never READY TO ORDER.
  FLY           Proven by a tool that is expected to fail until bench data exists. Part of
                READY TO FLY only.

STALENESS. State that goes off is worse than no state: "stock captured 2026-09-02" reads
as verified forever. Anything whose truth decays carries `max_age_days`, and the verdict
fails once it expires, naming the command that refreshes it.
"""
import os

GATED, ADVISORY, ORDER_CHECK, ORDER_ACTION, BENCH, FLY = (
    "GATED", "ADVISORY", "ORDER_CHECK", "ORDER_ACTION", "BENCH", "FLY")

# ---------------------------------------------------------------------------------
# The manifest. `tool=` names a file under tools/; `check=` names an inline preflight
# check. A GATED entry must have run and passed.
#
# `why` is required for every non-GATED entry: the reason it cannot be closed offline.
# An entry with no reason is an entry someone will later "tidy up" into a pass.
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
    dict(id="fw.defaults", cls=GATED, check="default parameters shipped",
         claim="the defaults.parm that ships is the one this board needs"),

    # -- deliberately report-only, with the reason recorded here rather than implied --
    dict(id="adv.decoupling", cls=ADVISORY, tool="check_placement.py",
         why="a PRE-routing placement guide whose limits relax once routing forces a part "
             "further from its pin. It measures distance to a pin, not electrical "
             "behaviour, so it cannot fail a board that passes check_power_cut."),
    dict(id="adv.thermal", cls=ADVISORY, tool="check_thermal.py",
         why="the junction figures are BRACKETS between the datasheet's JEDEC and EVM "
             "copper, and this board is between them. No desk calculation narrows it; "
             "T3a measures it. U19 logs the board beside U9 every flight in the meantime."),
    dict(id="adv.silk", cls=ADVISORY, check="pad silkscreen labels",
         why="an unlabelled pad costs a bench session, not a board, and silk_labels.py "
             "leaves a label off rather than print it wrong at 0.80 mm on 1.5 mm pads."),
    dict(id="adv.in4rails", cls=ADVISORY, check="In4.Cu rails not fragmented",
         why="separate pours around separate pad groups, each tied to its rail - a note "
             "about shape, not a defect in connectivity."),

    # -- must be confirmed BEFORE money moves; blocks until recorded with a source ---
    # Staleness is owned by check_stock.py, NOT duplicated here. The first draft of this
    # entry ALSO carried a max_age_days, which meant two mechanisms asserted the same
    # property - and the manifest's copy failed on a snapshot the tool had just certified,
    # because the manifest had no `state` of its own to age. That is the same defect this
    # file exists to remove, reproduced inside it: one property, one owner. The tool reads
    # the dated snapshot and exits nonzero when it expires, naming the refresh command.
    dict(id="order.stock", cls=GATED, tool="check_stock.py",
         claim="every BOM line is in stock at JLCPCB in the quantity ordered, the code "
               "resolves to the manufacturer part number the design intends, and the "
               "snapshot is no older than 7 days"),
    # Reclassified from ORDER_CHECK to BENCH, and the reason is the whole point of this
    # file: a prerequisite belongs in ORDER_CHECK only if confirming it could still change
    # WHAT YOU ORDER. The PCB is already placed and DRC'd; if the flange turns out wider
    # than the assumed 6.0 mm, the fix is a different grommet - a part in the frame kit -
    # not a re-spun board. It gates ASSEMBLY, so it is a bench item, and saying so is not
    # a way of dodging it: it is named, counted and printed every run.
    dict(id="bench.grommet", cls=BENCH,
         claim="the grommet flange (assumed 6.0 mm) clears the parts around the holes",
         why="the flange is a property of the grommet in the frame kit, not of this PCB. "
             "A wider flange means a different grommet, not a different board, so it "
             "cannot change what is ordered - only how the stack goes together.",
         refresh="measure the grommet when the frame kit arrives"),

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
         why="none is specified - USB is a plain differential pair, and there is no RF "
             "copper on this board. Ordering it would be paying for a claim not made."),
    dict(id="act.quantity", cls=ORDER_ACTION,
         claim="5 bare PCBs / 2 assembled, BOTH sides",
         why="5 is the multilayer minimum and 2 the SMT minimum; both sides are populated "
             "so two stencils are needed."),
    # Added 2026-09-19. This was missing while the runbook had it, and it belongs in the
    # class that means "done at the checkout, cannot be done earlier" more than any other:
    # JLCPCB's capability page gives Standard single-PCB assembly as 70 x 70 mm to
    # 460 x 500 mm, and this board is 45.1 x 46.1 mm, so it CANNOT go through Standard
    # unpanelled. "Panel by JLCPCB" is the answer and it also adds the edge rails, fiducial
    # marks and tooling holes by default. Economic needs no panel (10 x 10 mm up), which is
    # the one real advantage it has - and the reason this belongs in the checkout list is
    # that choosing the tier and the panel IS a checkout choice, not a design property.
    dict(id="act.panel", cls=ORDER_ACTION,
         claim="Panel by JLCPCB, 2 x 2 (not a committed panel file)",
         why="Standard assembly requires a single PCB of at least 70 x 70 mm and this is "
             "45.1 x 46.1 mm, so the board must be panelled to be assembled at all. "
             "2 x 2 gives roughly 93 x 95 mm. Do NOT commit a panelised .kicad_pcb: the "
             "board files stay exactly as verified, so nothing has to be re-checked."),

    # -- only knowable with hardware in hand: gates FLYING, not ordering ------------
    dict(id="bench.u8", cls=BENCH,
         claim="U8's junction temperature under load",
         why="the datasheet gives 118.6 C/W JEDEC and 57.2 C/W EVM, and this 6-layer "
             "board is between them. Only a thermocouple says where.",
         refresh="docs/BUILD.md T3"),
    dict(id="bench.u9", cls=BENCH,
         claim="U9's board-to-junction offset",
         why="U19 logs the board beside U9 every flight; the offset between TEMP[0] and "
             "the junction is set once, at T3a, and then carried forward.",
         refresh="docs/BUILD.md T3a"),
    dict(id="bench.escshunt", cls=BENCH,
         claim="BATT_AMP_PERVLT, from the ESC's actual shunt",
         why="it is a property of the ESC you receive, not of this board.",
         refresh="calibrate against a known current at T1"),
    dict(id="bench.esccable", cls=BENCH,
         claim="the ESC cable pinout matches J2",
         why="J2 matches Betaflight's documented SpeedyBee F405 V4 order, but the cable "
             "is a separate purchase and must be buzzed out.",
         refresh="continuity test on the cable received"),
    dict(id="bench.flowyaw", cls=BENCH,
         claim="FLOW_ORIENT_YAW, against the camera's actual mount",
         why="flow arrives as MAVLink from the companion; the sign depends on how the "
             "camera is mounted, which is not in any file here.",
         refresh="check the sign before position hold, docs/BUILD.md"),
    dict(id="bench.rf", cls=BENCH,
         claim="that this antenna and front end can produce a usable Iridium fix",
         why="sitl/ proves what ArduPilot does with a fix of a GIVEN quality; it cannot "
             "prove the receiver can produce one. Needs the SDR and the antenna.",
         refresh="docs/BUILD.md T3b"),
    dict(id="bench.cameraflow", cls=BENCH,
         claim="flow quality over real grass",
         why="simulated flow is perfect flow. This needs recorded footage from the "
             "actual camera, over actual ground.",
         refresh="record a flight, then replay it"),

    # -- flies the way the firmware says it does; an ORDERING prerequisite ----------
    # NOT classified as FLY. It runs offline, it has already found three prearm faults
    # that no build check could see, and the decision on 2026-09-18 was that it must be
    # GREEN before money moves - not merely reported. A suite that is not run is a suite
    # that is not passing, so an absent result blocks like a failing one.
    dict(id="sitl.scenarios", cls=GATED, check="SITL scenarios pass",
         claim="defaults.parm flies the full scenario suite against simulated truth, "
               "with every prearm fault resolved"),

    # -- READY TO FLY only ---------------------------------------------------------
    dict(id="fly.rfbench", cls=FLY, tool="check_rf.py",
         claim="the T3b bench measurements are recorded and within the link budget"),
]


def evaluate(results, tool_results, today=None):
    """Walk the manifest against what actually ran. Returns a report dict.

    `results`      : [(group, name, verdict, detail)] from preflight.check()
    `tool_results` : {tool_filename: returncode} from preflight.run()
    """
    import datetime
    today = today or datetime.date.today()

    by_name = {}
    for g, name, verdict, _ in results:
        by_name.setdefault(name, []).append(verdict)

    blocking, advisory, order_actions, bench, fly = [], [], [], [], []
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
                bench=bench, fly=fly,
                n_gated=sum(1 for p in PREREQUISITES if p["cls"] == GATED),
                n_total=len(PREREQUISITES))


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
               f"{len(rep['bench'])} bench-only, {len(rep['advisory'])} advisory")

    if rep["order_actions"]:
        out.append("\n  Do these AT THE CHECKOUT - they cannot be done before it:")
        for p in rep["order_actions"]:
            out.append(f"     - {p['claim']}")

    failed_fly = [p for p, bad in rep["fly"] if bad]
    out.append("")
    if failed_fly or rep["bench"]:
        out.append(f"NOT READY TO FLY - {len(failed_fly) + len(rep['bench'])} "
                   f"item(s) need hardware:")
        for p, bad in rep["fly"]:
            if bad:
                out.append(f"     - {p['claim']}  [{bad}]")
        for p in rep["bench"]:
            out.append(f"     - {p['claim']}")
    else:
        out.append("READY TO FLY - every bench item is recorded")

    out.append(f"\n  Advisory (report-only, reasons in tools/readiness.py): "
               f"{', '.join(p['id'].split('.', 1)[1] for p in rep['advisory'])}")
    return "\n".join(out)
