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

THE AUTHORITY, AND WHY IT CHANGED. Until 2026-09-18 this check REQUIRED the community
jlcparts mirror. Upstream stopped rebuilding it, so it returned no rows for most of this
BOM and the check could only print NOT IN MIRROR - which preflight then had to treat as a
blocker, because "could not check" is not "passed". It now reads the DATED SNAPSHOT in
fab/stock-snapshot.json, which tools/check_stock.py fetches from JLCPCB's own parts API.

That is not a downgrade. The snapshot carries componentSpecificationEn - JLCPCB's own
package string, e.g. 'LQFP-100(14x14)' - for every line. For U1 the mirror's description
field was EMPTY, which is the only reason DATASHEET_PACKAGE ever needed a hand-entered
entry for the most expensive part on the board. The live string states it.

Pad count is then derived from that token by PACKAGE_PADS: a LQFP-100 IS a 100-pin
package, a SOT-23-5 IS a five-lead one. Definitional, not per-part - the same lever
FAMILY_PITCH already pulls for pitch. Tokens that state no count (the connectors' bare
'SMD') yield no comparison, and are reported as uncovered rather than assumed good.

The mirror is still used when present, because it carries a real JOINT count. The live
API does not publish one.

    python3 tools/check_footprints.py
"""
import glob, gzip, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = sys.argv[1] if len(sys.argv) > 1 else "NAVCORE-SoOP.kicad_pcb"
DATA = os.environ.get("JLC_DATA", "/tmp/nav/jlc")
SNAPSHOT = os.path.join(REPO, "fab", "stock-snapshot.json")

# Parts JLCPCB assembles but the community mirror does not carry. Not a pass - a
# redirection to the authority, the same way check_lcsc_stock.py handles it.
MIRROR_GAPS = {
    "C51940119": "J3's JST-GH 6P - jlcpcb.com/partdetail/C51940119 confirms the part; "
                 "the mirror simply lacks the row",
}


# Packages the mirror describes not at all, or too loosely to key on. Each entry is
# read from the manufacturer datasheet, with the citation, because "the mirror has no
# string for it" must not silently become "checked". U1 is the whole point of this
# table: its description field is EMPTY, and it is the most expensive part to get wrong.
DATASHEET_PACKAGE = {
    "C5271084": ("LQFP-100", 14.0, 14.0, 0.50,
                 "[D] ST DS12110 STM32H743xI: LQFP100 14x14x1.4 mm, 0.50 mm pitch"),
    "C2682774": ("SMD3225-4P", 3.2, 2.5, None,
                 "[D] YXC X322508MSB4SI: 3.2 x 2.5 mm 4-pad SMD crystal"),
    # Mirror gap, but not an unknown: jlcpcb.com/partdetail/C51940119 states
    # "JLCPCB supports PCB assembly for the XY-SM06B-GHS-TB", verified 2026-09-03.
    # Carrying the MPN here lets the part-specific matcher resolve it the same way it
    # resolves every other connector, instead of leaving the row permanently unverified.
    "C51940119": ("XY-SM06B-GHS-TB", None, None, 1.25,
                  "[L] jlcpcb.com/partdetail/C51940119, verified 2026-09-03"),
}

# Industry-standard pitches by package family. These are definitional, not per-part -
# a SOT-23 is 0.95 mm by what SOT-23 MEANS - which is exactly what makes them usable as
# an outside authority against a footprint that claims a family.
FAMILY_PITCH = {
    "SOT-23": 0.95, "SOT-25": 0.95, "SOIC": 1.27, "LQFP-100": 0.50,
    "LGA-14": 0.50, "LGA-12": 0.80, "QFN-8": 1.25, "COB-28": 0.65,
    "SOP-8": 1.27, "TQFN-28-EP": 0.50, "DSBGA-6": 0.40,
}

# Electrical pad count implied by a JLCPCB package token. Definitional, and keyed
# explicitly rather than regex-parsed on purpose: a regex over the digits in
# 'DO-214AA(SMB)' reads 214, which would fail every diode on the board. -EP adds the
# exposed pad because JLCPCB counts it as a joint - TQFN-28-EP is 28 leads + 1 pad = 29,
# which is exactly what the MAX2112's footprint has.
PACKAGE_PADS = {
    "SMD3225-4P": 4, "LQFP-100": 100, "LGA-14": 14, "LGA-12": 12, "QFN-8": 8,
    "SOIC-8": 8, "SOIC-8-208MIL": 8, "SOP-8": 8, "TQFN-28-EP": 29, "DSBGA-6": 6,
    "COB-28": 28, "SOT-23": 3, "SOT-23-3": 3, "SOT-23-3L": 3, "SOT-23-5": 5,
    "SOT-23-6": 6, "SOT-25-5": 5, "SOD-123": 2, "DO-214AA": 2, "DO-214AA(SMB)": 2,
    "0402": 2, "0603": 2, "0805": 2, "1206": 2,
}


def pads_from_spec(spec):
    """Pin count JLCPCB's package string implies, or None if it states no count.

    Tokens arrive as 'SMD3225-4P', 'LQFP-100(14x14)', 'TQFN-28-EP(5x5)' - the body dims
    in parentheses are not part of the package name, so they are stripped first. The
    bare 'SMD' and 'SMD,P=1mm,...' of the connectors deliberately resolve to None.
    """
    if not spec:
        return None
    up = spec.strip().upper()
    # Exact token first. 'DO-214AA(SMB)' is the package NAME, not a name plus body dims,
    # so stripping the parentheses - which is right for 'LQFP-100(14x14)' - would throw
    # away the half that identifies it and leave every diode on the board unverified.
    if up in PACKAGE_PADS:
        return PACKAGE_PADS[up]
    return PACKAGE_PADS.get(re.sub(r"\(.*?\)", "", up).strip())


def load_snapshot():
    """{code: (mpn, package_spec)} from the dated JLCPCB snapshot, {} if unreadable."""
    try:
        with open(SNAPSHOT) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for code, r in (d.get("lines") or {}).items():
        if r.get("found"):
            out[code] = (r.get("mpn"), r.get("spec"))
    return out


def norm(t):
    """Strip everything that is not alphanumeric, upper-cased. MPNs are written with
    different punctuation in a library name than in a manufacturer's catalogue -
    'VL53L1CXV0FY/1' vs 'VL53L1CXV0FY-1' - and the punctuation carries no meaning."""
    return re.sub(r"[^A-Z0-9]", "", (t or "").upper())


def mpn_matches(fpname, mfr):
    """Is this footprint named after the exact manufacturer part number?

    This is STRONGER evidence than a package family token, not weaker. A footprint
    called MS5611-01BA03 is by construction the land pattern for that part; a footprint
    called QFN-8 merely shares a family with it. Three parts here are named this way -
    the barometer, the ToF sensor and every connector - and reading them as family
    mismatches would have been a false alarm that a looser family rule would then have
    been 'fixed' by weakening, which is how a check stops being able to fail.
    """
    f, m = norm(fpname), norm(mfr)
    if not m or len(m) < 5:
        return False
    return m in f or f.endswith(m) or (len(m) > 8 and m[:8] in f)


def dims_agree(jl_desc, fpname):
    """SMD3225-4P and L3.2-W2.5 are the same statement in two notations."""
    m = re.search(r"SMD(\d{2})(\d{2})", (jl_desc or "").upper())
    d = re.search(r"L([\d.]+)-W([\d.]+)", fpname or "")
    if not (m and d):
        return None
    want = (int(m.group(1)) / 10.0, int(m.group(2)) / 10.0)
    got = (float(d.group(1)), float(d.group(2)))
    return abs(want[0] - got[0]) < 0.15 and abs(want[1] - got[1]) < 0.15


def family_of(text):
    """The package family token in a JLC description or a footprint name."""
    if not text:
        return None
    for fam in ("LQFP-100", "LGA-14", "LGA-12", "QFN-8", "COB-28", "SOIC-8",
                "SOT-23-6", "SOT-23-5", "SOT-25-5", "SOT-23-3", "SOT-23",
                "SMD3225-4P", "TQFN-28-EP", "TQFN-28", "SOP-8", "DSBGA-6", "SOD-123",
                "SOIC"):
        if fam in text.upper().replace("_", "-"):
            return fam
    return None


def measured_pitch(fp):
    """Smallest centre-to-centre distance between two electrical pads, in mm."""
    pos = [(p.GetPosition().x / 1e6, p.GetPosition().y / 1e6)
           for p in fp.Pads() if p.GetNumber().strip()]
    best = None
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d = ((pos[i][0] - pos[j][0]) ** 2 + (pos[i][1] - pos[j][1]) ** 2) ** 0.5
            if d > 0.01 and (best is None or d < best):
                best = d
    return best


def electrical_pads(fp):
    """Pads that take solder. Unnumbered pads are mechanical NPTH and take none."""
    return [p for p in fp.Pads() if p.GetNumber().strip()]


def main():
    has_mirror = bool(glob.glob(os.path.join(DATA, "*.jsonl.gz")))
    snap = load_snapshot()
    if not has_mirror and not snap:
        print(f"no jlcparts mirror in {DATA} and no snapshot at {SNAPSHOT} - there is no "
              f"outside authority to check against. Run `python3 tools/check_stock.py "
              f"--fetch` to rebuild the snapshot.")
        return 1
    print(f"authority: JLCPCB live snapshot {SNAPSHOT}" +
          ("  + jlcparts mirror (joint counts)" if has_mirror else ""))

    board = pcbnew.LoadBoard(BOARD)
    on_board = {fp.GetReference(): fp for fp in board.GetFootprints()}
    # KEYED BY REF, NOT BY LCSC. Keying the other way collapses every part that shares a
    # part number - U8 and U18 are both C191884, so one of them silently vanished from
    # the comparison and was reported as neither pass nor fail. Found by testing that
    # this check could fail: pointing U9 at C191884 made the total drop 47 -> 46 with
    # zero mismatches, which is the signature of a part being dropped rather than caught.
    want = {r: c[3] for r, c in design.COMPONENTS.items() if c[3] and r in on_board}
    codes = set(want.values())

    recs, descs = {}, {}
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
                                descs[c] = r[idx["description"]]
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
            # No mirror row: the live snapshot is the authority. Its package string
            # still yields a pad count for every IC, connector-free part and passive.
            sn = snap.get(lcsc)
            if sn:
                spec_pads = pads_from_spec(sn[1])
                rec = (sn[0], spec_pads)
                descs[lcsc] = sn[1] or ""
            elif lcsc in MIRROR_GAPS:
                notes.append(f"{ref} ({lcsc}): {MIRROR_GAPS[lcsc]}")
                print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                      f"{'(gap)':>5}  -- known gap, verify at jlcpcb.com/partdetail")
                continue
            else:
                notes.append(f"{ref} ({lcsc}): in neither the mirror nor the snapshot - "
                             f"check jlcpcb.com/partdetail/{lcsc} by hand")
                print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                      f"{'?':>5}  -- NO AUTHORITY")
                continue
        mfr, joints = rec
        # A token with no count in it ('SMD') compares nothing. Say so rather than
        # letting the row print as though it had been checked.
        if joints is None:
            notes.append(f"{ref} ({lcsc}): JLCPCB package string '{descs.get(lcsc)}' "
                         f"states no pin count - pad count UNVERIFIED for this part")
            print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                  f"{'--':>5}  {str(mfr)[:30]}  -- no count in package string")
            continue
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

    # ---------------------------------------------------------- package family ---
    # Pad count catches SOT-23-5 vs SOT-23-6. It does NOT catch a footprint with the
    # right number of pads at the wrong pitch, which is equally a scrapped board. The
    # family token is the lever: a part JLCPCB calls SOT-23-5 has a 0.95 mm pitch by
    # definition, so measuring the pitch tests the footprint against the standard
    # rather than against itself.
    print()
    print("=== package family and pitch ===")
    pkg_ok = 0
    for ref, lcsc in sorted(want.items()):
        fp = on_board[ref]
        if len(electrical_pads(fp)) < 3:
            continue                      # a 2-pad passive has no meaningful pitch
        fpname = fp.GetFPIDAsString().split(":")[-1]
        desc = descs.get(lcsc) or ""
        ds = DATASHEET_PACKAGE.get(lcsc)
        if not desc:
            desc = (snap.get(lcsc) or (None, ""))[1] or ""
        jl_fam = family_of(desc)
        fp_fam = family_of(fpname)
        pitch = measured_pitch(fp)
        src = "JLC"
        if ds and not jl_fam:
            jl_fam, src = ds[0], "datasheet"
        # Strongest first: is the footprint named after the exact part number?
        mfr = (recs.get(lcsc) or ("", None))[0]
        if not mfr:
            mfr = (snap.get(lcsc) or (None, ""))[0]
        if not mfr and lcsc in DATASHEET_PACKAGE:
            mfr = DATASHEET_PACKAGE[lcsc][0]
        if mpn_matches(fpname, mfr):
            pkg_ok += 1
            print(f"  {ref:5} {fpname[:38]:38} {'part-specific':11} pitch "
                  f"{pitch:.3f} mm  [named for {str(mfr)[:20]}]")
            continue
        if jl_fam and dims_agree(desc, fpname):
            pkg_ok += 1
            print(f"  {ref:5} {fpname[:38]:38} {jl_fam:11} pitch {pitch:.3f} mm  "
                  f"[body dims agree]")
            continue
        if not jl_fam:
            notes.append(f"{ref} ({lcsc}): JLCPCB publishes no package string, the "
                         f"footprint is not named for the part, and there is no "
                         f"DATASHEET_PACKAGE entry - {fpname} is UNVERIFIED")
            print(f"  {ref:5} {fpname[:38]:38} -- no outside package string")
            continue
        if fp_fam != jl_fam and not (fp_fam and jl_fam.startswith(fp_fam)) \
           and not (fp_fam and fp_fam.startswith(jl_fam)):
            fails.append(f"{ref} ({lcsc}): {src} says package '{jl_fam}', footprint is "
                         f"'{fpname}' - different package family")
            print(f"  {ref:5} {fpname[:38]:38} FAMILY MISMATCH: {src} says {jl_fam}")
            continue
        want_p = FAMILY_PITCH.get(jl_fam) or FAMILY_PITCH.get((fp_fam or "")[:6])
        if want_p and pitch and abs(pitch - want_p) > 0.03:
            # SOT-23-3 is the documented exception: its two same-side pins sit 1.90 mm
            # apart (2 x 0.95), so the SMALLEST pad gap is not the pitch.
            if not (jl_fam.startswith("SOT-23") and abs(pitch - 1.90) < 0.05):
                fails.append(f"{ref} ({lcsc}): {jl_fam} is a {want_p} mm pitch package, "
                             f"footprint measures {pitch:.3f} mm")
                print(f"  {ref:5} {fpname[:38]:38} PITCH {pitch:.3f} vs {want_p} expected")
                continue
        pkg_ok += 1
        print(f"  {ref:5} {fpname[:38]:38} {jl_fam:11} pitch {pitch:.3f} mm  [{src}]")
    print(f"  {pkg_ok} package(s) agree with an outside package string")

    print("-" * 78)
    print(f"{ok} footprint(s) agree with an outside pad count, {len(fails)} mismatch(es), "
          f"{len(notes)} needing a manual look")
    for n in notes:
        print(f"  note {n}")
    for f in fails:
        print(f"  FAIL {f}")
    print("\nWhat this now covers: pad COUNT against JLCPCB's joint count, and package "
          "FAMILY\nand PITCH against an outside string - JLC's own, the datasheet, or the "
          "part number\nthe footprint is named after.\n"
          "\nWhat it still does not cover: individual pad LAND SIZE and the paste "
          "aperture.\nA 0.50 mm-pitch part can have correct pitch and undersized pads. "
          "Two things close\nthat and both are free: JLCPCB's DFM review on upload, and "
          "printing the fab\ndrawing 1:1 on paper and sitting the real parts on it.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
