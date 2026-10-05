#!/usr/bin/env python3
"""Layout and fabrication checks on the routed board.

Usage:  python3 tools/check_board.py CHECK [options]

Checks:
  backside           Does anything with a pin through the board land under a part on the other side?
  connectors         Every connector's opening must face off the board, with room for the plug.
  floorplan          Every perimeter port sits on its edge, mates, and leaves room for its neighbours.
  placement          Gate 1: is the placement electrically correct, before any routing time is spent?
  power_cut          How much copper actually crosses between a rail's regulator and its loads.
  silk_owner         Does every label on the silkscreen read as its own part's, and can it be read at all?
  traces             Signal-integrity review of the routed copper: length, layer changes, and pair matching.
  model_alignment    Check that every component's 3D body sits on its own footprint and touches no other part's,
  cpl                Verify the pick-and-place rotations from board geometry, independently of what wrote
  footprints         Every footprint's pad count, against JLCPCB's own joint count for that part number.
  libraries          The vendored JLC library is present, complete, and identical to the board it rebuilds.
"""
import collections, csv, glob, gzip, heapq, json, math, os, re, struct, subprocess, sys, tempfile
import cables, design, fplib, jlcpaths, pcbnew, pcbutil, symlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOARD = (sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv
         else os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb"))

T = pcbnew.ToMM


#backside

"""Does anything with a pin through the board land under a part on the other side?

Usage: python3 tools/check_board.py backside [--board PATH]
"""

CLEAR = 0.20      #mm between a hole and an opposite-side body


def body_box(fp):
    """Plan-view box of the part itself: Fab outline, else silk outline."""
    back = fp.IsFlipped()
    fab = pcbnew.B_Fab if back else pcbnew.F_Fab
    silk = pcbnew.B_SilkS if back else pcbnew.F_SilkS
    box = None
    for layer in (fab, silk):
        for g in fp.GraphicalItems():
            if g.GetLayer() != layer or g.Type() in (pcbnew.PCB_TEXT_T, pcbnew.PCB_FIELD_T):
                continue
            bb = g.GetBoundingBox()
            if box is None:
                box = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
            else:
                box.Merge(bb)
        if box is not None:
            break
    for p in fp.Pads():
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            continue    #its own holes are not its body
        bb = p.GetBoundingBox()
        if box is None:
            box = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
        else:
            box.Merge(bb)
    return box


def run_backside():
    board = sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv else BOARD
    b = pcbnew.LoadBoard(board)
    fps = list(b.GetFootprints())
    bodies = {fp.GetReference(): body_box(fp) for fp in fps}
    fails, notes, n_holes = [], [], 0
    for fp in fps:
        for p in fp.Pads():
            if p.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            n_holes += 1
            pb = p.GetBoundingBox()          #the ring: for the courtyard note
            c, d = p.GetPosition(), p.GetDrillSize()
            if p.GetOrientationDegrees() % 180 != 0:
                d = pcbnew.VECTOR2I(d.y, d.x)
            hole = pcbnew.BOX2I(pcbnew.VECTOR2I(c.x - d.x // 2, c.y - d.y // 2), d)
            for o in fps:
                if o is fp or o.IsFlipped() == fp.IsFlipped():
                    continue
                where = f"{fp.GetReference()} pad {p.GetNumber() or '(hole)'} at " \
                        f"({T(p.GetPosition().x):.2f}, {T(p.GetPosition().y):.2f})"
                body = bodies[o.GetReference()]
                #a locating peg that ends inside the board
                sink = design.MODEL_EXPECTED_SINK.get(fp.GetReference())
                if (p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and sink is not None
                        and sink < design.BOARD_T - CLEAR):
                    for op in o.Pads():
                        g = op.GetBoundingBox()
                        g.Inflate(pcbnew.FromMM(CLEAR))
                        if g.Intersects(hole):
                            fails.append(f"{where} is under {o.GetReference()} pad "
                                         f"{op.GetNumber()} on the other side")
                            break
                    continue
                if body is not None:
                    g = pcbnew.BOX2I(body.GetOrigin(), body.GetSize())
                    g.Inflate(pcbnew.FromMM(CLEAR))
                    if g.Intersects(hole):
                        fails.append(f"{where} is under {o.GetReference()} ({o.GetValue()}) "
                                     f"on the other side")
                        continue
                    if g.Intersects(pb):
                        notes.append(f"{where}: its ring is within {CLEAR} mm of "
                                     f"{o.GetReference()}'s pads (the hole itself is clear)")
                        continue
                crt = o.GetCourtyard(pcbnew.B_CrtYd if o.IsFlipped() else pcbnew.F_CrtYd)
                if crt.OutlineCount() and crt.Collide(pcbnew.SHAPE_RECT(pb)):
                    notes.append(f"{where} is inside {o.GetReference()}'s courtyard margin "
                                 f"(body clear by >= {CLEAR} mm)")
    print(f"{n_holes} through-holes checked against every part on the other side")
    for n in notes:
        print(f"  note {n}")
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} pin(s)/hole(s) land under a part on the other side")
        return 1
    print("no pin or hole lands under a part on the other side")
    return 0


#connectors

"""Every connector's opening must face off the board, with room for the plug.

Usage: python3 tools/check_board.py connectors [board.kicad_pcb]
"""

STEP  = 0.10          #mm, ray march
CORRIDOR_MARGIN = 0.5 #mm of slack each side of the connector body
CRITICAL_FRACTION = 0.5


def local_to_board(fp, lx, ly):
    """Footprint-local mm -> board mm, honouring rotation and side."""
    p = fp.GetPosition()
    px, py = p.x/1e6, p.y/1e6
    #a flipped footprint mirrors in local Y under this convention, not X
    if fp.IsFlipped(): ly = -ly
    a = math.radians(-fp.GetOrientationDegrees())
    return (px + lx*math.cos(a) - ly*math.sin(a),
            py + lx*math.sin(a) + ly*math.cos(a))


def derive_face(fp):
    """Mating face from the footprint itself: opposite the largest pad row."""
    if "PinHeader" in fp.GetFPIDAsString() and "Horizontal" in fp.GetFPIDAsString():
        return (1.0, 0.0), "horizontal pin header contacts step in X, pins in +X"
    rows = {}
    for pad in fp.Pads():
        p = pad.GetPosition()
        #back out to local coordinates
        a = math.radians(fp.GetOrientationDegrees())
        dx, dy = p.x/1e6 - fp.GetPosition().x/1e6, p.y/1e6 - fp.GetPosition().y/1e6
        ly = dx*math.sin(a) + dy*math.cos(a)
        if fp.IsFlipped(): ly = -ly
        rows.setdefault(round(ly, 2), 0)
        rows[round(ly, 2)] += 1
    if not rows: return None, "no pads"
    back = max(rows, key=lambda k: (rows[k], -abs(k)))
    if abs(back) < 0.01:
        #a single row on the origin (a right-angle pin header)
        bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
        a = math.radians(fp.GetOrientationDegrees())
        far = []
        for X in (bb.GetLeft(), bb.GetRight()):
            for Y in (bb.GetTop(), bb.GetBottom()):
                dx, dy = X/1e6 - fp.GetPosition().x/1e6, Y/1e6 - fp.GetPosition().y/1e6
                ly = dx*math.sin(a) + dy*math.cos(a)
                far.append(-ly if fp.IsFlipped() else ly)
        face = (0.0, 1.0) if max(far) > -min(far) else (0.0, -1.0)
        return face, f"{rows[back]} contacts on the origin, courtyard to {max(far):+.2f}/{min(far):+.2f}"
    face = (0.0, 1.0) if back < 0 else (0.0, -1.0)
    return face, f"{rows[back]} contacts at local y {back:+.2f}"


def board_outline(board):
    xs, ys = [], []
    for d in board.GetDrawings():
        if d.GetLayerName() == 'Edge.Cuts':
            bb = d.GetBoundingBox()
            xs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
            ys += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
    return min(xs), max(xs), min(ys), max(ys)


def run_connectors():
    board = pcbnew.LoadBoard(BOARD)
    X0, X1, Y0, Y1 = board_outline(board)
    inside = lambda x, y: X0 <= x <= X1 and Y0 <= y <= Y1

    fails, warns = [], []
    print(f"connector orientation - {os.path.basename(BOARD)}")
    print(f"  board {X0:.2f}..{X1:.2f} x {Y0:.2f}..{Y1:.2f} mm\n")

    for ref, declared in sorted(design.MATING_FACE.items()):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            fails.append(f"{ref}: not on the board"); continue
        need = design.MATING_CLEARANCE.get(ref, 6.0)

        #1 - declared vs derived
        derived, why = derive_face(fp)
        if derived and tuple(derived) != tuple(declared):
            fails.append(f"{ref}: design.MATING_FACE says {declared} but the footprint "
                         f"says {derived} ({why}) - footprint changed?")

        #mouth = the courtyard face furthest along the mating direction
        poly = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        if not poly.OutlineCount():
            warns.append(f"{ref}: no courtyard, cannot measure"); continue
        bb = poly.BBox()
        cl, cr = bb.GetLeft()/1e6, bb.GetRight()/1e6
        ct, cb = bb.GetTop()/1e6,  bb.GetBottom()/1e6
        cx, cy = (cl+cr)/2, (ct+cb)/2

        ox, oy = local_to_board(fp, *declared)
        px, py = fp.GetPosition().x/1e6, fp.GetPosition().y/1e6
        vx, vy = ox-px, oy-py
        n = math.hypot(vx, vy) or 1.0
        vx, vy = vx/n, vy/n
        #walk from the courtyard centre to its face along the mating direction
        half = (abs(vx)*(cr-cl) + abs(vy)*(cb-ct)) / 2
        mx, my = cx + vx*half, cy + vy*half
        #the plug travels the corridor, so its width sets it
        plug_w = design.MATING_PLUG.get(ref, (None,))[0]
        width = (plug_w / 2 if plug_w else (abs(vy)*(cr-cl) + abs(vx)*(cb-ct)) / 2) \
            + CORRIDOR_MARGIN

        #2 - does the mouth point off the board?
        exit_d = None
        d = 0.0
        while d <= 80.0:
            if not inside(mx+vx*d, my+vy*d): exit_d = d; break
            d += STEP
        if exit_d is None:
            fails.append(f"{ref}: mouth at ({mx:.2f},{my:.2f}) points INTO the board - "
                         f"no cable can be plugged in")
            continue

        #3 - is the plug corridor clear, out to whichever comes first
        reach = min(need, exit_d)
        blockers = {}
        for other in board.GetFootprints():
            if other.GetReference() == ref: continue
            if other.IsFlipped() != fp.IsFlipped(): continue      #other side, irrelevant
            #test pads and fiducials are bare copper with no body
            fpid = other.GetFPIDAsString()
            if 'TestPoint' in fpid or 'Fiducial' in fpid: continue
            if other.GetReference().startswith(('TP', 'FID')): continue
            op = other.GetCourtyard(pcbnew.B_CrtYd if other.IsFlipped() else pcbnew.F_CrtYd)
            if not op.OutlineCount(): continue
            ob = op.BBox()
            ol, orr = ob.GetLeft()/1e6, ob.GetRight()/1e6
            ot, obm = ob.GetTop()/1e6,  ob.GetBottom()/1e6
            #start just in front of the mouth, not at it
            d = 0.3
            while d <= reach:
                #sample across the corridor width
                for w in (-width, -width/2, 0.0, width/2, width):
                    sx = mx + vx*d - vy*w
                    sy = my + vy*d + vx*w
                    if ol <= sx <= orr and ot <= sy <= obm:
                        blockers[other.GetReference()] = min(blockers.get(other.GetReference(), 99), d)
                        break
                d += STEP
        edge = {'left':'left','right':'right','top':'top','bottom':'bottom'}[
            'left' if vx < -0.7 else 'right' if vx > 0.7 else 'top' if vy < 0 else 'bottom']
        side = 'bottom' if fp.IsFlipped() else 'top'
        line = (f"  {ref:4s} {side:6s} rot {fp.GetOrientationDegrees():>4.0f}  mouth "
                f"({mx:6.2f},{my:6.2f}) -> {edge:6s} edge, {exit_d:5.2f} mm to clear the board")
        if blockers:
            nearest = min(blockers.items(), key=lambda k: k[1])
            if nearest[1] < need * CRITICAL_FRACTION:
                fails.append(f"{ref}: only {nearest[1]:.2f} mm of clear space in front of "
                             f"the mouth ({nearest[0]} is in the way) - no plug can mate "
                             f"(needs {need:.1f} mm, hard limit {need*CRITICAL_FRACTION:.1f})")
                print(line + f"   BLOCKED by {nearest[0]} at {nearest[1]:.2f} mm")
                continue
            if nearest[1] < need:
                warns.append(f"{ref}: {nearest[1]:.2f} mm clear in front of the mouth "
                             f"({nearest[0]} is nearest); {need:.1f} mm is the nominal "
                             f"plug+bend allowance - measure the real plug before assembly")
                print(line + f"   {nearest[1]:.2f} mm to {nearest[0]} (nominal {need:.1f})")
                continue
        if exit_d < need and not blockers:
            print(line + f"   ok (clears the board in {exit_d:.2f} mm, plug needs {need:.1f})")
        else:
            print(line + f"   ok ({need:.1f} mm clear for the plug)")

    for ref, spec in sorted(getattr(design, "VERTICAL_MATING", {}).items()):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            fails.append(f"{ref}: not on the board"); continue
        if fp.IsFlipped():
            fails.append(f"{ref}: vertical connector on the BOTTOM face - the plug "
                         f"points down into the ESC")
            continue
        #horizontal sweep
        sweep_fail = sweep_warn = []
        for other in board.GetFootprints():
            if other.GetReference() == ref or other.IsFlipped(): continue
            dx = other.GetPosition().x/1e6 - fp.GetPosition().x/1e6
            dy = other.GetPosition().y/1e6 - fp.GetPosition().y/1e6
            if math.hypot(dx, dy) > spec["radius"]: continue
            h = design.part_height(other.GetFPIDAsString())
            if h is None:
                sweep_warn.append(other.GetReference())
            elif h > spec["plug"] - 0.5:
                sweep_fail.append(f"{other.GetReference()} ({h:.1f} mm tall)")
        if sweep_fail:
            fails.append(f"{ref}: {', '.join(sweep_fail)} sit inside the {spec['radius']:.0f} mm "
                         f"bend sweep and are tall enough to hit the coax")
        elif sweep_warn:
            warns.append(f"{ref}: {', '.join(sweep_warn)} sit inside the bend sweep with "
                         f"unknown height - check against the part that arrives")
        #vertical room: standoff - everything below the board top face
        try:
            s = design.required_standoff(board)
            below_board = (design.ESC["pcb"] + design.ESC["parts"] +
                           design.MOUNTING["gap"] +
                           s["bot"] + design.BOARD_T)
            #the top plate sits at the kit's height (design.TOP_PLATE_MOUNT)
            room = s["top_plate_z"] - s["below"] - below_board
            need = spec["plug"] + spec["bend"]
            if room < need:
                fails.append(f"{ref}: plug+bend need {need:.1f} mm but the top plate is "
                             f"only {room:.1f} mm above the board ({spec['src']})")
            else:
                print(f"  {ref:4s} vertical  +z plug {spec['plug']:.1f} + bend "
                      f"{spec['bend']:.1f} = {need:.1f} mm against {room:.1f} mm to the "
                      f"top plate   ok")
        except Exception as e:
            warns.append(f"{ref}: vertical room could not be computed ({e})")

    #how each plug stays in (design.CONNECTOR_RETENTION)
    print("\nretention")
    ret = design.CONNECTOR_RETENTION
    runbook = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "docs", "navcore-runbook.tex")).read()
    m = re.search(r"\\subsection\{Staking the plugs\}(.*?)\\(sub)?section", runbook, re.S)
    staking = m.group(1) if m else ""
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if not re.fullmatch(r"J\d+", ref):
            continue
        how, why = ret.get(ref, (None, None))
        gh = "GH" in fp.GetFPIDAsString().upper()
        if how is None:
            fails.append(f"{ref}: no retention declared (design.CONNECTOR_RETENTION)")
        elif gh and how != "latch":
            fails.append(f"{ref}: a latching JST-GH declared '{how}'")
        elif how == "latch" and "SH" in fp.GetFPIDAsString().upper() and not gh:
            fails.append(f"{ref}: declared a latch, but its footprint is a friction JST-SH")
        elif how == "stake" and f"\\file{{{ref}}}" not in staking:
            fails.append(f"{ref}: staked, but the runbook's 'Staking the plugs' step does not name it")
        else:
            print(f"  {ref:4s} {how:6s} {why}")
    print()
    for w in warns: print(f"  warn  {w}")
    for f in fails: print(f"  FAIL  {f}")
    print(f"\n{len(fails)} failure(s), {len(warns)} warning(s)")
    sys.stdout.flush()
    os._exit(1 if fails else 0)


