#!/usr/bin/env python3
"""Prove every gated check can fail, not merely that it passes.

Usage:  python3 tools/fault_injection.py [--recapture] [--list-gaps]
"""
import argparse
import math
import contextlib
import csv
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import readiness  # noqa: E402
import preflight  # noqa: E402  (imported here so run_gate can reach it)
import design     # noqa: E402

#keep the real subprocess.run
_REAL_RUN = subprocess.run

GATED = readiness.GATED
CAPTURE_DIR = os.path.join("/tmp", "nav_gate_toolout")


def capture_tools(outdir):
    """Run the real gate with every subprocess's output teed to `outdir`."""
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        os.unlink(os.path.join(outdir, f))

    def patched(args, *a, **k):
        r = _REAL_RUN(args, *a, **k)
        argv = [str(x) for x in (args if isinstance(args, (list, tuple)) else [args])]
        label = (readiness.tool_id(argv) or os.path.basename(argv[0])).replace(".py", "")
        text = lambda x: x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")
        with open(os.path.join(outdir, f"{label}.txt"), "a", encoding="utf-8") as fh:
            fh.write(f"\n##### argv={' '.join(argv)} rc={r.returncode}\n{text(r.stdout)}")
            if r.stderr:
                fh.write(f"\n##### stderr\n{text(r.stderr)}")
        return r

    subprocess.run = patched
    try:
        preflight.BOARD = "NAVCORE-SoOP.kicad_pcb"
        preflight.main()
    finally:
        subprocess.run = _REAL_RUN



def parse_capture(directory):
    """{tool basename: stdout it printed when green}, from the auditor's tee."""
    out = {}
    if not os.path.isdir(directory):
        return out
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".txt"):
            continue
        text = open(os.path.join(directory, name), encoding="utf-8",
                    errors="replace").read()
        heads = re.findall(r"^##### (.*)$", text, re.M)
        bodies = re.split(r"^##### .*$", text, flags=re.M)
        for i, head in enumerate(heads):
            if not head.startswith("argv="):
                continue                       #the "stderr" marker, already folded in
            argv_str, _, rc = head[len("argv="):].rpartition(" rc=")
            tool = readiness.tool_id(argv_str.split())
            if tool is None:
                continue                       #kicad-cli writes a report FILE, not stdout
            out.setdefault(tool, bodies[i + 1] if i + 1 < len(bodies) else "")
    return out


#the injection
class _Synth:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, rc, out=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


LAST_RUN = {}          #the rows, tool exits and sources of the latest run_gate call

#tier D: every gate tool added since the tiers above
SELF_TESTS = [
    ("fw.bdshot", ["tools/check_firmware.py", "bdshot", "--self-test"]),
    ("mech.prints", ["tools/check_mech.py", "prints", "--self-test"]),
    ("mech.balance", ["tools/check_mech.py", "balance", "--self-test"]),
    ("elec.esd", ["tools/check_circuit.py", "esd", "--self-test"]),
    ("elec.traces", ["tools/check_board.py", "traces", "--self-test"]),
    ("assy.cpl", ["tools/check_board.py", "cpl", "--self-test"]),
    ("fw.max2112", ["tools/check_soop.py", "max2112", "--self-test"]),
]


def make_gate_runner(capture, real_run):
    """Return a function that runs the gate in-process with only `fail_tool` red."""
    def run_gate(fail_tool):
        def patched(args, *a, **k):
            argv = [str(x) for x in (args if isinstance(args, (list, tuple)) else [args])]
            tool = readiness.tool_id(argv)
            if tool is None:
                return _Synth(0)               #kicad-cli: the report file is what matters
            return _Synth(1 if tool == fail_tool else 0, capture.get(tool, ""))

        subprocess.run = patched
        try:
            preflight.results.clear()
            preflight.TOOL_RESULTS.clear()
            preflight.CHECK_SOURCE.clear()
            preflight._LAST_TOOL[0] = None
            with contextlib.redirect_stdout(io.StringIO()):
                preflight.main()
        finally:
            subprocess.run = real_run
        rep = readiness.evaluate(preflight.results, dict(preflight.TOOL_RESULTS),
                                 sources=dict(preflight.CHECK_SOURCE))
        LAST_RUN.update(rows=list(preflight.results), tools=dict(preflight.TOOL_RESULTS),
                        sources=dict(preflight.CHECK_SOURCE))
        verdicts = {name: v for _, name, v, _ in preflight.results}
        return {p["id"] for p, _ in rep["blocking"]}, verdicts

    return run_gate


