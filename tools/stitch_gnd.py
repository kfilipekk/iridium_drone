#!/usr/bin/env python3
"""Reconnect GND pour islands that routing cut off, with a stitching via.

A new track across a pour can sever a neck and strand a piece of copper. That is a
real fault, not cosmetic: an isolated ground island is an unterminated antenna sitting
next to a switching regulator. Routing BUCK9_PH carved a 2.37 mm^2 island out of the
F.Cu pour at (128.9, 120.2), and KiCad reported it as "Zone [GND] on F.Cu / Zone [GND]
on B.Cu unconnected".

GND is poured on F.Cu, In1.Cu, In2.Cu, In3.Cu and B.Cu, so one through via anywhere
inside the island reconnects it to the planes. This finds a spot that clears every
other net on every layer and sits far enough inside the island's own outline.

    python3 tools/stitch_gnd.py --dry
    python3 tools/stitch_gnd.py
"""
import argparse, os, sys
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from route_last_two import Board, mm, CLEAR, VIA_D

# Ground-return vias next to the switching regulators' GND pins. Standard practice
# for a buck converter - it shortens the high-di/dt return loop - and here it also
# stops routing from stranding the pad: any island a later track carves around this
# pad already contains a via to the inner GND planes. U18.1 had none, which is how a
# single BUCK9_PH trace left the 9 V regulator's ground floating.
ANCHOR_PADS = ["U18.1", "U8.1"]


def same_island(polys, a, b):
    """True if points a and b lie in the same filled island."""
    ia = ib = None
    for i in range(polys.OutlineCount()):
        if polys.Contains(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])), i): ia = i
        if polys.Contains(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])), i): ib = i
    return ia is not None and ia == ib


def anchor_pads(bd, dry):
    added = []
    for ref_pad in ANCHOR_PADS:
        ref, num = ref_pad.split(".")
        pad = None
        for fp in bd.b.GetFootprints():
            if fp.GetReference() != ref: continue
            for q in fp.Pads():
                if q.GetNumber() == num: pad = q
        if pad is None:
            print(f"{ref_pad}: not on the board"); continue
        if pad.GetNetname() != "GND":
            print(f"{ref_pad}: net is {pad.GetNetname()}, not GND - skipped"); continue
        c = pad.GetPosition()
        c = (c.x / 1e6, c.y / 1e6)
        near = [t for t in bd.b.GetTracks()
                if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"
                and ((t.GetPosition().x/1e6 - c[0])**2
                     + (t.GetPosition().y/1e6 - c[1])**2) ** .5 < 1.5]
        if near:
            print(f"{ref_pad}: already has a GND via within 1.5 mm"); continue
        pour = None
        for z in bd.b.Zones():
            if z.IsOnLayer(pad.GetLayer()) and z.GetNetname() == "GND":
                pour = z.GetFilledPolysList(pad.GetLayer())
        best = None
        y = c[1] - 2.0
        while y <= c[1] + 2.0:
            x = c[0] - 2.0
            while x <= c[0] + 2.0:
                q = (round(x, 2), round(y, 2))
                v = bd.via(q, "GND")
                if all(bd.clear(v.GetEffectiveShape(l), l, "GND") for l in bd.layers):
                    # SAME ISLAND AS THE PAD, or it anchors nothing. The first version
                    # only minimised distance and put U18.1's "ground-return via" at
                    # (131.2, 124.27) - 2.52 mm away and in a different piece of
                    # copper, which would have looked like a fix and connected nothing.
                    if pour is not None and not same_island(pour, c, q):
                        x += 0.05; continue
                    d = ((q[0]-c[0])**2 + (q[1]-c[1])**2) ** .5
                    if best is None or d < best[0]: best = (d, q)
                x += 0.05
            y += 0.05
        if best:
            print(f"{ref_pad}: ground-return via at {best[1]} ({best[0]:.2f} mm away)")
            added.append(best[1])
        else:
            print(f"{ref_pad}: no room for a ground-return via within 2 mm")
    return added


