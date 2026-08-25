#!/usr/bin/env python3
"""
Nudge overlapping-courtyard footprints apart, in place, without touching routing.

Runs on the existing NAVCORE-SoOP.kicad_pcb rather than regenerating it, so the copper
already laid down survives. Only moves footprints that have no tracks attached; anything
already routed is left alone and reported instead.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD = "NAVCORE-SoOP.kicad_pcb"
TOMM, MM = pcbnew.ToMM, pcbnew.FromMM
import design
X0, Y0, W, H, R = (design.BOARD["X0"], design.BOARD["Y0"], design.BOARD["W"],
                   design.BOARD["H"], design.BOARD["R"])
MOUNT, HOLE_D = design.BOARD["MOUNT"], design.BOARD["HOLE_D"]
CX, CY = X0 + W/2, Y0 + H/2
HOLES = [(CX+dx, CY+dy) for dx in (-MOUNT/2, MOUNT/2) for dy in (-MOUNT/2, MOUNT/2)]


def crt(fp):
    lay = pcbnew.B_CrtYd if fp.GetLayerName() == "B.Cu" else pcbnew.F_CrtYd
    po = fp.GetCourtyard(lay)
    if not po.OutlineCount(): return None
    bb = po.BBox()
    return (TOMM(bb.GetLeft()), TOMM(bb.GetTop()), TOMM(bb.GetRight()), TOMM(bb.GetBottom()))


def overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0]
                or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def inside(box, margin=0.3):
    for x in (box[0], box[2]):
        for y in (box[1], box[3]):
            if not (X0+margin <= x <= X0+W-margin and Y0+margin <= y <= Y0+H-margin):
                return False
            for cx, cy in ((X0+R, Y0+R), (X0+W-R, Y0+R), (X0+R, Y0+H-R), (X0+W-R, Y0+H-R)):
                ox = x < X0+R if cx < CX else x > X0+W-R
                oy = y < Y0+R if cy < CY else y > Y0+H-R
                if ox and oy and math.hypot(x-cx, y-cy) > R - margin:
                    return False
    for hx, hy in HOLES:
        if overlap(box, (hx-HOLE_D/2, hy-HOLE_D/2, hx+HOLE_D/2, hy+HOLE_D/2), 0.2):
            return False
    return True


def copper_boxes(b, layername):
    """Bounding boxes of tracks and vias on a layer - a moved part must miss these too."""
    out = []
    lid = b.GetLayerID(layername)
    for t in b.GetTracks():
        p = t.GetPosition()
        if t.Type() == pcbnew.PCB_VIA_T:
            x, y = TOMM(p.x), TOMM(p.y)
            out.append((x-0.45, y-0.45, x+0.45, y+0.45))
        elif t.GetLayer() == lid:
            a, c = t.GetStart(), t.GetEnd()
            ax, ay, cx_, cy_ = TOMM(a.x), TOMM(a.y), TOMM(c.x), TOMM(c.y)
            out.append((min(ax,cx_)-0.25, min(ay,cy_)-0.25,
                        max(ax,cx_)+0.25, max(ay,cy_)+0.25))
    return out


def _hits(t, box, b, side):
    p = t.GetPosition()
    if t.Type() == pcbnew.PCB_VIA_T:
        x, y = TOMM(p.x), TOMM(p.y)
        return overlap(box, (x-0.45, y-0.45, x+0.45, y+0.45))
    if t.GetLayer() != b.GetLayerID(side): return False
    a, c = t.GetStart(), t.GetEnd()
    ax, ay, cx_, cy_ = TOMM(a.x), TOMM(a.y), TOMM(c.x), TOMM(c.y)
    return overlap(box, (min(ax,cx_)-0.25, min(ay,cy_)-0.25,
                         max(ax,cx_)+0.25, max(ay,cy_)+0.25))


def main():
    b = pcbnew.LoadBoard(BOARD)
    fps = [f for f in b.GetFootprints()]
    boxes = {f.GetReference(): crt(f) for f in fps}

    # which footprints already have copper attached?
    routed = set()
    codes = {}
    for f in fps:
        for p in f.Pads():
            if p.GetNet() and p.GetNet().GetNetCode():
                codes.setdefault(p.GetNet().GetNetCode(), []).append(f.GetReference())
    live = {t.GetNet().GetNetCode() for t in b.GetTracks() if t.GetNet()}
    for c in live:
        routed.update(codes.get(c, []))

    copper = {ln: copper_boxes(b, ln) for ln in ("F.Cu", "B.Cu")}

    pairs = []
    for i, f1 in enumerate(fps):
        b1 = boxes[f1.GetReference()]
        if not b1: continue
        for f2 in fps[i+1:]:
            if f1.GetLayerName() != f2.GetLayerName(): continue
            b2 = boxes[f2.GetReference()]
            if b2 and overlap(b1, b2):
                pairs.append((f1, f2))

    print(f"courtyard overlaps found: {len(pairs)}")
    fixed = stuck = 0
    for f1, f2 in pairs:
        area = lambda bx: (bx[2]-bx[0]) * (bx[3]-bx[1])
        mover = f1 if area(boxes[f1.GetReference()]) < area(boxes[f2.GetReference()]) else f2
        other = f2 if mover is f1 else f1
        ref = mover.GetReference()
        if ref in routed:
            print(f"  {ref} overlaps {other.GetReference()} - already routed, left alone")
            stuck += 1; continue
        box = boxes[ref]
        w, h = box[2]-box[0], box[3]-box[1]
        p0 = mover.GetPosition()
        placed = False
        # spiral outward on a 0.25 mm grid
        for rad in [0.2*k for k in range(1, 60)]:
            for ang in range(0, 360, 10):
                dx = rad*math.cos(math.radians(ang)); dy = rad*math.sin(math.radians(ang))
                nb = (box[0]+dx, box[1]+dy, box[2]+dx, box[3]+dy)
                if not inside(nb): continue
                clash = False
                for f3 in fps:
                    if f3 is mover or f3.GetLayerName() != mover.GetLayerName(): continue
                    b3 = boxes[f3.GetReference()]
                    if b3 and overlap(nb, b3): clash = True; break
                if clash: continue
                if any(overlap(nb, cb) for cb in copper[mover.GetLayerName()]):
                    continue          # would land on existing copper
                mover.SetPosition(pcbnew.VECTOR2I(p0.x + MM(dx), p0.y + MM(dy)))
                boxes[ref] = nb; placed = True
                print(f"  moved {ref} by ({dx:+.2f}, {dy:+.2f}) mm to clear {other.GetReference()}")
                break
            if placed: break
        if not placed and len(list(mover.Pads())) <= 2:
            # A breakout pad can live on either face. Try the other side, where the
            # congestion pattern is different.
            mover.Flip(mover.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            side = mover.GetLayerName()
            nb0 = crt(mover)
            for rad in [0.0] + [0.2*k for k in range(1, 60)]:
                for ang in range(0, 360, 10):
                    dx = rad*math.cos(math.radians(ang)); dy = rad*math.sin(math.radians(ang))
                    nb = (nb0[0]+dx, nb0[1]+dy, nb0[2]+dx, nb0[3]+dy)
                    if not inside(nb): continue
                    if any(overlap(nb, boxes[f3.GetReference()])
                           for f3 in fps
                           if f3 is not mover and f3.GetLayerName() == side
                           and boxes[f3.GetReference()]): continue
                    if any(overlap(nb, cb) for cb in copper[side]): continue
                    q = mover.GetPosition()
                    mover.SetPosition(pcbnew.VECTOR2I(q.x + MM(dx), q.y + MM(dy)))
                    boxes[ref] = nb; placed = True
                    print(f"  moved {ref} to {side} at ({dx:+.2f}, {dy:+.2f}) mm")
                    break
                if placed: break
            if not placed:
                mover.Flip(mover.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if not placed:
            # Last resort: take a position that only conflicts with copper, and rip up
            # the few tracks in the way - they return to ratsnest. Better than leaving a
            # pad under a connector body, where it is unreachable and can short to the shell.
            side = mover.GetLayerName(); nb0 = crt(mover)
            best = None
            for rad in [0.2*k for k in range(1, 60)]:
                for ang in range(0, 360, 10):
                    dx = rad*math.cos(math.radians(ang)); dy = rad*math.sin(math.radians(ang))
                    nb = (nb0[0]+dx, nb0[1]+dy, nb0[2]+dx, nb0[3]+dy)
                    if not inside(nb): continue
                    if any(overlap(nb, boxes[f3.GetReference()])
                           for f3 in fps
                           if f3 is not mover and f3.GetLayerName() == side
                           and boxes[f3.GetReference()]): continue
                    victims = [t for t in b.GetTracks()
                               if _hits(t, nb, b, side)]
                    if best is None or len(victims) < len(best[2]):
                        best = (dx, dy, victims, nb)
                    if not victims: break
                if best and not best[2]: break
            if best:
                dx, dy, victims, nb = best
                for t in victims: b.Remove(t)
                q = mover.GetPosition()
                mover.SetPosition(pcbnew.VECTOR2I(q.x + MM(dx), q.y + MM(dy)))
                boxes[ref] = nb; placed = True
                print(f"  moved {ref} by ({dx:+.2f}, {dy:+.2f}) mm, ripped up {len(victims)} track(s)")
        if placed: fixed += 1
        else:
            print(f"  {ref}: no free position found on either side"); stuck += 1

    if fixed:
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(BOARD)
    print(f"moved {fixed}, left alone {stuck}")


if __name__ == "__main__":
    main()
