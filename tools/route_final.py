#!/usr/bin/env python3
"""
Finish the nets left open by the J1/J2 rotation, on a clearance model that matches DRC.

tools/route.py could not route these, and the reason was its model rather than the board:

  * TRK_KEEP adds 0.15 mm where this board's rule is 0.1016, so every committed track
    projects a 0.63 mm no-go corridor where 0.41 is required. Where two overlap the cells
    go "contested" and block a third net outright - which is what sealed J2's pads in.
  * _mark_via_legal treats pads as circumscribed circles. On J2's 1.55 x 0.60 mm pads that
    is a 0.775 mm disc, which swallows the 0.4 mm gaps between neighbours and hides every
    escape between them. route.py makes exactly this argument about _stamp_rect and then
    leaves the bug here.
  * route_to_any steps layers with `other = 1 - li`, a two-layer leftover, so it can only
    ever hop F.Cu <-> In2.Cu and silently cannot reach In3.Cu or B.Cu.

This uses the real design rules, all four signal layers, and pads as rectangles.

Everything is POINT-sampled on a grid rather than tested segment-against-segment. That is
not just simpler, it removes a whole bug class: the segment-to-segment form has to special
-case crossing, because two segments that cross have every endpoint far from the other and
a true distance of zero. A cell sitting on top of another net's track is simply blocked.

Each net is committed, the zones refilled, and whole-board DRC decides. A net that raises
a hard violation or fails to reduce the unconnected count is reverted, so a failure costs
nothing but that net.

DRC must run on the board in its own directory: kicad-cli reads the design rules from the
.kicad_pro beside it, and a copy elsewhere silently falls back to KiCad's 0.2 mm defaults.

Usage: python3 tools/route_final.py [--apply] [NET ...]
"""
import os, sys, math, heapq, shutil, subprocess, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from route import add_via, add_track, inside_board

BOARD  = 'NAVCORE-SoOP.kicad_pcb'
LAYERS = ('F.Cu', 'In2.Cu', 'In3.Cu', 'B.Cu')
GRID   = 0.05
TRACK_W, CLR, HOLE_CLR = 0.1016, 0.1016, 0.20
VIA_R, VIA_DRILL_R     = 0.30, 0.15
HALF   = TRACK_W / 2
VIA_COST = 40          # grid steps a layer change is worth
BK     = 1.0           # spatial bucket, mm


def seg_d(px, py, x1, y1, x2, y2):
    dx, dy = x2-x1, y2-y1
    L2 = dx*dx + dy*dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy)/L2))
    return math.hypot(px-(x1+u*dx), py-(y1+u*dy))


def rect_d(px, py, l, r, t, b):
    return math.hypot(max(l-px, 0.0, px-r), max(t-py, 0.0, py-b))


