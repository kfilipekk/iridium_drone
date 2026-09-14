#!/usr/bin/env python3
"""
Rev B step 1 -- reuse the hand-tuned placement.

The committed board (git HEAD) carries a placement that satisfies all 70 ADJACENCY
rules, connector facing, mounting clearances and the signal-span budget: it passed
the whole gate. gen_pcb.py rebuilds placement from zones and lands 27 adjacency
violations - the packer has no memory of why the bucks sit where they sit.

134 of the committed board's footprints are still in the current design at the same
footprint, so their POSITIONS are still valid even though every trace on the board
is about to be rebuilt. This script copies position, rotation and side from the
committed board onto the regenerated one, for every reference present in both.
It reports what it could not place rather than guessing.

Usage: python3 tools/revb_transplant.py [old_board] [new_board]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

OLD = sys.argv[1] if len(sys.argv) > 1 else ".scratch/old_head_board.kicad_pcb"
NEW = sys.argv[2] if len(sys.argv) > 2 else "NAVCORE-SoOP.kicad_pcb"

old_b = pcbnew.LoadBoard(OLD)
new_b = pcbnew.LoadBoard(NEW)

def ref_map(b):
    return {fp.GetReference(): fp for fp in b.GetFootprints()}

old_fp, new_fp = ref_map(old_b), ref_map(new_b)
shared = sorted(set(old_fp) & set(new_fp))
moved = 0
for ref in shared:
    o, n = old_fp[ref], new_fp[ref]
    n.SetPosition(o.GetPosition())
    n.SetOrientation(o.GetOrientation())
    o_front = o.GetLayer() == pcbnew.F_Cu
    n_front = n.GetLayer() == pcbnew.F_Cu
    if o_front != n_front:
        n.Flip(n.GetPosition(), False)
    moved += 1

only_old = sorted(set(old_fp) - set(new_fp))
only_new = sorted(set(new_fp) - set(old_fp))
print(f"transplanted {moved} placements from {OLD}")
print(f"on old board only (deleted from design, will not exist on new board): {only_old}")
print(f"on new board only (new parts, keep generator placement): {only_new}")
print(f"never placed (must be added by hand): see gen_pcb log / UNPLACED")

new_b.Save(NEW)
print(f"saved {NEW}")
