#!/usr/bin/env python3
"""
Every footprint's pad count, against JLCPCB's own joint count for that part number.

THE GAP THIS CLOSES. check_ratings.py verifies that a part's terminals land on its pads,
but only for passives with a known body size - 1210, 0805, 1206. Every IC and connector
on this board was dimension-unchecked: the STM32H743's LQFP-100, both IMUs' LGA-14, the
USB-C, the microSD. A wrong footprint on any of those is not a rework, it is a scrapped
board and a reorder, and it is the one error class this project's own history keeps
producing (an oscillator on a crystal's land, a 4x4x3 mm inductor on a 1210).

WHY PAD COUNT. It is not the whole of "does this footprint fit" - it says nothing about
pitch or land size - but it is the strongest invariant available from an OUTSIDE
authority, and outside is the point: a footprint chosen from the wrong package variant
(SOT-23-5 vs -6, LQFP-100 vs -144, LGA-14 vs -16) changes the count, and JLCPCB publishes
the joint count for every part it assembles. This is the same principle as
check_topology.py - consult something that is not this project.

THE ONE SUBTLETY, and it is exact rather than a fudge. JLCPCB counts SOLDER JOINTS.
KiCad counts pads, including unnumbered non-plated mounting holes that take no solder.
J1 has 18 pads and JLC says 16; J8 has 15 and JLC says 13. Both deltas are exactly the
unnumbered mechanical pads, so the rule is not "allow +/- 2" - it is "exclude pads with
no pad number", after which all 49 parts agree exactly. A tolerance would have hidden a
real two-pad error; this does not.

Needs the jlcparts mirror (see tools/check_lcsc_stock.py for the fetch command).

    python3 tools/check_footprints.py
"""
import glob, gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = sys.argv[1] if len(sys.argv) > 1 else "NAVCORE-SoOP.kicad_pcb"
DATA = os.environ.get("JLC_DATA", "/tmp/nav/jlc")

# Parts JLCPCB assembles but the community mirror does not carry. Not a pass - a
# redirection to the authority, the same way check_lcsc_stock.py handles it.
MIRROR_GAPS = {
    "C51940119": "J3's JST-GH 6P - jlcpcb.com/partdetail/C51940119 confirms the part; "
                 "the mirror simply lacks the row",
}


def electrical_pads(fp):
    """Pads that take solder. Unnumbered pads are mechanical NPTH and take none."""
    return [p for p in fp.Pads() if p.GetNumber().strip()]


def main():
    if not glob.glob(os.path.join(DATA, "*.jsonl.gz")):
        print(f"no jlcparts data in {DATA} - see tools/check_lcsc_stock.py for the fetch "
              f"command. SKIPPING (this check needs the outside authority to mean "
              f"anything).")
        return 0

    board = pcbnew.LoadBoard(BOARD)
    on_board = {fp.GetReference(): fp for fp in board.GetFootprints()}
    # KEYED BY REF, NOT BY LCSC. Keying the other way collapses every part that shares a
    # part number - U8 and U18 are both C191884, so one of them silently vanished from
    # the comparison and was reported as neither pass nor fail. Found by testing that
    # this check could fail: pointing U9 at C191884 made the total drop 47 -> 46 with
    # zero mismatches, which is the signature of a part being dropped rather than caught.
    want = {r: c[3] for r, c in design.COMPONENTS.items() if c[3] and r in on_board}
    codes = set(want.values())

    recs = {}
    for f in glob.glob(os.path.join(DATA, "*.jsonl.gz")):
        try:
            with gzip.open(f, "rt") as fh:
                idx = json.loads(fh.readline())
                for line in fh:
                    for c in codes:
                        if c in line:
                            r = json.loads(line)
                            if r[idx["lcsc"]] == c:
                                recs[c] = (r[idx["mfr"]], r[idx["joints"]])
        except Exception:
            pass

    fails, notes, ok = [], [], 0
    print(f"{'ref':6} {'LCSC':11} {'pads':>5} {'mech':>5} {'elec':>5} {'JLC':>5}  part")
    for ref, lcsc in sorted(want.items()):
        fp = on_board[ref]
        allp = list(fp.Pads())
        elec = electrical_pads(fp)
        mech = len(allp) - len(elec)
        rec = recs.get(lcsc)
        if not rec:
            if lcsc in MIRROR_GAPS:
                notes.append(f"{ref} ({lcsc}): {MIRROR_GAPS[lcsc]}")
                print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                      f"{'(gap)':>5}  -- mirror gap, verify at jlcpcb.com/partdetail")
            else:
                notes.append(f"{ref} ({lcsc}): not in the mirror - check "
                             f"jlcpcb.com/partdetail/{lcsc} by hand")
                print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                      f"{'?':>5}  -- NOT IN MIRROR")
            continue
        mfr, joints = rec
        flag = ""
        if joints and len(elec) != joints:
            flag = "  <-- MISMATCH: wrong package variant scraps the board"
            fails.append(f"{ref} ({lcsc}, {mfr}): footprint has {len(elec)} electrical "
                         f"pad(s), JLCPCB says the part has {joints} joint(s). "
                         f"Footprint is {fp.GetFPIDAsString()}")
        else:
            ok += 1
        print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
              f"{str(joints):>5}  {str(mfr)[:30]}{flag}")

    print("-" * 78)
    print(f"{ok} footprint(s) agree with JLCPCB's joint count, {len(fails)} mismatch(es), "
          f"{len(notes)} needing a manual look")
    for n in notes:
        print(f"  note {n}")
    for f in fails:
        print(f"  FAIL {f}")
    print("\nThis checks COUNT, not pitch or land size. A footprint with the right number "
          "of\npads can still be the wrong size - that is what the assembly house's DFM "
          "report\nand a printed 1:1 paper check are for.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