class Field:
    """Per-layer obstacle and goal geometry for one net, bucketed for lookup."""

    def __init__(self, board, netname):
        self.b, self.net = board, netname
        self.lid = {n: board.GetLayerID(n) for n in LAYERS}
        self.obs = {n: {} for n in LAYERS}     # layer -> bucket -> [obstacles]
        self.own = {n: {} for n in LAYERS}     # same, but this net's copper (goals)
        self.allobs = {}                       # every layer, for via legality
        self.holes = {}

        def put(store, key, item):
            store.setdefault(key, []).append(item)

        def spread(store, l, r, t, b, item):
            for bi in range(int(math.floor(l/BK)), int(math.floor(r/BK))+1):
                for bj in range(int(math.floor(t/BK)), int(math.floor(b/BK))+1):
                    put(store, (bi, bj), item)

        for tr in board.GetTracks():
            mine = tr.GetNetname() == netname
            hw = tr.GetWidth()/2e6
            if tr.Type() == pcbnew.PCB_VIA_T:
                x, y = tr.GetStart().x/1e6, tr.GetStart().y/1e6
                item = ('c', x, y, hw)
                spread(self.allobs, x-hw-1, x+hw+1, y-hw-1, y+hw+1, item) if not mine else None
                for n in LAYERS:
                    spread(self.own[n] if mine else self.obs[n], x-hw-1, x+hw+1, y-hw-1, y+hw+1, item)
                if not mine:
                    hr = tr.GetDrill()/2e6
                    spread(self.holes, x-hr-1, x+hr+1, y-hr-1, y+hr+1, ('h', x, y, hr))
                continue
            lay = board.GetLayerName(tr.GetLayer())
            if lay not in LAYERS: continue
            x1, y1 = tr.GetStart().x/1e6, tr.GetStart().y/1e6
            x2, y2 = tr.GetEnd().x/1e6,   tr.GetEnd().y/1e6
            item = ('s', x1, y1, x2, y2, hw)
            spread(self.own[lay] if mine else self.obs[lay],
                   min(x1,x2)-hw-1, max(x1,x2)+hw+1, min(y1,y2)-hw-1, max(y1,y2)+hw+1, item)
            if not mine:
                spread(self.allobs, min(x1,x2)-hw-1, max(x1,x2)+hw+1,
                       min(y1,y2)-hw-1, max(y1,y2)+hw+1, item)

        for pd in board.GetPads():
            mine = pd.GetNetname() == netname
            bb = pd.GetBoundingBox()
            l, r = bb.GetLeft()/1e6, bb.GetRight()/1e6
            t, b = bb.GetTop()/1e6,  bb.GetBottom()/1e6
            item = ('r', l, r, t, b)
            for n in LAYERS:
                if pd.IsOnLayer(self.lid[n]):
                    spread(self.own[n] if mine else self.obs[n], l-1, r+1, t-1, b+1, item)
            if not mine:
                spread(self.allobs, l-1, r+1, t-1, b+1, item)
            hr = pd.GetDrillSizeX()/2e6
            if hr > 0:
                cx, cy = (l+r)/2, (t+b)/2
                spread(self.holes, cx-hr-1, cx+hr+1, cy-hr-1, cy+hr+1, ('h', cx, cy, hr))

    @staticmethod
    def _gap(item, x, y):
        if item[0] == 's': return seg_d(x, y, item[1], item[2], item[3], item[4]) - item[5]
        if item[0] == 'c': return math.hypot(item[1]-x, item[2]-y) - item[3]
        if item[0] == 'h': return math.hypot(item[1]-x, item[2]-y) - item[3]
        return rect_d(x, y, item[1], item[2], item[3], item[4])

    def _bucket(self, store, x, y):
        return store.get((int(math.floor(x/BK)), int(math.floor(y/BK))), ())

    def track_ok(self, lay, x, y):
        if not inside_board(x, y, HALF + 0.25): return False
        for it in self._bucket(self.obs[lay], x, y):
            if self._gap(it, x, y) < HALF + CLR: return False
        for it in self._bucket(self.holes, x, y):
            if self._gap(it, x, y) < HALF + HOLE_CLR: return False
        return True

    def via_ok(self, x, y):
        if not inside_board(x, y, VIA_R + 0.30): return False
        for it in self._bucket(self.allobs, x, y):
            if self._gap(it, x, y) < VIA_R + CLR: return False
        for it in self._bucket(self.holes, x, y):
            if self._gap(it, x, y) < VIA_DRILL_R + HOLE_CLR: return False
        return True

    def touches_own(self, lay, x, y):
        """Would a track centred here physically overlap this net's existing copper?"""
        for it in self._bucket(self.own[lay], x, y):
            if it[0] == 'r':
                if rect_d(x, y, it[1], it[2], it[3], it[4]) <= 0.0: return True
            elif self._gap(it, x, y) <= HALF:
                return True
        return False


def find_track(board, netname, layname, x, y):
    """The track object a DRC report line names, by net + layer + start point."""
    lid = board.GetLayerID(layname)
    best = None
    for t in board.GetTracks():
        if t.GetNetname() != netname or t.Type() == pcbnew.PCB_VIA_T: continue
        if t.GetLayer() != lid: continue
        # DRC names a track by whichever end it likes; matching only GetStart() misses
        # roughly half of them and the pass reports "piece not found" for a track that
        # is plainly there. Match either end, and fall back to nearest.
        for (ex, ey) in ((t.GetStart().x/1e6, t.GetStart().y/1e6),
                         (t.GetEnd().x/1e6,   t.GetEnd().y/1e6)):
            d = ((ex-x)**2 + (ey-y)**2) ** 0.5
            if d < 1e-3: return t
            if best is None or d < best[0]: best = (d, t)
    return best[1] if best and best[0] < 0.30 else None


def item_cells(tr, half=HALF):
    x1, y1 = tr.GetStart().x/1e6, tr.GetStart().y/1e6
    x2, y2 = tr.GetEnd().x/1e6,   tr.GetEnd().y/1e6
    return (x1, y1, x2, y2, tr.GetWidth()/2e6 + half)


