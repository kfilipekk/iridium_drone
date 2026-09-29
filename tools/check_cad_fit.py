#!/usr/bin/env python3
"""Geometric fit check on cad/drone.scad - the assembly, not its echo lines."""
import math, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

HERE = os.path.dirname(os.path.abspath(__file__))
CAD  = os.path.join(os.path.dirname(HERE), "cad")
SCAD = os.path.join(CAD, "drone.scad")

#the SCAD module that draws each part design.MOUNTED and design.MOUNTS name
MODULE = {"iridium_patch": "iridium_patch", "gps": "gps", "sawbird": "sawbird", "rx": "rx",
          "elrs_antenna": "elrs_antennas", "xiao": "rec_cam", "lidar": "lidar360",
          "range_down": "belly_sensor"}
#the printed parts that close a mount
LIDS = {"gps_pod": ("antenna_tower", "gps"), "gps_lid": ("gps_pod", "gps"),
        "xiao_lid": ("nose_mount", "xiao"), "rx_cover": ("nose_mount", "rx"),
        "range_lid": ("range_cradle", "range_down")}
MOUNTS = sorted(design.MOUNTS)
PRINTED = MOUNTS + sorted(LIDS)
#parts that belong to the airframe and are held by it
AIRFRAME = ["battery", "esc", "fc", "frame", "motors", "props", "skids", "stack_screws"]

#every part, and every pair of them - the list is generated, not curated
PARTS = sorted(AIRFRAME + PRINTED + [MODULE[k] for k in MODULE])

CLEARANCE = {
    ("esc", "gps"):      (30.0, "GPS at least 30 mm from the ESC (docs/HARDWARE.md)"),
    ("gps", "iridium_patch"): (2.0, "the two patches do not touch"),
    ("elrs_antennas", "frame"): (5.0, "ELRS antennas out of the carbon"),
    ("antenna_tower", "battery"): (3.0, "the battery slides in past the tower"),
    ("battery", "iridium_patch"): (5.0, "the strap passes under the patch deck"),
    ("esc", "fc"):       (0.5, "grommet gap must keep the boards apart"),
    ("battery", "fc"):   (1.0, "battery must not press on the connectors"),
    ("frame", "props"):  (2.0, "prop disc vs arms and plates"),
    ("battery", "props"): (2.0, "prop disc vs battery"),
    ("props", "skids"):  (2.0, "prop disc vs landing gear"),
    ("props", "rec_cam"): (2.0, "prop disc vs the nose recording camera"),
}
#nothing off the board comes within 5 mm of a prop disc
for _n in PRINTED + [MODULE[k] for k in MODULE]:
    CLEARANCE.setdefault(("props", _n), (5.0, "prop disc vs a mounted part"))

#the antennas that need sky, and the elevation below
SKY = {"gps": 15.0, "iridium_patch": 15.0}
#plastic is transparent to them; carbon, metal
SKY_BLOCKERS = [p for p in PARTS if p not in PRINTED]

GROUND_PARTS = {
    "lidar360":     5.0,   #LD06, 33.30 mm tall - the reason SKID drop went 25 -> 40 mm
    "belly_sensor": 5.0,   #downward rangefinder
    "range_lid":    5.0,
    "xiao_lid":     5.0,   #the nose camera hangs under the mid plate
}

#pairs that touch by design
CONTACT_OK = {
    ("frame", "motors"):        "motors bolt to the arms",
    ("motors", "props"):        "props mount on the motor bells",
    ("frame", "skids"):         "skids are sandwiched between motor and arm",
    ("motors", "skids"):        "skids bolt to the motor's 19x19 pattern",
    ("esc", "stack_screws"):    "the M3 bolt passes through the ESC's holes",
    ("fc", "stack_screws"):     "the M3 bolt passes through the board's holes",
    ("frame", "stack_screws"):  "the bolt passes through the plates",
}
for _m, _spec in design.MOUNTS.items():
    CONTACT_OK[("frame", _m)] = "bolts to the frame"
    for _c in _spec["carries"]:
        CONTACT_OK[(_m, MODULE[_c])] = f"{_m} carries it"
for _lid, (_m, _c) in LIDS.items():
    CONTACT_OK[(_lid, _m)] = f"screws to the {_m}"
    CONTACT_OK[(_lid, MODULE[_c])] = "holds it in place"


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
    #'use', not 'include'; by absolute path
    src = f'use <{SCAD}>\n{expr}\n'
    with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False,
                                     dir=os.path.dirname(path)) as f:
        f.write(src); tmp = f.name
    try:
        r = subprocess.run(["openscad", "-o", path, tmp],
                           capture_output=True, text=True, timeout=600)
        if not os.path.exists(path):
            #an empty result writes no file
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
    """Smallest vertex-to-triangle distance, both directions."""
    def verts(t): return {v for tri in t for v in tri}
    best = float("inf")
    for src, dst in ((ta, tb), (tb, ta)):
        #bucket destination triangles so we only test nearby ones
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

def bbox(tris):
    vs = [v for t in tris for v in t]
    return (tuple(min(v[i] for v in vs) for i in range(3)),
            tuple(max(v[i] for v in vs) for i in range(3)))


def box_gap(a, b):
    """Distance between two axis-aligned boxes (0 if they touch or overlap)."""
    d = [max(0.0, a[0][i] - b[1][i], b[0][i] - a[1][i]) for i in range(3)]
    return math.sqrt(sum(x * x for x in d))


