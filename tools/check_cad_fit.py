#!/usr/bin/env python3
"""Geometric fit check on cad/drone.scad - the assembly, not its ECHO lines.

WHY THIS EXISTS. cad/drone.scad ends with five echo() calls that print clearances.
Every one of them is arithmetic the file does on its own variables: it prints
"clearance above FC to top plate = 7.7" because someone wrote that subtraction,
not because anything looked at where the solids actually are. That is the defect
this project keeps finding - a check measuring something ADJACENT to the property
that matters. If a part were placed at the wrong z, or a connector overhung an
edge, or two plates overlapped, every echo would still print exactly the same
number.

So this asks the geometry instead. Each part is exported on its own, then for
every pair that must not touch we compute:

  * INTERSECTION VOLUME, via OpenSCAD intersection() -> STL -> signed-tetrahedron
    sum. Not facet count: an intersection of two coincident FACES produces facets
    but encloses no volume, and that is contact by design (a board bolted flat to
    a plate), not interference. Volume is the property; facet count is adjacent.

  * MINIMUM SEPARATION, as the smallest vertex-to-triangle distance between the
    two meshes. This is a LOWER bound sampled at vertices - it can only report a
    distance that exists, but a true minimum lying mid-face between two vertices
    is not sampled. With the tessellation here that error is bounded by the facet
    size, and every clearance below is checked against a limit with more margin
    than that. It is a screen for gross error, not a certificate.

Run: python3 tools/check_cad_fit.py
"""
import math, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

HERE = os.path.dirname(os.path.abspath(__file__))
CAD  = os.path.join(os.path.dirname(HERE), "cad")
SCAD = os.path.join(CAD, "drone.scad")

# EVERY PART, and EVERY PAIR of them - the list is generated, not curated.
#
# This began as thirteen hand-picked pairs, and a coverage audit found the obvious
# problem with that: `stack_screws` and `motors` appeared in no pair at all, and
# sixteen combinations of the parts that WERE listed went untested. A curated pair
# list cannot fail for a part nobody thought to list, which makes it the same defect
# this file exists to catch. So the pairs are now itertools.combinations of PARTS.
#
# Adjacency is normal in an assembly - a board bolted to a plate touches it - so the
# default requirement is simply "shares no volume". CLEARANCE holds the pairs that
# need real air between them, with the reason.
# "pi" is NOT in this list, deliberately. The Radxa Zero 3W is deferred and not
# fitted (design.PI), and testing a part that is not on the aircraft would leave a
# permanent failure here - which is how a check stops being read. The reason it is
# deferred is geometric, and the numbers it used to be argued from were the PLACEHOLDER
# ones: "the top plate is 50 mm wide, the battery takes 47 of it, and the Radxa needs 30
# more". The real top plate is 42.50 x 160.26 mm (design.PLATES, flattened from the
# manufacturer DXF), so the battery does not merely fill its width - it OVERHANGS by
# 2.25 mm a side. The conclusion survives and gets stronger; the arithmetic behind it was
# fiction. What the real plate does offer is LENGTH: 160.26 mm against a 138 mm battery
# leaves 22.26 mm - the same free strip the upward ToF claims in docs/SENSORS.md, so the
# Radxa and that sensor are competing for one space. Put "pi" back in this list the
# moment a mounting position is chosen, and it will be checked.
# "camera" (the deferred OV9281 flow camera) is NOT here for the same reason "pi" is not:
# it is not fitted, and it wants the SAME belly slot as the downward rangefinder that is.
# Modelling both reported 2299 mm^3 of overlap - which was the correct answer, not a bug.
# There is one position under the bottom plate with a view of the ground. Put "camera"
# back only when it DISPLACES belly_sensor, and the check will confirm the swap.
PARTS = ["battery", "belly_sensor", "esc", "fc", "frame", "lidar360", "motors", "props",
         "rec_cam", "skids", "stack_screws"]

CLEARANCE = {
    ("esc", "fc"):       (0.5, "grommet gap must keep the boards apart"),
    ("battery", "fc"):   (1.0, "battery must not press on the connectors"),
    ("frame", "props"):  (2.0, "prop disc vs arms and plates"),
    ("battery", "props"): (2.0, "prop disc vs battery"),
    # ("camera","props") and ("pi","props") USED TO LIVE HERE and never ran once:
    # pairs() iterates PARTS, and neither "camera" nor "pi" is in it. Two of eight rules
    # were dead, nothing said so, and a dead rule reads as coverage. If either part is
    # ever added to PARTS, add its rule back at the same time - the pair would otherwise
    # fall through to the default "shares no volume", which is NOT what a spinning prop
    # needs. Kept as a comment rather than deleted so the requirement is not lost.
    ("props", "skids"):  (2.0, "prop disc vs landing gear"),
    ("props", "rec_cam"): (2.0, "prop disc vs the nose recording camera"),
    # NOTE: there is deliberately NO ("belly_sensor", "skids") rule here any more.
    # It used to read "the belly sensor must clear the skid contact line or a landing
    # crushes it" with a 2.0 mm limit - and it could not detect that failure. The skids
    # stand at the MOTORS, 160 mm out; the belly parts sit at the centre. Min separation
    # between the two solids was ~114 mm and would stay large however far below the
    # ground plane a belly part hung. A pairwise test cannot answer a ground-clearance
    # question, because THE GROUND IS NOT A PART. See GROUND_PARTS below.
}