#floorplan

"""Every perimeter port sits on its edge, mates, and leaves room for its neighbours.

Usage: python3 tools/check_board.py floorplan [board.kicad_pcb]

Measured on the board, per port in design.FLOORPLAN_REV_D:
  1. side and direction: the mouth (footprint local +y) points out of its edge;
  2. seating: the body's front face is where the floorplan put it, and every pad keeps the
     project's copper-to-edge clearance;
  3. neighbours: bodies on the same edge and side are >= 2.0 mm apart where either latches
     (room for a thumb on the latch), and no two courtyards on a side overlap;
  4. stack hardware: no pad or body under the bolt's washer (top) or the hex spacer
     (bottom) - design.FC_HOLE_HARDWARE;
  5. plugs: each mated plug body (design.MATING_PLUG width x MATING_PLUG_BODY) clears the
     top-plate posts beside the fore and aft edges and every other plug on its side;
  6. holes: no port's through-hole leg or locating hole comes within the hole clearance of
     a pad on the other side.
"""

MM = 1e6
LATCH_GAP = 2.0       #mm between latching housings
PLUG_GAP = 0.8        #mm between two friction plugs side by side
POST_GAP = 0.5        #mm from a plug body to a top-plate post
floorplan_TOL = 0.05            #mm on the front-face position
OUTWARD = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}


def to_board(fp, lx, ly):
    """Library-local mm -> board mm (mirrored in y on the bottom side)."""
    p = fp.GetPosition()
    a = math.radians(fp.GetOrientationDegrees())
    if fp.IsFlipped():
        ly = -ly
    return (p.x / MM + lx * math.cos(a) + ly * math.sin(a),
            p.y / MM - lx * math.sin(a) + ly * math.cos(a))


def edge_clearance():
    pro = os.path.splitext(BOARD)[0] + ".kicad_pro"
    rules = json.load(open(pro))["board"]["design_settings"]["rules"]
    return rules["min_copper_edge_clearance"]


def seg_rect_dist(cx, cy, r):
    """Distance from point (cx, cy) to axis-aligned rect r = (x0, y0, x1, y1)."""
    dx = max(r[0] - cx, 0, cx - r[2])
    dy = max(r[1] - cy, 0, cy - r[3])
    return math.hypot(dx, dy)


def rect_gap(a, b):
    """Separation of two axis-aligned rects, 0 if they touch or overlap (then < 0 by depth)."""
    gx = max(b[0] - a[2], a[0] - b[2])
    gy = max(b[1] - a[3], a[1] - b[3])
    if gx < 0 and gy < 0:
        return max(gx, gy)
    return math.hypot(max(gx, 0), max(gy, 0))


def courtyard(fp):
    bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
    return (bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)


def pad_rect(pad):
    bb = pad.GetBoundingBox()
    return (bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)


def run_floorplan():
    board = pcbnew.LoadBoard(BOARD)
    B = design.BOARD
    X0, Y0, X1, Y1 = B["X0"], B["Y0"], B["X0"] + B["W"], B["Y0"] + B["H"]
    clear = edge_clearance()
    fails = []

    holes = []
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_CIRCLE:
            holes.append((d.GetCenter().x / MM, d.GetCenter().y / MM))
    bb = board.GetBoardEdgesBoundingBox()
    got = (bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)
    #the Edge.Cuts line width straddles the outline
    if any(abs(g - w) > 0.06 for g, w in zip(got, (X0, Y0, X1, Y1))):
        fails.append(f"outline {got} is not design.BOARD {(X0, Y0, X1, Y1)}")
    if len(holes) != 4:
        fails.append(f"{len(holes)} mounting holes, not 4")
    sx = sum(h[0] for h in holes) / max(len(holes), 1)
    sy = sum(h[1] for h in holes) / max(len(holes), 1)
    hw = design.FC_HOLE_HARDWARE
    reach = {"F": max(h["reach_d"] for h in hw["top"]) / 2,
             "B": max(h["reach_d"] for h in hw["bottom"]) / 2}
    tpm = design.TOP_PLATE_MOUNT
    #frame +y is aft, board -y is aft
    posts = [(sx + px, sy - py) for px, py in tpm["front_posts"][:2] + tpm["rear_posts"][:2]]
    post_r = tpm["post_od"] / 2

    print(f"floorplan - {os.path.basename(BOARD)}: {X1 - X0:.2f} x {Y1 - Y0:.2f} mm, "
          f"copper-to-edge {clear} mm, posts at "
          + ", ".join(f"({x:.1f},{y:.1f})" for x, y in posts) + "\n")
    print(f"{'ref':4} {'edge':4} {'face':>6} {'want':>6} {'pad in':>7} {'hardware':>9}  port")

    ports = {}
    for ref, spec in design.FLOORPLAN_REV_D.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            fails.append(f"{ref}: not on the board")
            continue
        name = str(fp.GetFPID().GetLibItemName())
        if name not in design.CONN_BODY:
            fails.append(f"{ref}: {name} has no design.CONN_BODY entry")
            continue
        half, front_ly, _src = design.CONN_BODY[name]
        side = "B" if fp.IsFlipped() else "F"
        if side != spec["side"]:
            fails.append(f"{ref}: on side {side}, floorplan says {spec['side']}")
        nx, ny = OUTWARD[spec["edge"]]
        ax, ay = to_board(fp, 0, 0)
        bx, by = to_board(fp, 0, 1)
        if abs(bx - ax - nx) > 1e-3 or abs(by - ay - ny) > 1e-3:
            fails.append(f"{ref}: mouth points ({bx - ax:+.0f},{by - ay:+.0f}), "
                         f"not out of the {spec['edge']} edge")
            continue
        fx, fy = to_board(fp, 0, front_ly)
        edge = {"N": Y0, "S": Y1, "E": X1, "W": X0}[spec["edge"]]
        face = (fx - edge) * nx if nx else (fy - edge) * ny        #+ is proud
        at = fx if nx == 0 else fy
        if abs(face - spec["front"]) > floorplan_TOL or abs(at - spec["at"]) > floorplan_TOL:
            fails.append(f"{ref}: face {face:+.2f} at {at:.2f}, floorplan says "
                         f"{spec['front']:+.2f} at {spec['at']:.2f} - run apply_floorplan.py")
        #body rectangle on the board: across the mouth +-half
        cy = courtyard(fp)
        if nx == 0:
            body = (fx - half, min(cy[1], fy), fx + half, max(cy[3], fy))
        else:
            body = (min(cy[0], fx), fy - half, max(cy[2], fx), fy + half)
        pad_in = min(min(r[0] - X0, r[1] - Y0, X1 - r[2], Y1 - r[3])
                     for r in map(pad_rect, fp.Pads()))
        if pad_in < clear - 1e-3:
            fails.append(f"{ref}: a pad is {pad_in:.2f} mm from the edge (rule {clear})")
        hard = min(min([seg_rect_dist(hx, hy, pad_rect(p)) for p in fp.Pads()] +
                       [seg_rect_dist(hx, hy, body)]) for hx, hy in holes)
        if hard < reach[side]:
            fails.append(f"{ref}: {hard:.2f} mm from a mounting hole; the "
                         f"{'washer' if side == 'F' else 'spacer'} reaches {reach[side]:.2f}")
        ports[ref] = dict(fp=fp, spec=spec, side=side, body=body, crt=cy, n=(nx, ny),
                          face=(fx, fy), edge=edge)
        print(f"{ref:4} {spec['edge']}/{side} {face:+6.2f} {spec['front']:+6.2f} "
              f"{pad_in:7.2f} {hard:9.2f}  {spec['desc']}")

    #3. neighbours
    print("\nneighbours along each edge (body gap; latching needs "
          f">= {LATCH_GAP} mm, plugs >= {PLUG_GAP} mm)")
    latching = {r for r, (how, _w) in design.CONNECTOR_RETENTION.items()
                if how in ("latch", "snap")}
    groups = {}
    for ref, p in ports.items():
        groups.setdefault((p["spec"]["edge"], p["side"]), []).append(ref)
    for (edge, side), refs in sorted(groups.items()):
        refs.sort(key=lambda r: ports[r]["spec"]["at"])
        for a, b in zip(refs, refs[1:]):
            g = rect_gap(ports[a]["body"], ports[b]["body"])
            need = LATCH_GAP if (a in latching or b in latching) else PLUG_GAP
            if need == PLUG_GAP:                  #friction plugs: the plugs, not the bodies
                wa, wb = design.MATING_PLUG[a][0], design.MATING_PLUG[b][0]
                g = abs(ports[b]["spec"]["at"] - ports[a]["spec"]["at"]) - (wa + wb) / 2
            ok = g >= need
            print(f"  {edge}/{side} {a:4} <-> {b:4} {g:5.2f} mm  {'ok' if ok else 'FAIL'}")
            if not ok:
                fails.append(f"{a}/{b}: {g:.2f} mm apart on the {edge} edge, need {need}")
    every = {r: (courtyard(f), "B" if f.IsFlipped() else "F") for r, f in
             ((f.GetReference(), f) for f in board.GetFootprints())}
    for ref, p in ports.items():
        for other, (crt, side) in every.items():
            if other == ref or side != p["side"]:
                continue
            if rect_gap(p["crt"], crt) < 0:
                fails.append(f"{ref}: courtyard overlaps {other}'s")

    #5. plugs
    print(f"\nplugs (width x body length beyond the edge; posts need >= {POST_GAP} mm)")
    plugs = {}
    for ref, p in ports.items():
        w = design.MATING_PLUG[ref][0]
        L = design.MATING_PLUG_BODY[ref]
        nx, ny = p["n"]
        fx, fy = p["face"]
        if nx == 0:
            e = p["edge"]
            rect = (fx - w / 2, min(e, e + ny * L), fx + w / 2, max(e, e + ny * L))
        else:
            e = p["edge"]
            rect = (min(e, e + nx * L), fy - w / 2, max(e, e + nx * L), fy + w / 2)
        plugs[ref] = (rect, p["side"])
        post = min(seg_rect_dist(px, py, rect) - post_r for px, py in posts)
        ok = post >= POST_GAP
        print(f"  {ref:4} {w:5.2f} x {L:4.1f}  {post:5.2f} mm to the nearest post"
              f"  {'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{ref}: its plug comes {post:.2f} mm from a top-plate post")
    refs = sorted(plugs)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            if plugs[a][1] == plugs[b][1] and rect_gap(plugs[a][0], plugs[b][0]) < 0:
                fails.append(f"{a}/{b}: their plugs overlap")

    #6. through-hole legs and locating holes
    hole_clear = json.load(open(os.path.splitext(BOARD)[0] + ".kicad_pro"))[
        "board"]["design_settings"]["rules"]["min_hole_clearance"]
    for ref, p in ports.items():
        for pad in p["fp"].Pads():
            if pad.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            q = pad.GetPosition()
            r = max(pad.GetDrillSize().x, pad.GetDrillSize().y) / MM / 2
            for other in board.GetFootprints():
                if other.IsFlipped() == p["fp"].IsFlipped() or other.GetReference() == ref:
                    continue
                for op in other.Pads():
                    if op.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                        continue
                    d = seg_rect_dist(q.x / MM, q.y / MM, pad_rect(op)) - r
                    if d < hole_clear:
                        fails.append(f"{ref} hole {pad.GetNumber() or '(locating)'} is "
                                     f"{d:.2f} mm from {other.GetReference()} pad "
                                     f"{op.GetNumber()} on the other side")

    print()
    for f in fails:
        print(f"  FAIL  {f}")
    print(f"{len(fails)} failure(s), {len(ports)} ports")
    sys.stdout.flush()
    os._exit(1 if fails else 0)


