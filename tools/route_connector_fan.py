#!/usr/bin/env python3
"""
Re-connect the nets left dangling when J1 and J2 were rotated to face off-board.

Both connectors were fitted with their mating faces pointing INTO the board. Rotating
them 180 degrees moved every pad, and on J2 it also reversed the pad order along y, so
the seven ESC nets have to fan back out to routing that starts in a different order.

The long-haul routing on In2/In3 was kept - it is the expensive part and regenerating
it would mean stripping the whole board - so each net only needs a short hop from its
new pad to the copper that survived.

Two things this does that tools/route.py cannot:

  1. route_to_any() there steps between layers with `other = 1 - li`, which is a
     two-layer assumption left over from when the router only used F.Cu and B.Cu.
     SIG_LAYERS has been four layers for a long time, so that expression can only ever
     hop F.Cu <-> In2.Cu and silently cannot reach In3.Cu or B.Cu. Here a via may go
     to any other signal layer.

  2. commit() stamps a via's keep-out on layers 0 and 1 only, for the same reason.
     Here it stamps every layer the via passes through.

Every net is committed, written, and checked by whole-board DRC on its own. A net that
raises the error count is reverted and the next one is tried against the board as it
was before it - so a failure costs nothing but that net.

Usage: python3 tools/route_connector_fan.py [--apply]
"""
import os, sys, math, heapq, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route
from route import (Router, SIG_LAYERS, add_via, add_track, VIA_D, CLEAR, TRACK_W,
                   GRID_MM, ROUTE_VIA_CLEAR, TOMM, inside_board)

BOARD = 'NAVCORE-SoOP.kicad_pcb'


