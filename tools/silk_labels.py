#!/usr/bin/env python3
"""
Put reference designators for the solder pads and test points onto the silkscreen.

WHY THIS IS NOT TRIVIAL
-----------------------
All 38 pad and test-point references live on the *Fab* layer, which is not printed. The
board therefore arrives with 38 identical unlabelled gold squares and no way to tell the
companion 5 V pad from a CAN ground.

The naive fix - flip the layer and shrink the text - fails. The board's own rule sets a
0.80 mm minimum silkscreen text height (below that a fab cannot print it legibly), and at
0.80 mm a three-character label is roughly 2.0 x 0.8 mm. The pads are 1.5 mm squares on a
2.84 mm pitch, so a label centred on its pad covers the pad and its neighbours.

So the text has to go BESIDE the pad, in whatever gap exists. This tries eight directions
at three distances for each label, rejects any placement that collides with a pad, an
existing silkscreen item, another new label, or the board edge, and keeps the best fit.
Labels that cannot be placed cleanly are LEFT OFF rather than placed illegibly - a wrong
or unreadable label on a board is worse than a blank pad, because it will be trusted.

Copper is never touched. Run tools/preflight.py afterwards regardless.

Usage:
  python3 tools/silk_labels.py            # report what it could place
  python3 tools/silk_labels.py --apply
"""
import math, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK = "/tmp/nav/silk_backup.kicad_pcb"
TOMM = lambda v: v / 1e6
FROMM = pcbnew.FromMM

# TARGETS names pads by reference, so it goes stale silently when the design changes -
# P42/P43/P45 and P51-P54 are all gone (the first three were never re-added; the last
# four became connector J5), and refs that are not on the board are skipped rather than
# reported. If a pad stops being labelled, check here before concluding the geometry
# got worse. preflight.py reports the coverage every run for the same reason.
TARGETS = (["P41", "P44", "P46"] + [f"P5{i}" for i in range(1, 5)] +
           [f"P6{i}" for i in range(1, 5)] + [f"P7{i}" for i in range(1, 5)] +
           [f"TP{i}" for i in range(1, 12)] + ["TP20", "TP21"] +
           ["PL1", "PL2", "PL3", "PV1", "PV2", "PZ1", "PZ2"])

TEXT_H = 0.80          # the board's own minimum; anything less is unprintable
TEXT_T = 0.12
CHAR_W = 1.05          # KiCad stroke font: glyph + inter-character gap, per unit height.
                       # An earlier 0.72 underestimated it and a third of the labels
                       # landed on top of something. The verification pass below now
                       # measures the REAL rendered box and withdraws any that still
                       # collide, so this only has to be close.
CLEAR = 0.18           # keep-out around a label


def bbox_of(x, y, w, h):
    return (x - w / 2 - CLEAR, y - h / 2 - CLEAR, x + w / 2 + CLEAR, y + h / 2 + CLEAR)


