#!/usr/bin/env python3
"""
Rev B step 2 -- place the 34 new parts on the transplanted board.

Architecture (derived from measured free space, not guessed):

  * The transplant (tools/revb_transplant.py) restored hand-tuned positions for
    the 134 parts this design shares with the committed board. Everything NEW
    starts at a generator scatter position and is PARKED: invisible to the
    conflict checker until this script places it. Without parking, the scatter
    positions block every search (that is exactly why the first version died
    with "U13 has no legal home").
  * Conflict model matches the real gates: footprint-to-footprint distance is
    judged on COURTYARD+PAD extents (GetBoundingBox includes silkscreen text,
    which the passing Rev A board disproves as a collision criterion -- C36
    sat inside U6's bbox there), and screw keepout is judged PAD-TO-HOLE like
    check_mechanical, not bbox-to-point.
  * RF core: J12 (vertical U.FL) on the TOP edge on F.Cu at x~38-42 -- on the
    top face the coax exits upward over the edge, which is the whole point of
    a vertical U.FL. U13 (MAX2112) goes on the B.Cu east canvas (the U6/U7
    ground freed at x 32-42, y 13-20), RFIN pin toward J12, C52 on the
    J12 -> C52 -> RFIN line. R43 shifts east first if the slot needs it,
    guarded by its own ADJACENCY bound to U18.4.
  * Baseband (U14, IQ terminations) is length-tolerant: it packs near U13 if
    there is room, and falls back toward U1's SOOP pads (PC4/PA4) or the big
    west B.Cu region otherwise. Reported, not silent.
  * The 17+1 single solder pads hogging the edges (RELOC, incl. PV1 per the
    plan's Correction 2) move to the nearest FREE interior cell, one at a
    time, each becoming an obstacle for the next. v1's fixed pocket list ran
    out (7 pads had no pocket), and every downstream failure cascaded from
    that: PV1 still on the top edge blocked J12 and J4, the right-edge test
    pads blocked J11. Nearest-free-cell needs no pocket inventory.
  * Q4/DZ1/R46 sit on B.Cu at the power entry, drain toward J2.2/D1.2.
  * Connectors (re-solved 2026-09-09 against measured courtyard/pad geometry and
    the 3.5 mm pad-to-M3 rule check_mechanical enforces; the run-17 arrangement
    put J9/J10/J5 pads 2-2.3 mm off the board and mouths into the board):
      J12  top edge F.Cu rot 180, pos (30.75,1.8) - clear of J1 (ends 28.3),
           R16 (starts 34.1) and hole 1 (RFIN pad 4.4 mm from it)
      J5   top-east corner rot 180, pos (43.45,1.8) - plug corridor through the
           hole-2 triangle; SERVO_PWN claim (design.py:1964) is unused by hwdef
      J11  east edge rot +90, pos (44.20,6.55) - court x 40.0, clear of R16,
           Q1 (0.2 mm court gap, same class as U9-J5), R1 (4.5 mm court gap)
      J10  bottom-east corner rot 0, pos (42.0,44.3) - clear of hole 4 and U17
           (court starts 30.67); hole-3 fence only binds the mid column
      J9   west edge rot -90, pos (2.10,30.00) - court y 25.3..33.7 below J2
      J4   west edge rot +90, pos (1.75,39.85) - court y 36.5..43.2, above the
           hole-4 45-degree fence
    West edge y-span used: J2 to 24.5 + J9 8.4 + J4 6.7 = 39.6 of 46.05.
    Edge connectors keep ONE axial side at the board line; the perpendicular
    overhang is never applied, so no pad crosses the outline (run-17 DRC class).
"""
import os, sys, math
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design, pcbnew, fplib, add_part

# THIS SCRIPT HAS RUN. It is kept for its docstring - the record of where every Rev B
# part went and why - and it must not run again.
#
# Two reasons. It re-places the WHOLE design from scratch, so on the finished board it
# would throw away a hand-tuned layout that took a session to converge and currently
# passes preflight with 0 blocking failures. And it is now stale: it places J4 and J10,
# which were cut from the design, so FPS["J10"] would raise KeyError partway through -
# after it had already moved parts.
#
# If a future board really needs re-placing, start from a banked copy and delete this
# guard deliberately, having read what the docstring says about parking, conflict
# models and the fallback ladder.
if os.environ.get("REVB_PLACE_REALLY") != "yes":
    raise SystemExit(
        "refusing: tools/revb_place_new.py is a spent one-shot.\n"
        "It re-places every part and would destroy the finished layout, and it still\n"
        "places J4/J10 which no longer exist in design.py.\n"
        "Bank the board and set REVB_PLACE_REALLY=yes if that is really what you want.")

BOARD_FILE = sys.argv[1] if len(sys.argv) > 1 else "NAVCORE-SoOP.kicad_pcb"
b = pcbnew.LoadBoard(BOARD_FILE)

