#!/usr/bin/env python3
"""Every connector's opening must face off the board, with room for the plug.

Usage: python3 tools/check_connectors.py [board.kicad_pcb]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = sys.argv[1] if len(sys.argv) > 1 else 'NAVCORE-SoOP.kicad_pcb'
STEP  = 0.10          # mm, ray march
CORRIDOR_MARGIN = 0.5 # mm of slack each side of the connector body
CRITICAL_FRACTION = 0.5


def local_to_board(fp, lx, ly):
    """Footprint-local mm -> board mm, honouring rotation and side."""
    p = fp.GetPosition()
    px, py = p.x/1e6, p.y/1e6
    # A flipped footprint mirrors in local Y under this convention, not X.
    if fp.IsFlipped(): ly = -ly
    a = math.radians(-fp.GetOrientationDegrees())
    return (px + lx*math.cos(a) - ly*math.sin(a),
            py + lx*math.sin(a) + ly*math.cos(a))


def derive_face(fp):
    """Mating face from the footprint itself: opposite the largest pad row."""
    rows = {}
    for pad in fp.Pads():
        p = pad.GetPosition()
        # back out to local coordinates
        a = math.radians(fp.GetOrientationDegrees())
        dx, dy = p.x/1e6 - fp.GetPosition().x/1e6, p.y/1e6 - fp.GetPosition().y/1e6
        ly = dx*math.sin(a) + dy*math.cos(a)
        if fp.IsFlipped(): ly = -ly
        rows.setdefault(round(ly, 2), 0)
        rows[round(ly, 2)] += 1
    if not rows: return None, "no pads"
    back = max(rows, key=lambda k: (rows[k], -abs(k)))
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


def main():
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

        # 1 - declared vs derived
        derived, why = derive_face(fp)
        if derived and tuple(derived) != tuple(declared):
            fails.append(f"{ref}: design.MATING_FACE says {declared} but the footprint "
                         f"says {derived} ({why}) - footprint changed?")

        # mouth = the courtyard face furthest along the mating direction
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
        # walk from the courtyard centre to its face along the mating direction
        half = (abs(vx)*(cr-cl) + abs(vy)*(cb-ct)) / 2
        mx, my = cx + vx*half, cy + vy*half
        width = (abs(vy)*(cr-cl) + abs(vx)*(cb-ct)) / 2 + CORRIDOR_MARGIN

        # 2 - does the mouth point off the board?
        exit_d = None
        d = 0.0
        while d <= 80.0:
            if not inside(mx+vx*d, my+vy*d): exit_d = d; break
            d += STEP
        if exit_d is None:
            fails.append(f"{ref}: mouth at ({mx:.2f},{my:.2f}) points INTO the board - "
                         f"no cable can be plugged in")
            continue

        # 3 - is the plug corridor clear, out to whichever comes first
        reach = min(need, exit_d)
        blockers = {}
        for other in board.GetFootprints():
            if other.GetReference() == ref: continue
            if other.IsFlipped() != fp.IsFlipped(): continue      # other side, irrelevant
            # Test pads and fiducials are bare copper with no body, so a plug passes over them.
            fpid = other.GetFPIDAsString()
            if 'TestPoint' in fpid or 'Fiducial' in fpid: continue
            if other.GetReference().startswith(('TP', 'FID')): continue
            op = other.GetCourtyard(pcbnew.B_CrtYd if other.IsFlipped() else pcbnew.F_CrtYd)
            if not op.OutlineCount(): continue
            ob = op.BBox()
            ol, orr = ob.GetLeft()/1e6, ob.GetRight()/1e6
            ot, obm = ob.GetTop()/1e6,  ob.GetBottom()/1e6
            # Start just in front of the mouth, not at it.
            d = 0.3
            while d <= reach:
                # sample across the corridor width
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

    # -------------------------------------------------------- vertical mating ----
    for ref, spec in sorted(getattr(design, "VERTICAL_MATING", {}).items()):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            fails.append(f"{ref}: not on the board"); continue
        if fp.IsFlipped():
            fails.append(f"{ref}: vertical connector on the BOTTOM face - the plug "
                         f"points down into the ESC")
            continue
        # Horizontal sweep: the coax bend needs `radius` around the connector centre.
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
        # vertical room: standoff - everything below the board top face
        try:
            s = design.required_standoff(board)
            below_board = (design.ESC["pcb"] + design.ESC["parts"] +
                           design.MOUNTING["gap"] +
                           s["bot"] + design.BOARD_T)
            room = s["buy"] - s["below"] - below_board
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

    print()
    for w in warns: print(f"  warn  {w}")
    for f in fails: print(f"  FAIL  {f}")
    print(f"\n{len(fails)} failure(s), {len(warns)} warning(s)")
    sys.stdout.flush()
    os._exit(1 if fails else 0)


main()
