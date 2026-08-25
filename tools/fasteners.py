#!/usr/bin/env python3
"""Every threaded joint in the aircraft, with the thickness stack each length comes from.

Usage: python3 tools/fasteners.py [--md]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

MD = "--md" in sys.argv
F = design.FRAME
ENGAGE = {3.0: 4.0, 2.5: 3.0, 2.0: 2.5}     # mm of thread, generous for soft materials

SKID_T = (3.5, "[A] ready-made TPU skid - MEASURE THE ONE YOU BUY, it sets this length")
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
    """Warn when rounding up to a stock length could bottom the screw out."""
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
    """layers: [(name, mm, src)] the screw passes through before engaging."""
    total = sum(t for _, t, _ in layers)
    need = total + ENGAGE[dia]
    L = std(need)
    ROWS.append(dict(where=where, dia=dia, qty=qty, through=total,
                     engage=ENGAGE[dia], need=need, L=L, layers=layers, note=note))


joint("Motor to arm, skid sandwiched", 3.0,
      [("frame arm", F["arm_t"], F["src"]), ("TPU skid", SKID_T[0], SKID_T[1])],
      16, "skids MUST match the MOTOR's 19x19 pattern, not the frame's 16x16")

joint("FC to ESC, through the 30.5 mm stack", 3.0,
      [("ESC PCB", ESC_PCB[0], ESC_PCB[1]),
       ("grommet gap", GAP[0], GAP[1]),
       ("FC PCB", FC_PCB[0], FC_PCB[1])],
      4, "into the frame's own standoff; grommets take M3 through a 4.00 mm hole")

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
        # The overshoot warning must appear here too.
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


sys.exit(main())
