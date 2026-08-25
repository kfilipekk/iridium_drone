#!/usr/bin/env python3
"""
Merge the routing into clean traces instead of thousands of one-cell stubs.

tools/route.py routes on a 0.0625 mm grid and emits ONE TRACK SEGMENT PER CELL. On this
board that left 4463 of 6040 segments exactly 0.0625 mm long - 74% of the routing - and
they are almost entirely axis aligned (1644 at 90 deg, 1092 at -90, 878 at 0, 813 at
180, and only 36 diagonals). So every trace the local router laid is a Manhattan
staircase built from hundreds of stubs. It bloats the file and the gerbers, it is
unreadable in KiCad, and it makes every geometry pass slower than it needs to be.

Two passes, each verified independently:

  merge  - follow each chain of segments through joints where exactly two meet, and
           collapse consecutive collinear ones into a single track. Pure simplification:
           the copper occupies the same space afterwards, so it cannot change DRC.

  mitre  - replace each 90 degree corner with a 45 degree chamfer. This DOES move
           copper, so every corner is checked and reverted individually if it costs a
           DRC error. Shorter, lower inductance, and what a person would have drawn.

Junctions matter: a point where three or more segments meet, or where a via lands, ends
a chain. Merging through one would be geometrically identical but makes the result
harder to reason about, and vias are the only thing tying most nets to their planes.

Usage:  python3 tools/tidy_tracks.py [--apply] [--no-mitre]
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/tidy_backup.kicad_pcb"
RPT   = "/tmp/nav/tidy.rpt"
Q     = lambda v: round(v / 1000.0)          # 1 um quantisation for joint matching


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def collinear(a, b, c, tol=1e-6):
    """Is b on the straight line a->c?"""
    return abs((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])) < tol


def build_chains(board):
    """Polylines of same-net, same-layer segments, split at junctions and vias."""
    # Deduplicate FIRST. Running route_remaining.py repeatedly commits overlapping
    # paths, which left 960 segments with identical endpoints. Each duplicate adds two
    # to the degree of both its endpoints, so the chain walker sees a junction where
    # there is really a plain joint - 285 points looked degree-4 and 198 degree-6.
    # Dropping them is what lets the merge actually reach along a trace.
    segs = []
    seen = set()
    dups = 0
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        n = t.GetNet()
        a, b = t.GetStart(), t.GetEnd()
        if a.x == b.x and a.y == b.y:
            continue                                    # zero length, drop it
        # The NET must be part of the key. Without it two coincident segments on
        # different nets look like duplicates and one gets dropped, which silently
        # breaks a connection - it cost two of them before this was caught.
        k = (n.GetNetCode() if n else 0, t.GetLayer(), t.GetWidth(),
             tuple(sorted([(Q(a.x), Q(a.y)), (Q(b.x), Q(b.y))])))
        if k in seen:
            dups += 1
            continue
        seen.add(k)
        segs.append((t, n.GetNetCode() if n else 0, t.GetLayer(),
                     (a.x/1e6, a.y/1e6), (b.x/1e6, b.y/1e6), t.GetWidth()))
    if dups:
        print(f"dropped {dups} duplicate segments")

    via_pts = set()
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            via_pts.add((Q(p.x), Q(p.y)))

    inc = {}
    for i, (_, code, lay, a, b, _w) in enumerate(segs):
        for p in (a, b):
            inc.setdefault((code, lay, Q(p[0]*1e6), Q(p[1]*1e6)), []).append(i)

    def key(code, lay, p):
        return (code, lay, Q(p[0]*1e6), Q(p[1]*1e6))

    def is_junction(code, lay, p):
        k = key(code, lay, p)
        if len(inc.get(k, [])) != 2:
            return True
        return (k[2], k[3]) in via_pts

    used = set()
    chains = []
    for i, (_, code, lay, a, b, w) in enumerate(segs):
        if i in used:
            continue
        pts = [a, b]
        used.add(i)
        # extend from both ends while the joint is a plain degree-2 connection
        for end in (0, 1):
            while True:
                tip = pts[0] if end == 0 else pts[-1]
                if is_junction(code, lay, tip):
                    break
                nxt = [j for j in inc[key(code, lay, tip)] if j not in used]
                if not nxt:
                    break
                j = nxt[0]
                used.add(j)
                _, _, _, ja, jb, _ = segs[j]
                far = jb if (Q(ja[0]*1e6), Q(ja[1]*1e6)) == (Q(tip[0]*1e6), Q(tip[1]*1e6)) else ja
                if end == 0:
                    pts.insert(0, far)
                else:
                    pts.append(far)
        chains.append((code, lay, w, pts))
    return segs, chains


def simplify(pts):
    """Drop points that lie on the straight line between their neighbours."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        if not collinear(out[-1], pts[i], pts[i+1]):
            out.append(pts[i])
    out.append(pts[-1])
    return out


