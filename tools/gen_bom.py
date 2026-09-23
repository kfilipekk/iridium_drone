#!/usr/bin/env python3
"""BOM and pick-and-place for JLCPCB, straight from design.py and the placed board."""
import os, re, sys, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design
import jlc_orientation

BOARD = "NAVCORE-SoOP.kicad_pcb"
OUT = "fab"

# Parts held back from an economic assembly order.
STANDARD_ONLY = {
    "U3": "ICM-42605 (C2655099) - second IMU, optional; ArduPilot flies on IMU1 alone",
}

# A footprint whose name carries LCSC's dimensional suffix came from add_jlc_part.sh and
# is already in JLCPCB's orientation.
JLC_FP = re.compile(r'_L\d|^CONN-|^SENSORS-|^OPTO-|^TF-SMD|^COB-|^USB-C-SMD|^CRYSTAL-SMD')

KICAD_FP_ROTATION = []


def cpl_rotation(fp):
    """JLCPCB rotation for a placed footprint, with both corrections and the reason."""
    rot = fp.GetOrientationDegrees()
    why = []
    if fp.GetLayerName() == "B.Cu":
        rot = (180.0 - rot) % 360.0
        why.append("bottom-side mirror")
    name = fp.GetFPID().GetLibItemName().wx_str()
    if not JLC_FP.search(name):
        for rx, off in KICAD_FP_ROTATION:
            if rx.search(name):
                rot = (rot + off) % 360.0
                why.append(f"{rx.pattern} {off:+d}")
                break
    else:
        why.append("LCSC footprint, no package offset")
    return rot % 360.0, "; ".join(why) or "as placed"


def main():
    economic = "--economic" in sys.argv
    no_fpv = "--no-fpv" in sys.argv
    if economic and no_fpv:
        print("--economic and --no-fpv are different builds; pick one")
        return 1
    suffix = "-economic" if economic else ("-nofpv" if no_fpv else "")
    vtx = set(getattr(design, "VTX_BUCK_DNP", ()))

    def is_dnp(ref, dnp):
        if no_fpv and ref in vtx:
            return True
        return bool(dnp)

    b = pcbnew.LoadBoard(BOARD)
    placed = {fp.GetReference(): fp for fp in b.GetFootprints()}

    groups = {}
    skip = getattr(design, "NOT_A_PART", set())
    for ref, (sym, fp, val, lcsc, dnp) in design.COMPONENTS.items():
        # Bare copper pads and test points are board features, not parts to buy.
        if not fp or ref not in placed or ref in skip: continue
        key = (val, lcsc, fp.split(":")[-1],
               is_dnp(ref, dnp) or (economic and ref in STANDARD_ONLY))
        groups.setdefault(key, []).append(ref)

    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/BOM-NAVCORE-SoOP{suffix}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC", "Qty", "DNP"])
        for (val, lcsc, fpn, dnp), refs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            w.writerow([val, ",".join(sorted(refs)), fpn, lcsc, len(refs),
                        "DNP" if dnp else ""])

    n_cpl = n_fit = 0
    jlc_db = jlc_orientation.load()
    with open(f"{OUT}/CPL-NAVCORE-SoOP{suffix}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for ref, fp in sorted(placed.items()):
            if ref in skip: continue      # nothing to pick and place
            if economic and ref in STANDARD_ONLY: continue
            # A DNP part is not placed.
            _c = design.COMPONENTS.get(ref)
            if _c and is_dnp(ref, _c[4]): continue
            p = fp.GetPosition()
            x, y, rot = pcbnew.ToMM(p.x), -pcbnew.ToMM(p.y), cpl_rotation(fp)[0]
            fit = (jlc_orientation.solve(fp, jlc_db[_c[3]])
                   if _c and _c[3] in jlc_db else None)
            if fit:
                rot, (x, y) = round(fit[0]) % 360, fit[1]
                n_fit += 1
            w.writerow([ref, f"{x:.4f}mm", f"{y:.4f}mm",
                        "bottom" if fp.GetLayerName() == "B.Cu" else "top",
                        f"{rot:.1f}"])
            n_cpl += 1

    n_lines = len(groups)
    n_parts = sum(len(r) for r in groups.values())
    n_dnp = sum(len(r) for (v, l, fpn, d), r in groups.items() if d)
    no_lcsc = [v for (v, l, fpn, d), r in groups.items()
               if not l or str(l).startswith("LOOKUP:")]
    print(f"BOM: {n_lines} lines, {n_parts} parts ({n_dnp} DNP)")
    # Count the rows actually written, not the footprints that are not test pads.
    print(f"CPL: {n_cpl} placements, {n_fit} placed from JLCPCB's own footprint "
          f"(tools/jlc_orientation.py), {n_cpl - n_fit} from the footprint rules")
    if no_fpv:
        print(f"NO-FPV variant - the 9 V VTX buck is left off ({len(vtx)} parts):")
        print(f"   {', '.join(sorted(vtx))}")
        import filecmp
        for kind in ("BOM", "CPL"):
            a = os.path.join(OUT, f"{kind}-NAVCORE-SoOP.csv")
            bfile = os.path.join(OUT, f"{kind}-NAVCORE-SoOP-nofpv.csv")
            if os.path.exists(a) and os.path.exists(bfile) and filecmp.cmp(a, bfile,
                                                                          shallow=False):
                print(f"   note {kind} is IDENTICAL to the main {kind} - the 9 V block "
                      f"is DNP already, so this variant changes nothing today")
    if economic:
        print("ECONOMIC variant - these are left off for hand-fitting:")
        for r, why in sorted(STANDARD_ONLY.items()):
            print(f"   {r:4} {why}")
    pend = [v for (v, l, fpn, d), r in groups.items()
            if str(l).startswith("LOOKUP:")]
    print(f"lines without an LCSC code: {len(no_lcsc)}"
          + (f"  ({len(pend)} awaiting an lcsc.com lookup by MPN)" if pend else ""))
    for v in sorted(no_lcsc):
        print(f"   {v}")


if __name__ == "__main__":
    main()
