#!/usr/bin/env python3
"""Make the routed board's PARTS, VALUES and PAD NETS match tools/design.py.

check_design.py proves the board and design.py agree. Nothing DID the agreeing: every
netlist change so far was applied to the board by hand, one part at a time, and the
one that went wrong went wrong silently - 43 parts diverged before the set comparison
existed to notice. This is the other half of that check.

What it does, in order, and reports every step:

  1. creates every net design.py names that the board lacks
  2. removes footprints design.py no longer has (their copper is left for step 6)
  3. adds footprints design.py has that the board lacks, parked at their adjacency
     anchor if they have one and at the board centre if not - PLACE THEM AFTERWARDS
  4. sets every pad's net to what design.py says, and lists each change
  5. copies values (10k -> 4k7) so the BOM and the silkscreen agree with the netlist
  6. deletes any track or via that now touches a pad on a DIFFERENT net from its own -
     the copper that a net change turns into a short. A pad that changed net keeps
     nothing that was drawn to it under the old name.
  7. renames nets given as OLD=NEW on the command line, moving every item across

It never routes. What it removes in step 6 is listed so the caller knows what to
re-route, and DRC afterwards is the authority on whether the result is sane.

    python3 tools/sync_board.py [OLDNET=NEWNET ...]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew
import design
import add_part

BOARD = "NAVCORE-SoOP.kicad_pcb"


def main(argv):
    renames = dict(a.split("=", 1) for a in argv if "=" in a)
    b = pcbnew.LoadBoard(BOARD)
    changed = []

    # 7 first: renames, so later steps see the new names
    for old, new in renames.items():
        n_old = b.FindNet(old)
        if n_old is None:
            print(f"rename {old} -> {new}: {old} not on board, nothing to move")
            continue
        n_new = b.FindNet(new) or pcbnew.NETINFO_ITEM(b, new)
        if b.FindNet(new) is None:
            b.Add(n_new)
        moved = 0
        for t in b.GetTracks():
            if t.GetNetname() == old:
                t.SetNet(n_new); moved += 1
        for fp in b.Footprints():
            for p in fp.Pads():
                if p.GetNetname() == old:
                    p.SetNet(n_new); moved += 1
        for z in b.Zones():
            if z.GetNetname() == old:
                z.SetNet(n_new); moved += 1
        print(f"rename {old} -> {new}: {moved} item(s) moved")

    # 1. nets
    for name in design.NETS:
        if b.FindNet(name) is None:
            b.Add(pcbnew.NETINFO_ITEM(b, name))
            print(f"net   + {name}")

    # 2. footprints to remove
    on_board = {fp.GetReference(): fp for fp in b.Footprints()}
    pre_existing = set(on_board)
    for ref, fp in list(on_board.items()):
        if ref not in design.COMPONENTS and not ref.startswith(("PWR", "#")):
            if fp.GetReference().startswith(("H", "FID", "LOGO")):
                continue
            b.Remove(fp)
            print(f"part  - {ref}")
            del on_board[ref]

    # 3. footprints to add
    bb = b.GetBoardEdgesBoundingBox()
    cx, cy = bb.GetCenter().x, bb.GetCenter().y
    for ref in design.COMPONENTS:
        if ref in on_board:
            continue
        if not design.COMPONENTS[ref][1]:
            continue                    # schematic-only (power flags): no footprint
        fp = add_part.load_fp(b, ref)
        b.Add(fp)                       # Flip() on a footprint not yet on a board segfaults
        anchor = design.ADJACENCY.get(ref)
        x, y = cx, cy
        if anchor and anchor[0] in on_board:
            a = on_board[anchor[0]]
            pad = next((q for q in a.Pads() if q.GetNumber() == str(anchor[1])), None)
            pos = (pad or a).GetPosition()
            x, y = pos.x, pos.y
            if a.IsFlipped() and not fp.IsFlipped():
                fp.Flip(pcbnew.VECTOR2I(0, 0), False)
        fp.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
        on_board[ref] = fp
        print(f"part  + {ref:5} parked at {x/1e6:.2f},{y/1e6:.2f} "
              f"({'near ' + anchor[0] if anchor else 'board centre'}) - UNPLACED")

    # 4. pad nets
    for ref, fp in on_board.items():
        if ref not in design.COMPONENTS:
            continue
        for p in fp.Pads():
            want = add_part._net_for(ref, p.GetNumber())
            have = p.GetNetname() or ""
            if want is None:
                if have:
                    # design.py names no net for this pad but the board has one. That
                    # is either a pad deliberately freed, or a LOOKUP FAILURE - and
                    # the first time this ran it was the latter, on U1's crystal
                    # pins, and the tool cut the oscillator tracks. It is not this
                    # tool's call: leave it and say so.
                    print(f"WARN  {ref}.{p.GetNumber():4} has net {have} but design.py "
                          f"names none - LEFT AS IS, confirm by hand")
                continue
            if have != want:
                p.SetNet(b.FindNet(want))
                changed.append((ref, p.GetNumber(), have, want, p.GetPosition()))
                print(f"pad   {ref}.{p.GetNumber():4} {have or '(none)'} -> {want}")

    # 5. values
    for ref, fp in on_board.items():
        c = design.COMPONENTS.get(ref)
        if c and fp.GetValue() != c[2]:
            print(f"value {ref:5} {fp.GetValue()} -> {c[2]}")
            fp.SetValue(c[2])

    # 6. copper that a net change turned into a short
    removed = 0
    if changed:
        # Only pads that were ALREADY on the board can have copper drawn to them. A
        # freshly parked part sits on top of whatever was there, and the first run of
        # this cut a motor track and two ADC tracks for being under a parked resistor.
        # And only copper that ENDS INSIDE the pad counts - proximity is not connection.
        pads = []
        for ref, num, _h, want, pos in changed:
            if ref not in pre_existing:
                continue
            fp = on_board[ref]
            pad = next(q for q in fp.Pads() if q.GetNumber() == num)
            layers = set(pad.GetLayerSet().CuStack())
            pads.append((ref, num, want, pad.GetBoundingBox(), layers))
        for t in list(b.GetTracks()):
            tn = t.GetNetname()
            hit = None
            is_via = t.Type() == pcbnew.PCB_VIA_T
            for ref, num, want, box, layers in pads:
                if tn == want:
                    continue
                # a track on In2 passing under an F.Cu pad touches nothing; a through
                # via is copper on every layer and does. The second run of this cut
                # two motor tracks and two IOUT_N tracks that merely crossed beneath.
                if not is_via and t.GetLayer() not in layers:
                    continue
                pts = [t.GetStart()] if is_via else [t.GetStart(), t.GetEnd()]
                if any(box.Contains(q) for q in pts):
                    hit = (ref, num, want)
                    break
            if hit:
                kind = "via" if t.Type() == pcbnew.PCB_VIA_T else "track"
                print(f"cut   {kind} [{tn}] at {hit[0]}.{hit[1]} (pad is now {hit[2]})")
                b.Remove(t)
                removed += 1

    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(BOARD)
    print(f"\nsaved: {len(changed)} pad net change(s), {removed} copper item(s) cut")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