def mitre(pts, frac=0.3, clear=None, width=0.1016):
    """Replace right-angle corners with 45 degree chamfers.

    Each chamfer is checked against foreign copper BEFORE it is accepted. Mitring
    blindly at 0.4 moved copper into tight clearances and cost 16 DRC errors, and a
    whole-board DRC per corner would take hours across 606 chains - so the test is done
    here in geometry. A corner that cannot be cut is simply left square.
    """
    if len(pts) < 3:
        return pts
    need = width / 2 + route.CLEAR
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        p, c, n = pts[i-1], pts[i], pts[i+1]
        v1 = (c[0]-p[0], c[1]-p[1])
        v2 = (n[0]-c[0], n[1]-c[1])
        l1 = math.hypot(*v1); l2 = math.hypot(*v2)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        dot = (v1[0]*v2[0] + v1[1]*v2[1]) / (l1*l2)
        if abs(dot) > 0.2:                 # not close to a right angle, leave it
            out.append(c); continue
        d = min(l1, l2) * frac
        a = (c[0] - v1[0]/l1*d, c[1] - v1[1]/l1*d)
        b = (c[0] + v2[0]/l2*d, c[1] + v2[1]/l2*d)
        ok = True
        if clear is not None:
            steps = max(2, int(math.hypot(b[0]-a[0], b[1]-a[1]) / 0.03))
            for k in range(steps + 1):
                f = k / steps
                sx, sy = a[0] + (b[0]-a[0])*f, a[1] + (b[1]-a[1])*f
                if not clear(sx, sy, need):
                    ok = False; break
        if ok:
            out.append(a); out.append(b)
        else:
            out.append(c)
    out.append(pts[-1])
    return out


def rebuild(board, chains, do_mitre, skip_nets=("GND",)):
    """Replace every non-via track with the simplified chains.

    GND is left alone by default. Merging its chains reliably costs four GND
    connections - the net is the one most entangled with the copper pours, and
    refilling around merged geometry evidently shifts where the pour bridges between
    islands. Everything else merges cleanly, so GND keeps its original segments rather
    than trading connectivity for tidiness.
    """
    skip_codes = set()
    for nm in skip_nets:
        n = board.FindNet(nm)
        if n:
            skip_codes.add(n.GetNetCode())
    doomed = [t for t in board.GetTracks()
              if t.Type() != pcbnew.PCB_VIA_T and t.GetNetCode() not in skip_codes]
    for t in doomed:
        board.Remove(t)
    # One obstacle set per (net, layer), built once and reused for every corner.
    cache = {}
    def clear_for(code, lay):
        if (code, lay) not in cache:
            nm = board.FindNet(code).GetNetname() if code else None
            shapes = [sh for sh in route.obstacle_shapes(board, exclude_net=nm)]
            cache[(code, lay)] = shapes
        shapes = cache[(code, lay)]
        def ok(x, y, need):
            return all(route.gap_to_shape(x, y, sh) >= need for sh in shapes)
        return ok

    made = 0
    for code, lay, w, pts in chains:
        if code in skip_codes:
            continue
        pts = simplify(pts)
        if do_mitre:
            pts = mitre(pts, clear=clear_for(code, lay),
                        width=w / 1e6 if w > 1000 else route.TRACK_W)
        net = board.FindNet(code) if code else None
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i+1]
            if abs(a[0]-b[0]) < 1e-9 and abs(a[1]-b[1]) < 1e-9:
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
            t.SetWidth(w); t.SetLayer(lay)
            if net:
                t.SetNet(net)
            board.Add(t)
            made += 1
    return len(doomed), made


def main():
    apply = "--apply" in sys.argv
    do_mitre = "--no-mitre" not in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0 = drc()
    print(f"baseline {hard0} errors, {un0} unconnected")

    dedupe_only = "--dedupe-only" in sys.argv
    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    segs, chains = build_chains(board)
    if dedupe_only:
        # one chain per surviving segment: drops duplicates, merges nothing
        chains = [(c, l, w, [p[0], p[-1]]) for c, l, w, p in
                  [(s2[1], s2[2], s2[5], [s2[3], s2[4]]) for s2 in segs]]
    tiny = sum(1 for s in segs if math.hypot(s[4][0]-s[3][0], s[4][1]-s[3][1]) <= 0.07)
    print(f"{len(segs)} segments ({tiny} of them <= 0.07 mm) in {len(chains)} chains")

    if not apply:
        total = sum(len(simplify(p)) - 1 for _, _, _, p in chains)
        print(f"merge alone would give ~{total} segments "
              f"({100*(1-total/max(len(segs),1)):.0f}% fewer)")
        print("dry run - pass --apply to write the board")
        return 0

    shutil.copy(BOARD, BAK)
    removed, made = rebuild(board, chains, do_mitre)
    route.fill(board)
    board.Save(BOARD)
    hard, un = drc()
    print(f"replaced {removed} segments with {made}"
          f"  ({100*(1-made/max(removed,1)):.0f}% fewer)")
    print(f"DRC: {hard0} -> {hard} errors, {un0} -> {un} unconnected")
    if hard > hard0 or un > un0:
        shutil.copy(BAK, BOARD)
        print("worse - rolled back"
              + ("; retry with --no-mitre" if do_mitre else ""))
        return 1
    print("kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
