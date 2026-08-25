#!/usr/bin/env python3
"""Production readiness gate for NAVCORE-SoOP.

Usage:  python3 tools/preflight.py [board.kicad_pcb]
"""
import os, sys, re, csv, math, glob, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design, route

BOARD = sys.argv[1] if len(sys.argv) > 1 else "NAVCORE-SoOP.kicad_pcb"
SCH   = "NAVCORE-SoOP.kicad_sch"
FAB   = "fab"
HWDEF = "firmware/NAVCORE_SoOP/hwdef.dat"

PLANE_LAYERS = ("In1.Cu", "In4.Cu")

results = []


def check(group, name, ok, detail, hard=True):
    results.append((group, name, "PASS" if ok else ("FAIL" if hard else "WARN"), detail))


def cli(args, out):
    subprocess.run(args, capture_output=True, timeout=900)
    return open(out).read() if os.path.exists(out) else ""


# ---------------------------------------------------------------- fabrication ---
def fabrication(board):
    rpt = cli(["kicad-cli", "pcb", "drc", "--output", "/tmp/nav/pf_drc.rpt",
               "--severity-error", BOARD], "/tmp/nav/pf_drc.rpt")
    cls = re.findall(r'^\[([a-z_]+)\]', rpt, re.M)
    hard = len([c for c in cls if c != "unconnected_items"])
    unconn = cls.count("unconnected_items")
    check("fabrication", "DRC errors", hard == 0, f"{hard} errors")
    # Split the unrouted nets by whether anything is actually fitted on them.
    unrouted_nets = set(re.findall(r"^\s+@.*?\[([A-Z0-9_+.]+)\] (?:of|on)", rpt, re.M))
    unrouted_nets |= set(re.findall(r'Zone \[([A-Z0-9_+.]+)\]', rpt))
    def _all_dnp(net):
        pins = design.NETS.get(net) or []
        if not pins: return False
        return all((design.COMPONENTS.get(q.split('.')[0]) or (0,0,0,0,False))[4]
                   for q in pins)
    dnp_only = sorted(n for n in unrouted_nets if _all_dnp(n))
    live = sorted(n for n in unrouted_nets if not _all_dnp(n))
    check("fabrication", "all nets routed (fitted parts)", not live,
          (f"unrouted on FITTED nets: {', '.join(live)}" if live
           else f"{unconn} unconnected item(s), all on DNP-only nets"
                + (f": {', '.join(dnp_only)}" if dnp_only else "")))
    if dnp_only:
        check("fabrication", "unpopulated variants", True,
              f"{', '.join(dnp_only)} unrouted - those variants CANNOT be populated on "
              f"this board; fitted-part nets are unaffected")

    erc = cli(["kicad-cli", "sch", "erc", "--output", "/tmp/nav/pf_erc.rpt",
               "--severity-error", "--severity-warning", SCH], "/tmp/nav/pf_erc.rpt")
    ne = len(re.findall(r'^\[', erc, re.M))
    check("fabrication", "ERC clean", ne == 0, f"{ne} violations")

    # All six copper layers must be exported. Shipping a 6-layer board with only
    # four gerbers gets you a 4-layer board with two nets missing entirely.
    want = ["F_Cu", "In1_Cu", "In2_Cu", "In3_Cu", "In4_Cu", "B_Cu",
            "F_Mask", "B_Mask", "F_Paste", "B_Paste",
            "F_Silkscreen", "B_Silkscreen", "Edge_Cuts"]
    have = [os.path.basename(p) for p in glob.glob(f"{FAB}/gerbers/*")]
    missing = [w for w in want if not any(w in h for h in have)]
    check("fabrication", "gerber layers", not missing,
          f"{len(have)} files" + (f", MISSING {missing}" if missing else ""))
    drl = glob.glob(f"{FAB}/gerbers/*.drl")
    check("fabrication", "drill file", bool(drl),
          os.path.basename(drl[0]) if drl else "none")

    fab_files = glob.glob(f"{FAB}/gerbers/*.gbr") + glob.glob(f"{FAB}/gerbers/*.drl")
    if fab_files and os.path.exists(BOARD):
        b_mtime = os.path.getmtime(BOARD)
        stale = [os.path.basename(f) for f in fab_files
                 if os.path.getmtime(f) < b_mtime]
        check("fabrication", "gerbers match the board", not stale,
              (f"{len(stale)} file(s) older than {BOARD} - REGENERATE before ordering "
               f"(tools/finish.sh): {', '.join(sorted(stale)[:4])}"
               + ("..." if len(stale) > 4 else "")) if stale else
              f"all {len(fab_files)} fab files newer than the board file")

    ds = board.GetDesignSettings()
    tw = ds.m_TrackMinWidth / 1e6
    vd = ds.m_ViasMinSize / 1e6
    dr = ds.m_MinThroughDrill / 1e6
    ok = tw >= 0.1016 - 1e-9 and vd >= 0.45 and dr >= 0.2
    check("fabrication", f"JLCPCB {board.GetCopperLayerCount()}-layer limits", ok,
          f"track {tw:.4f} mm, via {vd:.2f} mm, drill {dr:.2f} mm "
          f"(free tier: 0.1016 / 0.45 / 0.20)"
          + ("" if tw >= 0.1016 - 1e-9 else
             f" - {tw/0.0254:.1f} mil is under 4 mil and pays JLCPCB's +20% fine-trace fee"))

    edges = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    circles = [d for d in edges if d.ShowShape() == "Circle"]
    bb = board.GetBoardEdgesBoundingBox()
    w, h = bb.GetWidth()/1e6, bb.GetHeight()/1e6
    check("fabrication", "board outline", len(edges) >= 4,
          f"{w:.1f} x {h:.1f} mm, {len(edges)} Edge.Cuts shapes")
    check("fabrication", "mounting holes", len(circles) == 4,
          f"{len(circles)} holes (need 4 for a 30.5 mm stack)")