#placement

"""Gate 1: is the placement electrically correct, before any routing time is spent?"""

placement_TOMM = pcbnew.ToMM


def run_placement():
    b = pcbnew.LoadBoard(BOARD)
    #a pad number can name several pads
    pads, fps = {}, {}
    for fp in b.GetFootprints():
        fps[fp.GetReference()] = fp
        for pad in fp.Pads():
            pads.setdefault((fp.GetReference(), pad.GetPadName()), []).append(
                (placement_TOMM(pad.GetPosition().x), placement_TOMM(pad.GetPosition().y)))

    #adjacency rules
    fails, worst = [], []
    for ref, (t_ref, t_pad, max_mm) in design.ADJACENCY.items():
        if ref not in fps or (t_ref, t_pad) not in pads: continue
        best = min((math.hypot(px - tx, py - ty)
                    for tx, ty in pads[(t_ref, t_pad)]
                    for (r, _p), pts in pads.items() if r == ref for px, py in pts), default=None)
        if best is None: continue
        worst.append((best, ref, t_ref, t_pad, max_mm))
        if best > max_mm: fails.append((best, ref, t_ref, t_pad, max_mm))

    #net spans
    bynet = {}
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNet()
            #power rails are inherently long - +5V feeds connectors on every edge
            nm = n.GetNetname() if n else ""
            if nm and nm not in ("GND", "+3V3", "+3V3A", "+5V", "+9V",
                                 "VBAT", "VBUS", "VDDA", "VCC_RF"):
                p = pad.GetPosition()
                bynet.setdefault(n.GetNetname(), []).append((placement_TOMM(p.x), placement_TOMM(p.y)))
    spans = []
    for nn, ps in bynet.items():
        if len(ps) < 2: continue
        spans.append((max(math.hypot(a[0]-c[0], a[1]-c[1]) for a in ps for c in ps), nn))
    mean = sum(s for s, _ in spans) / len(spans)
    diag = math.hypot(design.BOARD["W"], design.BOARD["H"])
    frac = mean / diag

    print("=== Gate 1: placement ===\n")
    print(f"{'metric':<42} {'value':>10} {'target':>10}  ")
    print("-" * 68)
    print(f"{'adjacency rules checked':<42} {len(worst):>10} {'':>10}")
    print(f"{'  violations':<42} {len(fails):>10} {'0':>10}  {'PASS' if not fails else 'FAIL'}")
    #an MCU-to-edge-pad net cannot be short
    print(f"{'mean signal span, rails excluded (mm)':<42} {mean:>10.1f} {'':>10}")
    print(f"{'  as a fraction of the diagonal':<42} {frac:>10.2f} {'<0.30':>10}  "
          f"{'PASS' if frac < 0.30 else 'FAIL'}")
    for s, nn in sorted(spans, reverse=True)[:5]:
        print(f"{'    longest: ' + nn:<42} {s:>10.1f}")
    if fails:
        print(f"\nadjacency violations ({len(fails)}):")
        for d, ref, tr, tp, mx in sorted(fails, reverse=True):
            print(f"   {ref:<5} -> {tr}.{tp:<5} {d:6.2f} mm  (max {mx})")
    else:
        print("\nworst adjacency distances (all within limit):")
        for d, ref, tr, tp, mx in sorted(worst, reverse=True)[:6]:
            print(f"   {ref:<5} -> {tr}.{tp:<5} {d:6.2f} mm  (max {mx})")
    mount = check_mounting(b)
    return 1 if (fails or mount or frac >= 0.30) else 0


#the stack screws land on the board, not just through it
HARDWARE = [("M3 cap head, 5.5 mm OD", 2.75, True),      #true = hard failure
            ("silicone grommet flange, 6 mm OD", 3.00, False),
            ("M3 washer, 7 mm OD", 3.50, False)]


def check_mounting(board):
    import math, pcbnew
    holes = [(d.GetCenter().x / 1e6, d.GetCenter().y / 1e6) for d in board.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts and d.ShowShape() == "Circle"]
    if not holes:
        print("\nno mounting holes found on Edge.Cuts"); return 0
    near = []
    for f in board.GetFootprints():
        best = 1e9
        for pad in f.Pads():
            bb = pad.GetBoundingBox()
            x0, y0, x1, y1 = [v / 1e6 for v in (bb.GetLeft(), bb.GetTop(),
                                                bb.GetRight(), bb.GetBottom())]
            for hx, hy in holes:
                best = min(best, math.hypot(max(x0 - hx, 0, hx - x1),
                                            max(y0 - hy, 0, hy - y1)))
        if best < 1e9:
            near.append((best, f.GetReference()))
    near.sort()
    bad = 0
    print(f"\nmounting hardware clearance ({len(holes)} holes):")
    for label, r, hard in HARDWARE:
        hits = [(d, ref) for d, ref in near if d < r]
        if hits and hard:
            bad += len(hits)
            print(f"   FAIL {label}: pad copper within {r} mm -> "
                  + ", ".join(f"{ref} ({d:.2f})" for d, ref in hits))
        elif hits:
            print(f"   note {label}: {len(hits)} parts within {r} mm "
                  f"(closest {hits[0][1]} at {hits[0][0]:.2f}) - do not fit washers")
        else:
            print(f"   ok   {label}: nothing within {r} mm")
    return bad


#power_cut

"""How much copper actually crosses between a rail's regulator and its loads.

Usage:  python3 tools/check_board.py power_cut [-v]
"""

power_cut_TOMM  = pcbutil.TOMM
INNER = {"In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu"}


def ipc_width(width_mm, internal, dT=10.0):
    k = 0.024 if internal else 0.048
    return k * (dT ** 0.44) * (((width_mm / 0.0254) * 1.37) ** 0.725)


def seg_crosses(a, c, axis, v):
    """Does segment a-c cross the line axis=v? Returns the crossing or None."""
    i = 0 if axis == "x" else 1
    if (a[i] - v) * (c[i] - v) > 0:
        return None
    if abs(c[i] - a[i]) < 1e-12:
        return None
    return True


def poly_span(pts, axis, v):
    """Total length of the polygon's intersection with the line axis=v."""
    i = 0 if axis == "x" else 1
    j = 1 - i
    xs = []
    n = len(pts)
    for k in range(n):
        a, c = pts[k], pts[(k+1) % n]
        if (a[i] - v) * (c[i] - v) > 0 or abs(c[i] - a[i]) < 1e-12:
            continue
        t = (v - a[i]) / (c[i] - a[i])
        xs.append(a[j] + t * (c[j] - a[j]))
    xs.sort()
    return sum(xs[k+1] - xs[k] for k in range(0, len(xs) - 1, 2))


def _split_at_junctions(b, code, segs):
    """Each track as the sub-segments between the points."""
    vias = [v for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T and v.GetNetCode() == code]
    pads = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetCode() == code]

    def key(o, end):
        p = (power_cut_TOMM(o.GetStart().x), power_cut_TOMM(o.GetStart().y)) if end == 0 else \
            (power_cut_TOMM(o.GetEnd().x), power_cut_TOMM(o.GetEnd().y))
        return p

    out = []
    for t in segs:
        lay = t.GetLayer()
        a = (power_cut_TOMM(t.GetStart().x), power_cut_TOMM(t.GetStart().y))
        c = (power_cut_TOMM(t.GetEnd().x), power_cut_TOMM(t.GetEnd().y))
        dx, dy = c[0] - a[0], c[1] - a[1]
        L2 = dx * dx + dy * dy
        ts = {0.0, 1.0}

        def add(pt):
            if L2 == 0:
                return
            u = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2
            if 0 < u < 1 and math.hypot(a[0] + u * dx - pt[0], a[1] + u * dy - pt[1]) < 0.02:
                ts.add(u)
        for o in segs:
            if o is t or o.GetLayer() != lay:
                continue
            add(key(o, 0)); add(key(o, 1))
        for v in vias:
            if v.IsOnLayer(lay):
                add((power_cut_TOMM(v.GetPosition().x), power_cut_TOMM(v.GetPosition().y)))
        for p in pads:
            if not p.IsOnLayer(lay):
                continue
            pp = p.GetPosition()
            if math.hypot(power_cut_TOMM(pp.x) - (a[0] + dx / 2), power_cut_TOMM(pp.y) - (a[1] + dy / 2)) \
                    < max(0.5, math.hypot(dx, dy)):
                add((power_cut_TOMM(pp.x), power_cut_TOMM(pp.y)))
        ss = sorted(ts)
        for i in range(len(ss) - 1):
            u0, u1 = ss[i], ss[i + 1]
            out.append((lay, (a[0] + u0 * dx, a[1] + u0 * dy),
                        (a[0] + u1 * dx, a[1] + u1 * dy), power_cut_TOMM(t.GetWidth())))
    return out


def drop_dead_ends(b, code, segs):
    """Copper that leads nowhere carries no current."""
    vias = [v for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T and v.GetNetCode() == code]
    pads = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetCode() == code]
    zones = [z for z in b.Zones() if z.GetNetCode() == code]
    pieces = _split_at_junctions(b, code, segs)

    def anchored(t, pt, live):
        lay = t[0]
        if any(v.IsOnLayer(lay) and math.dist(pt, (power_cut_TOMM(v.GetPosition().x), power_cut_TOMM(v.GetPosition().y)))
               <= power_cut_TOMM(v.GetWidth(lay)) / 2 for v in vias):
            return True
        vp = pcbnew.VECTOR2I(pcbnew.FromMM(pt[0]), pcbnew.FromMM(pt[1]))
        if any(p.IsOnLayer(lay) and p.HitTest(vp) for p in pads):
            return True
        if any(z.IsOnLayer(lay) and z.HitTestFilledArea(lay, vp) for z in zones):
            return True
        return any(o is not t and o[0] == lay and point_on(pt, o[1], o[2]) for o in live)

    live = list(pieces)
    while True:
        dead = [t for t in live
                if not (anchored(t, t[1], live) and anchored(t, t[2], live))]
        if not dead:
            return live
        live = [t for t in live if t not in dead]