# Parts that hang below the plates and must stay ABOVE the skid contact plane, with the
# clearance each needs. This replaces a pairwise rule that named ground clearance but
# measured lateral distance to the skids and so could never fail.
#
# 5.0 mm rather than the old 2.0: TPU landing gear deflects several millimetres under a
# firm arrival, and the part absorbing that deflection would be the sensor.
GROUND_PARTS = {
    # 2026-09-05, SETTLED: the requirement stays 5.0 mm and the measured margin is
    # 10.2 mm (drop 40 + pad 3.5 = 43.5 mm depth vs the LD06's 33.30 mm). The earlier
    # 15.0 mm figure predates the drop change and was never derived - it would demand
    # >15 mm of TPU skid deflection, which is a crash, not a landing. Physical fact
    # that decides the question: carried upside-down (PRX1_ORIENT 1), the LD06's
    # rotating turret is the LOWEST part, so this margin protects the most delicate
    # surface the sensor has. Consequence for the printed bracket (design.OFFBOARD
    # 'printed bracket under the bottom plate'): give it a protective skirt that stands
    # proud of the turret, so ground contact - if it ever comes to that - lands on
    # printed TPU, not on the spinning head. Grip the BODY below the optical window,
    # whose height above the base is still MEASURE-ON-ARRIVAL (scan_plane_height_mm).
    "lidar360":     5.0,   # LD06, 33.30 mm tall - the reason SKID drop went 25 -> 40 mm
    "belly_sensor": 5.0,   # downward rangefinder
}

# Pairs that touch BY DESIGN, where zero clearance is the correct answer and the
# check is only that they do not overlap. Listed so the intent is explicit.
CONTACT_OK = {
    ("frame", "motors"):        "motors bolt to the arms",
    ("motors", "props"):        "props mount on the motor bells",
    ("frame", "skids"):         "skids are sandwiched between motor and arm",
    ("motors", "skids"):        "skids bolt to the motor's 19x19 pattern",
    ("esc", "stack_screws"):    "the M3 bolt passes through the ESC's holes",
    ("fc", "stack_screws"):     "the M3 bolt passes through the board's holes",
    ("frame", "stack_screws"):  "the bolt passes through the plates",
    # NOT a contact pair, and the label used to imply it was. This reads ~36 mm of
    # air because THE BRACKET IS NOT MODELLED - it is a part you print, and until it
    # exists the camera floats in front of the nose. So this pair proves the camera
    # does not foul the frame; it proves nothing about how it attaches.
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
    # 'use', NOT 'include'. include runs the file's top-level statements too, so every
    # single-part export came back as the ENTIRE assembly - seven parts reported an
    # identical 247949.4 mm^3 before this was caught. 'use' imports the modules only.
    src = f'use <{SCAD}>\n{expr}\n'
    with tempfile.NamedTemporaryFile("w", suffix=".scad", delete=False, dir=CAD) as f:
        f.write(src); tmp = f.name
    try:
        r = subprocess.run(["openscad", "-o", path, tmp],
                           capture_output=True, text=True, timeout=600)
        if not os.path.exists(path):
            # An EMPTY result writes no file. For an intersection that is the PASS
            # condition, not an error - OpenSCAD says so on stderr and exits 0. This
            # was scored as "export failed" at first, which turned ten clean pairs
            # into ten failures and buried the three real ones.
            if "top level object is empty" in r.stderr:
                return "empty"
            print(r.stderr[-2000:]); return False
        return True
    finally:
        os.unlink(tmp)

def read_stl(path):
    """ASCII or binary STL -> list of (v0,v1,v2)."""
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
    for n in names:
        f = os.path.join(out, n + ".stl")
        if not render(f"{n}();", f):
            print(f"  {n:10s} FAILED to export"); return 1
        parts[n] = read_stl(f)
        print(f"  {n:10s} {len(parts[n]):6d} facets  vol {volume(parts[n]):10.1f} mm^3")

    # Guard against the bug above returning: if two different parts render to the same
    # facet count AND the same volume, they are not different parts.
    seen = {}
    for n, tris in parts.items():
        k = (len(tris), round(volume(tris), 3))
        if k in seen:
            print(f"\nFAIL - '{n}' and '{seen[k]}' render identically ({k[0]} facets, "
                  f"{k[1]} mm^3). Each export is not isolating one part.")
            return 1
        seen[k] = n

    # ---------------------------------------------------------------------
    # GROUND CLEARANCE. Not a pairwise test - the ground is not a part, so no
    # amount of part-vs-part checking can express "this hangs below the skids".
    # The skid contact plane is at z = -(cam_drop + skid_t) relative to the arm
    # underside, which is the datum drone.scad draws from.
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
    for a, b, need, why in PAIRS:
        f = os.path.join(out, f"{a}-{b}.stl")
        res = render(f"intersection() {{ {a}(); {b}(); }}", f)
        if res is False:
            fails.append(f"{a} x {b}: export failed"); continue
        tris = [] if res == "empty" else read_stl(f)
        v = volume(tris)
        if v > 1e-6:
            # Report WHAT overlapped and by how much - do NOT print `why` here. `why`
            # is the reason the pair is *expected* to touch, and printing it beside a
            # failure reads as an explanation of the overlap. It cost real time once:
            # "the bolt passes through the plates" sent me to fix the plates, when the
            # 132.51 mm^3 was the corner posts (4 x pi/4 x 3^2 x 4.7 = 132.9, against
            # 127.2 for the plates). The volume is the evidence; the label is not.
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
