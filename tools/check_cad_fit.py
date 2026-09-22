#!/usr/bin/env python3
"""Geometric fit check on cad/drone.scad - the assembly, not its echo lines.

Run: python3 tools/check_cad_fit.py
"""
import math, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

HERE = os.path.dirname(os.path.abspath(__file__))
CAD  = os.path.join(os.path.dirname(HERE), "cad")
SCAD = os.path.join(CAD, "drone.scad")

# Every part, and every pair of them - the list is generated, not curated.
PARTS = ["battery", "belly_sensor", "esc", "fc", "frame", "lidar360", "motors", "props",
         "rec_cam", "skids", "stack_screws"]

CLEARANCE = {
    ("esc", "fc"):       (0.5, "grommet gap must keep the boards apart"),
    ("battery", "fc"):   (1.0, "battery must not press on the connectors"),
    ("frame", "props"):  (2.0, "prop disc vs arms and plates"),
    ("battery", "props"): (2.0, "prop disc vs battery"),
    ("props", "skids"):  (2.0, "prop disc vs landing gear"),
    ("props", "rec_cam"): (2.0, "prop disc vs the nose recording camera"),
}

GROUND_PARTS = {
    "lidar360":     5.0,   # LD06, 33.30 mm tall - the reason SKID drop went 25 -> 40 mm
    "belly_sensor": 5.0,   # downward rangefinder
}

# Pairs that touch by design, where zero clearance is the correct answer and the
# check is only that they do not overlap. Listed so the intent is explicit.
CONTACT_OK = {
    ("frame", "motors"):        "motors bolt to the arms",
    ("motors", "props"):        "props mount on the motor bells",
    ("frame", "skids"):         "skids are sandwiched between motor and arm",
    ("motors", "skids"):        "skids bolt to the motor's 19x19 pattern",
    ("esc", "stack_screws"):    "the M3 bolt passes through the ESC's holes",
    ("fc", "stack_screws"):     "the M3 bolt passes through the board's holes",
    ("frame", "stack_screws"):  "the bolt passes through the plates",
    ("frame", "rec_cam"):       "no bracket modelled - the camera floats here",
    ("frame", "belly_sensor"):  "bolts to a bracket under the bottom plate",
}


def pairs():
    import itertools
    out = []
    for a, b in itertools.combinations(PARTS, 2):
        need, why = CLEARANCE.get((a, b), CLEARANCE.get((b, a), (0.0, None)))
        if why is None:
            why = CONTACT_OK.get((a, b), CONTACT_OK.get((b, a), "must not overlap"))
        out.append((a, b, need, why))
    return out


PAIRS = pairs()


def render(expr, path):
    # 'use', not 'include'.
    src = f'use <{SCAD}>\n{expr}\n'
    with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False, dir=CAD) as f:
        f.write(src); tmp = f.name
    try:
        r = subprocess.run(["openscad", "-o", path, tmp],
                           capture_output=True, text=True, timeout=600)
        if not os.path.exists(path):
            # An empty result writes no file.
            if "top level object is empty" in r.stderr:
                return "empty"
            print(r.stderr[-2000:]); return False
        return True
    finally:
        os.unlink(tmp)

def render_many(jobs):
    """Render concurrently, preserving job order in the result."""
    from concurrent.futures import ThreadPoolExecutor
    n = int(os.environ.get("CADFIT_JOBS", min(8, os.cpu_count() or 4)))
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(lambda j: render(*j), jobs))


def read_stl(path):
    """ascii or binary STL -> list of (v0,v1,v2)."""
    with open(path, "rb") as f:
        head = f.read(5); f.seek(0)
        if head == b"solid":
            txt = f.read().decode("utf8", "replace")
            vs = [tuple(map(float, m.groups())) for m in
                  re.finditer(r"vertex\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)", txt)]
            return [tuple(vs[i:i+3]) for i in range(0, len(vs) - 2, 3)]
        import struct
        f.read(80); (n,) = struct.unpack("<I", f.read(4)); out = []
        for _ in range(n):
            d = struct.unpack("<12fH", f.read(50))
            out.append(((d[3],d[4],d[5]), (d[6],d[7],d[8]), (d[9],d[10],d[11])))
        return out

def volume(tris):
    """Signed tetrahedron sum - the enclosed volume, mm^3."""
    v = 0.0
    for a, b, c in tris:
        v += (a[0]*(b[1]*c[2]-b[2]*c[1])
            - a[1]*(b[0]*c[2]-b[2]*c[0])
            + a[2]*(b[0]*c[1]-b[1]*c[0])) / 6.0
    return abs(v)

def pt_tri(p, t):
    """Distance from point to triangle (Ericson, Real-Time Collision Detection)."""
    a, b, c = t
    ab = [b[i]-a[i] for i in range(3)]; ac = [c[i]-a[i] for i in range(3)]
    ap = [p[i]-a[i] for i in range(3)]
    d1 = sum(ab[i]*ap[i] for i in range(3)); d2 = sum(ac[i]*ap[i] for i in range(3))
    if d1 <= 0 and d2 <= 0: return math.dist(p, a)
    bp = [p[i]-b[i] for i in range(3)]
    d3 = sum(ab[i]*bp[i] for i in range(3)); d4 = sum(ac[i]*bp[i] for i in range(3))
    if d3 >= 0 and d4 <= d3: return math.dist(p, b)
    vc = d1*d4 - d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1/(d1-d3); return math.dist(p, [a[i]+v*ab[i] for i in range(3)])
    cp = [p[i]-c[i] for i in range(3)]
    d5 = sum(ab[i]*cp[i] for i in range(3)); d6 = sum(ac[i]*cp[i] for i in range(3))
    if d6 >= 0 and d5 <= d6: return math.dist(p, c)
    vb = d5*d2 - d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2/(d2-d6); return math.dist(p, [a[i]+w*ac[i] for i in range(3)])
    va = d3*d6 - d5*d4
    if va <= 0 and (d4-d3) >= 0 and (d5-d6) >= 0:
        w = (d4-d3)/((d4-d3)+(d5-d6))
        return math.dist(p, [b[i]+w*(c[i]-b[i]) for i in range(3)])
    den = 1.0/(va+vb+vc); v = vb*den; w = vc*den
    return math.dist(p, [a[i]+ab[i]*v+ac[i]*w for i in range(3)])

