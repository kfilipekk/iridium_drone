#!/usr/bin/env python3
#BOM and pick-and-place for JLCPCB, straight from design.py and the placed board
import os, re, sys, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design
import jlc_orientation

BOARD = "NAVCORE-SoOP.kicad_pcb"
OUT = "fab"

#parts held back from an economic assembly order
STANDARD_ONLY = {
    "U3": "ICM-42605 (C2655099) - second IMU, optional; ArduPilot flies on IMU1 alone",
}

#a footprint whose name carries LCSC's dimensional suffix came from add_jlc_part.sh
JLC_FP = re.compile(r'_L\d|^CONN-|^SENSORS-|^OPTO-|^TF-SMD|^COB-|^USB-C-SMD|^CRYSTAL-SMD')

KICAD_FP_ROTATION = []


#JLCPCB rotation for a placed footprint
def cpl_rotation(fp):
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
    suffix = "-economic" if economic else ""

    def is_dnp(ref, dnp):
        return bool(dnp)

    b = pcbnew.LoadBoard(BOARD)
    placed = {fp.GetReference(): fp for fp in b.GetFootprints()}

    groups = {}
    skip = getattr(design, "NOT_A_PART", set())
    for ref, (sym, fp, val, lcsc, dnp) in design.COMPONENTS.items():
        #bare copper pads and test points are board features, not parts to buy
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
            if ref in skip: continue      #nothing to pick and place
            if economic and ref in STANDARD_ONLY: continue
            #a DNP part is not placed
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
    #count the rows actually written
    print(f"CPL: {n_cpl} placements, {n_fit} placed from JLCPCB's own footprint "
          f"(tools/jlc_orientation.py), {n_cpl - n_fit} from the footprint rules")
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
