#!/usr/bin/env python3
"""
Push existing traces aside to make room, instead of only ever adding copper.

Every other closing tool in this directory searches for somewhere a via or a trace will
fit and gives up when nothing does. That is not what a person does at this stage of a
layout: they grab the trace that is in the way and drag it over. All the remaining
unconnected items are of exactly that kind - +5V's F.Cu trace has TOF_XSHUT running
0.053 mm beneath it on In2.Cu for the whole 14.75 mm, so EVERY via position along it is
shadowed by the same single trace, always short by the same 0.32 mm. No amount of
searching finds a gap, because there is no gap to find; the trace has to move.

A shove keeps both endpoints of the victim exactly where they were - so the victim's own
connectivity cannot change - and replaces its middle with a local detour: a ramp out, a
flat run past the obstruction, and a ramp back. That is the same shape a person draws by
hand, and it means the shove is confined to a couple of millimetres rather than dragging
a 15 mm trace across the board.

The victim is a CHAIN, never a single segment. tools/route.py emits one track per
0.0625 mm grid cell, so most "traces" on this board are hundreds of one-cell stubs. A
detour needs room to ramp out and back, and a 0.0625 mm segment has none - shoving
segment by segment failed on every single candidate for that reason alone. So the
segments are first walked into polylines (same net, same layer, split at junctions and
vias, exactly as tools/tidy_tracks.py does), the detour is cut into the polyline by
arc length, and the whole chain is rewritten. Replacing the staircase inside the detour
window with four points also leaves the trace tidier than it was.

Order of preference, so the smallest change that works is the one taken:
  1. no shove at all      - a via position where nothing is in the way
  2. shove one trace      - and by the least offset that clears
  3. shove several        - the push cascades through a bundle until it reaches slack
  4. move the net's own trace - see --free-via below

--free-via stops insisting that the via sit on the existing trace. Both remaining power
connections are blocked by the SAME bundle of five traces on In2.Cu, which is boxed in
by an I2C1_SCL via and cannot be shoved anywhere. Pinning the via to a trace that
happens to run directly over that bundle is self-imposed: the honest move is to find a
spot nearby where a via is legal and run a short piece of copper to it on each layer.
That is moving your own trace rather than someone else's, and it is the first thing a
person would try.

Refused outright: pads and vias are never shoved. Moving a pad moves a part, and moving
a via breaks whatever layer transition it exists to make. If a pad or a via is in the
way, the candidate position is rejected rather than worked around.

Everything is verified by whole-board DRC and rolled back per attempt - a shove that
closes one connection while opening another is not progress.

Usage:  python3 tools/shove.py [--apply] [--only NET] [--max-shove MM]
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import deque
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/shove_backup.kicad_pcb"
RPT   = "/tmp/nav/shove.rpt"
TIERS = [(0.45, 0.20), (0.50, 0.25), (0.60, 0.30)]
TOMM  = route.TOMM

# How far a detour may bow out, and how long the ramps and the flat section are. The
# ramp is at least as long as the offset so the corner never comes out sharper than 45
# degrees - sharp spikes are an acid trap in etching and look wrong on a board.
MAX_OFFSET = 1.20
FLAT       = 0.80
# Detour widths to try, narrowest first. A wide detour disturbs more of the board and
# runs into more of it: the last ground island needed BUCK_EN moved by 0.085 mm, and
# the only thing stopping it was that a 1.1 mm-long detour window hit the BUCK9_COMP2
# pad next door. A 0.5 mm window slips past. Narrowest first also means the smallest
# change that works is the one taken.
FLATS      = (0.20, 0.35, 0.55, 0.80, 1.20)
MARGIN     = 0.02      # a hair past the design rule, so rounding cannot fail DRC


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


# ---------------------------------------------------------------- board geometry

COPPER = ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu")


class Shape:
    """One obstacle, keeping the layers it occupies and the object it came from.

    `lset` is the fix for the thing that quietly defeated every earlier tool here:
    route.obstacle_shapes() models a pad with no layer at all, so a surface-mount pad
    on F.Cu blocks an inner-layer trace it cannot physically touch. Under a part like
    U7 that is the difference between "no via position exists" and a dozen clear ones.
    A via is drilled through the whole stack, so it is checked against every layer; a
    trace is only checked against copper that shares its layer.
    """
    __slots__ = ("geom", "kind", "net", "obj", "layer", "width", "p1", "p2", "lset")

    def __init__(self, geom, kind, net, obj=None, layer=None,
                 width=None, p1=None, p2=None, lset=None):
        self.geom, self.kind, self.net, self.obj = geom, kind, net, obj
        self.layer, self.width, self.p1, self.p2 = layer, width, p1, p2
        self.lset = lset if lset is not None else frozenset(COPPER)

    @property
    def shovable(self):
        return self.kind == "track"

    def key(self):
        return (self.net, self.layer, self.p1, self.p2)


def shapes_of(board, exclude_net=None, near=None, radius=6.0):
    """Every piece of copper as exact geometry, tagged with its source."""
    out = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNet()
            nm = n.GetNetname() if n else ""
            if exclude_net is not None and nm == exclude_net:
                continue
            bb = pad.GetBoundingBox()
            ls = frozenset(L for L in COPPER
                           if pad.IsOnLayer(board.GetLayerID(L)))
            out.append(Shape(("rect", TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                              TOMM(bb.GetRight()), TOMM(bb.GetBottom())),
                             "pad", nm, lset=ls))
    for t in board.GetTracks():
        n = t.GetNet()
        nm = n.GetNetname() if n else ""
        if exclude_net is not None and nm == exclude_net:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            try:
                r = TOMM(t.GetWidth(board.GetLayerID("F.Cu"))) / 2
            except TypeError:
                r = route.VIA_D / 2
            out.append(Shape(("cap", TOMM(p.x), TOMM(p.y), TOMM(p.x), TOMM(p.y), r),
                             "via", nm))
        else:
            a, c = t.GetStart(), t.GetEnd()
            p1, p2 = (TOMM(a.x), TOMM(a.y)), (TOMM(c.x), TOMM(c.y))
            w = TOMM(t.GetWidth())
            lname = board.GetLayerName(t.GetLayer())
            out.append(Shape(("cap", p1[0], p1[1], p2[0], p2[1], w / 2),
                             "track", nm, t, lname, w, p1, p2,
                             lset=frozenset([lname])))
    if near is not None:
        out = [s for s in out if route.gap_to_shape(near[0], near[1], s.geom) < radius]
    return out


class ShapeIndex:
    """Uniform-grid bucket index over shapes, so a point query is not O(all copper).

    Without it a point test walks every piece of copper on the board. The island escape
    search does exactly that once per grid cell - 200k cells against 10k shapes is two
    billion distance calculations and simply does not finish; the first attempt was
    killed at 25 minutes having printed nothing. Bucketing by 1 mm turns each query
    into a handful of candidates.
    """
    CELL = 1.0

    def __init__(self, shapes):
        self.b = {}
        for sh in shapes:
            g = sh.geom
            if g[0] == "rect":
                x1, y1, x2, y2 = g[1], g[2], g[3], g[4]
            else:
                x1, y1 = min(g[1], g[3]) - g[5], min(g[2], g[4]) - g[5]
                x2, y2 = max(g[1], g[3]) + g[5], max(g[2], g[4]) + g[5]
            for j in range(int(y1//self.CELL), int(y2//self.CELL) + 1):
                for i in range(int(x1//self.CELL), int(x2//self.CELL) + 1):
                    self.b.setdefault((i, j), []).append(sh)

    def near(self, x, y, r):
        out, seen = [], set()
        for j in range(int((y-r)//self.CELL), int((y+r)//self.CELL) + 1):
            for i in range(int((x-r)//self.CELL), int((x+r)//self.CELL) + 1):
                for sh in self.b.get((i, j), ()):
                    if id(sh) not in seen:
                        seen.add(id(sh)); out.append(sh)
        return out


def seg_gap(p, a, b, r):
    """Distance from point p to a capsule (segment a-b, radius r)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx*dx + dy*dy
    if L2 < 1e-12:
        d = math.hypot(p[0] - a[0], p[1] - a[1])
    else:
        t = max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / L2))
        d = math.hypot(p[0] - (a[0] + t*dx), p[1] - (a[1] + t*dy))
    return max(0.0, d - r)


