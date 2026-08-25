#!/usr/bin/env python3
"""Emit a minimal AP214 STEP solid for a rectangular part body.

Usage:
  python3 tools/make_box_step.py OUT.step DX DY DZ [--name NAME]
      DX, DY, DZ in mm. The box spans (0,0,0) to (DX,DY,DZ); KiCad places the origin at
      the footprint origin on the board surface, so DZ is the height above the board.
"""
import sys, datetime

def build(dx, dy, dz, name="BODY"):
    n = [0]
    out = []

    def E(text):
        n[0] += 1
        out.append(f"#{n[0]}={text};")
        return f"#{n[0]}"

    # --- geometry ------------------------------------------------------------------
    # vertex index (ix,iy,iz) -> VERTEX_POINT
    vp, cp = {}, {}
    for ix in (0, 1):
        for iy in (0, 1):
            for iz in (0, 1):
                x, y, z = ix * dx, iy * dy, iz * dz
                p = E(f"CARTESIAN_POINT('',({x:.6f},{y:.6f},{z:.6f}))")
                cp[(ix, iy, iz)] = p
                vp[(ix, iy, iz)] = E(f"VERTEX_POINT('',{p})")

    dirs = {'x': E("DIRECTION('',(1.0,0.0,0.0))"),
            'y': E("DIRECTION('',(0.0,1.0,0.0))"),
            'z': E("DIRECTION('',(0.0,0.0,1.0))")}
    length = {'x': dx, 'y': dy, 'z': dz}

    # 12 edges: every vertex pair differing in exactly one axis
    edges = {}
    for a in sorted(vp):
        for axis, i in (('x', 0), ('y', 1), ('z', 2)):
            if a[i] != 0:
                continue
            b = list(a)
            b[i] = 1
            b = tuple(b)
            vec = E(f"VECTOR('',{dirs[axis]},{length[axis]:.6f})")
            ln = E(f"LINE('',{cp[a]},{vec})")
            edges[(a, b)] = E(f"EDGE_CURVE('',{vp[a]},{vp[b]},{ln},.T.)")

    def oriented(a, b):
        """An ORIENTED_EDGE traversing a->b, reusing the one EDGE_CURVE either way."""
        if (a, b) in edges:
            return E(f"ORIENTED_EDGE('',*,*,{edges[(a, b)]},.T.)")
        return E(f"ORIENTED_EDGE('',*,*,{edges[(b, a)]},.F.)")

    def face(loop_pts, origin, normal):
        oe = [oriented(loop_pts[i], loop_pts[(i + 1) % 4]) for i in range(4)]
        el = E(f"EDGE_LOOP('',({','.join(oe)}))")
        fb = E(f"FACE_OUTER_BOUND('',{el},.T.)")
        o = E(f"CARTESIAN_POINT('',({origin[0]:.6f},{origin[1]:.6f},{origin[2]:.6f}))")
        nd = E(f"DIRECTION('',({normal[0]:.1f},{normal[1]:.1f},{normal[2]:.1f}))")
        # any direction not parallel to the normal works as the plane's reference
        refv = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.5 else (0.0, 1.0, 0.0)
        rd = E(f"DIRECTION('',({refv[0]:.1f},{refv[1]:.1f},{refv[2]:.1f}))")
        ax = E(f"AXIS2_PLACEMENT_3D('',{o},{nd},{rd})")
        pl = E(f"PLANE('',{ax})")
        return E(f"ADVANCED_FACE('',({fb}),{pl},.T.)")

    # Loops wound so the face normal points out of the solid (right-hand rule).
    faces = [
        face([(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)], (0, 0, 0), (-1, 0, 0)),
        face([(1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)], (dx, 0, 0), (1, 0, 0)),
        face([(0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)], (0, 0, 0), (0, -1, 0)),
        face([(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)], (0, dy, 0), (0, 1, 0)),
        face([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], (0, 0, 0), (0, 0, -1)),
        face([(0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1)], (0, 0, dz), (0, 0, 1)),
    ]
    shell = E(f"CLOSED_SHELL('',({','.join(faces)}))")
    brep = E(f"MANIFOLD_SOLID_BREP('{name}',{shell})")

    # --- product / context boilerplate ----------------------------------------------
    o0 = E("CARTESIAN_POINT('',(0.0,0.0,0.0))")
    dz1 = E("DIRECTION('',(0.0,0.0,1.0))")
    dx1 = E("DIRECTION('',(1.0,0.0,0.0))")
    axo = E(f"AXIS2_PLACEMENT_3D('',{o0},{dz1},{dx1})")
    lu = E("(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))")
    au = E("(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.))")
    su = E("(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT())")
    unc = E(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),{lu},'','')")
    ctx = E(f"(GEOMETRIC_REPRESENTATION_CONTEXT(3)"
            f"GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({unc}))"
            f"GLOBAL_UNIT_ASSIGNED_CONTEXT(({lu},{au},{su}))REPRESENTATION_CONTEXT('',''))")
    absr = E(f"ADVANCED_BREP_SHAPE_REPRESENTATION('{name}',({axo},{brep}),{ctx})")

    apc = E("APPLICATION_CONTEXT('automotive design')")
    E(f"APPLICATION_PROTOCOL_DEFINITION('international standard',"
      f"'automotive_design',2000,{apc})")
    pdc = E(f"PRODUCT_DEFINITION_CONTEXT('part definition',{apc},'design')")
    pc = E(f"PRODUCT_CONTEXT('',{apc},'mechanical')")
    prod = E(f"PRODUCT('{name}','{name}','',({pc}))")
    pdf = E(f"PRODUCT_DEFINITION_FORMATION('','',{prod})")
    pd = E(f"PRODUCT_DEFINITION('design','',{pdf},{pdc})")
    pds = E(f"PRODUCT_DEFINITION_SHAPE('','',{pd})")
    E(f"SHAPE_DEFINITION_REPRESENTATION({pds},{absr})")

    ts = datetime.datetime.now().replace(microsecond=0).isoformat()
    head = ("ISO-10303-21;\nHEADER;\n"
            "FILE_DESCRIPTION((''),'2;1');\n"
            f"FILE_NAME('{name}','{ts}',(''),(''),"
            "'tools/make_box_step.py','','');\n"
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\n"
            "ENDSEC;\nDATA;\n")
    return head + "\n".join(out) + "\nENDSEC;\nEND-ISO-10303-21;\n"


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    if len(a) < 4:
        print(__doc__)
        sys.exit(1)
    name = "BODY"
    if '--name' in sys.argv:
        name = sys.argv[sys.argv.index('--name') + 1]
    out, dx, dy, dz = a[0], float(a[1]), float(a[2]), float(a[3])
    open(out, 'w').write(build(dx, dy, dz, name))
    print(f"wrote {out}: {dx} x {dy} x {dz} mm box")