def point_on(pt, a, c, tol=1e-6):
    """Is pt on the closed segment a-c?"""
    dx, dy = c[0] - a[0], c[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(pt[0] - a[0], pt[1] - a[1]) <= tol
    u = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2
    if u < -tol or u > 1 + tol:
        return False
    return math.hypot(a[0] + u * dx - pt[0], a[1] + u * dy - pt[1]) <= tol


def run_power_cut():
    verbose = "-v" in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    pcbutil.set_rules(b)
    pcbutil.fill(b)
    BD = design.BOARD

    pads = {}
    #pad copper counts too
    pad_boxes = {}
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            n = pd.GetNet()
            if not n:
                continue
            pads.setdefault(n.GetNetname(), []).append(
                (f"{fp.GetReference()}.{pd.GetNumber()}",
                 (power_cut_TOMM(pd.GetPosition().x), power_cut_TOMM(pd.GetPosition().y))))
            bb = pd.GetBoundingBox()
            pad_boxes.setdefault(n.GetNetname(), []).append(
                (power_cut_TOMM(bb.GetLeft()), power_cut_TOMM(bb.GetTop()),
                 power_cut_TOMM(bb.GetRight()), power_cut_TOMM(bb.GetBottom())))

    fails, warns, notes = [], [], []
    for netname, want in sorted(design.NET_CURRENT.items()):
        src = design.NET_SOURCE.get(netname)
        if not src:
            continue
        code = b.FindNet(netname).GetNetCode()
        spos = next((p for r, p in pads.get(netname, []) if r == src), None)
        if spos is None:
            continue
        #capacitors and resistors draw nothing
        named = getattr(design, "LOAD_CURRENT", {}).get(netname, {})
        loads = [(r, p) for r, p in pads.get(netname, [])
                 if r != src and (r in named or not r.split(".")[0].startswith(("C", "R")))]
        if not loads:
            continue

        tracks = []
        segs = [t for t in b.GetTracks()
                if t.GetNetCode() == code and t.Type() != pcbnew.PCB_VIA_T]
        for lay, a, c, w in drop_dead_ends(b, code, segs):
            tracks.append((a, c, w, b.GetLayerName(lay) in INNER))
        zones = []
        for z in b.Zones():
            n = z.GetNet()
            if not n or n.GetNetname() != netname:
                continue
            for lid in z.GetLayerSet().CuStack():
                sh = z.GetFilledPolysList(lid)
                inner = b.GetLayerName(lid) in INNER
                for i in range(sh.OutlineCount()):
                    o = sh.Outline(i)
                    pts = [(power_cut_TOMM(o.CPoint(k).x), power_cut_TOMM(o.CPoint(k).y))
                           for k in range(o.PointCount())]
                    if pcbutil.area(pts) > 1.0:
                        zones.append((pts, inner))

        worst = None
        for axis in ("x", "y"):
            i = 0 if axis == "x" else 1
            lo = BD["X0"] if axis == "x" else BD["Y0"]
            hi = lo + (BD["W"] if axis == "x" else BD["H"])
            v = lo + 0.5
            while v < hi - 0.5:
                #only lines that actually separate the source from some load
                sep = [r for r, p in loads if (spos[i] - v) * (p[i] - v) < 0]
                if sep:
                    tot = 0.0
                    for a, c, w, inn in tracks:
                        if seg_crosses(a, c, axis, v):
                            tot += ipc_width(w, inn)
                    for pts, inn in zones:
                        span = poly_span(pts, axis, v)
                        if span > 0:
                            tot += ipc_width(span, inn)
                    for l, t_, r_, bm in pad_boxes.get(netname, []):
                        lo_, hi_ = (l, r_) if axis == "x" else (t_, bm)
                        if lo_ <= v <= hi_:
                            span = (bm - t_) if axis == "x" else (r_ - l)
                            if span > 0:
                                tot += ipc_width(span, False)
                    rail_load_cur = getattr(design, "LOAD_CURRENT", {}).get(netname, {})
                    need = min(want, sum(rail_load_cur.get(r, want) for r in sep))
                    margin = tot / need if need > 0 else 999.0
                    if worst is None or margin < worst[4]:
                        worst = (tot, axis, v, len(sep), margin, need)
                v += 0.5
        if worst is None:
            continue
        tot, axis, v, nsep, margin, need = worst
        line = (f"{netname}: tightest cut is {axis}={v:.1f} mm carrying ~{tot:.1f} A "
                f"with {nsep} load(s) beyond it, needs {need:.1f} A")
        _pins = design.NETS.get(netname) or []
        _all_dnp = bool(_pins) and all(
            (design.COMPONENTS.get(q.split('.')[0]) or (0, 0, 0, 0, False))[4]
            for q in _pins)
        if _all_dnp:
            notes.append(line + "  [every load is DNP - rail not populated]")
        elif tot < need:
            fails.append(line)
        elif tot < need * 1.5:
            warns.append(line)
        else:
            notes.append(line)

    for title, items in (("NOTES", notes), ("WARNINGS", warns), ("FAILURES", fails)):
        if items:
            print(f"{title} ({len(items)}):")
            for it in items:
                print(f"   {it}")
            print()
    print("Optimistic by construction - axis-aligned cuts only. A comfortable number "
          "means no obvious\nbottleneck; a low one is conclusive.")
    return 1 if fails else 0


#silk_owner

"""Does every label on the silkscreen read as its own part's, and can it be read at all?

Usage: python3 tools/check_board.py silk_owner [--board PATH]

A label fails if it is
  - nearer another part than MARGIN more than it is to its own (nearer, but only just, is a
    guess for the person holding the board)
  - printed where a part's body will sit (hidden once the board is assembled)
  - run together with another label
  - smaller than the fab prints legibly (MIN_H tall, MIN_W stroke)
The placing tools import owner_margin() so they cannot place what this check rejects.
"""

TEXT_GAP = pcbnew.FromMM(0.40)   #two labels closer than this read as one word
MARGIN = pcbnew.FromMM(0.50)     #nearer its own part than any other, by at least this
HIDE = pcbnew.FromMM(0.10)       #overlap with a body that hides a label, beyond rounding
MIN_H, MIN_W = pcbnew.FromMM(1.0), pcbnew.FromMM(0.15)   #JLCPCB: legible from 1.0 / 0.15


def grow(bb, d):
    b = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
    b.Inflate(d)
    return b


def text_box(t):
    """The strokes, not KiCad's padded text box."""
    return t.GetEffectiveTextShape().BBox()


def gap(bx, x, y):
    return math.hypot(max(bx.GetLeft() - x, 0, x - bx.GetRight()),
                      max(bx.GetTop() - y, 0, y - bx.GetBottom()))


def silk_owner_bodies(board):
    return {fp.GetReference(): (fp.IsFlipped(), body_box(fp)) for fp in board.GetFootprints()}


def owner_margin(bods, owner, bottom, x, y):
    """(distance to the nearest other part) - (distance to the owner)."""
    own = gap(bods[owner][1], x, y)
    best = None
    for ref, (flip, bx) in bods.items():
        if ref == owner or flip != bottom or bx is None:
            continue
        d = gap(bx, x, y)
        if best is None or d < best[0]:
            best = (d, ref)
    return (best[0] - own, best[1]) if best else (float("inf"), None)


def labels(board):
    """(owner ref, text item) for everything printed that names a part."""
    out = []
    for fp in board.GetFootprints():
        r = fp.Reference()
        if r.IsVisible() and r.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            out.append((fp.GetReference(), r))
        #a pad's function label (silk_labels.py) is text the footprint itself carries
        for g in fp.GraphicalItems():
            if g.Type() == pcbnew.PCB_TEXT_T and g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                out.append((fp.GetReference(), g))
    import design
    owner_of = {v: k for k, v in design.SILK_NAMES.items()}
    for d in board.GetDrawings():
        if d.Type() == pcbnew.PCB_TEXT_T and d.GetText() in owner_of:
            out.append((owner_of[d.GetText()], d))
    return out


def run_silk_owner():
    path = sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv else BOARD
    b = pcbnew.LoadBoard(path)
    bods = silk_owner_bodies(b)
    bad = []
    items = labels(b)
    for owner, t in items:
        c = text_box(t).GetCenter()
        bottom = t.GetLayer() == pcbnew.B_SilkS
        name = t.GetText() if t.Type() == pcbnew.PCB_TEXT_T else owner
        m, other = owner_margin(bods, owner, bottom, c.x, c.y)
        if m < MARGIN:
            bad.append(f"{name} (for {owner}) could read as {other}'s: "
                       f"{T(gap(bods[owner][1], c.x, c.y)):.2f} mm from {owner}, "
                       f"{T(gap(bods[other][1], c.x, c.y)):.2f} mm from {other} "
                       f"(needs {T(MARGIN):.2f} mm between)")
        strokes = grow(text_box(t), -HIDE)
        under = sorted(ref for ref, (flip, bx) in bods.items()
                       if flip == bottom and bx is not None and strokes.Intersects(bx))
        if under:
            bad.append(f"{name} (for {owner}) is printed under {', '.join(under)} - "
                       "hidden once assembled")
    #two labels closer than TEXT_GAP read as one word
    boxes = [(t.GetText() if t.Type() == pcbnew.PCB_TEXT_T else o, t.GetLayer(), text_box(t))
             for o, t in items]
    for i, (na, la, ba) in enumerate(boxes):
        for nb, lb, bb in boxes[i + 1:]:
            if la == lb and grow(ba, TEXT_GAP).Intersects(bb):
                bad.append(f"{na} and {nb} are closer than "
                           f"{T(TEXT_GAP):.2f} mm - they read as one word")
    #every printed text, labels or not, has to be printable
    small = []
    texts = [d for d in b.GetDrawings() if d.Type() == pcbnew.PCB_TEXT_T]
    for fp in b.GetFootprints():
        texts += [fp.Reference(), fp.Value()] + [g for g in fp.GraphicalItems()
                                                 if g.Type() == pcbnew.PCB_TEXT_T]
    for t in texts:
        if not t.IsVisible() or t.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            continue
        if t.GetTextHeight() < MIN_H - 1000 or t.GetEffectiveTextPenWidth() < MIN_W - 1000:
            small.append(f"'{t.GetShownText(False)}' is {T(t.GetTextHeight()):.2f} mm tall, "
                         f"{T(t.GetEffectiveTextPenWidth()):.2f} mm stroke")
    bad += [f"{x} - under {T(MIN_H):.1f} / {T(MIN_W):.2f} mm prints smudged" for x in small]
    print(f"{len(items)} printed labels checked against every part on their side; "
          f"{len(texts)} texts checked for size")
    for x in bad:
        print(f"  FAIL {x}")
    if bad:
        print(f"\nFAIL - {len(bad)} label problem(s): misattributed, hidden, run together "
              "or too small")
        return 1
    print("every label reads as its own part's by a clear margin, none is hidden or run "
          "together, and every text prints legibly")
    return 0


#traces

"""Signal-integrity review of the routed copper: length, layer changes, and pair matching."""

traces_TOMM = lambda v: v / 1e6

#limits are derived, not invented
CRYSTAL_MM = design.Y1_STRAY_PF / 0.1        #~0.1 pF per mm of trace
#an SPI line is electrically short
SPI_TR_PS, TPD_PS_MM = 2800.0, 7.0
SPI_MM = SPI_TR_PS / (6 * TPD_PS_MM)          #~66.7 mm
#nets judged on that path rather than on total copper: summed over a tree
EDGE_LIMITED = {"SPI1_SCK", "SPI1_MISO", "SPI1_MOSI", "SPI4_SCK", "SPI3_SCK"}
CRITICAL = {
    "OSC_IN":       ("crystal - stray C shifts the load; see Y1_STRAY_PF", CRYSTAL_MM),
    "OSC_OUT":      ("crystal", CRYSTAL_MM),
    "USB_DP":       ("USB 2.0 FS - delay is irrelevant at 12 Mbps", 80.0),
    "USB_DM":       ("USB 2.0 FS", 80.0),
    "SPI1_SCK":     ("IMU1 clock - the primary IMU, 24 MHz", SPI_MM),
    "SPI1_MISO":    ("IMU1", SPI_MM),
    "SPI1_MOSI":    ("IMU1", SPI_MM),
    "SPI4_SCK":     ("IMU2 clock", SPI_MM),
    "SPI3_SCK":     ("flash 32 MHz + flow port J14", SPI_MM),
    "I2C1_SCL":     ("external I2C - capacitance-limited, not length-limited", 200.0),
    "I2C1_SDA":     ("external I2C", 200.0),
    "SWCLK":        ("SWD ~4 MHz", 125.0),
    "SWDIO":        ("SWD", 125.0),
}
#USB 2.0 full speed tolerates enormous skew
PAIRS = [("USB_DP", "USB_DM", 20.0)]


def net_stats(board):
    """Length, via count and layer spread per net."""
    out = {}
    for t in board.GetTracks():
        net = t.GetNet()
        if not net:
            continue
        n = net.GetNetname()
        d = out.setdefault(n, {"len": 0.0, "vias": 0, "layers": set()})
        if t.Type() == pcbnew.PCB_VIA_T:
            d["vias"] += 1
        else:
            s, e = t.GetStart(), t.GetEnd()
            d["len"] += math.hypot(traces_TOMM(e.x - s.x), traces_TOMM(e.y - s.y))
            d["layers"].add(board.GetLayerName(t.GetLayer()))
    return out


def longest_path(board, net, driver="U1"):
    """mm from the driver's pad, through the net's copper."""
    T = traces_TOMM
    segs = [t for t in board.GetTracks() if t.GetNetname() == net and t.Type() != pcbnew.PCB_VIA_T]
    vias = [t for t in board.GetTracks() if t.GetNetname() == net and t.Type() == pcbnew.PCB_VIA_T]
    pads = [(fp.GetReference(), p) for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == net]
    nodes = []                                   #(layer, x, y)
    adj = {}

    def node(lay, q):
        nodes.append((lay, T(q.x), T(q.y)))
        adj[len(nodes) - 1] = []
        return len(nodes) - 1

    def link(a, b, w):
        adj[a].append((b, w)); adj[b].append((a, w))

    ends = []
    for t in segs:
        a, b = node(t.GetLayer(), t.GetStart()), node(t.GetLayer(), t.GetEnd())
        link(a, b, T(t.GetLength()))
        ends += [(a, t), (b, t)]
    for i, (a, ta) in enumerate(ends):
        la, xa, ya = nodes[a]
        for b, tb in ends[i + 1:]:
            lb, xb, yb = nodes[b]
            if la == lb and tb is not ta and math.hypot(xa - xb, ya - yb) <= T(ta.GetWidth() + tb.GetWidth()) / 2:
                link(a, b, math.hypot(xa - xb, ya - yb))
        for t in segs:                           #a tee onto another track's body
            if t is ta or t.GetLayer() != la:
                continue
            if t.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(xa), pcbnew.FromMM(ya)), ta.GetWidth() // 2):
                s0, s1 = t.GetStart(), t.GetEnd()
                for q in (s0, s1):
                    j = next(n for n, tt in ends if tt is t and nodes[n][1:] == (T(q.x), T(q.y)))
                    link(a, j, math.hypot(xa - T(q.x), ya - T(q.y)))
    for v in vias:
        c, r = v.GetPosition(), T(v.GetWidth(pcbnew.F_Cu)) / 2
        hub = node(None, c)
        for n, t in ends:
            if math.hypot(nodes[n][1] - T(c.x), nodes[n][2] - T(c.y)) <= r + T(t.GetWidth()) / 2:
                link(hub, n, 0.0)
    padnode = {}
    for ref, p in pads:
        hub = node(None, p.GetPosition())
        padnode[(ref, p.GetNumber())] = hub
        for n, t in ends:
            q = pcbnew.VECTOR2I(pcbnew.FromMM(nodes[n][1]), pcbnew.FromMM(nodes[n][2]))
            if p.IsOnLayer(t.GetLayer()) and p.HitTest(q, t.GetWidth() // 2):
                link(hub, n, 0.0)
    src = [h for (ref, _num), h in padnode.items() if ref == driver]
    if not src:
        return None
    dist = {s0: 0.0 for s0 in src}
    pq = [(0.0, s0) for s0 in src]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        for v2, w in adj[u]:
            if d + w < dist.get(v2, 1e18):
                dist[v2] = d + w
                heapq.heappush(pq, (d + w, v2))
    if any(h not in dist for h in padnode.values()):
        return None
    return max(dist.values())


def offboard_mm(net):
    """The longest lead fitted to a connector on the net."""
    refs = {q.split(".")[0] for q in design.NETS.get(net, [])}
    return max([cables.CABLES[r].get("buy") or 0.0 for r in refs if r in cables.CABLES] or [0.0])


def traces_self_test():
    """Each fault must put SPI3_SCK over its limit, or make a pad unreachable."""
    def over(board):
        path = longest_path(board, "SPI3_SCK")
        return path is None or path + offboard_mm("SPI3_SCK") > SPI_MM

    def stub(board):                       #a spur as long as the limit: over wherever it hangs
        segs = [t for t in board.GetTracks() if t.GetNetname() == "SPI3_SCK"
                and t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() == board.GetLayerID("In2.Cu")]
        t0 = max(segs, key=lambda t: t.GetEnd().x)
        t = pcbnew.PCB_TRACK(board)
        t.SetLayer(t0.GetLayer()); t.SetNet(t0.GetNet()); t.SetWidth(t0.GetWidth())
        t.SetStart(t0.GetEnd()); t.SetEnd(t0.GetEnd() + pcbnew.VECTOR2I(0, pcbnew.FromMM(SPI_MM)))
        board.Add(t)

    def cut(board):                        #the via that takes U1's escape down to In2
        v = min((t for t in board.GetTracks() if t.GetNetname() == "SPI3_SCK"
                 and t.Type() == pcbnew.PCB_VIA_T),
                key=lambda t: abs(traces_TOMM(t.GetPosition().x) - 121.73) + abs(traces_TOMM(t.GetPosition().y) - 123.4))
        board.Remove(v)

    def lead(board):                       #a flow sensor fitted on a 200 mm lead
        cables.CABLES["J14"]["buy"] = 200

    bad = 0
    if over(pcbnew.LoadBoard(BOARD)):
        print("  the unfaulted board is already over - the faults below would prove nothing")
        return 1
    for name, fault in (("spur of the limit's length", stub), ("escape via removed", cut), ("200 mm J14 lead", lead)):
        b = pcbnew.LoadBoard(BOARD)
        keep = cables.CABLES["J14"].get("buy")
        fault(b)
        caught = over(b)
        cables.CABLES["J14"]["buy"] = keep
        print(f"  {'ok  ' if caught else 'MISS'} {name}")
        bad += not caught
    print("self-test " + ("FAILED" if bad else "passed"))
    return 1 if bad else 0


def _all_dnp(net):
    """True if every pad on `net` belongs to a do-not-populate part."""
    pins = design.NETS.get(net) or []
    if not pins:
        return False
    return all((design.COMPONENTS.get(q.split(".")[0]) or (0, 0, 0, 0, False))[4]
               for q in pins)


def run_traces():
    if "--self-test" in sys.argv:
        return traces_self_test()
    board = pcbnew.LoadBoard(BOARD)
    st = net_stats(board)

    print("=== critical nets ===")
    print(f"{'net':14}{'len mm':>8}{'vias':>6}  {'layers':22} note")
    warn = 0
    for n, (why, limit) in CRITICAL.items():
        d = st.get(n)
        if not d:
            print(f"{n:14}{'--':>8}{'--':>6}  {'(not routed)':22} {why}")
            if not _all_dnp(n):
                print(f"{'':14}{'':>8}{'':>6}  {'':22} "
                      f"<-- NOT ROUTED and it is not a DNP-only net")
                warn += 1
            continue
        measure = d["len"]
        if n in EDGE_LIMITED:
            path = longest_path(board, n)
            if path is None:
                print(f"{n:14}{'--':>8}{d['vias']:6}  {'':22} {why}  <-- a pad is unreachable "
                      f"through the copper from U1")
                warn += 1
                continue
            lead = offboard_mm(n)
            measure = path + lead
            why = (f"{why}; longest path {path:.1f} mm" + (f" + {lead:.0f} mm lead" if lead else "")
                   + f" of {limit:.1f} (total copper {d['len']:.1f})")
        flag = "  <-- OVER" if measure > limit else ""
        if measure > limit:
            warn += 1
        print(f"{n:14}{measure:8.1f}{d['vias']:6}  {','.join(sorted(d['layers']))[:22]:22} {why}{flag}")

    print("\n=== differential pair matching ===")
    for a, bnet, tol in PAIRS:
        da, db = st.get(a), st.get(bnet)
        if not (da and db):
            print(f"  {a}/{bnet}: one or both not routed")
            continue
        skew = abs(da["len"] - db["len"])
        ok = skew <= tol
        print(f"  {a} {da['len']:.1f} mm vs {bnet} {db['len']:.1f} mm"
              f"  -> skew {skew:.2f} mm (tolerance {tol})  {'OK' if ok else 'MISMATCHED'}")
        if da["vias"] != db["vias"]:
            print(f"     via counts differ: {da['vias']} vs {db['vias']} - "
                  f"asymmetric pairs radiate and reflect")
        if not ok:
            warn += 1

    print("\n=== longest nets on the board ===")
    for n, d in sorted(st.items(), key=lambda kv: -kv[1]["len"])[:8]:
        print(f"  {n:18}{d['len']:8.1f} mm{d['vias']:4} vias")

    print("\nEstimated stray capacitance on the crystal nets "
          "(~0.1 pF/mm of trace, ~0.5 pF per via):")
    for n in ("OSC_IN", "OSC_OUT"):
        d = st.get(n)
        if d:
            c = d["len"] * 0.1 + d["vias"] * 0.5
            over = c > design.Y1_STRAY_PF
            if over:
                warn += 1
            print(f"  {n:8} ~{c:.1f} pF   (budget: design.Y1_STRAY_PF = "
                  f"{design.Y1_STRAY_PF} pF)" + ("  <-- OVER BUDGET" if over else ""))
        else:
            print(f"  {n:8} (not routed)")

    print(f"\n{warn} item(s) over their stated limit")
    return 1 if warn else 0


#model_alignment

"""Check that every component's 3D body sits on its own footprint and touches no other part's,
nor the hardware bolted through the stack holes, measured in the exported GLB - the thing
the 3D viewer and the renders actually draw.

Usage: python3 tools/check_board.py model_alignment [--tol 0.25] [--board PATH]
JLC_LIB defaults to ../.libraries/jlc.pretty beside the repo.
"""

EXPECTED = design.MODEL_EXPECTED
SINK_TOL = 0.15
COLLIDE = 0.05       #mm of overlap on every axis before two bodies are said to collide
EXPECTED_SINK = design.MODEL_EXPECTED_SINK


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def local_matrix(n):
    if "matrix" in n:
        m = n["matrix"]
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    tx, ty, tz = n.get("translation", [0, 0, 0])
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = n.get("scale", [1, 1, 1])
    R = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[R[0][0] * sx, R[0][1] * sy, R[0][2] * sz, tx],
            [R[1][0] * sx, R[1][1] * sy, R[1][2] * sz, ty],
            [R[2][0] * sx, R[2][1] * sy, R[2][2] * sz, tz],
            [0, 0, 0, 1]]