def island_polys(bd, layer, net="GND"):
    out = []
    for z in bd.b.Zones():
        if not z.IsOnLayer(layer) or z.GetNetname() != net: continue
        p = z.GetFilledPolysList(layer)
        for i in range(p.OutlineCount()):
            out.append((i, p, z))
    return out

def connected_islands(bd, layer, polys):
    """Indices of islands carrying a GND VIA - only those reach the inner planes.

    PADS DO NOT COUNT, and counting them hid the fault this script was written for.
    An SMD pad connects its component to the island; it does nothing to connect the
    island to the rest of the board. F.Cu island 10 held exactly one anchor - pad
    U18.1, the 9 V regulator's ground pin - and no via, so U18's ground return was a
    floating 2.37 mm^2 patch of copper. With pads counted as anchors this script
    printed "nothing to stitch".
    """
    ok = set()
    anchors = []
    for t in bd.b.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND":
            anchors.append(t.GetPosition())
    for i, p, z in polys:
        for a in anchors:
            if p.Contains(pcbnew.VECTOR2I(a.x, a.y), i):
                ok.add(i); break
    return ok

def inside_point(polys, i, margin=0.30):
    """A point at least `margin` mm inside island i, or None."""
    o = polys.Outline(i)
    xs = [o.CPoint(k).x / 1e6 for k in range(o.PointCount())]
    ys = [o.CPoint(k).y / 1e6 for k in range(o.PointCount())]
    step = 0.05
    y = min(ys)
    while y <= max(ys):
        x = min(xs)
        while x <= max(xs):
            q = (round(x, 3), round(y, 3))
            if all(polys.Contains(pcbnew.VECTOR2I(mm(q[0] + dx), mm(q[1] + dy)), i)
                   for dx, dy in ((0,0), (margin,0), (-margin,0), (0,margin), (0,-margin))):
                return q
            x += step
        y += step
    return None