# ---- add any design part the board lacks (gen_pcb left U13 unplaced) --------
for ref, comp in sorted(design.COMPONENTS.items()):
    if not comp[1]:                       # schematic-only (PWR_FLAG)
        continue
    if b.FindFootprintByReference(ref):
        continue
    fp = add_part.load_fp(b, ref)
    b.Add(fp)                              # own it FIRST - Flip segfaults otherwise
    for pad in fp.Pads():
        nm = add_part._net_for(ref, pad.GetNumber())
        if nm is None:
            continue
        n = b.FindNet(nm)
        if n is None:
            n = pcbnew.NETINFO_ITEM(b, nm)
            b.Add(n)
        pad.SetNet(n)
    print(f"added {ref} ({comp[2]}) with nets")

out = b.GetBoardEdgesBoundingBox()
X0, Y0 = out.GetLeft() / 1e6, out.GetTop() / 1e6
W, H = out.GetWidth() / 1e6, out.GetHeight() / 1e6

SCREW_R = 2.75        # M3 cap-head radius, hard failure per check_mechanical
HOLE_MARGIN = 0.25    # margin over the screw-head rule
EDGE   = 0.45         # copper-to-edge for ordinary parts
OVERHANG = 3.2        # how far an edge connector may stick past the outline
CLR    = 0.10         # courtyard-bbox inflation for the search

cx, cy = W / 2, H / 2
pitch = design.BOARD["MOUNT"]
HOLES = [(cx + sx * pitch / 2, cy + sy * pitch / 2) for sx in (-1, 1) for sy in (-1, 1)]

FPS = {fp.GetReference(): fp for fp in b.GetFootprints()}

NEW = {'C49','C50','C51','C52','C56','C57','C58','C59','DZ1','J10','J11','J12',
       'J4','J5','J9','Q4','R28','R29','R30','R31','R34','R35','R36','R37',
       'R46','TP22','U13','U14','Y2'}
PARKED = set(NEW)                    # invisible until placed
EDGE_OK = {'J1','J2','J3','J4','J5','J8','J9','J10','J11','J12'}  # may overhang

def side(fp):
    return "F" if fp.GetLayer() == pcbnew.F_Cu else "B"

_CBBOX = {}
def cbbox_mm(fp):
    """Courtyard + pads bbox, local mm. Silkscreen/fab text excluded.
    Cached per reference; the entry is dropped whenever that part moves."""
    ref = fp.GetReference()
    hit = _CBBOX.get(ref)
    if hit is not None:
        return hit
    xs, ys = [], []
    for d in fp.GraphicalItems():
        if d.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            bb = d.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]
            ys += [bb.GetTop(), bb.GetBottom()]
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        xs += [bb.GetLeft(), bb.GetRight()]
        ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        bb = fp.GetBoundingBox()
        xs = [bb.GetLeft(), bb.GetRight()]
        ys = [bb.GetTop(), bb.GetBottom()]
    r = (min(xs)/1e6 - X0, min(ys)/1e6 - Y0, max(xs)/1e6 - X0, max(ys)/1e6 - Y0)
    _CBBOX[ref] = r
    return r

def conflicts(fp):
    s = side(fp)
    ref = fp.GetReference()
    x0, y0, x1, y1 = cbbox_mm(fp)
    x0 -= CLR; y0 -= CLR; x1 += CLR; y1 += CLR
    bad = []
    if ref in EDGE_OK:
        # edge connectors: overhang allowed, but not absurd, and they must
        # still TOUCH the board (not float off in space)
        if x1 < EDGE or y1 < EDGE or x0 > W - EDGE or y0 > H - EDGE:
            bad.append(("off-board", None))
        over = max(0 - x0, 0 - y0, x1 - W, y1 - H)
        if over > OVERHANG:
            bad.append(("overhang", round(over, 2)))
    else:
        if x0 < EDGE or y0 < EDGE or x1 > W - EDGE or y1 > H - EDGE:
            bad.append(("edge", (round(x0,2), round(y0,2), round(x1,2), round(y1,2))))
    # screw heads bear on PAD copper (check_mechanical's rule), so test pads
    # individually against the screw circle, not the whole bbox
    for p in fp.Pads():
        v = p.GetPosition()
        px, py = v.x/1e6 - X0, v.y/1e6 - Y0
        bb = p.GetBoundingBox()
        rad = max(bb.GetWidth(), bb.GetHeight()) / 2e6
        for hx, hy in HOLES:
            d = math.hypot(px - hx, py - hy)
            if d < SCREW_R + rad + HOLE_MARGIN:
                bad.append(("hole", (hx, hy, round(d, 2))))
    for oref, other in FPS.items():
        if other is fp or oref in PARKED: continue
        if side(other) != s: continue
        ox0, oy0, ox1, oy1 = cbbox_mm(other)
        if not (x1 <= ox0 or ox1 <= x0 or y1 <= oy0 or oy1 <= y0):
            bad.append((oref, None))
    return bad