def model_alignment_bodies(glb):
    """reference -> (min xyz, max xyz) in the GLB world frame."""
    data = open(glb, "rb").read()
    ln = struct.unpack_from("<I", data, 12)[0]
    g = json.loads(data[20:20 + ln])
    parent = {c: i for i, n in enumerate(g["nodes"]) for c in n.get("children", [])}
    out = {}
    for i, n in enumerate(g["nodes"]):
        if "mesh" not in n or not n.get("name"):
            continue
        M, j = [[1 if r == c else 0 for c in range(4)] for r in range(4)], i
        chain = []
        while j is not None:
            chain.append(j)
            j = parent.get(j)
        for j in reversed(chain):
            M = matmul(M, local_matrix(g["nodes"][j]))
        lo, hi = [math.inf] * 3, [-math.inf] * 3
        for p in g["meshes"][n["mesh"]]["primitives"]:
            a = g["accessors"][p["attributes"]["POSITION"]]
            mn, mx = a["min"], a["max"]
            for cx in (mn[0], mx[0]):
                for cy in (mn[1], mx[1]):
                    for cz in (mn[2], mx[2]):
                        w = [sum(M[r][k] * v for k, v in enumerate((cx, cy, cz, 1))) for r in range(3)]
                        lo = [min(lo[k], w[k]) for k in range(3)]
                        hi = [max(hi[k], w[k]) for k in range(3)]
        out[n["name"]] = (lo, hi)
    return out