def bridge_to_pour(bd, layer, polys, i, all_polys):
    """Maze-route a GND trace from island i back to the biggest island on this layer."""
    import maze_route
    def area(j):
        o = polys.Outline(j)
        n = o.PointCount()
        return abs(sum(o.CPoint(k).x / 1e6 * o.CPoint((k+1) % n).y / 1e6
                       - o.CPoint((k+1) % n).x / 1e6 * o.CPoint(k).y / 1e6
                       for k in range(n))) / 2
    main = max((j for j, _, _ in all_polys if j != i), key=area, default=None)
    if main is None: return None
    s = inside_point(polys, i)
    if not s:
        print("   no interior point in the island to start from"); return None
    # THE GOAL IS THE NEAREST POINT OF THE POUR, not just any interior point. Taking
    # an arbitrary one put the goal at the pour's far corner (103.45, 100.65) - 33 mm
    # away and outside the search box, so the router reported "could not reach the
    # grid" when the real pour edge was a fraction of a millimetre away.
    g, gd = None, 1e18
    for r in [x * 0.05 for x in range(1, 121)]:
        n = max(8, int(2 * 3.1416 * r / 0.05))
        for k in range(n):
            import math
            q = (round(s[0] + r * math.cos(2*math.pi*k/n), 3),
                 round(s[1] + r * math.sin(2*math.pi*k/n), 3))
            if all(polys.Contains(pcbnew.VECTOR2I(mm(q[0]+dx), mm(q[1]+dy)), main)
                   for dx, dy in ((0,0), (0.2,0), (-0.2,0), (0,0.2), (0,-0.2))):
                g, gd = q, r; break
        if g: break
    if not g:
        print("   the main pour is more than 6 mm away - no bridge"); return None
    print(f"   nearest pour point is {gd:.2f} mm away")
    box = (min(s[0], g[0]) - 2.0, max(s[0], g[0]) + 2.0,
           min(s[1], g[1]) - 2.0, max(s[1], g[1]) + 2.0)
    print(f"   bridging {s} -> {g} on {bd.b.GetLayerName(layer)}")
    r = maze_route.route(bd, "GND", s, layer, g, layer, box, layers=[layer])
    return r


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "NAVCORE-SoOP.kicad_pcb")
    bd = Board(path)
    added = anchor_pads(bd, a.dry)
    bridges = []
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        polys = island_polys(bd, layer)
        if not polys: continue
        ok = connected_islands(bd, layer, polys)
        for i, p, z in polys:
            if i in ok: continue
            o = p.Outline(i)
            xs = [o.CPoint(k).x / 1e6 for k in range(o.PointCount())]
            ys = [o.CPoint(k).y / 1e6 for k in range(o.PointCount())]
            area = abs(sum(o.CPoint(k).x / 1e6 * o.CPoint((k+1) % o.PointCount()).y / 1e6
                           - o.CPoint((k+1) % o.PointCount()).x / 1e6 * o.CPoint(k).y / 1e6
                           for k in range(o.PointCount()))) / 2
            name = bd.b.GetLayerName(layer)
            print(f"{name} island {i}: {area:.2f} mm^2 "
                  f"x[{min(xs):.2f},{max(xs):.2f}] y[{min(ys):.2f},{max(ys):.2f}] "
                  f"- NOT anchored")
            spot = None
            step = 0.05
            y = min(ys)
            while y <= max(ys) and not spot:
                x = min(xs)
                while x <= max(xs):
                    q = (round(x, 3), round(y, 3))
                    pt = pcbnew.VECTOR2I(mm(q[0]), mm(q[1]))
                    if p.Contains(pt, i):
                        v = bd.via(q, "GND")
                        if all(bd.clear(v.GetEffectiveShape(l), l, "GND")
                               for l in bd.layers):
                            # keep the whole via body inside the island
                            r = VIA_D / 2 + CLEAR
                            if all(p.Contains(pcbnew.VECTOR2I(mm(q[0] + dx), mm(q[1] + dy)), i)
                                   for dx, dy in ((r,0),(-r,0),(0,r),(0,-r),
                                                  (r*.7,r*.7),(-r*.7,r*.7),
                                                  (r*.7,-r*.7),(-r*.7,-r*.7))):
                                spot = q; break
                    x += step
                y += step
            if spot:
                print(f"   stitching via at {spot}")
                added.append(spot)
            else:
                # NO ROOM FOR A VIA IS NOT THE END. A via needs 0.45 mm of body plus
                # 0.1016 either side - 0.65 mm of clear width. A 0.1016 mm trace needs
                # 0.31 mm. Where the island is too pinched for a via there is often
                # still a gap a bridging trace can take back to the main pour, and a
                # trace to the pour is as good a connection as a via to the planes.
                print("   no room for a via - trying a bridging trace to the pour")
                bridge = bridge_to_pour(bd, layer, p, i, polys)
                if bridge:
                    bridges.append((layer, bridge))
                else:
                    print("   NO bridge either - this island needs the route changed "
                          "or a placement fix; see docs/ROUTING-TODO.md")
    if not added and not bridges:
        print("\nnothing to stitch"); return 0
    if a.dry:
        print(f"\n(dry run - {len(added)} via(s), {len(bridges)} bridge(s) not written)")
        return 0
    for q in added:
        bd.b.Add(bd.via(q, "GND"))
    for layer, (segs, vias) in bridges:
        for x, y, l in segs:
            if x != y: bd.b.Add(bd.seg(x, y, l, "GND", 0.1016))
        for v in vias: bd.b.Add(bd.via(v, "GND"))
    pcbnew.ZONE_FILLER(bd.b).Fill(bd.b.Zones())
    bd.b.Save(path)
    print(f"\nwrote {len(added)} stitching via(s)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
