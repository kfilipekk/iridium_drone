
ISLAND_MAX_AREA = 50.0   # mm^2, [A] - see power_islands()
#!/usr/bin/env python3
"""
Post-placement copper: power fanout vias, plane fills, and a grid autorouter.

Run after gen_pcb.py. Operates on NAVCORE-SoOP.kicad_pcb in place.

Layer plan: L1 signal + RF, L2 solid GND, L3 +3V3, L4 signal. GND and +3V3 pads reach
their plane through a fanout via placed beside the pad; signals route on L1/L4 with vias.
"""
import sys, os, math, heapq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
BOARD = "NAVCORE-SoOP.kicad_pcb"
X0, Y0, W, H = (design.BOARD["X0"], design.BOARD["Y0"],
                design.BOARD["W"], design.BOARD["H"])

VIA_D, VIA_DRILL = 0.60, 0.30      # JLCPCB standard 4-layer, no upcharge
STUB_W           = 0.25    # fanout stub width - MUST match the check in fanout()
TRACK_W          = 0.1016  # 4 mil exactly. JLCPCB's 4-layer free tier is 4 mil; 3.0-3.5
                          # mil costs +20%, so 0.10 mm (3.94 mil) would have paid the
                          # upcharge for nothing. Safe at this width only because every
                          # power rail is on a plane - these carry logic currents only.
# 5 mil was tried and routed exactly ZERO further nets - the remaining blockage
# is topological (fragmented free space), not dimensional. Reverted to 6 mil for
# the manufacturing margin, since the tighter rule bought nothing.
CLEAR            = 0.1016
GRID             = 0.20                    # router grid pitch (mm)

# L2 is solid GND. L3 is a SPLIT power plane: +3V3 covers it as the base, with
# higher-priority islands for the other rails placed over where their pads cluster.
# Every pad on an outer layer reaches its rail through a fanout via.
# L2 is a solid GND plane. L3 carries +3V3 as its base pour plus higher-priority
# islands for the other rails. EVERY rail listed here gets a fanout via, which is what
# makes the island reachable from an outer-layer pad - previously only GND and +3V3 got
# vias at all and the rest depended entirely on routed traces.
# 6-layer stackup: F(sig) / In1(GND) / In2(sig) / In3(sig) / In4(PWR) / B(sig).
# GND sits directly under F.Cu as the reference for the fast nets; the split power
# rails sit under B.Cu. In2 and In3 are the two extra signal layers that make a
# 0.5 mm pitch LQFP100 routable at all.
PLANE = {"GND": "In1.Cu", "+3V3": "In4.Cu", "+3V3A": "In4.Cu", "VDDA": "In4.Cu",
         "+5V": "In4.Cu", "+9V": "In4.Cu", "VBAT": "In4.Cu", "VBUS": "In4.Cu"}


def load():
    return pcbnew.LoadBoard(BOARD)


def add_via(board, x_mm, y_mm, net, top="F.Cu", bot="B.Cu"):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(MM(x_mm), MM(y_mm)))
    v.SetWidth(MM(VIA_D)); v.SetDrill(MM(VIA_DRILL))
    v.SetLayerPair(board.GetLayerID(top), board.GetLayerID(bot))
    v.SetNet(net); board.Add(v)
    return v


def add_track(board, p1, p2, layer, net, width=TRACK_W):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(MM(p1[0]), MM(p1[1])))
    t.SetEnd(pcbnew.VECTOR2I(MM(p2[0]), MM(p2[1])))
    t.SetWidth(MM(width)); t.SetLayer(board.GetLayerID(layer)); t.SetNet(net)
    board.Add(t)
    return t


R_CORNER, MOUNT, HOLE_D = (design.BOARD["R"], design.BOARD["MOUNT"],
                           design.BOARD["HOLE_D"])
CX, CY = X0 + W/2, Y0 + H/2
HOLES = [(CX+dx, CY+dy) for dx in (-MOUNT/2, MOUNT/2) for dy in (-MOUNT/2, MOUNT/2)]


def inside_board(x, y, margin):
    if not (X0+margin <= x <= X0+W-margin and Y0+margin <= y <= Y0+H-margin):
        return False
    for cx, cy in ((X0+R_CORNER, Y0+R_CORNER), (X0+W-R_CORNER, Y0+R_CORNER),
                   (X0+R_CORNER, Y0+H-R_CORNER), (X0+W-R_CORNER, Y0+H-R_CORNER)):
        ox = x < X0+R_CORNER if cx < CX else x > X0+W-R_CORNER
        oy = y < Y0+R_CORNER if cy < CY else y > Y0+H-R_CORNER
        if ox and oy and math.hypot(x-cx, y-cy) > R_CORNER - margin:
            return False
    for hx, hy in HOLES:
        if math.hypot(x-hx, y-hy) < HOLE_D/2 + margin:
            return False
    return True