def vertices(glb, name):
    """Every vertex of the named node's mesh, in the GLB world frame (metres)."""
    data = open(glb, "rb").read()
    ln = struct.unpack_from("<I", data, 12)[0]
    g = json.loads(data[20:20 + ln])
    binoff = 20 + ln + 8
    parent = {c: i for i, n in enumerate(g["nodes"]) for c in n.get("children", [])}
    out = []
    for i, n in enumerate(g["nodes"]):
        if n.get("name") != name or "mesh" not in n:
            continue
        M, j, chain = [[1 if r == c else 0 for c in range(4)] for r in range(4)], i, []
        while j is not None:
            chain.append(j)
            j = parent.get(j)
        for j in reversed(chain):
            M = matmul(M, local_matrix(g["nodes"][j]))
        for p in g["meshes"][n["mesh"]]["primitives"]:
            a = g["accessors"][p["attributes"]["POSITION"]]
            bv = g["bufferViews"][a["bufferView"]]
            off = binoff + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
            stride = bv.get("byteStride", 12)
            for k in range(a["count"]):
                v = struct.unpack_from("<3f", data, off + k * stride)
                out.append([sum(M[r][q] * c for q, c in enumerate((*v, 1))) for r in range(3)])
    return out


def peg_holes(fp):
    """The footprint's non-plated locating holes: (x, y, radius) in mm."""
    return [(T(p.GetPosition().x), T(p.GetPosition().y), T(p.GetDrillSize().x) / 2)
            for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]


def silk_bbox(fp):
    xs, ys = [], []
    for gi in fp.GraphicalItems():
        if gi.GetLayerName() not in ("F.Silkscreen", "B.Silkscreen") or \
                gi.Type() in (pcbnew.PCB_TEXT_T, pcbnew.PCB_FIELD_T):
            continue
        bb = gi.GetBoundingBox()
        xs += [T(bb.GetLeft()), T(bb.GetRight())]
        ys += [T(bb.GetTop()), T(bb.GetBottom())]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def pad_bbox(fp):
    xs, ys = [], []
    for p in fp.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            continue
        bb = p.GetBoundingBox()
        xs += [T(bb.GetLeft()), T(bb.GetRight())]
        ys += [T(bb.GetTop()), T(bb.GetBottom())]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def fit(pairs):
    """Least-squares y = a*x + b."""
    n = len(pairs)
    sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
    sxx = sum(p[0] ** 2 for p in pairs); sxy = sum(p[0] * p[1] for p in pairs)
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return a, (sy - a * sx) / n


def run_model_alignment():
    tol = float(sys.argv[sys.argv.index("--tol") + 1]) if "--tol" in sys.argv else 0.25
    board = sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv else BOARD
    jlc = os.environ.get("JLC_LIB") or os.path.join(os.path.dirname(REPO), ".libraries",
                                                    "jlc.pretty")
    if not os.path.isdir(os.path.join(jlc, "packages3d")):
        #not a skip: a check that passes without looking cannot fail
        print(f"FAIL - no 3D models at {jlc}/packages3d; set JLC_LIB")
        return 1
    b = pcbnew.LoadBoard(board)
    #a part with locating pegs is placed by them: judge it
    pegged = {fp.GetReference(): peg_holes(fp) for fp in b.GetFootprints() if peg_holes(fp)}
    with tempfile.TemporaryDirectory() as td:
        glb = os.path.join(td, "board.glb")
        subprocess.run(["kicad-cli", "pcb", "export", "glb", "--output", glb, "-D", f"JLC_LIB={jlc}",
                        "--subst-models", "--force", board], capture_output=True, check=True)
        body = model_alignment_bodies(glb)
        #holes with no model to fit them (a Tag-Connect footprint) locate nothing
        pegged = {r: h for r, h in pegged.items() if r in body}
        verts = {r: vertices(glb, r) for r in pegged}
    ref_c = {}
    for fp in b.GetFootprints():
        r = fp.GetReference()
        if r not in body or r in pegged:
            continue
        s = silk_bbox(fp) if r.startswith("J") else None
        box = s or pad_bbox(fp)
        if box:
            ref_c[r] = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    #the GLB is Y-up in metres: its x and z carry the board plane
    cen = {r: ((body[r][0][0] + body[r][1][0]) / 2, (body[r][0][2] + body[r][1][2]) / 2) for r in ref_c}
    #two passes: fit, drop anything more than 1 mm out, refit
    use = list(ref_c)
    for _ in range(2):
        ax = fit([(cen[r][0], ref_c[r][0]) for r in use])
        ay = fit([(cen[r][1], ref_c[r][1]) for r in use])
        use = [r for r in ref_c if math.hypot(ax[0] * cen[r][0] + ax[1] - ref_c[r][0],
                                              ay[0] * cen[r][1] + ay[1] - ref_c[r][1]) < 1.0]
    bad = []
    for r in sorted(ref_c):
        bx, by = ax[0] * cen[r][0] + ax[1], ay[0] * cen[r][1] + ay[1]
        ex, ey = EXPECTED.get(r, (0.0, 0.0))
        d = math.hypot(bx - ref_c[r][0] - ex, by - ref_c[r][1] - ey)
        if d > tol:
            bad.append((r, d, bx - ref_c[r][0] - ex, by - ref_c[r][1] - ey))
    #the GLB is Y-up with the board's underside at 0 and its top at the board thickness
    thick = T(b.GetDesignSettings().GetBoardThickness())
    pegs = []
    for r, holes in sorted(pegged.items()):
        inside = [(ax[0] * v[0] + ax[1], ay[0] * v[2] + ay[1]) for v in verts.get(r, [])
                  if 0.05 < v[1] * 1000 < thick - 0.05]
        worst, dxy = 0.0, (0.0, 0.0)
        for hx, hy, hr in holes:
            #the peg is inside its hole: look no further
            near = [(x, y) for x, y in inside if math.hypot(x - hx, y - hy) < hr + 0.5]
            if not near:
                worst = math.inf
                break
            mx, my = sum(x for x, _ in near) / len(near), sum(y for _, y in near) / len(near)
            if math.hypot(mx - hx, my - hy) >= worst:
                worst, dxy = math.hypot(mx - hx, my - hy), (mx - hx, my - hy)
        pegs.append((r, worst, len(holes), dxy))
    sunk = []
    for fp in b.GetFootprints():
        r = fp.GetReference()
        if r not in body:
            continue
        lo, hi = body[r][0][1] * 1000, body[r][1][1] * 1000
        sink = thick - lo if fp.GetLayerName() == "F.Cu" else hi
        want = EXPECTED_SINK.get(r, 0.0)
        if (abs(sink - want) > SINK_TOL) if r in EXPECTED_SINK else sink > SINK_TOL:
            sunk.append((r, sink, want))
    #every body against every other
    side = {fp.GetReference(): fp.IsFlipped() for fp in b.GetFootprints()}
    box = {}
    for r, (lo, hi) in body.items():
        if r not in side:
            continue                    #the board itself, not a part
        xs = sorted((ax[0] * lo[0] + ax[1], ax[0] * hi[0] + ax[1]))
        ys = sorted((ay[0] * lo[2] + ay[1], ay[0] * hi[2] + ay[1]))
        box[r] = (xs[0], ys[0], xs[1], ys[1], lo[1] * 1000, hi[1] * 1000)
    clash = []
    refs = sorted(box)
    for i, ra in enumerate(refs):
        A = box[ra]
        for rb in refs[i + 1:]:
            B = box[rb]
            o = [min(A[h], B[h]) - max(A[l], B[l]) for l, h in ((0, 2), (1, 3), (4, 5))]
            if min(o) > COLLIDE:
                clash.append((ra, rb, o))
    #what is bolted through each stack hole sits flat on the board
    hw = design.FC_HOLE_HARDWARE
    reach = {False: hw["top"][0]["reach_d"] / 2, True: hw["bottom"][0]["reach_d"] / 2}
    stack = [(T(d.GetCenter().x), T(d.GetCenter().y)) for d in b.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts and d.ShowShape() == "Circle"]
    under = []
    for r, (x0, y0, x1, y1, _, _) in sorted(box.items()):
        for hx, hy in stack:
            d = math.hypot(max(x0 - hx, 0, hx - x1), max(y0 - hy, 0, hy - y1))
            if d < reach[side[r]]:
                under.append((r, d, reach[side[r]], hw["bottom" if side[r] else "top"][0]["name"]))
    print(f"{len(ref_c)} bodies measured against their footprints (tolerance {tol} mm)")
    print(f"{len(box)} bodies tested against the hardware at {len(stack)} stack holes: "
          f"{len(under)} under it")
    for r, d, rr, name in under:
        print(f"  FAIL {r:5s} body is {d:.2f} mm from a stack hole, inside the {name} ({rr:.2f} mm)")
    print(f"{len(box)} bodies tested against each other: {len(clash)} overlap(s)")
    for ra, rb, o in clash:
        print(f"  FAIL {ra} and {rb} bodies overlap by {o[0]:.2f} x {o[1]:.2f} x {o[2]:.2f} mm")
    peg_bad = 0
    for r, worst, n, (dx, dy) in pegs:
        ok = worst <= tol
        peg_bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {r:5s} its {n} locating pegs sit "
              + (f"{worst:.2f} mm from the footprint's holes (dx {dx:+.2f}, dy {dy:+.2f})"
                 if worst != math.inf else "nowhere near the footprint's holes"))
    for r, d, dx, dy in bad:
        print(f"  FAIL {r:5s} body is {d:.2f} mm off (dx {dx:+.2f}, dy {dy:+.2f})")
    for r, sink, want in sunk:
        print(f"  FAIL {r:5s} body reaches {sink:.2f} mm into the board (expected {want:.2f}) - "
              "correct the model's z offset")
    if sunk and not bad:
        print(f"\nFAIL - {len(sunk)} body/bodies at the wrong height")
        return 1
    if clash:
        print(f"\nFAIL - {len(clash)} pair(s) of bodies occupy the same space")
        return 1
    if under:
        print(f"\nFAIL - {len(under)} body/bodies under the stack hardware")
        return 1
    if bad or peg_bad:
        print(f"\nFAIL - {len(bad) + peg_bad} body/bodies misplaced; correct the model offset in the "
              "footprint (libraries/jlc.pretty) and on the board")
        return 1
    print("every body sits on its own footprint, at the right height")
    return 0


#cpl

"""Verify the pick-and-place rotations from board geometry, independently of what wrote
them.

Usage:  python3 tools/check_board.py cpl [-v] [--svg DIR] [--board PATH]
"""

CPL   = "fab/CPL-NAVCORE-SoOP.csv"
cpl_TOMM  = pcbutil.TOMM
cpl_TOL   = 12.0        #degrees; footprints place pin 1 on a coarse grid of directions


def pin1(fp):
    """The pad that defines orientation - pin 1, or the first pad if unnumbered."""
    pads = list(fp.Pads())
    for want in ("1", "A1", "A4B9"):
        for p in pads:
            if p.GetNumber() == want:
                return p
    return pads[0] if pads else None


def silk_dots(fp):
    """Small silkscreen circles."""
    return [g for g in fp.GraphicalItems()
            if g.GetLayerName() in ("F.Silkscreen", "B.Silkscreen")
            and g.GetShape() == pcbnew.SHAPE_T_CIRCLE and cpl_TOMM(g.GetRadius()) <= 0.3]


def dot_errors(board):
    """A pin-1 dot by the wrong pad does not move the machine."""
    dots, errs = 0, []
    for fp in board.GetFootprints():
        p1 = pin1(fp)
        if p1 is None or len(fp.Pads()) < 3:
            continue
        for g in silk_dots(fp):
            dots += 1
            c = g.GetCenter()
            near = min(fp.Pads(), key=lambda p: (p.GetPosition() - c).EuclideanNorm())
            if near.GetNumber() != p1.GetNumber():
                errs.append(f"{fp.GetReference()}: its silkscreen pin-1 dot at "
                            f"({cpl_TOMM(c.x):.2f}, {cpl_TOMM(c.y):.2f}) is nearest pad "
                            f"{near.GetNumber()}, not pad {p1.GetNumber()}")
    return dots, errs


def cpl_self_test():
    """U8's dot moved back beside pad 11 must be caught."""
    b = pcbnew.LoadBoard(BOARD)
    fp = b.FindFootprintByReference("U8")
    silk_dots(fp)[0].Move(pcbnew.VECTOR2I(0, pcbnew.FromMM(2.6)))
    _n, errs = dot_errors(b)
    caught = any(e.startswith("U8:") for e in errs)
    print(f"  {'ok  ' if caught else 'MISS'} U8's pin-1 dot moved to pad 11")
    return 0 if caught else 1