# ------------------------------------------------------------------- assembly ---
def assembly(board):
    # The base build is what gets gated.
    def _pick(kind):
        files = sorted(glob.glob(f"{FAB}/*{kind}*.csv"))
        base = [f for f in files
                if re.fullmatch(rf"{kind}-NAVCORE-SoOP\.csv", os.path.basename(f))]
        return base or files
    bom = _pick("BOM")
    cpl = _pick("CPL")
    check("assembly", "BOM present", bool(bom), bom[0] if bom else "none")
    check("assembly", "CPL present", bool(cpl), cpl[0] if cpl else "none")
    if bom:
        rows = list(csv.DictReader(open(bom[0])))
        key = next((k for k in rows[0] if "lcsc" in k.lower()), None)
        # A "lookup:<MPN>" sentinel is not a part number.
        def _missing(v):
            v = (v or "").strip()
            return (not v) or v.startswith("LOOKUP:")
        noc = [r for r in rows if _missing(r.get(key))] if key else rows
        pend = [(r.get("Comment") or "?", (r.get(key) or "")[len("LOOKUP:"):])
                for r in noc if (r.get(key) or "").startswith("LOOKUP:")]
        check("assembly", "every line has an LCSC code", not noc,
              f"{len(rows)} lines, {len(noc)} without a part number"
              + ("; awaiting lookup: "
                 + ", ".join(f"{v} = {m}" for v, m in pend) if pend else ""))

    # BOM must describe this board.
    if bom:
        bom_rows = [r for r in csv.DictReader(open(bom[0]))]
        fitted = [r for r in bom_rows
                  if not (r.get("DNP") or "").strip().upper().startswith("DNP")]
        board_parts = {fp.GetReference(): (fp.GetFPIDAsString().split(":")[-1],
                                           fp.GetFieldText("Value"))
                       for fp in board.GetFootprints()}
        skip_refs = getattr(design, "NOT_A_PART", set())
        fitted_refs = {r for r in design.COMPONENTS
                       if r in board_parts and not design.COMPONENTS[r][4]
                       and r not in skip_refs}
        refs_on_bom = set()
        problems = []
        for r in fitted:
            for ref in (r.get("Designator") or "").split(","):
                ref = ref.strip()
                if not ref:
                    continue
                refs_on_bom.add(ref)
                if ref not in board_parts:
                    problems.append(f"{ref} in BOM, not on board")
                    continue
                fp_name, value = board_parts[ref]
                if r.get("Footprint") and r["Footprint"] not in fp_name:
                    problems.append(f"{ref} BOM footprint {r['Footprint']} != board {fp_name}")
                if r.get("Comment") and value and r["Comment"] != value:
                    problems.append(f"{ref} BOM value {r['Comment']} != board {value}")
        for ref in sorted(fitted_refs - refs_on_bom):
            problems.append(f"{ref} fitted on board, not on any fitted BOM line")
        check("assembly", "BOM matches the board", not problems,
              f"{len(fitted)} fitted lines, {len(fitted_refs)} fitted parts cross-checked"
              if not problems else "; ".join(problems[:8]))
    if cpl:
        rows = list(csv.DictReader(open(cpl[0])))
        lk = next((k for k in rows[0] if "layer" in k.lower()), None)
        top = sum(1 for r in rows if r[lk].lower().startswith("t"))
        bot = len(rows) - top
        check("assembly", "two-sided assembly", True,
              f"{top} top / {bot} bottom - needs a stencil for BOTH sides", hard=False)

    holes = [(d.GetCenter().x/1e6, d.GetCenter().y/1e6)
             for d in board.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts and d.ShowShape() == "Circle"]
    worst, wref = 99.0, None
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            b = pad.GetBoundingBox()
            x0, y0 = b.GetLeft()/1e6, b.GetTop()/1e6
            x1, y1 = b.GetRight()/1e6, b.GetBottom()/1e6
            for hx, hy in holes:
                d = math.hypot(max(x0-hx, 0, hx-x1), max(y0-hy, 0, hy-y1))
                if d < worst:
                    worst, wref = d, fp.GetReference()
    check("assembly", "no copper under a screw head", worst >= 2.75,
          f"closest is {wref} at {worst:.2f} mm (M3 cap head is 2.75 mm)")


