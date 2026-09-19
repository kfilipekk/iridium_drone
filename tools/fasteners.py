#!/usr/bin/env python3
"""
Every threaded joint in the aircraft, with the thickness stack each length comes from.

Written because only ONE joint was ever computed - the motor screws - and the rest was
prose spread across four documents. A screw length is a derived quantity: it is the sum
of what it passes through plus the thread engagement, and if any layer in that sum
changes the length changes with it. Writing lengths down as constants is how you end up
at the field with M3x8 screws and a 3.5 mm skid that needs M3x14.

Engagement rule: aim for at least 1 x diameter into the thread, which is 3 mm for M3 and
2.5 mm for M2.5. Aluminium motor bells and nylon standoffs both tolerate that.

Anything this cannot derive is REPORTED as unknown rather than guessed. A missing row is
a thing to measure, not a thing to assume.

THE SKID THICKNESS IS NO LONGER ONE OF THEM. This file carried its own 3.5 mm copy,
tagged "[A] ready-made TPU skid - MEASURE THE ONE YOU BUY" - but the skid is a PRINTED
part (design.SKID['printed']), so its thickness is exact by design and there is nothing
to measure. The duplicate was also live, not merely redundant: design.SKID['t'] feeds
the CAD and the ground-clearance arithmetic, so editing it there would have left the
motor screw length computing from a stale 3.5 and the M3x14 purchase silently wrong - a
joint that fits in the BOM and not on the aircraft. It now reads design.SKID['t'].

Usage: python3 tools/fasteners.py [--md]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

MD = "--md" in sys.argv
F = design.FRAME
ENGAGE = {3.0: 4.0, 2.5: 3.0, 2.0: 2.5}     # mm of thread, generous for soft materials

SKID_T = (design.SKID["t"],
          "[M] design.SKID['t'] - PRINTED part, so exact by design, not a measurement")
ESC_PCB = (1.6, "[D] SpeedyBee BLS 60A")
FC_PCB = (1.6, "[D] this board, 6-layer stackup")
GAP = (3.0, "[A] M3 silicone grommet, compressed")


def std(x):
    """Next standard metric screw length at or above x."""
    for L in (4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40):
        if L >= x - 0.01:
            return L
    return None


def overshoot_note(needed, ordered, engage):
    """Warn when rounding up to a stock length could bottom the screw out.

    Rounding up is not free. The computed length already includes the engagement we
    WANT; every millimetre above it goes deeper into the thread, and a motor boss is
    typically only about 4 mm deep. A screw that bottoms out feels tight while clamping
    nothing, which is the failure that throws a motor in flight.

    M3x12.5 is not a stock length, so the 5 mm arm lands exactly on this trap: 12 mm
    under-engages by 0.5 mm, 14 mm drives 1.5 mm deeper than designed.
    """
    if ordered is None:
        return None
    extra = ordered - needed
    if extra < 0.25:
        return None
    total = engage + extra
    return (f"rounding {needed:.1f} -> M{'3'} x{ordered} puts {total:.1f} mm into the "
            f"thread, not {engage:.1f}. MEASURE THE TAPPED DEPTH before fitting: if it "
            f"is shallower than {total:.1f} mm the screw bottoms out and clamps nothing. "
            f"A {ordered - 2} mm screw plus a washer is the usual fix.")


ROWS = []


def joint(where, dia, layers, qty, note=""):
    """layers: [(name, mm, src)] the screw passes THROUGH before engaging."""
    total = sum(t for _, t, _ in layers)
    need = total + ENGAGE[dia]
    L = std(need)
    ROWS.append(dict(where=where, dia=dia, qty=qty, through=total,
                     engage=ENGAGE[dia], need=need, L=L, layers=layers, note=note))


# THE MOTOR JOINT IS NOT RESTATED HERE. It is built from design.MOTOR_JOINT - the one
# spec for the pitch, the hole diameters and the through-stack - so a change to the skid
# thickness or the arm moves the derived screw length in the same edit. The layer
# thicknesses are (DICT, KEY) references into design.py, resolved here; check_fit.py
# checks the same spec for hole-vs-screw clearance, so the two tools cannot disagree.
_MJ = design.MOTOR_JOINT
_JOINT_LAYERS = []
for _name, _ref, _hole, _src in _MJ["layers"]:
    _d, _k = _ref
    _t = getattr(design, _d)[_k]
    # label keeps the HOLE, not the thickness: the table prints the thickness itself
    # from the second field, and embedding it in the label printed every number twice.
    _JOINT_LAYERS.append((f"{_name}, hole {_hole:.1f}", _t, _src))
joint("Motor to arm, skid sandwiched", _MJ["screw_dia"], _JOINT_LAYERS, 16,
      f"skids MUST match the MOTOR's {_MJ['pitch_mm']:.0f}x{_MJ['pitch_mm']:.0f} pattern, "
      "not the frame's 16x16 - tools/check_fit.py verifies the printed part")

# THE STACK BOLT. Where it lands is settled by the DXF: the top plate has no 30.5 holes
# and the kit has no standoff at that pattern, but the BOTTOM plate carries 8 press
# nuts at the 30.5 / 20 patterns ("M3 Press nuts pre-install", layer 9) and the arm
# roots have matching holes. So the stack bolt runs FC -> ESC -> mid plate -> arm ->
# press nut, clamping the arms and the stack in one screw. The separation between the
# two PCBs is NOT a 3 mm grommet: the ESC's parts (6.2) + air (3.0) + this board's
# bottom parts (2.9) = 12.1 mm must be held by a spacer - 4 x M3 female standoffs,
# 12 mm, are the purchase that was missing from PARTS.csv.
# The board's bottom-parts height is MEASURED from the routed board (design.stack_heights
# walks the real footprints), not restated here - restating it is how SKID_T went stale.
import pcbnew as _pcbnew
_BOT = design.stack_heights(_pcbnew.LoadBoard(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "NAVCORE-SoOP.kicad_pcb")),
    skip_dnp=True)[1]
joint("FC to ESC to frame, the 30.5 mm stack bolt", 3.0,
      [("FC PCB", FC_PCB[0], FC_PCB[1]),
       ("ESC-to-FC spacer", round(design.ESC["parts"] + GAP[0] + _BOT, 1),
        f"[M] ESC parts {design.ESC['parts']:.1f} + air {GAP[0]:.1f} + board bottom "
        f"parts {_BOT:.1f} (design.stack_heights, measured)"),
       ("ESC PCB", ESC_PCB[0], ESC_PCB[1]),
       ("mid plate", F["medium_t"], "[D] TBS: middle plate 2 mm"),
       ("arm root", F["arm_t"], "[D] TBS: arm 6 mm")],
      4, "into the bottom plate's press nut (kit, 8 pcs); buy 4 x M3 female standoff "
         "12 mm for the ESC-to-FC spacer - a grommet cannot hold 12.1 mm")

UNKNOWN = [
    ("Frame assembly - top plate to standoffs", "M3",
     "the listing gives neither the standoff length nor the spacing; measure the kit"),
    ("Camera module to its mount", "M2 or M2.5",
     "no camera mount exists yet - position, plate and hole pattern all undecided"),
    ("Camera mount to frame", "M3",
     "depends where it lands; see the ground-clearance question in docs/HARDWARE.md"),
    # NOT "to the top plate" any more - it does not go there. The plate is 50 mm wide,
    # the battery takes 47 of it, and this board is 65 x 30 mm; check_cad_fit.py
    # measured 1165 mm^3 of battery inside it. Where it mounts is an open decision,
    # so the row says so rather than naming a location that will not work.
    (f"{design.PI['name']} - mounting location UNDECIDED", "M2.5",
     # Kept conditional. The Orange Pi Zero 2W episode is why: its four 3.0 mm holes are
     # documented but their centres are not published, and inheriting the Pi Zero's
     # 58 x 23 mm pattern would have been inventing it. The Pi Zero 2 W's pattern IS
     # published, in Raspberry Pi's own mechanical drawing, so it is stated here.
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
        # The overshoot warning MUST appear here too. The markdown table is what gets
        # pasted into docs/HARDWARE.md and read at ordering time, and the terminal
        # output is not. A table that prints "M3x14" with no hint that it drives 5.5 mm
        # into a boss that may only be 4 mm deep is the more dangerous of the two.
        print("| joint | screw | qty | passes through | engagement | order |")
        print("|---|---|---|---|---|---|")
        warns = []
        for r in ROWS:
            thru = " + ".join(f"{n} {t:.1f}" for n, t, _ in r["layers"])
            _ov = overshoot_note(r["need"], r["L"], r["engage"])
            print(f"| {r['where']} | M{r['dia']:.0f} | {r['qty']} | {thru} "
                  f"= {r['through']:.1f} mm | {r['engage']:.1f} mm | "
                  f"**M{r['dia']:.0f}x{r['L']}**{' &#9888;' if _ov else ''} |")
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
              f"[A] 1 x diameter into soft material")
        print(f"      {'':22s} {'':5s}      -> needs {r['need']:.1f} mm, "
              f"order M{r['dia']:.0f}x{r['L']}  x{r['qty']}")
        _ov = overshoot_note(r["need"], r["L"], r["engage"])
        if _ov:
            print(f"      WARN: {_ov}")
        if r["note"]:
            print(f"      note: {r['note']}")
    print("\nNOT derived - these need the parts in hand:")
    for w, d, why in UNKNOWN:
        print(f"  {w}\n      {d} - {why}")
    print(f"\n{len(ROWS)} joint(s) derived, {len(UNKNOWN)} still to measure")
    return 0


# Guarded: check_fit.py imports ROWS to compare its own derivation against this one,
# and an unguarded sys.exit(main()) ran this report and exited THE IMPORTER with rc 0
# before its checks printed - a green exit code from the wrong program.
if __name__ == "__main__":
    sys.exit(main())