#tier B (inline)
#a check that reads a file cannot be moved by failing a subprocess
def _lcsc_key(rows):
    return next(k for k in rows[0] if "lcsc" in k.lower())


@contextlib.contextmanager
def _fab_file(name, mutate):
    rows = list(csv.DictReader(open(f"fab/{name}")))
    mutate(rows)
    d = tempfile.mkdtemp(prefix="faultinj_")
    with open(os.path.join(d, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    old = preflight.FAB
    preflight.FAB = d
    try:
        yield
    finally:
        preflight.FAB = old


def _cpl_all_top(rows):
    lk = next(k for k in rows[0] if "layer" in k.lower())
    for r in rows:
        r[lk] = "Top"


def _bom_wrong_value(rows):
    rows[0]["Comment"] = "NOT-THE-BOARD-VALUE"


def _bom_no_code(rows):
    rows[0][_lcsc_key(rows)] = ""


class _Pt:
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y


class _Circle:
    def __init__(self, x, y, r=2_000_000):          #a 4.0 mm hole, in board units (nm)
        self._c, self._r = _Pt(x, y), r

    def GetCenter(self):
        return self._c

    def GetRadius(self):
        return self._r

    def GetLayer(self):
        return preflight.pcbnew.Edge_Cuts

    def ShowShape(self):
        return "Circle"


class _DesignSettings:
    #nm - the units the real KiCad settings report
    m_TrackMinWidth = 50_000
    m_ViasMinSize = 450_000
    m_MinThroughDrill = 200_000


class _PlaneTrack:
    def Type(self):
        return preflight.pcbnew.PCB_TRACE_T

    def GetLayer(self):
        return 999

    def GetLength(self):
        return 1_000_000

    def GetNet(self):
        return None


@contextlib.contextmanager
def _board_proxy(**over):
    """Load the real board, then hand the group a proxy with `over` replaced."""
    real_load = preflight.pcbnew.LoadBoard
    real = real_load(preflight.BOARD)

    class _Proxy:
        def __getattr__(self, name):
            return over[name] if name in over else getattr(real, name)

    preflight.pcbnew.LoadBoard = lambda *a, **k: _Proxy()
    try:
        yield
    finally:
        preflight.pcbnew.LoadBoard = real_load


class _UnlabelledPad:
    """A test pad whose footprint carries no text at all."""
    def GetFPIDAsString(self):
        return "TestPoint:TestPoint_Pad_1.5x1.5mm"

    def GetReference(self):
        return "P41"

    def GraphicalItems(self):
        return []


@contextlib.contextmanager
def _unlabelled_pad():
    with _board_proxy(GetFootprints=lambda: [_UnlabelledPad()]):
        yield


@contextlib.contextmanager
def _no_edge_cuts():
    with _board_proxy(GetDrawings=lambda: []):
        yield


@contextlib.contextmanager
def _undersize_tracks():
    with _board_proxy(GetDesignSettings=lambda: _DesignSettings()):
        yield


@contextlib.contextmanager
def _track_on_a_plane():
    with _board_proxy(GetTracks=lambda: [_PlaneTrack()],
                      GetLayerName=lambda _li: "In1.Cu"):
        yield


@contextlib.contextmanager
def _hole_near_a_pad():
    """A mounting hole 3.0 mm from the nearest pad."""
    real_load = preflight.pcbnew.LoadBoard
    real = real_load(preflight.BOARD)
    boxes = [p.GetBoundingBox() for p in real.GetPads()]

    def nearest(x, y):
        return min(math.hypot(max(b.GetLeft() - x, 0, x - b.GetRight()),
                              max(b.GetTop() - y, 0, y - b.GetBottom())) for b in boxes)

    spot = None
    for bb in boxes:
        cx, cy = (bb.GetLeft() + bb.GetRight()) // 2, (bb.GetTop() + bb.GetBottom()) // 2
        for x, y in ((bb.GetRight() + 3_000_000, cy), (bb.GetLeft() - 3_000_000, cy),
                     (cx, bb.GetBottom() + 3_000_000), (cx, bb.GetTop() - 3_000_000)):
            if 2_600_000 < nearest(x, y) <= 3_000_000:
                spot = (x, y)
                break
        if spot:
            break
    extra = _Circle(*spot)

    class _Proxy:
        def __getattr__(self, name):
            if name == "GetDrawings":
                return lambda: list(real.GetDrawings()) + [extra]
            return getattr(real, name)

    preflight.pcbnew.LoadBoard = lambda *a, **k: _Proxy()
    try:
        yield
    finally:
        preflight.pcbnew.LoadBoard = real_load


@contextlib.contextmanager
def _hole_on_a_pad():
    """Put a mounting hole dead centre on a real pad: 0 mm of copper clearance."""
    real_load = preflight.pcbnew.LoadBoard
    real = real_load(preflight.BOARD)
    bb = next(iter(real.GetPads())).GetBoundingBox()
    extra = _Circle((bb.GetLeft() + bb.GetRight()) // 2,
                    (bb.GetTop() + bb.GetBottom()) // 2)

    class _Proxy:
        def __getattr__(self, name):
            if name == "GetDrawings":
                return lambda: list(real.GetDrawings()) + [extra]
            return getattr(real, name)

    preflight.pcbnew.LoadBoard = lambda *a, **k: _Proxy()
    try:
        yield
    finally:
        preflight.pcbnew.LoadBoard = real_load


@contextlib.contextmanager
def _cli_reports(drc="", erc=""):
    """Replace the kicad-cli reader."""
    real = preflight.cli

    def fake(args, out):
        return erc if ("erc" in args or "sch" in args) else drc

    preflight.cli = fake
    try:
        yield
    finally:
        preflight.cli = real


@contextlib.contextmanager
def _stale_gerbers():
    real = os.path.getmtime

    def fake(p):
        return 1.0 if str(p).endswith((".gbr", ".drl")) else real(p)

    os.path.getmtime = fake
    try:
        yield
    finally:
        os.path.getmtime = real


@contextlib.contextmanager
def _no_defaults():
    real = os.path.exists

    def fake(p):
        return False if str(p).endswith("defaults.parm") else real(p)

    os.path.exists = fake
    try:
        yield
    finally:
        os.path.exists = real


@contextlib.contextmanager
def _oversize_peg_sink():
    old = design.MODEL_EXPECTED_SINK.get("J8")
    design.MODEL_EXPECTED_SINK["J8"] = 2.0
    try:
        yield
    finally:
        if old is not None:
            design.MODEL_EXPECTED_SINK["J8"] = old
        else:
            design.MODEL_EXPECTED_SINK.pop("J8", None)


_ACTIVE_CAPTURE = {}


@contextlib.contextmanager
def _mounts_fail():
    real = _ACTIVE_CAPTURE.get("check_mech.py cad_fit", "")
    _ACTIVE_CAPTURE["check_mech.py cad_fit"] = real.replace("carries", "carries").replace("joint(s)  ok", "joint(s)  FAIL", 1)
    try:
        yield
    finally:
        _ACTIVE_CAPTURE["check_mech.py cad_fit"] = real


@contextlib.contextmanager
def _empty_fab():
    real = preflight.FAB
    with tempfile.TemporaryDirectory() as d:
        preflight.FAB = d
        try:
            yield
        finally:
            preflight.FAB = real


@contextlib.contextmanager
def _no_gnd_plane():
    with _board_proxy(Zones=lambda: []):
        yield


class _Net:
    def __init__(self, name):
        self.name = name

    def GetNetname(self):
        return self.name


class _CriticalOnPlane(_PlaneTrack):
    def GetNet(self):
        return _Net("M1")


@contextlib.contextmanager
def _critical_on_plane():
    with _board_proxy(GetTracks=lambda: [_CriticalOnPlane()],
                      GetLayerName=lambda _li: "In4.Cu"):
        yield


@contextlib.contextmanager
def _no_crystal():
    real_load = preflight.pcbnew.LoadBoard
    real = real_load(preflight.BOARD)
    find = real.FindFootprintByReference
    with _board_proxy(FindFootprintByReference=lambda r: None if r == "Y1" else find(r)):
        yield


@contextlib.contextmanager
def _no_silk_texts():
    with _board_proxy(GetDrawings=lambda: []):
        yield


@contextlib.contextmanager
def _no_imu():
    real = preflight.pcbnew.LoadBoard(preflight.BOARD)
    fps = [f for f in real.GetFootprints() if f.GetReference() not in ("U2", "U3")]
    with _board_proxy(GetFootprints=lambda: fps):
        yield


@contextlib.contextmanager
def _hwdef_changed():
    real = preflight.HWDEF
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "hwdef.dat")
        open(f, "w").write(open(real).read() + "\n# a line the cached build never saw\n")
        preflight.HWDEF = f
        try:
            yield
        finally:
            preflight.HWDEF = real


@contextlib.contextmanager
def _belly_low():
    real = _ACTIVE_CAPTURE.get("check_mech.py cad_fit", "")
    _ACTIVE_CAPTURE["check_mech.py cad_fit"] = re.sub(
        r"(lowest z\s+[-\d.]+\s+clearance\s+)[-\d.]+( mm)", r"\g<1>1.00\2", real, count=1)
    try:
        yield
    finally:
        _ACTIVE_CAPTURE["check_mech.py cad_fit"] = real


TIER_B = [
    dict(pid="assy.twosided", group="assembly", check="two-sided assembly",
         fault=lambda: _fab_file("CPL-NAVCORE-SoOP.csv", _cpl_all_top),
         why="a CPL whose every row says TOP is not a two-sided board"),
    dict(pid="fab.drc", group="fabrication", check="DRC errors",
         fault=lambda: _cli_reports(drc="\n[drc_violation] clearance under 0.2 mm\n"),
         why="a DRC report with a violation in it must fail the DRC check"),
    dict(pid="fab.erc", group="fabrication", check="ERC clean",
         fault=lambda: _cli_reports(
             erc="\n[erc_pin_not_driven] input pin not driven\n"),
         why="an ERC report with a violation in it must fail the ERC check"),
    dict(pid="fab.erc", group="fabrication", check="ERC clean",
         fault=lambda: _cli_reports(erc=None),
         why="a schematic kicad-cli cannot load writes no report, and must not pass as clean"),
    dict(pid="fab.drc", group="fabrication", check="DRC errors",
         fault=lambda: _cli_reports(drc=None),
         why="a board kicad-cli cannot load writes no report, and must not pass as clean"),
    dict(pid="fab.routed", group="fabrication", check="all nets routed (fitted parts)",
         fault=lambda: _cli_reports(drc="\n  @[+5V] of U8\n"),
         why="an unrouted FITTED net must fail the routing check"),
    dict(pid="fab.gerbers", group="fabrication", check="gerbers match the board",
         fault=_stale_gerbers,
         why="a gerber older than the board must be flagged as stale"),
    dict(pid="fab.outline", group="fabrication", check="board outline",
         fault=_no_edge_cuts,
         why="a board with no Edge.Cuts is not a closed contour"),
    dict(pid="fab.limits", group="fabrication", check="JLCPCB 6-layer limits",
         fault=_undersize_tracks,
         why="a 0.05 mm minimum track is under JLCPCB's free-tier floor"),
    dict(pid="mech.mounting", group="fabrication", check="mounting holes",
         fault=_no_edge_cuts,
         why="no mounting holes is not a 30.5 mm four-hole pattern"),
    dict(pid="fab.padlabels", group="silkscreen", check="pad silkscreen labels",
         fault=_unlabelled_pad,
         why="a test pad with no function printed beside it must fail the label check"),
    dict(pid="mech.screwhead", group="assembly", check="no copper under a screw head",
         fault=_hole_on_a_pad,
         why="a screw hole landing on a pad must fail the clearance check"),
    dict(pid="mech.screwhead", group="assembly", check="no copper under a screw head",
         fault=_hole_near_a_pad,
         why="a pad 3 mm from a hole is inside a metal spacer's corners and must fail"),
    dict(pid="fab.planes", group="integrity", check="planes carry no routing",
         fault=_track_on_a_plane,
         why="signal copper on In1.Cu must fail the plane check"),
    dict(pid="fab.pegdepth", group="fabrication", check="locating peg sink depth within board core",
         fault=_oversize_peg_sink,
         why="a locating peg deeper than the board thickness must fail the exemption"),
    dict(pid="assy.bom", group="assembly", check="BOM matches the board",
         fault=lambda: _fab_file("BOM-NAVCORE-SoOP.csv", _bom_wrong_value),
         why="a BOM value that differs from the board must fail"),
    dict(pid="assy.codes", group="assembly", check="every line has an LCSC code",
         fault=lambda: _fab_file("BOM-NAVCORE-SoOP.csv", _bom_no_code),
         why="a BOM line with no part number must fail"),
    dict(pid="fw.defaults", group="firmware", check="default parameters shipped",
         fault=_no_defaults,
         why="a board shipped without defaults.parm must fail"),
    dict(pid="mech.mounts", group="firmware", check="every part off the board is mounted, with screws",
         fault=_mounts_fail,
         why="a mount that fails its joints check must fail the mounts gate"),
    dict(pid="fab.gerberlayers", group="fabrication", check="gerber layers", fault=_empty_fab,
         why="an empty fab directory has no gerbers"),
    dict(pid="fab.gerberlayers", group="fabrication", check="drill file", fault=_empty_fab,
         why="an empty fab directory has no drill file"),
    dict(pid="assy.files", group="assembly", check="BOM present", fault=_empty_fab,
         why="an empty fab directory has no BOM"),
    dict(pid="si.gndplane", group="integrity", check="GND plane is solid",
         fault=_no_gnd_plane, why="no GND pour on In1 is not one solid plane"),
    dict(pid="si.critical", group="integrity", check="critical nets have a reference",
         fault=_critical_on_plane, why="a motor line routed on the In4 plane has no reference"),
    dict(pid="si.crystal", group="integrity", check="crystal near the MCU",
         fault=_no_crystal, why="a board without Y1 has no crystal near the MCU"),
    dict(pid="fab.connnames", group="silkscreen", check="connector names on the silkscreen",
         fault=_no_silk_texts, why="no printed names leaves listed connectors blank"),
    dict(pid="project.functions", group="project", check="IMU 1 (ICM-42688-P)",
         fault=_no_imu, why="a board without its IMUs has lost a function"),
    dict(pid="mech.belly", group="firmware", check="belly parts clear the ground",
         fault=_belly_low, why="a belly part 1 mm above the skid plane is inside its 5 mm need"),
    dict(pid="fw.build", group="firmware", check="ArduPilot builds for this board",
         fault=_hwdef_changed, why="an hwdef edited after the build is not what was built"),
]


def run_inline_fault(capture, group_name, fault):
    """Run ONE preflight group with `fault` applied."""
    _ACTIVE_CAPTURE.clear()
    _ACTIVE_CAPTURE.update(capture)

    def patched(args, *a, **k):
        argv = [str(x) for x in (args if isinstance(args, (list, tuple)) else [args])]
        tool = readiness.tool_id(argv)
        return _Synth(0, _ACTIVE_CAPTURE.get(tool, "") if tool else "")

    subprocess.run = patched
    preflight.results.clear()
    try:
        with fault():
            board = preflight.pcbnew.LoadBoard(preflight.BOARD)
            with contextlib.redirect_stdout(io.StringIO()):
                getattr(preflight, group_name)(board)
    finally:
        subprocess.run = _REAL_RUN
    return {name: v for _, name, v, _ in preflight.results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recapture", action="store_true",
                    help="run the gate again to refresh the captured tool output")
    ap.add_argument("--list-gaps", action="store_true",
                    help="only list gated prerequisites no injection covers")
    a = ap.parse_args()

    if a.recapture or not os.path.isdir(CAPTURE_DIR) or not os.listdir(CAPTURE_DIR):
        print(f"no capture at {CAPTURE_DIR}; running it (this takes a few minutes)...")
        sys.argv = [sys.argv[0]]                  #keep preflight.BOARD at its default
        os.chdir(REPO)
        capture_tools(CAPTURE_DIR)
        os.chdir(REPO)

    capture = parse_capture(CAPTURE_DIR)
    if not capture:
        print(f"FAIL - could not read any tool output from {CAPTURE_DIR}")
        return 1

    os.chdir(REPO)
    #pin the board path
    preflight.BOARD = "NAVCORE-SoOP.kicad_pcb"
    subprocess.run = _REAL_RUN
    run_gate = make_gate_runner(capture, _REAL_RUN)

    gated = [p for p in readiness.PREREQUISITES if p["cls"] == GATED]
    gated_tools = sorted({p["tool"] for p in gated if "tool" in p})
    #fault every captured tool, not only the ones a `tool=` entry names
    tools_to_fault = sorted(capture)

    print("=== fault injection: can every gated prerequisite fail? ===\n")
    print(f"  {len(gated)} gated prerequisite(s); {len(tools_to_fault)} tool(s) captured\n")

    missing = [t for t in gated_tools if t not in capture]
    if missing:
        print(f"FAIL - no captured output for: {', '.join(missing)}")
        return 1

    base_blocking, base_verdicts = run_gate(None)
    base_run = dict(LAST_RUN)
    print(f"  positive control: all tools green -> {len(base_blocking)} blocking "
          f"prerequisite(s)")
    if base_blocking:
        print(f"    !! baseline is not clean: {', '.join(sorted(base_blocking))}")
        print("       the in-memory capture does not reproduce the live gate, so every")
        print("       result below would be measured against the wrong baseline")

    #one gate run per tool: which prerequisites does ITS failure block?
    covers = {}
    flips = {}
    for i, tool in enumerate(tools_to_fault, 1):
        blocking, verdicts = run_gate(tool)
        flips[tool] = {k for k, v in verdicts.items()
                       if v != base_verdicts.get(k) and v != "PASS"}
        for pid in blocking - base_blocking:
            covers.setdefault(pid, []).append(tool)
        print(f"  [{i:2}/{len(tools_to_fault)}] {tool:34} -> "
              f"{len(blocking - base_blocking)} prerequisite(s), "
              f"{len(flips[tool])} check(s) flipped")

    print(f"\n=== Tier B: {len(TIER_B)} inline fault(s) ===")
    inert = []      #a fault its check shrugged off
    for t in TIER_B:
        v = run_inline_fault(capture, t["group"], t["fault"]).get(t["check"])
        if v in ("FAIL", "WARN"):
            covers.setdefault(t["pid"], []).append(f"inline:{t['group']}")
        else:
            inert.append(f"{t['pid']} ({t['fault'].__name__})")
        print(f"  {' ok ' if v in ('FAIL', 'WARN') else 'FAIL'} {t['pid']:16} "
              f"{t['check']:24} -> {v or 'check not reported'}")
        if v not in ("FAIL", "WARN"):
            print(f"        {t['why']}")

    #tier C: every check the green run reported, turned FAIL one at a time
    rows0 = base_run["rows"]
    loose = []
    for i, (g, n, v, d) in enumerate(rows0):
        if v != "PASS":
            continue
        rows = list(rows0)
        rows[i] = (g, n, "FAIL", "injected")
        rep = readiness.evaluate(rows, base_run["tools"], sources=base_run["sources"])
        ids = {p["id"] for p, _ in rep["blocking"]}
        if not ids:
            loose.append(n)
        if "gate.hardchecks" in ids:
            covers.setdefault("gate.hardchecks", []).append("tier C")
    print(f"\n=== Tier C: {sum(1 for r in rows0 if r[2] == 'PASS')} check(s) forced FAIL "
          f"one at a time ===")
    print(f"  {'ok' if not loose else 'FAIL'} - "
          + ("every one blocks the order" if not loose else
             f"{len(loose)} did not block: {', '.join(loose[:6])}"))
    if loose:
        inert += [f"tier C ({n})" for n in loose]

    #tier D: the newer gates prove themselves by breaking their own input
    if SELF_TESTS:
        print(f"\n=== Tier D: {len(SELF_TESTS)} gate self-test(s) ===")
    for pid, argv in SELF_TESTS:
        r = _REAL_RUN([sys.executable, *argv], capture_output=True, text=True, timeout=1800)
        if r.returncode == 0:
            covers.setdefault(pid, []).append("self-test")
        else:
            inert.append(f"{pid} (self-test exit {r.returncode})")
        print(f"  {' ok ' if r.returncode == 0 else 'FAIL'} {pid:16} {' '.join(argv)}")

    gaps = [p["id"] for p in gated if p["id"] not in covers]

    if a.list_gaps:
        for g in gaps:
            print(g)
        return 0

    print("\n=== coverage ===")
    print(f"  covered : {len(gated) - len(gaps)}/{len(gated)} gated prerequisite(s)")
    for p in gated:
        c = covers.get(p["id"])
        mark = "  ok " if c else " GAP "
        what = ", ".join(c) if c else "no injection covers this"
        print(f" {mark} {p['id']:22} {what}")

    if gaps:
        print(f"\nFAIL - {len(gaps)} gated prerequisite(s) cannot currently be shown to "
              f"fail:")
        for g in gaps:
            p = next(x for x in gated if x["id"] == g)
            src = p.get("check", p.get("tool"))
            print(f"    {g:22} ({src})")
        print("\n     Two causes, and they are different:")
        print("     * Tier B inline checks - they read a FILE (the board, `fab/`,")
        print("       `design.py`, a doc) rather than a tool's stdout, so a subprocess")
        print("       fault cannot move them. Each needs its own declared input fault.")
        print("     * A check with an unconditional `ok` (e.g. `check(..., True, ...)`) -")
        print("       that one cannot fail for ANY input, and is a defect, not a gap.")
        print("     The list is intentionally a failure, not a silent pass.")
        return 1

    if inert:
        print(f"\nFAIL - {len(inert)} injected fault(s) went unnoticed: {', '.join(inert)}")
        return 1

    print("\nALL GATED PREREQUISITES REACT TO A FAULT - none is a check that cannot fail.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
