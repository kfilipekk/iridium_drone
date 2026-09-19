#!/usr/bin/env python3
"""Place parts that tools/sync_board.py parked, each within its ADJACENCY bound.

The obstacle model is the one place_tempsensor.py learned the hard way - footprints,
through-hole pads, copper on the target layer, vias, board- AND footprint-level rule
areas, then a zone refill and DRC in place. Two things are added here:

  * parts are placed IN THE ORDER GIVEN and each becomes an obstacle for the next, so
    an anchor chain (R52 -> R53 -> C75) resolves in sequence;
  * parts still waiting to be placed are NOT obstacles. sync_board.py parks every new
    part on top of its anchor, and a parked sibling would otherwise block the cell
    its neighbour needs.

Refuses rather than compromises: a part that cannot be placed inside its bound is
reported and left parked, because a decoupling capacitor 8 mm from its pin is worse
than one that is visibly not placed.

    python3 tools/place_parts.py R47 R48 R49 R50 R51 R52 R53 C75
"""
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import design
import place_tempsensor as P

BOARD = "NAVCORE-SoOP.kicad_pcb"
PREV = "NAVCORE-SoOP.prev.kicad_pcb"    # kicad-cli only loads *.kicad_pcb
# place_tempsensor's 0.35 mm margin is 3.5x the 0.1016 mm rule. For 0402s dropped
# into a routed block that is the difference between a slot and none; 0.15 mm is
# still 1.5x the rule and DRC in place remains the authority.
P.CLR = 0.15


def anchor_xy(b, ref):
    a = design.ADJACENCY.get(ref)
    if not a:
        return None, None
    fp = b.FindFootprintByReference(a[0])
    if fp is None:
        return None, None
    pad = next((q for q in fp.Pads() if q.GetNumber() == str(a[1])), None)
    pos = (pad or fp).GetPosition()
    return (pos.x / 1e6, pos.y / 1e6), a[2]


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    b = pcbnew.LoadBoard(BOARD)
    out = b.GetBoardEdgesBoundingBox()
    X0, Y0 = out.GetLeft() / 1e6, out.GetTop() / 1e6
    W, H = out.GetWidth() / 1e6, out.GetHeight() / 1e6
    pitch = design.BOARD["MOUNT"]
    cx, cy = X0 + W / 2, Y0 + H / 2
    holes = [(cx + dx, cy + dy) for dx in (-pitch / 2, pitch / 2)
             for dy in (-pitch / 2, pitch / 2)]
    geom = (X0, Y0, W, H, holes)

    pending = [a for a in argv if not a.startswith("--")]
    # hide the parked ones from the obstacle model by moving them off-board for the
    # duration; each is moved back when it is placed (or at the end if it is not)
    parked = {}
    for ref in pending:
        fp = b.FindFootprintByReference(ref)
        if fp is None:
            print(f"  {ref}: not on the board - run sync_board.py first")
            return 1
        parked[ref] = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(int((X0 - 50) * 1e6), int((Y0 - 50) * 1e6)))

    shutil.copy(BOARD, PREV)
    before = P.drc_classes(PREV)
    placed, failed = [], []
    for ref in pending:
        a = design.ADJACENCY.get(ref)
        if a and a[0] in pending and a[0] not in placed:
            print(f"  {ref}: anchor {a[0]} is itself unplaced - skipped")
            failed.append(ref)
            continue
        axy, lim = anchor_xy(b, ref)
        if axy is None:
            print(f"  {ref}: no ADJACENCY anchor - refusing to guess where it goes")
            failed.append(ref)
            continue
        xy, d, flip = P.place(b, ref, axy, lim, geom, placed)
        if xy is None:
            # place() moves the part through every candidate and leaves it at the
            # last one on failure - which put R47 on top of Q3. Park it off-board.
            b.FindFootprintByReference(ref).SetPosition(
                pcbnew.VECTOR2I(int((X0 - 50) * 1e6), int((Y0 - 50) * 1e6)))
            print(f"  {ref}: NO legal position within {lim} mm of "
                  f"{design.ADJACENCY[ref][0]}.{design.ADJACENCY[ref][1]}")
            failed.append(ref)
            continue
        placed.append(ref)
        print(f"  {ref:5} -> ({xy[0]:.2f}, {xy[1]:.2f}) {'B.Cu' if flip else 'F.Cu'}, "
              f"{d:.2f} mm from {design.ADJACENCY[ref][0]}.{design.ADJACENCY[ref][1]} "
              f"(bound {lim} mm)")
    # failures stay OFF-BOARD, not back on their anchor: a part parked on top of an
    # op-amp's pads shorts everything, and that shorting was blamed on the parts that
    # had placed correctly. sync_board.py re-parks anything that is still off-board.

    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(BOARD)
    after = P.drc_classes(BOARD)
    hard = {k: v for k, v in after.items() if k not in ("unconnected_items",)}
    hard0 = {k: v for k, v in before.items() if k not in ("unconnected_items",)}
    worse = {k: v for k, v in hard.items() if v > hard0.get(k, 0)}
    print()
    print(f"placed {len(placed)}, failed {len(failed)}; DRC hard errors "
          f"{sum(hard0.values())} -> {sum(hard.values())}, unconnected "
          f"{before.get('unconnected_items', 0)} -> {after.get('unconnected_items', 0)}")
    if worse and "--keep" not in sys.argv:
        print(f"DRC got WORSE in: {worse} - restoring the previous board "
              f"(--keep to inspect instead)")
        shutil.move(PREV, BOARD)
        return 1
    if worse:
        print(f"DRC got WORSE in: {worse} - KEPT for inspection")
    os.remove(PREV)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
