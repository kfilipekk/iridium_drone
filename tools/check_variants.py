#!/usr/bin/env python3
"""Every BOM/CPL variant describes THIS board, or it does not ship.

THE DEFECT THIS EXISTS TO CLOSE. `fab/` carries three BOM/CPL pairs - the default, an
Economic tier and a no-FPV build - and `fab/ORDER.md` recommends the Economic pair at the
checkout. Nothing compared the variants to the board. preflight's "BOM matches the board"
check reads `fab/BOM-NAVCORE-SoOP.csv`; `check_order_bundle.py` proves the bundle is
byte-identical to `fab/` - and both copies were equally stale, so the comparison agreed
with itself.

MEASURED 2026-09-19, that was not theoretical. Both variants were three days older than the
default pair and described a different board:

  * the Economic BOM still carried `Y2`'s OLD code, C22381771 - the part check_stock.py
    found at 1 unit in stock with no restock date, which is the whole reason Y2 changed
  * its CPL placed neither `U19` (the temperature sensor the design had gained) nor the
    tuner's decoupling, and had `R36` 38 mm from where the board now puts it
  * the no-FPV pair differed from the default while claiming to omit only a block that is
    already DNP

Ordering the Economic variant - which the ordering document recommends - would have bought
the unbuyable part. The root cause is fixed (`make_order_bundle.sh` now regenerates all
three pairs instead of copying whatever is on disk), and this is the check that makes the
fix stick.

WHAT IT ASSERTS, per variant:
  1. CODE      every designator's LCSC code equals the one design.py states for that part.
  2. SIDES     the CPL is a subset of the default CPL with identical X, Y, side and
               rotation - a variant omits parts, it never moves them.
  3. DNP       no designator the BOM marks DNP appears in the CPL, and every DNP line's
               LCSC code still resolves (a DNP part still has to be a part that exists).
  4. HEADER    the columns are the ones JLCPCB reads.

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

    # 4. HEADER - a renamed column silently drops the DNP flag.
    for got, want, kind in ((list(bom[0]), BOM_COLS, "BOM"), (list(cpl[0]), CPL_COLS, "CPL")):
        if got != want:
            problems.append(f"{label}: {kind} header is {got}, expected {want}")

    cpl_refs = {r["Designator"] for r in cpl}
    bom_refs = {}
    for r in bom:
        dnp = bool(r.get("DNP", "").strip())
        for ref in split(r["Designator"]):
            bom_refs[ref] = dnp
            # 1. CODE
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

    # 2. SIDES - a variant may drop a part, never move one
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
