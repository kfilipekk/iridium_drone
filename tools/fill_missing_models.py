#!/usr/bin/env python3
"""
Give every footprint a 3D body that actually resolves on this machine.

The board declared models for all 95 passives, so a check that asks "does this footprint
have a model?" answers yes for all of them. Every one of those references points into
${KICAD9_3DMODEL_DIR}, which is unset here, and kicad-packages3d is not installed - so
the files do not exist and KiCad renders nothing, silently. The STEP and GLB exports were
missing every capacitor, resistor, LED, switch and BOTH 10 uH power inductors: L2 and L5,
the 3.0 mm parts that set the bottom-side stack height.

That is this project's recurring bug in a new place, and this tool exists because the
obvious check walked straight into it: "has a model declared" and "has a model that
loads" are different properties, and only the second one puts a body in the export.

Bodies are boxes, sized from each footprint's own F.Fab outline - which is the body
outline for KiCad's standard passive footprints - and design.PART_HEIGHT for the height.
A box is honest about its own precision: it carries outline and height, which is what an
export or a collision view needs, and claims nothing more.

Footprints whose height is not in design.PART_HEIGHT are REPORTED and skipped, never
given a default.

Usage: python3 tools/fill_missing_models.py [--apply]
"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design, jlcpaths
from make_box_step import build

BOARD = 'NAVCORE-SoOP.kicad_pcb'
# The 3D models are the one part of the JLC library NOT vendored in this repo, so this
# points at MODEL_ROOT (env JLC_LIB) rather than at libraries/ - see jlcpaths.py.
JLC   = jlcpaths.MODEL_ROOT
OUT   = os.path.join(JLC, 'packages3d')


def resolves(path):
    p = path.replace('${JLC_LIB}', JLC)
    p = os.path.expandvars(p)
    return '${' not in p and os.path.exists(p)


def body_extent(fp, board):
    """(w, h, x0, y0) of the footprint body in mm, relative to its origin.

    F.Fab / B.Fab is the body outline on KiCad's standard footprints. Falls back to
    silkscreen, then to the pad span, and says which it used.

    Measured with the footprint temporarily rotated to zero. Graphic items report board
    coordinates, so a 90-degree-rotated instance yields a 0.64 x 1.15 mm box for an 0402
    - and that box would then be handed to all 33 resistors of that type regardless of
    their own rotation, since KiCad applies the footprint's rotation to the model itself.
    """
    ang = fp.GetOrientation()
    fp.SetOrientation(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    try:
        return _extent(fp, board)
    finally:
        fp.SetOrientation(ang)


def _extent(fp, board):
    c = fp.GetPosition()
    for layers, what in (((pcbnew.F_Fab, pcbnew.B_Fab), 'Fab'),
                         ((pcbnew.F_SilkS, pcbnew.B_SilkS), 'silk')):
        xs, ys = [], []
        for it in fp.GraphicalItems():
            if it.GetLayer() in layers and it.GetClass() == 'PCB_SHAPE':
                bb = it.GetBoundingBox()
                xs += [bb.GetLeft(), bb.GetRight()]
                ys += [bb.GetTop(), bb.GetBottom()]
        if xs and (max(xs) - min(xs)) > pcbnew.FromMM(0.3):
            return (pcbnew.ToMM(max(xs) - min(xs)), pcbnew.ToMM(max(ys) - min(ys)),
                    pcbnew.ToMM(min(xs) - c.x), pcbnew.ToMM(max(ys) - c.y), what)
    xs, ys = [], []
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        xs += [bb.GetLeft(), bb.GetRight()]
        ys += [bb.GetTop(), bb.GetBottom()]
    return (pcbnew.ToMM(max(xs) - min(xs)), pcbnew.ToMM(max(ys) - min(ys)),
            pcbnew.ToMM(min(xs) - c.x), pcbnew.ToMM(max(ys) - c.y), 'pads')


def main():
    apply = '--apply' in sys.argv
    board = pcbnew.LoadBoard(BOARD)
    os.makedirs(OUT, exist_ok=True)

    broken = {}
    for fp in board.GetFootprints():
        fid = fp.GetFPIDAsString()
        if fid.startswith('TestPoint') or 'Fiducial' in fid:
            continue
        for m in fp.Models():
            if not resolves(m.m_Filename):
                broken.setdefault(str(fp.GetFPID().GetLibItemName()), []).append(fp)

    print(f"{len(broken)} footprint type(s) with an unresolvable model, "
          f"{sum(len(v) for v in broken.values())} instance(s)\n")

    made, skipped = [], []
    for name, fps in sorted(broken.items()):
        h = design.part_height(name)
        if h is None:
            skipped.append((name, len(fps)))
            continue
        w, d, x0, ymax, src = body_extent(fps[0], board)
        f = os.path.join(OUT, f"{name}.step")
        if apply:
            open(f, 'w').write(build(w, d, h, name))
        made.append((name, w, d, h, x0, ymax, src, len(fps)))
        print(f"  {name:34s} {w:5.2f} x {d:5.2f} x {h:4.2f} mm  "
              f"({src}) x{len(fps)}")

    if skipped:
        print("\n  NO HEIGHT in design.PART_HEIGHT - skipped rather than guessed:")
        for n, c in skipped:
            print(f"    {n}  x{c}")

    if not apply:
        print("\ndry run - pass --apply")
        return 0

    n = 0
    for name, w, d, h, x0, ymax, src, _ in made:
        for fp in broken[name]:
            mods = fp.Models()
            while len(mods):
                mods.pop()
            m = pcbnew.FP_3DMODEL()
            m.m_Filename = "${JLC_LIB}/packages3d/%s.step" % name
            # KiCad model space has Y up; board Y is down. The box spans 0..d in model
            # Y, so its y=0 corner is the board's LOWER edge: offset = -(y_max).
            m.m_Offset = pcbnew.VECTOR3D(x0, -ymax, 0.0)
            m.m_Scale = pcbnew.VECTOR3D(1.0, 1.0, 1.0)
            m.m_Rotation = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
            m.m_Show = True
            mods.push_back(m)
            n += 1
    board.Save(BOARD)
    print(f"\nwrote {len(made)} box model(s), re-pointed {n} footprint(s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
