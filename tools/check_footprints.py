#!/usr/bin/env python3
"""Every footprint's pad count, against JLCPCB's own joint count for that part number."""
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


# Packages the mirror describes not at all, or too loosely to key on.
DATASHEET_PACKAGE = {
    "C5271084": ("LQFP-100", 14.0, 14.0, 0.50,
                 "[D] ST DS12110 STM32H743xI: LQFP100 14x14x1.4 mm, 0.50 mm pitch"),
    "C2682774": ("SMD3225-4P", 3.2, 2.5, None,
                 "[D] YXC X322508MSB4SI: 3.2 x 2.5 mm 4-pad SMD crystal"),
    "C51940119": ("XY-SM06B-GHS-TB", None, None, 1.25,
                  "[L] jlcpcb.com/partdetail/C51940119, verified 2026-09-03"),
}

# Industry-standard pitches by package family.
FAMILY_PITCH = {
    "SOT-23": 0.95, "SOT-25": 0.95, "SOIC": 1.27, "LQFP-100": 0.50,
    "LGA-14": 0.50, "LGA-12": 0.80, "QFN-8": 1.25, "COB-28": 0.65,
    "SOP-8": 1.27, "TQFN-28-EP": 0.50, "DSBGA-6": 0.40,
}

# Electrical pad count implied by a JLCPCB package token.
PACKAGE_PADS = {
    "SMD3225-4P": 4, "LQFP-100": 100, "LGA-14": 14, "LGA-12": 12, "QFN-8": 8,
    "SOIC-8": 8, "SOIC-8-208MIL": 8, "SOP-8": 8, "TQFN-28-EP": 29, "DSBGA-6": 6,
    "COB-28": 28, "SOT-23": 3, "SOT-23-3": 3, "SOT-23-3L": 3, "SOT-23-5": 5,
    "SOT-23-6": 6, "SOT-25-5": 5, "SOD-123": 2, "DO-214AA": 2, "DO-214AA(SMB)": 2,
    "0402": 2, "0603": 2, "0805": 2, "1206": 2,
}


def pads_from_spec(spec):
    """Pin count JLCPCB's package string implies, or None if it states no count."""
    if not spec:
        return None
    up = spec.strip().upper()
    # Exact token first.
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
    'VL53L1CXV0FY/1' vs 'VL53L1CXV0FY-1' - and the punctuation carries no meaning.
    """
    return re.sub(r"[^A-Z0-9]", "", (t or "").upper())


def mpn_matches(fpname, mfr):
    """Is this footprint named after the exact manufacturer part number?"""
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
    # Keyed by REF, not by LCSC.
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
        # A token with no count in it ('SMD') compares nothing.
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
    # Pad count catches SOT-23-5 vs SOT-23-6.
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
            # apart (2 x 0.95), so the smallest pad gap is not the pitch.
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