def route_break(board, netname, a_tr, b_tr, window=9.0):
    """Rejoin two disjoint pieces of one net.

    Removing the 15 objects that clashed with J1's rotated pads cut five nets in half -
    each had been relying on a via that had to go. DRC reports these as unconnected
    track-to-track, not as an unconnected pad, so the pad-driven pass never saw them.
    Start and goal are the two named pieces specifically: using "any copper of this net"
    would make the start piece its own goal and return a zero-length route."""
    f = Field(board, netname)
    A, B = item_cells(a_tr), item_cells(b_tr)
    la = board.GetLayerName(a_tr.GetLayer()); lb = board.GetLayerName(b_tr.GetLayer())
    if la not in LAYERS or lb not in LAYERS: return None, "piece on a plane layer"
    xs = [A[0], A[2], B[0], B[2]]; ys = [A[1], A[3], B[1], B[3]]
    X0, X1 = min(xs)-window, max(xs)+window
    Y0, Y1 = min(ys)-window, max(ys)+window
    nx = int((X1-X0)/GRID)+1; ny = int((Y1-Y0)/GRID)+1
    if nx*ny > 900_000:
        return None, f"window too large ({nx}x{ny} cells)"
    pos = lambda i, j: (X0+i*GRID, Y0+j*GRID)
    free = {}
    for lay in LAYERS:
        fr = [[False]*nx for _ in range(ny)]
        for j in range(ny):
            for i in range(nx):
                x, y = pos(i, j)
                fr[j][i] = f.track_ok(lay, x, y) or f.touches_own(lay, x, y)
        free[lay] = fr
    viaok = [[f.via_ok(*pos(i, j)) for i in range(nx)] for j in range(ny)]
    def on(item, x, y): return seg_d(x, y, item[0], item[1], item[2], item[3]) <= item[4]
    ia, ib = LAYERS.index(la), LAYERS.index(lb)
    starts = [(ia, i, j) for j in range(ny) for i in range(nx) if on(A, *pos(i, j))]
    goals  = {(ib, i, j) for j in range(ny) for i in range(nx) if on(B, *pos(i, j))}
    goals -= set(starts)
    if not starts or not goals: return None, "endpoint outside window"
    gx = sum(g[1] for g in goals)/len(goals); gy = sum(g[2] for g in goals)/len(goals)
    h = lambda n: abs(n[1]-gx) + abs(n[2]-gy)
    dist = {}; prev = {}; pq = []
    for st in starts:
        if free[LAYERS[st[0]]][st[2]][st[1]]:
            dist[st] = 0; heapq.heappush(pq, (h(st), st))
    while pq:
        fs, cur = heapq.heappop(pq)
        if cur in goals:
            path = [cur]
            while path[-1] in prev: path.append(prev[path[-1]])
            path.reverse()
            return [(LAYERS[l],)+pos(i, j) for l, i, j in path], "ok"
        d = dist[cur]
        if fs - h(cur) > d: continue
        li, i, j = cur
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1)):
            ni, nj = i+di, j+dj
            if not (0 <= ni < nx and 0 <= nj < ny): continue
            if not free[LAYERS[li]][nj][ni]: continue
            nb = (li, ni, nj)
            if d+1 < dist.get(nb, 1e18):
                dist[nb] = d+1; prev[nb] = cur; heapq.heappush(pq, (d+1+h(nb), nb))
        if not viaok[j][i]: continue
        for lj in range(len(LAYERS)):
            if lj == li or not free[LAYERS[lj]][j][i]: continue
            nb = (lj, i, j)
            if d+VIA_COST < dist.get(nb, 1e18):
                dist[nb] = d+VIA_COST; prev[nb] = cur; heapq.heappush(pq, (d+VIA_COST+h(nb), nb))
    return None, "no path"