def min_sep(ta, tb):
    """Smallest vertex-to-triangle distance, both directions. Grid-bucketed."""
    def verts(t): return {v for tri in t for v in tri}
    best = float("inf")
    for src, dst in ((ta, tb), (tb, ta)):
        # bucket destination triangles so we only test nearby ones
        CELL = 20.0
        grid = {}
        for tri in dst:
            lo = [min(v[i] for v in tri) for i in range(3)]
            hi = [max(v[i] for v in tri) for i in range(3)]
            for gx in range(int(lo[0]//CELL), int(hi[0]//CELL)+1):
                for gy in range(int(lo[1]//CELL), int(hi[1]//CELL)+1):
                    for gz in range(int(lo[2]//CELL), int(hi[2]//CELL)+1):
                        grid.setdefault((gx,gy,gz), []).append(tri)
        for p in verts(src):
            g = (int(p[0]//CELL), int(p[1]//CELL), int(p[2]//CELL))
            cand, r = [], 0
            while not cand and r <= 3:
                for dx in range(-r, r+1):
                    for dy in range(-r, r+1):
                        for dz in range(-r, r+1):
                            cand += grid.get((g[0]+dx, g[1]+dy, g[2]+dz), [])
                r += 1
            for tri in cand or dst:
                d = pt_tri(p, tri)
                if d < best: best = d
    return best

def main():
    if subprocess.run(["which", "openscad"], capture_output=True).returncode:
        print("openscad not installed - cannot check the assembly"); return 1
    out = tempfile.mkdtemp(prefix="cadfit-")
    parts, fails, warns = {}, [], []
    names = sorted({n for p in PAIRS for n in p[:2]})
    print("exporting parts")
    for n, res in zip(names, render_many([(f"{n}();", os.path.join(out, n + ".stl"))
                                          for n in names])):
        if res is False:
            print(f"  {n:10s} FAILED to export"); return 1
        f = os.path.join(out, n + ".stl")
        parts[n] = read_stl(f)
        print(f"  {n:10s} {len(parts[n]):6d} facets  vol {volume(parts[n]):10.1f} mm^3")

    # Guard against the bug above returning: if two different parts render to the same
    # facet count and the same volume, they are not different parts.
    seen = {}
    for n, tris in parts.items():
        k = (len(tris), round(volume(tris), 3))
        if k in seen:
            print(f"\nFAIL - '{n}' and '{seen[k]}' render identically ({k[0]} facets, "
                  f"{k[1]} mm^3). Each export is not isolating one part.")
            return 1
        seen[k] = n

    # ---------------------------------------------------------------------
    # ---------------------------------------------------------------------
    contact_z = -(design.SKID["drop"] + design.SKID["t"])
    print(f"\nground clearance (skid contact plane at z = {contact_z:.2f} mm)")
    for n in GROUND_PARTS:
        if n not in parts:
            continue
        low = min(v[2] for tri in parts[n] for v in tri)
        clear = low - contact_z
        need = GROUND_PARTS[n]
        ok = clear >= need
        print(f"  {n:14s} lowest z {low:8.2f}  clearance {clear:6.2f} mm  "
              f"(need {need:.1f})  {'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{n}: hangs to z={low:.2f}, only {clear:.2f} mm above the skid "
                         f"contact plane (need {need:.1f}) - a landing lands on it")

    print("\npairwise interference")
    # Render every pair first (parallel), then analyse in the original order so the
    # report and its failure list are byte-identical to the serial version.
    pair_res = render_many([
        (f"intersection() {{ {a}(); {b}(); }}", os.path.join(out, f"{a}-{b}.stl"))
        for a, b, _, _ in PAIRS])
    for (a, b, need, why), res in zip(PAIRS, pair_res):
        f = os.path.join(out, f"{a}-{b}.stl")
        if res is False:
            fails.append(f"{a} x {b}: export failed"); continue
        tris = [] if res == "empty" else read_stl(f)
        v = volume(tris)
        if v > 1e-6:
            # Report what overlapped and by how much - do not print `why` here.
            fails.append(f"{a} x {b} INTERFERE by {v:.2f} mm^3 "
                         f"(expected relationship: {why})")
            print(f"  {a:8s} x {b:8s} FAIL  overlap {v:8.2f} mm^3   "
                  f"<- unexplained; expected only: {why}")
            continue
        sep = min_sep(parts[a], parts[b])
        ok = sep >= need - 1e-9
        tag = "ok  " if ok else "FAIL"
        if not ok:
            fails.append(f"{a} x {b}: {sep:.2f} mm apart, needs {need:.1f} - {why}")
        print(f"  {a:8s} x {b:8s} {tag}  clear {sep:8.2f} mm  (need {need:.1f})  {why}")

    print()
    for w in warns: print("  WARN " + w)
    if fails:
        print(f"FAIL - {len(fails)} geometric problem(s)")
        for f_ in fails: print("  - " + f_)
        return 1
    print(f"PASS - {len(PAIRS)} pairs, no interference, all clearances met")
    return 0

if __name__ == "__main__":
    sys.exit(main())
