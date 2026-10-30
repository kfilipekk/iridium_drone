#!/usr/bin/env python3
"""Production readiness gate for NAVCORE-SoOP.

Usage:  python3 tools/preflight.py [board.kicad_pcb]
"""
import os, sys, re, csv, math, glob, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design, readiness   #readiness puts kicad-tools on the path
from kicadtools import gate
from kicadtools.gate import check, cli

BOARD = os.environ.get("KICAD_BOARD") or (sys.argv[1] if len(sys.argv) > 1 else "NAVCORE-SoOP.kicad_pcb")
SCH   = "NAVCORE-SoOP.kicad_sch"
FAB   = "fab"
HWDEF = "firmware/NAVCORE_SoOP/hwdef.dat"

PLANE_LAYERS = ("In1.Cu", "In4.Cu")

def fabrication(board):
    rpt = cli(["kicad-cli", "pcb", "drc", "--output", "/tmp/nav/pf_drc.rpt",
               "--severity-error", BOARD], "/tmp/nav/pf_drc.rpt")
    check("fabrication", "kicad-cli loads the board", rpt is not None,
          "DRC ran" if rpt is not None else "kicad-cli pcb drc failed - the board did not load")
    ran, rpt = rpt is not None, rpt or ""
    cls = re.findall(r'^\[([a-z_]+)\]', rpt, re.M)
    hard = len([c for c in cls if c != "unconnected_items"])
    unconn = cls.count("unconnected_items")
    check("fabrication", "DRC errors", ran and hard == 0, f"{hard} errors" if ran else "DRC did not run")
    #split the unrouted nets by whether anything is actually fitted on them
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
    check("fabrication", "kicad-cli loads the schematic", erc is not None,
          "ERC ran" if erc is not None else "kicad-cli sch erc failed - the schematic did not load")
    ne = len(re.findall(r'^\[', erc or "", re.M))
    check("fabrication", "ERC clean", erc is not None and ne == 0,
          f"{ne} violations" if erc is not None else "ERC did not run")

    #all six copper layers must be exported
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
               f"(fab.py bundle): {', '.join(sorted(stale)[:4])}"
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

    #locating peg sink depths and copper clearance (design.MODEL_EXPECTED_SINK)
    peg_fails = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        sink = design.MODEL_EXPECTED_SINK.get(ref)
        if sink is None:
            continue
        max_sink = design.BOARD_T - 0.20
        #legs soldered through plated holes (J12's MMCX) are meant to come out underneath
        pegs = any(p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH for p in fp.Pads())
        if pegs and sink >= max_sink:
            peg_fails.append(f"{ref} peg sink {sink:.2f} mm exceeds core limit ({max_sink:.2f} mm)")
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                continue
            hole = p.GetBoundingBox()
            for other in board.GetFootprints():
                if other.IsFlipped() == fp.IsFlipped() or other.GetReference() == ref:
                    continue
                for op in other.Pads():
                    if op.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                        g = op.GetBoundingBox()
                        g.Inflate(pcbnew.FromMM(0.20))
                        if g.Intersects(hole):
                            peg_fails.append(f"{ref} peg hole under {other.GetReference()} pad {op.GetNumber()}")
    check("fabrication", "locating peg sink depth within board core", not peg_fails,
          f"{len(design.MODEL_EXPECTED_SINK)} part(s) with short pegs stop inside core (< {design.BOARD_T - 0.20:.2f} mm) and clear opposite copper"
          if not peg_fails else "; ".join(peg_fails))


def assembly(board):
    #the base build is what gets gated
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
        #a "lookup:<MPN>" sentinel is not a part number
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

    #BOM must describe this board
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
        top = sum(1 for r in rows if (r.get(lk) or "").strip().lower()[:1] == "t")
        bot = sum(1 for r in rows if (r.get(lk) or "").strip().lower()[:1] == "b")
        unknown = len(rows) - top - bot
        #the claim is two-sided assembly: every row says which side it
        check("assembly", "two-sided assembly",
              bool(lk) and unknown == 0 and top > 0 and bot > 0,
              (f"{top} top / {bot} bottom - needs a stencil for BOTH sides"
               + (f"; {unknown} row(s) name no layer" if unknown else "")
               if lk else
               "CPL has no Layer column - nothing says which side a part is on"))

    #what actually touches each face at the stack holes (design.FC_HOLE_HARDWARE)
    holes = [(d.GetCenter().x/1e6, d.GetCenter().y/1e6, d.GetRadius()/1e6)
             for d in board.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts and d.ShowShape() == "Circle"]
    hw = design.FC_HOLE_HARDWARE
    near = {}                                  #face -> (distance, ref)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            b = pad.GetBoundingBox()
            x0, y0 = b.GetLeft()/1e6, b.GetTop()/1e6
            x1, y1 = b.GetRight()/1e6, b.GetBottom()/1e6
            for face, layer in (("top", pcbnew.F_Cu), ("bottom", pcbnew.B_Cu)):
                if not pad.IsOnLayer(layer):
                    continue
                for hx, hy, _ in holes:
                    d = math.hypot(max(x0-hx, 0, hx-x1), max(y0-hy, 0, hy-y1))
                    if d < near.get(face, (99.0, None))[0]:
                        near[face] = (d, f"{fp.GetReference()}.{pad.GetNumber()}")
    bad = []
    ring = max(r for _, _, r in holes) if holes else 0.0
    for face in ("top", "bottom"):
        d, ref = near.get(face, (99.0, None))
        if d < ring:
            bad.append(f"{ref} inside the hole's {2 * ring:.1f} mm ring, against the shank")
        stack = hw[face]
        if stack[0]["conductive"] and d < stack[0]["reach_d"] / 2:
            bad.append(f"{ref} at {d:.2f} mm under the {stack[0]['name']} "
                       f"({stack[0]['reach_d'] / 2:.2f} mm)")
        if d < hw["pad_clear"]:
            bad.append(f"{ref} at {d:.2f} mm, inside the {hw['pad_clear']:.2f} mm a metal "
                       "spacer would reach")
        for lo, hi in zip(stack, stack[1:]):
            if not lo["conductive"] and hi["conductive"] and hi["reach_d"] > lo["reach_d"]:
                bad.append(f"the {hi['name']} overhangs the {lo['name']} it sits on")
    worst = min(v[0] for v in near.values()) if near else 99.0
    check("assembly", "no copper under a screw head", bool(holes) and not bad,
          "; ".join(bad) if bad else
          f"nothing metal touches a face: {hw['top'][0]['name']} top, {hw['bottom'][0]['name']} "
          f"below; nearest pad {worst:.2f} mm, clear of even a metal hex's corners")