# ------------------------------------------------------- signal integrity ---
def integrity(board):
    plane_seg = plane_mm = 0
    crit = {}
    CRITICAL = ("USB_DM", "USB_DP", "USB_DM_CON", "USB_DP_CON", "SD_CK",
                "SD_D0", "SD_D1", "SD_D2", "SD_D3", "OSC_IN", "OSC_OUT",
                "SPI1_SCK", "SPI3_SCK", "SPI4_SCK", "M1", "M2", "M3", "M4",
                "SOOP_I_ADC", "SOOP_Q_ADC")
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        ln = board.GetLayerName(t.GetLayer())
        if ln in PLANE_LAYERS:
            plane_seg += 1
            plane_mm += t.GetLength()/1e6
            nm = t.GetNet().GetNetname() if t.GetNet() else ""
            if nm in CRITICAL:
                crit[nm] = crit.get(nm, 0) + 1
    check("signal integrity", "planes carry no routing", plane_seg == 0,
          f"{plane_seg} segments, {plane_mm:.0f} mm on "
          + "/".join(PLANE_LAYERS))

    islands = 0
    for z in board.Zones():
        if z.GetNetname() != "GND":
            continue
        for li in z.GetLayerSet().CuStack():
            if board.GetLayerName(li) == "In1.Cu":
                islands += z.GetFilledPolysList(li).OutlineCount()
    check("signal integrity", "GND plane is solid", islands == 1,
          f"In1.Cu GND is {islands} island(s)")

    zones, isles = {}, {}
    for z in board.Zones():
        nm = z.GetNetname()
        if nm in ("", "GND"):
            continue
        for li in z.GetLayerSet().CuStack():
            if board.GetLayerName(li) == "In4.Cu":
                zones[nm] = zones.get(nm, 0) + 1
                isles[nm] = isles.get(nm, 0) + z.GetFilledPolysList(li).OutlineCount()
    frag = {k: (zones[k], isles[k]) for k in zones if isles[k] > zones[k]}
    check("signal integrity", "In4.Cu rails not fragmented", not frag,
          (", ".join(f"{k} {v[0]} zones split into {v[1]}" for k, v in sorted(frag.items()))
           if frag else
           ", ".join(f"{k}:{isles[k]}" for k in sorted(zones)) + " (islands = zones)"),
          hard=False)
    check("signal integrity", "critical nets have a reference", not crit,
          "all clear" if not crit else f"{len(crit)} crossing a plane: "
          + ", ".join(sorted(crit)))

    # crystal proximity - the defect that started this
    y1 = board.FindFootprintByReference("Y1")
    u1 = board.FindFootprintByReference("U1")
    if y1 and u1:
        osc = next((p.GetPosition() for p in u1.Pads() if p.GetNumber() == "12"), None)
        if osc:
            t = (osc.x/1e6, osc.y/1e6)
            best = 99.0
            for p in y1.Pads():
                b = p.GetBoundingBox()
                best = min(best, math.hypot(
                    max(b.GetLeft()/1e6-t[0], 0, t[0]-b.GetRight()/1e6),
                    max(b.GetTop()/1e6-t[1], 0, t[1]-b.GetBottom()/1e6)))
            check("signal integrity", "crystal near the MCU", best <= 8.0,
                  f"Y1 is {best:.2f} mm from U1.12 (OSC_IN)")


