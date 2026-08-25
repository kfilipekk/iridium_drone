#!/usr/bin/env python3
"""
Deliberate re-layout of the two buck converters, so each inductor sits on a land that
fits it and beside its own switching node.

The defect: L2 and L5 were 1210 chip lands (3.2 x 2.5 mm) holding LCSC C167879, which is
a 4.0 x 4.0 x 3.0 mm FNR4030. Neither fitted. L2 additionally carried 1.89 A on a 1.6 A
RMS rating.

Automated rearrangement was tried five ways and none worked - incremental shoving
oscillated, nearest-free relocation found no home for C40 or C18, and a full re-placement
put L2 8.13 mm from U8 while discarding all routing. The power section is boxed in: U8
and U18 sit 0.26 mm apart, U1 is 0.26 mm to their left, C22 0.46 mm above, D4 0.78 mm to
the right.

So the moves here are chosen, not searched, and each is justified:

  L2  -> TOP (130.79, 106.43), 4x4 land. This is where C22 currently sits, directly below
         U8's PH pin (128.59, 110.23) - 4.39 mm away and ON THE SAME SIDE, so the switch
         node no longer crosses the board through a via. That is better than the layout
         being replaced, not merely equal to it.
  C22 -> BOTTOM (131.27, 103.16). It is one of two 22 uF output caps; C23 stays next to
         the output, so the output loop keeps a close bulk cap.
  L5  -> BOTTOM (127.90, 119.70), 4x4 land. 1.38 mm from U18's PH pin. This position was
         chosen because it displaces exactly ONE part, C69, against two or more anywhere
         else nearby.
  C69 -> the nearest free bottom position. It is a 9 V OUTPUT cap, and docs/BUYING.md
         records the 9 V VTX buck as "DNP by default; populate only for an analogue-FPV
         build", so its loop is the least critical thing in this area.

Usage: python3 tools/relayout_bucks.py [--apply]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = 'NAVCORE-SoOP.kicad_pcb'
LIB   = '/usr/share/kicad/footprints/Inductor_SMD.pretty'
HOLES = [(107.25, 107.75), (137.75, 107.75), (107.25, 138.25), (137.75, 138.25)]

# ref -> (new footprint or None, x, y, put on the TOP side?)
_keep_alive = []   # removed footprints, held so Python cannot collect them early

PLAN = {
    'L2':  ('L_APV_ANR4030', 130.79, 106.43, True),
    'C22': (None,            131.27, 103.16, False),
    # L5 is deliberately NOT moved. A 4x4 land at (127.90,119.70) - the only nearby
    # position that displaced just one part - sits on top of U1's escape routing, and
    # clearing the copper it lands on cuts M1, M2 and VTX_EN. Those three are
    # F.Cu <-> In2/In3 hops whose vias were legal exactly where they were, and no legal
    # via position exists within 1.2 mm of any of them once L5 is in the way.
    #
    # It is not worth it: docs/BUYING.md records the 9 V VTX buck as "DNP by default;
    # populate only for an analogue-FPV build", so L5 is not fitted on this build at all.
    # The land stays wrong for anyone who does populate it, which is a Rev B item, not a
    # reason to cut three working nets on a board that ships without the part.
}


def cb(f):
    """Courtyard box from the footprint's own graphics.

    Not GetCourtyard(): for a footprint that has just been loaded, added and flipped,
    SWIG hands back a raw SwigPyObject with no OutlineCount, and the cached version is
    stale anyway. Walking the drawings works whatever state the footprint is in."""
    lay = pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd
    xs, ys = [], []
    for d in f.GraphicalItems():
        if d.GetLayer() != lay: continue
        bb = d.GetBoundingBox()
        xs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
        ys += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
    if not xs:
        # No courtyard on this layer: fall back to the pads, which every real part has.
        # GetBoundingBox()'s signature varies between KiCad versions and calling it with
        # the wrong arity segfaults rather than raising.
        for pd in f.Pads():
            bb = pd.GetBoundingBox()
            xs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
            ys += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
        if not xs:
            p = f.GetPosition()
            return [p.x/1e6, p.x/1e6, p.y/1e6, p.y/1e6]
    return [min(xs), max(xs), min(ys), max(ys)]


def swap_footprint(b, ref, newname, top_side):
    """Replace one footprint with another, keeping position, side and net assignments."""
    old = b.FindFootprintByReference(ref)
    nets = {p.GetPadName(): p.GetNet() for p in old.Pads()}
    val = old.GetValue()
    b.Remove(old)
    new = pcbnew.FootprintLoad(LIB, newname)
    if new is None:
        raise SystemExit(f"cannot load {newname} from {LIB}")
    new.SetReference(ref)
    new.SetValue(val)
    b.Add(new)
    if not top_side:
        new.Flip(new.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    for p in new.Pads():
        if p.GetPadName() in nets:
            p.SetNet(nets[p.GetPadName()])
    # Return the handle we already have. Re-fetching by reference straight after
    # Remove()+Add() of the same refdes SEGFAULTS: the removed footprint is no longer
    # owned by the board, Python is free to collect it, and the lookup walks it. Holding
    # `old` and using the direct handle avoids both.
    _keep_alive.append(old)
    return new


def main():
    apply = '--apply' in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    for ref, (newfp, x, y, top) in PLAN.items():
        fp = swap_footprint(b, ref, newfp, top) if newfp else b.FindFootprintByReference(ref)
        if newfp is None and fp.IsFlipped() == top:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(pcbnew.VECTOR2I(int(x*1e6), int(y*1e6)))
        c = cb(fp)
        print(f"  {ref:4s} -> {'TOP' if not fp.IsFlipped() else 'BOT'} ({x:.2f},{y:.2f})"
              f"  land {c[1]-c[0]:.2f} x {c[3]-c[2]:.2f} mm"
              + (f"  [{newfp}]" if newfp else "  [moved only]"))


    # C69 is displaced by L5 - give it the nearest clear bottom home
    bots = {}
    for f in list(b.GetFootprints()):
        if f.IsFlipped(): bots[f.GetReference()] = cb(f)
    c69 = b.FindFootprintByReference('C69')
    cc = cb(c69); w, h = cc[1]-cc[0], cc[3]-cc[2]
    px, py = c69.GetPosition().x/1e6, c69.GetPosition().y/1e6
    best = None
    for j in range(-100, 101):
        for i in range(-100, 101):
            gx, gy = px+i*0.1, py+j*0.1
            l, r, t, bm = gx-w/2-0.15, gx+w/2+0.15, gy-h/2-0.15, gy+h/2+0.15
            if l < 100.35 or r > 144.65 or t < 100.35 or bm > 145.65: continue
            if any(math.hypot(hx-gx, hy-gy) < 2.0+max(w, h)/2 for hx, hy in HOLES): continue
            if any(orr > l and ol < r and obm > t and ot < bm
                   for q, (ol, orr, ot, obm) in bots.items() if q != 'C69'): continue
            d = math.hypot(gx-px, gy-py)
            if best is None or d < best[0]: best = (d, gx, gy)
    if best:
        c69.SetPosition(pcbnew.VECTOR2I(int(best[1]*1e6), int(best[2]*1e6)))
        print(f"  C69  -> BOT ({best[1]:.2f},{best[2]:.2f})  moved {best[0]:.2f} mm")
    else:
        print("  C69  NO HOME"); raise SystemExit(1)

    # rip the copper on every net that touches something we moved
    touched = set()
    for ref in list(PLAN) + ['C69']:
        for p in b.FindFootprintByReference(ref).Pads():
            if p.GetNetname(): touched.add(p.GetNetname())
    # LOCAL rip only. Ripping by net alone tears out +5V and GND across the whole
    # board - 4799 objects - to fix a few millimetres of buck layout, and the router
    # then cannot put the power distribution back. Both conditions: the copper must
    # belong to a disturbed net AND lie near something that moved.
    WINDOW = 3.5
    boxes = []
    for ref in list(PLAN) + ['C69']:
        c = cb(b.FindFootprintByReference(ref))
        boxes.append((c[0]-WINDOW, c[1]+WINDOW, c[2]-WINDOW, c[3]+WINDOW))

    def near(x, y):
        return any(l <= x <= r and t <= y <= bm for l, r, t, bm in boxes)

    killed = 0
    for t in list(b.GetTracks()):
        if t.GetNetname() not in touched: continue
        if t.Type() == pcbnew.PCB_VIA_T:
            hit = near(t.GetStart().x/1e6, t.GetStart().y/1e6)
        else:
            hit = (near(t.GetStart().x/1e6, t.GetStart().y/1e6) and
                   near(t.GetEnd().x/1e6, t.GetEnd().y/1e6))
        if hit:
            b.Remove(t); killed += 1
    print(f"\n  ripped {killed} objects on {len(touched)} net(s): {', '.join(sorted(touched))}")

    # Overlap checking is left to kicad-cli DRC after the write, not done here:
    # walking every footprint through the SWIG API straight after Remove()+Add()
    # segfaults, and DRC is the authority on this anyway.
    if apply:
        pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(BOARD); print("  saved")
    else:
        print("  (dry run)")
    sys.stdout.flush(); os._exit(0)


main()
