#!/usr/bin/env python3
"""Prove a gate check can FAIL, not merely that it passes.

Usage:  python3 tools/fault_injection.py [--list-gaps]

The problem this answers: a check that cannot fail is not a check. `prove_readiness.py`
proves the manifest BLOCKS when a tool is missing or exits nonzero, and
`audit_gate_patterns.py` proves each regex still matches the text a tool prints. Neither
answers the question a reader of a READY TO ORDER verdict actually has - *can every one
of these checks still go red?*

Tier A - each gated prerequisite, one tool at a time.

    Take the tool output captured by `audit_gate_patterns.py --capture-only`, stub the
    whole subprocess boundary with it so the gate sees a realistic green board, then run
    the gate once per tool with ONLY that tool's exit code forced to 1. A prerequisite is
    COVERED when it goes from not-blocking to blocking under exactly that injection.

    This is stronger than one global "a tool failed" test: a check wired to a tool it
    never reads, or to a mistyped tool name, passes that and fails this.

Tier B - the inline checks that read a file rather than a tool's stdout.

    DRC, ERC, the board outline, the planes, the BOM, the fab file ages and the rest live
    in preflight.py itself and read the board or `fab/`. Forcing a subprocess cannot move
    them; each needs a real fault in the file it reads. Until one is declared here they
    are listed as GAPS and this tool exits nonzero, so the uncovered set is explicit and
    cannot be mistaken for coverage.

No file in the tree is modified: the fault is injected in memory, into the subprocess
boundary, and the working tree stays exactly as verified.
"""
import argparse
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

# audit_gate_patterns.capture() leaves subprocess.run patched; snapshot the real one
# BEFORE it could be, so run_gate always restores the true function.
_REAL_RUN = subprocess.run

GATED = readiness.GATED
CAPTURE_DIR = os.path.join("/tmp", "nav_gate_toolout")


# ------------------------------------------------------------------ capture parsing ---
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
                continue                       # the "stderr" marker, already folded in
            argv_str, _, rc = head[len("argv="):].rpartition(" rc=")
            tool = next((os.path.basename(tok) for tok in argv_str.split()
                         if tok.endswith(".py")), None)
            if tool is None:
                continue                       # kicad-cli writes a report FILE, not stdout
            out.setdefault(tool, bodies[i + 1] if i + 1 < len(bodies) else "")
    return out


# ------------------------------------------------------------------- the injection ---
class _Synth:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, rc, out=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def make_gate_runner(capture, real_run):
    """Return a function that runs the gate in-process with only `fail_tool` red."""
    def run_gate(fail_tool):
        def patched(args, *a, **k):
            argv = [str(x) for x in (args if isinstance(args, (list, tuple)) else [args])]
            tool = next((os.path.basename(x) for x in argv if x.endswith(".py")), None)
            if tool is None:
                return _Synth(0)               # kicad-cli: the report file is what matters
            return _Synth(1 if tool == fail_tool else 0, capture.get(tool, ""))

        subprocess.run = patched
        try:
            preflight.results.clear()
            preflight.TOOL_RESULTS.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                preflight.main()
        finally:
            subprocess.run = real_run
        rep = readiness.evaluate(preflight.results, dict(preflight.TOOL_RESULTS))
        verdicts = {name: v for _, name, v, _ in preflight.results}
        return {p["id"] for p, _ in rep["blocking"]}, verdicts

    return run_gate


# ------------------------------------------------------------------- Tier B (inline) ---
# A check that reads a file cannot be moved by failing a subprocess. Each entry names
# the preflight group that produces the check and a context manager that applies a real
# fault to the file (or board object) it reads. The fault is built from the verified
# tree and written to a scratch directory, or patched in over the live object, so nothing
# under version control is touched.
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
    def __init__(self, x, y):
        self._c = _Pt(x, y)

    def GetCenter(self):
        return self._c

    def GetLayer(self):
        return preflight.pcbnew.Edge_Cuts

    def ShowShape(self):
        return "Circle"