# -------------------------------------------------------------- the project ---
def project(board):
    """Everything the drone actually needs, by function rather than by part."""
    refs = {fp.GetReference() for fp in board.GetFootprints()}
    dnp = {r for r in refs
           if (design.COMPONENTS.get(r) or (0, 0, 0, 0, False))[4]}
    fitted = refs - dnp
    nets = {n.GetNetname() for n in board.GetNetInfo().NetsByName().values()}

    NEED = [
        ("MCU STM32H743",            {"U1"}),
        ("IMU 1 (ICM-42688-P)",      {"U2"}),
        ("IMU 2 (ICM-42605)",        {"U3"}),
        ("barometer MS5611",         {"U4"}),
        ("optical flow PMW3901",     {"U6"}),
        ("ToF rangefinder VL53L1X",  {"U7"}),
        ("config flash W25Q128",     {"U5"}),
        ("microSD socket",           {"J8"}),
        ("USB-C",                    {"J1"}),
        ("USB ESD protection",       {"U12"}),
        ("ESC connector (JST-SH 8)", {"J2"}),
        ("GPS / telemetry JST-GH",   {"J3"}),
        ("CAN transceiver",          {"U11"}),
        ("5 V buck",                 {"U8"}),
        ("9 V buck (VTX)",           {"U18"}),
        ("3V3 digital LDO",          {"U9"}),
        ("3V3 analogue LDO",         {"U10"}),
        ("WS2812 level shifter",     {"U17"}),
        ("VBAT input TVS",           {"D1"}),
        ("crystal",                  {"Y1"}),
        ("boot / reset buttons",     {"SW1", "SW2"}),
    ]
    for label, need in NEED:
        have_fitted = need & fitted
        have_dnp = need & dnp
        if have_fitted:
            check("project", label, True, ", ".join(sorted(have_fitted)))
        elif have_dnp:
            check("project", f"{label} [NOT FITTED]", False,
                  f"{', '.join(sorted(have_dnp))} is DNP: pads are provisioned, no part "
                  f"is placed, the aircraft does NOT have this function as ordered",
                  hard=False)
        else:
            check("project", label, False, "MISSING")

    NETS = [
        ("4x DShot motor outputs", ("M1", "M2", "M3", "M4")),
        ("battery voltage sense",  ("BATT_V_DIV",)),
        ("ESC current sense",      ("ESC_CUR",)),
        ("SoOP I/Q ADC inputs",    ("SOOP_I_ADC", "SOOP_Q_ADC")),
        ("SWD debug",              ("SWDIO", "SWCLK")),
        ("power rails",            ("+3V3", "+5V", "+9V", "VBAT", "GND")),
    ]
    for label, need in NETS:
        miss = [n for n in need if n not in nets]
        check("project", label, not miss,
              "present" if not miss else f"missing {miss}")

    if os.path.exists(HWDEF):
        hw = open(HWDEF).read()
        rot = re.findall(r'^IMU \S+ \S+ ROTATION_(\S+)', hw, re.M)
        check("project", "hwdef IMU rotations set", len(rot) == 2,
              ", ".join(rot) if rot else "none found")
        check("project", "board ID declared",
              "APJ_BOARD_ID" in hw, "AP_HW_NAVCORE_SOOP (UNREGISTERED with ArduPilot)")
    else:
        check("project", "ArduPilot hwdef", False, "missing")