def set_pos(ref, x, y, rot=None, flip_to=None):
    fp = FPS[ref]
    _CBBOX.pop(ref, None)          # the cache must not survive a move
    fp.SetPosition(pcbnew.VECTOR2I(int((X0 + x) * 1e6), int((Y0 + y) * 1e6)))
    if rot is not None:
        fp.SetOrientationDegrees(rot)
    if flip_to is not None:
        want = pcbnew.F_Cu if flip_to == "F" else pcbnew.B_Cu
        if fp.GetLayer() != want:
            fp.Flip(fp.GetPosition(), False)
    return fp

def pad_pos(ref, num):
    fp = FPS[ref]
    for p in fp.Pads():
        if p.GetNumber() == str(num):
            v = p.GetPosition()
            return (v.x / 1e6 - X0, v.y / 1e6 - Y0)
    raise KeyError(f"{ref}.{num}")

def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def adjacency_ok(ref, t_ref, t_pad, max_mm):
    """Mirror check_placement: best pad-of-ref distance to the target pad."""
    tx, ty = pad_pos(t_ref, t_pad)
    fp = FPS[ref]
    return min(math.hypot(p.GetPosition().x/1e6 - X0 - tx,
                          p.GetPosition().y/1e6 - Y0 - ty) for p in fp.Pads()) <= max_mm

report = []
def commit(ref, why):
    fp = FPS[ref]
    x0, y0, x1, y1 = cbbox_mm(fp)
    bad = conflicts(fp)
    tag = "OK " if not bad else "BAD"
    report.append(f"{tag} {ref:5s} ({(x0+x1)/2:6.2f},{(y0+y1)/2:6.2f}) {side(fp)} "
                  f"rot={fp.GetOrientationDegrees():5.1f} {why} {bad[:2] if bad else ''}")
    PARKED.discard(ref)
    return fp

def scan(ref, windows, rots, flip=None, why="", guard=None):
    for rot in rots:
        for (wx0, wy0, wx1, wy1, step) in windows:
            y = wy0
            while y <= wy1 + 1e-9:
                x = wx0
                while x <= wx1 + 1e-9:
                    set_pos(ref, x, y, rot, flip)
                    if not conflicts(FPS[ref]) and (guard is None or guard()):
                        commit(ref, why)
                        return (x, y, rot)
                    x += step
                y += step
    return None

def search(ref, windows, rots, flip=None, why="", fallback=True, guard=None):
    got = scan(ref, windows, rots, flip, why, guard)
    if got: return got
    if fallback:
        # coarse grid, primary rotation first -- this must stay fast
        got = scan(ref, [(0.8, 0.8, W - 0.8, H - 0.8, 0.8)], rots[:1] + rots[1:2], flip,
                   why + " [whole-board fallback]", guard)
        if got: return got
    report.append(f"FAIL {ref:5s} no legal spot (windows tried: {len(windows)}, fallback={fallback})")
    # name the blockers: sample the first window, count conflict reasons,
    # then put the part back where it was so anchors stay honest. The part
    # stays PARKED either way: an unplaced part at a scatter position must
    # not become an obstacle for every later search (that cascade cost run 4).
    was_parked = ref in PARKED
    v0 = FPS[ref].GetPosition()
    rot0 = FPS[ref].GetOrientationDegrees()
    cnt = Counter()
    wx0, wy0, wx1, wy1, step = windows[0]
    y = wy0
    while y <= wy1 + 1e-9:
        x = wx0
        while x <= wx1 + 1e-9:
            set_pos(ref, x, y, rots[0], flip)
            for tag, who in conflicts(FPS[ref]):
                cnt[f"{tag}:{who}" if who else tag] += 1
            x += step
        y += step
    set_pos(ref, v0.x / 1e6 - X0, v0.y / 1e6 - Y0, rot0, flip)
    if was_parked:
        PARKED.add(ref)
    tops = ", ".join(f"{k}x{v}" for k, v in cnt.most_common(5))
    report.append(f"      blockers in window 1: {tops if tops else '(window sampled empty)'}")
    return None

# ============================================================ edge pad relocation
RELOC = ["P72", "P73", "P74", "TP7", "TP8", "P41", "TP4", "P63", "P62",
         "TP1", "TP2", "TP3", "TP21", "PL1", "PL2", "PL3", "D3", "PV1"]
