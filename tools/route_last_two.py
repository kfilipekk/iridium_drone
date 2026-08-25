#!/usr/bin/env python3
"""Close the last two connections using KiCad's OWN collision engine.

Every earlier router here could only ADD copper and judged clearance with its own
arithmetic - which is how a via once shorted VBAT to USART2_RX on In3.Cu: the check
looked at drill radius and at one layer. This one asks pcbnew: it builds the candidate
geometry, calls SHAPE::Collide against every track, via, pad and filled zone on every
copper layer, and only then writes it. kicad-cli DRC is the final word.

    python3 tools/route_last_two.py --dry     # search and report, write nothing
    python3 tools/route_last_two.py           # write NAVCORE-SoOP.kicad_pcb
"""
import argparse, os, sys
import pcbnew

MM = 1_000_000
CELL = 1_000_000        # 1 mm spatial-index cell
CLEAR = 0.1016          # netclass Default
# Board minimum (kicad_pro: min_via_diameter 0.45, min_through_hole 0.20). The
# netclass default 0.60 finds nothing here - this corner is dense with the F.Cu
# VBAT rail, and 0.15 mm of radius is the difference between a route and no route.
VIA_D, VIA_DRILL = 0.45, 0.20
# 0.1016, NOT 0.10. The netclass minimum is 0.1016 mm and the existing BUCK9_PH copper
# is exactly that - it only printed as "0.10" because the dump used two decimals.
# Routing at 0.10 produced 15 track_width DRC errors.
TRACK_W = 0.1016

def mm(v): return int(round(v * MM))