def route(board, netname, ref, pn, window=9.0, verbose=False):
    f = Field(board, netname)
    pad = next(p for p in board.FindFootprintByReference(ref).Pads() if p.GetPadName() == pn)
    bb = pad.GetBoundingBox()
    px, py = pad.GetPosition().x/1e6, pad.GetPosition().y/1e6
    start_lays = [n for n in LAYERS if pad.IsOnLayer(f.lid[n])] or [LAYERS[0]]

    # Window must hold the pad AND the nearest of the net's own copper - but not the
    # source pad, which is own-copper at distance 0. Latching onto it sized CC2's window
    # to +/-9 mm around its own start and put the only other CC2 pad, 12.6 mm away,
    # outside it: the search then reported "no reachable copper" for a net whose two
    # endpoints were simply further apart than the window.
    pl, pr = bb.GetLeft()/1e6, bb.GetRight()/1e6
    pt, pbm = bb.GetTop()/1e6, bb.GetBottom()/1e6
    tx, ty = px, py
    best = None
    for lay in LAYERS:
        for items in f.own[lay].values():
            for it in items:
                cx, cy = ((it[1], it[2]) if it[0] in 'sc' else ((it[1]+it[2])/2, (it[3]+it[4])/2))
                if pl-0.05 <= cx <= pr+0.05 and pt-0.05 <= cy <= pbm+0.05: continue
                d = math.hypot(cx-px, cy-py)
                if best is None or d < best[0]: best, tx, ty = (d, cx, cy), cx, cy
    X0 = min(px, tx) - window; X1 = max(px, tx) + window
    Y0 = min(py, ty) - window; Y1 = max(py, ty) + window
    nx = int((X1-X0)/GRID) + 1; ny = int((Y1-Y0)/GRID) + 1
    # Refuse an oversized grid rather than be OOM-killed. Four layers of nx*ny booleans
    # times three arrays: a net spanning the board needs ~5.4M cells per array, which
    # the kernel kills mid-pass and takes the whole routing run with it.
    if nx*ny > 900_000:
        return None, f"window too large ({nx}x{ny} cells)"
    pos = lambda i, j: (X0 + i*GRID, Y0 + j*GRID)
    cell = lambda x, y: (int(round((x-X0)/GRID)), int(round((y-Y0)/GRID)))

    free = {}; goal = {}; viaok = [[False]*nx for _ in range(ny)]
    for lay in LAYERS:
        fr = [[False]*nx for _ in range(ny)]; go = [[False]*nx for _ in range(ny)]
        for j in range(ny):
            for i in range(nx):
                x, y = pos(i, j)
                if f.touches_own(lay, x, y): go[j][i] = True; fr[j][i] = True
                elif f.track_ok(lay, x, y):  fr[j][i] = True
        free[lay] = fr; goal[lay] = go
    for j in range(ny):
        for i in range(nx):
            x, y = pos(i, j)
            viaok[j][i] = f.via_ok(x, y)

    # start cells: inside the source pad, on its own layer(s)
    starts = []
    for lay in start_lays:
        li = LAYERS.index(lay)
        for j in range(ny):
            for i in range(nx):
                x, y = pos(i, j)
                if rect_d(x, y, bb.GetLeft()/1e6, bb.GetRight()/1e6,
                          bb.GetTop()/1e6, bb.GetBottom()/1e6) <= 0.0:
                    starts.append((li, i, j))
    if not starts: return None, "pad outside the window"

    goals = {(LAYERS.index(l), i, j) for l in LAYERS for j in range(ny) for i in range(nx)
             if goal[l][j][i] and not any((LAYERS.index(l), i, j) == s for s in starts)}
    goals -= set(starts)
    if not goals: return None, "no reachable copper of this net"

    gset = goals
    gx = sum(g[1] for g in gset)/len(gset); gy = sum(g[2] for g in gset)/len(gset)
    h = lambda n: abs(n[1]-gx) + abs(n[2]-gy)
    dist = {}; prev = {}; pq = []
    for s in starts:
        if free[LAYERS[s[0]]][s[2]][s[1]]:
            dist[s] = 0; heapq.heappush(pq, (h(s), s))
    seen = 0
    while pq:
        fsc, cur = heapq.heappop(pq)
        if cur in gset:
            path = [cur]
            while path[-1] in prev: path.append(prev[path[-1]])
            path.reverse()
            return [(LAYERS[l],) + pos(i, j) for l, i, j in path], f"{seen} cells"
        d = dist[cur]
        if fsc - h(cur) > d: continue
        seen += 1
        li, i, j = cur
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1)):
            ni, nj = i+di, j+dj
            if not (0 <= ni < nx and 0 <= nj < ny): continue
            if not free[LAYERS[li]][nj][ni]: continue
            nb = (li, ni, nj)
            if d+1 < dist.get(nb, 1e18):
                dist[nb] = d+1; prev[nb] = cur; heapq.heappush(pq, (d+1+h(nb), nb))
        if not viaok[j][i]: continue
        for lj in range(len(LAYERS)):
            if lj == li: continue
            if not free[LAYERS[lj]][j][i]: continue
            nb = (lj, i, j)
            if d+VIA_COST < dist.get(nb, 1e18):
                dist[nb] = d+VIA_COST; prev[nb] = cur; heapq.heappush(pq, (d+VIA_COST+h(nb), nb))
    return None, "no path"


def commit(board, netname, path):
    net = board.GetNetInfo().GetNetItem(netname)
    # collapse collinear runs so the board gets a few clean segments, not hundreds
    pts = [path[0]]
    for p in path[1:]:
        if len(pts) >= 2 and pts[-1][0] == p[0] == pts[-2][0]:
            ax, ay = pts[-2][1], pts[-2][2]; bx, by = pts[-1][1], pts[-1][2]
            if abs((bx-ax)*(p[2]-ay) - (by-ay)*(p[1]-ax)) < 1e-9:
                pts[-1] = p; continue
        pts.append(p)
    prev = None
    for p in pts:
        if prev is not None:
            if prev[0] != p[0]: add_via(board, p[1], p[2], net)
            else: add_track(board, (prev[1], prev[2]), (p[1], p[2]), p[0], net)
        prev = p


