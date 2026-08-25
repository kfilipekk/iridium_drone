#!/usr/bin/env python3
"""
Generate NAVCORE-SoOP.kicad_pcb from tools/design.py using KiCad's own pcbnew API.

Using the API rather than emitting s-expressions means the file format and, critically,
the back-side flip convention are correct by construction - a mirrored footprint that
looks fine on screen but is unbuildable is exactly the failure this avoids.

Board is 41.6 x 39.4 mm with a 30.5 mm M3 pattern, so at 133% of one side's area the
layout is necessarily two-sided.
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design, fplib

MM  = pcbnew.FromMM
# Overridable so the generator can be exercised without overwriting a routed board.
# This file rebuilds the PCB from scratch, so running it to check a placement change
# used to mean throwing away every trace on the board first.
OUT = os.environ.get("GEN_PCB_OUT", "NAVCORE-SoOP.kicad_pcb")

# board geometry (absolute, matching the outline already drawn)
# Board grew from 41.6x39.4 to 45.0x46.0 mm. The ESC it stacks on is 45.6x44.0,
# so this overhangs by 2 mm on one axis only - mechanically identical, same
# 30.5 mm M3 pattern. The height is set by needing the microSD (17.3 mm with
# clearance) to sit entirely CLEAR of the MCU on the back face. The SpeedyBee ESC it stacks on is
# 45.6x44.0, so this is still the SMALLER board in the stack - it costs nothing
# mechanically and takes courtyard density from 71% to ~52%. The old size left the
# microSD directly under 39 of the MCU's 100 pads, so ~40% of the H743 had nowhere
# to put its decoupling on either face.
X0, Y0, W, H, R = (design.BOARD["X0"], design.BOARD["Y0"], design.BOARD["W"],
                   design.BOARD["H"], design.BOARD["R"])
MOUNT, HOLE_D   = design.BOARD["MOUNT"], design.BOARD["HOLE_D"]
CX, CY = X0 + W/2, Y0 + H/2
HOLES = [(CX+dx, CY+dy) for dx in (-MOUNT/2, MOUNT/2) for dy in (-MOUNT/2, MOUNT/2)]

# ---- placement zones, in board-local mm: (x0, y0, x1, y1, back?) -----------
ZONES = {
 # U1 occupies y 8.4-26.8 on the top; the microSD y 27.4-45.4 on the back, fully clear
 # of it. At 43 and 44 mm tall they still overlapped, which left the MCU's lower pins
 # with no back-side space for decoupling - the reason the board grew at all.
 "T_N":    ( 8.0,  0.6, 37.0,  8.6, False),   # USB-C (needs 7.55) + ESC conn
 "MCU":    ( 9.6,  8.8, 35.4, 27.2, False),   # STM32H743 + its decoupling ring
 "T_W":    ( 0.6,  8.8,  9.2, 27.4, False),   # 5V buck
 "T_E":    (35.8,  8.8, 44.4, 27.4, False),   # 9V buck, CAN
 "T_S":    ( 0.6, 27.6, 44.4, 45.4, False),   # GPS conn + pads, full width
 "B_N":    ( 8.0,  0.6, 37.0,  7.2, True),
 "B_W":    ( 0.6,  7.6, 12.0, 27.2, True),
 "B_MCU":  (12.4,  7.6, 33.0, 27.2, True),    # decoupling directly under the MCU
 "B_E":    (33.4,  7.6, 44.4, 27.2, True),    # flow + ToF looking down
 "B_SD":   ( 9.0, 27.8, 35.4, 45.4, True),    # microSD, fully clear of the MCU
 "B_WS":   ( 0.6, 27.8,  8.6, 45.4, True),
 "B_ES":   (35.8, 27.8, 44.4, 45.4, True),
}


# Which way is "off the board" from each zone, as a board-space unit vector. Only zones
# that hold a connector need an entry.
#
# This is the half of zone_of() that was missing. The placer knew J1 belonged in the top
# strip and J2 on the left, and picked their rotation purely to make them FIT - 0 or 90,
# whichever packed - so both ended up with their openings facing INTO the board. J1 was
# fatal: no cable could be plugged in, so the board could not be flashed or talked to.
ZONE_FACING = {
    "T_N": (0.0, -1.0),   # top edge
    "T_S": (0.0, +1.0),   # bottom edge
    "T_W": (-1.0, 0.0),   # left edge
    "T_E": (+1.0, 0.0),   # right edge
    "B_SD": (0.0, +1.0),  # microSD, card comes out of the bottom edge
    "B_WS": (-1.0, 0.0),
    "B_ES": (+1.0, 0.0),
    "B_N": (0.0, -1.0),
}


def required_rotation(ref, zname, flipped):
    """Rotation that turns this connector's opening toward its zone's outward edge.

    Solved by trying all four quarter turns through the same transform
    tools/check_connectors.py verifies with, rather than by a hand-written table of
    cases - the two then cannot disagree, and a footprint whose mating face is not +y
    is handled without touching this function."""
    face = design.MATING_FACE.get(ref)
    want = ZONE_FACING.get(zname)
    if face is None or want is None: return None
    fx, fy = face
    if flipped: fy = -fy
    best, bestdot = 0, -2.0
    for rot in (0, 90, 180, 270):
        a = math.radians(-rot)
        gx = fx*math.cos(a) - fy*math.sin(a)
        gy = fx*math.sin(a) + fy*math.cos(a)
        dot = gx*want[0] + gy*want[1]
        if dot > bestdot: best, bestdot = rot, dot
    return best


# At 1.6 GHz the LNA -> SAW -> tuner chain must stay together; the generic fallback
# scattered it across the board. These refs get their zone or nothing.
RF_REFS = {"U13", "U14", "U15", "U16", "Y2", "FL1", "J9"}
# IMUs must sit at the board centroid for clean gyro data - also no fallback.
FIXED_REFS = RF_REFS | {"U1", "U2", "U3", "U4", "J8", "J1", "J2", "J3"}


def zone_of(ref):
    val = design.COMPONENTS[ref][2]
    if ref == "U1": return "MCU"
    if ref == "J8": return "B_SD"
    if ref in ("U2","U3","U4"): return "B_MCU"                    # IMUs+baro at centroid
    if ref in ("U6","U7"): return "B_E"                       # flow + ToF look down
    if ref in ("U8","U9","U10","L2","D1"): return "T_W"
    # One connector per edge. The top strip holds only one once the mounting hole
    # pushes it to centre, and J1 must stay clear of the microSD underneath.
    if ref == "J1": return "T_N"      # USB-C, top edge
    if ref == "J2": return "T_W"      # ESC 8-pin, left edge (rotates)
    if ref == "J3": return "T_S"      # GPS, bottom edge
    
    if ref in ("U13","U14","U15","U16","Y2","FL1","J9"): return "B_W"
    if ref.startswith("TP"): return "B_ES"
    if ref.startswith("P") and ref[1:].isdigit(): return "T_S"
    return None                                                 # passives: follow their net

# passives follow the block they decouple
BLOCK_HINT = [
 (("C17","C18","C19","C20","C21","C22","C23","C24","C25","C26","C27","C28","C29",
   "R4","R5","R6","R7","R8"), "T_W"),
 (("C31","C32","C33","C34","C35","C30"), "B_MCU"),
 (("C37","C38","C39","C40","R13","R9","R10"), "B_E"),
 (("C45","C46","R22","R23","R24","R25","R26","R27"), "B_SD"),
 (("C42","R16","R17"), "T_N"),
 (("C41","R14","R15","R20","R21","D2","D3"), "T_S"),
]
RF_PREFIX_MIN = 47   # C47.. and R28.. belong to the RF block

def resolve_zone(ref):
    z = zone_of(ref)
    if z: return z
    for refs, zz in BLOCK_HINT:
        if ref in refs: return zz
    if ref[0] in "CRL" and ref[1:].isdigit() and int(ref[1:]) >= RF_PREFIX_MIN:
        return "B_W"
    return "T_E"

class Packer:
    """Free-rectangle bin packer, one instance per placement zone.

    Shelf packing wasted most of the board: a single 17.5 mm part consumed a whole
    strip. This keeps a list of free rectangles, places into the best-fitting one,
    and splits the remainder - so small passives reuse the gaps big parts leave.
    """
    def __init__(self, x0, y0, x1, y1):
        self.free = [(x0, y0, x1, y1)]

    def carve(self, a, b, c, d):
        """Remove a rectangle from the free list (a through-hole part on the other side)."""
        out = []
        for (fa, fb, fc, fd) in self.free:
            if fa >= c or fc <= a or fb >= d or fd <= b:
                out.append((fa, fb, fc, fd)); continue
            if fa < a: out.append((fa, fb, a, fd))
            if fc > c: out.append((c, fb, fc, fd))
            if fb < b: out.append((fa, fb, fc, b))
            if fd > d: out.append((fa, d, fc, fd))
        self.free = [r for r in out if r[2]-r[0] > 0.2 and r[3]-r[1] > 0.2]

    def place_near(self, w, h, tx, ty, reject=None, max_dist=None):
        """Place as close as possible to (tx, ty) instead of wherever it fits best.

        Best-fit packing is what scattered the decoupling: it optimises for wasted
        area, which has nothing to do with electrical distance.
        """
        best = None
        for idx, (a, b, c, d) in enumerate(self.free):
            if c - a < w or d - b < h: continue
            # closest legal centre inside this rect
            cx = min(max(tx, a + w/2), c - w/2)
            cy = min(max(ty, b + h/2), d - h/2)
            if reject and reject(cx, cy, w, h): continue
            dist = math.hypot(cx - tx, cy - ty)
            if max_dist is not None and dist > max_dist:
                continue          # the limit is a CONSTRAINT, not a preference
            if best is None or dist < best[0]:
                best = (dist, idx, cx, cy)
        if best is None: return None
        _d, idx, cx, cy = best
        a, b = cx - w/2, cy - h/2
        self._split(a, b, a + w, b + h)
        return cx, cy

    def _split(self, a, b, rx1, ry1):
        out = []
        for (fa, fb, fc, fd) in self.free:
            if fa >= rx1 or fc <= a or fb >= ry1 or fd <= b:
                out.append((fa, fb, fc, fd)); continue
            if fa < a:   out.append((fa, fb, a, fd))
            if fc > rx1: out.append((rx1, fb, fc, fd))
            if fb < b:   out.append((fa, fb, fc, b))
            if fd > ry1: out.append((fa, ry1, fc, fd))
        out = [r for r in out if r[2]-r[0] > 0.2 and r[3]-r[1] > 0.2]
        keep = []
        for i, r in enumerate(out):
            if not any(i != j and o[0] <= r[0] and o[1] <= r[1]
                       and o[2] >= r[2] and o[3] >= r[3] for j, o in enumerate(out)):
                keep.append(r)
        self.free = keep

    def place(self, w, h, reject=None):
        best, bi, bpos = None, -1, None
        for i, (a, b, c, d) in enumerate(self.free):
            if c - a < w or d - b < h: continue
            # Try several positions inside the rect, not just its corner. Testing only
            # the corner meant one rejected spot (a mounting-hole keepout) threw away
            # the whole rectangle - which is why a connector could not be placed in an
            # otherwise empty zone.
            spot = None
            for fx in (0.0, 0.5, 1.0):
                for fy in (0.0, 0.5, 1.0):
                    cx = a + w/2 + fx * (c - a - w)
                    cy = b + h/2 + fy * (d - b - h)
                    if reject and reject(cx, cy, w, h): continue
                    spot = (cx, cy); break
                if spot: break
            if spot is None: continue
            fit = min(c - a - w, d - b - h)          # best short-side fit
            if best is None or fit < best:
                best, bi, bpos = fit, i, spot
        if bi < 0: return None
        px, py = bpos
        a, b = px - w/2, py - h/2
        rx1, ry1 = a + w, b + h
        out = []
        for (fa, fb, fc, fd) in self.free:               # split every overlapping rect
            if fa >= rx1 or fc <= a or fb >= ry1 or fd <= b:
                out.append((fa, fb, fc, fd)); continue
            if fa < a:   out.append((fa, fb, a, fd))
            if fc > rx1: out.append((rx1, fb, fc, fd))
            if fb < b:   out.append((fa, fb, fc, b))
            if fd > ry1: out.append((fa, ry1, fc, fd))
        # prune degenerate and fully-contained rectangles
        out = [r for r in out if r[2]-r[0] > 0.2 and r[3]-r[1] > 0.2]
        keep = []
        for i, r in enumerate(out):
            if not any(i != j and o[0] <= r[0] and o[1] <= r[1]
                       and o[2] >= r[2] and o[3] >= r[3] for j, o in enumerate(out)):
                keep.append(r)
        self.free = keep
        return px, py


def corner_clash(x, y, w, h):
    """Reject anything poking into a rounded corner (board is R4, not square)."""
    for cx, cy in ((X0+R, Y0+R), (X0+W-R, Y0+R), (X0+R, Y0+H-R), (X0+W-R, Y0+H-R)):
        for sx in (-1, 1):
            for sy in (-1, 1):
                px, py = x + sx*w/2, y + sy*h/2
                outx = (px < X0+R and cx == X0+R) or (px > X0+W-R and cx == X0+W-R)
                outy = (py < Y0+R and cy == Y0+R) or (py > Y0+H-R and cy == Y0+H-R)
                if outx and outy and math.hypot(px-cx, py-cy) > R - 0.3:
                    return True
    return False


def hole_clash(x, y, w, h, pad=0.3):
    for hx, hy in HOLES:
        if (abs(hx - x) < w/2 + HOLE_D/2 + pad) and (abs(hy - y) < h/2 + HOLE_D/2 + pad):
            return True
    return False

def main():
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    board.GetDesignSettings().SetBoardThickness(MM(1.6))

    # ---- nets ------------------------------------------------------------
    netmap = {}
    for name in design.NETS:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni); netmap[name] = ni

    # pad -> net lookup, using the same resolver the checker uses
    import symlib
    syms = symlib.load()
    pin_net = {}
    for netname, specs in design.NETS.items():
        for sp in specs:
            ref, pin = sp.split(".", 1)
            if ref not in design.COMPONENTS: continue
            pin_net.setdefault(ref, {})[pin] = netname

    # ---- load + place ----------------------------------------------------
    packers = {k: Packer(v[0], v[1], v[2], v[3]) for k, v in ZONES.items()}
    placed, overflow = 0, []
    side_boxes = []       # (x0,y0,x1,y1,side) of everything placed so far
    targets = {}          # ref -> (x, y) in board coords, filled as anchors land

    # Pass 1 places anchors and anything with no adjacency rule (by size, as before);
    # pass 2 places the parts that must sit next to a specific pin, once that pin's
    # owner has a position. Two passes are enough because every ADJACENCY target is
    # an IC or connector, and those are all anchors or large parts placed in pass 1.
    ADJ = getattr(design, "ADJACENCY", {})
    by_area = sorted(design.COMPONENTS, key=lambda r: -_area(r))
    # Order by how CONSTRAINED a part is, not by how big it is:
    #   1. anchors        - their position is functional (MCU, IMUs, connectors)
    #   2. adjacency parts - must sit within millimetres of a specific pin
    #   3. everything else - can go anywhere, so it goes last
    # The first attempt placed by size throughout, so unconstrained passives took the
    # space the decoupling needed and 16 attracted parts had nowhere to go.
    # Solder pads and test points are small but must reach a board EDGE to be
    # usable, so they are placed before generic passives rather than last.
    is_pad = lambda r: (r.startswith("TP")
                        or (r[0] == "P" and (r[1:].isdigit() or r[1] in "ZLV")))
    # Anything an ADJACENCY rule POINTS AT must be placed before the parts that aim
    # at it - otherwise targets[] is empty when they are placed and they fall through
    # to best-fit, which is how U11/U18/U6 ended up with no room at all.
    TARGETS = {t for (t, _p, _m) in ADJ.values()} - FIXED_REFS
    # Order by constraint, tightest first. There is 722 mm2 of headroom, so nothing
    # here is a capacity problem - it is fragmentation, and whoever goes last loses.
    #   1. anchors        - position is functional (MCU, IMUs, connectors)
    #   2. pads/testpoints - only 192 mm2 total, but they MUST reach a board edge,
    #                        so they go early where they cannot be starved
    #   3. adjacency targets - the ICs that other parts must sit next to
    #   4. adjacency parts   - the decoupling itself
    #   5. everything else   - genuinely free to go anywhere
    TARGETS = {t for (t, _p, _m) in ADJ.values()} - FIXED_REFS
    rest = lambda r: r not in FIXED_REFS and r not in TARGETS and r not in ADJ
    # Adjacency parts are NOT placed by zone. A 0402 that must sit within 2 mm of a
    # pin does not care which rectangle it is in - it cares about free space next to
    # that pin. Zone packing kept putting them 15-25 mm away because that was where a
    # rectangle happened to fit. They get a direct spiral search instead, after
    # everything else has claimed its space.
    adj_parts = [r for r in by_area if r not in FIXED_REFS and r not in TARGETS and r in ADJ]
    order = ([r for r in by_area if r in FIXED_REFS]
             + [r for r in by_area if rest(r) and is_pad(r)]
             + [r for r in by_area if r in TARGETS]
             + [r for r in by_area if rest(r) and not is_pad(r)])
    def place_by_zone(reflist):
        nonlocal placed
        deferred = []
        relax_factor = 1.0
        for relaxed in (False, True, True, True):
          if relaxed: relax_factor *= 2.5
          todo_now, deferred = (list(reflist), []) if not relaxed else (deferred, [])
          for ref in [r for r in todo_now if r not in adj_parts]:
              lib_id, fpid, val, lcsc, dnp = design.COMPONENTS[ref]
              if not fpid: continue                                    # PWR_FLAG: schematic only
              path = fplib.find(fpid)
              fp = pcbnew.FootprintLoad(os.path.dirname(path),
                                        os.path.basename(path)[:-len(".kicad_mod")])
              if fp is None:
                  overflow.append((ref, "load failed")); continue
              # FootprintLoad returns an FPID with no library nickname, so every part
              # then fails schematic parity against a symbol that has one. 199 of the
              # board's 218 parity issues were exactly this and nothing else.
              if ":" in fpid:
                  _n, _m = fpid.split(":", 1)
                  fp.SetFPID(pcbnew.LIB_ID(_n, _m))
              info = fplib.load(fpid)
              has_th = any(pd['type'] in ('thru_hole', 'np_thru_hole')
                           for pd in info['pads'])
              # Ask pcbnew for the real courtyard. Our own bbox missed fp_poly/arc outlines,
              # which showed up later as courtyard-overlap DRC errors.
              w = h = None
              for cl in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                  poly = fp.GetCourtyard(cl)
                  if poly.OutlineCount():
                      bb = poly.BBox()
                      w = pcbnew.ToMM(bb.GetWidth()); h = pcbnew.ToMM(bb.GetHeight())
                      break
              # Some footprints (the U.FL connector notably) declare a courtyard SMALLER
              # than their own pad extent, so neighbours got packed on top of the pads.
              # Take whichever is larger.
              if info['pads']:
                  pxs = [pd['x'] + sx*pd['sx']/2 for pd in info['pads'] for sx in (-1, 1)]
                  pys = [pd['y'] + sy*pd['sy']/2 for pd in info['pads'] for sy in (-1, 1)]
                  pw, ph = max(pxs) - min(pxs) + 0.5, max(pys) - min(pys) + 0.5
              else:
                  pw = ph = 0.0
              if not w: w, h = info['w'], info['h']
              extra = 0.8 if ref == "J8" else 0.25   # microSD keeps overlapping neighbours
              w = max(w, pw) + extra; h = max(h, ph) + extra
              z = resolve_zone(ref)
              zx0, zy0, zx1, zy1, back = ZONES[z]

              ok = False
              if ref in FIXED_REFS:
                  # Connectors must reach an edge but either edge will do; the MCU, IMUs
                  # and microSD have exactly one correct home.
                  # USB-C on a side edge is normal, and the top strip cannot hold two
                  # connectors once the mounting hole pushes the first one to centre.
                  cand = [z] + (["T_N", "T_E", "T_W", "T_S"]
                                if ref.startswith("J") and ref != "J8" else [])
                  cand = list(dict.fromkeys(cand))
              elif is_pad(ref) and ref not in ADJ:
                  cand = ["T_S", "T_N", "B_ES", "B_WS", "B_N", "T_E", "T_W",
                          "B_E", "B_W", "B_MCU", "B_SD", "MCU"]
              elif ref in ADJ and ref in targets:
                  # go wherever is closest to the pin, including the opposite face - a cap
                  # directly under its IC with a via is the shortest loop there is
                  tx, ty = targets[ref]
                  cand = sorted(ZONES, key=lambda k: (
                      max(ZONES[k][0] - (tx-X0), 0, (tx-X0) - ZONES[k][2]) ** 2 +
                      max(ZONES[k][1] - (ty-Y0), 0, (ty-Y0) - ZONES[k][3]) ** 2))
              else:
                  same = [k for k in ZONES if k != z and ZONES[k][4] == ZONES[z][4]]
                  other = [k for k in ZONES if ZONES[k][4] != ZONES[z][4]]
                  cand = [z] + same + other         # last resort: either side
              for zname in cand:
                  bk = ZONES[zname][4]
                  rej = (lambda cx, cy, ww, hh: hole_clash(X0+cx, Y0+cy, ww, hh)
                                                or corner_clash(X0+cx, Y0+cy, ww, hh))
                  # A part with through-hole features must clear the OPPOSITE side
                  # entirely, not merely other TH pads - the USB-C shell pins landed
                  # on top of the microSD's SMD pads otherwise.
                  if has_th:
                      _o = "F.Cu" if bk else "B.Cu"
                      rej = (lambda cx, cy, ww, hh, _r=rej, _oo=_o:
                             _r(cx, cy, ww, hh) or any(
                                 not (X0+cx+ww/2+0.2 <= a or c+0.2 <= X0+cx-ww/2
                                      or Y0+cy+hh/2+0.2 <= b or d+0.2 <= Y0+cy-hh/2)
                                 for (a, b, c, d, sd) in side_boxes if sd == _oo))
                  # If we know which pin this part serves, place it AT that pin. Best-fit
                  # packing optimises wasted area, which has nothing to do with electrical
                  # distance - that is what left VCAP2 30 mm from the H743.
                  tgt = targets.get(ref)
                  pos = None
                  # A connector's rotation is decided by the edge it sits on, not by what
                  # packs. Reserve the footprint the right way round so the packer cannot
                  # hand back a slot that only fits the other orientation.
                  forced = required_rotation(ref, zname, bk)
                  pw, ph = ((h, w) if forced in (90, 270) else (w, h))
                  if forced is not None:
                      pos = packers[zname].place_near(pw, ph, tgt[0]-X0, tgt[1]-Y0,
                                                      reject=rej) if tgt else None
                      if pos is None: pos = packers[zname].place(pw, ph, reject=rej)
                      if pos is None: continue
                      rot = forced
                  elif tgt is not None:
                      # Honour the adjacency limit as a hard constraint first. Only if no
                      # zone can satisfy it do we relax - and the relaxation is reported by
                      # check_placement.py rather than hidden.
                      # On the relaxed pass widen the limit in steps rather than
                      # dropping it entirely - "anywhere" was putting a gate resistor
                      # 26 mm from its FET, which is worse than useless.
                      lim = ADJ[ref][2] if ref in ADJ else None
                      if relaxed and lim is not None: lim *= relax_factor
                      pos = packers[zname].place_near(w, h, tgt[0]-X0, tgt[1]-Y0,
                                                      reject=rej, max_dist=lim)
                  if forced is None and pos is None and not (ref in ADJ and not relaxed):
                      pos = packers[zname].place(w, h, reject=rej)
                  if forced is None: rot = 0
                  # Connectors may turn 90 degrees to sit on a side edge - the top
                  # strip cannot hold two of them once a mounting hole pushes the
                  # first to centre. Everything else only rotates if it is small.
                  if forced is None and pos is None and abs(w - h) > 0.2 and (w*h < 30.0
                                                           or ref.startswith("J")):
                      pos = packers[zname].place(h, w, reject=rej)
                      rot = 90
                  if pos is None: continue
                  px, py = pos
                  fp.SetPosition(pcbnew.VECTOR2I(MM(X0 + px), MM(Y0 + py)))
                  # NOTE: Flip() segfaults on a footprint not yet owned by a board, so it must
                  # be added first. KiCad 9 also takes a FLIP_DIRECTION enum, not the historical
                  # bool - passing a bool segfaults too.
                  board.Add(fp)
                  if bk: fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
                  if rot: fp.SetOrientationDegrees(rot)   # was hardcoded 90
                  # SetPosition() sets the footprint ORIGIN, which is not the courtyard centre
                  # (on the microSD socket they differ by >1 mm). Measure the placed courtyard
                  # and shift so the courtyard lands where the packer reserved space. Done
                  # after rotate+flip so it self-corrects for any orientation.
                  for _fix in range(2):
                      poly = fp.GetCourtyard(pcbnew.B_CrtYd if bk else pcbnew.F_CrtYd)
                      if not poly.OutlineCount(): break
                      c = poly.BBox().GetCenter()
                      dx = MM(X0 + px) - c.x; dy = MM(Y0 + py) - c.y
                      if abs(dx) < 1000 and abs(dy) < 1000: break
                      fp.SetPosition(pcbnew.VECTOR2I(fp.GetPosition().x + dx,
                                                     fp.GetPosition().y + dy))
                  fp.SetReference(ref); fp.SetValue(val)
                  # Silkscreen policy for a dense board: designators only on parts a human
                  # needs to find by eye (ICs, connectors, crystals, buttons). Passives keep
                  # their reference on F.Fab for the assembly drawing, but off the silk -
                  # 0.8 mm is the minimum legible/allowed height and they simply do not fit.
                  fp.Value().SetVisible(False)
                  rt = fp.Reference()
                  rt.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
                  rt.SetTextThickness(MM(0.12))
                  passive = (ref[0] in "RCL" or ref.startswith("TP")
                             or (ref[0] == "P" and ref[1:].isdigit()))
                  if passive:
                      fab = board.GetLayerID("B.Fab" if bk else "F.Fab")
                      rt.SetLayer(fab)
                      # and their silk OUTLINES too - on an 85%-dense board these overlap
                      # everything. The fab layer still documents them for assembly.
                      for it in fp.GraphicalItems():
                          if it.GetLayerName() in ("F.SilkS", "B.SilkS"):
                              it.SetLayer(fab)
                  if lcsc:
                      fp.SetField("LCSC", lcsc)
                      # SetField creates a VISIBLE field - it rendered the LCSC code as
                      # giant silkscreen text across every part.
                      for fld in fp.GetFields():
                          if fld.GetName() == "LCSC": fld.SetVisible(False)
                  if dnp:  fp.SetDNP(True)
                  for pad in fp.Pads():
                      nn = pin_net.get(ref, {}).get(pad.GetPadName())
                      if nn is None:
                          nn = _by_name(syms, lib_id, pad.GetPadName(), pin_net.get(ref, {}))
                      if nn: pad.SetNet(netmap[nn])
                  # A through-hole feature occupies BOTH sides. Without this, bottom-side
                  # passives land inside the USB-C shell pins and the microSD NPTH posts.
                  # A through-hole feature occupies both sides - but only the TH PADS do,
                  # not the whole part. Carving the entire footprint bbox meant the microSD's
                  # two mounting posts blocked most of the opposite edge zone, leaving the GPS
                  # connector nowhere to go. Carve each TH pad's own area instead.
                  for pad in fp.Pads():
                      if pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH,
                                                    pcbnew.PAD_ATTRIB_NPTH):
                          continue
                      bb = pad.GetBoundingBox()
                      ax = pcbnew.ToMM(bb.GetLeft()) - X0 - 0.25
                      ay = pcbnew.ToMM(bb.GetTop()) - Y0 - 0.25
                      bx = pcbnew.ToMM(bb.GetRight()) - X0 + 0.25
                      by = pcbnew.ToMM(bb.GetBottom()) - Y0 + 0.25
                      for k2, z2 in ZONES.items():
                          if z2[4] != bk:
                              packers[k2].carve(ax, ay, bx, by)
                  if bk:
                      items = [fp.Reference(), fp.Value()] + list(fp.GraphicalItems())
                      if hasattr(fp, "GetFields"): items += list(fp.GetFields())
                      for it in items:
                          if hasattr(it, "SetMirrored"): it.SetMirrored(True)
                  # remember where this part's pads ended up, so parts with an adjacency
                  # rule pointing at it can aim for the right pin
                  for pad in fp.Pads():
                      pp = pad.GetPosition()
                      targets[(ref, pad.GetPadName())] = (pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y))
                  for r2, (t_ref, t_pad, _mx) in ADJ.items():
                      if t_ref == ref and (t_ref, t_pad) in targets:
                          targets[r2] = targets[(t_ref, t_pad)]
                  placed += 1; ok = True
                  break
              if not ok:
                  if ref in ADJ and not relaxed:
                      deferred.append(ref)          # retry without the distance limit
                  else:
                      overflow.append((ref, "no space"))


    def place_adjacency():
        nonlocal placed
        # ---- adjacency parts: spiral search around the pin each one serves -------
        boxes = list(side_boxes)   # everything placed so far, both faces
        for fp in board.GetFootprints():
            lay = pcbnew.B_CrtYd if fp.GetLayerName() == "B.Cu" else pcbnew.F_CrtYd
            poly = fp.GetCourtyard(lay)
            if not poly.OutlineCount(): continue
            bb = poly.BBox()
            boxes.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                          pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                          fp.GetLayerName()))

        # Through-hole pads pass through BOTH faces, so they block a spiral placement
        # on either side. Without this the USB-C shell pins landed on top of the ESD
        # diode and the buck inductor sitting underneath them.
        th_boxes = []
        for _fp in board.GetFootprints():
            for _pad in _fp.Pads():
                if _pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH,
                                               pcbnew.PAD_ATTRIB_NPTH):
                    continue
                _b = _pad.GetBoundingBox()
                th_boxes.append((pcbnew.ToMM(_b.GetLeft()) - 0.25,
                                 pcbnew.ToMM(_b.GetTop()) - 0.25,
                                 pcbnew.ToMM(_b.GetRight()) + 0.25,
                                 pcbnew.ToMM(_b.GetBottom()) + 0.25))

        def free_at(cx, cy, w, h, side):
            if not (X0+0.4 <= cx-w/2 and cx+w/2 <= X0+W-0.4
                    and Y0+0.4 <= cy-h/2 and cy+h/2 <= Y0+H-0.4): return False
            if hole_clash(cx, cy, w, h) or corner_clash(cx, cy, w, h): return False
            for (a, b, c, d) in th_boxes:          # blocks on both faces
                if not (cx+w/2 <= a or c <= cx-w/2
                        or cy+h/2 <= b or d <= cy-h/2): return False
            for (a, b, c, d, sd) in boxes:
                if sd != side: continue
                if not (cx+w/2+0.2 <= a or c+0.2 <= cx-w/2
                        or cy+h/2+0.2 <= b or d+0.2 <= cy-h/2): return False
            return True

        adj_placed = adj_far = 0
        for ref in sorted(adj_parts, key=lambda r: ADJ[r][2]):     # tightest limit first
            t_ref, t_pad, max_mm = ADJ[ref]
            tgt = targets.get((t_ref, t_pad))
            if tgt is None: overflow.append((ref, "no target")); continue
            lib_id, fpid, val, lcsc, dnp = design.COMPONENTS[ref]
            path = fplib.find(fpid)
            fp = pcbnew.FootprintLoad(os.path.dirname(path),
                                      os.path.basename(path)[:-len(".kicad_mod")])
            info = fplib.load(fpid)
            w = h = None
            for cl in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                poly = fp.GetCourtyard(cl)
                if poly.OutlineCount():
                    bb = poly.BBox()
                    w = pcbnew.ToMM(bb.GetWidth()); h = pcbnew.ToMM(bb.GetHeight()); break
            if not w: w, h = info['w'], info['h']
            w += 0.25; h += 0.25
            spot = None
            for rad in [0.0] + [0.2*k for k in range(1, 130)]:
                for ang in range(0, 360, 12):
                    cx = tgt[0] + rad*math.cos(math.radians(ang))
                    cy = tgt[1] + rad*math.sin(math.radians(ang))
                    for side in ("F.Cu", "B.Cu"):
                        if free_at(cx, cy, w, h, side):
                            spot = (cx, cy, side, rad); break
                    if spot: break
                if spot: break
            if spot is None: overflow.append((ref, "no space")); continue
            cx, cy, side, rad = spot
            fp.SetPosition(pcbnew.VECTOR2I(MM(cx), MM(cy)))
            board.Add(fp)
            if side == "B.Cu": fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            for _fix in range(2):
                poly = fp.GetCourtyard(pcbnew.B_CrtYd if side == "B.Cu" else pcbnew.F_CrtYd)
                if not poly.OutlineCount(): break
                c = poly.BBox().GetCenter()
                dx = MM(cx) - c.x; dy = MM(cy) - c.y
                if abs(dx) < 1000 and abs(dy) < 1000: break
                fp.SetPosition(pcbnew.VECTOR2I(fp.GetPosition().x + dx, fp.GetPosition().y + dy))
            fp.SetReference(ref); fp.SetValue(val)
            fp.Value().SetVisible(False)
            rt = fp.Reference(); rt.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
            rt.SetTextThickness(MM(0.12))
            rt.SetLayer(board.GetLayerID("B.Fab" if side == "B.Cu" else "F.Fab"))
            for it in fp.GraphicalItems():
                if it.GetLayerName() in ("F.SilkS", "B.SilkS"):
                    it.SetLayer(board.GetLayerID("B.Fab" if side == "B.Cu" else "F.Fab"))
            if side == "B.Cu":
                for it in [fp.Reference(), fp.Value()] + list(fp.GraphicalItems()):
                    if hasattr(it, "SetMirrored"): it.SetMirrored(True)
            if lcsc:
                fp.SetField("LCSC", lcsc)
                for fld in fp.GetFields():
                    if fld.GetName() == "LCSC": fld.SetVisible(False)
            if dnp: fp.SetDNP(True)
            for pad in fp.Pads():
                nn = pin_net.get(ref, {}).get(pad.GetPadName())
                if nn is None:
                    nn = _by_name(syms, lib_id, pad.GetPadName(), pin_net.get(ref, {}))
                if nn: pad.SetNet(netmap[nn])
            bb = fp.GetCourtyard(pcbnew.B_CrtYd if side == "B.Cu" else pcbnew.F_CrtYd).BBox()
            bx0, by0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
            bx1, by1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
            boxes.append((bx0, by0, bx1, by1, side))
            side_boxes.append((bx0, by0, bx1, by1, side))
            # Take this area out of the ZONE packers too. The passives placed after
            # the spiral run from those free-rect lists, and without this they land
            # straight on top of the decoupling.
            for k2, z2 in ZONES.items():
                if bool(z2[4]) == (side == "B.Cu"):
                    packers[k2].carve(bx0 - X0 - 0.2, by0 - Y0 - 0.2,
                                      bx1 - X0 + 0.2, by1 - Y0 + 0.2)
            placed += 1; adj_placed += 1
            if rad > max_mm: adj_far += 1
        print(f"adjacency parts: {adj_placed} placed, {adj_far} beyond their limit")


    # Order matters: the ICs land first, then the parts that must hug their pins get
    # a direct spiral search, and only then do the free-roaming passives fill in. Run
    # the other way round (as the first attempt did) and the passives take the space
    # the decoupling needed.
    place_by_zone([r for r in by_area if r in FIXED_REFS]
                  + [r for r in by_area if r in TARGETS])
    place_adjacency()
    place_by_zone([r for r in by_area if rest(r) and is_pad(r)]
                  + [r for r in by_area if rest(r) and not is_pad(r)])

    _outline(board)
    _zones(board, netmap)
    pcbnew.SaveBoard(OUT, board)

    for k in sorted(packers):
        fa = sum((c-a)*(d-b) for a,b,c,d in packers[k].free)
        za = (ZONES[k][2]-ZONES[k][0])*(ZONES[k][3]-ZONES[k][1])
        print("  zone %-7s %6.1f mm^2 free of %6.1f  (%3.0f%% used)  %d frags"
              % (k, fa, za, 100*(1-fa/za), len(packers[k].free)))
    unplaced = [r for r, _ in overflow]
    print(f"placed {placed} footprints, {len(design.NETS)} nets")
    if unplaced:
        print(f"UNPLACED ({len(unplaced)}): {' '.join(unplaced)}")

def _area(ref):
    fpid = design.COMPONENTS[ref][1]
    if not fpid: return 0
    try:
        d = fplib.load(fpid); return d['w'] * d['h']
    except Exception:
        return 0

def _by_name(syms, lib_id, padname, refnets):
    """Map a pad number back to a net when design.py used a pin NAME."""
    key = lib_id.split(":", 1)[1] if lib_id.startswith("jlc_parts:") else None
    pins = syms.get(key) if key else None
    if not pins: return None
    for p in pins:
        if p['num'] == padname:
            for cand in (p['name'], p['name'].split('-')[0]):
                if cand in refnets: return refnets[cand]
    return None

def _outline(board):
    lay = board.GetLayerID("Edge.Cuts")
    def seg(x1, y1, x2, y2):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT); s.SetLayer(lay)
        s.SetStart(pcbnew.VECTOR2I(MM(x1), MM(y1))); s.SetEnd(pcbnew.VECTOR2I(MM(x2), MM(y2)))
        s.SetWidth(MM(0.1)); board.Add(s)
    def arc(cx, cy, a0, a1):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC); s.SetLayer(lay)
        p = lambda a: pcbnew.VECTOR2I(MM(cx + R*math.cos(math.radians(a))),
                                      MM(cy + R*math.sin(math.radians(a))))
        s.SetStart(p(a0)); s.SetEnd(p(a1))
        mid = p((a0 + a1) / 2)
        s.SetArcGeometry(p(a0), mid, p(a1)); s.SetWidth(MM(0.1)); board.Add(s)
    def circ(cx, cy, d):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_CIRCLE); s.SetLayer(lay)
        s.SetStart(pcbnew.VECTOR2I(MM(cx), MM(cy)))
        s.SetEnd(pcbnew.VECTOR2I(MM(cx + d/2), MM(cy))); s.SetWidth(MM(0.1)); board.Add(s)
    X1, Y1 = X0 + W, Y0 + H
    seg(X0+R, Y0, X1-R, Y0); seg(X1, Y0+R, X1, Y1-R)
    seg(X1-R, Y1, X0+R, Y1); seg(X0, Y1-R, X0, Y0+R)
    arc(X0+R, Y0+R, 180, 270); arc(X1-R, Y0+R, 270, 360)
    arc(X1-R, Y1-R, 0, 90);    arc(X0+R, Y1-R, 90, 180)
    for hx, hy in HOLES: circ(hx, hy, HOLE_D)

def _zones(board, netmap):
    """L2 solid GND, L3 +3V3, plus GND pours on both outer layers."""
    for layer, net in (("In1.Cu", "GND"), ("In2.Cu", "+3V3"),
                       ("F.Cu", "GND"), ("B.Cu", "GND")):
        z = pcbnew.ZONE(board)
        z.SetLayer(board.GetLayerID(layer))
        z.SetNet(netmap[net])
        z.SetIsFilled(False)
        z.SetLocalClearance(MM(0.25))
        z.SetMinThickness(MM(0.2))
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.4))
        if layer in ("F.Cu", "B.Cu"):
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        else:
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        pts = pcbnew.wxPoint_Vector() if hasattr(pcbnew, "wxPoint_Vector") else None
        outline = z.Outline()
        outline.NewOutline()
        m = 0.3
        for x, y in ((X0+m, Y0+m), (X0+W-m, Y0+m), (X0+W-m, Y0+H-m), (X0+m, Y0+H-m)):
            outline.Append(MM(x), MM(y))
        board.Add(z)

if __name__ == "__main__":
    main()