# ---------------------------------------------------------------- chains

Q = lambda v: round(v / 1000.0)          # 1 um, for matching track endpoints


def build_chains(board):
    """Same-net same-layer polylines, split at junctions and vias.

    Duplicated segments are dropped first: they double the apparent degree of their
    endpoints, so the walker sees a junction where there is really a plain joint and
    stops a chain that should have carried on.
    """
    segs, seen = [], set()
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        a, b = t.GetStart(), t.GetEnd()
        if a.x == b.x and a.y == b.y:
            continue
        n = t.GetNet()
        code = n.GetNetCode() if n else 0
        k = (code, t.GetLayer(), t.GetWidth(),
             tuple(sorted([(Q(a.x), Q(a.y)), (Q(b.x), Q(b.y))])))
        if k in seen:
            continue
        seen.add(k)
        segs.append((code, n.GetNetname() if n else "", t.GetLayer(),
                     board.GetLayerName(t.GetLayer()), TOMM(t.GetWidth()),
                     (TOMM(a.x), TOMM(a.y)), (TOMM(b.x), TOMM(b.y))))

    via_pts = set()
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            via_pts.add((Q(p.x), Q(p.y)))

    inc = {}
    for i, sg in enumerate(segs):
        for p in (sg[5], sg[6]):
            inc.setdefault((sg[0], sg[2], Q(p[0]*1e6), Q(p[1]*1e6)), []).append(i)

    def key(code, lay, p):
        return (code, lay, Q(p[0]*1e6), Q(p[1]*1e6))

    def junction(code, lay, p):
        k = key(code, lay, p)
        return len(inc.get(k, [])) != 2 or (k[2], k[3]) in via_pts

    used, chains = set(), []
    for i, sg in enumerate(segs):
        if i in used:
            continue
        code, net, lay, layname, w, a, b = sg
        pts = [a, b]
        used.add(i)
        for end in (0, 1):
            while True:
                tip = pts[0] if end == 0 else pts[-1]
                if junction(code, lay, tip):
                    break
                nxt = [j for j in inc[key(code, lay, tip)] if j not in used]
                if not nxt:
                    break
                j = nxt[0]
                used.add(j)
                ja, jb = segs[j][5], segs[j][6]
                far = jb if (Q(ja[0]*1e6), Q(ja[1]*1e6)) == \
                            (Q(tip[0]*1e6), Q(tip[1]*1e6)) else ja
                pts.insert(0, far) if end == 0 else pts.append(far)
        chains.append({"net": net, "layer": layname, "lid": lay,
                       "width": w, "pts": pts})
    # index every segment of every chain so a blocker can find the chain it belongs to
    index = {}
    for ci, ch in enumerate(chains):
        for i in range(len(ch["pts"]) - 1):
            p, q = ch["pts"][i], ch["pts"][i+1]
            index[(ch["net"], ch["layer"],
                   tuple(sorted([(Q(p[0]*1e6), Q(p[1]*1e6)),
                                 (Q(q[0]*1e6), Q(q[1]*1e6))])))] = ci
    return chains, index