print("== edge pad relocation ==")
GRID_STEP = 0.5
GRIDS = {}
def build_grid(fside):
    """Coarse free-cell map for one face: 0 free, 1 edge band, 2 screw, 3 part."""
    gx, gy = int(W / GRID_STEP) + 1, int(H / GRID_STEP) + 1
    g = [[0] * gx for _ in range(gy)]
    for iy in range(gy):
        y = iy * GRID_STEP
        for ix in range(gx):
            x = ix * GRID_STEP
            if x < EDGE or y < EDGE or x > W - EDGE or y > H - EDGE:
                g[iy][ix] = 1
    for hx, hy in HOLES:
        R = SCREW_R + HOLE_MARGIN
        for iy in range(max(0, int((hy - R) / GRID_STEP)), min(gy, int((hy + R) / GRID_STEP) + 1)):
            for ix in range(max(0, int((hx - R) / GRID_STEP)), min(gx, int((hx + R) / GRID_STEP) + 1)):
                if math.hypot(ix * GRID_STEP - hx, iy * GRID_STEP - hy) <= R:
                    g[iy][ix] = 2
    for oref, other in FPS.items():
        if oref in PARKED: continue
        if side(other) != fside: continue
        bx0, by0, bx1, by1 = cbbox_mm(other)
        for iy in range(max(0, int(by0 / GRID_STEP)), min(gy, int(by1 / GRID_STEP) + 1)):
            row = g[iy]
            for ix in range(max(0, int(bx0 / GRID_STEP)), min(gx, int(bx1 / GRID_STEP) + 1)):
                row[ix] = 3
    return g

def relocate(ref, forbid=None):
    """Move a test pad to the free cell nearest its current position (ring
    search on the coarse grid, conflicts() authoritative), then mark the grid.
    forbid(ix, iy) optionally rejects cells (e.g. connector plug corridors) so
    a relocated pad cannot migrate back into a window this script must keep
    clear."""
    fp = FPS[ref]
    fside = side(fp)
    g = GRIDS.setdefault(fside, build_grid(fside))
    gx, gy = len(g[0]), len(g)
    v = fp.GetPosition()
    c0x = min(max(int((v.x / 1e6 - X0) / GRID_STEP), 0), gx - 1)
    c0y = min(max(int((v.y / 1e6 - Y0) / GRID_STEP), 0), gy - 1)
    for r in range(0, max(gx, gy)):
        cand = [(ix, iy)
                for iy in range(max(0, c0y - r), min(gy, c0y + r + 1))
                for ix in range(max(0, c0x - r), min(gx, c0x + r + 1))
                if max(abs(iy - c0y), abs(ix - c0x)) == r and g[iy][ix] == 0]
        if not cand: continue
        cand.sort(key=lambda c: (c[0] - c0x) ** 2 + (c[1] - c0y) ** 2)
        # no sampling limit: at ring 40 a cand[:60] cap tried 60 of ~320 cells
        # and reported 'no free cell anywhere' while free cells existed
        for ix, iy in cand:
            if forbid and forbid(ix * GRID_STEP, iy * GRID_STEP):
                continue
            x, y = ix * GRID_STEP, iy * GRID_STEP
            set_pos(ref, x, y)
            if conflicts(fp): continue
            bx0, by0, bx1, by1 = cbbox_mm(fp)
            for yy in range(max(0, int(by0 / GRID_STEP)), min(gy, int(by1 / GRID_STEP) + 1)):
                for xx in range(max(0, int(bx0 / GRID_STEP)), min(gx, int(bx1 / GRID_STEP) + 1)):
                    g[yy][xx] = 3
            commit(ref, f"relocated to nearest free cell, ring {r}")
            return True
    report.append(f"FAIL {ref:5s} no free cell anywhere on {fside}")
    PARKED.add(ref)          # stay invisible: do not cascade into later searches
    return False

# ---- U5 stays at its transplanted position.
# The 2026-09-09 re-solve measured every claimed conflict and found none:
# J11's final home is the TOP-east edge, not the east-mid strip U5 courts, and
# everything else J11 reaches is on the other side of the board. Shifting U5
# 2.25 mm west would actually make things worse: its courtyard would cross
# U8's (0.68 mm overlap) and U18's (0.71 mm). U5 has no ADJACENCY rule, so a
# shift stays available as a fallback if routing later demands it.
fp5 = FPS["U5"]
print("   U5 left at its transplanted position (no conflict measured)")

# Pads whose TRANSPLANTED position sits inside a connector window must clear
# it by a real margin. Ring-nearest is the wrong tool there: the nearest free
# cell to an edge pad is 0.5 mm inside the border, which is still inside the
# connector's footprint (run 4 put P72 at (2.0,27.0) exactly where J9 goes).
# These groups get explicit interior windows instead; everything else (P74,
# P41, PV1 -- not in any connector window) keeps ring-nearest.
# U17/TP9/R14/R15 are NOT edge pads but their transplanted bottom-left spots
# sit inside J4's horizontal span; C28/C29/C30 stay (ADJACENCY-pinned to U10,
# which J4's span ends west of).
RELOC = ["P72", "P73", "P74", "TP7", "TP8", "P41", "TP4", "P63", "P62",
         "TP1", "TP2", "TP3", "TP21", "PL1", "PL2", "PL3", "D3", "PV1",
         "U17", "TP9", "TP20",
         "TP5", "TP6", "P61", "P71", "PZ1"]   # occupy the F.Cu pocket U5 must shift into