class FanRouter(Router):
    """Router with two of route.py's own corrections applied to the parts that never got them.

    route.py already argues both of these against itself and then only half-applies them:

      * ROUTE_VIA_CLEAR was cut from an invented 0.15 to the board's real 0.1016 with
        the note "DRC is the arbiter, not a hand-picked constant". TRK_KEEP still adds
        0.15, so every committed track projects a 0.63 mm no-go corridor where the rules
        need 0.41. Where two such corridors overlap the cells go contested and block a
        third net outright - which is the wall sealing J2's pads off to the east.

      * _stamp_rect was changed to stamp pads as real rectangles because "a circumscribed
        circle around a 1.6x0.3 mm LQFP pad blocks 0.81 mm ... and makes escape routing
        impossible". _mark_via_legal still uses circumscribed circles, so J2's 1.55x0.60
        pads each veto vias within 0.83 mm instead of their true outline - which is why
        via_ok is empty for most of the fan.

    Both are relaxed to the real design rules here. Nothing is trusted on that basis:
    every net is still committed and judged by whole-board DRC, and reverted if it
    raises a violation.
    """
    def __init__(self, board):
        route.TRK_KEEP = TRACK_W/2 + CLEAR + TRACK_W/2 + GRID_MM/2
        super().__init__(board)

    def _mark_via_legal(self):
        need = VIA_D/2 + ROUTE_VIA_CLEAR
        BK = 2.0
        rects, circs = {}, {}
        def addr(l, r, t, bt):
            for bi in range(int(l/BK)-1, int(r/BK)+2):
                for bj in range(int(t/BK)-1, int(bt/BK)+2):
                    rects.setdefault((bi, bj), []).append((l, r, t, bt))
        def addc(x, y, rr):
            bi, bj = int(x/BK), int(y/BK)
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    circs.setdefault((bi+di, bj+dj), []).append((x, y, rr))
        for fp in self.b.GetFootprints():
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                addr(TOMM(bb.GetLeft()), TOMM(bb.GetRight()), TOMM(bb.GetTop()), TOMM(bb.GetBottom()))
        for t in self.b.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                p = t.GetPosition(); addc(TOMM(p.x), TOMM(p.y), VIA_D/2)
            else:
                a, c = t.GetStart(), t.GetEnd()
                ax, ay, cx, cy = TOMM(a.x), TOMM(a.y), TOMM(c.x), TOMM(c.y)
                n = max(1, int(math.hypot(cx-ax, cy-ay)/0.4) + 1)
                for k in range(n+1):
                    addc(ax + (cx-ax)*k/n, ay + (cy-ay)*k/n, TRACK_W/2)
        for j in range(self.ny):
            for i in range(self.nx):
                x, y = self.pos(i, j)
                if not inside_board(x, y, VIA_D/2 + 0.35):
                    self.via_ok[j][i] = False; continue
                bad = False
                for (l, r, t, bt) in rects.get((int(x/BK), int(y/BK)), ()):
                    dx = max(l - x, 0.0, x - r); dy = max(t - y, 0.0, y - bt)
                    if math.hypot(dx, dy) < need:
                        bad = True; break
                if not bad:
                    for ox, oy, orad in circs.get((int(x/BK), int(y/BK)), ()):
                        if math.hypot(ox-x, oy-y) < need + orad:
                            bad = True; break
                if bad: self.via_ok[j][i] = False

    def route_to_any(self, code, a, goals_cells, via_cost=None, start_layer=None):
        """A* to any cell of the net's existing copper, over ALL signal layers."""
        if via_cost is not None: self.via_cost = via_cost
        nl = len(self.lay)
        layers = range(nl) if start_layer is None else [start_layer]
        goals = set(goals_cells)
        if not goals: return None
        gx = sum(g[1] for g in goals) / len(goals)
        gy = sum(g[2] for g in goals) / len(goals)
        dist, prev, pq = {}, {}, []
        for li in layers:
            st = (li,) + self.cell(*a)
            if self._free(st[0], st[1], st[2], code):
                dist[st] = 0; heapq.heappush(pq, (0, st))
        h = lambda n: abs(n[1] - gx) + abs(n[2] - gy)
        while pq:
            f, cur = heapq.heappop(pq)
            if cur in goals:
                path = [cur]
                while path[-1] in prev: path.append(prev[path[-1]])
                return [(p[0],) + self.pos(p[1], p[2]) for p in reversed(path)]
            d = dist[cur]
            if f - h(cur) > d: continue
            li, i, j = cur
            for di, dj in ((1,0),(-1,0),(0,1),(0,-1)):
                if not self._free(li, i+di, j+dj, code): continue
                nb = (li, i+di, j+dj); nd = d + 1
                if nd < dist.get(nb, 1e18):
                    dist[nb] = nd; prev[nb] = cur
                    heapq.heappush(pq, (nd + h(nb), nb))
            if not self.via_ok[j][i]: continue
            for other in range(nl):                       # <-- was `1 - li`
                if other == li: continue
                nb = (other, i, j)
                if not self._free(other, i, j, code): continue
                if dist.get(nb, 1e18) > d + self.via_cost:
                    dist[nb] = d + self.via_cost; prev[nb] = cur
                    heapq.heappush(pq, (d + self.via_cost + h(nb), nb))
        return None

    def commit(self, code, net, path):
        prev = None
        for (li, x, y) in path:
            if prev is not None:
                if prev[0] != li:
                    add_via(self.b, x, y, net)
                    r = VIA_D/2 + CLEAR + TRACK_W/2 + GRID_MM/2 + 0.05
                    for k in range(len(self.lay)):        # <-- was layers 0 and 1 only
                        self._stamp(k, x, y, r, code)
                    ci, cj = self.cell(x, y); k = int((VIA_D + ROUTE_VIA_CLEAR)/GRID_MM) + 1
                    for jj in range(max(0, cj-k), min(self.ny, cj+k+1)):
                        for ii in range(max(0, ci-k), min(self.nx, ci+k+1)):
                            self.via_ok[jj][ii] = False
                else:
                    add_track(self.b, (prev[1], prev[2]), (x, y), SIG_LAYERS[li], net)
                    self._stamp(li, x, y, route.TRK_KEEP, code)
            prev = (li, x, y)


