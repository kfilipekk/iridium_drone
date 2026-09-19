#!/usr/bin/env python3
"""Every dimension needed to buy a frame and hardware for this board, measured from the
board file rather than restated from memory.

Usage: python3 tools/dimensions.py [board.kicad_pcb] [--md]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = next((a for a in sys.argv[1:] if not a.startswith('-')), 'NAVCORE-SoOP.kicad_pcb')
MD = '--md' in sys.argv

# Read from design.py, not RESTATED.
PCB_T     = (design.BOARD_T, "[M] design.py stackup")
ESC       = dict(design.ESC)
FRAME_H   = (design.FRAME["inner_h"], design.FRAME["src"].split(";")[0])
PLATE_T   = (design.FRAME["bottom_t"], design.FRAME["src"].split(";")[0])
GAP       = (design.MOUNTING["gap"], design.MOUNTING["src"])
GROMMET_D = (design.MOUNTING["grommet_d"], design.MOUNTING["src"])

# height above the board surface, and how far a mated plug protrudes past the courtyard
CONN = {
 "J1": (3.16, 6.5,  "USB-C",         "[D] TYPE-C 16P 2MD(073); [A] plug overmould"),
 "J2": (2.90, 4.0,  "ESC JST-SH 8P", "[D] JST SH series; [A] plug + wire exit"),
 "J3": (4.40, 4.0,  "GPS JST-GH 6P", "[D] JST GH series; [A] plug + wire exit"),
 "J8": (1.85, 12.0, "microSD",       "[D] TF-01A; [M] a microSD card is 15 mm long"),
}

def h(t):   print(f"\n{'## ' if MD else ''}{t}")
def row(*c):
    if MD: print("| " + " | ".join(str(x) for x in c) + " |")
    else:  print("   " + "  ".join(str(x).ljust(w) for x, w in zip(c, (34, 22, 44))))
def hdr(*c):
    if MD:
        print("| " + " | ".join(c) + " |")
        print("|" + "|".join("---" for _ in c) + "|")
    else:
        row(*c); print("   " + "-"*100)

def main():
    b = pcbnew.LoadBoard(BOARD)

    # ---- outline, exactly -----------------------------------------------------
    xs, ys, radii, holes = [], [], [], []
    for d in b.GetDrawings():
        if d.GetLayerName() != 'Edge.Cuts': continue
        bb = d.GetBoundingBox()
        if d.GetShape() == pcbnew.SHAPE_T_CIRCLE:
            c = d.GetCenter()
            holes.append((c.x/1e6, c.y/1e6, d.GetRadius()/1e6*2))
            continue
        if d.GetShape() == pcbnew.SHAPE_T_ARC:
            radii.append(d.GetRadius()/1e6)
        xs += [bb.GetLeft()/1e6, bb.GetRight()/1e6]
        ys += [bb.GetTop()/1e6, bb.GetBottom()/1e6]
    X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
    L, W = X1-X0, Y1-Y0
    cx, cy = (X0+X1)/2, (Y0+Y1)/2

    print(f"{'# ' if MD else ''}NAVCORE-SoOP — exact dimensions")
    print(f"\nMeasured from `{os.path.basename(BOARD)}`. [M] = measured, exact.")

    h("Board")
    hdr("dimension", "value", "source")
    row("outline", f"{L:.2f} x {W:.2f} mm", "[M]")
    row("thickness", f"{PCB_T[0]:.2f} mm", PCB_T[1])
    row("corner radius", f"{(min(radii) if radii else 0):.2f} mm", "[M]")
    _, _bot_base, _, _br, _ = design.stack_heights(b, skip_dnp=True)
    _, _bot_fpv, _, _fr, _ = design.stack_heights(b, skip_dnp=False)
    _tall = max(c[0] for c in CONN.values())
    row("overall height, board + parts",
        f"{PCB_T[0] + _tall + _bot_base:.2f} mm", f"[M] + [D] part heights, base build")
    if _bot_fpv > _bot_base:
        row("  same, with the FPV buck fitted",
            f"{PCB_T[0] + _tall + _bot_fpv:.2f} mm",
            f"[M] + [D] {_fr} is {_bot_fpv:.2f} mm on the underside")

    h("Mounting")
    hdr("dimension", "value", "source")
    pitch_x = max(x for x, y, d in holes) - min(x for x, y, d in holes)
    pitch_y = max(y for x, y, d in holes) - min(y for x, y, d in holes)
    row("hole pattern", f"{pitch_x:.2f} x {pitch_y:.2f} mm", "[M]")
    row("hole diameter", f"{holes[0][2]:.2f} mm", "[M] M3 + silicone grommet")
    row("screw", "M3", "[D] standard 30x30 stack")
    for i, (hx, hy, hd) in enumerate(sorted(holes), 1):
        row(f"  hole {i}, from board centre",
            f"X {hx-cx:+.2f}  Y {hy-cy:+.2f} mm", "[M]")
    # Nearest copper to a hole centre - pads, not footprint bounding boxes.
    worst = None
    for hx, hy, hd in holes:
        for pd in b.GetPads():
            bb2 = pd.GetBoundingBox()
            d = math.hypot(max(bb2.GetLeft()/1e6-hx, 0, hx-bb2.GetRight()/1e6),
                           max(bb2.GetTop()/1e6-hy, 0, hy-bb2.GetBottom()/1e6))
            if worst is None or d < worst[0]:
                worst = (d, pd.GetParentFootprint().GetReference() + "." + pd.GetPadName())
    row("nearest copper to a hole centre", f"{worst[0]:.2f} mm ({worst[1]})", "[M] pads only")
    for what, rad, note in (("M3 cap head", 2.75, "5.5 mm dia"),
                            ("silicone grommet flange", GROMMET_D[0]/2, "6.0 mm dia"),
                            ("M3 washer", 3.50, "7.0 mm dia")):
        clr = worst[0] - rad
        row(f"  vs {what} ({note})",
            f"{clr:+.2f} mm" + ("" if clr > 0 else "   OVERLAPS - do not use"),
            "[M] + " + ("[D]" if rad == 2.75 else GROMMET_D[1][:3]))

    h("Connectors — position and the space each one needs")
    hdr("connector", "value", "source")
    for ref in sorted(CONN):
        fp = b.FindFootprintByReference(ref)
        if fp is None: continue
        ht, pro, what, src = CONN[ref]
        poly = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        bb2 = poly.BBox()
        l, r = bb2.GetLeft()/1e6, bb2.GetRight()/1e6
        t, bm = bb2.GetTop()/1e6, bb2.GetBottom()/1e6
        fx, fy = design.MATING_FACE[ref]
        if fp.IsFlipped(): fy = -fy
        a = math.radians(-fp.GetOrientationDegrees())
        vx = fx*math.cos(a) - fy*math.sin(a); vy = fx*math.sin(a) + fy*math.cos(a)
        mx = (l+r)/2 + vx*(r-l)/2; my = (t+bm)/2 + vy*(bm-t)/2
        edge = ('left' if vx < -.5 else 'right' if vx > .5 else 'top' if vy < -.5 else 'bottom')
        to_edge = {'left': mx-X0, 'right': X1-mx, 'top': my-Y0, 'bottom': Y1-my}[edge]
        side = 'BOTTOM' if fp.IsFlipped() else 'top'
        row(f"{ref} {what}", f"{r-l:.2f} x {bm-t:.2f} mm footprint, {side} side", "[M]")
        row("  faces", f"{edge} edge, mouth {to_edge:.2f} mm inboard", "[M]")
        row("  body height above the PCB", f"{ht:.2f} mm", src.split(';')[0])
        row("  clear space needed beyond that edge",
            f"{max(pro-to_edge, 0):.1f} mm", src)

    h("What is on each board edge")
    hdr("edge", "value", "source")
    for name, ref in (("top", "J1"), ("left", "J2"), ("bottom", "J3 (GPS) and J8 (microSD)"),
                      ("right", "nothing")):
        row(name, ref, "[M]")

    h("Stack, measured up from the frame's bottom plate")
    hdr("level", "height", "source")
    z = PLATE_T[0]
    row("top of the bottom plate", f"{z:.2f} mm", PLATE_T[1])
    z += design.FRAME["arm_t"]
    row("top of the arms", f"{z:.2f} mm", design.FRAME["src"].split(";")[0])
    z += design.FRAME["medium_t"]
    row("top of the mid plate - the stack starts here", f"{z:.2f} mm",
        design.FRAME["src"].split(";")[0])
    z += ESC["pcb"]; row("top of the ESC's PCB", f"{z:.2f} mm", ESC["src"])
    z += ESC["parts"]; row("top of the ESC's tallest part", f"{z:.2f} mm", ESC["src"])
    z += GAP[0];  row("bottom of this board's tallest bottom part", f"{z:.2f} mm", GAP[1])
    z += _bot_fpv; row("underside of this board's PCB", f"{z:.2f} mm",
                      f"[M] + [D] {_fr} at {_bot_fpv:.2f} mm, the FPV build's underside")
    z += PCB_T[0]; row("top surface of this board", f"{z:.2f} mm", PCB_T[1])
    ztop = z + max(c[0] for c in CONN.values())
    row("top of the tallest part (J3)", f"{ztop:.2f} mm", "[D] JST GH series")
    # The kit's inner height is not the number to build to - standoff length is a
    # purchase. Report both, and say which one governs.
    _sto = design.required_standoff(b)
    # The top plate is where the kit puts it (design.TOP_PLATE_MOUNT): 22 mm front
    # standoffs on the mid plate, 30 mm rear on the bottom plate. No standoff purchase.
    row("frame's inner space over the mid plate (kit 22 mm standoffs)",
        f"{FRAME_H[0]:.2f} mm", FRAME_H[1])
    row("top plate underside above z=0", f"{_sto['top_plate_z']:.2f} mm", _sto["src"])
    row("SPARE under the top plate", f"{_sto['top_plate_z']-ztop:.2f} mm", "[M] derived")

    h("What the frame must provide")
    hdr("requirement", "value", "source")
    # Not "a plate opening".
    row("clear rectangle around the 30.5 mm pattern", f"{L:.2f} x {W:.2f} mm", "[M]")
    row("stack mounting", f"{pitch_x:.2f} x {pitch_y:.2f} mm M3", "[M]")
    row("inner height, at least", f"{ztop:.2f} mm", "[M] + [D]")
    row("clear beyond the TOP edge (USB)", f"{max(CONN['J1'][1]-0.0,0):.1f} mm", "[A] plug")
    row("clear beyond the LEFT edge (ESC)", f"{CONN['J2'][1]:.1f} mm minus 0.40 inboard",
        "[A] plug")
    row("clear below the BOTTOM edge (card)", f"{CONN['J8'][1]:.0f} mm on the bottom side",
        "[M] card length")

    h("Compared with the ESC it stacks on")
    hdr("", "value", "source")
    row("ESC outline", f"{ESC['L']:.2f} x {ESC['W']:.2f} mm", ESC["src"])
    row("this board", f"{L:.2f} x {W:.2f} mm", "[M]")
    dg_b = math.hypot(L, W); dg_e = math.hypot(ESC['L'], ESC['W'])
    row("corner to corner", f"{dg_b:.2f} vs {dg_e:.2f} mm  ->  {dg_b-dg_e:+.2f} mm",
        "[M] + [D]")
    row("extra clearance needed per corner", f"{(dg_b-dg_e)/2:.2f} mm", "[M] derived")
    sys.stdout.flush(); os._exit(0)

main()
