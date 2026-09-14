#!/usr/bin/env python3
"""Bridge orphaned copper to its own net with a track - but only where that is provable.

Every other closing tool here asks "is there somewhere a via fits" or "is there a
grid path", and both fail on the last few items because the answer is no: the
islands are pockets in other nets' copper. This one asks a narrower, checkable
question first:

    walk the straight line between the closest point on the orphan and the
    closest point on the main part of the same net, and measure the clearance to
    FOREIGN copper (other nets' tracks, pads, vias AND pours) at every step.

If the worst clearance along that line is at least TRACK_W/2 + CLEAR, a 0.1016 mm
track through it is legal and the island can be joined. If it is not, this tool
says so and does not touch the board - it never guesses.

That distinction is the whole point. A tool that adds copper and then checks
whether the board got better cannot tell "closed one, opened another" from
"closed one"; this one refuses up front and verifies afterwards.

Usage:  python3 tools/bridge_orphans.py NET [--apply] [--clear MM]
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK = "/tmp/nav/bridge_orphans_backup.kicad_pcb"
RPT = "/tmp/nav/bridge_orphans.rpt"
MM = pcbnew.FromMM
FROM = lambda v: v / 1e6
STEP = 0.01          # walk resolution, mm


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json",
                    "--severity-all", "--units", "mm", "-o", RPT, BOARD],
                   capture_output=True, timeout=900)
    import json
    d = json.load(open(RPT))
    hard = sum(1 for v in d.get("violations", [])
               if v.get("severity") == "error")
    return hard, len(d.get("unconnected_items", []))


def layers_of(pad, cu):
    return [l for l in cu if pad.IsOnLayer(l)]


def pad_rect(pad):
    """A pad as a rectangle over its bounding box.

    This used to be pad.GetEffectiveShape(layer), and that is the wrong tool for
    clearance. GetEffectiveShape returns a SHAPE_COMPOUND and compound.Distance() does
    not agree with DRC: C3.1 (+3V3, a 0.56 x 0.62 mm 0402 land at (126.18,113.77))
    measured 0.2447 mm from a point that DRC scored at 0.0736 mm, so a GND bridge ran
    0.0229 mm from that pad edge while this tool certified 0.208 mm of clearance and
    would not stop. Bounding boxes are what route.obstacle_shapes() and shove.shapes_of()
    both use for pads, and they are exact for the rectangular lands this board uses.
    """
    bb = pad.GetBoundingBox()
    poly = pcbnew.SHAPE_POLY_SET()
    ch = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                 (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
        ch.Append(x, y)
    ch.SetClosed(True)
    poly.AddOutline(ch)
    return poly


def build(board, net):
    cu = list(board.GetLayerSet().CuStack())
    allcu = set(cu)
    code = board.FindNet(net).GetNetCode()
    items = []

    def add(shape, layers, label, base):
        items.append(dict(shape=shape, layers=layers, label=label, base=base))

    for t in board.GetTracks():
        if t.GetNetCode() != code:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            add(t.GetEffectiveShape(), set(allcu),
                f"via@({FROM(t.GetPosition().x):.2f},{FROM(t.GetPosition().y):.2f})",
                "via" + t.m_Uuid.AsString())
        else:
            add(t.GetEffectiveShape(), {t.GetLayer()},
                f"trk[{board.GetLayerName(t.GetLayer())}]", "trk" + t.m_Uuid.AsString())
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != code:
                continue
            rect = pad_rect(p)
            for ln in layers_of(p, cu):
                add(rect, {ln}, f"pad {fp.GetReference()}.{p.GetNumber()}",
                    "pad" + p.m_Uuid.AsString())
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != net:
            continue
        for ln in z.GetLayerSet().CuStack():
            poly = z.GetFilledPolysList(ln)
            for i in range(poly.OutlineCount()):
                sub = pcbnew.SHAPE_POLY_SET()
                sub.AddOutline(poly.Outline(i))
                for h in range(poly.HoleCount(i)):
                    sub.AddHole(poly.Hole(i, h), 0)
                add(sub, {ln},
                    f"zone[{board.GetLayerName(ln)}]a={poly.Outline(i).Area()/1e12:.2f}",
                    f"z{z.m_Uuid.AsString()}{ln}{i}")
    return items


def verts(sh):
    pts = []
    if isinstance(sh, pcbnew.SHAPE_POLY_SET):
        for i in range(sh.OutlineCount()):
            o = sh.Outline(i)
            n = o.PointCount()
            for k in range(n):
                pts.append(o.CPoint(k))
                pts.append(pcbnew.VECTOR2I((o.CPoint(k).x + o.CPoint((k + 1) % n).x) // 2,
                                           (o.CPoint(k).y + o.CPoint((k + 1) % n).y) // 2))
    else:
        bb = sh.BBox()
        for fx in (0.0, 0.5, 1.0):
            for fy in (0.0, 0.5, 1.0):
                pts.append(pcbnew.VECTOR2I(int(bb.GetLeft() + fx * (bb.GetRight() - bb.GetLeft())),
                                           int(bb.GetTop() + fy * (bb.GetBottom() - bb.GetTop()))))
    return pts


def bbox(sh, m=0):
    x = sh.BBox()
    return (x.GetLeft() - m, x.GetTop() - m, x.GetRight() + m, x.GetBottom() + m)


def components(items):
    n = len(items)
    par = list(range(n))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    bx = [bbox(it["shape"]) for it in items]
    for i in range(n):
        for j in range(i + 1, n):
            if items[i]["layers"].isdisjoint(items[j]["layers"]):
                continue
            a, c = bx[i], bx[j]
            if a[2] < c[0] or c[2] < a[0] or a[3] < c[1] or c[3] < a[1]:
                continue
            if items[i]["shape"].Collide(items[j]["shape"], 0):
                r, s = find(i), find(j)
                if r != s:
                    par[s] = r
    byb = {}
    for i, it in enumerate(items):
        byb.setdefault(it["base"], []).append(i)
    for k, idx in byb.items():
        for x in idx[1:]:
            r, s = find(idx[0]), find(x)
            if r != s:
                par[s] = r
    g = {}
    for i in range(n):
        g.setdefault(find(i), []).append(i)
    return sorted(g.values(), key=len, reverse=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    net = sys.argv[1]
    apply_ = "--apply" in sys.argv
    # The design rule is TRACK_W/2 + CLEAR, but the grid only certifies the CELLS and
    # DRC measures the drawn segments. A margin makes the difference between the two
    # too small to matter: without it the R12 bridge came back having measured 0.202 mm
    # to the pad at one endpoint and still reported 0.009 mm of real clearance, because
    # the grid samples positions and DRC does not.
    margin = float(sys.argv[sys.argv.index("--margin") + 1]) \
        if "--margin" in sys.argv else 0.05
    need = route.TRACK_W / 2 + route.CLEAR + margin

    board = pcbnew.LoadBoard(BOARD)
    cu = list(board.GetLayerSet().CuStack())
    items = build(board, net)
    comps = components(items)
    if len(comps) < 2:
        print(f"{net}: already one piece ({len(items)} shapes)")
        return 0
    main = comps[0]
    print(f"{net}: {len(items)} shapes, {len(comps)} components "
          f"(main {len(main)}); need {need:.3f} mm free for a {route.TRACK_W} mm track")

    # foreign copper per layer, for the walk
    code = board.FindNet(net).GetNetCode()
    foreign = {}
    for t in board.GetTracks():
        if t.GetNetCode() == code:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            sh = t.GetEffectiveShape()
            for l in cu:
                foreign.setdefault(l, []).append(sh)
        else:
            foreign.setdefault(t.GetLayer(), []).append(t.GetEffectiveShape())
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == code:
                continue
            rect = pad_rect(p)
            for ln in layers_of(p, cu):
                foreign.setdefault(ln, []).append(rect)
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() == net:
            continue
        for ln in z.GetLayerSet().CuStack():
            poly = z.GetFilledPolysList(ln)
            for i in range(poly.OutlineCount()):
                sub = pcbnew.SHAPE_POLY_SET()
                sub.AddOutline(poly.Outline(i))
                for h in range(poly.HoleCount(i)):
                    sub.AddHole(poly.Hole(i, h), 0)
                foreign.setdefault(ln, []).append(sub)

    # Hard obstacles for a same-layer TRACK: foreign tracks, pads and vias. Pours are
    # deliberately NOT here. A track may cross another net's pour - the pour yields when
    # it is refilled, leaving a legal slot - so refusing to cross one is refusing a move
    # that costs nothing. What a track may not do is touch foreign metal, so that is
    # all this list contains. Pours still matter for the straight-line test below, which
    # is why it keeps its own copy.
    solids = {}
    for t in board.GetTracks():
        if t.GetNetCode() == code:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            sh = t.GetEffectiveShape()
            for l in cu:
                solids.setdefault(l, []).append(sh)
        else:
            solids.setdefault(t.GetLayer(), []).append(t.GetEffectiveShape())
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == code:
                continue
            rect = pad_rect(p)
            for ln in layers_of(p, cu):
                solids.setdefault(ln, []).append(rect)

    def bfs(layer, src_shapes, tgt_shapes, step=0.02, pad=6.0):
        """Shortest 8-connected path from any cell inside src to any cell inside tgt,
        staying at least `need` from every foreign track/pad/via on this layer."""
        from collections import deque
        # Bound the search to this orphan's neighbourhood. Taking the bbox of the MAIN
        # piece instead puts the grid over the whole board - the main pour IS the whole
        # board - and the search never finishes.
        xs = []; ys = []
        for sh in src_shapes:
            b = sh.BBox()
            xs += [FROM(b.GetLeft()), FROM(b.GetRight())]
            ys += [FROM(b.GetTop()), FROM(b.GetBottom())]
        x0, x1 = min(xs) - pad, max(xs) + pad
        y0, y1 = min(ys) - pad, max(ys) + pad
        region = pcbnew.BOX2I(pcbnew.VECTOR2I(MM(x0), MM(y0)),
                              pcbnew.VECTOR2I(MM(x1 - x0), MM(y1 - y0)))
        tgt_shapes = [sh for sh in tgt_shapes if sh.BBox().Intersects(region)]
        if not tgt_shapes:
            return None, "no same-net copper within reach"
        nx = int((x1 - x0) / step) + 1
        ny = int((y1 - y0) / step) + 1
        free = bytearray(b"\x01" * (nx * ny))
        needi = MM(need)
        obs = solids.get(layer, [])
        for sh in obs:
            bb = sh.BBox()
            i0 = max(0, int((FROM(bb.GetLeft()) - need - x0) / step) - 1)
            i1 = min(nx - 1, int((FROM(bb.GetRight()) + need - x0) / step) + 1)
            j0 = max(0, int((FROM(bb.GetTop()) - need - y0) / step) - 1)
            j1 = min(ny - 1, int((FROM(bb.GetBottom()) + need - y0) / step) + 1)
            for j in range(j0, j1 + 1):
                for i in range(i0, i1 + 1):
                    k = j * nx + i
                    if not free[k]:
                        continue
                    v = pcbnew.VECTOR2I(MM(x0 + i * step), MM(y0 + j * step))
                    if sh.Distance(v) < needi:
                        free[k] = 0
        src = set(); tgt = set()
        for j in range(ny):
            for i in range(nx):
                k = j * nx + i
                if not free[k]:
                    continue
                v = pcbnew.VECTOR2I(MM(x0 + i * step), MM(y0 + j * step))
                if any(sh.Collide(v, 0) for sh in src_shapes):
                    src.add((i, j))
                if any(sh.Collide(v, 0) for sh in tgt_shapes):
                    tgt.add((i, j))
        if not src or not tgt:
            return None, f"{len(src)} start cells, {len(tgt)} target cells"
        prev = {}
        q = deque()
        for s in src:
            prev[s] = None
            q.append(s)
        while q:
            cur = q.popleft()
            if cur in tgt and prev[cur] is not None:
                path = [cur]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                pts = [(x0 + i * step, y0 + j * step) for (i, j) in reversed(path)]
                return pts, f"{len(src)} start cells, {len(tgt)} target cells"
            i, j = cur
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nb = (i + di, j + dj)
                if nb in prev:
                    continue
                if not (0 <= nb[0] < nx and 0 <= nb[1] < ny):
                    continue
                if not free[nb[1] * nx + nb[0]]:
                    continue
                # No corner cutting. On an 8-connected grid both ends of a diagonal can
                # be legal while the DIAGONAL ITSELF passes within a hair of a pad in one
                # of the two orthogonal cells it skips - the cells are checked, the
                # segment is not. That is how the first GND bridge came back with eight
                # 0.009 mm clearance violations against R12's +3V3 pad, each one a
                # segment of a path whose every cell had passed. Requiring both
                # orthogonal neighbours to be free makes the diagonal provably as clear
                # as the cells, because it then runs inside the square of four free
                # cells, and the two nearest blocked cells are a full cell away.
                if di and dj:
                    if not (free[j * nx + (i + di)] and free[(j + dj) * nx + i]):
                        continue
                prev[nb] = cur
                q.append(nb)
        return None, f"{len(src)} start cells, {len(tgt)} target cells, no path"

    def clear_along(layer, pts, step=STEP):
        """Worst distance from the CENTRELINE of this polyline to foreign track/pad/via
        copper on `layer`, sampled densely along every segment.

        This exists because certifying CELLS is not the same as certifying the SEGMENTS
        DRAWN BETWEEN THEM. The set of points at least `need` from a foreign shape is the
        complement of a convex buffer, so it is NOT convex: a straight line joining two
        legal cells can pass inside the buffer, and the longer the merged segment the
        deeper the dip. That is precisely how the first GND bridge measured 0.202 mm at
        its endpoints and came back from DRC with 0.0229 mm of real clearance against
        C3.1 (+3V3) - the cells were legal, the drawn segment was not.
        """
        obs = solids.get(layer, [])
        if not obs:
            return 1e18, None
        worst, wat = 1e18, None
        for k in range(len(pts) - 1):
            ax, ay = pts[k]
            bx, by = pts[k + 1]
            n = max(2, int(math.hypot(bx - ax, by - ay) / step) + 1)
            for s in range(n + 1):
                t = s / n
                v = pcbnew.VECTOR2I(MM(ax + t * (bx - ax)), MM(ay + t * (by - ay)))
                c = min((sh.Distance(v) for sh in obs), default=1e18) / 1e6
                if c < worst:
                    worst, wat = c, (ax + t * (bx - ax), ay + t * (by - ay))
        return worst, wat

    def simplify(pts, layer):
        """Drop collinear grid points, but only where the longer segment that replaces
        them is still provably clear. The unmerged fallback has consecutive points one grid
        step apart, which cannot dip meaningfully below the clearance its cells certified.
        """
        if len(pts) < 3:
            return pts
        out = [pts[0]]
        for i in range(1, len(pts) - 1):
            ax, ay = pts[i][0] - out[-1][0], pts[i][1] - out[-1][1]
            bx, by = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
            if abs(ax * by - ay * bx) > 1e-9:
                out.append(pts[i])
        out.append(pts[-1])
        if len(out) == len(pts):
            return out
        return out if clear_along(layer, out)[0] >= need else pts

    todo = []
    for comp in comps[1:]:
        best = (1e18, None, None, None)
        for i in comp:
            ai = items[i]
            for x in verts(ai["shape"]):
                for j in main:
                    aj = items[j]
                    common = ai["layers"] & aj["layers"]
                    if not common:
                        continue
                    d = aj["shape"].Distance(x)
                    if d < best[0]:
                        best = (d, i, j, x, sorted(common))
        if best[1] is None:
            print(f"  orphan({len(comp)}): no shared layer with the main piece")
            continue
        d, i, j, xa, common = best
        # closest point on the target, by sampling its vertices
        ptb, db = None, 1e18
        for y in verts(items[j]["shape"]):
            dd = items[i]["shape"].Distance(y)
            if dd < db:
                db, ptb = dd, y
        lay = common[0]
        worst, wat = 1e18, None
        n = max(2, int(d / 1e6 / STEP))
        for s in range(1, n):
            t = s / n
            px = xa.x + t * (ptb.x - xa.x)
            py = xa.y + t * (ptb.y - xa.y)
            v = pcbnew.VECTOR2I(int(px), int(py))
            c = min((sh.Distance(v) for sh in foreign.get(lay, [])), default=1e18) / 1e6
            if c < worst:
                worst, wat = c, (FROM(px), FROM(py))
        lab = items[i]["label"]
        print(f"  orphan {lab:34s} -> {items[j]['label']:32s} "
              f"gap {d/1e6:.3f} mm on {board.GetLayerName(lay)}")
        if worst >= need:
            print(f"      free along the line: worst {worst:.3f} mm at "
                  f"({wat[0]:.3f},{wat[1]:.3f})  -> BRIDGEABLE (straight)")
            todo.append((lay, [(FROM(xa.x), FROM(xa.y)), (FROM(ptb.x), FROM(ptb.y))], lab))
            continue
        print(f"      straight line blocked (worst {worst:.3f} mm at "
              f"({wat[0]:.3f},{wat[1]:.3f})); searching a route that crosses pours")
        routed = False
        for candidate_lay in common:
            srcs = [items[k]["shape"] for k in comp if candidate_lay in items[k]["layers"]]
            tgts = [items[k]["shape"] for k in main if candidate_lay in items[k]["layers"]]
            if not srcs or not tgts:
                continue
            path, note = bfs(candidate_lay, srcs, tgts)
            if not path:
                print(f"        {board.GetLayerName(candidate_lay)}: {note}")
                continue
            pts = simplify(path, candidate_lay)
            worst, wat = clear_along(candidate_lay, pts)
            if worst < need:
                # The grid found a path but the polyline it becomes does not survive its
                # own clearance check. Say so; do not hand DRC a segment we could not
                # prove.
                print(f"        {board.GetLayerName(candidate_lay)}: routed path fails per-segment "
                      f"check (worst {worst:.3f} mm at ({wat[0]:.3f},{wat[1]:.3f})) - refusing")
                continue
            L = sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
                    for k in range(len(pts) - 1))
            print(f"        {board.GetLayerName(candidate_lay)}: {L:.2f} mm in "
                  f"{len(pts) - 1} segment(s), min clearance {worst:.3f} mm  "
                  f"[{note}]  -> BRIDGEABLE (routed)")
            todo.append((candidate_lay, pts, lab))
            routed = True
            break
        if not routed:
            print("      no route on any shared layer - board untouched for this one")

    if not todo:
        print("nothing provably bridgeable - board untouched")
        return 0
    if not apply_:
        print(f"\n{len(todo)} bridge(s) ready - dry run, pass --apply")
        return 0

    hard0, un0 = drc()
    n0 = len(components(build(pcbnew.LoadBoard(BOARD), net)))
    print(f"\nbaseline {hard0} errors, {un0} unconnected, {n0} component(s) on {net}")
    for lay, pts, lab in todo:
        shutil.copy(BOARD, BAK)
        bd = pcbnew.LoadBoard(BOARD)
        route.set_rules(bd)
        n = bd.FindNet(net)
        for k in range(len(pts) - 1):
            route.add_track(bd, pts[k], pts[k + 1], bd.GetLayerName(lay), n, width=route.TRACK_W)
        route.fill(bd)
        bd.Save(BOARD)
        hard, un = drc()
        # DRC's unconnected PAIR count is not the measure: with four pieces it
        # reports two pairs, so closing one of three orphans leaves that number
        # untouched. The measure is how many pieces the net has, plus whether the
        # bridge broke anything else.
        n1 = len(components(build(pcbnew.LoadBoard(BOARD), net)))
        if "--keep" in sys.argv and hard > hard0:
            print(f"  {lab}: KEPT despite {hard} errors (--keep) - inspect {RPT}")
            continue
        if hard > hard0 or n1 >= n0:
            shutil.copy(BAK, BOARD)
            print(f"  {lab}: rolled back ({hard} errors, {n1} components)")
        else:
            hard0, n0 = hard, n1
            print(f"  {lab}: bridged -> {hard} errors, {n1} component(s), {un} unconnected pairs")
    print(f"\n{hard0} errors, {n0} component(s) on {net}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
