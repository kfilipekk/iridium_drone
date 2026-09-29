#!/usr/bin/env python3
#every threaded joint in the aircraft, with the thickness stack each length comes from
#Usage: python3 tools/fasteners.py [--md]
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

MD = "--md" in sys.argv
F = design.FRAME
ENGAGE = {3.0: 4.0, 2.5: 3.0, 2.0: 2.5}     #mm of thread, generous for soft materials

SKID_T = (design.SKID["t"],
          "[M] design.SKID['t'] - PRINTED part, so exact by design, not a measurement")
ESC_PCB = (1.6, "[D] SpeedyBee BLS 60A")
FC_PCB = (1.6, "[D] this board, 6-layer stackup")
GAP = (3.0, "[A] M3 silicone grommet, compressed")


#next standard metric screw length at or above x
def std(x):
    for L in (4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40):
        if L >= x - 0.01:
            return L
    return None


#warn when rounding up to a stock length could bottom the screw out in a tapped hole
def overshoot_note(needed, ordered, engage, dia=3.0, tapped=True):
    if ordered is None or not tapped:
        return None
    extra = ordered - needed
    if extra < 0.25:
        return None
    total = engage + extra
    return (f"rounding {needed:.1f} -> M{dia:g}x{ordered} puts {total:.1f} mm into the "
            f"thread, not {engage:.1f}. MEASURE THE TAPPED DEPTH before fitting: if it "
            f"is shallower than {total:.1f} mm the screw bottoms out and clamps nothing. "
            f"A {ordered - 2} mm screw plus a washer is the usual fix.")


ROWS = []


#layers: [(name, mm, src)] the screw passes through before engaging
def joint(where, dia, layers, qty, note="", engage=None, material="steel", limit=None):
    total = sum(t for _, t, _ in layers)
    engage = ENGAGE[dia] if engage is None else engage
    need = total + engage
    L = std(need)
    if limit is not None and L is not None and L - total > limit + 1e-9:
        note = (note + "; " if note else "") + (
            f"M{dia:g}x{L} would put {L - total:.1f} mm into a {limit:.1f} mm bore - "
            f"bottoms out: use M{dia:g}x{L - 1 if L - 1 >= need else L} or a washer")
    ROWS.append(dict(where=where, dia=dia, qty=qty, through=total, engage=engage,
                     need=need, L=L, layers=layers, note=note, material=material,
                     tapped=limit is None and engage == ENGAGE[dia]))


_MJ = design.MOTOR_JOINT
_JOINT_LAYERS = []
for _name, _ref, _hole, _src in _MJ["layers"]:
    _d, _k = _ref
    _t = getattr(design, _d)[_k]
    _JOINT_LAYERS.append((f"{_name}, hole {_hole:.1f}", _t, _src))
joint("Motor to arm, skid sandwiched", _MJ["screw_dia"], _JOINT_LAYERS, 16,
      f"skids MUST match the MOTOR's {_MJ['pitch_mm']:.0f}x{_MJ['pitch_mm']:.0f} pattern, "
      "not the frame's 16x16 - the fit check verifies the printed part")

import pcbnew as _pcbnew
_BOT = design.stack_heights(_pcbnew.LoadBoard(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "NAVCORE-SoOP.kicad_pcb")),
    skip_dnp=True)[1]
joint("FC to ESC to frame, the 30.5 mm stack bolt", 3.0,
      [("nylon washer under the head", design.FC_HOLE_HARDWARE["top"][0]["t"],
        "[L] M3 nylon washer - keeps the steel head off the pads (design.FC_HOLE_HARDWARE)"),
       ("FC PCB", FC_PCB[0], FC_PCB[1]),
       ("ESC-to-FC spacer", round(design.ESC["parts"] + GAP[0] + _BOT, 1),
        f"[M] ESC parts {design.ESC['parts']:.1f} + air {GAP[0]:.1f} + board bottom "
        f"parts {_BOT:.1f} (design.stack_heights, measured)"),
       ("ESC PCB", ESC_PCB[0], ESC_PCB[1]),
       ("mid plate", F["medium_t"], "[D] TBS: middle plate 2 mm"),
       ("arm root", F["arm_t"], "[D] TBS: arm 6 mm")],
      4, "into the bottom plate's press nut (kit, 8 pcs); buy 4 x M3 nylon female standoff 12 mm for the ESC-to-FC spacer - a grommet cannot hold 12.1 mm")

#the printed mounts (design.MOUNTS): every part off the board
import gen_scad_mounts as _gm

_G = _gm.G
_DERIVED = {"antenna_tower": {"gps.lid_under_head": _G["tower"]["lid_under_head"],
                              "gps.pod_h": _G["tower"]["pod_h"]},
            "range_cradle": {"body_h": _G["range"]["body_h"]}}
_GPS = (0.0, _G["tower"]["gps_y"], (_G["tower"]["gps_bot"] + _G["tower"]["gps_top"]) / 2)
_NUT_H = {2.0: 1.6, 2.5: 2.0, 3.0: 2.4}          #ISO 4032


