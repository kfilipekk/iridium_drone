#!/usr/bin/env python3
#how much copper actually crosses between a rail's regulator and its loads
#Usage:  python3 tools/check_power_cut.py [-v]
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design, pcbutil

BOARD = "NAVCORE-SoOP.kicad_pcb"
TOMM  = pcbutil.TOMM
INNER = {"In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu"}


def ipc_width(width_mm, internal, dT=10.0):
    k = 0.024 if internal else 0.048
    return k * (dT ** 0.44) * (((width_mm / 0.0254) * 1.37) ** 0.725)


#does segment a-c cross the line axis=v? Returns the crossing or None
def seg_crosses(a, c, axis, v):
    i = 0 if axis == "x" else 1
    if (a[i] - v) * (c[i] - v) > 0:
        return None
    if abs(c[i] - a[i]) < 1e-12:
        return None
    return True


#total length of the polygon's intersection with the line axis=v
def poly_span(pts, axis, v):
    i = 0 if axis == "x" else 1
    j = 1 - i
    xs = []
    n = len(pts)
    for k in range(n):
        a, c = pts[k], pts[(k+1) % n]
        if (a[i] - v) * (c[i] - v) > 0 or abs(c[i] - a[i]) < 1e-12:
            continue
        t = (v - a[i]) / (c[i] - a[i])
        xs.append(a[j] + t * (c[j] - a[j]))
    xs.sort()
    return sum(xs[k+1] - xs[k] for k in range(0, len(xs) - 1, 2))


#each track as the sub-segments between the points
def _split_at_junctions(b, code, segs):
    vias = [v for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T and v.GetNetCode() == code]
    pads = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetCode() == code]

    def key(o, end):
        p = (TOMM(o.GetStart().x), TOMM(o.GetStart().y)) if end == 0 else \
            (TOMM(o.GetEnd().x), TOMM(o.GetEnd().y))
        return p

    out = []
    for t in segs:
        lay = t.GetLayer()
        a = (TOMM(t.GetStart().x), TOMM(t.GetStart().y))
        c = (TOMM(t.GetEnd().x), TOMM(t.GetEnd().y))
        dx, dy = c[0] - a[0], c[1] - a[1]
        L2 = dx * dx + dy * dy
        ts = {0.0, 1.0}

        def add(pt):
            if L2 == 0:
                return
            u = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2
            if 0 < u < 1 and math.hypot(a[0] + u * dx - pt[0], a[1] + u * dy - pt[1]) < 0.02:
                ts.add(u)
        for o in segs:
            if o is t or o.GetLayer() != lay:
                continue
            add(key(o, 0)); add(key(o, 1))
        for v in vias:
            if v.IsOnLayer(lay):
                add((TOMM(v.GetPosition().x), TOMM(v.GetPosition().y)))
        for p in pads:
            if not p.IsOnLayer(lay):
                continue
            pp = p.GetPosition()
            if math.hypot(TOMM(pp.x) - (a[0] + dx / 2), TOMM(pp.y) - (a[1] + dy / 2)) \
                    < max(0.5, math.hypot(dx, dy)):
                add((TOMM(pp.x), TOMM(pp.y)))
        ss = sorted(ts)
        for i in range(len(ss) - 1):
            u0, u1 = ss[i], ss[i + 1]
            out.append((lay, (a[0] + u0 * dx, a[1] + u0 * dy),
                        (a[0] + u1 * dx, a[1] + u1 * dy), TOMM(t.GetWidth())))
    return out


#copper that leads nowhere carries no current
def drop_dead_ends(b, code, segs):
    vias = [v for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T and v.GetNetCode() == code]
    pads = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetCode() == code]
    zones = [z for z in b.Zones() if z.GetNetCode() == code]
    pieces = _split_at_junctions(b, code, segs)

    def anchored(t, pt, live):
        lay = t[0]
        if any(v.IsOnLayer(lay) and math.dist(pt, (TOMM(v.GetPosition().x), TOMM(v.GetPosition().y)))
               <= TOMM(v.GetWidth(lay)) / 2 for v in vias):
            return True
        vp = pcbnew.VECTOR2I(pcbnew.FromMM(pt[0]), pcbnew.FromMM(pt[1]))
        if any(p.IsOnLayer(lay) and p.HitTest(vp) for p in pads):
            return True
        if any(z.IsOnLayer(lay) and z.HitTestFilledArea(lay, vp) for z in zones):
            return True
        return any(o is not t and o[0] == lay and point_on(pt, o[1], o[2]) for o in live)

    live = list(pieces)
    while True:
        dead = [t for t in live
                if not (anchored(t, t[1], live) and anchored(t, t[2], live))]
        if not dead:
            return live
        live = [t for t in live if t not in dead]