def chain_of(index, sh):
    if sh.p1 is None or sh.layer is None:
        return None                # a detour planned in this round, not a real track
    k = (sh.net, sh.layer,
         tuple(sorted([(Q(sh.p1[0]*1e6), Q(sh.p1[1]*1e6)),
                       (Q(sh.p2[0]*1e6), Q(sh.p2[1]*1e6))])))
    return index.get(k)


def arclen(pts):
    s, out = 0.0, [0.0]
    for i in range(len(pts) - 1):
        s += math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
        out.append(s)
    return out


def at_s(pts, ss, target):
    """Point at arc length `target` along the polyline."""
    for i in range(len(pts) - 1):
        if ss[i] <= target <= ss[i+1]:
            span = ss[i+1] - ss[i]
            f = 0.0 if span < 1e-12 else (target - ss[i]) / span
            return (pts[i][0] + (pts[i+1][0]-pts[i][0])*f,
                    pts[i][1] + (pts[i+1][1]-pts[i][1])*f)
    return pts[-1]


def closest_on(pts, v):
    """(arc length, point, distance) of the closest point on the polyline to v."""
    ss = arclen(pts)
    best = (0.0, pts[0], 1e9)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i+1]
        dx, dy = b[0]-a[0], b[1]-a[1]
        L2 = dx*dx + dy*dy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0,
            ((v[0]-a[0])*dx + (v[1]-a[1])*dy) / L2))
        px, py = a[0] + t*dx, a[1] + t*dy
        d = math.hypot(v[0]-px, v[1]-py)
        if d < best[2]:
            best = (ss[i] + t*math.hypot(dx, dy), (px, py), d)
    return best


def shove_chain(pts, via, off, flip=False, flat=FLAT):
    """Rewrite a chain so it bows `off` mm clear of `via`, endpoints untouched.

    Returns (whole_chain, detour_only). Only the detour is new geometry - the head and
    tail are untouched copper that was already legal - so a caller checking clearance
    need only check the detour. Checking the whole chain instead meant re-validating a
    32 mm trace at 0.02 mm for every one of the ~230 offset/width combinations tried,
    which is where the search was spending all its time.
    """
    ss = arclen(pts)
    L = ss[-1]
    s_star, cp, dist = closest_on(pts, via)
    dx, dy = cp[0]-via[0], cp[1]-via[1]
    n = math.hypot(dx, dy)
    if n < 1e-9:
        # the via sits exactly on the chain; push along the local perpendicular
        a, b = pts[0], pts[-1]
        ux, uy = b[0]-a[0], b[1]-a[1]
        n2 = math.hypot(ux, uy) or 1.0
        dx, dy, n = -uy/n2, ux/n2, 1.0
    d = (-dx/n, -dy/n) if flip else (dx/n, dy/n)
    ramp = max(off, 0.15)
    s0, s1 = s_star - flat/2 - ramp, s_star + flat/2 + ramp
    if s0 < 0.02 or s1 > L - 0.02:
        return None                     # no room to ramp without dragging an endpoint
    m0, m1 = at_s(pts, ss, s_star - flat/2), at_s(pts, ss, s_star + flat/2)
    head = [p for p, s in zip(pts, ss) if s < s0]
    tail = [p for p, s in zip(pts, ss) if s > s1]
    detour = [at_s(pts, ss, s0),
              (m0[0] + d[0]*off, m0[1] + d[1]*off),
              (m1[0] + d[0]*off, m1[1] + d[1]*off),
              at_s(pts, ss, s1)]
    out = head + detour + tail
    # drop any duplicate points the slicing may have produced
    clean = [out[0]]
    for p in out[1:]:
        if math.hypot(p[0]-clean[-1][0], p[1]-clean[-1][1]) > 1e-6:
            clean.append(p)
    if len(clean) < 2:
        return None
    return clean, detour


# ---------------------------------------------------------------- the shove itself

def _walk(pts, step=0.02):
    """Sample points along a polyline."""
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i+1]
        L = math.hypot(b[0]-a[0], b[1]-a[1])
        n = max(2, int(L / step))
        for k in range(n + 1):
            f = k / n
            yield a[0] + (b[0]-a[0])*f, a[1] + (b[1]-a[1])*f


