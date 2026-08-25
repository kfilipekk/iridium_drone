#!/usr/bin/env python3
"""
Move reference designators off copper, off each other and off the board edge.

DRC's silk classes are warnings, so they never blocked anything and 42 accumulated.
Most are harmless: a footprint's own outline crossing its own pads is normal for
connectors, and the fab clips silk over a mask opening automatically. What is NOT
harmless is a clipped REFERENCE - it prints with pieces missing, and the parts affected
are the ones you most need labelled during hand rework: U8 and U18 (the two bucks),
U5, U10, U3, U6, D3, J8.

So this moves reference fields only. Footprint outlines are left alone - changing those
means editing library footprints, which is a much larger blast radius for a cosmetic
gain, and `silk_over_copper` on a connector's own body outline is expected.

Placement is decided geometrically here rather than by DRC, because a DRC run costs ~30 s
and this tries hundreds of candidate positions. Bounding boxes are used throughout, which
overstates the extent of rotated text - conservative in the right direction. A single DRC
run at the end confirms the result.

Candidates are ranked by distance from the part: a reference designator that has wandered
3 mm away has stopped labelling anything, so the nearest legal position wins.

The work list comes from DRC, not from the geometry test. The test here uses bounding
boxes, which overstate rotated text, so it disagrees with DRC on a handful of labels that
are actually fine - and moving a label DRC is happy with is a regression, not a fix. DRC
decides WHICH labels are broken; the geometry only decides where each one goes.

Usage: python3 tools/tidy_silk.py [--apply]
"""
import os, re, sys, math, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD    = 'NAVCORE-SoOP.kicad_pcb'
CLR      = pcbnew.FromMM(0.12)   # silk-to-copper / silk-to-silk breathing room
EDGE_CLR = pcbnew.FromMM(0.20)   # silk-to-board-edge
MAX_R    = pcbnew.FromMM(4.0)    # beyond this the label no longer identifies the part
STEP     = pcbnew.FromMM(0.25)


def flagged():
    """Refdes of every footprint whose Reference field DRC reports on a silk rule."""
    os.makedirs('/tmp/nav', exist_ok=True)
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--output', '/tmp/nav/silk.rpt',
                    '--severity-all', BOARD], capture_output=True, timeout=900)
    rpt = open('/tmp/nav/silk.rpt').read()
    out, kind = set(), None
    for line in rpt.splitlines():
        m = re.match(r'^\[([a-z_]+)\]', line)
        if m:
            kind = m.group(1)
            continue
        if kind and kind.startswith('silk'):
            m = re.search(r'Reference field of (\S+)', line)
            if m:
                out.add(m.group(1))
    return out


def grow(bb, d):
    b = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
    b.Inflate(d)
    return b


def hits(a, b):
    return a.Intersects(b)


def silk_layer_of(fp):
    return pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS


def collect(board, exclude):
    """Obstacles per silk layer: copper pads on that side, plus every silk graphic.

    Reference fields belonging to `exclude` are left out entirely. Without that, the
    labels being placed chase each other: the first sees the second's old box and moves
    away from it, the second then moves onto the space the first just left, and the pass
    oscillates forever without converging.
    """
    obstacles = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    # A pad is registered against the layers it is ACTUALLY on, not against the side its
    # footprint sits on. Those are different things: J1 is a front-side USB-C connector
    # whose pad 13 also lands on B.Cu, and keying off the footprint's side missed it -
    # which is why U3's bottom-side label kept being placed on exposed copper and DRC
    # kept rejecting a position this tool called legal.
    for fp in board.GetFootprints():
        sl = silk_layer_of(fp)
        for p in fp.Pads():
            if p.IsOnLayer(pcbnew.F_Cu):
                obstacles[pcbnew.F_SilkS].append(p.GetBoundingBox())
            if p.IsOnLayer(pcbnew.B_Cu):
                obstacles[pcbnew.B_SilkS].append(p.GetBoundingBox())
        for it in fp.GraphicalItems():
            if it.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                obstacles[it.GetLayer()].append(it.GetBoundingBox())
        ref = fp.Reference()
        if (ref.IsVisible() and fp.GetReference() not in exclude
                and ref.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)):
            obstacles[ref.GetLayer()].append(ref.GetBoundingBox())
    for it in board.GetDrawings():
        if it.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            obstacles[it.GetLayer()].append(it.GetBoundingBox())
    # Vias are copper on both outer layers and are not tented on this board, so silk
    # over one is clipped exactly as it is over a pad.
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            bb = t.GetBoundingBox()
            obstacles[pcbnew.F_SilkS].append(bb)
            obstacles[pcbnew.B_SilkS].append(bb)
    return obstacles