def is_closed(tris):
    """Every edge shared by exactly two triangles."""
    from collections import Counter
    edges = Counter()
    for t in tris:
        for i in range(3):
            edges[tuple(sorted((t[i], t[(i + 1) % 3])))] += 1
    return bool(edges) and all(n == 2 for n in edges.values())


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

    #guard against the bug above returning
    seen = {}
    for n, tris in parts.items():
        k = (len(tris), round(volume(tris), 3))
        if k in seen:
            print(f"\nFAIL - '{n}' and '{seen[k]}' render identically ({k[0]} facets, "
                  f"{k[1]} mm^3). Each export is not isolating one part.")
            return 1
        seen[k] = n

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
    #only pairs whose boxes meet can intersect; render those (in parallel)
    box = {n: bbox(t) for n, t in parts.items()}
    near = [(a, b) for a, b, _, _ in PAIRS if box_gap(box[a], box[b]) <= 0.0]
    pair_res = dict(zip(near, render_many([
        (f"intersection() {{ {a}(); {b}(); }}", os.path.join(out, f"{a}-{b}.stl"))
        for a, b in near])))
    for a, b, need, why in PAIRS:
        gap = box_gap(box[a], box[b])
        if gap > 0.0 and gap >= need:
            print(f"  {a:8s} x {b:8s} ok    clear >{gap:7.2f} mm  (need {need:.1f})  {why}")
            continue
        res = pair_res.get((a, b), "empty")
        f = os.path.join(out, f"{a}-{b}.stl")
        if res is False:
            fails.append(f"{a} x {b}: export failed"); continue
        tris = [] if res == "empty" else read_stl(f)
        v = volume(tris)
        if v > 1e-6:
            #report what overlapped and by how much - do not print `why` here
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

    print("\nsky view (nothing but plastic above the elevation mask)")
    for n, mask in SKY.items():
        lo, hi = box[n]
        c = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2])     #top face, the phase centre
        worst = (-90.0, None)
        for b in SKY_BLOCKERS:
            if b == n:
                continue
            for tri in parts[b]:
                for v in tri:
                    d = math.hypot(v[0] - c[0], v[1] - c[1])
                    e = math.degrees(math.atan2(v[2] - c[2], d))
                    if e > worst[0]:
                        worst = (e, b)
        ok = worst[0] < mask
        print(f"  {n:14s} highest obstruction {worst[0]:6.1f} deg ({worst[1]})  "
              f"(mask {mask:.0f})  {'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{n}: {worst[1]} rises {worst[0]:.1f} deg above it, inside the "
                         f"{mask:.0f} deg mask")

    print("\nmounts: every part off the board on a printed mount, held by screws")
    import fasteners
    derived = {r["where"] for r in fasteners.ROWS}
    carried = {c for m in design.MOUNTS.values() for c in m["carries"]}
    for c in sorted(set(MODULE) - carried):
        fails.append(f"{c} is modelled but no mount carries it")
    for m, spec in sorted(design.MOUNTS.items()):
        missing = [j["where"] for j in spec["joints"] if j["where"] not in derived]
        ok = spec["joints"] and not missing
        print(f"  {m:14s} carries {', '.join(spec['carries']):32s} {len(spec['joints'])} "
              f"joint(s)  {'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{m}: joints not derived by tools/fasteners.py: {missing or 'none'}")
    #and the buy list sells every screw and insert those joints use
    sold = open(os.path.join(os.path.dirname(HERE), "docs", "PARTS.csv")).read()
    ours = {j["where"] for m in design.MOUNTS.values() for j in m["joints"]}
    need = {f"M{r['dia']:g}x{r['L']}" for r in fasteners.ROWS if r["where"] in ours}
    need |= {f"{k.rstrip('s')} x {v['L']:g}" for k, v in design.INSERTS.items()}
    unsold = sorted(n for n in need if n not in sold)
    print(f"  docs/PARTS.csv sells {len(need) - len(unsold)} of the {len(need)} screw and insert "
          f"sizes the mounts use  {'ok' if not unsold else 'FAIL'}")
    if unsold:
        fails.append(f"docs/PARTS.csv does not sell {', '.join(unsold)} (tools/fasteners.py)")

    print(f"\nprinted parts, laid out for printing ({design.PRINTER['name']}, "
          f"{design.PRINTER['x']:.0f} x {design.PRINTER['y']:.0f} x {design.PRINTER['z']:.0f})")
    res = render_many([(f"print_{n}();", os.path.join(out, f"print_{n}.stl"))
                       for n in PRINTED])
    for n, r in zip(PRINTED, res):
        if r is not True:
            fails.append(f"print_{n}: export failed"); continue
        tris = read_stl(os.path.join(out, f"print_{n}.stl"))
        lo, hi = bbox(tris)
        size = [hi[i] - lo[i] for i in range(3)]
        fits = all(sz <= lim for sz, lim in zip(sorted(size[:2]) + [size[2]],
                   sorted([design.PRINTER["x"], design.PRINTER["y"]]) + [design.PRINTER["z"]]))
        flat, closed = abs(lo[2]) < 1e-3, is_closed(tris)
        ok = fits and flat and closed
        print(f"  {n:14s} {size[0]:6.1f} x {size[1]:6.1f} x {size[2]:6.1f} mm  "
              f"{'on the bed' if flat else 'OFF THE BED'}  {'closed' if closed else 'OPEN'}  "
              f"{'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"print_{n}: " + ", ".join(w for w, bad in (
                ("does not fit the printer", not fits), ("not on the bed", not flat),
                ("not a closed solid", not closed)) if bad))

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