def polyline_clear(pts, others, width, extra=(), layer=None):
    """Is every point along this polyline clear of `others` (and `extra` shapes)?

    `layer` restricts the check to copper that actually shares the trace's layer;
    `extra` shapes are raw geometry that always applies (the via being made room for,
    which is drilled through every layer).
    """
    if layer is not None:
        others = [s for s in others if layer in s.lset]
    need = width/2 + route.CLEAR + MARGIN
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i+1]
        L = math.hypot(b[0]-a[0], b[1]-a[1])
        steps = max(2, int(L / 0.02))
        for k in range(steps + 1):
            f = k / steps
            x, y = a[0] + (b[0]-a[0])*f, a[1] + (b[1]-a[1])*f
            if not route.inside_board(x, y, width/2 + 0.30):
                return False
            for s in others:
                if route.gap_to_shape(x, y, s.geom) < need:
                    return False
            for g in extra:
                if route.gap_to_shape(x, y, g) < need:
                    return False
    return True


def polyline_hits(pts, others, width, extra=(), layer=None, index=None,
                  skip_net=None):
    """Which of `others` the polyline collides with. Empty means it is clear.

    `index` is a ShapeIndex over `others`. Without one this walks every shape at every
    sampled point, which for a 20 mm chain against 6800 shapes is millions of distance
    calls per offset tried - the search does not finish. Pass the index.
    """
    need = width/2 + route.CLEAR + MARGIN
    hit, seen = [], set()
    for x, y in _walk(pts):
        if not route.inside_board(x, y, width/2 + 0.30):
            return [None]                          # off the board: unfixable
        pool = index.near(x, y, need + 1.0) if index is not None else others
        for sh in pool:
            if id(sh) in seen or (layer is not None and layer not in sh.lset) \
               or (skip_net is not None and sh.net == skip_net):
                continue
            if route.gap_to_shape(x, y, sh.geom) < need:
                seen.add(id(sh)); hit.append(sh)
        for g in extra:
            if route.gap_to_shape(x, y, g) < need:
                return [None]                      # hits the new copper it must clear
    return hit


def plan_shoves(via, via_d, blockers, all_shapes, chains, index, connector=None,
                why=None, max_chains=10):
    """Work out how to move every blocker out of the way of `via`.

    Blockers are resolved to the CHAIN each belongs to and deduplicated, so a trace
    made of forty one-cell segments is shoved once rather than forty times. Returns a
    list of (chain_index, new_points, offset) or None if any of them cannot be moved.
    """
    want = set()
    for b in blockers:
        if not b.shovable:
            return None
        ci = chain_of(index, b)
        if ci is None:
            return None
        want.add(ci)

    extra = [("cap", via[0], via[1], via[0], via[1], via_d/2)]
    if connector:
        extra.append(("cap", connector[0][0], connector[0][1],
                      connector[1][0], connector[1][1], route.TRACK_W/2))

    # Cascade. A trace pushed aside lands on its neighbour, so the neighbour has to
    # move too - that is how a bundle of parallel traces gets shoved as a bundle, which
    # is exactly the situation here: TOF_INT and TOF_XSHUT run 0.256 mm apart on In2.Cu
    # with only 0.05 mm of slack between them. Each round adds whoever the last round
    # ran into and starts again, so the push propagates outwards until it reaches slack.
    for _round in range(max_chains):
        rest = [sh for sh in all_shapes
                if not (sh.shovable and chain_of(index, sh) in want)]
        rest_idx = ShapeIndex(rest)
        # nearest to the via first: it is pushed least, and the ones behind it are
        # pushed further to stay clear of it.
        order = sorted(want, key=lambda ci: closest_on(chains[ci]["pts"], via)[2])
        plans, placed, blocked_by, stuck = [], [], None, None
        for idx, ci in enumerate(order):
            ch = chains[ci]
            # Copper on the chain's OWN net is not an obstacle to it - two pieces of
            # the same net may touch, and DRC has no clearance rule between them. Left
            # in, a chain is "held" by the very via it terminates on, which stopped
            # every cascade dead at the second trace.
            mine = ch["net"]
            near = rest                     # same-net shapes are skipped below
            side = [sh for sh in placed if sh.net != mine]
            got, hits = None, []
            for base_flat in FLATS:
                # each chain further out needs a wider flat so it clears the whole
                # detour of the one inside it, ramps included
                flat = base_flat + idx * 0.9
                for flip in (False, True):
                    off = 0.10
                    while off <= MAX_OFFSET:
                        res = shove_chain(ch["pts"], via, off, flip=flip, flat=flat)
                        if res is None:
                            break
                        pts, detour = res
                        # only the detour is new copper; the rest of the chain has not
                        # moved and was legal already
                        h = polyline_hits(detour, near, ch["width"], extra,
                                          layer=ch["layer"], index=rest_idx,
                                          skip_net=mine)
                        h += [sh for sh in polyline_hits(detour, side, ch["width"],
                                                         layer=ch["layer"])
                              if sh is not None]
                        if any(sh is None for sh in h):
                            h = [None]
                        if not h:
                            got = (ci, pts, off)
                            break
                        hits = h
                        off += 0.05
                    if got:
                        break
                if got:
                    break
            if not got:
                stuck, blocked_by = ch, hits
                break
            plans.append(got)
            for i in range(len(got[1]) - 1):
                placed.append(Shape(("cap", got[1][i][0], got[1][i][1],
                                     got[1][i+1][0], got[1][i+1][1], ch["width"]/2),
                                    "track", ch["net"],
                                    lset=frozenset([ch["layer"]])))
        if stuck is None:
            return plans
        # who stopped it? if they can move too, add them and cascade another round.
        more = set()
        for sh in blocked_by:
            if sh is None or not sh.shovable:
                more = None
                break
            ci = chain_of(index, sh)
            if ci is None:
                more = None
                break
            if ci not in want:
                more.add(ci)
        if not more:
            if why is not None:
                L = arclen(stuck["pts"])[-1]
                names = "the new via or its connector" \
                    if (blocked_by and blocked_by[0] is None) \
                    else ", ".join(sorted({f"{x.kind} [{x.net}]" for x in blocked_by
                                           if x is not None})[:3]) or "nothing movable"
                why.append(f"{stuck['net']}/{stuck['layer']} "
                           f"({len(stuck['pts'])} pts, {L:.1f} mm) is held by {names}")
            return None
        if len(want) + len(more) > max_chains:
            if why is not None:
                why.append(f"the shove cascades past {max_chains} traces")
            return None
        want |= more
    return None