def obstacles(board, exclude_net=None):
    """Rectangular obstacles: (x0, y0, x1, y1) in mm.

    These were circumscribed CIRCLES, which is wildly conservative for a 0402: the
    other pad of the same capacitor, 0.96 mm away, blocked every via position within
    1.02 mm, so most pads could never be fanned out. Rectangles from pcbnew's own
    bounding boxes fix that.
    """
    # A via placed next to copper of its OWN net is not a violation - it is a
    # connection. Treating same-net copper as an obstacle is why GND fanout kept
    # failing on a board that is mostly GND.
    obs = []
    def nn(item):
        n = item.GetNet()
        return n.GetNetname() if n else ""
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if exclude_net is not None and nn(pad) == exclude_net: continue
            bb = pad.GetBoundingBox()
            obs.append((TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                        TOMM(bb.GetRight()), TOMM(bb.GetBottom())))
    for t in board.GetTracks():
        if exclude_net is not None and nn(t) == exclude_net: continue
        p = t.GetPosition()
        if t.Type() == pcbnew.PCB_VIA_T:
            x, y = TOMM(p.x), TOMM(p.y)
            obs.append((x - VIA_D/2, y - VIA_D/2, x + VIA_D/2, y + VIA_D/2))
        else:
            a, c = t.GetStart(), t.GetEnd()
            ax, ay, cx, cy = TOMM(a.x), TOMM(a.y), TOMM(c.x), TOMM(c.y)
            hw = TRACK_W/2
            obs.append((min(ax, cx)-hw, min(ay, cy)-hw, max(ax, cx)+hw, max(ay, cy)+hw))
    return obs


def obstacle_shapes(board, exclude_net=None):
    """Obstacles as exact geometry rather than bounding boxes.

    obstacles() models a track by its bounding box. For an axis-aligned trace that is
    exact, but freerouting emits mostly 45 degree traces, and the bbox of a diagonal
    is enormously bigger than the trace - a 2 mm diagonal blocks a 2x2 mm square
    instead of a 0.15 mm ribbon. That over-blocking is why a thorough fanout search
    could place only 1 via out of 32 attempts on pads that were sitting directly over
    their own plane pour. Here a track is a capsule (segment + half width), a via is a
    disc, and a pad stays a rect.

    Shapes are ("rect", x0, y0, x1, y1) or ("cap", x1, y1, x2, y2, radius).
    """
    out = []
    def nn(item):
        n = item.GetNet()
        return n.GetNetname() if n else ""
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if exclude_net is not None and nn(pad) == exclude_net: continue
            bb = pad.GetBoundingBox()
            out.append(("rect", TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                        TOMM(bb.GetRight()), TOMM(bb.GetBottom())))
    for t in board.GetTracks():
        if exclude_net is not None and nn(t) == exclude_net: continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            # PCB_VIA::GetWidth() needs a layer in this KiCad build; bare calls trip
            # an assert and flood stderr with one line per via.
            try:
                r = TOMM(t.GetWidth(board.GetLayerID("F.Cu"))) / 2
            except TypeError:
                r = VIA_D / 2
            out.append(("cap", TOMM(p.x), TOMM(p.y), TOMM(p.x), TOMM(p.y), r))
        else:
            a, c = t.GetStart(), t.GetEnd()
            out.append(("cap", TOMM(a.x), TOMM(a.y), TOMM(c.x), TOMM(c.y),
                        TOMM(t.GetWidth()) / 2))
    return out


HOLE_CLEAR = 0.25      # board setup: hole-to-hole, drill edge to drill edge.
                       # Was 0.20, which is LOOSER than the board's own 0.2495 rule and
                       # than JLCPCB's 0.254 mm same-net minimum - so via placement kept
                       # producing pairs at 0.20-0.246 mm that DRC then flagged. 23 of
                       # them had to be thinned out afterwards by tools/thin_vias.py.


def hole_shapes(board):
    """Every drilled hole as (x_mm, y_mm, drill_radius_mm).

    Copper clearance is not enough on its own. A via can sit a legal 0.48 mm from an
    NPTH pad's COPPER and still be only 0.18 mm from its DRILL, because the hole is
    wider than the annulus is. That is exactly how two VBUS fanout vias landed against
    J1's USB-C mounting holes. Fabricators check drill-to-drill separately, so this
    has to be checked separately too.
    """
    out = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            d = pad.GetDrillSizeX()
            if d > 0:
                p = pad.GetPosition()
                out.append((TOMM(p.x), TOMM(p.y), TOMM(d) / 2.0))
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            out.append((TOMM(p.x), TOMM(p.y), TOMM(t.GetDrill()) / 2.0))
    return out


def hole_ok(x, y, holes, drill=VIA_D):
    """Would a via placed here keep HOLE_CLEAR from every existing hole?

    THE DEFAULT IS VIA_D, THE OUTER DIAMETER - NOT VIA_DRILL. That looks wrong and is
    not: it is what KiCad's DRC actually enforces, measured rather than assumed.

    Three hole_clearance errors survived this guard because it used VIA_DRILL. Worked
    backwards from the DRC report on a via 0.767 mm from J1's 0.70 mm NPTH:

        via radius 0.15 (drill/2)  ->  gap 0.267 mm   guard said PASS
        via radius 0.30 (width/2)  ->  gap 0.117 mm   DRC said 0.117, FAIL

    Both reported violations matched the width-based figure to three decimals, so KiCad
    is measuring from the via's copper edge, not its drill edge. A guard that measures
    something ADJACENT to what the authority measures is not a guard - it is the same
    fault as every other near-miss in this project, and it is why the catch diode was
    missed too. Match the authority.
    """
    r = drill / 2.0
    for hx, hy, hr in holes:
        if math.hypot(x - hx, y - hy) - r - hr < HOLE_CLEAR:
            return False
    return True