class _DesignSettings:
    # nm - the units the real KiCad settings report. A 0.05 mm track is under JLC's
    # free-tier 0.1016 mm floor.
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
    """Replace the kicad-cli reader: DRC and ERC each see the report named for them."""
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
    dict(pid="mech.screwhead", group="assembly", check="no copper under a screw head",
         fault=_hole_on_a_pad,
         why="a screw hole landing on a pad must fail the clearance check"),
    dict(pid="fab.planes", group="integrity", check="planes carry no routing",
         fault=_track_on_a_plane,
         why="signal copper on In1.Cu must fail the plane check"),
    dict(pid="assy.bom", group="assembly", check="BOM matches the board",
         fault=lambda: _fab_file("BOM-NAVCORE-SoOP.csv", _bom_wrong_value),
         why="a BOM value that differs from the board must fail"),
    dict(pid="assy.codes", group="assembly", check="every line has an LCSC code",
         fault=lambda: _fab_file("BOM-NAVCORE-SoOP.csv", _bom_no_code),
         why="a BOM line with no part number must fail"),
    dict(pid="fw.defaults", group="firmware", check="default parameters shipped",
         fault=_no_defaults,
         why="a board shipped without defaults.parm must fail"),
]


def run_inline_fault(capture, group_name, fault):
    """Run ONE preflight group with `fault` applied; return {check name: verdict}.

    The subprocess boundary is stubbed with the captured green output, so a group like
    `firmware()` does not re-run the toolchain; only the injected fault is real.
    """
    def patched(args, *a, **k):
        argv = [str(x) for x in (args if isinstance(args, (list, tuple)) else [args])]
        tool = next((os.path.basename(x) for x in argv if x.endswith(".py")), None)
        return _Synth(0, capture.get(tool, "") if tool else "")

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
    ap.add_argument("--list-gaps", action="store_true",
                    help="only list gated prerequisites no injection covers")
    a = ap.parse_args()

    if not os.path.isdir(CAPTURE_DIR) or not os.listdir(CAPTURE_DIR):
        print(f"no capture at {CAPTURE_DIR}; running it (this takes a few minutes)...")
        import audit_gate_patterns
        sys.argv = [sys.argv[0]]                  # keep preflight.BOARD at its default
        os.chdir(REPO)
        audit_gate_patterns.capture(CAPTURE_DIR)
        os.chdir(REPO)

    capture = parse_capture(CAPTURE_DIR)
    if not capture:
        print(f"FAIL - could not read any tool output from {CAPTURE_DIR}")
        return 1

    os.chdir(REPO)
    # Pin the board path: importing preflight with argparse flags in argv would
    # otherwise let it read sys.argv[1] ("--list-gaps") as the board file.
    preflight.BOARD = "NAVCORE-SoOP.kicad_pcb"
    subprocess.run = _REAL_RUN
    run_gate = make_gate_runner(capture, _REAL_RUN)

    gated = [p for p in readiness.PREREQUISITES if p["cls"] == GATED]
    gated_tools = sorted({p["tool"] for p in gated if "tool" in p})
    # Fault EVERY captured tool, not only the ones a `tool=` entry names: the checks
    # behind a `check=` entry (SITL, the SoOP solvers, the generators) are produced by
    # tools too, and the only way to reach them is to fail their tool as well.
    tools_to_fault = sorted(capture)

    print("=== fault injection: can every gated prerequisite fail? ===\n")
    print(f"  {len(gated)} gated prerequisite(s); {len(tools_to_fault)} tool(s) captured\n")

    missing = [t for t in gated_tools if t not in capture]
    if missing:
        print(f"FAIL - no captured output for: {', '.join(missing)}")
        return 1

    base_blocking, base_verdicts = run_gate(None)
    print(f"  positive control: all tools green -> {len(base_blocking)} blocking "
          f"prerequisite(s)")
    if base_blocking:
        print(f"    !! baseline is not clean: {', '.join(sorted(base_blocking))}")
        print("       the in-memory capture does not reproduce the live gate, so every")
        print("       result below would be measured against the wrong baseline")

    # One gate run per tool: which prerequisites does ITS failure block?
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

    # Tier B: inline faults, run against the verified tree with only the read patched.
    print(f"\n=== Tier B: {len(TIER_B)} inline fault(s) ===")
    for t in TIER_B:
        v = run_inline_fault(capture, t["group"], t["fault"]).get(t["check"])
        if v in ("FAIL", "WARN"):
            covers.setdefault(t["pid"], []).append(f"inline:{t['group']}")
        print(f"  {' ok ' if v in ('FAIL', 'WARN') else 'FAIL'} {t['pid']:16} "
              f"{t['check']:24} -> {v or 'check not reported'}")
        if v not in ("FAIL", "WARN"):
            print(f"        {t['why']}")

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

    print("\nALL GATED PREREQUISITES REACT TO A FAULT - none is a check that cannot fail.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