#signal integrity
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

    #crystal proximity - the defect that started this
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
        else:
            check("signal integrity", "crystal near the MCU", False, "U1 has no pad 12")
    else:
        check("signal integrity", "crystal near the MCU", False,
              "Y1 or U1 is not on the board")


def silkscreen(board):
    """Report how many pads carry their function (design.PAD_LABELS) on the silkscreen."""
    #count what is printed, not what silk_labels could place
    try:
        placed, skipped = [], []
        for fp in board.GetFootprints():
            if "TestPoint" not in fp.GetFPIDAsString():
                continue
            want = design.PAD_LABELS.get(fp.GetReference())
            texts = {g.GetText() for g in fp.GraphicalItems()
                     if g.Type() == pcbnew.PCB_TEXT_T and g.IsVisible()
                     and g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)}
            (placed if want and want in texts else skipped).append(fp.GetReference())
    except Exception as e:
        check("fabrication", "pad silkscreen labels", False,
              f"could not evaluate: {e}")
        return
    total = len(placed) + len(skipped)
    listed = set(getattr(design, "PAD_LABELS_UNPRINTED", {}))
    unlisted = sorted(set(skipped) - listed)
    stale = sorted(listed & set(placed))
    ok = not unlisted and not stale
    detail = (f"{len(placed)}/{total} pads carry their function on the silkscreen"
              + (f"; unprinted by design, on padmap.svg: {', '.join(sorted(set(skipped) & listed))}"
                 if set(skipped) & listed else "")
              + (f"; BLANK and not in PAD_LABELS_UNPRINTED: {', '.join(unlisted)}" if unlisted else "")
              + (f"; labelled but still listed as unprinted: {', '.join(stale)}" if stale else ""))
    check("fabrication", "pad silkscreen labels", ok, detail)

    #the same for connector names (silk_names.py prints them as board texts)
    printed = {d.GetText() for d in board.GetDrawings()
               if d.Type() == pcbnew.PCB_TEXT_T and d.IsVisible()
               and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)}
    names = getattr(design, "SILK_NAMES", {})
    on = sorted(r for r, n in names.items() if n in printed)
    off = sorted(set(names) - set(on))
    listed = set(getattr(design, "SILK_NAMES_UNPRINTED", {}))
    unlisted = sorted(set(off) - listed)
    stale = sorted(listed & set(on))
    check("fabrication", "connector names on the silkscreen", not unlisted and not stale,
          f"{len(on)}/{len(names)} connectors named"
          + (f"; unprinted by design, on padmap.svg: {', '.join(sorted(set(off) & listed))}"
             if set(off) & listed else "")
          + (f"; BLANK and not in SILK_NAMES_UNPRINTED: {', '.join(unlisted)}" if unlisted else "")
          + (f"; named but still listed as unprinted: {', '.join(stale)}" if stale else ""))


