#!/usr/bin/env python3
"""Does every label on the silkscreen sit nearer its own part than any other part?

Usage: python3 tools/check_silk_owner.py [--board PATH]
The placing tools import owner_margin() so they cannot place what this check rejects.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from check_backside import body_box

BOARD = "NAVCORE-SoOP.kicad_pcb"
TEXT_GAP = pcbnew.FromMM(0.40)   # two labels closer than this read as one word
T = pcbnew.ToMM


def grow(bb, d):
    b = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
    b.Inflate(d)
    return b


def text_box(t):
    """The strokes, not KiCad's padded text box ."""
    return t.GetEffectiveTextShape().BBox()


def gap(bx, x, y):
    return math.hypot(max(bx.GetLeft() - x, 0, x - bx.GetRight()),
                      max(bx.GetTop() - y, 0, y - bx.GetBottom()))


def bodies(board):
    return {fp.GetReference(): (fp.IsFlipped(), body_box(fp)) for fp in board.GetFootprints()}


def owner_margin(bods, owner, bottom, x, y):
    """(distance to the nearest other part) - (distance to the owner), in board units, and
    that other part's reference. Positive means the label reads as its owner's.
    """
    own = gap(bods[owner][1], x, y)
    best = None
    for ref, (flip, bx) in bods.items():
        if ref == owner or flip != bottom or bx is None:
            continue
        d = gap(bx, x, y)
        if best is None or d < best[0]:
            best = (d, ref)
    return (best[0] - own, best[1]) if best else (float("inf"), None)


def labels(board):
    """(owner ref, text item) for everything printed that names a part."""
    out = []
    for fp in board.GetFootprints():
        r = fp.Reference()
        if r.IsVisible() and r.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            out.append((fp.GetReference(), r))
    import design
    owner_of = {v: k for k, v in design.SILK_NAMES.items()}
    for d in board.GetDrawings():
        if d.Type() == pcbnew.PCB_TEXT_T and d.GetText() in owner_of:
            out.append((owner_of[d.GetText()], d))
    return out


def main():
    path = sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv else BOARD
    b = pcbnew.LoadBoard(path)
    bods = bodies(b)
    bad = []
    items = labels(b)
    for owner, t in items:
        c = text_box(t).GetCenter()
        m, other = owner_margin(bods, owner, t.GetLayer() == pcbnew.B_SilkS, c.x, c.y)
        if m <= 0:
            name = t.GetText() if t.Type() == pcbnew.PCB_TEXT_T else owner
            bad.append(f"{name} (for {owner}) reads as {other}'s: "
                       f"{T(gap(bods[owner][1], c.x, c.y)):.2f} mm from {owner}, "
                       f"{T(gap(bods[other][1], c.x, c.y)):.2f} mm from {other}")
    # Two labels closer than TEXT_GAP read as one word ("P71TP21",.
    boxes = [(t.GetText() if t.Type() == pcbnew.PCB_TEXT_T else o, t.GetLayer(), text_box(t))
             for o, t in items]
    for i, (na, la, ba) in enumerate(boxes):
        for nb, lb, bb in boxes[i + 1:]:
            if la == lb and grow(ba, TEXT_GAP).Intersects(bb):
                bad.append(f"{na} and {nb} are closer than "
                           f"{T(TEXT_GAP):.2f} mm - they read as one word")
    print(f"{len(items)} printed labels checked against every part on their side")
    for x in bad:
        print(f"  FAIL {x}")
    if bad:
        print(f"\nFAIL - {len(bad)} label problem(s): misattributed or run together")
        return 1
    print("every label sits nearer its own part than any other, and none run together")
    return 0


if __name__ == "__main__":
    sys.exit(main())
