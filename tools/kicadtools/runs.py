#copper runs: one net's tracks on one layer as a graph of segments, split at junctions
import collections, math
import pcbnew

T = pcbnew.ToMM
NEAR = 0.0005            #mm: how close a point must be to count as on a segment


def point_seg_dist(p, a, c):
    dx, dy = c[0]-a[0], c[1]-a[1]
    L2 = dx*dx + dy*dy
    u = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / L2))
    return math.hypot(p[0] - a[0] - u*dx, p[1] - a[1] - u*dy)


#the shared-endpoint key of a point in mm: 1 um, as a tuple
def _node(p):
    return (round(p[0] * 1000), round(p[1] * 1000))


#is p on segment a-b, away from either end?
def _inside(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return False
    u = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    if u <= 1e-6 or u >= 1 - 1e-6:
        return False
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / math.sqrt(L2) < NEAR


#is `narrow` wholly inside the wider `wide`? Both are [a, b, width, track]
def inside_wider(narrow, wide, margin=0.0):
    if wide[2] <= narrow[2] + 1e-9:
        return False
    return all(point_seg_dist(p, wide[0], wide[1]) <= wide[2] / 2 - margin + NEAR
               for p in (narrow[0], narrow[1]))


#indices of pieces wholly inside a wider one that is itself kept
def covered_indices(geom, strict=False):
    survivors, dead = [], set()
    for i in sorted(range(len(geom)), key=lambda k: -geom[k][2]):
        if any(inside_wider(geom[i], geom[j], geom[i][2] / 2 if strict else 0.0)
               for j in survivors):
            dead.add(i)
        else:
            survivors.append(i)
    return dead


#one (net, layer)'s copper split at T-junctions
def net_graph(board, code, layer):
    raw = []
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != code or t.GetLayer() != layer:
            continue
        a = (T(t.GetStart().x), T(t.GetStart().y))
        b = (T(t.GetEnd().x), T(t.GetEnd().y))
        if a == b:
            continue
        raw.append([a, b, T(t.GetWidth()), t])
    seen, segs = set(), []
    for a, b, w, t in raw:
        k = tuple(sorted([_node(a), _node(b)])) + (round(w, 6),)
        if k in seen:
            continue
        seen.add(k)
        segs.append([a, b, w, t])
    dead = covered_indices(segs)
    segs = [s for i, s in enumerate(segs) if i not in dead]
    #t-junctions: where a segment's end lands on another segment's middle
    tips = [p for s in segs for p in (s[0], s[1])]
    split = []
    for a, b, w, t in segs:
        cuts = sorted({p for p in tips if p != a and p != b and _inside(p, a, b)},
                      key=lambda p: (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2)
        if not cuts:
            split.append([a, b, w, t])
            continue
        prev = a
        for p in cuts + [b]:
            split.append([prev, p, w, t])
            prev = p
    adj = collections.defaultdict(list)
    for i, (a, b, w, t) in enumerate(split):
        for p in (a, b):
            k = _node(p)
            if i not in adj[k]:
                adj[k].append(i)
    return split, adj


#node keys of segment ends that land on a pad of this net and layer
def pad_nodes(board, code, layer, segs):
    pads = [pd for fp in board.GetFootprints() for pd in fp.Pads()
            if pd.GetNetCode() == code and layer in pd.GetLayerSet().CuStack()]
    if not pads:
        return set()
    keys = set()
    for s in segs:
        for p in (s[0], s[1]):
            v = pcbnew.VECTOR2I(int(round(p[0] * 1e6)), int(round(p[1] * 1e6)))
            if any(pd.HitTest(v, 0) for pd in pads):
                keys.add(_node(p))
    return keys


#maximal chains of degree-2 nodes between junctions
def net_runs(segs, adj, via_nodes=(), pad_nodes=()):
    stops = set(via_nodes) | set(pad_nodes)

    def junction(k):
        return len(adj[k]) != 2 or k in stops

    used, runs = set(), []
    for i in range(len(segs)):
        if i in used:
            continue
        chain = [i]
        used.add(i)
        for end in (0, 1):
            while True:
                k = _node(segs[chain[0]][0] if end == 0 else segs[chain[-1]][1])
                if junction(k):
                    break
                nxt = [j for j in adj[k] if j not in used]
                if len(nxt) != 1:
                    break
                j = nxt[0]
                used.add(j)
                if end == 0:
                    #prepended: it has to arrive at the run's start, not leave it
                    if _node(segs[j][1]) != k:
                        segs[j] = [segs[j][1], segs[j][0], segs[j][2], segs[j][3]]
                    chain.insert(0, j)
                else:
                    if _node(segs[j][0]) != k:             #turn it round to continue outward
                        segs[j] = [segs[j][1], segs[j][0], segs[j][2], segs[j][3]]
                    chain.append(j)
        runs.append(chain)
    return runs
