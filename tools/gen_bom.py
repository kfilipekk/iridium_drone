#!/usr/bin/env python3
"""
BOM and pick-and-place for JLCPCB, straight from design.py and the placed board.

BOM is grouped by part so the LCSC codes can be pasted into JLCPCB's parts tool.
CPL carries real placed coordinates, rotations and sides from the .kicad_pcb.

ROTATION IS NOT KiCad's ORIENTATION. Two corrections stand between them, and this file
used to apply neither - it wrote fp.GetOrientationDegrees() straight out, which was wrong
for all 82 bottom-side parts on this board including both IMUs and every sensor.

1. Bottom-side coordinate system. KiCad flips a footprint about its local Y axis;
   JLCPCB rotates it about X. The board proves it: Q1 (top, 0 deg) and Q3 (bottom,
   180 deg) are the same AO3400A footprint and their pin-1 offsets are (+1.00,+0.95) and
   (-1.00,+0.95) - MIRRORED, not rotated. Q3's true bottom-view rotation is 0. The fix is
   (180 - rotation) % 360 for back-side parts.

2. Per-package library orientation. JLCPCB holds each part in its own canonical
   orientation, which need not match the footprint's. The community table (JLCKicadTools'
   cpl_rotations_db.csv) corrects for this - but it is calibrated against KiCad's STANDARD
   library, and applying it blindly here would create errors rather than fix them.

   This board's ICs and connectors use footprints fetched from LCSC by add_jlc_part.sh -
   the "_L3.0-W1.7-P0.95" naming. Those are generated from EasyEDA's own footprint data,
   which is the data JLCPCB assembles against, so they are ALREADY in JLCPCB orientation
   and need no correction. Correcting them would rotate a SOT-23 by -90 for nothing.
   The table is therefore applied only to KiCad standard-library footprints, and the
   passives among those are symmetric anyway.

tools/check_cpl.py verifies the result from board geometry, independently of this file.
"""
import os, re, sys, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = "NAVCORE-SoOP.kicad_pcb"
OUT = "fab"

# Parts held back from an ECONOMIC assembly order. Standard has a 70x70 mm minimum and
# this board is 45.1 x 46.1, so Standard means panelising (2x2 gives ~93x95 mm).
#
# THE REASON HERE IS UNVERIFIED AND MAY BE STALE. It was recorded as "JLCPCB will only
# place these on Standard", but JLCPCB's published assembly capabilities say Economic
# supports double-sided placement and BGA/LGA/QFN down to 0.40 mm pitch, and this board's
# finest pitch is 0.50 mm (U1 LQFP-100, U2/U3 LGA-14). So package capability does not
# explain it. The likelier reason is Economic's requirement that 100% of the BOM be in
# LCSC stock, which the PMW3901 in particular is at risk of failing.
#
# It no longer affects the order - the build is Standard and panelised, which places
# everything - but CONFIRM IT WITH JLC before relying on it again. A wrong reason left in
# the repo is how the next decision goes wrong.
#
# U6 and U7 are now DNP anyway (design.POPULATE_BLIND_SENSORS): neither can see the
# ground with the ESC 3 mm below them. They stay listed so the note survives if either
# is ever populated.
STANDARD_ONLY = {
    "U3": "ICM-42605 (C2655099) - second IMU, optional; ArduPilot flies on IMU1 alone",
    "U6": "PMW3901 (C43496881) - optical flow, needs X-ray; DNP, cannot see the ground",
    "U7": "VL53L1X (C190004) - downward rangefinder; DNP, cannot see the ground",
}

# A footprint whose name carries LCSC's dimensional suffix came from add_jlc_part.sh and
# is already in JLCPCB's orientation.
JLC_FP = re.compile(r'_L\d|^CONN-|^SENSORS-|^OPTO-|^TF-SMD|^COB-|^USB-C-SMD|^CRYSTAL-SMD')

# From JLCKicadTools cpl_rotations_db.csv, restricted to patterns that can match a KiCad
# standard-library footprint actually used on this board. Everything else there keys on
# packages this design does not use, and listing them would only invite mis-application.
KICAD_FP_ROTATION = [
    (re.compile(r'^SW_SPST_B3'), 90),
]


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
    # The 9 V VTX buck is now POPULATED by default (design.POPULATE_VTX), so the plain
    # run is the FPV build and there is nothing to opt into. --no-fpv is the opt-OUT,
    # for a build without video: it puts exactly design.VTX_BUCK_DNP back to DNP and
    # changes nothing else.
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

    with open(f"{OUT}/CPL-NAVCORE-SoOP{suffix}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for ref, fp in sorted(placed.items()):
            if ref in skip: continue      # nothing to pick and place
            if economic and ref in STANDARD_ONLY: continue
            # A DNP part is not placed. The BOM marked the 9 V VTX buck's 17 parts DNP
            # and the CPL still listed every one of them, so the assembler would have
            # picked and placed parts the BOM says not to fit - the two files
            # contradicting each other on the same board.
            _c = design.COMPONENTS.get(ref)
            if _c and is_dnp(ref, _c[4]): continue
            p = fp.GetPosition()
            w.writerow([ref, f"{pcbnew.ToMM(p.x):.4f}mm", f"{-pcbnew.ToMM(p.y):.4f}mm",
                        "bottom" if fp.GetLayerName() == "B.Cu" else "top",
                        f"{cpl_rotation(fp)[0]:.1f}"])

    n_lines = len(groups)
    n_parts = sum(len(r) for r in groups.values())
    n_dnp = sum(len(r) for (v, l, fpn, d), r in groups.items() if d)
    # `not l` alone missed the LOOKUP:<MPN> sentinel, which is a placeholder for an
    # unconfirmed C-code and must never reach JLCPCB as if it were one.
    no_lcsc = [v for (v, l, fpn, d), r in groups.items()
               if not l or str(l).startswith("LOOKUP:")]
    print(f"BOM: {n_lines} lines, {n_parts} parts ({n_dnp} DNP)")
    print(f"CPL: {sum(1 for r in placed if r not in skip)} placements")
    if no_fpv:
        print(f"NO-FPV variant - the 9 V VTX buck is left off ({len(vtx)} parts):")
        print(f"   {', '.join(sorted(vtx))}")
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
