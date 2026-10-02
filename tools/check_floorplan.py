#!/usr/bin/env python3
"""Every perimeter port sits on its edge, mates, and leaves room for its neighbours.

Usage: python3 tools/check_floorplan.py [board.kicad_pcb]
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import design

BOARD = sys.argv[1] if len(sys.argv) > 1 else "NAVCORE-SoOP.kicad_pcb"
MM = 1e6
LATCH_GAP = 2.0       #mm between latching housings
PLUG_GAP = 0.8        #mm between two friction plugs side by side
POST_GAP = 0.5        #mm from a plug body to a top-plate post
TOL = 0.05            #mm on the front-face position
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


def main():
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
        if abs(face - spec["front"]) > TOL or abs(at - spec["at"]) > TOL:
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


if __name__ == "__main__":
    main()
