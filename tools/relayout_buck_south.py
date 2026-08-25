#!/usr/bin/env python3
"""
Re-plan the whole area south of the 5 V buck, as one job.

C25's floating ground could not be fixed on its own, and the reason turned out to be
structural rather than local. Searching with copper properly accounted for, R8, C24 and
C25 each had 4, 6 and 6 valid positions and EVERY ONE was the same small pocket at
~(130.8, 107.8) - one part's worth of space for three parts.

Four functional groups compete for that pocket:

    compensation   R8, C24, C25      COMP pin, U8.6
    FB divider     R6, R7            FB pin,   U8.5
    +5 V output    C22, C23          L2's output
    the inductor   L2                PH pin,   U8.8  (already fixed, stays put)

Any one of them can be placed well. Not all four, while the copper that serves them is
already in the way. So the copper for those nets is ripped FIRST, the parts are placed
into the space that frees, and everything is routed afterwards.

Placement rules, in priority order:
  * every GND pad must have a legal position for a ground via - that is the defect being
    fixed, and a part that cannot be grounded has not been placed;
  * each part within its design.ADJACENCY limit of its pin where possible, and as close
    as the space allows otherwise;
  * pads checked against real copper, not just other footprints' courtyards. Checking
    courtyards alone put R8's BUCK_COMP pad on top of a +5V via.

Usage: python3 tools/relayout_buck_south.py [--apply]
"""
import os, sys, math, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = 'NAVCORE-SoOP.kicad_pcb'
CLR, HOLE = 0.1016, 0.20
VIA_R, DRILL_R = 0.225, 0.10          # 0.45 mm via, the board's minimum
REGION = (126.5, 136.5, 103.5, 112.5)  # the area being re-planned
MOVE = ['R8', 'C24', 'C25', 'R6', 'R7']
RIP_NETS = {'BUCK_COMP', 'BUCK_COMP2', 'BUCK_FB'}


def segd(px, py, x1, y1, x2, y2):
    dx, dy = x2-x1, y2-y1
    L2 = dx*dx + dy*dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy)/L2))
    return math.hypot(px-(x1+u*dx), py-(y1+u*dy))


def courtyard(f):
    lay = pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd
    xs, ys = [], []
    for d in f.GraphicalItems():
        if d.GetLayer() != lay: continue
        bb = d.GetBoundingBox()
        xs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
        ys += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
    if not xs:
        for p in f.Pads():
            bb = p.GetBoundingBox()
            xs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
            ys += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
    return [min(xs), max(xs), min(ys), max(ys)]


