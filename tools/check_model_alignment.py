#!/usr/bin/env python3
"""Check that every component's 3D body sits on its own footprint, measured in the exported
GLB - the thing the 3D viewer and the renders actually draw.

Usage: JLC_LIB=<path/to/jlc.pretty> python3 tools/check_model_alignment.py [--tol 0.25] [--board PATH]
"""
import json, math, os, struct, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import design
EXPECTED = design.MODEL_EXPECTED
SINK_TOL = 0.15
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


def bodies(glb):
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


def main():
    tol = float(sys.argv[sys.argv.index("--tol") + 1]) if "--tol" in sys.argv else 0.25
    board = sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv else BOARD
    jlc = os.environ.get("JLC_LIB")
    if not jlc or not os.path.isdir(os.path.join(jlc, "packages3d")):
        print("SKIP - set JLC_LIB to the jlc.pretty directory holding packages3d/")
        return 0
    with tempfile.TemporaryDirectory() as td:
        glb = os.path.join(td, "board.glb")
        subprocess.run(["kicad-cli", "pcb", "export", "glb", "--output", glb, "-D", f"JLC_LIB={jlc}",
                        "--subst-models", "--force", board], capture_output=True, check=True)
        body = bodies(glb)
    b = pcbnew.LoadBoard(board)
    ref_c = {}
    for fp in b.GetFootprints():
        r = fp.GetReference()
        if r not in body:
            continue
        s = silk_bbox(fp) if r.startswith("J") else None
        box = s or pad_bbox(fp)
        if box:
            ref_c[r] = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    # The GLB is Y-up in metres: its x and z carry the board plane. Fit each axis.
    cen = {r: ((body[r][0][0] + body[r][1][0]) / 2, (body[r][0][2] + body[r][1][2]) / 2) for r in ref_c}
    # Two passes: fit, drop anything more than 1 mm out, refit.
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
    # The GLB is Y-up with the board's underside at 0 and its top at the board thickness.
    thick = T(b.GetDesignSettings().GetBoardThickness())
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
    print(f"{len(ref_c)} bodies measured against their footprints (tolerance {tol} mm)")
    for r, d, dx, dy in bad:
        print(f"  FAIL {r:5s} body is {d:.2f} mm off (dx {dx:+.2f}, dy {dy:+.2f})")
    for r, sink, want in sunk:
        print(f"  FAIL {r:5s} body reaches {sink:.2f} mm into the board (expected {want:.2f}) - "
              "correct the model's z offset")
    if sunk and not bad:
        print(f"\nFAIL - {len(sunk)} body/bodies at the wrong height")
        return 1
    if bad:
        print(f"\nFAIL - {len(bad)} body/bodies misplaced; correct the model offset in the "
              "footprint (libraries/jlc.pretty) and on the board")
        return 1
    print("every body sits on its own footprint, at the right height")
    return 0


if __name__ == "__main__":
    sys.exit(main())