# R14/R15/R20 dropped from RELOC (2026-09-09 re-solve): J4 no longer takes the
# bottom-WEST span, so nothing needs them moved -- R20 is only vacated for U17.
GROUP_L = ["P72", "P73", "TP7", "TP8", "TP4", "P63", "P62", "D3", "TP9"]
GROUP_R = ["TP3", "TP21", "PL3", "TP20"]   # TP20/PL1 sit in J10's bottom-east
                                            # window (run-18 survey)
WIN_L = [(8.6, 24.0, 27.0, 39.6, 0.5)]     # frees the west edge for J9/J4;
                                           # x>=8.6 clears their courtyard reach
WIN_R = [(18.0, 34.5, 39.2, 40.4, 0.5)]    # frees the right-south edge band
WIN_R2 = [(32.6, 13.2, 35.6, 27.2, 0.5)]   # interior pocket, freemap F.Cu rect
WIN_U17 = [(32.9, 41.0, 38.3, 45.0, 0.25)] # bottom-east band, needs the bottom
                                           # pads (PL1/R20/TP20/PZ2/TP11) gone first
# cells a RELOCATED pad must never take: inside a connector plug corridor
# (left/right edge strips, J4's bottom span, the top edge, U17's band)
def forbid_conn(x, y):
    # fenced to the plug corridors of the connectors' FINAL 2026-09-09
    # assignments (see the connectors block below for the measurements).
    return ((x < 8.3 and 11.8 <= y <= 24.5)    # J2 west corridor
            or (x < 9.1 and 25.3 < y < 33.7)   # J9 west corridor
            or (x < 7.4 and y > 36.4)          # J4 west corridor + corner reach
            or (y < 4.9 and 28.9 < x < 32.6)   # J12 top corridor
            or (y < 4.9 and x > 41.0)          # J5 top-east corridor
            or (x > 39.3 and y < 11.2)         # J11 east corridor
            or (x > 38.4 and y > 41.3)         # J10 bottom-east corridor
            or (x > 32.5 and y > 40.5))        # U17's band

# every relocated pad keeps out of the connector corridors
RELOCATE_FORBID = forbid_conn
# Order matters and is not cosmetic: the priority groups claim scarce windows
# before the ring-nearest pads scatter, and U17 (5.2 mm courtyard, the largest
# relocated part) runs only after PL1/R20 have vacated its window. Run 7 lost
# TP21/PL2/PL3 because TP3 (same group) entered the shared pocket first.
for ref in GROUP_R:
    if ref not in FPS: continue
    if not search(ref, WIN_R, [FPS[ref].GetOrientationDegrees()],
                  flip=side(FPS[ref]), fallback=False, why="clear the right edge for J10"):
        search(ref, WIN_R2, [FPS[ref].GetOrientationDegrees()],
               flip=side(FPS[ref]), fallback=False,
               why="clear the right edge for J10 (interior pocket)")
for ref in ("PL1", "R20", "TP20", "PZ2", "TP11"):
    if ref in FPS:
        relocate(ref, forbid=RELOCATE_FORBID)
for ref in RELOC:
    if ref not in FPS or ref in GROUP_R or ref in ("PL1", "R20", "TP20", "PZ2", "TP11"):
        continue
    if ref == "U17":
        if not search(ref, WIN_U17, [FPS[ref].GetOrientationDegrees()],
                      flip=side(FPS[ref]), fallback=False,
                      why="bottom-east band (bottom pads vacated)"):
            relocate(ref, forbid=RELOCATE_FORBID)   # 222 F.Cu homes exist (probe_u17.py)
    elif ref in GROUP_L:
        if not search(ref, WIN_L, [FPS[ref].GetOrientationDegrees()],
                      flip=side(FPS[ref]), fallback=False, why="clear the left edge for J9/J4"):
            if not search(ref, WIN_R2, [FPS[ref].GetOrientationDegrees()],
                          flip=side(FPS[ref]), fallback=False,
                          why="clear the left edge (interior pocket)"):
                relocate(ref, forbid=RELOCATE_FORBID)
    else:
        if not relocate(ref, forbid=RELOCATE_FORBID):
            # F.Cu is full by this point; a test pad is copper on either face.
            # The transplanted net tie is rebuilt by routing, so the FACE is
            # free to change -- flip and retry on B.Cu.
            fp = FPS[ref]
            want = pcbnew.B_Cu if side(fp) == "F" else pcbnew.F_Cu
            if fp.GetLayer() != want:
                fp.Flip(fp.GetPosition(), False)
                relocate(ref, forbid=RELOCATE_FORBID)

