#!/usr/bin/env python3
"""Every BOM/CPL variant describes this board, or it does not ship.

Usage: python3 tools/check_variants.py
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
os.chdir(REPO)
sys.path.insert(0, HERE)
import pcbnew, design  # noqa: E402

BOARD = "NAVCORE-SoOP.kicad_pcb"
FAB = "fab"
DEFAULT = f"{FAB}/BOM-NAVCORE-SoOP.csv"
VARIANTS = ("", "-economic", "-nofpv")
BOM_COLS = ["Comment", "Designator", "Footprint", "LCSC", "Qty", "DNP"]
CPL_COLS = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]

problems = []


def read(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def split(refs):
    return [r.strip() for r in refs.split(",") if r.strip()]


# ---------------------------------------------------------------- the board itself ---
board = pcbnew.LoadBoard(BOARD)
placed = {fp.GetReference(): fp for fp in board.GetFootprints()}
design_by_ref = design.COMPONENTS
skip = getattr(design, "NOT_A_PART", set())

# The design's own truth for each ref: LCSC code, and whether it is fitted.
want_code, want_dnp = {}, {}
for ref, (_sym, _fp, _val, lcsc, dnp) in design_by_ref.items():
    if ref in skip or not _fp:
        continue
    want_code[ref] = lcsc
    want_dnp[ref] = bool(dnp)

# The default pair is the reference the variants are subsets of.
base_cpl = {r["Designator"]: r for r in read(f"{FAB}/CPL-NAVCORE-SoOP.csv")}

n_checked = 0
for suf in VARIANTS:
    bom_p = f"{FAB}/BOM-NAVCORE-SoOP{suf}.csv"
    cpl_p = f"{FAB}/CPL-NAVCORE-SoOP{suf}.csv"
    label = suf.lstrip("-") or "default"
    for p in (bom_p, cpl_p):
        if not os.path.exists(p):
            problems.append(f"{label}: {p} is missing")
    if problems and not os.path.exists(bom_p):
        continue
    if not (os.path.exists(bom_p) and os.path.exists(cpl_p)):
        continue

    bom, cpl = read(bom_p), read(cpl_p)

    for got, want, kind in ((list(bom[0]), BOM_COLS, "BOM"), (list(cpl[0]), CPL_COLS, "CPL")):
        if got != want:
            problems.append(f"{label}: {kind} header is {got}, expected {want}")

    cpl_refs = {r["Designator"] for r in cpl}
    bom_refs = {}
    for r in bom:
        dnp = bool(r.get("DNP", "").strip())
        for ref in split(r["Designator"]):
            bom_refs[ref] = dnp
            # 1. code
            if ref in want_code and str(r["LCSC"]).strip() != str(want_code[ref]).strip():
                problems.append(
                    f"{label}: {ref} carries LCSC {r['LCSC']}, design says {want_code[ref]}")
            if ref not in want_code and not ref.startswith("PV"):
                problems.append(f"{label}: {ref} is in the BOM but not in the design")
        # 3. DNP still names a real part
        if dnp and str(r["LCSC"]).strip().startswith("LOOKUP:"):
            problems.append(f"{label}: DNP line '{r['Designator']}' has no real LCSC code")

    # 3. a DNP part must not be placed
    for ref in sorted(cpl_refs):
        if bom_refs.get(ref):
            problems.append(f"{label}: {ref} is marked DNP but the CPL places it")
    # fitted parts must appear in the CPL
    for ref, dnp in sorted(bom_refs.items()):
        if not dnp and ref not in cpl_refs:
            problems.append(f"{label}: {ref} is fitted in the BOM but missing from the CPL")

    # 2. sides - a variant may drop a part, never move one
    for r in cpl:
        ref = r["Designator"]
        b = base_cpl.get(ref)
        if b is None:
            problems.append(f"{label}: {ref} is placed but absent from the default CPL")
            continue
        if (r["Mid X"], r["Mid Y"], r["Layer"], r["Rotation"]) != \
           (b["Mid X"], b["Mid Y"], b["Layer"], b["Rotation"]):
            problems.append(
                f"{label}: {ref} sits at {r['Mid X']},{r['Mid Y']} {r['Rotation']} but the "
                f"board's CPL puts it at {b['Mid X']},{b['Mid Y']} {b['Rotation']} "
                f"- a variant omits parts, it does not move them")

    n_checked += 1
    print(f"  {label:9} BOM {len(bom):3} lines / CPL {len(cpl):3} placements")

print(f"\n{n_checked} variant pair(s) checked against the board")
if problems:
    print(f"\nFAIL - {len(problems)} problem(s):")
    for p in problems[:40]:
        print(f"   - {p}")
    if len(problems) > 40:
        print(f"   ... and {len(problems) - 40} more")
    sys.exit(1)
print("every variant matches the board and the design")