def drc(path):
    subprocess.run(['kicad-cli','pcb','drc','--severity-error','--output','/tmp/nav/rf.rpt',path],
                   capture_output=True)
    txt = open('/tmp/nav/rf.rpt').read()
    return len(re.findall(r'^\[', txt, re.M)), len(re.findall(r'^\[unconnected_items\]', txt, re.M))


def main():
    apply = '--apply' in sys.argv
    only  = [a for a in sys.argv[1:] if not a.startswith('--')]
    os.makedirs('/tmp/nav', exist_ok=True)
    shutil.copy(BOARD, '/tmp/nav/rf_base.kicad_pcb')
    err, unc = drc(BOARD)
    print(f"baseline: {err} errors ({err-unc} hard), {unc} unconnected\n")
    txt = open('/tmp/nav/rf.rpt').read()
    jobs, seen = [], set()
    for m in re.finditer(r'Pad (\S+) \[([^\]]+)\] of (\w+) on', txt):
        pn, nn, ref = m.group(1), m.group(2), m.group(3)
        if (ref, pn) in seen or (only and nn not in only): continue
        seen.add((ref, pn)); jobs.append((ref, pn, nn))
    print(f"  {'pad':10s} {'net':10s} {'result':10s} {'note':16s} {'err':>4s} {'unconn':>7s}")
    print("  " + "-"*62)
    kept = 0
    for ref, pn, nn in jobs:
        t0 = time.time()
        board = pcbnew.LoadBoard(BOARD)
        path, note = route(board, nn, ref, pn)
        if not path:
            print(f"  {ref+'.'+pn:10s} {nn:10s} {'-':10s} {note:16s}"); continue
        commit(board, nn, path)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(BOARD)
        e, u = drc(BOARD)
        dt = f"{time.time()-t0:.0f}s"
        if (e-u) > (err-unc) or u >= unc:
            shutil.copy('/tmp/nav/rf_base.kicad_pcb', BOARD)
            print(f"  {ref+'.'+pn:10s} {nn:10s} {'REVERTED':10s} {dt:16s} {e:4d} {u:7d}")
        else:
            shutil.copy(BOARD, '/tmp/nav/rf_base.kicad_pcb')
            err, unc = e, u; kept += 1
            print(f"  {ref+'.'+pn:10s} {nn:10s} {'routed':10s} {dt:16s} {e:4d} {u:7d}")
    # second pass: breaks reported between two pieces of copper rather than at a pad
    txt = open('/tmp/nav/rf.rpt').read()
    breaks = []
    for blk in txt.split('[unconnected_items]')[1:]:
        its = re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): Track \[([^\]]+)\] on (\S+),', blk)
        if len(its) == 2 and its[0][2] == its[1][2]:
            if only and its[0][2] not in only: continue
            breaks.append(its)
    if breaks:
        print(f"\n  {len(breaks)} break(s) between copper pieces:")
        print("  " + "-"*62)
        for (ax, ay, nn, al), (bx, by, _, bl) in breaks:
            t0 = time.time()
            board = pcbnew.LoadBoard(BOARD)
            a = find_track(board, nn, al, float(ax), float(ay))
            b = find_track(board, nn, bl, float(bx), float(by))
            if a is None or b is None:
                print(f"  {nn:10s} {'-':10s} piece not found"); continue
            path, note = route_break(board, nn, a, b)
            if not path:
                print(f"  {nn:10s} {'-':10s} {note}"); continue
            commit(board, nn, path)
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            board.Save(BOARD)
            e, u = drc(BOARD)
            dt = f"{time.time()-t0:.0f}s"
            if (e-u) > (err-unc) or u >= unc:
                shutil.copy('/tmp/nav/rf_base.kicad_pcb', BOARD)
                print(f"  {nn:10s} {'REVERTED':10s} {dt:6s} {e:4d} err {u:4d} unconn")
            else:
                shutil.copy(BOARD, '/tmp/nav/rf_base.kicad_pcb')
                err, unc = e, u; kept += 1
                print(f"  {nn:10s} {'rejoined':10s} {dt:6s} {e:4d} err {u:4d} unconn")
    print("  " + "-"*62)
    print(f"  kept {kept} -> {err} errors ({err-unc} hard), {unc} unconnected")
    sys.stdout.flush(); os._exit(0)

main()