# ================================================================== RF core
print("== RF core ==")
# J12 on the TOP edge, F.Cu, coax mating upward. Keep it clear of J1 (ends
# x 28.3) and R16 (ends x 36.3). fallback=False: a U.FL off the edge is a
# design error, not a placement to scatter into the interior.
if not search("J12", [(38.0, 0.8, 42.0, 2.4, 0.25)], [0], flip="F", fallback=False,
              why="U.FL on the top edge, coax exits upward"):
    raise SystemExit("J12 unplaced - the RF input has no edge home")
jp = pad_pos("J12", "1")
# NOTE: no R43 pre-shift. freemap.py measures the B.Cu free rect at
# (33.25,14.00)-(44.75,20.75), which already excludes the ADJACENCY-pinned
# passives C36 (y<=13.8), R42 (x<=33.0) and R43 (y>=20.9) -- U13 fits with
# all of them left alone. Pre-shifting R43 is what killed the previous run:
# its landing stole the top band of the U13 window.
# U13 on the B.Cu east canvas; pick the rotation that points pad 4 (RFIN) at
# J12 and the spot that makes the chain straight and short.
best = None
for rot in (0, 90, 180, 270):
    for yi in range(0, 65):                  # y 4.8 .. 20.8
        y = 4.8 + yi * 0.25
        for xi in range(0, 53):              # x 32.4 .. 45.2
            x = 32.4 + xi * 0.25
            set_pos("U13", x, y, rot, "B")
            if conflicts(FPS["U13"]): continue
            rfin = pad_pos("U13", "4")
            s = dist(rfin, jp) + abs(rfin[1] - jp[1]) * 2 + abs(rfin[0] - jp[0]) * 0.5
            if best is None or s < best[0]:
                best = (s, x, y, rot)
if best is None:
    print("\n== U13 window blockers (courtyard bboxes, B.Cu) ==")
    for oref, other in sorted(FPS.items()):
        if side(other) != "B" or oref == "U13": continue
        ox0, oy0, ox1, oy1 = cbbox_mm(other)
        if ox1 < 32.0 or ox0 > 45.2 or oy1 < 4.0 or oy0 > 20.5: continue
        print(f"  {oref:5s} ({ox0:5.2f},{oy0:5.2f})-({ox1:5.2f},{oy1:5.2f})")
    raise SystemExit("U13 has no legal home in the east canvas")
set_pos("U13", best[1], best[2], best[3], "B")
commit("U13", "MAX2112, RFIN toward J12")
rfin = pad_pos("U13", "4")
# C52 on the J12 -> RFIN line: sample several points along it with lateral
# slack, so one candidate surviving the screw keepout is enough (the straight
# midpoint sits inside the top-right M3's keepout circle).
c52_win = []
for frac in (0.3, 0.45, 0.6, 0.75):
    px = jp[0] + (rfin[0] - jp[0]) * frac
    py = jp[1] + (rfin[1] - jp[1]) * frac
    for dx, dy in ((0, 0), (1.6, 0), (-1.6, 0), (0, 1.6), (0, -1.6)):
        c52_win.append((max(0.5, px + dx - 0.9), max(0.5, py + dy - 0.9),
                        px + dx + 0.9, py + dy + 0.9, 0.2))
search("C52", c52_win, [0, 90], flip="B", fallback=False,
       why="input coupling in the antenna path")

# ================================================================ connectors
# Edge connectors go in BEFORE the pin-followers: interior parts fill pockets
# greedily and the last-placed parts lose their edge windows (run 2's J5/J4
# failure). fallback=False: a connector that is not on its edge is a design
# error, not something to scatter into the interior.
#
# Rotation convention, read off the PASSING Rev A board rather than derived:
# J1 top rot 180, J2 LEFT edge rot -90, J3 bottom rot 0. MATING_FACE is local
# (0,+1) for every connector, and J9/J10 are declared "same class as J2" --
# so left/right edge means rot -90 exactly like J2, not the +90 a
# mouth=(-sin rot, cos rot) derivation produces.
#
# Edge assignment (edgeprobe.py, on the transplanted board):
#   J5  right-north  y 1.4..8.0    (free 0..9.0, Q1 starts at 9.0)
#   J10 right-south  y 34.4..40.2  (free 34.2..44.9 after PL2/PL3/TP3/TP21 move)
#   J9  left-south   y 25.6..31.4  (left edge free 24.5..45.3 after GROUP_L),
#       fallback left-north y 2.6..11.6 (free 0..11.8)
#   J4  left-south   GH-6P horizontal like J3, x 3.5..19.5 on the bottom band
#       (U17/TP9 cleared by GROUP_L; U10 and its pinned C28/C29/C30 end at
#       x 24.8/27.2 so the x 21..27.5 fallback window is NOT offered)
#   J11 right-north y 14.2..22.6 -- the gap between Q1 and R1 is 9 mm, but
#       U5's courtyard fenced it at x<=42.7. U5 (W25Q128 flash, NO ADJACENCY
#       rule, SPI is length-tolerant) shifts 1.5 mm west to open it; anything
#       still overlapping J11's final courtyard (TP10, P46) relocates after.
print("== connectors ==")
search("J5",  [(43.0, 1.4, 44.7, 8.0, 0.25)], [-90, 90], flip="F", fallback=False,
       why="RC receiver, right edge north")