# ---------------------------------------------------------------- targets

def stacked_pairs(text):
    """Unconnected items that are two tracks needing a via between layers."""
    out = []
    for blk in re.split(r'^\[unconnected_items\][^\n]*\n', text, flags=re.M)[1:]:
        eps = re.findall(r'@\(([\d.]+) mm, ([\d.]+) mm\): Track \[([^\]]+)\] on '
                         r'(\S+), length ([\d.]+) mm', blk[:400])
        if len(eps) != 2:
            continue
        a, b = eps
        out.append((a[2],
                    ((float(a[0]), float(a[1])), a[3], float(a[4])),
                    ((float(b[0]), float(b[1])), b[3], float(b[4]))))
    return out


def find_track(board, net, at, layer, length):
    """The track the DRC report means: right net, layer, length and start point."""
    n = board.FindNet(net)
    if n is None:
        return None
    lid = board.GetLayerID(layer)
    best, bd = None, 1e9
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != n.GetNetCode():
            continue
        if t.GetLayer() != lid or abs(TOMM(t.GetLength()) - length) > 3e-3:
            continue
        for p in (t.GetStart(), t.GetEnd()):
            d = math.hypot(TOMM(p.x) - at[0], TOMM(p.y) - at[1])
            if d < bd:
                bd, best = d, t
    return best if bd < 0.02 else None


def sample(p1, p2, step=0.02):
    L = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
    n = max(1, int(L/step))
    return [(p1[0] + (p2[0]-p1[0])*i/n, p1[1] + (p2[1]-p1[1])*i/n) for i in range(n+1)]