def drc_errors(path):
    subprocess.run(['kicad-cli','pcb','drc','--severity-error','--output','/tmp/nav/fan.rpt',path],
                   capture_output=True)
    txt = open('/tmp/nav/fan.rpt').read()
    errs = len(re.findall(r'^\[', txt, re.M))
    unc  = len(re.findall(r'^\[unconnected_items\]', txt, re.M))
    return errs, unc


def net_copper_points(b, netname, skip=None):
    """Every point of this net's copper, EXCLUDING the pad we are routing from.

    Leaving that pad in makes its own cells goals, so A* finishes on the cell it
    started on: a zero-length 'route' that reports success and connects nothing.
    Every one of the first 13 attempts failed this way."""
    pts = []
    for t in b.GetTracks():
        if t.GetNetname() != netname: continue
        pts.append((t.GetStart().x/1e6, t.GetStart().y/1e6))
        pts.append((t.GetEnd().x/1e6,   t.GetEnd().y/1e6))
    for p in b.GetPads():
        if p.GetNetname() != netname: continue
        if skip and (p.GetParentFootprint().GetReference(), p.GetPadName()) == skip: continue
        pts.append((p.GetPosition().x/1e6, p.GetPosition().y/1e6))
    return pts


def pad_cells(r, pad):
    """Grid cells covered by one pad, so they can be removed from the goal set."""
    bb = pad.GetBoundingBox()
    l, rt = bb.GetLeft()/1e6, bb.GetRight()/1e6
    t, bt = bb.GetTop()/1e6, bb.GetBottom()/1e6
    i0, j0 = r.cell(l, t); i1, j1 = r.cell(rt, bt)
    out = set()
    for j in range(j0-1, j1+2):
        for i in range(i0-1, i1+2):
            for li in range(len(r.lay)):
                out.add((li, i, j))
    return out


def snap_point(b, netname, layer_name, x, y, skip=None):
    """Nearest point of this net's REAL copper to (x, y).

    cells_of_net() returns the cells of a track's keep-out halo, which reaches
    TRK_KEEP ~ 0.31 mm from the centreline - well outside the 0.1 mm track itself. A
    via committed on a goal cell can therefore sit beside the track it is supposed to
    land on and connect nothing, which is what happened to five of the first attempts:
    they committed copper, raised no DRC error, and left the pad unconnected.

    So the route's last point is snapped onto the copper itself before committing.
    """
    lid = b.GetLayerID(layer_name)
    best = None
    def cons(px, py):
        nonlocal best
        d = math.hypot(px-x, py-y)
        if best is None or d < best[0]: best = (d, px, py)
    for t in b.GetTracks():
        if t.GetNetname() != netname: continue
        if t.Type() == pcbnew.PCB_VIA_T:
            if t.IsOnLayer(lid): cons(t.GetStart().x/1e6, t.GetStart().y/1e6)
            continue
        if t.GetLayer() != lid: continue
        ax, ay = t.GetStart().x/1e6, t.GetStart().y/1e6
        bx, by = t.GetEnd().x/1e6,   t.GetEnd().y/1e6
        dx, dy = bx-ax, by-ay
        L2 = dx*dx + dy*dy
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x-ax)*dx + (y-ay)*dy)/L2))
        cons(ax+u*dx, ay+u*dy)
    for pd in b.GetPads():
        if pd.GetNetname() != netname or not pd.IsOnLayer(lid): continue
        if skip and (pd.GetParentFootprint().GetReference(), pd.GetPadName()) == skip: continue
        cons(pd.GetPosition().x/1e6, pd.GetPosition().y/1e6)
    return best