def edge_boxes(board):
    return [it.GetBoundingBox() for it in board.GetDrawings()
            if it.GetLayer() == pcbnew.Edge_Cuts]


def legal(bb, layer, obstacles, edges):
    g = grow(bb, CLR)
    for ob in obstacles[layer]:
        if hits(g, ob):
            return False
    ge = grow(bb, EDGE_CLR)
    for e in edges:
        if hits(ge, e):
            return False
    return True


def main():
    apply = '--apply' in sys.argv
    work = flagged()
    print(f"DRC flags {len(work)} reference field(s): {', '.join(sorted(work))}\n")
    board = pcbnew.LoadBoard(BOARD)
    obstacles = collect(board, work)
    edges = edge_boxes(board)

    moved, stuck = [], []
    for fp in board.GetFootprints():
        if fp.GetReference() not in work:
            continue
        ref = fp.Reference()
        if not ref.IsVisible():
            continue
        layer = ref.GetLayer()
        if layer not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            continue
        start = ref.GetPosition()
        start_ang = ref.GetTextAngleDegrees()
        best = None
        # Text height is already at the 0.8 mm DRC minimum so it cannot shrink. A 90 deg
        # rotation turns a 2.56 x 1.36 mm box into 1.36 x 2.56 and fits gaps the
        # horizontal one cannot - normal practice on a dense board.
        r = STEP
        while r <= MAX_R and best is None:
            for k in range(16):
                a = 2 * math.pi * k / 16
                dx, dy = int(r * math.cos(a)), int(r * math.sin(a))
                for ang in (start_ang, start_ang + 90.0):
                    ref.SetTextAngleDegrees(ang)
                    ref.SetPosition(pcbnew.VECTOR2I(start.x + dx, start.y + dy))
                    if legal(ref.GetBoundingBox(), layer, obstacles, edges):
                        best = (start.x + dx, start.y + dy, pcbnew.ToMM(r), ang)
                        break
                if best:
                    break
            r += STEP
        if best is None:
            ref.SetPosition(start)
            ref.SetTextAngleDegrees(start_ang)
            stuck.append(fp.GetReference())
        else:
            ref.SetTextAngleDegrees(best[3])
            ref.SetPosition(pcbnew.VECTOR2I(best[0], best[1]))
            # Register where it landed so the next label does not sit on top of it.
            obstacles[layer].append(ref.GetBoundingBox())
            moved.append((fp.GetReference(), best[2], best[3]))

    for r, d, ang in moved:
        rot = "" if abs(ang % 180) < 1 else f", rotated {ang:.0f} deg"
        print(f"  moved {r:6s} {d:.2f} mm{rot}")
    if stuck:
        print(f"\n  no clear position within {pcbnew.ToMM(MAX_R):.1f} mm: "
              f"{', '.join(stuck)}")
    print(f"\n{len(moved)} moved, {len(stuck)} stuck")

    if apply and moved:
        board.Save(BOARD)
        print("saved")
    elif not apply:
        print("dry run - pass --apply")
    return 0


if __name__ == '__main__':
    sys.exit(main())
