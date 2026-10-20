#!/usr/bin/env python3
"""Layout and fabrication checks on the routed board.

Usage:  python3 tools/check_board.py CHECK [options]

Checks:
  connectors         Every connector's opening must face off the board, with room for the plug.
  floorplan          Every perimeter port sits on its edge, mates, and leaves room for its neighbours.
  placement          Gate 1: is the placement electrically correct, before any routing time is spent?
  traces             Signal-integrity review of the routed copper: length, layer changes, and pair matching.

The checks any board needs (backside, silk_owner, model_alignment, cpl, footprints, libraries)
are kicad-tools' check.py, and whether the copper carries each rail's current is its irdrop.py check.
"""
import heapq, json, math, os, re, sys
import cables, design, pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOARD = (sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv
         else os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb"))

T = pcbnew.ToMM


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

    print("\n=== reference plane under the tuner's clock and the antenna line ===")
    for n, need in REFERENCED.items():
        frac = over_ground(board, n)
        bad = frac is not None and frac < need
        if bad:
            warn += 1
        print(f"  {n:12} " + ("(not routed)" if frac is None else
              f"{frac*100:5.1f}% over ground on the adjacent layer (need {need*100:.0f}%)")
              + ("  <-- RETURNS THROUGH ANOTHER NET" if bad else ""))

    print(f"\n{warn} item(s) over their stated limit")
    return 1 if warn else 0


#a clock whose return path runs in a supply plane carries that plane's noise, and the
#antenna line is only 50 ohm over ground; J12's centre pin needs its own clearance in In1
REFERENCED = {"TUNER_REF": 0.9, "TUNER_XTAL": 0.9, "ANT_IN": 0.85, "RFIN": 0.95}


def over_ground(board, net, step=0.05):
    """Share of a net's track length lying over GND fill on the layer next to it."""
    cu = list(board.GetEnabledLayers().CuStack())
    fills = {}
    for z in board.Zones():
        if z.GetNetname() != "GND":
            continue
        for lid in z.GetLayerSet().Seq():
            if z.HasFilledPolysForLayer(lid):
                fills.setdefault(lid, []).append(z.GetFilledPolysList(lid))
    #the planes are cleared round the net's own vias: a layer change is not a return path
    own = [v.GetPosition() for v in board.GetTracks()
           if v.Type() == pcbnew.PCB_VIA_T and v.GetNetname() == net]
    tot = hit = 0.0
    for t in board.GetTracks():
        if t.GetNetname() != net or t.Type() == pcbnew.PCB_VIA_T:
            continue
        i = cu.index(t.GetLayer())
        near = [cu[j] for j in (i - 1, i + 1) if 0 <= j < len(cu)]
        a, e = t.GetStart(), t.GetEnd()
        n = max(1, int(traces_TOMM((e - a).EuclideanNorm()) / step))
        for k in range(n):
            q = pcbnew.VECTOR2I(int(a.x + (e.x - a.x) * (k + .5) / n), int(a.y + (e.y - a.y) * (k + .5) / n))
            if any(traces_TOMM((q - v).EuclideanNorm()) < 0.6 for v in own):
                continue
            tot += 1
            if any(f.Contains(q) for lid in near for f in fills.get(lid, [])):
                hit += 1
    return hit / tot if tot else None


CHECKS = {
    "connectors": run_connectors,
    "floorplan": run_floorplan,
    "placement": run_placement,
    "traces": run_traces,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        print(__doc__)
        return 2
    return CHECKS[sys.argv.pop(1)]()


if __name__ == "__main__":
    sys.exit(main())
