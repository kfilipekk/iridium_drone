#!/usr/bin/env python3
"""Replace a part's FOOTPRINT in place, on a board that is already routed and placed.

WHY THIS EXISTS - AND IT IS A LESSON, NOT A CONVENIENCE.

Swapping both bucks from TPS54331 (SOIC-8) to TPS54202 (SOT-23-6) was first attempted by
editing design.py and re-running gen_pcb.py. That works, and it is the wrong move: gen_pcb
rebuilds PLACEMENT from scratch, and from-scratch placement is far worse than the placement
this board had accumulated by hand over many sessions. Measured, rebuilt vs the board it
replaced:

    crystal to U1.12      4.43 mm  ->  15.70 mm     (HSE integrity, and OSC traces went
                                                     27.6 / 25.4 mm, both over limit)
    copper under a screw  clear    ->  C73 at 2.65 mm against a 2.75 mm cap head
    CPL rotations         consistent -> FAIL
    unconnected           0 of 472 ->  226
    preflight             READY TO ORDER -> NOT READY, 7 blocking

None of that damage was to the bucks. It was collateral, and repairing it is the hand
tuning that produced the good board in the first place.

THE RULE THIS ENCODES: on a placed and routed board, MODIFY IN PLACE. Never regenerate.
tools/add_part.py already said so for additions; this says it for substitutions.

The blast radius here is bounded and measurable: 181 tracks and 22 vias sit on buck-only
nets, out of 8732 tracks on the board. Two percent. Everything else - crystal, MCU, USB,
microSD, both IMUs - is never touched.

    swap_footprint.py <REF> [<REF> ...]     footprint from design.COMPONENTS
    swap_footprint.py --check               report what would change

Pads are re-netted from design.NETS by pad NUMBER, which is the whole hazard of a
substitution: TPS54331 is 1 BOOT / 2 VIN / 3 EN / 4 SS / 5 VSENSE / 6 COMP / 7 GND / 8 PH
and TPS54202 is 1 GND / 2 SW / 3 VIN / 4 FB / 5 EN / 6 BOOT. Every number means something
different. design.py is the source of truth for the new mapping; this only makes the board
agree with it.
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design
import fplib

BOARD = os.path.join(os.path.dirname(HERE), "NAVCORE-SoOP.kicad_pcb")
TOMM = lambda v: v / 1e6


def pad_nets(ref):
    """{pad number: net name} for `ref`, from design.NETS."""
    out = {}
    for net, nodes in design.NETS.items():
        for n in nodes:
            if "." not in n:
                continue
            r, p = n.split(".", 1)
            if r == ref:
                out[p] = net
    return out


def main():
    check = "--check" in sys.argv
    refs = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not refs:
        print(__doc__)
        return 2

    board = pcbnew.LoadBoard(BOARD)
    changed = 0
    for ref in refs:
        old = board.FindFootprintByReference(ref)
        if old is None:
            print(f"  {ref}: not on the board")
            continue
        lib_id, fpid, val, lcsc, dnp = design.COMPONENTS[ref]
        cur = str(old.GetFPID().GetLibItemName())
        want = fpid.split(":", 1)[-1]
        if cur == want:
            print(f"  {ref}: already {want}")
            continue
        pos, rot, flipped = old.GetPosition(), old.GetOrientation(), old.IsFlipped()
        print(f"  {ref}: {cur}  ->  {want}"
              f"   at ({TOMM(pos.x):.3f},{TOMM(pos.y):.3f})"
              f" rot {old.GetOrientationDegrees():.0f}{' FLIPPED' if flipped else ''}")
        if check:
            continue

        path = fplib.find(fpid)
        new = pcbnew.FootprintLoad(os.path.dirname(path),
                                   os.path.basename(path)[:-len(".kicad_mod")])
        if new is None:
            raise SystemExit(f"could not load {fpid}")
        new.SetReference(ref)
        new.SetValue(val)
        board.Remove(old)
        board.Add(new)
        new.SetPosition(pos)
        if flipped:
            new.Flip(pos, False)
        new.SetOrientation(rot)

        want_nets = pad_nets(ref)
        for pad in new.Pads():
            num = pad.GetNumber()
            nm = want_nets.get(num)
            if nm is None:
                continue
            net = board.FindNet(nm)
            if net is None:
                net = pcbnew.NETINFO_ITEM(board, nm)
                board.Add(net)
            pad.SetNet(net)
            print(f"      pad {num:>3} -> {nm}")
        changed += 1

    if check:
        print("\n--check: nothing written")
        return 0
    if changed:
        board.Save(BOARD)
        print(f"\nswapped {changed} footprint(s); board saved. "
              f"Re-route the affected nets and run DRC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
