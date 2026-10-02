#!/usr/bin/env python3
#check that every component's 3D body sits on its own footprint and touches no other part's,
#Usage: python3 tools/check_model_alignment.py [--tol 0.25] [--board PATH]
#JLC_LIB defaults to ../.libraries/jlc.pretty beside the repo.
import json, math, os, struct, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import design
EXPECTED = design.MODEL_EXPECTED
SINK_TOL = 0.15
COLLIDE = 0.05       #mm of overlap on every axis before two bodies are said to collide
EXPECTED_SINK = design.MODEL_EXPECTED_SINK
BOARD = os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb")
T = pcbnew.ToMM


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


#reference -> (min xyz, max xyz) in the GLB world frame
def bodies(glb):
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


#every vertex of the named node's mesh, in the GLB world frame (metres)
def vertices(glb, name):
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


#the footprint's non-plated locating holes: (x, y, radius) in mm
def peg_holes(fp):
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


#Least-squares y = a*x + b
def fit(pairs):
    n = len(pairs)
    sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
    sxx = sum(p[0] ** 2 for p in pairs); sxy = sum(p[0] * p[1] for p in pairs)
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return a, (sy - a * sx) / n


def main():
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
        body = bodies(glb)
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


if __name__ == "__main__":
    sys.exit(main())
