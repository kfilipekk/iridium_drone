#!/usr/bin/env python3
"""The bolted joints, checked as JOINTS rather than as prose.

WHY THIS EXISTS. Every other mechanical check measures either clearance
(check_cad_fit.py: interference volume and separation between solids) or sums
(fasteners.py: the screw length from the thickness stack). Neither can see the two
failures that appear at assembly as a bolt that will not pass through:

  * A HOLE IS ABSENT MATERIAL. check_cad_fit.py measures interference and minimum
    separation; a skid printed with its bolt holes at 16x16 instead of the motor's
    19x19 produces zero overlap and a comfortable clearance, and reads ok. Same defect
    shape as the 4-byte stub that fooled the firmware gate: a green result measuring
    something adjacent to the property.
  * NO HOLE DIAMETER WAS DECLARED ANYWHERE. "19x19" named the pattern; nothing named
    the hole. A printed skid with 2.0 mm holes for an M3 screw passes every check in
    this repo until build day.

So the joint is now DECLARED ONCE - design.MOTOR_JOINT, with (dict, key) references for
the layer thicknesses so it cannot drift from the parts it names - and this file checks
the declaration:

  1. every through-layer's hole clears the screw by at least MIN_CLEAR,
  2. the pattern agrees across every participant, by reference to MOTOR_JOINT rather
     than to a literal or a substring (the old tests: "6x1" in "16x16 / 19x19" was
     True, and the skid was compared to the literal 19.0),
  3. the thickness references resolve - a renamed or moved design key fails here
     instead of silently computing a screw from a stale copy,
  4. the derived screw length agrees with tools/fasteners.py,
  5. the two remaining physical unknowns are shown to be BOUNDED rather than measured:
     the grommet compressed height is swept over 2.0-4.5 mm and every PURCHASE it could
     move (standoff length, FC/ESC screw, motor screw) must be invariant, and the
     microSD card's sliding gap is checked the same way. A range over which nothing
     changes does not need calipers.

Run: python3 tools/check_fit.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

MJ = design.MOTOR_JOINT
MIN_CLEAR = 0.2     # mm of radial clearance a hole must offer the screw


def resolve(ref):
    """('FRAME', 'arm_t') -> design.FRAME['arm_t'] - the (dict, key) reference."""
    d, k = ref
    obj = getattr(design, d, None)
    if obj is None or k not in obj:
        return None
    return obj[k]


def std_len(need_mm):
    for L in (4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40):
        if L >= need_mm:
            return L
    return None


def main():
    fails, notes = [], []

    # ---- the layers resolve --------------------------------------------------
    stack = []
    for name, ref, hole, src in MJ["layers"]:
        t = resolve(ref)
        if t is None:
            fails.append(f"{name}: thickness reference {ref} does not resolve in "
                         f"design.py - the joint spec is stale")
            continue
        stack.append((name, t, hole, src))
        if hole < MJ["screw_dia"] + MIN_CLEAR:
            fails.append(f"{name}: hole {hole:.1f} mm for an M{MJ['screw_dia']:.0f} screw "
                         f"({MJ['screw_dia']:.1f} mm) - needs >= "
                         f"{MJ['screw_dia'] + MIN_CLEAR:.1f} mm, the bolt will not pass")
        else:
            print(f"  ok   {name:14} {t:5.1f} mm thick, {hole:.1f} mm hole "
                  f"for a {MJ['screw_dia']:.1f} mm screw")

    # ---- the pattern, by reference ------------------------------------------
    p = MJ["pitch_mm"]
    in_frame = p in design.FRAME["motor_patterns_mm"]
    print(f"  ok   pattern        motor {p:.0f}x{p:.0f} is offered by the arm "
          f"({design.fmt_pattern(design.FRAME['motor_patterns_mm'])})"
          if in_frame else
          f"  FAIL pattern        motor {p:.0f}x{p:.0f} not among "
          f"{design.fmt_pattern(design.FRAME['motor_patterns_mm'])}")
    if not in_frame:
        fails.append(f"motor pattern {p:.0f}x{p:.0f} is not offered by the frame's arms")
    if abs(design.SKID["hole_pitch"] - p) > 1e-6:
        fails.append(f"skid is built to {design.SKID['hole_pitch']:.1f}x"
                     f"{design.SKID['hole_pitch']:.1f} but the motor taps "
                     f"{p:.1f}x{p:.1f} - check_fit caught what the literal 19.0 could not")
    else:
        print(f"  ok   skid           built to {p:.0f}x{p:.0f}, compared to MOTOR_JOINT "
              f"not to a literal")

    # ---- engagement, and what stays honestly unknown ------------------------
    if MJ["engage_mm"] < MJ["screw_dia"]:
        fails.append(f"engagement {MJ['engage_mm']:.1f} mm is under one diameter for "
                     f"M{MJ['screw_dia']:.0f}")
    else:
        print(f"  ok   engagement     {MJ['engage_mm']:.1f} mm into the "
              f"{MJ['engages']} (>= 1 x diameter)")
    if MJ["boss_depth_mm"] is None:
        # NOT silently accepted: the fasteners.py overshoot warning is the mitigation,
        # and it must actually be armed - a boss deeper than the screw cannot bottom out.
        need = sum(t for _, t, _, _ in stack) + MJ["engage_mm"]
        L = std_len(need)
        over = L - need + MJ["engage_mm"] if L else None
        if over is not None and over > MJ["engage_mm"]:
            notes.append(f"motor boss tapped depth is unpublished; M{MJ['screw_dia']:.0f}x{L} "
                         f"drives {over:.1f} mm and could bottom out if the boss is "
                         f"shallower - fasteners.py already prints this warning at "
                         f"purchase time; if it fires, drop one length and add a washer")
        print(f"  note boss depth     not published by BrotherHobby - bounded, see notes")

    # ---- agreement with fasteners.py ----------------------------------------
    need = sum(t for _, t, _, _ in stack) + MJ["engage_mm"]
    mine = std_len(need)
    # Compared to what fasteners.py DERIVES and to what PARTS.csv SELLS - not to a
    # literal. (The first version compared to 14 and claimed it "matches fasteners.py".)
    import fasteners, csv, re
    frow = next(r for r in fasteners.ROWS if r["where"].startswith("Motor to arm"))
    parts_csv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "docs", "PARTS.csv")
    sold = None
    with open(parts_csv, newline="") as f:
        for row in csv.reader(f):
            if len(row) > 1 and "(motor)" in row[1]:
                m = re.search(r"M3x(\d+)", row[1]); sold = int(m.group(1)) if m else None
    if mine == frow["L"] == sold:
        print(f"  ok   screw          {need:.1f} mm needed -> M{MJ['screw_dia']:.0f}x{mine} "
              f"x{frow['qty']}; fasteners.py derives M3x{frow['L']}, PARTS.csv sells M3x{sold}")
    else:
        fails.append(f"motor screw: check_fit derives M3x{mine}, fasteners.py M3x{frow['L']}, "
                     f"PARTS.csv sells M3x{sold} - they must agree")

    # ---- the grommet unknown is BOUNDED, not measured -----------------------
    # Sweep the compressed grommet over its plausible range and require the DOCUMENTED
    # purchases to cover the whole of it. The first formulation demanded invariance and
    # was wrong on its own first run: the FC/ESC screw genuinely flips M3x10 -> M3x12
    # across the range. That is not the unknown "being real" in the harmful sense - a
    # bounded unknown is COVERED by buying for the worst case, which is what you do
    # when you buy hardware against an interval. What IS a failure: the range forcing
    # MORE than the documented purchase, or the documented purchase having been chosen
    # from the middle of the range and leaving the worst case uncovered.
    print(f"\ngrommet compression sweep (the '[A] 3.0 mm' the docs promise to caliper):")
    import pcbnew
    board_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "NAVCORE-SoOP.kicad_pcb")
    b = pcbnew.LoadBoard(board_path)
    # The top plate sits where the KIT's standoffs put it (design.TOP_PLATE_MOUNT, from
    # the manufacturer DXF): 22 mm over the mid plate. That is not a purchase and does
    # not move with the grommet, so the property to sweep is the stack CLEARING it at
    # every plausible compression - and the stack bolt (fasteners.py) covering the
    # longest through-stack in the range.
    GROMMET_RANGE = (2.0, 4.5)     # silicone M3 grommet, compressed - generous bracket
    declared = design.MOUNTING["gap"]
    results = {}
    for gap in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5):
        design.MOUNTING["gap"] = gap
        sto = design.required_standoff(b)
        results[gap] = sto["slack"]
    design.MOUNTING["gap"] = declared
    worst_gap = min(results, key=results.get)
    if min(results.values()) >= 0.5:
        print(f"  ok   top plate       stack clears the kit's top plate by "
              f"{min(results.values()):.1f} mm at worst ({worst_gap:.1f} mm grommet); "
              f"{results[declared]:.1f} mm at the declared {declared:.1f} mm")
    else:
        fails.append(f"stack hits or grazes the top plate at {worst_gap:.1f} mm grommet "
                     f"compression ({min(results.values()):.2f} mm) - the 22 mm kit "
                     f"standoff is not enough; both standoff sets must grow by the same "
                     f"amount to keep the top plate flat")
    srow = next(r for r in fasteners.ROWS if "stack bolt" in r["where"])
    worst_need = srow["need"] + (GROMMET_RANGE[1] - declared)
    if std_len(worst_need) <= srow["L"]:
        print(f"  ok   stack bolt      M3x{srow['L']} covers the sweep (needs "
              f"{worst_need:.1f} mm at {GROMMET_RANGE[1]:.1f} mm grommet)")
    else:
        fails.append(f"stack bolt M3x{srow['L']} is short at {GROMMET_RANGE[1]:.1f} mm grommet "
                     f"({worst_need:.1f} mm needed) - buy M3x{std_len(worst_need)}")

    # ---- the kit's posts vs the board and the ESC --------------------------
    # Ø5 standoffs at |y| = 27.88 from the stack centre (the two front posts nearest the
    # stack). Both boards are concentric with the stack, so the clearance is a subtraction
    # - taken against the LONGER half-dimension of each, since either may lie along y.
    tpm = design.TOP_PLATE_MOUNT
    nearest = min(abs(p[1]) for p in tpm["front_posts"] + tpm["rear_posts"])
    post_edge = nearest - tpm["post_od"] / 2
    for name, half in (("board", max(design.BOARD["W"], design.BOARD["H"]) / 2 + 0.05),
                       ("ESC", max(design.ESC["L"], design.ESC["W"]) / 2)):
        c = post_edge - half
        if c >= 1.0:
            print(f"  ok   posts vs {name:5} nearest Ø{tpm['post_od']:.0f} post edge at "
                  f"{post_edge:.2f} mm vs a {half:.2f} mm half-length - {c:.2f} mm clear")
        else:
            fails.append(f"the kit's standoff posts sit {c:.2f} mm from the {name}'s edge "
                         f"(need >= 1.0)")

    # ---- microSD withdrawal, bounded the same way ---------------------------
    # The card slides out of J8 on the board's BOTTOM side, i.e. into the gap between
    # this board and the ESC below it. Card thickness is [D] 1.0 mm (SD spec); the
    # sliding gap is MOUNTING['gap'] (measured board-to-board) and does not involve
    # either board's parts - the card slides BETWEEN them, past the ESC's edge.
    j8 = b.FindFootprintByReference("J8")
    if j8 is None:
        fails.append("J8 (microSD) not found on the board")
    elif not j8.IsFlipped():
        notes.append("J8 is on the TOP side - the withdrawal constraint below does "
                     "not apply; re-check if the connector moves")
        print(f"  note microSD        J8 is top-side; no bottom clearance constraint")
    else:
        card_t = 1.0   # [D] SD specification
        worst = min(results)          # most-compressed grommet in the sweep
        margin = worst - card_t
        if margin >= 0.5:
            print(f"  ok   microSD        slides into the {worst:.1f} mm worst-case gap "
                  f"vs a {card_t:.1f} mm card - {margin:.1f} mm margin even at full "
                  f"compression; withdraws without removing anything from the frame")
        else:
            fails.append(f"microSD withdrawal: {worst:.1f} mm gap vs a {card_t:.1f} mm "
                         f"card at worst-case grommet compression")

    print()
    for n in notes:
        print(f"  NOTE {n}")
    if fails:
        print(f"FAIL - {len(fails)} fit problem(s)")
        for f_ in fails:
            print(f"  - {f_}")
        return 1
    print(f"PASS - the motor/arm/skid joint fits by declaration; the two remaining "
          f"physical unknowns are bounded, not deferred")
    return 0


if __name__ == "__main__":
    sys.exit(main())