def main():
    apply = '--apply' in sys.argv
    keep = []
    b = pcbnew.LoadBoard(BOARD)

    # 1 - rip the copper that competes for the space
    def inregion(x, y):
        return REGION[0] <= x <= REGION[1] and REGION[2] <= y <= REGION[3]
    todo = []
    for t in list(b.GetTracks()):
        n = t.GetNetname()
        if n in RIP_NETS:
            todo.append(t); continue
        if n in ('+5V', 'GND'):
            if t.Type() == pcbnew.PCB_VIA_T:
                if inregion(t.GetStart().x/1e6, t.GetStart().y/1e6): todo.append(t)
            elif (inregion(t.GetStart().x/1e6, t.GetStart().y/1e6)
                  and inregion(t.GetEnd().x/1e6, t.GetEnd().y/1e6)):
                todo.append(t)
    for t in todo:
        b.Remove(t); keep.append(t)
    print(f"  ripped {len(todo)} objects on BUCK_COMP/BUCK_COMP2/BUCK_FB and local +5V/GND")

    # 2 - build the obstacle set from what is LEFT
    obs, holes = [], []
    for t in b.GetTracks():
        n = t.GetNetname()
        if t.Type() == pcbnew.PCB_VIA_T:
            obs.append(('c', t.GetStart().x/1e6, t.GetStart().y/1e6, t.GetWidth()/2e6, n))
            holes.append((t.GetStart().x/1e6, t.GetStart().y/1e6, t.GetDrill()/2e6))
        else:
            obs.append(('s', t.GetStart().x/1e6, t.GetStart().y/1e6,
                        t.GetEnd().x/1e6, t.GetEnd().y/1e6, t.GetWidth()/2e6, n))
    for p in b.GetPads():
        if p.GetParentFootprint().GetReference() in MOVE: continue
        bb = p.GetBoundingBox(); hr = p.GetDrillSizeX()/2e6
        obs.append(('r', bb.GetLeft()/1e6, bb.GetRight()/1e6,
                    bb.GetTop()/1e6, bb.GetBottom()/1e6, p.GetNetname()))
        if hr > 0:
            holes.append(((bb.GetLeft()+bb.GetRight())/2e6,
                          (bb.GetTop()+bb.GetBottom())/2e6, hr))
    others = [courtyard(f) for f in b.GetFootprints()
              if f.IsFlipped() and f.GetReference() not in MOVE]

    def viafits(x, y):
        for o in obs:
            if o[-1] == 'GND': continue
            if o[0] == 'c':
                if math.hypot(o[1]-x, o[2]-y) < VIA_R+CLR+o[3]: return False
            elif o[0] == 's':
                if segd(x, y, o[1], o[2], o[3], o[4]) < VIA_R+CLR+o[5]: return False
            else:
                if math.hypot(max(o[1]-x, 0, x-o[2]), max(o[3]-y, 0, y-o[4])) < VIA_R+CLR:
                    return False
        for hx, hy, hr in holes:
            if math.hypot(hx-x, hy-y) < DRILL_R+HOLE+hr: return False
        return True

    geom = {}
    for ref in MOVE:
        f = b.FindFootprintByReference(ref)
        c = courtyard(f)
        fx, fy = f.GetPosition().x/1e6, f.GetPosition().y/1e6
        geom[ref] = dict(w=c[1]-c[0], h=c[3]-c[2],
                         pads=[(p.GetPosition().x/1e6-fx, p.GetPosition().y/1e6-fy,
                                p.GetSizeX()/1e6, p.GetSizeY()/1e6, p.GetNetname())
                               for p in f.Pads()])

    def pads_clear(ref, gx, gy):
        for dx, dy, pw, ph, pnet in geom[ref]['pads']:
            px, py = gx+dx, gy+dy
            hw, hh = pw/2, ph/2
            for o in obs:
                if o[-1] == pnet: continue
                if o[0] == 'c':
                    if math.hypot(max(px-hw-o[1], 0, o[1]-px-hw),
                                  max(py-hh-o[2], 0, o[2]-py-hh)) < CLR+o[3]: return False
                elif o[0] == 's':
                    if min(segd(px+sx*hw, py+sy*hh, o[1], o[2], o[3], o[4])
                           for sx in (-1, 1) for sy in (-1, 1)) < CLR+o[5]: return False
                else:
                    if (o[2] > px-hw-CLR and o[1] < px+hw+CLR
                            and o[4] > py-hh-CLR and o[3] < py+hh+CLR): return False
            for hx, hy, hr in holes:
                if math.hypot(max(px-hw-hx, 0, hx-px-hw),
                              max(py-hh-hy, 0, hy-py-hh)) < HOLE+hr: return False
        return True

    def boxfree(gx, gy, w, h):
        l, r, t, bm = gx-w/2-CLR, gx+w/2+CLR, gy-h/2-CLR, gy+h/2+CLR
        return not any(orr > l and ol < r and obm > t and ot < bm
                       for ol, orr, ot, obm in others)

    u8 = b.FindFootprintByReference('U8')
    pin = {p.GetPadName(): (p.GetPosition().x/1e6, p.GetPosition().y/1e6) for p in u8.Pads()}
    TARGET = {'R8': pin['6'], 'C24': pin['6'], 'C25': pin['6'],
              'R6': pin['5'], 'R7': pin['5']}

    cands = {}
    for ref in MOVE:
        g = geom[ref]
        gnd = [(dx, dy) for dx, dy, _w, _h, n in g['pads'] if n == 'GND']
        out = []
        tx, ty = TARGET[ref]
        for j in range(-45, 46):
            for i in range(-55, 56):
                gx, gy = tx+i*0.1, ty+j*0.1
                if not (REGION[0] < gx < REGION[1] and REGION[2] < gy < REGION[3]): continue
                d = math.hypot(gx-tx, gy-ty)
                if d > 5.0: continue
                if not boxfree(gx, gy, g['w'], g['h']): continue
                if not pads_clear(ref, gx, gy): continue
                via = None
                if gnd:
                    vx, vy = gx+gnd[0][0], gy+gnd[0][1]
                    if not viafits(vx, vy): continue
                    via = (round(vx, 2), round(vy, 2))
                out.append((round(d, 2), round(gx, 2), round(gy, 2), via))
        out.sort()
        seen, spread = set(), []
        for c in out:
            k = (round(c[1]*3)/3, round(c[2]*3)/3)
            if k in seen: continue
            seen.add(k); spread.append(c)
        cands[ref] = spread
        print(f"  {ref:4s}: {len(out)} position(s), {len(spread)} distinct")
    if any(not cands[r] for r in MOVE):
        print("  a part has nowhere to go"); os._exit(1)

    # 3 - choose a non-overlapping set, cheapest total distance
    # Cost a position by how far it EXCEEDS its own limit, not by raw distance. Plain
    # distance-minimising traded R7 from 0.70 mm out to 2.83 mm - over its limit - to buy
    # a fraction of a millimetre for parts that were already inside theirs. Being inside
    # the limit is the thing that matters; beyond that, closer is only a tie-break.
    LIMIT = {r: (design.ADJACENCY.get(r) or (None, None, 3.0))[2] for r in MOVE}

    def cost_of(ref, c):
        over = max(0.0, c[0] - LIMIT[ref])
        return over * 100.0 + c[0] * 0.01

    for r in MOVE:
        cands[r].sort(key=lambda c: cost_of(r, c))
    order = sorted(MOVE, key=lambda r: len(cands[r]))
    best = {}
    def fits(ref, c, chosen):
        for oref, oc in chosen.items():
            if (abs(c[1]-oc[1]) < (geom[ref]['w']+geom[oref]['w'])/2 + CLR and
                    abs(c[2]-oc[2]) < (geom[ref]['h']+geom[oref]['h'])/2 + CLR): return False
            if c[3] and oc[3] and math.hypot(c[3][0]-oc[3][0], c[3][1]-oc[3][1]) < 2*VIA_R+CLR:
                return False
        return True
    def search(k, chosen, cost, bestbox):
        if k == len(order):
            if bestbox[0] is None or cost < bestbox[1]:
                bestbox[0] = dict(chosen); bestbox[1] = cost
            return
        ref = order[k]
        for c in cands[ref][:60]:
            if bestbox[0] is not None and cost + cost_of(ref, c) >= bestbox[1]: break
            if not fits(ref, c, chosen): continue
            chosen[ref] = c
            search(k+1, chosen, cost+cost_of(ref, c), bestbox)
            del chosen[ref]
    box = [None, 1e9]
    search(0, {}, 0.0, box)
    if box[0] is None:
        print("  no non-overlapping arrangement"); os._exit(1)
    print("\n  arrangement:")
    for ref in MOVE:
        c = box[0][ref]
        cur = b.FindFootprintByReference(ref)
        was = math.hypot(cur.GetPosition().x/1e6-TARGET[ref][0],
                         cur.GetPosition().y/1e6-TARGET[ref][1])
        lim = design.ADJACENCY.get(ref, (None, None, None))[2]
        flag = 'ok' if (lim and c[0] <= lim) else (f'over {lim}' if lim else '')
        print(f"    {ref:4s} -> ({c[1]:6.2f},{c[2]:6.2f})  {c[0]:.2f} mm from its pin "
              f"(was {was:.2f}, limit {lim})  {flag}"
              + (f"  GND via {c[3]}" if c[3] else ""))

    if not apply:
        print("\n  (dry run)"); sys.stdout.flush(); os._exit(0)

    gnd = b.GetNetInfo().GetNetItem('GND')
    for ref in MOVE:
        c = box[0][ref]
        f = b.FindFootprintByReference(ref)
        f.SetPosition(pcbnew.VECTOR2I(int(c[1]*1e6), int(c[2]*1e6)))
        if c[3]:
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pcbnew.VECTOR2I(int(c[3][0]*1e6), int(c[3][1]*1e6)))
            v.SetWidth(450000); v.SetDrill(200000)
            v.SetLayerPair(b.GetLayerID('F.Cu'), b.GetLayerID('B.Cu'))
            v.SetNet(gnd); b.Add(v)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(BOARD)
    print("\n  applied and saved")
    sys.stdout.flush(); os._exit(0)


main()