def gap_to_shape(x, y, s):
    """Distance from a point to an exact obstacle shape, 0 if inside."""
    if s[0] == "rect":
        return gap_to_rect(x, y, (s[1], s[2], s[3], s[4]))
    _, x1, y1, x2, y2, r = s
    dx, dy = x2 - x1, y2 - y1
    L2 = dx*dx + dy*dy
    if L2 < 1e-12:
        d = math.hypot(x - x1, y - y1)
    else:
        t = max(0.0, min(1.0, ((x - x1)*dx + (y - y1)*dy) / L2))
        d = math.hypot(x - (x1 + t*dx), y - (y1 + t*dy))
    return max(0.0, d - r)


def gap_to_rect(x, y, r):
    """Distance from point (x,y) to rectangle r, 0 if inside."""
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


# Fanout vias are placed by search, not blind, so they only need the real design rule
# plus a little margin. 0.30 was costing more than half of all fanout attempts - and a
# rail pad with no via has NO copper on it at all, since the outer pours are GND.
VIA_CLEAR = CLEAR    # was a separate, more conservative 0.15 while the board's real
                     # rule is 0.1016. That 0.05 mm of invented margin was the only
                     # thing stopping a 0.45 mm via tying down a 9.4 mm2 GND island:
                     # widest gap 0.37, "needed" 0.38. DRC is the arbiter, not a
                     # hand-picked constant.
# The router's own vias are placed on a checked grid, so they only need the real design
# rule plus quantisation. Using the fanout figure here left just 8% of cells via-legal
# while 40% was free for tracks - so most cross-layer nets simply could not be routed.
ROUTE_VIA_CLEAR = CLEAR    # was a separate, more conservative 0.15 while the board's real
                     # rule is 0.1016. That 0.05 mm of invented margin was the only
                     # thing stopping a 0.45 mm via tying down a 9.4 mm2 GND island:
                     # widest gap 0.37, "needed" 0.38. DRC is the arbiter, not a
                     # hand-picked constant. + 0.0625


def keepout_boxes(board):
    out = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            bb = z.GetBoundingBox()
            out.append((TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                        TOMM(bb.GetRight()), TOMM(bb.GetBottom())))
    return out


def fanout(board):
    """Give every GND/+3V3 pad a via down to its plane."""
    kos = keepout_boxes(board)
    holes = hole_shapes(board)
    _obs_cache = {}
    # Vias placed during this pass have to be visible to EVERY later net, not just
    # the one that placed them. Caching per net and appending only to that net's list
    # meant the GND pass and the +3V3 pass were blind to each other, and they duly
    # put a GND via and a +3V3 via 0.42 mm apart - they need 0.75 mm. Placements go
    # in a shared list tagged with their net; same-net copper is still not an
    # obstacle, so the tag is what keeps fanout from blocking itself.
    _placed = []
    def obs_for(net):
        if net not in _obs_cache:
            _obs_cache[net] = obstacle_shapes(board, exclude_net=net)
        return _obs_cache[net] + [r for nm, r in _placed if nm != net]
    occupied = obstacle_shapes(board)

    def clear_at(x, y):
        if not inside_board(x, y, VIA_D/2 + 0.5): return False
        if not hole_ok(x, y, holes): return False
        for x1, y1, x2, y2 in kos:
            if x1 - VIA_D/2 < x < x2 + VIA_D/2 and y1 - VIA_D/2 < y < y2 + VIA_D/2:
                return False
        for r in occupied:
            if gap_to_shape(x, y, r) < VIA_D/2 + VIA_CLEAR: return False
        return True

    made = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNet()
            if net is None or net.GetNetname() not in PLANE: continue
            occupied = obs_for(net.GetNetname())
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH: continue   # already all layers
            p = pad.GetPosition(); px, py = TOMM(p.x), TOMM(p.y)
            pr = math.hypot(TOMM(pad.GetSize().x), TOMM(pad.GetSize().y)) / 2
            _pbb = pad.GetBoundingBox()
            own_rect = ("rect", TOMM(_pbb.GetLeft()), TOMM(_pbb.GetTop()),
                        TOMM(_pbb.GetRight()), TOMM(_pbb.GetBottom()))
            # Be persistent: on the outer layers the pours are GND, so a +3V3 pad with
            # no via has NO copper at all. A timid fanout left 27 of 47 +3V3 pads
            # stranded, which is most of the board's unconnected count.
            placed = False
            base = pr + VIA_D/2 + VIA_CLEAR
            # capped: a long fanout stub is inductance, and it also has to cross
            # more copper. 0.9 mm past the minimum is plenty.
            for rad in [base + d for d in (0.05, 0.2, 0.35, 0.5, 0.7,
                                            0.9, 1.15, 1.4)]:
                for k in range(24):
                    a = k * math.pi / 12
                    vx, vy = px + rad*math.cos(a), py + rad*math.sin(a)
                    # Sample the WHOLE stub. Testing only its midpoint was fine for
                    # 0.5 mm stubs but let longer ones run straight through other pads.
                    steps = max(3, int(math.hypot(vx-px, vy-py) / 0.1))
                    stub_ok = True
                    for r in occupied:
                        # Skip only the source pad's OWN rectangle. The old test
                        # skipped anything whose rect contained the pad origin, and
                        # the bounding box of a long diagonal track can easily do
                        # that - which let a GND stub run straight across CANL.
                        if r == own_rect:
                            continue
                        for t in range(steps + 1):
                            sx = px + (vx-px)*t/steps; sy = py + (vy-py)*t/steps
                            # STUB_W, not TRACK_W. The stub is DRAWN at 0.25 mm
                            # (add_track below) but was CHECKED at TRACK_W 0.1016,
                            # under-checking by 0.074 mm - which is exactly the
                            # shortfall in the two J1 clearance violations this
                            # produced (0.1016 required, 0.0330 actual). Third time in
                            # this file that a guard measured something adjacent to
                            # what gets built: check the width you actually draw.
                            if gap_to_shape(sx, sy, r) < STUB_W/2 + VIA_CLEAR:
                                stub_ok = False; break
                        if not stub_ok: break
                    if clear_at(vx, vy) and stub_ok:
                        add_via(board, vx, vy, net)
                        lay = "F.Cu" if pad.IsOnLayer(board.GetLayerID("F.Cu")) else "B.Cu"
                        add_track(board, (px, py), (vx, vy), lay, net, width=STUB_W)
                        nm = net.GetNetname()
                        _placed.append((nm, ("cap", vx, vy, vx, vy, VIA_D/2)))
                        holes.append((vx, vy, VIA_DRILL/2))
                        # The stub itself is an obstacle too - without this a
                        # later via lands on top of an earlier pad-to-via track.
                        _hw = TRACK_W/2
                        _placed.append((nm, ("cap", px, py, vx, vy, _hw)))
                        occupied = obs_for(nm)
                        made += 1; placed = True; break
                if placed: break
    return made