def overlaps(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def collect_obstacles(board, exclude=()):
    """Everything a label must not sit on: pads, existing silk, board edge.

    `exclude` skips the reference text of the footprints being labelled - without it the
    verification pass re-collects the labels it just placed and every one collides with
    itself, withdrawing the lot.
    """
    obs = []
    for fp in board.GetFootprints():
        skip_ref = fp.GetReference() in exclude
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            obs.append((TOMM(bb.GetX()), TOMM(bb.GetY()),
                        TOMM(bb.GetX() + bb.GetWidth()), TOMM(bb.GetY() + bb.GetHeight())))
        items = list(fp.GraphicalItems()) + [fp.Value()]
        if not skip_ref:
            items.append(fp.Reference())
        for item in items:
            try:
                if not item.IsVisible():
                    continue
                if "Silkscreen" not in board.GetLayerName(item.GetLayer()):
                    continue
            except Exception:
                continue
            bb = item.GetBoundingBox()
            obs.append((TOMM(bb.GetX()), TOMM(bb.GetY()),
                        TOMM(bb.GetX() + bb.GetWidth()), TOMM(bb.GetY() + bb.GetHeight())))
    return obs


def place_labels(board):
    """Return (placed, skipped) for every TARGETS ref actually on the board.

    Separated from main() so preflight can report the coverage count without
    touching the board. Placement rules are unchanged: a label that cannot sit
    cleanly beside its pad is LEFT OFF rather than printed illegibly.
    """
    edge = board.GetBoardEdgesBoundingBox()
    ex0, ey0 = TOMM(edge.GetX()), TOMM(edge.GetY())
    ex1, ey1 = ex0 + TOMM(edge.GetWidth()), ey0 + TOMM(edge.GetHeight())

    obstacles = collect_obstacles(board)
    placed, skipped = [], []

    # try close in first, and cardinal directions before diagonals
    dirs = [(0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1)]
    dists = [1.15, 1.55, 2.0, 2.5]

    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref not in TARGETS:
            continue
        p = fp.GetPosition()
        px, py = TOMM(p.x), TOMM(p.y)
        w, h = len(ref) * CHAR_W * TEXT_H / 0.8 * 0.8, TEXT_H
        w = len(ref) * CHAR_W
        best = None
        for d in dists:
            for dx, dy in dirs:
                n = math.hypot(dx, dy)
                cx, cy = px + dx / n * (d + w / 2 * abs(dx)), py + dy / n * (d + h / 2 * abs(dy))
                bb = bbox_of(cx, cy, w, h)
                if bb[0] < ex0 + 0.3 or bb[1] < ey0 + 0.3 or bb[2] > ex1 - 0.3 or bb[3] > ey1 - 0.3:
                    continue
                if any(overlaps(bb, o) for o in obstacles):
                    continue
                best = (cx, cy, bb)
                break
            if best:
                break
        if best:
            placed.append((ref, fp, best))
            obstacles.append(best[2])
        else:
            skipped.append(ref)

    return placed, skipped


def main():
    apply = "--apply" in sys.argv
    board = pcbnew.LoadBoard(BOARD)
    placed, skipped = place_labels(board)

    print(f"placeable: {len(placed)} of {len(placed) + len(skipped)}")
    if skipped:
        print(f"  no clean position for: {', '.join(sorted(skipped))}")

    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0

    shutil.copy(BOARD, BAK)
    silk_f = board.GetLayerID("F.Silkscreen")
    silk_b = board.GetLayerID("B.Silkscreen")
    for ref, fp, (cx, cy, _bb) in placed:
        t = fp.Reference()
        t.SetLayer(silk_b if board.GetLayerName(fp.GetLayer()).startswith("B.") else silk_f)
        t.SetVisible(True)
        t.SetTextSize(pcbnew.VECTOR2I(FROMM(TEXT_H), FROMM(TEXT_H)))
        t.SetTextThickness(FROMM(TEXT_T))
        t.SetPosition(pcbnew.VECTOR2I(FROMM(cx), FROMM(cy)))
        t.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    # --- verification pass -------------------------------------------------
    # Estimating text extents from a character-width ratio is only ever approximate.
    # Now that the text objects exist, ask KiCad for their ACTUAL bounding boxes and
    # withdraw any label that still collides. A label that overlaps its neighbour is
    # unreadable, and an unreadable label is worse than a blank pad because it will be
    # trusted.
    fixed = collect_obstacles(board, exclude=set(TARGETS))
    real = []
    for ref, fp, _ in placed:
        t = fp.Reference()
        bb = t.GetBoundingBox()
        real.append((ref, fp, (TOMM(bb.GetX()) - CLEAR, TOMM(bb.GetY()) - CLEAR,
                               TOMM(bb.GetX() + bb.GetWidth()) + CLEAR,
                               TOMM(bb.GetY() + bb.GetHeight()) + CLEAR)))
    keep, withdrawn = [], []
    for i, (ref, fp, bb) in enumerate(real):
        others = [b for j, (_r, _f, b) in enumerate(real) if j != i and (_r, _f) not in
                  [(k[0], k[1]) for k in withdrawn]]
        if any(overlaps(bb, o) for o in fixed) or any(overlaps(bb, o) for o in others):
            withdrawn.append((ref, fp, bb))
        else:
            keep.append(ref)
    for ref, fp, _ in withdrawn:
        t = fp.Reference()
        t.SetLayer(board.GetLayerID("F.Fab") if not
                   board.GetLayerName(fp.GetLayer()).startswith("B.")
                   else board.GetLayerID("B.Fab"))
        t.SetVisible(True)

    board.Save(BOARD)
    print(f"\nplaced cleanly: {len(keep)}")
    if withdrawn:
        print(f"withdrawn after measuring real extents: "
              f"{', '.join(sorted(r for r, _f, _b in withdrawn))}")
    print(f"backup at {BAK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
