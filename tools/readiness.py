#!/usr/bin/env python3
"""Every prerequisite for ordering this board, what proves it, and what cannot be proven"""
import kt   #puts kicad-tools on the path
from kicadtools import gate
from kicadtools.gate import GATED, ADVISORY, ORDER_ACTION, BENCH, FLY

PREREQUISITES = [
    #the board is the design it claims to be
    dict(id="design.netlist", cls=GATED, tool="check_circuit.py design",
         claim="the netlist matches the schematic, and every MCU pin used is declared"),
    dict(id="elec.esd", cls=GATED, tool="check_circuit.py esd",
         claim="every signal that leaves the board on a cable has a clamp at its connector, "
               "and every series resistor is in the path, not beside it"),
    dict(id="mech.balance", cls=GATED, tool="check_mech.py balance",
         claim="every mass has a position, the CG sits over the thrust centre, and the "
               "aircraft stands on its skids through a 45 deg lean"),
    dict(id="mech.prints", cls=GATED, tool="check_mech.py prints",
         claim="every printed part - each mount, its lids and the skid - is in cad/print, and "
               "each STL is the solid today's design exports"),
    dict(id="fw.bdshot", cls=GATED, tool="check_firmware.py bdshot",
         claim="all four motors sit on capture-capable timer channels with BIDIR and DMA of "
               "their own, so RPM telemetry and the RPM notch work once Bluejay is flashed"),
    dict(id="design.hwdef", cls=GATED, tool="check_firmware.py hwdef",
         claim="ArduPilot's hwdef agrees with the netlist pin for pin"),
    dict(id="design.symbols", cls=GATED, tool="check_circuit.py symbol_pinout",
         claim="every active part's symbol pinout matches KiCad's library or its datasheet"),
    dict(id="design.library", cls=GATED, tool="check.py libraries",
         claim="the vendored library is complete and its footprints equal the board's"),
    dict(id="design.lcscprops", cls=GATED, tool="fab.py lcsc",
         claim="every symbol and footprint carries the LCSC code design.py assigns "
               "that reference - the artwork agrees with the BOM, not just the order"),

    #the board is physically manufacturable
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
    dict(id="fab.backside", cls=GATED, tool="check.py backside",
         claim="no through-hole pin or post lands under a part on the other side"),
    dict(id="fab.pegdepth", cls=GATED, check="locating peg sink depth within board core",
         claim="locating pegs sink within board core and clear opposite-side copper"),
    dict(id="fab.silkowner", cls=GATED, tool="check.py silk_owner",
         claim="every printed label sits nearer the part it names than any other part"),
    dict(id="fab.models", cls=GATED, tool="check.py model_alignment",
         claim="every part's 3D body sits on its footprint - pegged parts with their pegs "
               "in the holes - no two bodies occupy the same space, and none sits under the "
               "washer or spacer bolted through a stack hole"),
    dict(id="fab.bundle", cls=GATED, tool="fab.py check_bundle",
         claim="the bundle you upload matches the verified BOM, CPL and gerbers"),

    #absence detection: the class that hid the catch diode
    dict(id="topology.externals", cls=GATED, tool="check_circuit.py topology",
         claim="every datasheet-required external component is PRESENT "
               "(this is the only check that can see an absent part)"),
    dict(id="topology.connections", cls=GATED, tool="check_order.py module_wiring",
         claim="modules plug in without splicing cables"),
    dict(id="topology.pins", cls=GATED, tool="check_circuit.py pin_semantics",
         claim="each pin's direction, reset level and role agree with its function"),

    #electrically sound
    dict(id="elec.values", cls=GATED, tool="check_circuit.py electrical",
         claim="dividers, decoupling and pull-ups are the right values"),
    dict(id="elec.ratings", cls=GATED, tool="check_circuit.py ratings",
         claim="every part is rated for the net it sits on"),
    dict(id="elec.current", cls=GATED, tool="irdrop.py check",
         claim="every rail carries its budget to its loads through the copper the current "
               "actually takes: drop, current density and via current in limit"),
    dict(id="elec.traces", cls=GATED, tool="check_board.py traces",
         claim="trace lengths, differential skew and crystal stray capacitance are in limit"),
    dict(id="fab.geometry", cls=GATED, tool="check.py geometry",
         claim="no track corner is sharper than 90 degrees, no track or via dangles or "
               "leads to no pad or pour, and no via enters an SMD pad mask opening"),
    dict(id="rf.gain", cls=GATED, tool="check_soop.py gain",
         claim="the antenna's noise reaches the ADC well above the converter's own and well "
               "under the tuner's compression and full scale, and the DSP meets its gates at "
               "both ends of the parts' spread"),
    dict(id="rf.spurs", cls=GATED, tool="check_soop.py spurs",
         claim="no crystal-locked clock's harmonic folds into the Ring Alert search window, "
               "at any LO offset soop.cfg can set"),
    dict(id="rf.bench", cls=GATED, tool="check_soop.py bench",
         claim="soop_bench.py runs end to end, and its LO search finds a crystal-referenced "
               "receiver's error (the Pluto's, up to 40 kHz) rather than a channel alias"),
    dict(id="rf.flow", cls=GATED, tool="check_soop.py flow",
         claim="the guard's flow velocity inverts EKF3's own flow model at any attitude to 40 "
               "deg, and refuses a steeper one"),
    dict(id="order.sheet", cls=GATED, check="the order sheet states every checkout setting",
         claim="fab/HOW-TO-ORDER.in, the sheet uploaded with the bundle, states each order-time "
               "action this manifest lists, so a setting cannot be left off the checkout"),
    dict(id="elec.sim", cls=GATED, tool="check_soop.py spice",
         claim="the analogue blocks - the buck output filters, the payload buck under a "
               "double servo stall, the battery hot-plug transient, the MAX2112 PLL loop "
               "filter, the ANT_IN bias tee, the baseband difference amp, the battery sense "
               "chain, the three linear regulators and the antenna feed monitor - simulate "
               "inside their datasheet and design bounds (sim/, nine decks)"),

    #mechanically sound
    dict(id="mech.connectors", cls=GATED, tool="check_board.py connectors",
         claim="every connector's mouth faces off-board with room for its plug"),
    dict(id="mech.floorplan", cls=GATED, tool="check_board.py floorplan",
         claim="every perimeter port sits on its edge, mates, and leaves room for its neighbours"),
    dict(id="mech.cables", cls=GATED, tool="check_mech.py cables",
         claim="every cable routed through the airframe meets length, bend radius and clearance"),
    dict(id="mech.stack", cls=GATED, tool="check_mech.py mechanical",
         claim="the board, ESC and frame fit in Z"),
    dict(id="mech.interference", cls=GATED, tool="check_mech.py cad_fit",
         claim="no two placed parts overlap in the assembly"),
    dict(id="mech.joints", cls=GATED, tool="check_mech.py fit",
         claim="every bolted joint fits by declaration: pattern, hole, screw length, "
               "stack under the kit's top plate, standoff posts clear of the boards"),
    dict(id="mech.mounts", cls=GATED, check="every part off the board is mounted, with screws",
         claim="the GPS, Iridium helix and its bias tee, receiver and antennas, nose camera, lidar "
               "and rangefinder each sit on a printed mount that fits the printer, held by "
               "screws the buy list sells, with the two patches clear to the sky"),
    dict(id="mech.frame", cls=GATED, check="CAD frame matches design.FRAME",
         claim="the CAD frame is generated from design.FRAME, not stale"),
    dict(id="mech.screwhead", cls=GATED, check="no copper under a screw head",
         claim="nothing metal touches the board at the stack holes: the steel heads sit on "
               "nylon washers and the spacers below are nylon, since pads lie inside a "
               "metal hex's reach"),
    dict(id="mech.mounting", cls=GATED, check="mounting holes",
         claim="the 30.5 mm 4-hole mounting pattern is present"),

    #assemblable by the fab
    dict(id="assy.cpl", cls=GATED, tool="check.py cpl",
         claim="CPL rotations derived from board geometry agree with the CPL"),
    dict(id="assy.bom", cls=GATED, check="BOM matches the board",
         claim="every BOM line matches what is on the board"),
    dict(id="assy.codes", cls=GATED, check="every line has an LCSC code",
         claim="every BOM line carries a real LCSC part number"),
    dict(id="assy.paste", cls=GATED, check="exposed pads windowpaned",
         claim="every thermal slug has a vented paste array"),
    dict(id="assy.twosided", cls=GATED, check="two-sided assembly",
         claim="the bottom-side placement is stated, so you order the right stencil"),
    dict(id="assy.variants", cls=GATED, tool="fab.py variants",
         claim="every BOM/CPL variant - including the Economic pair the ordering "
               "document recommends at the checkout - matches the board, and no variant "
               "moves a part rather than omitting it"),
    dict(id="assy.padcount", cls=GATED, tool="check.py footprints",
         claim="each footprint's pad count, package family and pitch match JLCPCB's own "
               "package string for that part, from the live parts API"),

    #the aircraft, as a whole
    dict(id="build.aircraft", cls=GATED, tool="check_mech.py build",
         claim="power budget, mass, thrust, geometry and buses, with every value "
               "tagged [M]easured / [D]atasheet / [L]isting / [A]ssumed"),
    dict(id="build.modules", cls=GATED, tool="check_order.py modules",
         claim="every module the documents claim has landing pads on the board"),
    dict(id="build.payload", cls=GATED, tool="check_order.py payload",
         claim="the payload provisions the docs claim are still spare"),
    dict(id="build.purchase", cls=GATED, tool="check_order.py purchase",
         claim="every buy-to-buy interface mates"),

    dict(id="fw.params", cls=GATED, tool="check_firmware.py params",
         claim="every shipped parameter exists in the pinned firmware"),
    dict(id="fw.drivers", cls=GATED, tool="check_firmware.py features",
         claim="every parameter's DRIVER is compiled into this board's binary, "
               "measured by linked symbol size"),
    dict(id="fw.docs", cls=GATED, check="generated doc tables match the code",
         claim="generated tables in the docs are derived from the code, not typed"),
    dict(id="fw.figures", cls=GATED, tool="check_order.py doc_figures",
         claim="no retired figure is presented as current in the live documentation"),
    dict(id="fw.defaults", cls=GATED, check="default parameters shipped",
         claim="the defaults.parm that ships is the one this board needs"),
    dict(id="fw.antfeed", cls=GATED, tool="check_soop.py antenna",
         claim="the active antenna feed monitor reads parts right, handles faults and compiles"),
    dict(id="fw.max2112", cls=GATED, tool="check_soop.py max2112",
         check="tuner registers match the MAX2112 datasheet",
         claim="the tuner's register image and lock decode follow the MAX2112 datasheet "
               "field by field, the LO carries correctly, and the code compiles for the H743"),

    dict(id="adv.decoupling", cls=ADVISORY, tool="check_board.py placement",
         why="a PRE-routing placement guide whose limits relax once routing forces a part "
             "further from its pin. It measures distance to a pin, not electrical "
             "behaviour, so it cannot fail a board that passes irdrop.py check."),
    dict(id="adv.thermal", cls=ADVISORY, tool="check_circuit.py thermal",
         why="the junction figures are BRACKETS between the datasheet's JEDEC and EVM "
             "copper, and this board is between them. No desk calculation narrows it; "
             "T3a measures it. U19 logs the board beside U9 every flight in the meantime."),
    dict(id="adv.buck_cout", cls=ADVISORY, tool="check_circuit.py electrical",
         why="TI Table 9-2 recommends 4 x 22 uF (88 uF) at 400 kHz / 5 V; the Rev D respin "
             "fits 2 x 47 uF 1206 (Samsung CL31A476MPHNNNE, 94 uF rated, ~50 uF effective at 5.0 V bias), "
             "exceeding Table 9-2 recommended capacity and Eq. 6 transient floor."),
    dict(id="adv.j2_contact", cls=ADVISORY, tool="check_circuit.py electrical",
         why="J2 (JST-SH 8P) carries all board power through one contact rated 1.0 A [D]; "
             "design.NET_CURRENT['VBAT_IN'] is 1.2 A. Measured lander flight draw is ~0.66 A at 4S "
             "and ~0.9 A at low 3S; full payload load on 3S must be avoided until Rev E battery pads."),
    dict(id="adv.i2c2_pullups", cls=ADVISORY, tool="check_circuit.py electrical",
         why="I2C2 pull-ups sit on different 3.3 V rails (R11 on +3V3A, R12 on +3V3); "
             "tolerated in Rev D as both rails are 3.3 V LDO outputs with matched enable, "
             "scheduled for cleanup in Rev E (T2.2)."),
    dict(id="fab.padlabels", cls=GATED, check="pad silkscreen labels",
         claim="every solder pad and test point carries its function (design.PAD_LABELS) on "
               "the silkscreen, where check.py silk_owner reads it as that pad's - or is named "
               "in design.PAD_LABELS_UNPRINTED with the reason, and on padmap.svg"),
    #checks that live in preflight itself, owned by name
    dict(id="fab.gerberlayers", cls=GATED, check=("gerber layers", "drill file"),
         claim="the fab directory holds a gerber for every layer and the drill file"),
    dict(id="assy.files", cls=GATED, check=("BOM present", "CPL present"),
         claim="the BOM and the placement file exist"),
    dict(id="si.gndplane", cls=GATED, check="GND plane is solid",
         claim="In1.Cu is one unbroken GND pour"),
    dict(id="si.critical", cls=GATED, check="critical nets have a reference",
         claim="every critical net runs next to a solid reference plane"),
    dict(id="si.crystal", cls=GATED, check="crystal near the MCU",
         claim="Y1 sits within reach of OSC_IN"),
    dict(id="fab.connnames", cls=GATED, check="connector names on the silkscreen",
         claim="every connector is named on the silkscreen, or listed in "
               "design.SILK_NAMES_UNPRINTED with the reason and drawn on padmap.svg"),
    dict(id="project.functions", cls=GATED, group="project",
         claim="every fitted function is on the board and the hwdef sets IMU rotations "
               "and a board ID"),
    dict(id="fab.padmap", cls=GATED, check="pad map matches the board",
         claim="docs/img/padmap.svg is generated from the board as built"),
    dict(id="mech.mountscad", cls=GATED, check="CAD mounts match design.MOUNTS",
         claim="cad/mounts.scad is generated from design.MOUNTS"),
    dict(id="mech.belly", cls=GATED, check="belly parts clear the ground",
         claim="nothing under the bottom plate reaches the skid contact plane"),
    dict(id="order.links", cls=GATED, check="buying links are recoverable",
         claim="every buying link resolves or carries a fallback search term"),
    dict(id="fw.build", cls=GATED, check="ArduPilot builds for this board",
         claim="the cached firmware was built from the hwdef on disk"),
    #anything preflight fails that no entry above owns still stops the order
    dict(id="gate.hardchecks", cls=GATED, rule="no_unowned_fail",
         claim="no hard failure in preflight goes unowned"),
    dict(id="adv.in4rails", cls=ADVISORY, check="In4.Cu rails not fragmented",
         why="separate pours around separate pad groups, each tied to its rail - a note "
             "about shape, not a defect in connectivity."),

    dict(id="order.stock", cls=GATED, tool="fab.py stock",
         claim="every BOM line is in stock at JLCPCB in the quantity ordered, the code "
               "resolves to the manufacturer part number the design intends, and the "
               "snapshot is no older than 7 days"),
    dict(id="bench.bounds", cls=GATED, check="no bench item can change what is ordered",
         claim="every bench-only item confirms a design-side bound, sets a firmware "
               "constant, or records a bought part's property - none can require "
               "different copper"),


    #performed at the checkout, so they cannot be done earlier
    dict(id="act.copper", cls=ORDER_ACTION, sheet=r"Outer copper\s+1 oz",
         claim="select 1 oz outer copper",
         why="half-ounce halves every trace's current rating and invalidates "
             "irdrop.py check. It is a checkout setting, not a design property."),
    dict(id="act.inner_copper", cls=ORDER_ACTION, sheet=r"Inner copper\s+1 oz",
         claim="select 1 oz inner copper",
         why="JLC's default 0.5 oz inner layers put the VBAT plane on In4 at 99% of its "
             "current density; irdrop.py check now assumes 1 oz (design.INNER_COPPER_UM)."),
    dict(id="act.dfm", cls=ORDER_ACTION, sheet=r"Accept JLCPCB's free DFM review",
         claim="accept JLCPCB's free DFM review",
         why="it is the only thing that checks pad LAND SIZE and paste apertures; "
             "check.py footprints verifies pad count, package and pitch but not those."),
    dict(id="act.impedance", cls=ORDER_ACTION, sheet=r"Impedance control\s+No",
         claim="leave impedance control OFF",
         why="none is needed. USB is a plain differential pair. The 1.62 GHz J12 -> U13 "
             "line is drawn as 50 ohm grounded coplanar on F.Cu over the solid In1 ground "
             "(0.21 mm track, 0.2 mm gap): 45-55 ohm across JLC's 6-layer prepregs "
             "(0.10-0.12 mm, er 4.1-4.2), into an RFIN that is 75 ohm anyway, so the uncontrolled tolerance costs a fraction of "
             "a dB behind the HC610's 28 dB of gain. Ordering impedance control would not "
             "change the drawn geometry."),
    dict(id="act.quantity", cls=ORDER_ACTION, sheet=r"5 bare PCBs, 2 assembled(.|\n)*BOTH sides",
         claim="5 bare PCBs / 2 assembled, BOTH sides",
         why="5 is the multilayer minimum and 2 the SMT minimum; both sides are populated "
             "so two stencils are needed."),
    dict(id="act.panel", cls=ORDER_ACTION, sheet=r"Panel by JLCPCB, 1 x 1, edge rails on all 4 sides, 12 mm",
         claim="Panel by JLCPCB, 1 x 1, 12 mm rails on all 4 sides (not a committed panel file)",
         why="Standard assembly requires a single PCB of at least 70 x 70 mm and this is "
             "46.5 x 47.2 mm, so the board must be panelled to be assembled at all. "
             "1 x 1 with 12 mm rails gives about 70.5 x 71.2 mm. Not 2 x 2: J17/J23 "
             "overhang the south edge by 6.3 mm and would sit over the neighbouring board. "
             "Do NOT commit a panelised .kicad_pcb: the board files stay exactly as "
             "verified, so nothing has to be re-checked."),

    dict(id="bench.u8", cls=BENCH, bound="87 C worst case against 125 C - 38 C of margin",
         claim="U8's junction temperature under load",
         why="BOUND. The fitted LMR33630A RNX carries ONE theta_JA (72.5 C/W) rather than "
             "the old part's JEDEC-EVM bracket, so 87 C is the corner and not the top of "
             "a range. U8 was swapped for exactly this and the swap is already on the "
             "board; a reading can confirm it and cannot un-fit it.",
         refresh="runbook T3 (docs/navcore-runbook.tex Part 9)"),
    dict(id="bench.u9", cls=BENCH,
         bound="82 C peak on good copper against 125 C - 43 C of margin",
         claim="U9's board-to-junction offset",
         why="BOUND. U9 is a TLV75733PDYD with an exposed pad soldered to the GND plane; "
             "check_circuit.py thermal gives 82 C peak on good copper against 125 C. "
             "What the bench sets is the offset between TEMP[0] and the junction, a constant U19 "
             "then carries forward every flight.",
         refresh="runbook T3a (docs/navcore-runbook.tex Part 10)"),
    dict(id="bench.u20", cls=BENCH,
         bound="104 C worst case against 125 C - 21 C of margin (check_circuit.py thermal)",
         claim="U20's junction temperature at the worst payload mission",
         why="BOUND. U20 is the same LMR33630A RNX as U8, carrying the payload rail's "
             "worst mission (design.RAIL_5V_PAYLOAD); the figure is the single-theta_JA "
             "corner at 40 C ambient, so a reading confirms it and cannot change copper.",
         refresh="runbook T3a (docs/navcore-runbook.tex Part 10)"),
    dict(id="bench.flowyaw", cls=BENCH, bound="one of four cardinal values in defaults.parm",
         claim="FLOW_ORIENT_YAW, against the camera's actual mount",
         why="PARAM. Flow arrives as MAVLink from the off-board companion, so the board "
             "cannot encode the sign and has no pin to change. Set it from CAD, confirm "
             "it in position hold.",
         refresh="check the sign before position hold, runbook Part 14"),
    dict(id="bench.rf", cls=BENCH,
         bound="Pr >= -110 dBm at 2 dB system NF, met by the bought HC610 (NF 2.0 dB)",
         claim="that this antenna and front end can produce a usable Iridium fix",
         why="MODULE. sitl/ proves what ArduPilot does with a fix of a GIVEN quality; it "
             "cannot prove the receiver can produce one. But the receiver IS a bought "
             "part - the Tallysman HC610, a filter then 28 dB of LNA inside the antenna - "
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

    #flies the way the firmware says it does
    dict(id="sitl.scenarios", cls=GATED, check="SITL scenarios pass",
         claim="defaults.parm flies the full scenario suite against simulated truth, "
               "with every prearm fault resolved"),

    #ready to FLY only
    dict(id="fly.rfbench", cls=FLY, tool="check_order.py rf",
         bound="recorded data; asserts nothing about the board",
         claim="the T3b bench measurements are recorded and within the link budget"),

    dict(id="solver.ephemeris", cls=GATED,
         check="real Iridium ephemeris inverts the geometry",
         claim="the solver propagates real TLEs with SGP4 and recovers a known position"),
    dict(id="solver.burst", cls=GATED,
         check="burst detection and carrier estimation meet the 5 Hz target",
         claim="I/Q gives a carrier estimate inside the solver's 5 Hz target"),
    dict(id="solver.dsp", cls=GATED,
         check="the on-board DSP finds bursts and meets 5 Hz on a simulated sky",
         claim="the flight DSP in C (soop_dsp.c) detects Iridium simplex bursts and measures "
               "their carriers inside the solver's 5 Hz, on a sky built with the board's "
               "impairments, and builds for the H743"),
    dict(id="solver.nav", cls=GATED,
         check="the on-board navigation holds position through simulated denied flights",
         claim="the flight navigation in C (soop_nav.c) associates bursts to satellites, "
               "tracks the TCXO, the orbit errors and the flight EKF's velocity drift, and "
               "holds a fix with an honest accuracy through 15-30 min denied flights on "
               "real orbits, checks the GPS against Iridium so a jump or a fast drag is "
               "caught and honest GPS is never refused, and builds for the H743"),
    #the solve is ported to C and gated (solver.c below)
    dict(id="build.firmware", cls=BENCH,
         bound="AP_SoOP builds and links into the NAVCORE_SoOP firmware",
         claim="the flight firmware: MAX2112 control, I/Q capture and the EKF hand-off on the H743",
         why="BUILT. The gated C (solver.dsp, solver.nav) runs in AP_SoOP with the tuner "
             "driver and simultaneous ADC1/ADC2 capture. Tuner lock, the 1 MSPS capture and "
             "the CPU share are only known on the board: runbook T3b step 2."),
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



def evaluate(results, tool_results, today=None, sources=None):
    """Walk the manifest against what actually ran."""
    return gate.evaluate(PREREQUISITES, results, tool_results, today, sources)


def render(rep, width=72):
    """The verdict, derived."""
    return gate.render(rep, width, manifest="tools/readiness.py",
                       bench="tools/check_order.py bench_bounds")