def stitch(board):
    """GND stitching vias, tying the F/B pours to the L2 plane.

    On a 2.5 mm grid a dense board offered only 13 legal positions, which is far too
    few ties for a ground plane carrying DShot edges. 1.8 mm finds many more.
    """
    gnd = board.FindNet("GND")
    occupied = obstacle_shapes(board)
    holes = hole_shapes(board)
    made = 0
    y = Y0 + 2.0
    while y < Y0 + H - 2.0:
        x = X0 + 2.0
        while x < X0 + W - 2.0:
            ok = (inside_board(x, y, VIA_D/2 + 0.6)
                  and hole_ok(x, y, holes)
                  and all(gap_to_shape(x, y, r) > VIA_D/2 + VIA_CLEAR for r in occupied))
            if ok:
                add_via(board, x, y, gnd); made += 1
                occupied.append(("cap", x, y, x, y, VIA_D/2))
                holes.append((x, y, VIA_DRILL/2))
            x += 1.8
        y += 1.8
    return made


def _cluster(pts, dist=7.0):
    """Single-linkage clustering. Islands must be compact BLOBS, not bounding boxes.

    A bounding box round +3V3A's pads was an 11 x 36 mm strip that bisected the L3
    plane and orphaned the +3V3 base pour on one side of it - 28 unconnected items
    from one badly shaped zone.
    """
    groups = []
    for p in pts:
        hit = [g for g in groups
               if any(math.hypot(p[0]-q[0], p[1]-q[1]) <= dist for q in g)]
        if not hit:
            groups.append([p])
        else:
            merged = [p]
            for g in hit: merged += g
            groups = [g for g in groups if g not in hit] + [merged]
    return groups


def power_islands(board):
    """Give each secondary rail compact regions of the L3 plane.

    Priority is ordered by area, smallest first, so a compact rail always wins where
    regions overlap (KiCad resolves zone overlap by priority). A cluster larger than
    the cap is skipped and left to the router rather than allowed to swallow L3.
    """
    cands = []
    for rail in PLANE:
        if rail in ("GND", "+3V3"): continue          # L2 solid / L3 base pour
        net = board.FindNet(rail)
        if net is None: continue
        pts = []
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNet() and pad.GetNet().GetNetname() == rail:
                    p = pad.GetPosition(); pts.append((TOMM(p.x), TOMM(p.y)))
        if len(pts) < 2: continue
        for grp in _cluster(pts):
            if len(grp) < 2: continue
            m = 0.9
            x1 = max(X0+0.5, min(p[0] for p in grp) - m)
            x2 = min(X0+W-0.5, max(p[0] for p in grp) + m)
            y1 = max(Y0+0.5, min(p[1] for p in grp) - m)
            y2 = min(Y0+H-0.5, max(p[1] for p in grp) + m)
            area = (x2-x1) * (y2-y1)
            # ISLAND_MAX_AREA was referenced here but never defined - this code path
            # raised NameError on every fresh run, so route.py has not completed since
            # whenever the constant was dropped. The routed board in the repo predates
            # that. Restored with an ASSUMED value: these are meant to be LOCAL power
            # islands on In2.Cu, and the board is only 45.1 x 46.1 = 2079 mm2, so an
            # island above ~50 mm2 (2.4% of the board) is not local any more - it starts
            # fragmenting the signal layer it sits on, which is the thing the aspect-ratio
            # test below also guards against.
            if area > ISLAND_MAX_AREA: continue
            # a long thin island still cuts the plane in half - reject those too
            if max(x2-x1, y2-y1) / max(min(x2-x1, y2-y1), 0.1) > 4.0: continue
            cands.append((area, rail, net, x1, y1, x2, y2))

    made = 0
    for prio, (area, rail, net, x1, y1, x2, y2) in enumerate(sorted(cands), start=1):
        z = pcbnew.ZONE(board)
        z.SetLayer(board.GetLayerID("In2.Cu")); z.SetNet(net)
        z.SetAssignedPriority(len(cands) - prio + 1)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetLocalClearance(MM(0.25)); z.SetMinThickness(MM(0.2))
        o = z.Outline(); o.NewOutline()
        for x, y in ((x1,y1),(x2,y1),(x2,y2),(x1,y2)): o.Append(MM(x), MM(y))
        board.Add(z); made += 1
    return made


