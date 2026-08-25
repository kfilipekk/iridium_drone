#!/usr/bin/env python3
"""
Convert the board from 4 to 6 copper layers.

Layer COUNT was never the whole problem - layer ORDER matters as much. The stackup is:

    F.Cu    signal      referenced by In1 GND directly beneath it
    In1.Cu  GND plane   solid, untouched - the return path for the fast nets
    In2.Cu  signal
    In3.Cu  signal
    In4.Cu  power       split per-rail islands, the reference for B.Cu
    B.Cu    signal

That gives four signal layers instead of two, which is the actual constraint: U1 is a
100-pin 0.5 mm pitch package and no trace can pass between its pads at any purchasable
rule (0.200 mm gap against 0.3048 mm needed), so every pin escapes outward to a via -
and with only two layers the inner pins had nowhere to go.

In2 and In3 are adjacent signal layers with no plane between them, which is the one
compromise here. Freerouting prefers orthogonal directions per layer, which keeps
broadside coupling between them low; the alternative stackup that avoids it entirely
(SIG/GND/SIG/PWR/GND/SIG) buys only one extra signal layer instead of two.

Usage:  python3 tools/to_6layer.py <board.kicad_pcb> [--apply]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

PWR_FROM = "In2.Cu"      # where the power pours live on the 4-layer board
PWR_TO   = "In4.Cu"      # where they belong once In2/In3 become signal layers


def main():
    path = sys.argv[1]
    apply = "--apply" in sys.argv
    board = pcbnew.LoadBoard(path)

    board.SetCopperLayerCount(6)
    print(f"copper layers -> {board.GetCopperLayerCount()}")

    src = board.GetLayerID(PWR_FROM)
    dst = board.GetLayerID(PWR_TO)
    moved = kept = 0
    for z in board.Zones():
        ls = z.GetLayerSet()
        layers = list(ls.CuStack())
        if src not in layers:
            kept += 1
            continue
        if z.GetNetname() in ("", "GND"):
            # keepout rule areas and the GND pour stay where they are
            kept += 1
            continue
        new = pcbnew.LSET()
        for li in layers:
            new.addLayer(dst if li == src else li)
        z.SetLayerSet(new)
        moved += 1
        print(f"   {z.GetNetname():8} pour {PWR_FROM} -> {PWR_TO}")

    print(f"moved {moved} power pours, left {kept} zones alone")
    if not apply:
        print("dry run - pass --apply to write")
        return 0
    board.Save(path)
    print(f"saved {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