def attempt(net, A, B, apply, max_shove, debug=False, hard0=0, un0=10**9,
            budget=10):
    """One unconnected pair. Returns a description, and writes the board if applying."""
    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    ta = find_track(board, net, *A)
    tb = find_track(board, net, *B)
    if ta is None or tb is None:
        return f"  {net:6} could not identify both tracks", False

    a1 = (TOMM(ta.GetStart().x), TOMM(ta.GetStart().y))
    a2 = (TOMM(ta.GetEnd().x),   TOMM(ta.GetEnd().y))
    b1 = (TOMM(tb.GetStart().x), TOMM(tb.GetStart().y))
    b2 = (TOMM(tb.GetEnd().x),   TOMM(tb.GetEnd().y))
    alay = board.GetLayerName(ta.GetLayer())
    blay = board.GetLayerName(tb.GetLayer())
    nn = board.FindNet(net)
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)
    allsh = shapes_of(board, exclude_net=net, near=b1, radius=8.0)
    sidx = ShapeIndex(allsh)
    chains, index = build_chains(board)
    if debug:
        print(f"  [{net}] A {alay} {a1}->{a2}   B {blay} {b1}->{b2}")

    # Candidate via positions: along one track (so the via lands on it), with a short
    # connector on the other track's layer to its nearer end.
    cands = []
    for host, other, hlay in ((sample(a1, a2), (b1, b2), blay),
                              (sample(b1, b2), (a1, a2), alay)):
        for v in host:
            end = min(other, key=lambda p: math.hypot(p[0]-v[0], p[1]-v[1]))
            cands.append((math.hypot(end[0]-v[0], end[1]-v[1]), v, end, hlay))
    cands.sort(key=lambda c: c[0])

    scored, refused = [], {}
    def note(why):
        refused[why] = refused.get(why, 0) + 1
    for clen, v, end, hlay in cands:
        if clen > 3.0:
            continue
        for via_d, drill in TIERS:
            if not route.inside_board(v[0], v[1], via_d/2 + 0.35):
                note("outside the board outline"); continue
            if any(x1 - via_d/2 < v[0] < x2 + via_d/2 and
                   y1 - via_d/2 < v[1] < y2 + via_d/2 for x1, y1, x2, y2 in kos):
                note("inside a keepout"); continue
            if not route.hole_ok(v[0], v[1], holes, drill):
                note("too close to another drill"); continue
            need = via_d/2 + route.VIA_CLEAR + MARGIN
            conn_need = route.TRACK_W/2 + route.CLEAR + MARGIN
            conn_pts = sample(v, end, 0.03) if clen > 1e-6 else []
            blockers, seen = [], set()
            # the via is drilled through the whole stack, so every layer counts
            for sh in sidx.near(v[0], v[1], need + 1.0):
                if route.gap_to_shape(v[0], v[1], sh.geom) < need:
                    seen.add(id(sh)); blockers.append(sh)
            # the connector is copper on one layer only
            for x, y in conn_pts:
                for sh in sidx.near(x, y, conn_need + 1.0):
                    if id(sh) in seen or hlay not in sh.lset:
                        continue
                    if route.gap_to_shape(x, y, sh.geom) < conn_need:
                        seen.add(id(sh)); blockers.append(sh)
            hard = [sh for sh in blockers if not sh.shovable]
            if hard:
                note(f"{hard[0].kind} [{hard[0].net}] cannot be moved")
                continue
            scored.append((len({chain_of(index, sh) for sh in blockers}),
                           clen, v, end, via_d, drill, blockers, hlay))
            break
    if debug:
        for why, k in sorted(refused.items(), key=lambda kv: -kv[1])[:6]:
            print(f"      {k:5} candidates: {why}")
    if not scored:
        return (f"  {net:6} every via position is blocked by something that "
                f"cannot be moved"), False
    scored.sort(key=lambda x: (x[0], x[1]))
    if debug:
        print(f"      best candidate needs {scored[0][0]} chain(s) shoved")

    seen_why, attempts = set(), 0
    for cnt, clen, v, end, via_d, drill, blockers, hlay in scored[:80]:
        if cnt > max_shove:
            continue
        why = [] if debug else None
        plans = plan_shoves(v, via_d, blockers, allsh, chains, index,
                            connector=(v, end) if clen > 1e-6 else None, why=why)
        if plans is None:
            if debug and why and len(seen_why) < 6 and why[0] not in seen_why:
                seen_why.add(why[0])
                print(f"      cannot shove {why[0]}")
            continue
        desc = (f"  {net:6} via {via_d:.2f} at ({v[0]:.3f},{v[1]:.3f})"
                + (f" + {clen:.2f} mm on {hlay}" if clen > 1e-6 else "")
                + (", shoving " + ", ".join(
                    f"{chains[ci]['net']}/{chains[ci]['layer']} by {off:.2f} mm"
                    for ci, _p, off in plans)
                   if plans else ", nothing in the way"))
        if not apply:
            return desc, True

        shutil.copy(BOARD, BAK)
        bd = pcbnew.LoadBoard(BOARD)
        route.set_rules(bd)
        net2 = bd.FindNet(net)
        # Delete the victim chains by geometry. Wrappers from the other board object
        # are not valid here, and Remove() invalidates them as it goes.
        doomed_keys = set()
        for ci, _pts, _off in plans:
            ch = chains[ci]
            for i in range(len(ch["pts"]) - 1):
                p, q = ch["pts"][i], ch["pts"][i+1]
                doomed_keys.add((ch["net"], ch["layer"],
                                 tuple(sorted([(Q(p[0]*1e6), Q(p[1]*1e6)),
                                               (Q(q[0]*1e6), Q(q[1]*1e6))]))))
        doomed = []
        for t in bd.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                continue
            nx = t.GetNet()
            aa, bb2 = t.GetStart(), t.GetEnd()
            k = (nx.GetNetname() if nx else "", bd.GetLayerName(t.GetLayer()),
                 tuple(sorted([(Q(aa.x), Q(aa.y)), (Q(bb2.x), Q(bb2.y))])))
            if k in doomed_keys:
                doomed.append(t)
        for t in doomed:
            bd.Remove(t)
        for ci, pts, _off in plans:
            ch = chains[ci]
            cnet = bd.FindNet(ch["net"])
            for i in range(len(pts) - 1):
                route.add_track(bd, pts[i], pts[i+1], ch["layer"], cnet,
                                width=ch["width"])
        vv = route.add_via(bd, v[0], v[1], net2)
        vv.SetWidth(pcbnew.FromMM(via_d)); vv.SetDrill(pcbnew.FromMM(drill))
        if clen > 1e-6:
            route.add_track(bd, v, end, hlay, net2, width=route.TRACK_W)
        route.fill(bd)
        bd.Save(BOARD)
        hard, un, _ = drc()
        if hard <= hard0 and un < un0:
            return desc + f"  [{len(doomed)} segments rewritten] -> {un} unconnected", \
                   (hard, un)
        shutil.copy(BAK, BOARD)
        attempts += 1
        if debug:
            print(f"      {desc.strip()}  -> +{hard-hard0} err, {un} unconn; "
                  f"trying another position")
            sys.stdout.flush()
        if attempts >= budget:
            break
    return (f"  {net:6} {len(scored)} positions, "
            f"{attempts} written and reverted, none clean"), False



# ---------------------------------------------------------------- routed connectors

def cells_along(g, pts, step=0.01):
    """The grid cells a polyline passes through."""
    out = set()
    for x, y in _walk(pts, step):
        c = g.cell(x, y)
        if g.ok(*c):
            out.add(c)
    return out


