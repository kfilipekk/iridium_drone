#!/usr/bin/env python3
"""A retired figure may not appear in a live document unless the text says it is retired.

Usage:  python3 tools/check_doc_figures.py [--explain]
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
os.chdir(REPO)

# Only live, actionable prose.
EXEMPT = ("docs/HISTORY.md",)
SCAN = ["README.md", "docs/*.md", "docs/*.tex", "fab/*.md", "tools/README.md", "docs/PARTS.csv"]

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
    (r"22\.3\s?mm against 25\s?mm|2\.7\s?mm spare", "the Mark4-era stack clearance",
     "check_mechanical.py: 30.3 mm stack against the top plate at 32.5 mm - 2.2 mm spare, "
     "on the kit's 22 mm front standoffs"),
    (r"30\s?mm standoffs for the top plate", "a top-plate standoff the frame does not use over the stack",
     "the top plate rides on the kit's 22 mm FRONT standoffs over the stack (30 mm at the rear)"),
    (r"27k\s?/\s?5k1|47k\s?/\s?4k7", "the TPS54331-era feedback dividers (0.8 V reference)",
     "the TPS54202 references 0.596 V: +5V is 37k4/5k1 -> 4.97 V, +9V is 100k/6k8 -> 9.36 V (DNP)"),
    (r"\b9\.03\s?V\b", "the +9V setpoint before the divider was re-derived", "9.36 V, and the rail is DNP"),
    (r"10\.2\s?mm needed", "the FC-to-ESC joint before the stack bolt was derived end to end",
     "fasteners.py: the 30.5 mm stack bolt needs 27.3 mm -> M3x30, with a 12 mm F-F spacer"),
    (r"\b43 (of 43 )?gated\b|all 43 gated", "a gate count from one commit ago", "read it off preflight.py; do not type it"),
    (r"\bJ10\b", "a servo connector that was dropped in the Rev B re-layout",
     "the servo lands on TP3/TP4 (PWM5/6) with VSERVO on TP22"),
    (r"70\s?[-–]{1,2}\s?139|\b139\s?(°\s?C|C\b|\\degC)|\b0\.947\s?A|\b947\s?mA|\b653\s?mA",
     "U8's junction bracket and the +5 V budget it was computed from (0.947 A, 653 mA headroom)",
     "design.LOADS_5V derives 0.737 A; check_thermal.py gives 63-117 C; headroom 863 mA - "
     "the old figures counted 281 mA of deleted parts and missed U10"),
    # Revision C: figures the Rev C work left behind or introduced.
    (r"46\.1\s?(mm|\$|x|×)|x\s?46\.1|\\times\s?46\.1|45\.1\s?[x×]\s?46", "the Rev B board outline",
     "Revision C is 45.1 x 47.3 mm (Edge.Cuts bounding box; check_design prints it)"),
    (r"\b14 (DNP|designators|refs)\b", "the Rev B DNP count", "Revision C fits everything but R15, the CAN terminator"),
    (r"3S\s?[–-]{1,2}\s?6S|\b26\.1\s?V", "a 6S input rating the input TVS cannot protect",
     "the board is 5S max: the SMBJ22A stands off 22 V and clamps at 35.5 V under the bucks' 38 V"),
    (r"TPS54332", "a buck part this board never used", "both bucks are LMR33630 (design.BUCK_THERMAL)"),
    (r"JST-SH 8P Gimbal|8-pin Actuator|J17\.6[`)]* \(`?\+5V", "the 8-pin J17 pinout with +5 V on pin 6",
     "J17 is a 6-pin JST-SH: pin 5 +5V_PAYLOAD, pin 6 GND"),
    (r"5V\s?/\s?(2\.5|3)A payload|3A continuous|5V / 3A Payload", "the payload buck's IC rating quoted as the rail's",
     "L5 limits +5V_PAYLOAD to 1.6 A continuous"),
    (r"bootloader over SWD|no bootloader will not enumerate", "a first-flash procedure that is wrong for an H743",
     "hold BOOT (SW1) through RESET and the ROM DFU enumerates as 0483:df11 with no bootloader; SWD is the fallback"),
]

# A retirement marker is a word that says the reader should not act on this value.
MARKERS = (
    "retired", "no longer", "used to", "previously", "superseded", "corrected", "stale",
    "deprecated", "obsolete", "instead of", "until", "came from", "was wrong", "wrong",
    "earlier", "old ", "history", "not in ", "does not contain", "no longer exists",
    "not stocked", "two revisions", "originally",
    "this said", "dropped",
)
WINDOW = 3

CLAUSE_BREAK = re.compile(r"(?<=[.;!?])\s|\u2014|\u2013|--")


def retirement_marker(text, rx, anchor):
    """The retirement marker that excuses the first match of `rx` at or after `anchor`."""
    m = next((q for q in re.finditer(rx, text, re.I) if q.start() >= anchor), None)
    if not m:
        return None
    breaks = list(CLAUSE_BREAK.finditer(text))
    before = [q for q in breaks if q.end() <= m.start()]
    after = [q for q in breaks if q.start() >= m.end()]
    start = before[-1].end() if before else 0
    end = after[0].start() if after else len(text)
    candidates = [text[start:end]]
    if len(before) >= 2:
        candidates.append(text[before[-2].end():start].lstrip(" *_>#:-\t"))
    elif start == 0:
        candidates.append(text[:start])
    else:
        candidates.append("")
    if len(after) >= 2:
        candidates.append(text[end:after[1].start()].lstrip(" *_>#:-\t"))
    else:
        candidates.append(text[end:].lstrip(" *_>#:-\t"))
    # The figure's own clause: any marker. Its neighbours: only a marker that opens the clause.
    for mk in MARKERS:
        if mk in candidates[0]:
            return mk
    for mk in MARKERS:
        if candidates[1].startswith(mk) or candidates[2].startswith(mk):
            return mk
    return None

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
            anchor = len(" ".join(lines[lo:i])) + (1 if i > lo else 0)
            mark = retirement_marker(near, rx, anchor)
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