def fill(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def set_rules(board):
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth   = MM(TRACK_W)
    # The DEFAULT via stays 0.6/0.3 - JLCPCB's recommended pairing and what almost
    # every via on this board uses. The MINIMUM is set to their actual floor, 0.45/0.20,
    # which is still standard-price on 4-layer. That matters for stitching: 27 of the
    # 32 stranded GND connections are pour islands too narrow for a 0.6 mm via, and a
    # 0.45 mm one needs 0.075 mm less room on each side. Without this the board's own
    # rules reject the smaller tier and those islands can never be tied down.
    ds.m_ViasMinSize     = MM(0.45)
    ds.m_MinThroughDrill = MM(0.20)
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_MinClearance        = MM(CLEAR)
    ds.m_HoleClearance       = MM(0.20)
    # The DRC clearance actually applied comes from the DEFAULT NETCLASS, not the
    # min-clearance constraint - and board.Save() rewrites .kicad_pro from it, so
    # editing the project JSON afterwards is silently undone. Set it here.
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(MM(CLEAR))
    nc.SetTrackWidth(MM(TRACK_W))
    nc.SetViaDiameter(MM(VIA_D))
    nc.SetViaDrill(MM(VIA_DRILL))
    ds.m_MinResolvedSpokes   = 1     # 0402 GND pads cannot fit two spokes
    ds.SetCopperLayerCount(6)


def main():
    board = load()
    set_rules(board)
    npi = power_islands(board)
    nf = fanout(board)
    ns = stitch(board)
    fill(board)
    # Signal autorouting is OPT-IN (NAVCORE_AUTOROUTE=1).
    #
    # The maze router below routes ~35% of segments but leaves DRC shorts behind: at
    # this density it has no rip-up-and-retry, so it paints itself into corners and
    # commits copper that later nets violate. A board with 190 shorts is worse than an
    # unrouted one, so the default output is placement + planes + fanout, which is
    # DRC-clean, and the remaining signals stay as ratsnest for manual routing.
    if os.environ.get("NAVCORE_AUTOROUTE") == "1":
        nd, nfail = route_signals(board)
        fill(board)      # refill: new tracks change the pour outlines
        print(f"autoroute: {nd} segments routed, {nfail} failed (EXPECT DRC ERRORS)")
    board.Save(BOARD)
    print(f"power islands: {npi}   fanout vias: {nf}   stitching vias: {ns}   zones: {len(board.Zones())}")




# ---------------------------------------------------------------- autorouter
GRID_MM   = 0.0625   # halved: a 0.1016 mm track needs a 0.305 mm envelope, and at
                     # 0.125 mm the router could not resolve channels that do exist
# keep-out radius around a committed track centreline, seen by OTHER nets:
# my half width + clearance + their half width + grid quantisation
TRK_KEEP  = TRACK_W/2 + 0.15 + TRACK_W/2 + 0.0625
SIG_LAYERS = ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu")

class Router:
    """Grid maze router on the two outer layers, vias between them.

    L2/L3 are planes and are not routed on. Pads of other nets, the board edge, the
    rounded corners, mounting holes and already-routed copper are obstacles.
    """
    def __init__(self, board):
        self.b = board
        self.nx = int(W / GRID_MM); self.ny = int(H / GRID_MM)
        self.lay = [board.GetLayerID(l) for l in SIG_LAYERS]
        # occ[layer][y][x] = net code occupying that cell (0 = free)
        self.occ = [[[0]*self.nx for _ in range(self.ny)] for _ in SIG_LAYERS]
        self.via_ok = [[True]*self.nx for _ in range(self.ny)]
        self.core = [[[False]*self.nx for _ in range(self.ny)] for _ in SIG_LAYERS]
        self.via_cost = 12      # grid steps a layer change costs; tunable per attempt
        self._mark_static()
        self._mark_via_legal()

    def cell(self, x, y): return int((x - X0)/GRID_MM), int((y - Y0)/GRID_MM)
    def pos(self, cx, cy): return X0 + (cx+0.5)*GRID_MM, Y0 + (cy+0.5)*GRID_MM

    def _stamp_rect_phase(self, li, x, y, w, h, m, code, phase):
        """phase 'core' = actual pad copper (protected, owned by its net).
        phase 'halo' = clearance ring: free -> claim; owned by ANOTHER net -> BLOCK.

        First-come-wins was wrong: a cell inside two different nets' keepouts was
        claimed by whichever pad was stamped first, silently discarding the other
        pad's clearance and letting the router lay copper 0.14 mm from it."""
        hw, hh = w/2 + m, h/2 + m
        ci, cj = self.cell(x, y)
        ri = int(hw/GRID_MM) + 1; rj = int(hh/GRID_MM) + 1
        for j in range(max(0, cj-rj), min(self.ny, cj+rj+1)):
            for i in range(max(0, ci-ri), min(self.nx, ci+ri+1)):
                px, py = self.pos(i, j)
                if abs(px - x) > hw or abs(py - y) > hh: continue
                if phase == "core":
                    self.occ[li][j][i] = code; self.core[li][j][i] = True
                else:
                    if self.core[li][j][i]: continue
                    cur = self.occ[li][j][i]
                    if cur == 0: self.occ[li][j][i] = code
                    elif cur != code: self.occ[li][j][i] = -1

    def _stamp_rect(self, li, x, y, w, h, rot_deg, m, code):
        """Rectangular obstacle stamp. A circumscribed circle around a 1.6x0.3 mm
        LQFP pad blocks 0.81 mm, swallowing its 0.5 mm-pitch neighbours and making
        escape routing impossible - so pads are stamped as real rectangles."""
        a = math.radians(-rot_deg); ca, sa = math.cos(a), math.sin(a)
        hw, hh = w/2 + m, h/2 + m
        rad = math.hypot(hw, hh); rc = int(rad/GRID_MM) + 1
        cx, cy = self.cell(x, y)
        for j in range(max(0, cy-rc), min(self.ny, cy+rc+1)):
            for i in range(max(0, cx-rc), min(self.nx, cx+rc+1)):
                px, py = self.pos(i, j)
                dx, dy = px - x, py - y
                lx, ly = dx*ca - dy*sa, dx*sa + dy*ca
                if abs(lx) <= hw and abs(ly) <= hh:
                    if self.occ[li][j][i] == 0: self.occ[li][j][i] = code

    def _stamp(self, li, x, y, r, code):
        cx, cy = self.cell(x, y); rc = int(r/GRID_MM) + 1
        for j in range(max(0, cy-rc), min(self.ny, cy+rc+1)):
            for i in range(max(0, cx-rc), min(self.nx, cx+rc+1)):
                px, py = self.pos(i, j)
                if math.hypot(px-x, py-y) <= r:
                    # same conflict rule as pad halos: a cell inside two different
                    # nets' keepouts belongs to neither
                    if self.core[li][j][i]: continue
                    cur = self.occ[li][j][i]
                    if cur == 0: self.occ[li][j][i] = code
                    elif cur != code: self.occ[li][j][i] = -1

    def _mark_static(self):
        BLOCK = -1
        self._pads = []
        for j in range(self.ny):
            for i in range(self.nx):
                px, py = self.pos(i, j)
                if not inside_board(px, py, TRACK_W/2 + 0.35):
                    for li in range(len(self.lay)): self.occ[li][j][i] = BLOCK
        for fp in self.b.GetFootprints():
            for pad in fp.Pads():
                p = pad.GetPosition()
                # An unconnected pad still returns a NETINFO_ITEM with net code 0,
                # not None - and 0 is the router's "free cell" marker, so every
                # no-connect pad was invisible and got routed straight over.
                net = pad.GetNet()
                code = net.GetNetCode() if (net and net.GetNetCode()) else BLOCK
                # Use pcbnew's own bounding box: it is already in board coordinates
                # and orientation-correct, including for pads on flipped footprints,
                # where my own rotation maths was off by a fraction of a grid cell.
                self._pads.append((pad, code))
        m = CLEAR + TRACK_W/2 + GRID_MM/2      # + grid quantisation
        for phase in ("core", "halo"):
            for pad, code in self._pads:
                bb = pad.GetBoundingBox()
                bx, by = TOMM(bb.GetCenter().x), TOMM(bb.GetCenter().y)
                pw, ph = TOMM(bb.GetWidth()), TOMM(bb.GetHeight())
                for li, lid in enumerate(self.lay):
                    if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH,
                                              pcbnew.PAD_ATTRIB_NPTH) or pad.IsOnLayer(lid):
                        self._stamp_rect_phase(li, bx, by, pw, ph,
                                               0.0 if phase == "core" else m, code, phase)

        for z in self.b.Zones():
            if not z.GetIsRuleArea(): continue
            bb = z.GetBoundingBox()
            for li in range(len(self.lay)):
                x1, y1 = TOMM(bb.GetLeft()), TOMM(bb.GetTop())
                x2, y2 = TOMM(bb.GetRight()), TOMM(bb.GetBottom())
                for jj in range(self.ny):
                    for ii in range(self.nx):
                        px, py = self.pos(ii, jj)
                        if x1 <= px <= x2 and y1 <= py <= y2:
                            self.occ[li][jj][ii] = BLOCK
        for t in self.b.GetTracks():
            net = t.GetNet()
            code = net.GetNetCode() if (net and net.GetNetCode()) else BLOCK
            p = t.GetPosition()
            if t.Type() == pcbnew.PCB_VIA_T:
                for li in range(len(self.lay)):
                    self._stamp(li, TOMM(p.x), TOMM(p.y), VIA_D/2 + CLEAR + TRACK_W/2, code)
            else:
                li = self.lay.index(t.GetLayer()) if t.GetLayer() in self.lay else None
                if li is None: continue
                a, c = t.GetStart(), t.GetEnd()
                n = max(2, int(math.hypot(TOMM(c.x-a.x), TOMM(c.y-a.y))/GRID_MM)+1)
                for k in range(n+1):
                    xx = TOMM(a.x) + (TOMM(c.x)-TOMM(a.x))*k/n
                    yy = TOMM(a.y) + (TOMM(c.y)-TOMM(a.y))*k/n
                    self._stamp(li, xx, yy, TRK_KEEP, code)

    def _mark_via_legal(self):
        """A cell is via-legal only if a 0.6 mm via with full clearance fits there.

        Spatially bucketed: the naive form compared every one of ~100k cells against
        every obstacle, and once the board carried 16k track segments that became
        billions of comparisons and effectively hung. Bucketing to a coarse grid makes
        each cell test only its local neighbourhood.
        """
        need = VIA_D/2 + ROUTE_VIA_CLEAR
        BK = 2.0                                    # bucket size, mm
        buckets = {}
        def add(x, y, r):
            bi, bj = int(x/BK), int(y/BK)
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    buckets.setdefault((bi+di, bj+dj), []).append((x, y, r))

        for fp in self.b.GetFootprints():
            for pad in fp.Pads():
                p = pad.GetPosition()
                add(TOMM(p.x), TOMM(p.y),
                    math.hypot(TOMM(pad.GetSize().x), TOMM(pad.GetSize().y))/2)
        for t in self.b.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                p = t.GetPosition(); add(TOMM(p.x), TOMM(p.y), VIA_D/2)
            else:
                a, c = t.GetStart(), t.GetEnd()
                ax, ay, cx, cy = TOMM(a.x), TOMM(a.y), TOMM(c.x), TOMM(c.y)
                n = max(1, int(math.hypot(cx-ax, cy-ay)/0.4) + 1)
                for k in range(n+1):
                    add(ax + (cx-ax)*k/n, ay + (cy-ay)*k/n, TRACK_W/2)

        for j in range(self.ny):
            for i in range(self.nx):
                x, y = self.pos(i, j)
                if not inside_board(x, y, VIA_D/2 + 0.35):
                    self.via_ok[j][i] = False; continue
                for ox, oy, orad in buckets.get((int(x/BK), int(y/BK)), ()):
                    if math.hypot(ox-x, oy-y) < need + orad:
                        self.via_ok[j][i] = False; break

    def _free(self, li, i, j, code):
        if not (0 <= i < self.nx and 0 <= j < self.ny): return False
        v = self.occ[li][j][i]
        return v == 0 or v == code

    def _soft_ok(self, li, i, j, code):
        """Cell usable if we are willing to rip up whoever is there.

        Hard blocks stay hard: BLOCK cells (board edge, keepouts, contested halos) and
        any cell that is another net's actual PAD copper. Everything else is another
        net's track halo, which can be ripped up and re-routed.
        """
        if not (0 <= i < self.nx and 0 <= j < self.ny): return False
        v = self.occ[li][j][i]
        if v == -1: return False
        if v == 0 or v == code: return True
        return not self.core[li][j][i]

    def route_soft(self, code, a, b, penalty=60):
        """A* that may cross other nets. Returns (path, victim net codes)."""
        t = (0,) + self.cell(*b)
        goals = {(li,) + self.cell(*b) for li in range(len(self.lay))}
        starts = [(li,) + self.cell(*a) for li in range(len(self.lay))]
        dist, prev, pq = {}, {}, []
        for st in starts:
            if self._soft_ok(st[0], st[1], st[2], code):
                dist[st] = 0; heapq.heappush(pq, (0, st))
        h = lambda n: (abs(n[1]-t[1]) + abs(n[2]-t[2]))
        while pq:
            f, cur = heapq.heappop(pq)
            if cur in goals:
                path = [cur]
                while path[-1] in prev: path.append(prev[path[-1]])
                path = list(reversed(path))
                victims = set()
                for (li, i, j) in path:
                    v = self.occ[li][j][i]
                    if v not in (0, -1, code): victims.add(v)
                return [(p[0],) + self.pos(p[1], p[2]) for p in path], victims
            d = dist[cur]
            if f - h(cur) > d: continue
            li, i, j = cur
            for di, dj in ((1,0),(-1,0),(0,1),(0,-1)):
                ni, nj = i+di, j+dj
                if not self._soft_ok(li, ni, nj, code): continue
                v = self.occ[li][nj][ni]
                w = 1 if v in (0, code) else penalty
                nb = (li, ni, nj); nd = d + w
                if nd < dist.get(nb, 1e18):
                    dist[nb] = nd; prev[nb] = cur
                    heapq.heappush(pq, (nd + h(nb), nb))
            other = 1 - li
            nb = (other, i, j)
            if (self.via_ok[j][i] and self._soft_ok(other, i, j, code)
                    and dist.get(nb, 1e18) > d + self.via_cost):
                dist[nb] = d + self.via_cost; prev[nb] = cur
                heapq.heappush(pq, (d + self.via_cost + h(nb), nb))
        return None, set()

    def route_to_any(self, code, a, goals_cells, via_cost=None, start_layer=None):
        """A* from a point to ANY cell in `goals_cells`.

        This is what hand routing actually does: you land the trace on whatever copper
        of that net is nearest, not on one nominated pad. Routing strictly pad-to-pad
        throws away every already-routed track as a landing site, which on a congested
        board is most of the net.

        start_layer pins which signal layer the path may BEGIN on. Without it the
        search starts on all of them, so a route meant to rescue a B.Cu pour island can
        begin on In2.Cu at the same XY and never touch the island at all - it looks
        like a successful route and connects nothing. That is exactly what happened
        three times to the last GND islands.
        """
        if via_cost is not None: self.via_cost = via_cost
        layers = range(len(self.lay)) if start_layer is None else [start_layer]
        starts = [(li,) + self.cell(*a) for li in layers]
        goals = set(goals_cells)
        if not goals: return None
        gx = sum(g[1] for g in goals) / len(goals)
        gy = sum(g[2] for g in goals) / len(goals)
        dist, prev, pq = {}, {}, []
        for st in starts:
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
                nb = (li, i+di, j+dj)
                if not self._free(li, i+di, j+dj, code): continue
                nd = d + 1
                if nd < dist.get(nb, 1e18):
                    dist[nb] = nd; prev[nb] = cur
                    heapq.heappush(pq, (nd + h(nb), nb))
            other = 1 - li
            nb = (other, i, j)
            vc = self.via_cost
            if (self.via_ok[j][i] and self._free(other, i, j, code)
                    and dist.get(nb, 1e18) > d + vc):
                dist[nb] = d + vc; prev[nb] = cur
                heapq.heappush(pq, (d + vc + h(nb), nb))
        return None

    def cells_of_net(self, code, points, radius=1):
        """Grid cells occupied by a net's existing copper, usable as A* goals."""
        out = set()
        for (x, y) in points:
            ci, cj = self.cell(x, y)
            for dj in range(-radius, radius+1):
                for di in range(-radius, radius+1):
                    i, j = ci+di, cj+dj
                    if not (0 <= i < self.nx and 0 <= j < self.ny): continue
                    for li in range(len(self.lay)):
                        if self.occ[li][j][i] == code:
                            out.add((li, i, j))
        return out

    def route(self, code, a, b):
        """A* from point a to point b (mm tuples). Returns list of (layer, x, y)."""
        s = (0,) + self.cell(*a); t = (0,) + self.cell(*b)
        goals = {(li,) + self.cell(*b) for li in range(len(self.lay))}
        starts = [(li,) + self.cell(*a) for li in range(len(self.lay))]
        dist = {}; prev = {}; pq = []
        for st in starts:
            if self._free(st[0], st[1], st[2], code):
                dist[st] = 0; heapq.heappush(pq, (0, st))
        h = lambda n: (abs(n[1]-t[1]) + abs(n[2]-t[2]))
        while pq:
            f, cur = heapq.heappop(pq)
            if cur in goals:
                path = [cur]
                while path[-1] in prev: path.append(prev[path[-1]])
                return [(p[0],) + self.pos(p[1], p[2]) for p in reversed(path)]
            d = dist[cur]
            if f - h(cur) > d: continue
            li, i, j = cur
            for di, dj, w in ((1,0,1),(-1,0,1),(0,1,1),(0,-1,1)):
                nb = (li, i+di, j+dj)
                if not self._free(li, i+di, j+dj, code): continue
                nd = d + w
                if nd < dist.get(nb, 1e18):
                    dist[nb] = nd; prev[nb] = cur
                    heapq.heappush(pq, (nd + h(nb), nb))
            other = 1 - li
            nb = (other, i, j)
            if (self.via_ok[j][i] and self._free(other, i, j, code)
                    and dist.get(nb, 1e18) > d + self.via_cost):
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
                    self._stamp(0, x, y, r, code); self._stamp(1, x, y, r, code)
                    ci, cj = self.cell(x, y); k = int((VIA_D + ROUTE_VIA_CLEAR)/GRID_MM) + 1
                    for jj in range(max(0, cj-k), min(self.ny, cj+k+1)):
                        for ii in range(max(0, ci-k), min(self.nx, ci+k+1)):
                            self.via_ok[jj][ii] = False
                else:
                    add_track(self.b, (prev[1], prev[2]), (x, y), SIG_LAYERS[li], net)
                    self._stamp(li, x, y, TRK_KEEP, code)
                    ci, cj = self.cell(x, y)
                    k = int((VIA_D/2 + ROUTE_VIA_CLEAR + TRACK_W/2)/GRID_MM) + 1
                    for jj in range(max(0, cj-k), min(self.ny, cj+k+1)):
                        for ii in range(max(0, ci-k), min(self.nx, ci+k+1)):
                            self.via_ok[jj][ii] = False
            prev = (li, x, y)