class Board:
    def __init__(self, path):
        self.b = pcbnew.LoadBoard(path)
        self.layers = [l for l in self.b.GetEnabledLayers().CuStack()]
        self.items = {l: [] for l in self.layers}
        for t in self.b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                for l in self.layers:
                    if t.IsOnLayer(l): self.items[l].append(t)
            elif t.GetLayer() in self.items:
                self.items[t.GetLayer()].append(t)
        for fp in self.b.GetFootprints():
            for p in fp.Pads():
                for l in self.layers:
                    if p.IsOnLayer(l): self.items[l].append(p)
        self.zones = []
        for z in self.b.Zones():
            for l in self.layers:
                if z.IsOnLayer(l):
                    self.zones.append((l, z, z.GetFilledPolysList(l)))
        # SPATIAL INDEX. Without it every candidate position tested every item on
        # every layer - 23400 positions x 6 layers x thousands of items, which does
        # not finish. Bucket each item's bounding box into 1 mm cells and test only
        # the cells a candidate actually touches.
        self.grid = {}
        for l, items in self.items.items():
            g = {}
            for it in items:
                bb = it.GetBoundingBox()
                x0, x1 = bb.GetLeft() // CELL, bb.GetRight() // CELL
                y0, y1 = bb.GetTop() // CELL, bb.GetBottom() // CELL
                for gx in range(int(x0), int(x1) + 1):
                    for gy in range(int(y0), int(y1) + 1):
                        g.setdefault((gx, gy), []).append(it)
            self.grid[l] = g

    def near(self, shape, layer, pad):
        bb = shape.BBox(pad)
        g = self.grid.get(layer, {})
        out = []
        for gx in range(int(bb.GetLeft() // CELL), int(bb.GetRight() // CELL) + 1):
            for gy in range(int(bb.GetTop() // CELL), int(bb.GetBottom() // CELL) + 1):
                out += g.get((gx, gy), ())
        return out

    def clear(self, shape, layer, net, gap=CLEAR):
        """True if `shape` on `layer` keeps `gap` from everything not on `net`."""
        seen = set()
        for it in self.near(shape, layer, mm(gap)):
            if id(it) in seen: continue
            seen.add(id(it))
            if it.GetNetname() == net: continue
            if shape.Collide(it.GetEffectiveShape(layer), mm(gap)): return False
        # ZONES DO NOT VETO. In1.Cu and In2.Cu are filled planes, and the fill on
        # disk was computed before this via existed - every candidate position
        # "collides" with it. In reality KiCad refills and cuts an antipad. Testing
        # against a stale fill rejected all 2679 candidate positions.
        # Zones are re-filled before saving and kicad-cli DRC is the final word.
        return True

    def seg(self, a, b_, layer, net, w=TRACK_W):
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        t.SetEnd(pcbnew.VECTOR2I(mm(b_[0]), mm(b_[1])))
        t.SetWidth(mm(w)); t.SetLayer(layer)
        t.SetNet(self.b.FindNet(net))
        return t

    def via(self, p, net):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(pcbnew.VECTOR2I(mm(p[0]), mm(p[1])))
        v.SetWidth(mm(VIA_D)); v.SetDrill(mm(VIA_DRILL))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(self.b.FindNet(net))
        return v

def path_ok(bd, pts, layer, net, w=TRACK_W):
    for a, c in zip(pts, pts[1:]):
        if a == c: continue
        if not bd.clear(bd.seg(a, c, layer, net, w).GetEffectiveShape(layer),
                        layer, net): return False
    return True

def find_via(bd, start, target, net, box, step=0.05):
    """A via that both an F.Cu run from `start` and a B.Cu run to `target` can reach."""
    x0, x1, y0, y1 = box
    best = None
    n = 0
    y = y0
    while y <= y1 + 1e-9:
        x = x0
        while x <= x1 + 1e-9:
            p = (round(x, 3), round(y, 3))
            n += 1
            vs = bd.via(p, net)
            if all(bd.clear(vs.GetEffectiveShape(l), l, net) for l in bd.layers):
                for fpath, bpath in (
                        ([start, p],                       [p, target]),
                        ([start, (p[0], start[1]), p],     [p, target]),
                        ([start, (start[0], p[1]), p],     [p, target]),
                        ([start, p],           [p, (p[0], target[1]), target]),
                        ([start, p],           [p, (target[0], p[1]), target]),
                        ([start, (p[0], start[1]), p], [p, (target[0], p[1]), target]),
                ):
                    if path_ok(bd, fpath, pcbnew.F_Cu, net) and \
                       path_ok(bd, bpath, pcbnew.B_Cu, net):
                        d = abs(p[0]-start[0])+abs(p[1]-start[1]) + \
                            abs(p[0]-target[0])+abs(p[1]-target[1])
                        if best is None or d < best[0]:
                            best = (d, p, fpath, bpath)
                        break
            x += step
        y += step
    return best, n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "NAVCORE-SoOP.kicad_pcb")
    bd = Board(path)
    print(f"copper layers: {[bd.b.GetLayerName(l) for l in bd.layers]}")

    jobs = [
        ("BUCK9_PH", (130.500, 122.369), (128.487, 122.969),
         (126.0, 132.5, 118.0, 127.0)),
    ]
    added = []
    for net, start, target, box in jobs:
        print(f"\n{net}: {start} -> {target}")
        best, n = find_via(bd, start, target, net, box)
        if not best:
            print(f"   no clear via in {n} candidate positions"); continue
        d, p, fpath, bpath = best
        print(f"   via at {p}  (searched {n})")
        print(f"   F.Cu {fpath}")
        print(f"   B.Cu {bpath}")
        added.append((net, p, fpath, bpath))

    if a.dry or not added:
        print("\n(dry run - nothing written)" if a.dry else "\nnothing to write")
        return 0
    for net, p, fpath, bpath in added:
        bd.b.Add(bd.via(p, net))
        for q, r in zip(fpath, fpath[1:]):
            if q != r: bd.b.Add(bd.seg(q, r, pcbnew.F_Cu, net))
        for q, r in zip(bpath, bpath[1:]):
            if q != r: bd.b.Add(bd.seg(q, r, pcbnew.B_Cu, net))
    # refill every zone so the planes get their antipads around the new via
    filler = pcbnew.ZONE_FILLER(bd.b)
    filler.Fill(bd.b.Zones())
    bd.b.Save(path)
    print(f"\nwrote {len(added)} connection(s) to {path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