# J10: the right-south window is fenced by the bottom-right M3 head (pad
# copper must stay 4.05 mm clear, edgeprobe/preflight rule) and right-north
# by U5's courtyard (x<=42.7, y 13.2-23.1). The left-north gap (free y
# 0..11.8) takes J10; J9 keeps the left-south span below J2.
search("J10", [(0.5, 2.6, 2.2, 10.4, 0.25)], [-90, 90], flip="F", fallback=False,
       why="servo port, left edge north (right edge fenced by screw/U5)")
search("J9",  [(0.5, 25.7, 3.0, 31.4, 0.25)],
       [-90, 90], flip="F", fallback=False,
       why="I2C port, left edge south of J2 (J10 owns the north gap)")
search("J4",  [(3.5, 40.9, 17.4, 45.3, 0.25)],
       [0, 180], flip="F", fallback=False, why="companion TELEM1, left-south edge")
# J11 into the gap U5's shift opened; anything still overlapping its final
# courtyard (TP10, P46, ...) relocates below (run 11's DRC showed J11's
# scatter box shorting onto TP8 -- it MUST be on the artwork).
search("J11", [(42.5, 14.2, 44.6, 22.6, 0.25)], [-90, 90], flip="F", fallback=False,
       why="SERIAL2 lidar port, right edge north (U5 shifted west)")
jx0, jy0, jx1, jy1 = cbbox_mm(FPS["J11"])
for oref, other in list(FPS.items()):
    if oref in NEW or oref in EDGE_OK: continue
    if side(other) != "F": continue
    ox0, oy0, ox1, oy1 = cbbox_mm(other)
    if not (jx1 <= ox0 or ox1 <= jx0 or jy1 <= oy0 or oy1 <= jy0):
        relocate(oref, forbid=RELOCATE_FORBID)

# ========================================================== RF pin-followers
print("== RF pin-followers ==")
ux0, uy0, ux1, uy1 = cbbox_mm(FPS["U13"])
def near_pin(ref, pin, span, why, flip="B", rots=(0, 90), fallback=False, east=0.0):
    # east: extra room toward +x -- the B.Cu right column (41-44.75) is the one
    # large free region on this side, so crowded pins reach into it.
    tgt = pad_pos("U13", pin)
    return search(ref, [(tgt[0] - span, tgt[1] - span, tgt[0] + span + east, tgt[1] + span, 0.2)],
                  list(rots), flip=flip, fallback=fallback, why=why)
vcc = sorted(p.split(".")[1] for p in design.NETS["VCC_RF"] if p.startswith("U13."))
for i, ref in enumerate(["C49", "C50", "C51"]):
    near_pin(ref, vcc[i] if i < len(vcc) else "3", 2.0,
             f"U13.{vcc[i] if i < len(vcc) else 3} decoupling", east=0.6)
near_pin("R28", vcc[0] if vcc else "3", 3.0, "+3V3A feed to U13", east=0.6)
for ref, pin in [("C60", "8"), ("C56", "9"), ("R34", "12"), ("R35", "5"), ("R29", "28")]:
    near_pin(ref, pin, 2.4, f"U13.{pin}", east=0.6)
r34_ok = search("R34", [(0, 0, 0, 0, 1)], [0]) if False else None  # placed above
r34 = pad_pos("R34", "2") if r34_ok else None
if r34 is None:
    r34 = pad_pos("U13", "12")
search("C57", [(r34[0] - 1.8, r34[1] - 1.8, r34[0] + 1.8, r34[1] + 1.8, 0.2),
               (r34[0] - 1.8, r34[1] - 1.8, 44.7, r34[1] + 3.6, 0.2)],
       [0, 90], flip="B", fallback=False, why="CPOUT/LOOP")
xtal = pad_pos("U13", "14")
c58_ok = search("C58", [(xtal[0] - 2.2, xtal[1] - 2.2, xtal[0] + 2.2 + 3.0, xtal[1] + 2.2, 0.2)],
                [0, 90], flip="B", fallback=False, why="XTAL series cap")
c58 = pad_pos("C58", "1") if c58_ok else xtal
# Y2 is 3.2x2.5 (courtyards -> ~3.8x3.4): the B.Cu column east of U13 is only
# ~2.75 mm wide, so aim Y2 at the free slot SOUTH of U13 (freemap: B.Cu free
# from y 22.5 down to R43) within reach of the XTAL pad.
search("Y2", [(c58[0] - 1.2, c58[1] + 0.6, 44.9, c58[1] + 8.0, 0.2),
              (c58[0] - 1.2, max(0.6, c58[1] - 8.0), 44.9, c58[1] - 0.6, 0.2)],
       [0, 90, 180, 270], flip="B", fallback=False, why="25 MHz TCXO at the XTAL pin")


