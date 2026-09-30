#!/usr/bin/env python3
"""Does every label on the silkscreen read as its own part's, and can it be read at all?

Usage: python3 tools/check_silk_owner.py [--board PATH]
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from check_backside import body_box

BOARD = "NAVCORE-SoOP.kicad_pcb"
TEXT_GAP = pcbnew.FromMM(0.40)   #two labels closer than this read as one word
MARGIN = pcbnew.FromMM(0.50)     #nearer its own part than any other, by at least this
HIDE = pcbnew.FromMM(0.10)       #overlap with a body that hides a label, beyond rounding
MIN_H, MIN_W = pcbnew.FromMM(1.0), pcbnew.FromMM(0.15)   #JLCPCB: legible from 1.0 / 0.15
T = pcbnew.ToMM


def grow(bb, d):
    b = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
    b.Inflate(d)
    return b


def text_box(t):
    """The strokes, not KiCad's padded text box."""
    return t.GetEffectiveTextShape().BBox()


def gap(bx, x, y):
    return math.hypot(max(bx.GetLeft() - x, 0, x - bx.GetRight()),
                      max(bx.GetTop() - y, 0, y - bx.GetBottom()))


def bodies(board):
    return {fp.GetReference(): (fp.IsFlipped(), body_box(fp)) for fp in board.GetFootprints()}


def owner_margin(bods, owner, bottom, x, y):
    """(distance to the nearest other part) - (distance to the owner)."""
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
        #a pad's function label (silk_labels.py) is text the footprint itself carries
        for g in fp.GraphicalItems():
            if g.Type() == pcbnew.PCB_TEXT_T and g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                out.append((fp.GetReference(), g))
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
        bottom = t.GetLayer() == pcbnew.B_SilkS
        name = t.GetText() if t.Type() == pcbnew.PCB_TEXT_T else owner
        m, other = owner_margin(bods, owner, bottom, c.x, c.y)
        if m < MARGIN:
            bad.append(f"{name} (for {owner}) could read as {other}'s: "
                       f"{T(gap(bods[owner][1], c.x, c.y)):.2f} mm from {owner}, "
                       f"{T(gap(bods[other][1], c.x, c.y)):.2f} mm from {other} "
                       f"(needs {T(MARGIN):.2f} mm between)")
        strokes = grow(text_box(t), -HIDE)
        under = sorted(ref for ref, (flip, bx) in bods.items()
                       if flip == bottom and bx is not None and strokes.Intersects(bx))
        if under:
            bad.append(f"{name} (for {owner}) is printed under {', '.join(under)} - "
                       "hidden once assembled")
    #two labels closer than TEXT_GAP read as one word
    boxes = [(t.GetText() if t.Type() == pcbnew.PCB_TEXT_T else o, t.GetLayer(), text_box(t))
             for o, t in items]
    for i, (na, la, ba) in enumerate(boxes):
        for nb, lb, bb in boxes[i + 1:]:
            if la == lb and grow(ba, TEXT_GAP).Intersects(bb):
                bad.append(f"{na} and {nb} are closer than "
                           f"{T(TEXT_GAP):.2f} mm - they read as one word")
    #every printed text, labels or not, has to be printable
    small = []
    texts = [d for d in b.GetDrawings() if d.Type() == pcbnew.PCB_TEXT_T]
    for fp in b.GetFootprints():
        texts += [fp.Reference(), fp.Value()] + [g for g in fp.GraphicalItems()
                                                 if g.Type() == pcbnew.PCB_TEXT_T]
    for t in texts:
        if not t.IsVisible() or t.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            continue
        if t.GetTextHeight() < MIN_H - 1000 or t.GetEffectiveTextPenWidth() < MIN_W - 1000:
            small.append(f"'{t.GetShownText(False)}' is {T(t.GetTextHeight()):.2f} mm tall, "
                         f"{T(t.GetEffectiveTextPenWidth()):.2f} mm stroke")
    bad += [f"{x} - under {T(MIN_H):.1f} / {T(MIN_W):.2f} mm prints smudged" for x in small]
    print(f"{len(items)} printed labels checked against every part on their side; "
          f"{len(texts)} texts checked for size")
    for x in bad:
        print(f"  FAIL {x}")
    if bad:
        print(f"\nFAIL - {len(bad)} label problem(s): misattributed, hidden, run together "
              "or too small")
        return 1
    print("every label reads as its own part's by a clear margin, none is hidden or run "
          "together, and every text prints legibly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
