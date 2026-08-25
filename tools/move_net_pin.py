#!/usr/bin/env python3
"""
Move a net from one MCU pin to another on a board that is already routed.

Regenerating the PCB from design.py re-places every part and throws away the routing -
which on this board took an entire session to get to 472/472. When the fix is "this net
is on the wrong pin", that is a wildly disproportionate price. This does it surgically:
reassign the two pads, rip only that net's copper, route it again across all four signal
layers, and let whole-board DRC decide whether the result is acceptable.

Built for the ESC telemetry defect: J2.8 carries telemetry FROM the ESC and landed on
PE1 = UART8_TX. A transmit pin cannot receive it. PE0 (UART8_RX) is 0.5 mm away and was
wired to nothing.

The vacated pin gets `--spare-net` so it still has a net and ERC stays clean, matching
the PE15_SPARE / PB2_SPARE convention already in design.py.

Everything is verified and rolled back on any regression - a fix that closes one
connection and opens another is not a fix.

Usage:
  python3 tools/move_net_pin.py --net ESC_TEL --from U1.98 --to U1.97 \
      --spare-net PE1_SPARE [--apply] [--grid MM]
"""
import os, sys, re, math, heapq, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove, island_route as ir

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/movepin_backup.kicad_pcb"
RPT   = "/tmp/nav/movepin.rpt"
TOMM  = route.TOMM
SIG   = ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu")
VIA_D, VIA_DRILL = 0.45, 0.20


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def pad_of(board, spec):
    ref, num = spec.split(".", 1)
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        raise SystemExit(f"no footprint {ref}")
    for pad in fp.Pads():
        if pad.GetNumber() == num:
            return pad
    raise SystemExit(f"{ref} has no pad {num}")


def pad_layers(board, pad):
    return [L for L in SIG if pad.IsOnLayer(board.GetLayerID(L))]


def route_pad_to_pad(board, a_pad, b_pad, netname, step, pad_mm=8.0, via_cost=40,
                     extra=()):
    """Multi-layer A* between two pads, avoiding every other net's copper.

    `extra` is copper that is planned but not yet on the board. Two routes computed from
    the same board state do not see each other, and the first time a part with two
    signal pads was added its two traces were laid straight across one another - DRC
    reported them shorting. Anything already planned has to be passed in here.
    """
    ap, bp = a_pad.GetPosition(), b_pad.GetPosition()
    a = (TOMM(ap.x), TOMM(ap.y)); b = (TOMM(bp.x), TOMM(bp.y))
    allsh = [s for s in shove.shapes_of(board) if s.net != netname] + list(extra)
    kidx = shove.ShapeIndex(allsh)
    holes = route.hole_shapes(board)
    kos = route.keepout_boxes(board)
    box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
    grids = [ir.Grid(board, L, box, step, allsh, pad_mm) for L in SIG]
    g0 = grids[0]
    ca, cb = g0.cell(*a), g0.cell(*b)
    al = [SIG.index(L) for L in pad_layers(board, a_pad) if grids[SIG.index(L)].ok(*ca)]
    bl = [SIG.index(L) for L in pad_layers(board, b_pad) if grids[SIG.index(L)].ok(*cb)]
    if not al or not bl:
        return None, "a pad has no legal cell to start or finish on"

    need = VIA_D/2 + route.VIA_CLEAR + 0.005
    vcache = {}
    def via_ok(i, j):
        if (i, j) not in vcache:
            x, y = g0.pos(i, j)
            vcache[(i, j)] = (
                route.inside_board(x, y, VIA_D/2 + 0.35)
                and route.hole_ok(x, y, holes, VIA_DRILL)
                and not any(x1 - VIA_D/2 < x < x2 + VIA_D/2 and
                            y1 - VIA_D/2 < y < y2 + VIA_D/2 for x1, y1, x2, y2 in kos)
                and not any(route.gap_to_shape(x, y, s.geom) < need
                            for s in kidx.near(x, y, need + 1.0)))
        return vcache[(i, j)]

    goals = {(li,) + cb for li in bl}
    dist, prev, pq = {}, {}, []
    for li in al:
        st = (li,) + ca
        dist[st] = 0; prev[st] = None
        heapq.heappush(pq, (0, st))
    h = lambda n: (abs(n[1] - cb[0]) + abs(n[2] - cb[1])) * 10
    goal = None
    while pq:
        f, cur = heapq.heappop(pq)
        if cur in goals:
            goal = cur; break
        d = dist[cur]
        if f - h(cur) > d:
            continue
        li, i, j = cur
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = (li, i+di, j+dj)
            if not grids[li].ok(i+di, j+dj):
                continue
            nd = d + (14 if di and dj else 10)
            if nd < dist.get(nb, 1 << 60):
                dist[nb] = nd; prev[nb] = cur
                heapq.heappush(pq, (nd + h(nb), nb))
        if via_ok(i, j):
            for lj in range(len(SIG)):
                if lj != li and grids[lj].ok(i, j):
                    nb = (lj, i, j)
                    nd = d + via_cost*10
                    if nd < dist.get(nb, 1 << 60):
                        dist[nb] = nd; prev[nb] = cur
                        heapq.heappush(pq, (nd + h(nb), nb))
    if goal is None:
        return None, "no path across any signal layer"

    seq = []
    node = goal
    while node is not None:
        seq.append(node); node = prev[node]
    seq.reverse()
    runs, vias, cur_l, buf = [], [], seq[0][0], []
    for (li, i, j) in seq:
        if li != cur_l:
            runs.append((SIG[cur_l], shove.straighten([g0.pos(*c[1:]) for c in buf])))
            vias.append(g0.pos(i, j))
            cur_l, buf = li, []
        buf.append((li, i, j))
    runs.append((SIG[cur_l], shove.straighten([g0.pos(*c[1:]) for c in buf])))
    runs = [(L, list(p)) for L, p in runs]
    runs[0][1][0] = a
    runs[-1][1][-1] = b
    n = sum(len(p) - 1 for _l, p in runs)
    return (runs, vias), f"{n} segments, {len(vias)} via(s), {dist[goal]/10*step:.2f} mm"