def run_cpl():
    if "--self-test" in sys.argv:
        return cpl_self_test()
    verbose = "-v" in sys.argv
    svgdir = None
    if "--svg" in sys.argv:
        svgdir = sys.argv[sys.argv.index("--svg") + 1]

    b = pcbnew.LoadBoard(BOARD)
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
    rows = list(csv.DictReader(open(CPL)))

    by_fp = collections.defaultdict(list)
    errs, notes = [], []
    drawn = []

    for r in rows:
        ref = r["Designator"]
        fp = fps.get(ref)
        if fp is None:
            errs.append(f"{ref} is in the CPL but not on the board")
            continue
        p1 = pin1(fp)
        if p1 is None:
            continue
        c, pp = fp.GetPosition(), p1.GetPosition()
        dx, dy = cpl_TOMM(pp.x) - cpl_TOMM(c.x), cpl_TOMM(pp.y) - cpl_TOMM(c.y)
        if math.hypot(dx, dy) < 0.05:
            continue                       #centred pin 1 carries no direction
        bottom = r["Layer"].strip().lower() == "bottom"
        if bottom:
            dx = -dx                       #the assembler sees the back mirrored
        rot = float(r["Rotation"])
        a = math.radians(rot)
        cx = dx * math.cos(a) - dy * math.sin(a)
        cy = dx * math.sin(a) + dy * math.cos(a)
        name = fp.GetFPID().GetLibItemName().wx_str()
        by_fp[name].append((ref, math.degrees(math.atan2(cy, cx)) % 360.0,
                            r["Layer"].strip(), rot))
        drawn.append((ref, name, r["Layer"].strip(), rot,
                      cpl_TOMM(c.x), cpl_TOMM(c.y), cpl_TOMM(pp.x), cpl_TOMM(pp.y)))

    checked = 0
    for name, items in sorted(by_fp.items()):
        if len(items) < 2:
            continue
        checked += len(items)
        base = items[0][1]
        spread = [(ref, ((ang - base + 180) % 360) - 180, lay, rot)
                  for ref, ang, lay, rot in items]
        bad = [x for x in spread if abs(x[1]) > cpl_TOL]
        if bad:
            errs.append(
                f"{name}: parts disagree on where pin 1 is once their CPL rotation is "
                f"undone - " + ", ".join(
                    f"{ref} ({lay}, {rot:.0f} deg) off by {d:+.0f} deg"
                    for ref, d, lay, rot in bad[:4]))
        elif verbose:
            print(f"  ok  {name:48} {len(items)} parts agree")

    dots, wrong = dot_errors(b)
    errs += wrong
    print(f"pin-1 dots         : {dots} checked against the pad they sit beside")
    sides = collections.Counter(r["Layer"].strip() for r in rows)
    rots = collections.Counter(float(r["Rotation"]) for r in rows)
    print(f"CPL placements     : {len(rows)}  ({sides['top']} top, {sides['bottom']} bottom)")
    print(f"rotations used     : " + ", ".join(f"{k:.0f} deg x{v}"
                                               for k, v in sorted(rots.items())))
    print(f"cross-checked      : {checked} parts across "
          f"{sum(1 for v in by_fp.values() if len(v) > 1)} shared footprints")

    if svgdir:
        os.makedirs(svgdir, exist_ok=True)
        for side in ("top", "bottom"):
            write_svg(os.path.join(svgdir, f"pin1-{side}.svg"),
                      [d for d in drawn if d[2] == side], side, b)
            print(f"wrote {svgdir}/pin1-{side}.svg")

    for it in notes:
        print(f"   {it}")
    if errs:
        print(f"\nERRORS ({len(errs)}):")
        for e in errs:
            print(f"   {e}")
        return 1
    print("\nevery shared footprint agrees on pin 1 - rotations are self-consistent.")
    return 0


def write_svg(path, items, side, board):
    """Pin-1 overlay: part outline, a dot at pin 1, and the CPL rotation."""
    import design
    BD = design.BOARD
    W, H = BD["W"], BD["H"]
    X0, Y0 = BD["X0"], BD["Y0"]
    sc = 16
    flip = (side == "bottom")

    def X(x):
        return ((X0 + W - x) if flip else (x - X0)) * sc

    def Y(y):
        return (y - Y0) * sc

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*sc}" height="{H*sc+30}" '
           f'viewBox="0 0 {W*sc} {H*sc+30}">',
           f'<rect width="100%" height="100%" fill="#14181c"/>',
           f'<text x="8" y="{H*sc+20}" fill="#8aa" font-family="monospace" '
           f'font-size="13">{side} side, viewed as the assembler sees it - '
           f'dot = pin 1, number = CPL rotation</text>']
    for ref, name, lay, rot, cx, cy, px, py in items:
        out.append(f'<line x1="{X(cx):.1f}" y1="{Y(cy):.1f}" x2="{X(px):.1f}" '
                   f'y2="{Y(py):.1f}" stroke="#3d5a6c" stroke-width="1"/>')
        out.append(f'<circle cx="{X(px):.1f}" cy="{Y(py):.1f}" r="2.6" fill="#ffb347"/>')
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy):.1f}" fill="#dfe7ea" '
                   f'font-family="monospace" font-size="8" text-anchor="middle">'
                   f'{ref}</text>')
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy)+8:.1f}" fill="#6fd0c0" '
                   f'font-family="monospace" font-size="7" text-anchor="middle">'
                   f'{rot:.0f}</text>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out))


#footprints

"""Every footprint's pad count, against JLCPCB's own joint count for that part number."""

DATA = os.environ.get("JLC_DATA", "/tmp/nav/jlc")
SNAPSHOT = os.path.join(REPO, "fab", "stock-snapshot.json")

#parts JLCPCB assembles but the community mirror does not carry
MIRROR_GAPS = {
    "C51940119": "J3's JST-GH 6P - jlcpcb.com/partdetail/C51940119 confirms the part; "
                 "the mirror simply lacks the row",
}

#packages the mirror describes not at all, or too loosely to key on
DATASHEET_PACKAGE = {
    "C5271084": ("LQFP-100", 14.0, 14.0, 0.50,
                 "[D] ST DS12110 STM32H743xI: LQFP100 14x14x1.4 mm, 0.50 mm pitch"),
    "C2682774": ("SMD3225-4P", 3.2, 2.5, None,
                 "[D] YXC X322508MSB4SI: 3.2 x 2.5 mm 4-pad SMD crystal"),
    "C51940119": ("XY-SM06B-GHS-TB", None, None, 1.25,
                  "[L] jlcpcb.com/partdetail/C51940119, verified 2026-09-03"),
}

#parts whose package has an exposed thermal pad that JLCPCB's package string leaves out
THERMAL_PAD = {
    "C22399950": "[D] TI TLV757P SBVS320: 'DYD Package, 5-Pin SOT-23 With Exposed Thermal "
                 "Pad' (fig. 4-2); the pad goes to a large ground plane",
}

#industry-standard pitches by package family
FAMILY_PITCH = {
    "SOT-23": 0.95, "SOT-25": 0.95, "SOIC": 1.27, "LQFP-100": 0.50,
    "LGA-14": 0.50, "LGA-12": 0.80, "QFN-8": 1.25, "COB-28": 0.65,
    "SOP-8": 1.27, "TQFN-28-EP": 0.50, "DSBGA-6": 0.40,
}

#electrical pad count implied by a JLCPCB package token
PACKAGE_PADS = {
    "SMD3225-4P": 4, "LQFP-100": 100, "LGA-14": 14, "LGA-12": 12, "QFN-8": 8,
    "SOIC-8": 8, "SOIC-8-208MIL": 8, "SOP-8": 8, "TQFN-28-EP": 29, "DSBGA-6": 6,
    "COB-28": 28, "SOT-23": 3, "SOT-23-3": 3, "SOT-23-3L": 3, "SOT-23-5": 5,
    "SOT-23-6": 6, "SOT-25-5": 5, "SOD-123": 2, "DO-214AA": 2, "DO-214AA(SMB)": 2,
    #U8's RNX: 'VQFN-12(2x3)' in JLCPCB's own package string
    "VQFN-12": 12,
    "0402": 2, "0603": 2, "0805": 2, "1206": 2,
}


def pads_from_spec(spec):
    """Pin count JLCPCB's package string implies, or None if it states no count."""
    if not spec:
        return None
    up = spec.strip().upper()
    #exact token first
    if up in PACKAGE_PADS:
        return PACKAGE_PADS[up]
    return PACKAGE_PADS.get(re.sub(r"\(.*?\)", "", up).strip())


def load_snapshot():
    """{code: (mpn, package_spec)} from the dated JLCPCB snapshot."""
    try:
        with open(SNAPSHOT) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for code, r in (d.get("lines") or {}).items():
        if r.get("found"):
            out[code] = (r.get("mpn"), r.get("spec"))
    return out


def norm(t):
    """Strip everything that is not alphanumeric, upper-cased."""
    return re.sub(r"[^A-Z0-9]", "", (t or "").upper())


def mpn_matches(fpname, mfr):
    """Is this footprint named after the exact manufacturer part number?"""
    f, m = norm(fpname), norm(mfr)
    if not m or len(m) < 5:
        return False
    return m in f or f.endswith(m) or (len(m) > 8 and m[:8] in f)


def dims_agree(jl_desc, fpname):
    """SMD3225-4P and L3.2-W2.5 are the same statement in two notations."""
    m = re.search(r"SMD(\d{2})(\d{2})", (jl_desc or "").upper())
    d = re.search(r"L([\d.]+)-W([\d.]+)", fpname or "")
    if not (m and d):
        return None
    want = (int(m.group(1)) / 10.0, int(m.group(2)) / 10.0)
    got = (float(d.group(1)), float(d.group(2)))
    return abs(want[0] - got[0]) < 0.15 and abs(want[1] - got[1]) < 0.15


def family_of(text):
    """The package family token in a JLC description or a footprint name."""
    if not text:
        return None
    for fam in ("VQFN-12", "LQFP-100", "LGA-14", "LGA-12", "QFN-8", "COB-28", "SOIC-8",
                "SOT-23-6", "SOT-23-5", "SOT-25-5", "SOT-23-3", "SOT-23",
                "SMD3225-4P", "TQFN-28-EP", "TQFN-28", "SOP-8", "DSBGA-6", "SOD-123",
                "SOIC"):
        if fam in text.upper().replace("_", "-"):
            return fam
    return None


def measured_pitch(fp):
    """Smallest centre-to-centre distance between two electrical pads, in mm."""
    pos = [(p.GetPosition().x / 1e6, p.GetPosition().y / 1e6)
           for p in fp.Pads() if p.GetNumber().strip()]
    best = None
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d = ((pos[i][0] - pos[j][0]) ** 2 + (pos[i][1] - pos[j][1]) ** 2) ** 0.5
            if d > 0.01 and (best is None or d < best):
                best = d
    return best


def electrical_pads(fp):
    """Pads that take solder."""
    return [p for p in fp.Pads() if p.GetNumber().strip()]