#is pt on the closed segment a-c?
def point_on(pt, a, c, tol=1e-6):
    dx, dy = c[0] - a[0], c[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(pt[0] - a[0], pt[1] - a[1]) <= tol
    u = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2
    if u < -tol or u > 1 + tol:
        return False
    return math.hypot(a[0] + u * dx - pt[0], a[1] + u * dy - pt[1]) <= tol


def main():
    verbose = "-v" in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    pcbutil.set_rules(b)
    pcbutil.fill(b)
    BD = design.BOARD

    pads = {}
    #pad copper counts too
    pad_boxes = {}
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            n = pd.GetNet()
            if not n:
                continue
            pads.setdefault(n.GetNetname(), []).append(
                (f"{fp.GetReference()}.{pd.GetNumber()}",
                 (TOMM(pd.GetPosition().x), TOMM(pd.GetPosition().y))))
            bb = pd.GetBoundingBox()
            pad_boxes.setdefault(n.GetNetname(), []).append(
                (TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                 TOMM(bb.GetRight()), TOMM(bb.GetBottom())))

    fails, warns, notes = [], [], []
    for netname, want in sorted(design.NET_CURRENT.items()):
        src = design.NET_SOURCE.get(netname)
        if not src:
            continue
        code = b.FindNet(netname).GetNetCode()
        spos = next((p for r, p in pads.get(netname, []) if r == src), None)
        if spos is None:
            continue
        #capacitors and resistors draw nothing
        named = getattr(design, "LOAD_CURRENT", {}).get(netname, {})
        loads = [(r, p) for r, p in pads.get(netname, [])
                 if r != src and (r in named or not r.split(".")[0].startswith(("C", "R")))]
        if not loads:
            continue

        tracks = []
        segs = [t for t in b.GetTracks()
                if t.GetNetCode() == code and t.Type() != pcbnew.PCB_VIA_T]
        for lay, a, c, w in drop_dead_ends(b, code, segs):
            tracks.append((a, c, w, b.GetLayerName(lay) in INNER))
        zones = []
        for z in b.Zones():
            n = z.GetNet()
            if not n or n.GetNetname() != netname:
                continue
            for lid in z.GetLayerSet().CuStack():
                sh = z.GetFilledPolysList(lid)
                inner = b.GetLayerName(lid) in INNER
                for i in range(sh.OutlineCount()):
                    o = sh.Outline(i)
                    pts = [(TOMM(o.CPoint(k).x), TOMM(o.CPoint(k).y))
                           for k in range(o.PointCount())]
                    if pcbutil.area(pts) > 1.0:
                        zones.append((pts, inner))

        worst = None
        for axis in ("x", "y"):
            i = 0 if axis == "x" else 1
            lo = BD["X0"] if axis == "x" else BD["Y0"]
            hi = lo + (BD["W"] if axis == "x" else BD["H"])
            v = lo + 0.5
            while v < hi - 0.5:
                #only lines that actually separate the source from some load
                sep = [r for r, p in loads if (spos[i] - v) * (p[i] - v) < 0]
                if sep:
                    tot = 0.0
                    for a, c, w, inn in tracks:
                        if seg_crosses(a, c, axis, v):
                            tot += ipc_width(w, inn)
                    for pts, inn in zones:
                        span = poly_span(pts, axis, v)
                        if span > 0:
                            tot += ipc_width(span, inn)
                    for l, t_, r_, bm in pad_boxes.get(netname, []):
                        lo_, hi_ = (l, r_) if axis == "x" else (t_, bm)
                        if lo_ <= v <= hi_:
                            span = (bm - t_) if axis == "x" else (r_ - l)
                            if span > 0:
                                tot += ipc_width(span, False)
                    rail_load_cur = getattr(design, "LOAD_CURRENT", {}).get(netname, {})
                    need = min(want, sum(rail_load_cur.get(r, want) for r in sep))
                    margin = tot / need if need > 0 else 999.0
                    if worst is None or margin < worst[4]:
                        worst = (tot, axis, v, len(sep), margin, need)
                v += 0.5
        if worst is None:
            continue
        tot, axis, v, nsep, margin, need = worst
        line = (f"{netname}: tightest cut is {axis}={v:.1f} mm carrying ~{tot:.1f} A "
                f"with {nsep} load(s) beyond it, needs {need:.1f} A")
        _pins = design.NETS.get(netname) or []
        _all_dnp = bool(_pins) and all(
            (design.COMPONENTS.get(q.split('.')[0]) or (0, 0, 0, 0, False))[4]
            for q in _pins)
        if _all_dnp:
            notes.append(line + "  [every load is DNP - rail not populated]")
        elif tot < need:
            fails.append(line)
        elif tot < need * 1.5:
            warns.append(line)
        else:
            notes.append(line)

    for title, items in (("NOTES", notes), ("WARNINGS", warns), ("FAILURES", fails)):
        if items:
            print(f"{title} ({len(items)}):")
            for it in items:
                print(f"   {it}")
            print()
    print("Optimistic by construction - axis-aligned cuts only. A comfortable number "
          "means no obvious\nbottleneck; a low one is conclusive.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