def _reassign(bd, src, dst, netname, spare):
    """Put the net on the destination pad and park the vacated one on a spare net."""
    net = bd.FindNet(netname)
    sp, dp = pad_of(bd, src), pad_of(bd, dst)
    if spare:
        sn = bd.FindNet(spare)
        if sn is None:
            sn = pcbnew.NETINFO_ITEM(bd, spare)
            bd.Add(sn)
        sp.SetNet(sn)
    dp.SetNet(net)
    return net


def main():
    def arg(name, default=None):
        return sys.argv[sys.argv.index(name)+1] if name in sys.argv else default
    netname = arg("--net"); src = arg("--from"); dst = arg("--to")
    spare = arg("--spare-net")
    apply = "--apply" in sys.argv
    step = float(arg("--grid", "0.05"))
    if not (netname and src and dst):
        print(__doc__.strip()); return 2
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, _ = drc()
    print(f"baseline {hard0} errors, {un0} unconnected")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    a_pad, b_pad = pad_of(board, src), pad_of(board, dst)
    n_src = a_pad.GetNet().GetNetname() if a_pad.GetNet() else ""
    n_dst = b_pad.GetNet().GetNetname() if b_pad.GetNet() else ""
    print(f"  {src} currently on '{n_src}'  ->  {dst} currently on '{n_dst}'")
    if n_src != netname:
        print(f"  refusing: {src} is not on {netname}")
        return 1

    # find the other endpoint(s) of the net - everything that is not the pin we vacate
    ends = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nn = pad.GetNet()
            if nn and nn.GetNetname() == netname:
                spec = f"{fp.GetReference()}.{pad.GetNumber()}"
                if spec != src:
                    ends.append(spec)
    if len(ends) != 1:
        print(f"  expected exactly one other endpoint on {netname}, found {ends}")
        return 1
    far = pad_of(board, ends[0])
    print(f"  other endpoint: {ends[0]}")

    # Reassign the pads BEFORE routing. The destination pad still belongs to its old
    # net, so leaving it there makes the pad an obstacle to the very route that has to
    # land on it - the search fails before it starts. Doing the swap first means the
    # obstacle set is the one the finished board will actually have.
    _reassign(board, src, dst, netname, spare)

    res, note = route_pad_to_pad(board, far, b_pad, netname, step)
    if res is None:
        print(f"  cannot route {ends[0]} -> {dst}: {note}")
        return 1
    runs, vias = res
    print(f"  new route {ends[0]} -> {dst}: {note}")
    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0

    shutil.copy(BOARD, BAK)
    bd = pcbnew.LoadBoard(BOARD)
    route.set_rules(bd)
    net = bd.FindNet(netname)
    # rip the old copper
    doomed = [t for t in bd.GetTracks() if t.GetNetCode() == net.GetNetCode()]
    for t in doomed:
        bd.Remove(t)
    _reassign(bd, src, dst, netname, spare)
    for lay, pts in runs:
        for k in range(len(pts) - 1):
            route.add_track(bd, pts[k], pts[k+1], lay, net, width=route.TRACK_W)
    for vx, vy in vias:
        v = route.add_via(bd, vx, vy, net)
        v.SetWidth(pcbnew.FromMM(VIA_D)); v.SetDrill(pcbnew.FromMM(VIA_DRILL))
    route.fill(bd)
    bd.Save(BOARD)
    hard, un, txt = drc()
    if hard <= hard0 and un <= un0:
        print(f"  moved {netname}: {src} -> {dst}  ({len(doomed)} items ripped, "
              f"{sum(len(p)-1 for _l,p in runs)} laid)  -> {hard} errors, "
              f"{un} unconnected")
        return 0
    bad = [z for z in re.split(r'^\[', txt, flags=re.M)
           if z and not z.startswith("unconnected_items") and not z.startswith("** ")]
    print(f"  rolled back: +{hard-hard0} errors, {un} unconnected"
          + (f" - {bad[0].splitlines()[0]}" if bad else ""))
    shutil.copy(BAK, BOARD)
    return 1


if __name__ == "__main__":
    sys.exit(main())