def run_footprints():
    has_mirror = bool(glob.glob(os.path.join(DATA, "*.jsonl.gz")))
    snap = load_snapshot()
    if not has_mirror and not snap:
        print(f"no jlcparts mirror in {DATA} and no snapshot at {SNAPSHOT} - there is no "
              f"outside authority to check against. Run `python3 tools/check_order.py stock "
              f"--fetch` to rebuild the snapshot.")
        return 1
    print(f"authority: JLCPCB live snapshot {SNAPSHOT}" +
          ("  + jlcparts mirror (joint counts)" if has_mirror else ""))

    board = pcbnew.LoadBoard(BOARD)
    on_board = {fp.GetReference(): fp for fp in board.GetFootprints()}
    #keyed by REF, not by LCSC
    want = {r: c[3] for r, c in design.COMPONENTS.items() if c[3] and r in on_board}
    codes = set(want.values())

    recs, descs = {}, {}
    for f in glob.glob(os.path.join(DATA, "*.jsonl.gz")):
        try:
            with gzip.open(f, "rt") as fh:
                idx = json.loads(fh.readline())
                for line in fh:
                    for c in codes:
                        if c in line:
                            r = json.loads(line)
                            if r[idx["lcsc"]] == c:
                                recs[c] = (r[idx["mfr"]], r[idx["joints"]])
                                descs[c] = r[idx["description"]]
        except Exception:
            pass

    fails, notes, ok = [], [], 0
    print(f"{'ref':6} {'LCSC':11} {'pads':>5} {'mech':>5} {'elec':>5} {'JLC':>5}  part")
    for ref, lcsc in sorted(want.items()):
        fp = on_board[ref]
        allp = list(fp.Pads())
        elec = electrical_pads(fp)
        mech = len(allp) - len(elec)
        rec = recs.get(lcsc)
        if not rec:
            #no mirror row: the live snapshot is the authority
            sn = snap.get(lcsc)
            if sn:
                spec_pads = pads_from_spec(sn[1])
                rec = (sn[0], spec_pads)
                descs[lcsc] = sn[1] or ""
            elif lcsc in MIRROR_GAPS:
                notes.append(f"{ref} ({lcsc}): {MIRROR_GAPS[lcsc]}")
                print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                      f"{'(gap)':>5}  -- known gap, verify at jlcpcb.com/partdetail")
                continue
            else:
                notes.append(f"{ref} ({lcsc}): in neither the mirror nor the snapshot - "
                             f"check jlcpcb.com/partdetail/{lcsc} by hand")
                print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                      f"{'?':>5}  -- NO AUTHORITY")
                continue
        mfr, joints = rec
        #a token with no count in it ('SMD') compares nothing
        if joints is None:
            notes.append(f"{ref} ({lcsc}): JLCPCB package string '{descs.get(lcsc)}' "
                         f"states no pin count - pad count UNVERIFIED for this part")
            print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                  f"{'--':>5}  {str(mfr)[:30]}  -- no count in package string")
            continue
        flag = ""
        if joints and lcsc in THERMAL_PAD and len(elec) == joints + 1:
            notes.append(f"{ref} ({lcsc}): {joints} joints + the exposed pad - {THERMAL_PAD[lcsc]}")
            flag = "  (+ exposed pad, datasheet)"
            ok += 1
        elif joints and len(elec) != joints:
            flag = "  <-- MISMATCH: wrong package variant scraps the board"
            fails.append(f"{ref} ({lcsc}, {mfr}): footprint has {len(elec)} electrical "
                         f"pad(s), JLCPCB says the part has {joints} joint(s). "
                         f"Footprint is {fp.GetFPIDAsString()}")
        else:
            ok += 1
        print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
              f"{str(joints):>5}  {str(mfr)[:30]}{flag}")

    #package family
    #pad count catches SOT-23-5 vs SOT-23-6
    print()
    print("=== package family and pitch ===")
    pkg_ok = 0
    for ref, lcsc in sorted(want.items()):
        fp = on_board[ref]
        if len(electrical_pads(fp)) < 3:
            continue                      #a 2-pad passive has no meaningful pitch
        fpname = fp.GetFPIDAsString().split(":")[-1]
        desc = descs.get(lcsc) or ""
        ds = DATASHEET_PACKAGE.get(lcsc)
        if not desc:
            desc = (snap.get(lcsc) or (None, ""))[1] or ""
        jl_fam = family_of(desc)
        fp_fam = family_of(fpname)
        pitch = measured_pitch(fp)
        src = "JLC"
        if ds and not jl_fam:
            jl_fam, src = ds[0], "datasheet"
        #strongest first: is the footprint named after the exact part number?
        mfr = (recs.get(lcsc) or ("", None))[0]
        if not mfr:
            mfr = (snap.get(lcsc) or (None, ""))[0]
        if not mfr and lcsc in DATASHEET_PACKAGE:
            mfr = DATASHEET_PACKAGE[lcsc][0]
        if mpn_matches(fpname, mfr):
            pkg_ok += 1
            print(f"  {ref:5} {fpname[:38]:38} {'part-specific':11} pitch "
                  f"{pitch:.3f} mm  [named for {str(mfr)[:20]}]")
            continue
        if jl_fam and dims_agree(desc, fpname):
            pkg_ok += 1
            print(f"  {ref:5} {fpname[:38]:38} {jl_fam:11} pitch {pitch:.3f} mm  "
                  f"[body dims agree]")
            continue
        if not jl_fam:
            notes.append(f"{ref} ({lcsc}): JLCPCB publishes no package string, the "
                         f"footprint is not named for the part, and there is no "
                         f"DATASHEET_PACKAGE entry - {fpname} is UNVERIFIED")
            print(f"  {ref:5} {fpname[:38]:38} -- no outside package string")
            continue
        if fp_fam != jl_fam and not (fp_fam and jl_fam.startswith(fp_fam)) \
           and not (fp_fam and fp_fam.startswith(jl_fam)):
            fails.append(f"{ref} ({lcsc}): {src} says package '{jl_fam}', footprint is "
                         f"'{fpname}' - different package family")
            print(f"  {ref:5} {fpname[:38]:38} FAMILY MISMATCH: {src} says {jl_fam}")
            continue
        want_p = FAMILY_PITCH.get(jl_fam) or FAMILY_PITCH.get((fp_fam or "")[:6])
        if want_p and pitch and abs(pitch - want_p) > 0.03:
            #SOT-23-3 is the documented exception
            if not (jl_fam.startswith("SOT-23") and abs(pitch - 1.90) < 0.05):
                fails.append(f"{ref} ({lcsc}): {jl_fam} is a {want_p} mm pitch package, "
                             f"footprint measures {pitch:.3f} mm")
                print(f"  {ref:5} {fpname[:38]:38} PITCH {pitch:.3f} vs {want_p} expected")
                continue
        pkg_ok += 1
        print(f"  {ref:5} {fpname[:38]:38} {jl_fam:11} pitch {pitch:.3f} mm  [{src}]")
    print(f"  {pkg_ok} package(s) agree with an outside package string")

    print("-" * 78)
    print(f"{ok} footprint(s) agree with an outside pad count, {len(fails)} mismatch(es), "
          f"{len(notes)} needing a manual look")
    for n in notes:
        print(f"  note {n}")
    for f in fails:
        print(f"  FAIL {f}")
    print("\nWhat this now covers: pad COUNT against JLCPCB's joint count, and package "
          "FAMILY\nand PITCH against an outside string - JLC's own, the datasheet, or the "
          "part number\nthe footprint is named after.\n"
          "\nWhat it still does not cover: individual pad LAND SIZE and the paste "
          "aperture.\nA 0.50 mm-pitch part can have correct pitch and undersized pads. "
          "Two things close\nthat and both are free: JLCPCB's DFM review on upload, and "
          "printing the fab\ndrawing 1:1 on paper and sitting the real parts on it.")
    return 1 if fails else 0


#libraries

"""The vendored JLC library is present, complete, and identical to the board it rebuilds.

Usage: python3 tools/check_board.py libraries
"""

def geometry(fp):
    """[(num, x, y, size, size)] in library coordinates, sorted, to 0.01 mm."""
    out = []
    for p in fp.Pads():
        q = p.GetFPRelativePosition()          #mirrored on a flipped footprint
        y = -q.y if fp.IsFlipped() else q.y
        s = p.GetSize()
        out.append((p.GetNumber(), round(q.x / 1e6, 2), round(y / 1e6, 2) + 0.0,
                    *sorted((round(s.x / 1e6, 2), round(s.y / 1e6, 2)))))
    return sorted(out)


def lib_geometry(info):
    return sorted((p["num"], round(p["x"], 2), round(p["y"], 2) + 0.0,
                   *sorted((round(p["sx"], 2), round(p["sy"], 2)))) for p in info["pads"])


def run_libraries():
    print(f"symbols    : {jlcpaths.SYMBOLS}")
    print(f"footprints : {jlcpaths.FOOTPRINTS}")
    print(f"3d models  : {jlcpaths.MODEL_ROOT}  (NOT vendored - reported only)")
    print()

    fp_refs = collections.defaultdict(list)      #footprint id -> [refs]
    sym_refs = collections.defaultdict(list)     #symbol id -> [refs]
    for ref, v in design.COMPONENTS.items():
        sym, fp = v[0], v[1]
        if fp.startswith("jlc:"):
            fp_refs[fp].append(ref)
        if sym.startswith("jlc_parts:"):
            sym_refs[sym].append(ref)

    fails = []

    #1. complete
    resolved = {}
    for fpid, refs in sorted(fp_refs.items()):
        path = fplib.find(fpid)
        if path is None:
            fails.append(f"{fpid}: referenced by {','.join(sorted(refs))} but not in "
                         f"{os.path.relpath(jlcpaths.FOOTPRINTS)}")
            continue
        resolved[fpid] = path

    syms = symlib.load()
    for sid, refs in sorted(sym_refs.items()):
        name = sid.split(":", 1)[1]
        if name not in syms:
            fails.append(f"{sid}: referenced by {','.join(sorted(refs))} but not in "
                         f"{os.path.basename(jlcpaths.SYMBOLS)}")

    print(f"referenced : {len(fp_refs)} footprint(s), {len(sym_refs)} symbol(s)")
    print(f"resolved   : {len(resolved)} footprint(s), "
          f"{len([s for s in sym_refs if s.split(':', 1)[1] in syms])} symbol(s)")

    #2. identical
    board_pads, board_geom = {}, {}
    if os.path.exists(BOARD):
        bd = pcbnew.LoadBoard(BOARD)
        for f in bd.GetFootprints():
            board_pads[f.GetReference()] = sorted(p.GetNumber() for p in f.Pads())
            board_geom[f.GetReference()] = geometry(f)
    else:
        fails.append(f"{BOARD} not found - cannot compare the library to the board")

    checked = 0
    for fpid, refs in sorted(fp_refs.items()):
        if fpid not in resolved:
            continue
        info = fplib.load(fpid)
        lib_pads = sorted(p["num"] for p in info["pads"])
        for ref in refs:
            if ref not in board_pads:
                fails.append(f"{ref} ({fpid}): in design.py but has no footprint on "
                             f"{BOARD}")
                continue
            checked += 1
            if board_pads[ref] != lib_pads:
                only_lib = sorted(set(lib_pads) - set(board_pads[ref]))
                only_brd = sorted(set(board_pads[ref]) - set(lib_pads))
                detail = []
                if only_lib:
                    detail.append(f"in library only: {only_lib}")
                if only_brd:
                    detail.append(f"on board only: {only_brd}")
                fails.append(f"{ref} ({fpid}): pads differ - "
                             + "; ".join(detail or
                                         [f"same numbers, different order? lib={lib_pads} "
                                          f"board={board_pads[ref]}"]))
            elif board_geom[ref] != lib_geometry(info):
                #same pad numbers is not the same land
                diff = [(b, l) for b, l in zip(board_geom[ref], lib_geometry(info)) if b != l]
                fails.append(f"{ref} ({fpid}): pad geometry differs from the library, first "
                             f"pad board {diff[0][0]} vs library {diff[0][1]} - swap_footprint")
    print(f"compared   : {checked} ref(s) library pads vs board pads (numbers, positions, sizes)")

    wired = 0
    for netname, specs in design.NETS.items():
        for sp in specs:
            if "." not in sp:
                continue
            ref, pin = sp.split(".", 1)
            v = design.COMPONENTS.get(ref)
            if not v or not v[0].startswith("jlc_parts:"):
                continue
            pins = syms.get(v[0].split(":", 1)[1])
            if pins is None:
                continue          #already reported under complete
            wired += 1
            if symlib.resolve(pins, pin) is None:
                fails.append(f"{netname}: {sp} is wired, but {v[0]} has no pin {pin!r}")
    print(f"wired pins : {wired} spec(s) resolved against the vendored symbols")

    #4. tidy
    vendored = {f[:-len(".kicad_mod")] for f in os.listdir(jlcpaths.FOOTPRINTS)
                if f.endswith(".kicad_mod")}
    used = {fpid.split(":", 1)[1] for fpid in fp_refs}
    orphans = sorted(vendored - used)
    print(f"vendored   : {len(vendored)} file(s), {len(orphans)} unreferenced")
    for o in orphans:
        fails.append(f"{o}.kicad_mod is vendored but no design.py part uses it")

    #3D models: report only
    have_models = sum(1 for u in used
                      if os.path.exists(os.path.join(jlcpaths.MODEL_ROOT, "packages3d",
                                                     u + ".step")))
    print(f"3d bodies  : {have_models}/{len(used)} present under MODEL_ROOT "
          f"(not required here)")

    print()
    if fails:
        print(f"FAIL - {len(fails)} problem(s) with the vendored library:")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("vendored library is complete, agrees with the board, and nothing is orphaned")
    return 0


CHECKS = {
    "backside": run_backside,
    "connectors": run_connectors,
    "floorplan": run_floorplan,
    "placement": run_placement,
    "power_cut": run_power_cut,
    "silk_owner": run_silk_owner,
    "traces": run_traces,
    "model_alignment": run_model_alignment,
    "cpl": run_cpl,
    "footprints": run_footprints,
    "libraries": run_libraries,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        print(__doc__)
        return 2
    return CHECKS[sys.argv.pop(1)]()


if __name__ == "__main__":
    sys.exit(main())