#A joint layer's thickness: a number, or a dimension named in design.py
def _dim(mount, ref):
    if not isinstance(ref, str):
        return ref, "[D] design.FRAME - TBS plate thicknesses"
    if "-" in ref:
        a, b = ref.split("-")
        return (_dim(mount, a)[0] - _dim(mount, b)[0],
                f"[M] {mount}.{a} less {b} (gen_scad_mounts)")
    if ref in _DERIVED.get(mount, {}):
        return _DERIVED[mount][ref], f"[M] derived in tools/gen_scad_mounts.py ({ref})"
    head, _, key = ref.partition(".")
    spec = design.MOUNTS[mount]
    if not key:
        return spec[head], f"[M] design.MOUNTS['{mount}']"
    if head in spec and key in spec[head]:
        return spec[head][key], f"[M] design.MOUNTS['{mount}']['{head}']"
    if head in design.MOUNTED:
        return design.MOUNTED[head][key], design.MOUNTED[head]["src"]
    return design.OFFBOARD[head][key], design.OFFBOARD[head]["src"][:80]


for _m, _spec in design.MOUNTS.items():
    for _j in _spec["joints"]:
        _size = _j["size"]
        _dia = design.INSERTS[_size]["dia"] if _size in design.INSERTS else float(_size[1:])
        _layers = []
        for _name, _ref in _j["layers"]:
            _t, _src = _dim(_m, _ref)
            _layers.append((_name, round(_t, 2), _src))
        #brass near the compass: a joint at a known place is measured to the GPS
        _near = (min(math.dist(p, _GPS) for p in _j["at"]) < design.NONMAG_RADIUS_MM
                 if "at" in _j else "gps" in _spec["carries"])
        _mat = "brass" if _near else "steel"
        if _j["into"] == "insert":
            _ins = design.INSERTS[_size]
            joint(_j["where"], _dia, _layers, _j["qty"],
                  f"into {_size.rstrip('s')} x {_ins['L']:g} heat-set inserts",
                  engage=min(ENGAGE[_dia], _ins["L"]), material=_mat, limit=_ins["L"] + 1.0)
        elif _j["into"] == "nut":
            joint(_j["where"], _dia, _layers, _j["qty"], "nylon-insert lock nut on top",
                  engage=_NUT_H[_dia] + 1.0, material=_mat)
        else:
            joint(_j["where"], _dia, _layers, _j["qty"],
                  "into the kit's threaded standoff", material=_mat)

UNKNOWN = [
    ("Frame assembly - top plate to standoffs", "M3",
     "the listing gives neither the standoff length nor the spacing; measure the kit"),
    ("Camera module to its mount", "M2 or M2.5",
     "no camera mount exists yet - position, plate and hole pattern all undecided"),
    ("Camera mount to frame", "M3",
     "depends where it lands; see the ground-clearance question in docs/HARDWARE.md"),
    (f"{design.PI['name']} - mounting location UNDECIDED", "M2.5",
     ((f"{design.PI['hole_pitch'][0]:.1f} x {design.PI['hole_pitch'][1]:.1f} mm pattern"
       if isinstance(design.PI.get('hole_pitch'), tuple)
       else f"{design.PI['hole_pitch']} mm pattern")
      if design.PI.get('hole_pitch')
      else "hole PATTERN NOT PUBLISHED by the vendor - measure the board")
     + f"; {design.PI['hole_dia']:.1f} mm holes, self-tapping into a "
       f"{F['upper_t']:.1f} mm plate; standoff height unmeasured"),
]


def main():
    if MD:
        #the overshoot warning must appear here too
        print("| joint | screw | qty | passes through | engagement | order |")
        print("|---|---|---|---|---|---|")
        warns = []
        for r in ROWS:
            thru = " + ".join(f"{n} {t:.1f}" for n, t, _ in r["layers"])
            _ov = overshoot_note(r["need"], r["L"], r["engage"], r["dia"], r.get("tapped", True))
            print(f"| {r['where']} | M{r['dia']:.0f} | {r['qty']} | {thru} "
                  f"= {r['through']:.1f} mm | {r['engage']:.1f} mm | "
                  f"**M{r['dia']:g}x{r['L']}** {r['material']}{' &#9888;' if _ov else ''} |")
            if _ov:
                warns.append(f"- **{r['where']}** &#9888; {_ov}")
        if warns:
            print()
            print("\n".join(warns))
        print()
        print("| joint | screw | why it is not derived |")
        print("|---|---|---|")
        for w, d, why in UNKNOWN:
            print(f"| {w} | {d} | {why} |")
        return 0

    print("derived joints")
    for r in ROWS:
        print(f"\n  {r['where']}")
        for n, t, s in r["layers"]:
            print(f"      {n:22s} {t:5.1f} mm   {s}")
        print(f"      {'thread engagement':22s} {r['engage']:5.1f} mm   "
              f"[A] {'1 x diameter into soft material' if r['engage'] == ENGAGE[r['dia']] else 'the insert, or a nut and a thread past it'}")
        print(f"      {'':22s} {'':5s}      -> needs {r['need']:.1f} mm, "
              f"order M{r['dia']:g}x{r['L']} {r['material']}  x{r['qty']}")
        _ov = overshoot_note(r["need"], r["L"], r["engage"], r["dia"], r.get("tapped", True))
        if _ov:
            print(f"      WARN: {_ov}")
        if r["note"]:
            print(f"      note: {r['note']}")
    print("\nNOT derived - these need the parts in hand:")
    for w, d, why in UNKNOWN:
        print(f"  {w}\n      {d} - {why}")
    print(f"\n{len(ROWS)} joint(s) derived, {len(UNKNOWN)} still to measure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