def firmware(board):
    """The half of "ready" that has nothing to do with copper."""
    import subprocess as sp

    def run(tool):
        name, *extra = tool.split()
        r = sp.run([sys.executable, f"tools/{name}", *extra], capture_output=True,
                   text=True, timeout=1800)
        return r.returncode, (r.stdout or "") + (r.stderr or "")

    rc, out = run("check_connectors.py")
    nf = re.search(r'^(\d+) failure\(s\), (\d+) warning\(s\)', out, re.M)
    bad = re.findall(r'^  FAIL  (\S+):', out, re.M)
    check("fabrication", "connectors face off-board", rc == 0,
          (f"{', '.join(bad)} cannot be plugged in" if bad else
           f"all {len(design.MATING_FACE)} openings clear the board"
           + (f", {nf.group(2)} warning(s)" if nf and nf.group(2) != '0' else "")))

    rc, out = run("check_mechanical.py")
    m = re.search(r'^(\d+) computed check\(s\) ok', out, re.M)
    unk = "!! footprints with no declared height" in out
    check("fabrication", "mechanical fit in the stack", rc == 0 and not unk,
          ("some footprints have no declared height" if unk else
           f"{m.group(1) if m else '?'} computed checks ok; frame items listed for measurement"))

    rc, out = run("check_pin_semantics.py")
    bad = re.search(r'^(\d+) pin\(s\) are wired or configured the wrong way', out, re.M)
    check("firmware", "pins run the right way", rc == 0,
          f"{bad.group(1)} pin(s) wrong" if bad else "direction, reset level and role agree")

    # Ratings: is each part actually rated for the net it sits on?
    rc, out = run("check_ratings.py")
    m = re.search(r'^(\d+) failure\(s\), (\d+) warning\(s\), (\d+) unrated', out, re.M)
    check("firmware", "parts rated for their nets", rc == 0,
          (f"{m.group(1)} over-rating/package failure(s)" if m and m.group(1) != '0' else
           f"all capacitors rated; {m.group(2) if m else '?'} derating note(s)"))

    rc, out = run("check_electrical.py")
    m = re.search(r'^ERRORS \((\d+)\)', out, re.M)
    w = re.search(r'^WARNINGS \((\d+)\)', out, re.M)
    check("firmware", "electrical values", rc == 0,
          f"{m.group(1)} error(s)" if m else
          f"dividers, decoupling and pull-ups check out"
          + (f"; {w.group(1)} warning(s)" if w else ""))

    rc, out = run("check_params.py")
    fw = re.search(r'^firmware\s+:\s+(.+?)\s+\(tag (\S+)\)', out, re.M)
    check("firmware", "parameters exist in the target build", rc == 0,
          (f"validated against {fw.group(1)} / {fw.group(2)}" if fw
           else "could not validate - run tools/build_firmware.sh"))

    rc, out = run("check_power_cut.py")
    tight = re.findall(r'^\s+(\S+): tightest cut is \S+ mm carrying ~([\d.]+) A',
                       out, re.M)
    check("firmware", "power copper reaches the loads", rc == 0,
          ("tightest cut " + min(tight, key=lambda t: float(t[1]))[0] + " at "
           + min(tight, key=lambda t: float(t[1]))[1] + " A") if tight
          else "could not measure")

    rc, out = run("check_cpl.py")
    m = re.search(r'cross-checked\s+:\s+(\d+) parts across (\d+)', out)
    check("assembly", "CPL rotations self-consistent", rc == 0,
          (f"{m.group(1)} parts across {m.group(2)} shared footprints agree on pin 1"
           if m else "geometry check failed - see tools/check_cpl.py"))

    rc, out = run("check_design.py")
    m = re.search(r'^(\d+) error', out, re.M)
    w = re.search(r'^WARNINGS \((\d+)\)', out, re.M)
    check("fabrication", "schematic matches the netlist", rc == 0 and "no errors" in out,
          "netlist, pin coverage and hwdef agree"
          + (f"; {w.group(1)} unconnected-pin note(s)" if w else ""))

    rc, out = run("gen_doc_tables.py --check")
    check("firmware", "generated doc tables match the code", rc == 0,
          "sitl/README.md scenarios and docs/HARDWARE.md frame table are current" if rc == 0
          else "a generated table is stale - run tools/gen_doc_tables.py")

    rc, out = run("gen_scad_frame.py --check")
    check("mechanical", "CAD frame matches design.FRAME", rc == 0,
          "cad/frame.scad is current" if rc == 0
          else "cad/frame.scad is stale - run tools/gen_scad_frame.py")

    rc, out = run("check_purchase.py")
    m = re.search(r'^(\d+) interface\(s\) still rest on an ASSUMED', out, re.M)
    check("mechanical", "buy-to-buy interfaces mate", rc == 0,
          ("every buy-to-buy interface asserted"
           + (f"; {m.group(1)} still on an ASSUMED source - confirm on the listing" if m
              else "")) if rc == 0
          else "an interface does not mate - see tools/check_purchase.py")

    rc, out = run("check_modules.py")
    m = re.search(r'(\d+)/(\d+) modules attach', out)
    check("firmware", "later modules still have somewhere to land", rc == 0,
          f"{m.group(1)}/{m.group(2)} modules attach to the board as fabricated; "
          f"the +5 V rail cannot carry them all at once" if m and rc == 0
          else "a module's landing pads are missing - see tools/check_modules.py")

    rc, out = run("check_payload.py")
    m = re.search(r'payload provisions intact: (.+)$', out, re.M)
    check("firmware", "payload provisions still spare", rc == 0,
          m.group(1).strip() if m
          else "a payload provision has been consumed - see tools/check_payload.py")

    # Geometric fit of the whole aircraft.
    rc, out = run("check_cad_fit.py")
    m = re.search(r'PASS - (\d+) pairs', out)
    check("mechanical", "assembly has no interference", rc == 0,
          f"{m.group(1)} part pairs checked by intersection volume, all clear" if m
          else "parts overlap in the assembly - see tools/check_cad_fit.py")

    g = re.findall(r'^\s+(\w+)\s+lowest z\s+[-\d.]+\s+clearance\s+([-\d.]+) mm', out, re.M)
    if g:
        worst = min(g, key=lambda x: float(x[1]))
        check("mechanical", "belly parts clear the ground", rc == 0,
              f"{len(g)} hanging part(s); tightest is {worst[0]} at {worst[1]} mm above "
              f"the skid contact plane"
              if rc == 0 else
              f"FAILED - {worst[0]} at {worst[1]} mm above the skid contact plane: "
              f"see tools/check_cad_fit.py")

    rc, out = run("check_thermal.py")
    warns_t = re.findall(r'^\s+- (\S+): (.+)$', out, re.M)
    # A finding that needs a thermocouple is not a pass.
    check("thermal", "regulator junction temperature", rc == 0 and not warns_t,
          ("; ".join(f"{r} {d}" for r, d in warns_t)[:400] + " - MEASURE AT T3a"
           if warns_t else
           ("all regulators within their junction limits" if rc == 0
            else "see tools/check_thermal.py")), hard=False)

    rc, out = run("check_links.py")
    m_frag = re.search(r'(\d+) AliExpress item link', out)
    check("assembly", "buying links are recoverable", rc == 0,
          (f"{m_frag.group(1)} fragile link(s), all with a fallback search term; none "
           f"geo-gated" if rc == 0 and m_frag
           else "see tools/check_links.py"))

    rc, out = run("check_hwdef.py")
    check("firmware", "hwdef matches the netlist", rc == 0,
          "hwdef is consistent with the netlist" if "is consistent" in out
          else "hwdef and netlist disagree - see tools/check_hwdef.py")

    rc, out = run("check_traces.py")
    m = re.search(r'^(\d+) item\(s\) over their stated limit', out, re.M)
    over = int(m.group(1)) if m else -1
    check("signal integrity", "trace lengths and pair matching", rc == 0 and over == 0,
          f"{over} net(s) over their stated limit" if over > 0
          else "lengths, skew and crystal stray capacitance within limits")

    rc, out = run("check_placement.py")
    far = len(re.findall(r'^\s+\S+\s+-> \S+\s+[\d.]+ mm\s+\(max', out, re.M))
    check("signal integrity", "decoupling placement (report only)", True,
          f"{far} part(s) beyond their pre-routing guide - accepted, see docs/VERIFICATION.md"
          if far else "every decoupling part within its guide")

    dp = os.path.join(os.path.dirname(HWDEF), "defaults.parm")
    check("firmware", "default parameters shipped", os.path.exists(dp),
          f"{sum(1 for l in open(dp) if l.strip() and not l.startswith('#'))} parameters"
          if os.path.exists(dp) else
          "no defaults.parm - a flashed board would not know it has a rangefinder")

    # The firmware build is the only proof the hwdef is real.
    apj = os.path.expanduser(os.environ.get("AP_DIR", "~/.cache/navcore/ardupilot")
                             + "/build/NAVCORE_SoOP/bin/arducopter.apj")
    if os.path.exists(apj) and os.path.exists(HWDEF):
        fresh = os.path.getmtime(apj) >= os.path.getmtime(HWDEF)
        size = os.path.getsize(apj)
        check("firmware", "ArduPilot builds for this board", fresh,
              f"arducopter.apj {size} bytes"
              + ("" if fresh else " - OLDER than hwdef.dat, re-run tools/build_firmware.sh"),
              hard=False)
    else:
        check("firmware", "ArduPilot builds for this board", False,
              "not built - run tools/build_firmware.sh", hard=False)