def route_signals(board, limit_seconds=600):
    """Route every net that is not carried by a plane. Returns (done, failed)."""
    import time
    t0 = time.time()
    r = Router(board)
    pads = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNet()
            if not net or not net.GetNetname(): continue
            nn = net.GetNetname()
            if nn in PLANE: continue
            p = pad.GetPosition()
            pads.setdefault(nn, []).append((TOMM(p.x), TOMM(p.y), net))
    done = failed = 0
    # short nets first: they are the most likely to succeed and least likely to block
    order = sorted(pads, key=lambda n: (len(pads[n]), _span(pads[n])))
    for nn in order:
        pts = pads[nn]
        if len(pts) < 2: continue
        net = pts[0][2]; code = net.GetNetCode()
        for a, b in _mst(pts):
            if time.time() - t0 > limit_seconds:
                failed += 1; continue
            path = r.route(code, (a[0], a[1]), (b[0], b[1]))
            if path:
                r.commit(code, net, path); done += 1
            else:
                failed += 1
    return done, failed


def _span(pts):
    return max(math.hypot(p[0]-q[0], p[1]-q[1]) for p in pts for q in pts)


def _mst(pts):
    """Prim MST over pad positions -> list of (a, b) segments to route."""
    n = len(pts); inm = [0]; out = list(range(1, n)); edges = []
    while out:
        best = None
        for i in inm:
            for j in out:
                d = math.hypot(pts[i][0]-pts[j][0], pts[i][1]-pts[j][1])
                if best is None or d < best[0]: best = (d, i, j)
        _d, i, j = best
        edges.append((pts[i], pts[j])); inm.append(j); out.remove(j)
    return edges

if __name__ == "__main__":
    main()