# ================================================================== baseband
print("== baseband ==")
# U14 measured (probe_u14.py, exhaustive on real courtyard bboxes): exactly one
# legal B.Cu home exists outside U13's own pocket -- the west strip at
# (~4.45, 14.5), under J2's overhang. The east B.Cu column is 2.45 mm wide and
# every neighbour (C26/C27/R41/C73/R5) is ADJACENCY-pinned to a buck pad, so
# the plan's 'RF block contiguous' guideline cannot hold for U14 as a
# courtyard-level fact. It is satisfied where it is checkable: the RF path
# J12 -> C52 -> U13.4 and Y2 stay within ~15 mm of each other, while U14 --
# the baseband op-amp whose OUTPUTS feed U1's west-side ADCs -- sits at the
# ADC side. Recorded here so nobody 'fixes' it back into a wall.
if not search("U14", [(3.6, 13.6, 5.3, 15.4, 0.25)], [0], flip="B", fallback=False,
              why="OPA2374 in the west B.Cu strip, at the U1 ADC side"):
    raise SystemExit("U14 has no legal home (west strip window failed)")
for ref, pin in [("R30", "17"), ("R31", "18"), ("R36", "19"), ("R37", "20"),
                 ("C61", "21"), ("C62", "22"), ("C63", "23"), ("C64", "24")]:
    near_pin(ref, pin, 3.0, f"U13.{pin}", fallback=True, east=0.6)
u13bb = cbbox_mm(FPS["U13"])
search("C59", [(u13bb[0] - 2.0, u13bb[1] - 2.0, u13bb[2] + 2.0, u13bb[3] + 2.0, 0.25)],
       [0, 90], flip="B", fallback=False, why="VCC_RF bulk at U13")

# =============================================================== P-FET cluster
print("== P-FET cluster ==")
# fallback=False on all three: the P-FET belongs at the power entry, and a
# whole-board fallback would silently strand it 30 mm from J2/D1. The cluster
# packs into y <= 10.2 of the west strip: U14's courtyard owns y >= 10.55.
search("Q4", [(0.9, 2.5, 6.5, 10.2, 0.2)], [0, 90, 180, 270], flip="B", fallback=False,
       why="reverse-polarity FET at power entry")
q4s = pad_pos("Q4", "2")
search("DZ1", [(max(0.5, q4s[0] - 4.0), max(0.6, q4s[1] - 5.5), q4s[0] + 4.0, q4s[1] + 2.0, 0.2)],
       [0, 90], flip="B", fallback=False, why="clamp on VBAT at Q4 source")
search("R46", [(max(0.5, q4s[0] - 4.0), max(0.6, q4s[1] - 5.5), q4s[0] + 4.0, q4s[1] + 2.0, 0.2)],
       [0, 90], flip="B", fallback=False, why="gate pull-down")

j10c = FPS["J10"].GetPosition()
j10mm = (j10c.x/1e6 - X0, j10c.y/1e6 - Y0)
search("TP22", [(j10mm[0] + 1.0, j10mm[1] - 4.0, j10mm[0] + 4.5, j10mm[1] + 4.0, 0.25)],
       [0], flip="F", why="VSERVO test point at the servo port")



print()
print("== report ==")
# A ref that failed its primary window but landed on a later one shows both a
# FAIL line and an OK line; the FAIL is history, not a problem. Keep the OK,
# drop the stale FAIL/blocker lines for any ref that ultimately committed.
ok_refs = {ln.split()[1] for ln in report if ln.startswith("OK ")}
shown = [ln for ln in report
         if not (ln.startswith("FAIL ") or ln.startswith("      blockers"))
         or ln.split()[1] not in ok_refs]
for line in shown:
    print(line)
nbad = sum(1 for r in shown if r.startswith("BAD") or r.startswith("FAIL"))
print(f"\n{len(report)} placements, {nbad} problems")
if nbad == 0:
    b.Save(BOARD_FILE)
    print("saved")
else:
    print("NOT saved - fix the failures and re-run from the clean transplant")

# on U13 failure, dump what actually blocks the window
if "U13" in PARKED:
    print("\n== U13 window blockers (courtyard bboxes, B.Cu) ==")
    for oref, other in sorted(FPS.items()):
        if side(other) != "B" or oref == "U13": continue
        ox0, oy0, ox1, oy1 = cbbox_mm(other)
        if ox1 < 32.0 or ox0 > 45.2 or oy1 < 4.0 or oy0 > 20.5: continue
        print(f"  {oref:5s} ({ox0:5.2f},{oy0:5.2f})-({ox1:5.2f},{oy1:5.2f})")