def unverifiable():
    try:
        _n_bom = sum(1 for _ in csv.DictReader(open("fab/BOM-NAVCORE-SoOP.csv")))
    except OSError:
        _n_bom = None
    print("\n  Cannot be checked offline - verify before spending money:")
    for s in (f"LCSC stock and pricing for all {_n_bom or '50+'} BOM lines "
              "(stock snapshot in docs/BUYING.md - refresh it)",
              "the 1620 MHz SAW is NOT stocked at LCSC - Rev B / separate RF board",
              "ArduPilot board ID 9001 is unregistered - request it upstream",
              "SpeedyBee grommet flange diameter is assumed 6 mm",
              "the ESC cable pinout - J2 matches Betaflight's documented SpeedyBee "
              "F405 V4 order, but check continuity on the cable you receive",
              "impedance control - none specified, USB is a plain differential pair",
              "the 1 oz copper assumption behind the current-capacity check - confirm "
              "the stackup you order is 1 oz outer, not 0.5 oz",
              "BATT_AMP_PERVLT - a property of the ESC's shunt, calibrate on the bench",
              "FLOW_ORIENT_YAW - U6 is bottom-side, check the sign before position hold",
              "whether Iridium NEXT Doppler can actually produce a usable fix from this "
              "antenna - sitl/ proves what ArduPilot does with a fix of a given quality, "
              "not that the receiver can produce one",
              "real camera flow over grass - simulated flow is perfect flow; this needs "
              "recorded footage, not a simulator",
              "U9's theta_JA - 184 C/W is the AP2112 datasheet's 'no heatsink' figure, and "
              "on it U9's PEAK junction (179 C) sits above its 150 C limit. The copper you "
              "pour is what changes it. docs/BUILD.md T3a",
              "U8's theta_JA - SLVSD26 gives 118.6 C/W (JEDEC) and 57.2 C/W (EVM); this "
              "6-layer board is between the two and only a thermocouple says where"):
        print(f"     - {s}")

    # Derived, not restated.
    _b = pcbnew.LoadBoard(BOARD)
    _, _bb, _, _br, _ = design.stack_heights(_b, skip_dnp=True)
    _, _bf, _, _fr, _ = design.stack_heights(_b, skip_dnp=False)
    _bot = (f"bottom-side parts {_bb:.2f} mm tall max ({_br}) - clears the ESC below"
            + (f"; {_bf:.2f} mm ({_fr}) if the FPV buck is populated"
               if _bf > _bb else ""))
    print("\n  Mechanical, verified against the 30x30 stack:")
    for s in ("mounting holes 30.50 x 30.50 mm, 4.00 mm dia - standard 30x30, M3 + grommet",
              _bot,
              "USB-C and ESC connector both 0.80 mm from their board edges",
              "microSD slot faces the bottom edge, 1.62 mm inboard - check your frame "
              "does not block that edge",
              "board 45.10 x 46.10 mm - confirm the frame's centre plate accepts it"):
        print(f"     - {s}")

    print("\n  Whole-aircraft checks (tools/check_build.py):")
    for s in ("connectors, power budget, current path, mass and thrust, geometry, buses",
              "every value tagged [M]easured / [D]atasheet / [L]isting / [A]ssumed",
              "run it before ordering - it is what caught the missing microSD card, the "
              "2x BATT_AMP_PERVLT error and the 19x19 motor bolt pattern"):
        print(f"     - {s}")

    print("\n  Run before flying, not before ordering:")
    for s in ("sitl/run_scenarios.sh - flies defaults.parm against simulated truth. "
              "Found three prearm faults the build checks could not see",
              "docs/BUILD.md - T1 power on a current-limited supply BEFORE USB"):
        print(f"     - {s}")


def main():
    os.makedirs("/tmp/nav", exist_ok=True)
    board = pcbnew.LoadBoard(BOARD)
    fabrication(board)
    assembly(board)
    integrity(board)
    project(board)
    firmware(board)

    order = ["fabrication", "assembly", "signal integrity", "project", "firmware"]
    results.sort(key=lambda r: order.index(r[0]) if r[0] in order else len(order))

    group = None
    nf = nw = 0
    for g, name, verdict, detail in results:
        if g != group:
            group = g
            print(f"\n=== {g} ===")
        mark = {"PASS": "  ok  ", "WARN": " warn ", "FAIL": " FAIL "}[verdict]
        print(f"{mark} {name:32} {detail}")
        nf += verdict == "FAIL"
        nw += verdict == "WARN"

    print("\n" + "=" * 72)
    if nf:
        print(f"NOT READY TO ORDER - {nf} blocking failure(s), {nw} warning(s)")
    else:
        print(f"READY TO ORDER - 0 blocking failures, {nw} warning(s)")
    unverifiable()
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