def spread(g, sources):
    """Multi-source BFS over free cells. Returns (distance, previous-cell).

    Done once per layer, from the chain outward, rather than once per candidate via
    position. Every candidate then reads its connector length straight out of the
    distance map, and the path comes back by walking `prev` - so 1400 candidates cost
    one flood rather than 1400 searches.
    """
    dist = {c: 0 for c in sources}
    prev = {c: None for c in sources}
    q = deque(sources)
    while q:
        cur = q.popleft()
        i, j = cur
        d = dist[cur] + 1
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = (i+di, j+dj)
            if nb in dist or not g.ok(*nb):
                continue
            dist[nb] = d; prev[nb] = cur
            q.append(nb)
    return dist, prev


def walk_back(g, prev, cell):
    """The route from `cell` back to whichever source the flood started at."""
    path = [cell]
    while prev.get(path[-1]) is not None:
        path.append(prev[path[-1]])
    return [g.pos(*c) for c in path]


def straighten(pts):
    """Collapse the cell-by-cell path into straight runs."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i][0]-out[-1][0], pts[i][1]-out[-1][1]
        bx, by = pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]
        if abs(ax*by - ay*bx) > 1e-9:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def free_via(net, A, B, apply, max_shove, debug=False, window=3.5, step=0.02,
             hard0=0, un0=10**9, budget=15):
    """Find a via position nearby and ROUTE a connector to each layer's copper.

    attempt() requires the via to land on one of the two tracks. When the copper
    directly under that trace cannot move, no position on it will ever be legal no
    matter how hard the shove cascades - so the via is freed to sit wherever it fits
    and the two tracks reach out to meet it.

    The connectors are routed, not drawn straight. A straight connector crossed a GND
    trace on F.Cu, and shoving that trace aside does not help: a shove bows a trace
    around a POINT, so pushing it 0.1 mm just moves where it crosses. Every one of the
    first fifteen candidate positions closed the connection and cost the same
    tracks_crossing error for that reason. Routing on a 0.02 mm grid goes around.

    One flood per layer, outward from the chain, does all the work: each candidate then
    reads its connector length out of the distance map instead of running its own
    search.
    """
    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    ta = find_track(board, net, *A)
    tb = find_track(board, net, *B)
    if ta is None or tb is None:
        return f"  {net:6} could not identify both tracks", False
    alay = board.GetLayerName(ta.GetLayer())
    blay = board.GetLayerName(tb.GetLayer())
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)
    chains, index = build_chains(board)

    def chain_for(t):
        aa, bb = t.GetStart(), t.GetEnd()
        sh = Shape(None, "track", net, layer=board.GetLayerName(t.GetLayer()),
                   p1=(TOMM(aa.x), TOMM(aa.y)), p2=(TOMM(bb.x), TOMM(bb.y)))
        ci = chain_of(index, sh)
        return chains[ci]["pts"] if ci is not None else [sh.p1, sh.p2]
    ca, cb = chain_for(ta), chain_for(tb)
    mid = ((ca[0][0] + cb[0][0]) / 2, (ca[0][1] + cb[0][1]) / 2)
    allsh = shapes_of(board, exclude_net=net, near=mid, radius=window + 8.0)
    idx = ShapeIndex(allsh)

    # One grid per layer, covering the via search window and enough of each chain to
    # reach it. import here rather than at module scope: island_route imports shove.
    import island_route as ir
    box = (mid[0] - window, mid[1] - window, mid[0] + window, mid[1] + window)
    ga = ir.Grid(board, alay, box, step, allsh, 2.5)
    gb = ir.Grid(board, blay, box, step, allsh, 2.5)
    sa, sb = cells_along(ga, ca), cells_along(gb, cb)
    if not sa or not sb:
        return (f"  {net:6} neither chain has a cell inside the search window"), False
    da, pa_prev = spread(ga, sa)
    db, pb_prev = spread(gb, sb)
    if debug:
        print(f"  [{net}] free-via: {alay} reachable from {len(sa)} chain cells "
              f"-> {len(da)} cells; {blay} from {len(sb)} -> {len(db)} cells")
        sys.stdout.flush()

    scored = []
    n = int(window / 0.05)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            v = (mid[0] + i*0.05, mid[1] + j*0.05)
            ca_cell, cb_cell = ga.cell(*v), gb.cell(*v)
            if ca_cell not in da or cb_cell not in db:
                continue                      # not reachable on one of the two layers
            for via_d, drill in TIERS:
                if not route.inside_board(v[0], v[1], via_d/2 + 0.35):
                    continue
                if any(x1 - via_d/2 < v[0] < x2 + via_d/2 and
                       y1 - via_d/2 < v[1] < y2 + via_d/2
                       for x1, y1, x2, y2 in kos):
                    continue
                if not route.hole_ok(v[0], v[1], holes, drill):
                    continue
                need = via_d/2 + route.VIA_CLEAR + MARGIN
                vb = [sh for sh in idx.near(v[0], v[1], need + 1.0)
                      if route.gap_to_shape(v[0], v[1], sh.geom) < need]
                if any(not sh.shovable for sh in vb):
                    continue
                L = (da[ca_cell] + db[cb_cell]) * step
                scored.append((len({chain_of(index, x) for x in vb}), L,
                               v, ca_cell, cb_cell, via_d, drill, vb))
                break
    if not scored:
        return f"  {net:6} no via position in {window} mm is reachable on both layers", False
    scored.sort(key=lambda x: (x[0], x[1]))
    if debug:
        print(f"      {len(scored)} reachable spots; best shoves {scored[0][0]} "
              f"chain(s), {scored[0][1]:.2f} mm of connector")
        sys.stdout.flush()

    attempts = 0
    for cnt, L, v, ca_cell, cb_cell, via_d, drill, vb in scored:
        if cnt > max_shove:
            continue
        route_a = straighten(walk_back(ga, pa_prev, ca_cell))[::-1]
        route_b = straighten(walk_back(gb, pb_prev, cb_cell))[::-1]
        # walk_back ends at the chain; reverse so the run starts at the via
        plans = []
        if vb:
            plans = plan_shoves(v, via_d, vb, allsh, chains, index)
            if plans is None:
                continue
        desc = (f"  {net:6} via {via_d:.2f} at ({v[0]:.3f},{v[1]:.3f}), "
                f"{len(route_a)-1}-segment run on {alay} + "
                f"{len(route_b)-1} on {blay} ({L:.2f} mm total)"
                + (", shoving " + ", ".join(
                    f"{chains[ci]['net']}/{chains[ci]['layer']} by {off:.2f} mm"
                    for ci, _p, off in plans) if plans else ", nothing moved"))
        if not apply:
            return desc, True

        shutil.copy(BOARD, BAK)
        bd = pcbnew.LoadBoard(BOARD)
        route.set_rules(bd)
        nb = bd.FindNet(net)
        if plans:
            doomed_keys = set()
            for ci, _pts, _off in plans:
                ch = chains[ci]
                for k in range(len(ch["pts"]) - 1):
                    q1, q2 = ch["pts"][k], ch["pts"][k+1]
                    doomed_keys.add((ch["net"], ch["layer"], tuple(sorted(
                        [(Q(q1[0]*1e6), Q(q1[1]*1e6)), (Q(q2[0]*1e6), Q(q2[1]*1e6))]))))
            doomed = []
            for t in bd.GetTracks():
                if t.Type() == pcbnew.PCB_VIA_T:
                    continue
                nx = t.GetNet()
                aa, bb = t.GetStart(), t.GetEnd()
                k = (nx.GetNetname() if nx else "", bd.GetLayerName(t.GetLayer()),
                     tuple(sorted([(Q(aa.x), Q(aa.y)), (Q(bb.x), Q(bb.y))])))
                if k in doomed_keys:
                    doomed.append(t)
            for t in doomed:
                bd.Remove(t)
            for ci, pts, _off in plans:
                ch = chains[ci]
                cnet = bd.FindNet(ch["net"])
                for k in range(len(pts) - 1):
                    route.add_track(bd, pts[k], pts[k+1], ch["layer"], cnet,
                                    width=ch["width"])
        vv = route.add_via(bd, v[0], v[1], nb)
        vv.SetWidth(pcbnew.FromMM(via_d)); vv.SetDrill(pcbnew.FromMM(drill))
        for lay, run in ((alay, route_a), (blay, route_b)):
            for k in range(len(run) - 1):
                route.add_track(bd, run[k], run[k+1], lay, nb, width=route.TRACK_W)
        route.fill(bd)
        bd.Save(BOARD)
        hard, un, _ = drc()
        if hard <= hard0 and un < un0:
            return desc + f"  -> {un} unconnected", (hard, un)
        if debug:
            txt = open(RPT).read()
            bad = [x for x in re.split(r'^\[', txt, flags=re.M)
                   if x and not x.startswith("unconnected_items")
                   and not x.startswith("** ")]
            print(f"      {desc.strip()}  -> +{hard-hard0} err, {un} unconn")
            for x in bad[:1]:
                for ln in ("[" + x).splitlines()[:4]:
                    print(f"          {ln.strip()}")
            sys.stdout.flush()
        shutil.copy(BAK, BOARD)
        attempts += 1
        if attempts >= budget:
            break
    return (f"  {net:6} {len(scored)} spots searched, "
            f"{attempts} written and reverted, none clean"), False


def main():
    apply = "--apply" in sys.argv
    only = sys.argv[sys.argv.index("--only")+1] if "--only" in sys.argv else None
    max_shove = int(sys.argv[sys.argv.index("--max-shove")+1]) \
        if "--max-shove" in sys.argv else 8
    debug = "--debug" in sys.argv
    freev = "--no-free-via" not in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, text = drc()
    todo = stacked_pairs(text)
    if only:
        todo = [t for t in todo if t[0] == only]
    print(f"baseline {hard0} errors, {un0} unconnected; {len(todo)} stacked pairs\n")

    for net, A, B in todo:
        desc, res = attempt(net, A, B, apply, max_shove, debug, hard0, un0)
        if res is False and freev:
            print(desc)
            desc, res = free_via(net, A, B, apply, max_shove, debug,
                                 hard0=hard0, un0=un0)
        if res is False:
            print(desc)
            continue
        if res is True:
            print(desc)
            continue
        hard, un = res
        un0 = un
        print(desc)

    hard, un, _ = drc()
    print(f"\n{hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