def main():
    apply = '--apply' in sys.argv
    os.makedirs('/tmp/nav', exist_ok=True)
    shutil.copy(BOARD, '/tmp/nav/fan_base.kicad_pcb')
    base_err, base_unc = drc_errors(BOARD)
    print(f"baseline: {base_err} errors, {base_unc} unconnected\n")

    # Read the jobs from DRC itself rather than a fixed list. The list changes as
    # nets get routed, and a pad that would not route from one end often routes from
    # the other - so both ends of every unconnected net are offered, hardest first.
    txt = open('/tmp/nav/fan.rpt').read()
    seen, JOBS = set(), []
    for m in re.finditer(r'Pad (\S+) \[([^\]]+)\] of (\w+) on', txt):
        pn, netname, ref = m.group(1), m.group(2), m.group(3)
        if (ref, pn) in seen: continue
        seen.add((ref, pn)); JOBS.append((ref, pn, netname))
    if not JOBS:
        print("nothing unconnected"); sys.stdout.flush(); os._exit(0)
    print(f"{len(JOBS)} unconnected pads to attempt\n")

    print(f"  {'#':>2s} {'pad':10s} {'net':11s} {'result':12s} {'err':>4s} {'unconn':>7s}")
    print("  " + "-"*52)
    kept = 0
    for k, (ref, pn, netname) in enumerate(JOBS, 1):
        b = pcbnew.LoadBoard(BOARD)
        fp = b.FindFootprintByReference(ref)
        pad = next((p for p in fp.Pads() if p.GetPadName() == pn), None)
        if pad is None:
            print(f"  {k:2d} {ref+'.'+pn:10s} {netname:11s} {'no such pad':12s}"); continue
        net = pad.GetNet(); code = net.GetNetCode()
        a = (pad.GetPosition().x/1e6, pad.GetPosition().y/1e6)
        start_li = next((i for i, ln in enumerate(SIG_LAYERS) if pad.IsOnLayer(b.GetLayerID(ln))), 0)

        r = FanRouter(b)
        all_goals = r.cells_of_net(code, net_copper_points(b, netname, skip=(ref, pn)), radius=2)
        all_goals -= pad_cells(r, pad)
        if not all_goals:
            print(f"  {k:2d} {ref+'.'+pn:10s} {netname:11s} {'no target':12s}"); continue

        # Aim at the NEAREST copper of the net, not all of it. route_to_any's heuristic
        # steers toward the CENTROID of the goal set, so offering a net's whole run of
        # copper aims the search at its middle: M3's first accepted path wandered 11 mm
        # east through six layer changes to land near U1 when its own via sat 2.9 mm
        # away, and laid up 90 clearance violations doing it. Widen the radius only if
        # nothing close is reachable.
        ci, cj = r.cell(*a)
        def within(radius_mm):
            n = radius_mm / GRID_MM
            return {g for g in all_goals if math.hypot(g[1]-ci, g[2]-cj) <= n}
        path = None
        for radius in (2.0, 4.0, 8.0, None):
            goals = all_goals if radius is None else within(radius)
            if not goals: continue
            for vc in (12, 6, 24):
                path = r.route_to_any(code, a, goals, via_cost=vc, start_layer=start_li)
                if path: break
            if path: break
        if not path:
            print(f"  {k:2d} {ref+'.'+pn:10s} {netname:11s} {'no path':12s}")
            continue
        li_end = path[-1][0]
        snap = snap_point(b, netname, SIG_LAYERS[li_end], path[-1][1], path[-1][2], skip=(ref, pn))
        if snap and snap[0] > 1e-6:
            path = path + [(li_end, snap[1], snap[2])]
        r.commit(code, net, path)
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(BOARD)
        err, unc = drc_errors(BOARD)
        if (err - unc) > (base_err - base_unc) or unc >= base_unc:
            shutil.copy('/tmp/nav/fan_base.kicad_pcb', BOARD)
            print(f"  {k:2d} {ref+'.'+pn:10s} {netname:11s} {'ROLLBACK':12s} {err:4d} {unc:7d}")
        else:
            shutil.copy(BOARD, '/tmp/nav/fan_base.kicad_pcb')
            base_err, base_unc = err, unc
            kept += 1
            print(f"  {k:2d} {ref+'.'+pn:10s} {netname:11s} {'routed':12s} {err:4d} {unc:7d}")
    print("  " + "-"*52)
    print(f"  kept {kept}/{len(JOBS)} -> {base_err} errors, {base_unc} unconnected")
    sys.stdout.flush(); os._exit(0)

main()
