#!/usr/bin/env python3
"""
How much copper actually crosses between a rail's regulator and its loads.

An earlier attempt at this modelled the net as a graph and looked for the widest path.
It kept reporting 0.00 A on a board KiCad calls fully connected, because faithfully
reproducing zone-to-pad connectivity - thermal spokes, pads overlapping a pour by area
rather than centre, T-junctions - is a bigger job than it looks, and a check that cries
wolf is worse than no check. That tool was deleted rather than shipped.

This asks a question that needs no connectivity model at all: draw a line across the
board separating the regulator from a load, and add up the current rating of every piece
of that net's copper crossing it. Tracks contribute by width; a plane region contributes
by how wide it is where the line cuts it. Whatever the topology, current cannot exceed
that sum.

The measure is OPTIMISTIC by construction: it sweeps axis-aligned lines, and the true
minimum cut may be a shape none of them match. Read a comfortable number as "no obvious
bottleneck here", not as proof. A number below the rail's rating IS conclusive, because
copper that is not there cannot carry current.

Usage:  python3 tools/check_power_cut.py [-v]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, design, island_route as ir

BOARD = "NAVCORE-SoOP.kicad_pcb"
TOMM  = route.TOMM
INNER = {"In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu"}


def ipc_width(width_mm, internal, dT=10.0):
    k = 0.024 if internal else 0.048
    return k * (dT ** 0.44) * (((width_mm / 0.0254) * 1.37) ** 0.725)


def seg_crosses(a, c, axis, v):
    """Does segment a-c cross the line axis=v? Returns the crossing or None."""
    i = 0 if axis == "x" else 1
    if (a[i] - v) * (c[i] - v) > 0:
        return None
    if abs(c[i] - a[i]) < 1e-12:
        return None
    return True


def poly_span(pts, axis, v):
    """Total length of the polygon's intersection with the line axis=v."""
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


def main():
    verbose = "-v" in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    route.fill(b)
    BD = design.BOARD

    pads = {}
    # Pad copper counts too. Without this the sweep reported +9V at 0.0 A: no TRACK
    # crosses x=135.0, but PV1's 1.5 mm pad spans it and is what actually carries the
    # current across that line. A cut that ignores pads invents bottlenecks wherever a
    # rail terminates on one - and "0.0 A" is the tool's own conclusive-failure signal,
    # so the false alarm was the loudest kind.
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
        loads = [(r, p) for r, p in pads.get(netname, [])
                 if r != src and not r.split(".")[0].startswith(("C", "R"))]
        if not loads:
            continue

        tracks = []
        for t in b.GetTracks():
            if t.GetNetCode() != code or t.Type() == pcbnew.PCB_VIA_T:
                continue
            tracks.append(((TOMM(t.GetStart().x), TOMM(t.GetStart().y)),
                           (TOMM(t.GetEnd().x), TOMM(t.GetEnd().y)),
                           TOMM(t.GetWidth()),
                           b.GetLayerName(t.GetLayer()) in INNER))
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
                    if ir.area(pts) > 1.0:
                        zones.append((pts, inner))

        worst = None
        for axis in ("x", "y"):
            i = 0 if axis == "x" else 1
            lo = BD["X0"] if axis == "x" else BD["Y0"]
            hi = lo + (BD["W"] if axis == "x" else BD["H"])
            v = lo + 0.5
            while v < hi - 0.5:
                # only lines that actually separate the source from some load
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
                    if worst is None or tot < worst[0]:
                        worst = (tot, axis, v, len(sep))
                v += 0.5
        if worst is None:
            continue
        tot, axis, v, nsep = worst
        line = (f"{netname}: tightest cut is {axis}={v:.1f} mm carrying ~{tot:.1f} A "
                f"with {nsep} load(s) beyond it, needs {want:.1f} A")
        # A rail whose every pad is on a DNP part carries no current, so "how much
        # copper crosses it" is not a question about this board - failing on it would
        # block an orderable board over a rail nothing is connected to. The rail IS
        # routed (it once was not, and this comment used to say so); it is simply not
        # populated on the default build.
        _pins = design.NETS.get(netname) or []
        _all_dnp = bool(_pins) and all(
            (design.COMPONENTS.get(q.split('.')[0]) or (0, 0, 0, 0, False))[4]
            for q in _pins)
        if _all_dnp:
            notes.append(line + "  [every load is DNP - rail not populated]")
        elif tot < want:
            fails.append(line)
        elif tot < want * 1.5:
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