def project(board):
    """Everything the drone actually needs, by function rather than by part."""
    refs = {fp.GetReference() for fp in board.GetFootprints()}
    dnp = {r for r in refs
           if (design.COMPONENTS.get(r) or (0, 0, 0, 0, False))[4]}
    fitted = refs - dnp
    nets = {n.GetNetname() for n in board.GetNetInfo().NetsByName().values()}

    NEED = [
        ("MCU STM32H743",            {"U1"}),
        ("IMU 1 (ICM-45686)",        {"U2"}),
        ("IMU 2 (ICM-42605)",        {"U3"}),
        ("barometer MS5611",         {"U4"}),
        ("dedicated I2C port",        {"J9"}),
        ("config flash W25Q128",     {"U5"}),
        ("microSD socket",           {"J8"}),
        ("USB-C",                    {"J1"}),
        ("USB ESD protection",       {"U12"}),
        ("ESC connector (JST-GH 8)", {"J2"}),
        ("GPS / telemetry JST-GH",   {"J3"}),
        ("CAN transceiver",          {"U11"}),
        ("5 V buck",                 {"U8"}),
        ("payload 5 V buck",         {"U20"}),
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
        ("power rails",            ("+3V3", "+5V", "+5V_PAYLOAD", "+3V3_CAN", "VBAT",
                                    "VBAT_IN", "GND")),
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
    run = gate.run

    rc, out = run("check_circuit.py topology")
    check("fabrication", "datasheet-required externals present", rc == 0,
          "every IC has the external components its datasheet requires" if rc == 0 else
          "a required component is ABSENT - see tools/check_circuit.py topology")

    rc, out = run("check.py backside")
    m = re.search(r'(\d+) through-holes checked', out)
    check("fabrication", "no pin lands under a part on the other side", rc == 0,
          (f"{m.group(1) if m else '?'} through-holes clear of every opposite-side body"
           if rc == 0 else
           "a through-hole pin or post lands under a part - see check.py backside"))

    #a label nearer a neighbour than its own part is read as the neighbour's
    rc, out = run("check.py silk_owner")
    m = re.search(r'(\d+) printed labels checked', out)
    check("fabrication", "every label reads as its own part's", rc == 0,
          (f"{m.group(1) if m else '?'} printed labels, each nearest the part it names"
           if rc == 0 else
           "a label sits nearer another part - see check.py silk_owner"))

    #the 3D bodies the renders and any enclosure CAD are drawn
    rc, out = run("check.py model_alignment")
    m = re.search(r'(\d+) bodies tested against each other', out)
    check("fabrication", "3D bodies sit on their footprints and overlap nothing", rc == 0,
          (f"{m.group(1) if m else '?'} bodies, each on its footprint, none overlapping another "
           "or the stack hardware"
           if rc == 0 else
           "a 3D body is misplaced, overlaps another or sits under the stack hardware - see "
           "check.py model_alignment"))

    rc, out = run("check_mech.py build")
    m = re.search(r'BUILD CHECKS PASS - (\d+) checks across (\d+)', out)
    check("mechanical", "aircraft-level build checks", rc == 0,
          (f"{m.group(1)} checks across {m.group(2)} areas" if m else
           "see tools/check_mech.py build") if rc == 0 else
          "the aircraft does not add up - see tools/check_mech.py build")

    #stock and part resolution against JLCPCB itself, from a dated snapshot
    rc, out = run("fab.py stock")
    m = re.search(r'(\d+)/(\d+) line\(s\) resolved with stock', out)
    age = re.search(r'snapshot\s+:\s+\S+ \((\d+) day', out)
    check("assembly", "every BOM line is buyable", rc == 0,
          (f"{m.group(1)}/{m.group(2)} lines in stock for the order, snapshot "
           f"{age.group(1)} day(s) old" if m else
           "stock/part check failed - see fab.py stock") if rc == 0 else
          "a BOM line is unavailable, unreachable or resolves to the wrong part - "
          "see fab.py stock")

    rc, out = run("check_order.py rf")
    check("fly", "link budget has bench data", rc == 0,
          "T3b measurements recorded and within budget" if rc == 0 else
          "no T3b bench measurements yet - gates FLYING, not ordering", hard=False)

    rc, out = run("check_firmware.py sitl")
    #the count comes from the line check_firmware.py sitl actually prints
    m = re.search(r'mechanisms\s*:\s*(\d+)/(\d+) asserting', out)
    n_info = re.search(r'measurement:\s*(\d+) informational', out)
    first_problem = re.search(r'^FAIL - \d+ problem\(s\):\n\s+- (.+)$', out, re.M)
    if m and rc == 0:
        _sitl = (f"{m.group(1)}/{m.group(2)} asserting scenarios pass"
                 + (f", {n_info.group(1)} measured not gated" if n_info else "")
                 + ", against the parameters that ship")
    elif first_problem:
        _sitl = (f"{m.group(1)}/{m.group(2)} asserting scenarios pass, but the suite is "
                 f"NOT green - {first_problem.group(1).strip()}" if m else
                 f"the suite is NOT green - {first_problem.group(1).strip()}")
    elif m:
        _sitl = (f"{m.group(1)}/{m.group(2)} asserting scenarios pass, but check_firmware.py sitl "
                 f"exited non-zero and named no problem - its output above says why")
    else:
        #no count at all
        _sitl = ("check_firmware.py sitl reported no scenario count - its output above says why; "
                 "a suite that has not run is not a passing suite")
    check("firmware", "SITL scenarios pass", rc == 0, _sitl)

    #the real-ephemeris prerequisite
    rc, out = run("check_soop.py ephemeris")
    m = re.search(r'EPHEMERIS OK - (\d+)/(\d+) assertions on (\d+) real', out)
    check("firmware", "real Iridium ephemeris inverts the geometry", rc == 0,
          (f"SGP4 + TLE, {m.group(3)} satellites, {m.group(1)}/{m.group(2)} assertions"
           if m else "see tools/check_soop.py ephemeris") if rc == 0 else
          "the SGP4/TLE ephemeris or the TEME->ECEF frame conversion does not hold - "
          "see tools/check_soop.py ephemeris")

    #the C SGP4 propagator, gated
    rc, out = run("check_soop.py sgp4")
    m = re.search(r'(\d+) checks against Python reference \(tol: (\d+) m', out)
    check("firmware", "C SGP4 propagator agrees with Python reference and builds for the target",
          rc == 0,
          (f"{m.group(1)} checks, tol {m.group(2)} m, cross-compiled Cortex-M7"
           if m else "see tools/check_soop.py sgp4") if rc == 0 else
          "the C SGP4 propagator disagrees with Python sgp4.api.Satrec or does not "
          "cross-compile - see tools/check_soop.py sgp4")

    #the burst-DSP prerequisite, gated
    rc, out = run("check_soop.py burst")
    m = re.search(r'BURST DSP OK - (\d+)/(\d+) assertions, p90 ([\d.]+) Hz < 5 Hz '
                  r'at C/N0 (\d+) dB-Hz', out)
    check("firmware", "burst detection and carrier estimation meet the 5 Hz target",
          rc == 0,
          (f"{m.group(1)}/{m.group(2)} assertions, p90 {m.group(3)} Hz, "
           f"C/N0 {m.group(4)} dB-Hz on synthetic I/Q" if m else
           "see tools/check_soop.py burst") if rc == 0 else
          "the burst detector or the carrier estimator does not meet the solver's "
          "precision - see tools/check_soop.py burst")

    #the on-board DSP in C
    rc, out = run("check_soop.py dsp")
    m = re.search(r'SOOP-DSP OK - (\d+)/(\d+) assertions', out)
    p = re.search(r'carrier error p90 ([\d.]+) Hz at >= (\d+) dB-Hz', out)
    check("firmware", "the on-board DSP finds bursts and meets 5 Hz on a simulated sky",
          rc == 0,
          (f"{m.group(1)}/{m.group(2)} assertions, p90 {p.group(1)} Hz at >= {p.group(2)} dB-Hz, "
           f"C built for the H743" if m and p else
           "see tools/check_soop.py dsp") if rc == 0 else
          "the C burst DSP misses, invents or mis-measures bursts on the simulated sky - "
          "see tools/check_soop.py dsp")

    #the on-board navigation in C
    rc, out = run("check_soop.py nav")
    m = re.search(r'SOOP-NAV OK - (\d+)/(\d+) assertions', out)
    e = re.search(r'median (\d+) m, p95 (\d+) m, max (\d+) m', out)
    check("firmware", "the on-board navigation holds position through simulated denied flights",
          rc == 0,
          (f"{m.group(1)}/{m.group(2)} assertions, median {e.group(1)} m, p95 {e.group(2)} m "
           f"over the denied flights, C built for the H743" if m and e else
           "see tools/check_soop.py nav") if rc == 0 else
          "the C navigation loses position, reports an accuracy it does not have, or "
          "credits bursts to the wrong satellite - see tools/check_soop.py nav")

    #the C port of the solve, gated
    rc, out = run("check_soop.py solver")
    m = re.search(r'SOOP-C OK - C solver agrees with Python to ([\d.eE+-]+) m', out)
    check("firmware", "the C solver agrees with the Python reference and builds for the target",
          rc == 0,
          (f"differential on identical observations, agreement {m.group(1)} m, "
           f"cross-compiled Cortex-M7" if m else
           "see tools/check_soop.py solver") if rc == 0 else
          "the C solver disagrees with the Python reference, or does not build for the "
          "target - see tools/check_soop.py solver")

    #the SoOP AP_GPS backend, gated
    rc, out = run("check_firmware.py soop_backend")
    m = re.search(r'AP_GPS_SoOP::read\(\) is (\d+) bytes', out)
    check("firmware", "the SoOP GPS backend is registered and compiled into the firmware",
          rc == 0,
          (f"GPS_TYPE_SOOP = 27; backend read() {m.group(1)} bytes in the board and SITL "
           f"firmwares" if m else "see tools/check_firmware.py soop_backend") if rc == 0 else
          "the SoOP backend is not registered or not in the firmware - see "
          "tools/check_firmware.py soop_backend")

    rc, out = run("check_firmware.py soop_sitl")
    check("firmware", "SoOP fix reaches the EKF", rc == 0,
          "GPS_RAW_INT has a 3D SoOP fix and EKF publishes global position"
          if rc == 0 else "see tools/check_firmware.py soop_sitl")

    rc, out = run("check_order.py bench_bounds")
    n = re.search(r'^(\d+) items accounted for: (.*)$', out, re.M)
    check("mechanical", "no bench item can change what is ordered", rc == 0,
          (f"{n.group(1)} classified - {n.group(2)}" if n else
           "see tools/check_order.py bench_bounds") if rc == 0 else
          "a bench item could force a board change - see tools/check_order.py bench_bounds")

    rc, out = run("check_board.py connectors")
    nf = re.search(r'^(\d+) failure\(s\), (\d+) warning\(s\)', out, re.M)
    bad = re.findall(r'^  FAIL  (\S+):', out, re.M)
    check("fabrication", "connectors face off-board", rc == 0,
          (f"{', '.join(bad)} cannot be plugged in" if bad else
           f"all {len(design.MATING_FACE)} openings clear the board"
           + (f", {nf.group(2)} warning(s)" if nf and nf.group(2) != '0' else "")))

    rc, out = run("check_board.py floorplan")
    m = re.search(r'(\d+) failure\(s\), (\d+) ports', out)
    check("fabrication", "perimeter floorplan and plug clearances", rc == 0,
          (f"all {m.group(2) if m else '?'} perimeter ports seated, latches and plugs clear" if rc == 0 else
           "perimeter port or plug clearance violation - see tools/check_board.py floorplan"))

    rc, out = run("check_mech.py mechanical")
    m = re.search(r'^(\d+) computed check\(s\) ok', out, re.M)
    unk = "!! footprints with no declared height" in out
    check("fabrication", "mechanical fit in the stack", rc == 0 and not unk,
          ("some footprints have no declared height" if unk else
           f"{m.group(1) if m else '?'} computed checks ok; frame items listed for measurement"))

    rc, out = run("check_circuit.py pin_semantics")
    bad = re.search(r'^(\d+) pin\(s\) are wired or configured the wrong way', out, re.M)
    check("firmware", "pins run the right way", rc == 0,
          f"{bad.group(1)} pin(s) wrong" if bad else "direction, reset level and role agree")

    #ratings: is each part actually rated for the net it sits on?
    rc, out = run("check_circuit.py ratings")
    m = re.search(r'^(\d+) failure\(s\), (\d+) warning\(s\), (\d+) unrated', out, re.M)
    check("firmware", "parts rated for their nets", rc == 0,
          (f"{m.group(1)} over-rating/package failure(s)" if m and m.group(1) != '0' else
           f"all capacitors rated; {m.group(2) if m else '?'} derating note(s)"))

    rc, out = run("check_circuit.py electrical")
    m = re.search(r'^ERRORS \((\d+)\)', out, re.M)
    w = re.search(r'^WARNINGS \((\d+)\)', out, re.M)
    check("firmware", "electrical values", rc == 0,
          f"{m.group(1)} error(s)" if m else
          f"dividers, decoupling and pull-ups check out"
          + (f"; {w.group(1)} warning(s)" if w else ""))

    #the SPICE suite simulates the analogue blocks from design.py and fails on a bound
    rc, out = run("check_soop.py spice")
    m = re.search(r'SIM OK - (\d+)/(\d+) assertions across (\d+) deck', out)
    check("firmware", "analogue blocks simulate inside their limits", rc == 0,
          (f"{m.group(1)}/{m.group(2)} assertions across {m.group(3)} decks" if m
           else "the suite printed no tally - see sim/run_suite.py") if rc == 0 else
          "a simulation bound is violated, or a deck did not run - see sim/run_suite.py")

    rc, out = run("check_soop.py gain")
    m = re.search(r"noise per rail: (\d+) counts \(spread (\d+)-(\d+)\)", out)
    check("firmware", "the receiver's gain plan suits the DSP", rc == 0,
          (f"noise {m.group(1)} counts at the ADC ({m.group(2)}-{m.group(3)}), the DSP gated at "
           f"both ends" if m else "see tools/check_soop.py gain") if rc == 0 else
          "the chain clips, compresses or sinks under the ADC - see tools/check_soop.py gain")

    rc, out = run("check_soop.py spurs")
    check("firmware", "no clock harmonic in the Ring Alert window", rc == 0,
          "every steady clock folds clear of the DSP's search window" if rc == 0 else
          "a clock harmonic lands where the DSP looks - see tools/check_soop.py spurs")

    rc, out = run("check_soop.py bench")
    check("firmware", "the bench tool and its LO search work", rc == 0,
          "soop_bench.py runs, and finds a mistuned recording's LO" if rc == 0 else
          "soop_bench.py or its LO search fails - see tools/check_soop.py bench")

    rc, out = run("check_soop.py flow")
    check("firmware", "the guard's flow velocity matches EKF3's model", rc == 0,
          "soop_flow_velocity inverts EKF3's flow model" if rc == 0 else
          "the flow velocity disagrees with EKF3's flow model - see tools/check_soop.py flow")

    rc, out = run("check_soop.py antenna")
    m = re.search(r'ANT CHECK (?:PASSED|FAILED): (\d+) failure\(s\), (\d+) steps simulated', out)
    check("firmware", "antenna bias feed monitor", rc == 0,
          (f"active antenna feed monitor verified ({m.group(2) if m else '?'} simulated steps)" if rc == 0 else
           "antenna bias feed monitor failed - see tools/check_soop.py antenna"))

    rc, out = run("check_soop.py max2112")
    m = re.search(r'(\d+) register images and (\d+) status pairs', out)
    check("firmware", "tuner registers match the MAX2112 datasheet", rc == 0,
          (f"{m.group(1)} register images and {m.group(2)} status pairs decoded field by field"
           if rc == 0 and m else "the tuner's register image or lock decode disagrees with "
           "the datasheet - see tools/check_soop.py max2112"))

    rc, out = run("check_firmware.py params")
    fw = re.search(r'^firmware\s+:\s+(.+?)\s+\(tag (\S+)\)', out, re.M)
    check("firmware", "parameters exist in the target build", rc == 0,
          (f"validated against {fw.group(1)} / {fw.group(2)}" if fw
           else "could not validate - run tools/build_firmware.sh"))

    #check_params.py proves a parameter name is real
    rc, out = run("check_firmware.py features")
    m = re.search(r'^(\d+) enabled feature', out, re.M)
    check("firmware", "enabled features are IN the binary", rc == 0,
          (f"{m.group(1)} feature(s) traced from defaults.parm into linked symbols"
           if m and rc == 0 else
           "a parameter selects a driver this build does not contain - see "
           "tools/check_firmware.py features"))

    rc, out = run("irdrop.py check")
    rails = re.findall(r'^  (?:ok  |FAIL) (\S+)\s+[\d.]+ A over', out, re.M)
    first = re.search(r'^FAIL - \d+ problem\(s\):\n\s+- (.+)$', out, re.M)
    check("firmware", "power copper reaches the loads", rc == 0,
          f"{len(rails)} rails solved at their budget: drop, current density and vias in limit"
          if rc == 0 else (first.group(1) if first else "irdrop.py check did not run"))

    rc, out = run("check.py cpl")
    m = re.search(r'cross-checked\s+:\s+(\d+) parts across (\d+)', out)
    check("assembly", "CPL rotations self-consistent", rc == 0,
          (f"{m.group(1)} parts across {m.group(2)} shared footprints agree on pin 1"
           if m else "geometry check failed - see check.py cpl"))

    #the order bundle is the artefact that actually gets uploaded
    rc, out = run("fab.py check_bundle")
    m = re.search(r'gerbers\s+:\s+(\d+) identical, (\d+) diverged, (\d+) absent', out)
    check("assembly", "order bundle matches the tree", rc == 0,
          (f"{m.group(1) if m else '?'} gerber(s) and every BOM/CPL copy identical to "
           f"fab/; placement counts re-derived from the bundled CPL") if rc == 0 else
          "the order bundle is stale or incomplete - re-run fab.py bundle")

    #every order-time action in the manifest, stated on the sheet that goes up with the bundle
    sheet = open(os.path.join(FAB, "HOW-TO-ORDER.in")).read()
    acts = [p for p in readiness.PREREQUISITES if p["cls"] == readiness.ORDER_ACTION]
    missing = [p["id"] for p in acts if not re.search(p["sheet"], sheet)]
    check("assembly", "the order sheet states every checkout setting", not missing,
          f"all {len(acts)} order-time actions are on HOW-TO-ORDER" if not missing else
          "HOW-TO-ORDER.in does not state: " + ", ".join(missing))

    rc, out = run("fab.py variants")
    m = re.search(r'^(\d+) variant pair\(s\) checked', out, re.M)
    check("assembly", "every BOM/CPL variant matches the board", rc == 0,
          (f"{m.group(1)} variant pair(s) agree with the board and the design" if m else
           "checked, but the count was not reported") if rc == 0 else
          "a variant BOM/CPL describes a different board - see fab.py variants")

    rc, out = run("check_circuit.py symbol_pinout")
    m = re.search(r'(\d+) symbol\(s\) have NO outside authority', out)
    check("fabrication", "symbol pinouts match an outside authority", rc == 0,
          "every active part agrees with KiCad's library or its datasheet" if rc == 0
          else (f"{m.group(1)} symbol(s) verified against nothing - see "
                f"tools/check_circuit.py symbol_pinout" if m else
                "a symbol DISAGREES with its authority - see tools/check_circuit.py symbol_pinout"))

    #"The library is in git" and "the project still builds" are different properties
    rc, out = run("check.py libraries")
    m = re.search(r'compared\s+:\s+(\d+) ref', out)
    o = re.search(r'vendored\s+:\s+(\d+) file\(s\), (\d+) unreferenced', out)
    check("fabrication", "vendored part library is load-bearing", rc == 0,
          (f"{m.group(1) if m else '?'} ref(s) agree with the board; "
           f"{o.group(1) if o else '?'} footprint(s), "
           f"{o.group(2) if o else '?'} orphaned") if rc == 0 else
          "the vendored library is incomplete, diverged from the board, or has orphaned "
          "files - see check.py libraries")

    rc, out = run("check_circuit.py design")
    w = re.search(r'^WARNINGS \((\d+)\)', out, re.M)
    check("fabrication", "schematic matches the netlist", rc == 0 and "no errors" in out,
          "netlist, pin coverage and hwdef agree"
          + (f"; {w.group(1)} unconnected-pin note(s)" if w else ""))

    #the artwork's own LCSC fields
    rc, out = run("fab.py lcsc")
    n = re.search(r'^(\S+): (\d+) LCSC field\(s\) disagree', out, re.M)
    check("fabrication", "artwork LCSC fields match design.py", rc == 0,
          ("every symbol and footprint carries the code design.py assigns"
           if rc == 0 else
           (f"{n.group(2)} LCSC field(s) in {n.group(1)} disagree with design.py - "
            f"run fab.py lcsc --write" if n else
            "artwork part numbers disagree with design.py - run "
            "fab.py lcsc --write")))

    rc, out = run("gen_doc_tables.py --check")
    check("firmware", "generated doc tables match the code", rc == 0,
          "the runbook's buy list matches docs/PARTS.csv" if rc == 0
          else "a generated table is stale - run tools/gen_doc_tables.py")

    #the pad map is where every unprinted label is documented
    rc, out = run("gen_padmap.py --check")
    check("fabrication", "pad map matches the board", rc == 0,
          "docs/img/padmap.svg shows every pad and connector as built" if rc == 0
          else "docs/img/padmap.svg is stale - run tools/gen_padmap.py")

    rc, out = run("gen_scad_frame.py --check")
    check("mechanical", "CAD frame matches design.FRAME", rc == 0,
          "cad/frame.scad is current" if rc == 0
          else "cad/frame.scad is stale - run tools/gen_scad_frame.py")

    rc, out = run("gen_scad_mounts.py --check")
    check("mechanical", "CAD mounts match design.MOUNTS", rc == 0,
          "cad/mounts.scad is current" if rc == 0
          else "cad/mounts.scad is stale - run tools/gen_scad_mounts.py")

    rc, out = run("check_order.py purchase")
    m = re.search(r'^(\d+) interface\(s\) still rest on an ASSUMED', out, re.M)
    check("mechanical", "buy-to-buy interfaces mate", rc == 0,
          ("every buy-to-buy interface asserted"
           + (f"; {m.group(1)} still on an ASSUMED source - confirm on the listing" if m
              else "")) if rc == 0
          else "an interface does not mate - see tools/check_order.py purchase")

    rc, out = run("check_order.py modules")
    m = re.search(r'(\d+)/(\d+) modules attach', out)
    check("firmware", "later modules still have somewhere to land", rc == 0,
          f"{m.group(1)}/{m.group(2)} modules attach to the board as fabricated; "
          f"the +5 V rail cannot carry them all at once" if m and rc == 0
          else "a module's landing pads are missing - see tools/check_order.py modules")

    rc, out = run("check_order.py payload")
    m = re.search(r'payload provisions intact: (.+)$', out, re.M)
    check("firmware", "payload provisions still spare", rc == 0,
          m.group(1).strip() if m
          else "a payload provision has been consumed - see tools/check_order.py payload")

    #geometric fit of the whole aircraft
    rc, out = run("check_mech.py cad_fit")
    m = re.search(r'PASS - (\d+) pairs', out)
    check("mechanical", "assembly has no interference", rc == 0,
          f"{m.group(1)} part pairs checked by intersection volume, all clear" if m
          else "parts overlap in the assembly - see tools/check_mech.py cad_fit")

    mounts = re.findall(r'^  (\w+)\s+carries .* joint\(s\)\s+(ok|FAIL)$', out, re.M)
    sky = re.findall(r'^  (\w+)\s+highest obstruction\s+([-\d.]+) deg.*(ok|FAIL)$', out, re.M)
    printed = re.findall(r'^  (\w+)\s+[\d.]+ x .* (ok|FAIL)$', out, re.M)
    #judged on its own rows, not the tool's global exit
    good = (bool(mounts) and bool(sky) and bool(printed)
            and all(v[-1] == "ok" for v in mounts + sky + printed))
    check("mechanical", "every part off the board is mounted, with screws", good,
          f"{len(mounts)} printed mounts, every joint derived and sold; {len(printed)} printed "
          f"parts fit the printer as closed solids; nothing rises more than "
          f"{max(float(v[1]) for v in sky):.1f} deg above the GPS or the Iridium antenna" if good else
          "a part lacks a mount, a joint or its sky - see tools/check_mech.py cad_fit")

    g = re.findall(r'^\s+(\w+)\s+lowest z\s+[-\d.]+\s+clearance\s+([-\d.]+) mm'
                   r'\s+\(need ([\d.]+)\)', out, re.M)
    #each part against its own need (check_mech.GROUND_PARTS)
    short = [(n_, float(c), float(nd)) for n_, c, nd in g if float(c) < float(nd) - 1e-6]
    if g:
        worst = min(g, key=lambda x: float(x[1]) - float(x[2]))
        check("mechanical", "belly parts clear the ground", not short,
              f"{len(g)} hanging part(s); tightest is {worst[0]} at {worst[1]} mm above "
              f"the skid contact plane (needs {worst[2]})"
              if not short else
              "FAILED - " + ", ".join(f"{n_} {c:.2f} mm (needs {nd:.1f})"
                                      for n_, c, nd in short)
              + " above the skid contact plane: see tools/check_mech.py cad_fit")
    else:
        check("mechanical", "belly parts clear the ground", False,
              "check_mech.py cad_fit reported no ground clearances")

    rc, out = run("check_mech.py balance")
    m = re.search(r'static tip angle ([\d.]+) deg', out)
    o = re.search(r'CG ([\d.]+) mm from the thrust centre', out)
    check("mechanical", "centre of gravity and tip-over", rc == 0,
          f"CG {o.group(1) if o else '?'} mm off the thrust centre; tips past "
          f"{m.group(1) if m else '?'} deg" if rc == 0
          else "the CG is off-centre or the skids tip too easily - see tools/check_mech.py balance")

    rc, out = run("check_mech.py prints")
    m = re.search(r'(\d+) printed parts', out)
    check("mechanical", "printed parts are current STLs", rc == 0,
          f"{m.group(1) if m else '?'} parts in cad/print, each the solid today's design exports"
          if rc == 0 else "a printed part is missing or stale - see tools/check_mech.py prints")

    rc, out = run("check_mech.py cables")
    m = re.search(r'PASS - (\d+) cables routed', out)
    check("mechanical", "cable harness routing and clearances", rc == 0,
          (f"{m.group(1) if m else '?'} cables routed, bend radii and clearances met" if rc == 0 else
           "cable routing, bend or clearance violation - see tools/check_mech.py cables"))

    #the bolted joints, as joints
    rc, out = run("check_mech.py fit")
    check("mechanical", "bolted joints fit by declaration", rc == 0,
          "motor/arm/skid joint, stack bolt, top-plate clearance and standoff posts "
          "all verified - see tools/check_mech.py fit" if rc == 0
          else "a joint does not fit - see tools/check_mech.py fit")

    rc, out = run("check_circuit.py thermal")
    warns_t = re.findall(r'^\s+- (\S+): (.+)$', out, re.M)
    #a finding that needs a thermocouple is not a pass
    check("thermal", "regulator junction temperature", rc == 0 and not warns_t,
          ("; ".join(f"{r} {d}" for r, d in warns_t)[:400] + " - MEASURE AT T3a"
           if warns_t else
           ("all regulators within their junction limits" if rc == 0
            else "see tools/check_circuit.py thermal")), hard=False)

    rc, out = run("check.py footprints")
    m_fp = re.search(r'(\d+) footprint\(s\) agree', out)
    check("assembly", "footprints match JLCPCB's pad count", rc == 0 and bool(m_fp),
          f"{m_fp.group(1)} footprint(s) agree with JLCPCB's joint count"
          if rc == 0 and m_fp else "MISMATCH or no authority - see check.py footprints")

    rc, out = run("fab.py paste --scan")
    m_wp = re.search(r'(\d+) pad\(s\) need windowpaning', out)
    check("assembly", "exposed pads windowpaned", rc == 0,
          "every thermal slug has a vented paste array" if rc == 0
          else (f"{m_wp.group(1) if m_wp else '?'} exposed pad(s) still carry a solid "
                f"100% aperture - run fab.py paste <REF> <PAD> --apply"))

    rc, out = run("check_order.py links")
    m_frag = re.search(r'(\d+) AliExpress item link', out)
    check("assembly", "buying links are recoverable", rc == 0,
          (f"{m_frag.group(1)} fragile link(s), all with a fallback search term; none "
           f"geo-gated" if rc == 0 and m_frag
           else "see tools/check_order.py links"))

    #check_links.py proves the buying links resolve
    rc, out = run("check_order.py doc_figures")
    m_ret = re.search(r'(\d+) mention\(s\) of', out)
    n_exc = re.search(r'(\d+) mention\(s\) are marked as retired', out)
    check("assembly", "no retired figure reads as current", rc == 0,
          (f"{n_exc.group(1) if n_exc else m_ret.group(1) if m_ret else '?'} retired "
           f"mention(s) in the live docs, every one marked as retired" if rc == 0
           else "a retired figure is presented as current - run tools/check_order.py doc_figures"))

    rc, out = run("check_order.py module_wiring")
    m = re.search(r'(\d+) module\(s\) wire cleanly, (\d+) need a cable splice', out)
    check("firmware", "modules plug in without splicing cables", rc == 0,
          (f"{m.group(1)} clean, {m.group(2)} splice(s)" if m and rc == 0 else
           f"{m.group(2) if m else '?'} module(s) need a cable splice - "
           "see tools/check_order.py module_wiring"))

    rc, out = run("check_firmware.py hwdef")
    check("firmware", "hwdef matches the netlist", rc == 0,
          "hwdef is consistent with the netlist" if "is consistent" in out
          else "hwdef and netlist disagree - see tools/check_firmware.py hwdef")

    rc, out = run("check_circuit.py esd")
    m = re.search(r'(\d+) off-board signal pin', out)
    check("signal integrity", "off-board signals clamped at their connectors", rc == 0,
          f"{m.group(1) if m else '?'} cable-facing pins, each with a clamp, series R in the path"
          if rc == 0 else "a cable-facing pin is unclamped or bypassed - see tools/check_circuit.py esd")

    rc, out = run("check_firmware.py bdshot")
    check("firmware", "motors can run bidirectional DShot", rc == 0,
          "BIDIR timers on all four motors, each with DMA of its own" if rc == 0
          else "a motor cannot capture its ESC's reply - see tools/check_firmware.py bdshot")

    rc, out = run("check_board.py traces")
    m = re.search(r'^(\d+) item\(s\) over their stated limit', out, re.M)
    over = int(m.group(1)) if m else -1
    check("signal integrity", "trace lengths and pair matching", rc == 0 and over == 0,
          f"{over} net(s) over their stated limit" if over > 0
          else "lengths, skew and crystal stray capacitance within limits")

    rc, out = run("check.py geometry")
    m = re.search(r'FAIL - (\d+) acute corner\(s\), (\d+) dangling item\(s\), (\d+) dead copper item\(s\)(?:, (\d+) via\(s\) in pad mask openings)?', out)
    check("signal integrity", "no acute corners or dead copper", rc == 0,
          "every track corner is 90 degrees or wider, all copper leads somewhere and no vias in pads" if rc == 0 else
          f"{m.group(1)} acute, {m.group(2)} dangling, {m.group(3)} dead, {m.group(4) or 0} via-in-pad"
          " - see check.py geometry" if m else "check.py geometry did not run")

    rc, out = run("check_board.py placement")
    far = len(re.findall(r'^\s+\S+\s+-> \S+\s+[\d.]+ mm\s+\(max', out, re.M))
    check("signal integrity", "decoupling placement (report only)", True,
          f"{far} part(s) beyond their pre-routing guide - accepted, see docs/VERIFICATION.md"
          if far else "every decoupling part within its guide")

    dp = os.path.join(os.path.dirname(HWDEF), "defaults.parm")
    check("firmware", "default parameters shipped", os.path.exists(dp),
          f"{sum(1 for l in open(dp) if l.strip() and not l.startswith('#'))} parameters"
          if os.path.exists(dp) else
          "no defaults.parm - a flashed board would not know it has a rangefinder")

    #the firmware build is the only proof the hwdef is real
    apj = os.path.expanduser(os.environ.get("AP_DIR", "~/.cache/navcore/ardupilot")
                             + "/build/NAVCORE_SoOP/bin/arducopter.apj")
    stamp = apj + ".hwdef.sha256"
    if os.path.exists(apj) and os.path.exists(HWDEF):
        size = os.path.getsize(apj)
        have = hashlib.sha256(open(HWDEF, "rb").read()).hexdigest()
        built = ""
        if os.path.exists(stamp):
            parts = open(stamp).read().split()
            built = parts[0] if parts else ""
        if built:
            fresh, basis = have == built, f"hwdef sha256 {have[:12]}"
        else:
            fresh = os.path.getmtime(apj) >= os.path.getmtime(HWDEF)
            basis = "no digest recorded, fell back to timestamps"
        check("firmware", "ArduPilot builds for this board", fresh,
              f"arducopter.apj {size} bytes, {basis}"
              + ("" if fresh else " - does NOT match the hwdef on disk, "
                                   "re-run tools/build_firmware.sh"))
    else:
        check("firmware", "ArduPilot builds for this board", False,
              "not built - run tools/build_firmware.sh")


def main():
    os.makedirs("/tmp/nav", exist_ok=True)
    board = pcbnew.LoadBoard(BOARD)
    fabrication(board)
    assembly(board)
    integrity(board)
    silkscreen(board)
    project(board)
    firmware(board)

    return gate.report(readiness.PREREQUISITES,
                       ["fabrication", "assembly", "signal integrity", "project", "firmware",
                        "mechanical", "thermal", "fly"],
                       "tools/readiness.py", "tools/check_order.py bench_bounds")


if __name__ == "__main__":
    sys.exit(main())
