#!/usr/bin/env python3
"""
A retired figure may not appear in a live document unless the text says it is retired.

THE DEFECT THIS EXISTS TO CLOSE. Five separate defects found on 2026-09-19 were the same
shape: a document stated something that HAD BEEN TRUE and had silently stopped being true,
in a file a person acts on.

  * `BATT_AMP_PERVLT` "ships at 52.7" in four documents. The firmware had been corrected to
    25.0, so an operator following T3.5 would have "fixed" a correct value into a 2x wrong one.
  * `U6`/`U7` described as "on the board but DNP" when the Rev B re-layout had DELETED them,
    and a costed order priced a hand-fit route around two parts with no pads.
  * `fab/README.md` - the README of the folder you order from - still said "NOT READY TO
    ORDER, 64% routed" about a 4-layer board, two revisions stale.
  * `J3`'s "6.0 mm nominal", a retired JST-GH class figure, quoted as the live requirement in
    six documents and ten places. Three copies were still stale AFTER the first correction
    pass, because fixing one fact meant editing ten sites.
  * `89.2 C/W` cited to SLVSD26 in three documents. SLVSD26 does not contain it - section 5.4
    gives 118.6 (JEDEC) and 57.2 (EVM) - so the docs asserted a datasheet figure that is not
    in the datasheet, which is the worst kind because it is quotable.

Every one of those was found by a person reading carefully, which is not a mechanism. Nothing
in this repository could catch them, because they are prose.

HOW IT WORKS. Each entry is a retired VALUE, why it retired, and what to write instead. A hit
is a problem unless a retirement marker appears within WINDOW lines of it - so "it was 52.7
until 2026-09-19" passes, and "it ships at 52.7" fails. The grace is deliberately visible:
`--explain` prints which marker excused each hit, so an entry cannot be quietly neutered by
widening the marker list.

WHAT IT DELIBERATELY DOES NOT DO. It cannot tell whether a number is CORRECT, only whether it
is a number this project has already retired. That is a much smaller claim, and it is the one
the failures above actually needed.

Usage:  python3 tools/check_doc_figures.py [--explain]
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
os.chdir(REPO)

# Only live, actionable prose. `docs/HISTORY.md` is exempt because it is a record of what was
# believed at the time - but see the marker rule below: even there, a retired value has to be
# marked as one, and it usually is, because history prose says "was" and "corrected".
EXEMPT = ("docs/HISTORY.md",)
SCAN = ["README.md", "docs/*.md", "fab/*.md", "tools/README.md"]

# (pattern, what it was, what to write instead)
RETIRED = [
    (r"\b52\.7\b", "the BATT_AMP_PERVLT value from a different SpeedyBee stack",
     "the firmware ships 25.0 - 1000 / the ESC's 40 mV/A, and check_build.py verifies it"),
    (r"\b89\.2\b", "a theta_JA that is NOT in SLVSD26",
     "SLVSD26 5.4 gives 118.6 C/W (JEDEC) and 57.2 C/W (EVM); publish them as a bracket"),
    (r"\b48/48\b", "the LCSC code count when the community mirror still worked",
     "56/56 codes resolve, via JLCPCB's live API (tools/check_stock.py)"),
    (r"NAVCORE-SoOP-fpv\b", "a BOM/CPL variant name retired two revisions ago",
     "the no-video variant is -nofpv, and today it is byte-identical to the default"),
    (r"\b64% routed\b", "the stale routing figure from before the board was finished",
     "the board is fully routed; check_traces.py and DRC both pass"),
    (r"6\.0\s?mm\s?\"?\s?nominal|nominal\s?6\.0\s?mm|allowance (is|of) 6\.0\s?mm",
     "J3's retired JST-GH class clearance",
     "the derived requirement is 3.6 mm (design.MATING_CLEARANCE['J3']); 5.30 mm clears it"),
    (r"\beighteen\b.*\bpart", "a part count from before the Rev B re-layout", "count it"),
]

# A retirement marker is a word that says the reader should NOT act on this value.
MARKERS = (
    "retired", "no longer", "used to", "previously", "superseded", "corrected", "stale",
    "deprecated", "obsolete", "instead of", "until", "came from", "was wrong", "wrong",
    "earlier", "old ", "history", "not in ", "does not contain", "no longer exists",
    "not stocked", "two revisions", "originally",
)
WINDOW = 3

explain = "--explain" in sys.argv

files = []
for pat in SCAN:
    files.extend(sorted(glob.glob(pat)))
files = [f for f in files if os.path.isfile(f)]
files = [f for f in files if f not in EXEMPT]

problems, excused, hits = [], [], 0
for path in files:
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    for i, line in enumerate(lines):
        for rx, what, instead in RETIRED:
            if not re.search(rx, line, re.I):
                continue
            hits += 1
            lo, hi = max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)
            near = " ".join(lines[lo:hi]).lower()
            mark = next((m for m in MARKERS if m in near), None)
            if mark:
                excused.append((path, i + 1, what, mark))
                continue
            problems.append((path, i + 1, line.strip()[:110], what, instead))

print("=== retired figures in live prose ===")
print(f"      scanned {len(files)} file(s), {hits} mention(s) of {len(RETIRED)} retired value(s)")

if explain:
    for path, ln, what, mark in excused:
        print(f"      excused {path}:{ln}  ({what}) because it says \"{mark}\"")

for path, ln, text, what, instead in problems:
    print(f"  FAIL  {path}:{ln}")
    print(f"        {text}")
    print(f"        {what} is retired: {instead}")

if problems:
    print(f"\nFAIL - {len(problems)} retired figure(s) presented as current")
    print("     Either write the current value, or say the old one is retired - this check")
    print("     only asks that a reader can tell which they are looking at.")
    sys.exit(1)

print(f"      {len(excused)} mention(s) are marked as retired and pass")
print("\nno retired figure is presented as current")
