#!/usr/bin/env python3
"""Checks on a placed and routed board that hold for any project.

Usage:  python3 check.py CHECK [options]

Checks:
  backside         Does anything with a pin through the board land under a part on the other side?
  silk_owner       Does every label on the silkscreen read as its own part's, and can it be read?
  model_alignment  Does every 3D body sit on its own footprint, clear of every other part's?
  cpl              Do the pick-and-place rotations agree with the board's own geometry?
  footprints       Does every footprint's pad count match JLCPCB's joint count for its part?
  libraries        Is the vendored JLC library complete and identical to the board it rebuilds?
  geometry         No acute corners or dangling copper; right angles, jogs and thin power runs listed
"""
import collections, csv, glob, gzip, json, math, os, re, struct, subprocess, sys, tempfile
import pcbnew
from kicadtools import fplib, pcb, project, runs, symlib
from kicadtools.project import design

BOARD = project.board_path()
T = pcbnew.ToMM


#backside

CLEAR = 0.20      #mm between a hole and an opposite-side body


#plan-view box of the part itself: Fab outline, else silk outline
def body_box(fp):
    back = fp.IsFlipped()
    fab = pcbnew.B_Fab if back else pcbnew.F_Fab
    silk = pcbnew.B_SilkS if back else pcbnew.F_SilkS
    box = None
    for layer in (fab, silk):
        for g in fp.GraphicalItems():
            if g.GetLayer() != layer or g.Type() in (pcbnew.PCB_TEXT_T, pcbnew.PCB_FIELD_T):
                continue
            bb = g.GetBoundingBox()
            if box is None:
                box = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
            else:
                box.Merge(bb)
        if box is not None:
            break
    for p in fp.Pads():
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            continue    #its own holes are not its body
        bb = p.GetBoundingBox()
        if box is None:
            box = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
        else:
            box.Merge(bb)
    return box


#usage: python3 check.py backside [--board PATH]
def run_backside():
    b = pcbnew.LoadBoard(BOARD)
    thick = getattr(design, "BOARD_T", None) or T(b.GetDesignSettings().GetBoardThickness())
    sinks = getattr(design, "MODEL_EXPECTED_SINK", {})
    fps = list(b.GetFootprints())
    bodies = {fp.GetReference(): body_box(fp) for fp in fps}
    fails, notes, n_holes = [], [], 0
    for fp in fps:
        for p in fp.Pads():
            if p.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            n_holes += 1
            pb = p.GetBoundingBox()          #the ring: for the courtyard note
            c, d = p.GetPosition(), p.GetDrillSize()
            if p.GetOrientationDegrees() % 180 != 0:
                d = pcbnew.VECTOR2I(d.y, d.x)
            hole = pcbnew.BOX2I(pcbnew.VECTOR2I(c.x - d.x // 2, c.y - d.y // 2), d)
            for o in fps:
                if o is fp or o.IsFlipped() == fp.IsFlipped():
                    continue
                where = f"{fp.GetReference()} pad {p.GetNumber() or '(hole)'} at " \
                        f"({T(p.GetPosition().x):.2f}, {T(p.GetPosition().y):.2f})"
                body = bodies[o.GetReference()]
                #a locating peg that ends inside the board
                sink = sinks.get(fp.GetReference())
                if (p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and sink is not None
                        and sink < thick - CLEAR):
                    for op in o.Pads():
                        g = op.GetBoundingBox()
                        g.Inflate(pcbnew.FromMM(CLEAR))
                        if g.Intersects(hole):
                            fails.append(f"{where} is under {o.GetReference()} pad "
                                         f"{op.GetNumber()} on the other side")
                            break
                    continue
                if body is not None:
                    g = pcbnew.BOX2I(body.GetOrigin(), body.GetSize())
                    g.Inflate(pcbnew.FromMM(CLEAR))
                    if g.Intersects(hole):
                        fails.append(f"{where} is under {o.GetReference()} ({o.GetValue()}) "
                                     f"on the other side")
                        continue
                    if g.Intersects(pb):
                        notes.append(f"{where}: its ring is within {CLEAR} mm of "
                                     f"{o.GetReference()}'s pads (the hole itself is clear)")
                        continue
                crt = o.GetCourtyard(pcbnew.B_CrtYd if o.IsFlipped() else pcbnew.F_CrtYd)
                if crt.OutlineCount() and crt.Collide(pcbnew.SHAPE_RECT(pb)):
                    notes.append(f"{where} is inside {o.GetReference()}'s courtyard margin "
                                 f"(body clear by >= {CLEAR} mm)")
    print(f"{n_holes} through-holes checked against every part on the other side")
    for n in notes:
        print(f"  note {n}")
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} pin(s)/hole(s) land under a part on the other side")
        return 1
    print("no pin or hole lands under a part on the other side")
    return 0


#silk_owner

TEXT_GAP = pcbnew.FromMM(0.40)   #two labels closer than this read as one word
MARGIN = pcbnew.FromMM(0.50)     #nearer its own part than any other, by at least this
HIDE = pcbnew.FromMM(0.10)       #overlap with a body that hides a label, beyond rounding
MIN_H, MIN_W = pcbnew.FromMM(1.0), pcbnew.FromMM(0.15)   #JLCPCB: legible from 1.0 / 0.15
TITLE_GAP = pcbnew.FromMM(3.0)   #a title this near another text reads as one phrase with it
EDGE_GAP = pcbnew.FromMM(0.20)   #silk this near the board edge is trimmed or smudged


def grow(bb, d):
    b = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
    b.Inflate(d)
    return b


#the strokes, not KiCad's padded text box
def text_box(t):
    return t.GetEffectiveTextShape().BBox()


def gap(bx, x, y):
    return math.hypot(max(bx.GetLeft() - x, 0, x - bx.GetRight()),
                      max(bx.GetTop() - y, 0, y - bx.GetBottom()))


def part_bodies(board):
    return {fp.GetReference(): (fp.IsFlipped(), body_box(fp)) for fp in board.GetFootprints()}


#(distance to the nearest other part) - (distance to the owner)
def owner_margin(bods, owner, bottom, x, y):
    own = gap(bods[owner][1], x, y)
    best = None
    for ref, (flip, bx) in bods.items():
        if ref == owner or flip != bottom or bx is None:
            continue
        d = gap(bx, x, y)
        if best is None or d < best[0]:
            best = (d, ref)
    return (best[0] - own, best[1]) if best else (float("inf"), None)


#(owner ref, text item) for everything printed that names a part
def labels(board):
    out = []
    for fp in board.GetFootprints():
        r = fp.Reference()
        if r.IsVisible() and r.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            out.append((fp.GetReference(), r))
        #a pad's function label (silk_labels.py) is text the footprint itself carries
        for g in fp.GraphicalItems():
            if g.Type() == pcbnew.PCB_TEXT_T and g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                out.append((fp.GetReference(), g))
    owner_of = {v: k for k, v in getattr(design, "SILK_NAMES", {}).items()}
    for d in board.GetDrawings():
        if d.Type() == pcbnew.PCB_TEXT_T and d.GetText() in owner_of:
            out.append((owner_of[d.GetText()], d))
    return out


#usage: python3 check.py silk_owner [--board PATH]
def run_silk_owner():
    b = pcbnew.LoadBoard(BOARD)
    bods = part_bodies(b)
    bad = []
    items = labels(b)
    for owner, t in items:
        c = text_box(t).GetCenter()
        bottom = t.GetLayer() == pcbnew.B_SilkS
        name = t.GetText() if t.Type() == pcbnew.PCB_TEXT_T else owner
        m, other = owner_margin(bods, owner, bottom, c.x, c.y)
        if m < MARGIN:
            bad.append(f"{name} (for {owner}) could read as {other}'s: "
                       f"{T(gap(bods[owner][1], c.x, c.y)):.2f} mm from {owner}, "
                       f"{T(gap(bods[other][1], c.x, c.y)):.2f} mm from {other} "
                       f"(needs {T(MARGIN):.2f} mm between)")
        strokes = grow(text_box(t), -HIDE)
        under = sorted(ref for ref, (flip, bx) in bods.items()
                       if flip == bottom and bx is not None and strokes.Intersects(bx))
        if under:
            bad.append(f"{name} (for {owner}) is printed under {', '.join(under)} - "
                       "hidden once assembled")
    #two labels closer than TEXT_GAP read as one word
    boxes = [(t.GetText() if t.Type() == pcbnew.PCB_TEXT_T else o, t.GetLayer(), text_box(t))
             for o, t in items]
    for i, (na, la, ba) in enumerate(boxes):
        for nb, lb, bb in boxes[i + 1:]:
            if la == lb and grow(ba, TEXT_GAP).Intersects(bb):
                bad.append(f"{na} and {nb} are closer than "
                           f"{T(TEXT_GAP):.2f} mm - they read as one word")
    #every printed text, labels or not, has to be printable
    small = []
    texts = [d for d in b.GetDrawings() if d.Type() == pcbnew.PCB_TEXT_T]
    for fp in b.GetFootprints():
        texts += [fp.Reference(), fp.Value()] + [g for g in fp.GraphicalItems()
                                                 if g.Type() == pcbnew.PCB_TEXT_T]
    shown = [t for t in texts
             if t.IsVisible() and t.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
    titles = set(getattr(design, "SILK_TITLE", ()))
    seen = {(t.GetShownText(False), t.GetLayer(), tuple(text_box(t).GetOrigin()))
            for _, t in items}
    for i, a in enumerate(shown):
        for c in shown[i + 1:]:
            if a.GetLayer() != c.GetLayer():
                continue
            ka = (a.GetShownText(False), a.GetLayer(), tuple(text_box(a).GetOrigin()))
            kc = (c.GetShownText(False), c.GetLayer(), tuple(text_box(c).GetOrigin()))
            if ka in seen and kc in seen:
                continue                    #two labels: judged above
            g = TITLE_GAP if titles & {a.GetShownText(False), c.GetShownText(False)} \
                else TEXT_GAP
            if grow(text_box(a), g).Intersects(text_box(c)):
                bad.append(f"'{a.GetShownText(False)}' and '{c.GetShownText(False)}' are "
                           f"closer than {T(g):.2f} mm - they read as one")
    eb = b.GetBoardEdgesBoundingBox()
    inner = grow(eb, -EDGE_GAP - pcbnew.FromMM(0.05))   #the edge line's own half-width
    for t in shown:
        bx = text_box(t)
        if not (inner.Contains(bx.GetOrigin()) and inner.Contains(bx.GetEnd())):
            bad.append(f"'{t.GetShownText(False)}' is within {T(EDGE_GAP):.2f} mm of the "
                       "board edge")
    for t in texts:
        if not t.IsVisible() or t.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            continue
        if t.GetTextHeight() < MIN_H - 1000 or t.GetEffectiveTextPenWidth() < MIN_W - 1000:
            small.append(f"'{t.GetShownText(False)}' is {T(t.GetTextHeight()):.2f} mm tall, "
                         f"{T(t.GetEffectiveTextPenWidth()):.2f} mm stroke")
    bad += [f"{x} - under {T(MIN_H):.1f} / {T(MIN_W):.2f} mm prints smudged" for x in small]
    print(f"{len(items)} printed labels checked against every part on their side; "
          f"{len(texts)} texts checked for size")
    for x in bad:
        print(f"  FAIL {x}")
    if bad:
        print(f"\nFAIL - {len(bad)} label problem(s): misattributed, hidden, run together "
              "or too small")
        return 1
    print("every label reads as its own part's by a clear margin, none is hidden or run "
          "together, and every text prints legibly")
    return 0


#model_alignment

#from the project's design.py, if it has them
EXPECTED = getattr(design, "MODEL_EXPECTED", {})
SINK_TOL = 0.15
COLLIDE = 0.05       #mm of overlap on every axis before two bodies are said to collide
EXPECTED_SINK = getattr(design, "MODEL_EXPECTED_SINK", {})
HARDWARE = getattr(design, "FC_HOLE_HARDWARE", None)


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
def glb_bodies(glb):
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


#least-squares y = a*x + b
def fit(pairs):
    n = len(pairs)
    sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
    sxx = sum(p[0] ** 2 for p in pairs); sxy = sum(p[0] * p[1] for p in pairs)
    a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return a, (sy - a * sx) / n


#usage: python3 check.py model_alignment [--tol 0.25] [--board PATH] The 3D models
def run_model_alignment():
    tol = float(project.arg("--tol", 0.25))
    jlc = project.MODELS
    if not os.path.isdir(os.path.join(jlc, "packages3d")):
        #not a skip: a check that passes without looking cannot fail
        print(f"FAIL - no 3D models at {jlc}/packages3d; set JLC_LIB")
        return 1
    b = pcbnew.LoadBoard(BOARD)
    #a part with locating pegs is placed by them: judge it
    pegged = {fp.GetReference(): peg_holes(fp) for fp in b.GetFootprints() if peg_holes(fp)}
    with tempfile.TemporaryDirectory() as td:
        glb = os.path.join(td, "board.glb")
        subprocess.run(["kicad-cli", "pcb", "export", "glb", "--output", glb, "-D", f"JLC_LIB={jlc}",
                        "--subst-models", "--force", BOARD], capture_output=True, check=True)
        body = glb_bodies(glb)
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
    hw = HARDWARE
    reach = ({False: hw["top"][0]["reach_d"] / 2, True: hw["bottom"][0]["reach_d"] / 2}
             if hw else {False: 0.0, True: 0.0})
    stack = [(T(d.GetCenter().x), T(d.GetCenter().y)) for d in b.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts and d.ShowShape() == "Circle"] if hw else []
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


#cpl

CPL = os.path.join(project.FAB, f"CPL-{project.NAME}.csv")
TOL = 12.0        #degrees; footprints place pin 1 on a coarse grid of directions


#the pad that defines orientation - pin 1, or the first pad if unnumbered
def pin1(fp):
    pads = list(fp.Pads())
    for want in ("1", "A1", "A4B9"):
        for p in pads:
            if p.GetNumber() == want:
                return p
    return pads[0] if pads else None


#small silkscreen circles
def silk_dots(fp):
    return [g for g in fp.GraphicalItems()
            if g.GetLayerName() in ("F.Silkscreen", "B.Silkscreen")
            and g.GetShape() == pcbnew.SHAPE_T_CIRCLE and T(g.GetRadius()) <= 0.3]


#a pin-1 dot by the wrong pad does not move the machine
def dot_errors(board):
    dots, errs = 0, []
    for fp in board.GetFootprints():
        p1 = pin1(fp)
        if p1 is None or len(fp.Pads()) < 3:
            continue
        for g in silk_dots(fp):
            dots += 1
            c = g.GetCenter()
            near = min(fp.Pads(), key=lambda p: (p.GetPosition() - c).EuclideanNorm())
            if near.GetNumber() != p1.GetNumber():
                errs.append(f"{fp.GetReference()}: its silkscreen pin-1 dot at "
                            f"({T(c.x):.2f}, {T(c.y):.2f}) is nearest pad "
                            f"{near.GetNumber()}, not pad {p1.GetNumber()}")
    return dots, errs


#a pin-1 dot moved beside the pad farthest from pin 1 must be caught
def cpl_self_test():
    b = pcbnew.LoadBoard(BOARD)
    fp = next(f for f in sorted(b.GetFootprints(), key=lambda f: f.GetReference())
              if len(f.Pads()) >= 3 and pin1(f) is not None and silk_dots(f))
    p1 = pin1(fp)
    far = max(fp.Pads(), key=lambda p: (p.GetPosition() - p1.GetPosition()).EuclideanNorm())
    dot = silk_dots(fp)[0]
    dot.Move(far.GetPosition() - dot.GetCenter())
    _n, errs = dot_errors(b)
    ref = fp.GetReference()
    caught = any(e.startswith(f"{ref}:") for e in errs)
    print(f"  {'ok  ' if caught else 'MISS'} {ref}'s pin-1 dot moved to pad {far.GetNumber()}")
    return 0 if caught else 1


#usage: python3 check.py cpl [-v] [--svg DIR] [--self-test] [--board PATH]
def run_cpl():
    if "--self-test" in sys.argv:
        return cpl_self_test()
    verbose = "-v" in sys.argv
    svgdir = project.arg("--svg")

    b = pcbnew.LoadBoard(BOARD)
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
    rows = list(csv.DictReader(open(CPL)))

    by_fp = collections.defaultdict(list)
    errs, notes = [], []
    drawn = []

    for r in rows:
        ref = r["Designator"]
        fp = fps.get(ref)
        if fp is None:
            errs.append(f"{ref} is in the CPL but not on the board")
            continue
        p1 = pin1(fp)
        if p1 is None or pcb.nonpolar(ref):
            continue                       #a part either way round has no pin 1 to agree on
        c, pp = fp.GetPosition(), p1.GetPosition()
        dx, dy = T(pp.x) - T(c.x), T(pp.y) - T(c.y)
        if math.hypot(dx, dy) < 0.05:
            continue                       #centred pin 1 carries no direction
        bottom = r["Layer"].strip().lower() == "bottom"
        if bottom:
            dx = -dx                       #the assembler sees the back mirrored
        rot = float(r["Rotation"])
        a = math.radians(rot)
        cx = dx * math.cos(a) - dy * math.sin(a)
        cy = dx * math.sin(a) + dy * math.cos(a)
        name = fp.GetFPID().GetLibItemName().wx_str()
        by_fp[name].append((ref, math.degrees(math.atan2(cy, cx)) % 360.0,
                            r["Layer"].strip(), rot))
        drawn.append((ref, name, r["Layer"].strip(), rot,
                      T(c.x), T(c.y), T(pp.x), T(pp.y)))

    checked = 0
    for name, items in sorted(by_fp.items()):
        if len(items) < 2:
            continue
        checked += len(items)
        base = items[0][1]
        spread = [(ref, ((ang - base + 180) % 360) - 180, lay, rot)
                  for ref, ang, lay, rot in items]
        bad = [x for x in spread if abs(x[1]) > TOL]
        if bad:
            errs.append(
                f"{name}: parts disagree on where pin 1 is once their CPL rotation is "
                f"undone - " + ", ".join(
                    f"{ref} ({lay}, {rot:.0f} deg) off by {d:+.0f} deg"
                    for ref, d, lay, rot in bad[:4]))
        elif verbose:
            print(f"  ok  {name:48} {len(items)} parts agree")

    dots, wrong = dot_errors(b)
    errs += wrong
    print(f"pin-1 dots         : {dots} checked against the pad they sit beside")
    sides = collections.Counter(r["Layer"].strip() for r in rows)
    rots = collections.Counter(float(r["Rotation"]) for r in rows)
    print(f"CPL placements     : {len(rows)}  ({sides['top']} top, {sides['bottom']} bottom)")
    print("rotations used     : " + ", ".join(f"{k:.0f} deg x{v}"
                                               for k, v in sorted(rots.items())))
    print(f"cross-checked      : {checked} parts across "
          f"{sum(1 for v in by_fp.values() if len(v) > 1)} shared footprints")

    if svgdir:
        os.makedirs(svgdir, exist_ok=True)
        for side in ("top", "bottom"):
            write_svg(os.path.join(svgdir, f"pin1-{side}.svg"),
                      [d for d in drawn if d[2] == side], side, b)
            print(f"wrote {svgdir}/pin1-{side}.svg")

    for it in notes:
        print(f"   {it}")
    if errs:
        print(f"\nERRORS ({len(errs)}):")
        for e in errs:
            print(f"   {e}")
        return 1
    print("\nevery shared footprint agrees on pin 1 - rotations are self-consistent.")
    return 0


#Pin-1 overlay: part outline, a dot at pin 1, and the CPL rotation
def write_svg(path, items, side, board):
    bb = board.GetBoardEdgesBoundingBox()
    X0, Y0, W, H = T(bb.GetX()), T(bb.GetY()), T(bb.GetWidth()), T(bb.GetHeight())
    sc = 16
    flip = (side == "bottom")

    def X(x):
        return ((X0 + W - x) if flip else (x - X0)) * sc

    def Y(y):
        return (y - Y0) * sc

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*sc}" height="{H*sc+30}" '
           f'viewBox="0 0 {W*sc} {H*sc+30}">',
           '<rect width="100%" height="100%" fill="#14181c"/>',
           f'<text x="8" y="{H*sc+20}" fill="#8aa" font-family="monospace" '
           f'font-size="13">{side} side, viewed as the assembler sees it - '
           f'dot = pin 1, number = CPL rotation</text>']
    for ref, name, lay, rot, cx, cy, px, py in items:
        out.append(f'<line x1="{X(cx):.1f}" y1="{Y(cy):.1f}" x2="{X(px):.1f}" '
                   f'y2="{Y(py):.1f}" stroke="#3d5a6c" stroke-width="1"/>')
        out.append(f'<circle cx="{X(px):.1f}" cy="{Y(py):.1f}" r="2.6" fill="#ffb347"/>')
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy):.1f}" fill="#dfe7ea" '
                   f'font-family="monospace" font-size="8" text-anchor="middle">'
                   f'{ref}</text>')
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy)+8:.1f}" fill="#6fd0c0" '
                   f'font-family="monospace" font-size="7" text-anchor="middle">'
                   f'{rot:.0f}</text>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out))


#footprints

DATA = os.environ.get("JLC_DATA") or project.scratch("jlcparts")
SNAPSHOT = os.path.join(project.FAB, "stock-snapshot.json")

#the project's own: parts the mirror lacks, packages from datasheets
MIRROR_GAPS = getattr(design, "MIRROR_GAPS", {})
DATASHEET_PACKAGE = getattr(design, "DATASHEET_PACKAGE", {})
THERMAL_PAD = getattr(design, "THERMAL_PAD", {})

#industry-standard pitches by package family
FAMILY_PITCH = {
    "SOT-23": 0.95, "SOT-25": 0.95, "SOIC": 1.27, "LQFP-100": 0.50,
    "LGA-14": 0.50, "LGA-12": 0.80, "QFN-8": 1.25, "COB-28": 0.65,
    "SOP-8": 1.27, "TQFN-28-EP": 0.50, "DSBGA-6": 0.40,
}

#electrical pad count implied by a JLCPCB package token
PACKAGE_PADS = {
    "SMD3225-4P": 4, "LQFP-100": 100, "LGA-14": 14, "LGA-12": 12, "QFN-8": 8,
    "SOIC-8": 8, "SOIC-8-208MIL": 8, "SOP-8": 8, "TQFN-28-EP": 29, "DSBGA-6": 6,
    "COB-28": 28, "SOT-23": 3, "SOT-23-3": 3, "SOT-23-3L": 3, "SOT-23-5": 5,
    "SOT-23-6": 6, "SOT-25-5": 5, "SOD-123": 2, "DO-214AA": 2, "DO-214AA(SMB)": 2,
    #U8's RNX: 'VQFN-12(2x3)' in JLCPCB's own package string
    "VQFN-12": 12,
    "0402": 2, "0603": 2, "0805": 2, "1206": 2,
}


#pin count JLCPCB's package string implies, or None if it states no count
def pads_from_spec(spec):
    if not spec:
        return None
    up = spec.strip().upper()
    #exact token first
    if up in PACKAGE_PADS:
        return PACKAGE_PADS[up]
    return PACKAGE_PADS.get(re.sub(r"\(.*?\)", "", up).strip())


#{code: (mpn, package_spec)} from the dated JLCPCB snapshot
def load_snapshot():
    try:
        with open(SNAPSHOT) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for code, r in (d.get("lines") or {}).items():
        if r.get("found"):
            out[code] = (r.get("mpn"), r.get("spec"))
    return out


#strip everything that is not alphanumeric, upper-cased
def norm(t):
    return re.sub(r"[^A-Z0-9]", "", (t or "").upper())


#is this footprint named after the exact manufacturer part number?
def mpn_matches(fpname, mfr):
    f, m = norm(fpname), norm(mfr)
    if not m or len(m) < 5:
        return False
    return m in f or f.endswith(m) or (len(m) > 8 and m[:8] in f)


#SMD3225-4P and L3.2-W2.5 are the same statement in two notations
def dims_agree(jl_desc, fpname):
    m = re.search(r"SMD(\d{2})(\d{2})", (jl_desc or "").upper())
    d = re.search(r"L([\d.]+)-W([\d.]+)", fpname or "")
    if not (m and d):
        return None
    want = (int(m.group(1)) / 10.0, int(m.group(2)) / 10.0)
    got = (float(d.group(1)), float(d.group(2)))
    return abs(want[0] - got[0]) < 0.15 and abs(want[1] - got[1]) < 0.15


#the package family token in a JLC description or a footprint name
def family_of(text):
    if not text:
        return None
    for fam in ("VQFN-12", "LQFP-100", "LGA-14", "LGA-12", "QFN-8", "COB-28", "SOIC-8",
                "SOT-23-6", "SOT-23-5", "SOT-25-5", "SOT-23-3", "SOT-23",
                "SMD3225-4P", "TQFN-28-EP", "TQFN-28", "SOP-8", "DSBGA-6", "SOD-123",
                "SOIC"):
        if fam in text.upper().replace("_", "-"):
            return fam
    return None


#smallest centre-to-centre distance between two electrical pads, in mm
def measured_pitch(fp):
    pos = [(p.GetPosition().x / 1e6, p.GetPosition().y / 1e6)
           for p in fp.Pads() if p.GetNumber().strip()]
    best = None
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d = ((pos[i][0] - pos[j][0]) ** 2 + (pos[i][1] - pos[j][1]) ** 2) ** 0.5
            if d > 0.01 and (best is None or d < best):
                best = d
    return best


#pads that take solder
def electrical_pads(fp):
    return [p for p in fp.Pads() if p.GetNumber().strip()]


#usage: python3 check.py footprints (the mirror is $JLC_DATA)
def run_footprints():
    has_mirror = bool(glob.glob(os.path.join(DATA, "*.jsonl.gz")))
    snap = load_snapshot()
    if not has_mirror and not snap:
        print(f"no jlcparts mirror in {DATA} and no snapshot at {SNAPSHOT} - there is no "
              f"outside authority to check against. Run `python3 fab.py stock --fetch` to "
              f"rebuild the snapshot.")
        return 1
    print(f"authority: JLCPCB live snapshot {SNAPSHOT}" +
          ("  + jlcparts mirror (joint counts)" if has_mirror else ""))

    board = pcbnew.LoadBoard(BOARD)
    on_board = {fp.GetReference(): fp for fp in board.GetFootprints()}
    #keyed by REF, not by LCSC
    want = {r: c[3] for r, c in design.COMPONENTS.items() if c[3] and r in on_board}
    codes = set(want.values())

    recs, descs = {}, {}
    for f in glob.glob(os.path.join(DATA, "*.jsonl.gz")):
        try:
            with gzip.open(f, "rt") as fh:
                idx = json.loads(fh.readline())
                for line in fh:
                    for c in codes:
                        if c in line:
                            r = json.loads(line)
                            if r[idx["lcsc"]] == c:
                                recs[c] = (r[idx["mfr"]], r[idx["joints"]])
                                descs[c] = r[idx["description"]]
        except Exception:
            pass

    fails, notes, ok = [], [], 0
    print(f"{'ref':6} {'LCSC':11} {'pads':>5} {'mech':>5} {'elec':>5} {'JLC':>5}  part")
    for ref, lcsc in sorted(want.items()):
        fp = on_board[ref]
        allp = list(fp.Pads())
        elec = electrical_pads(fp)
        mech = len(allp) - len(elec)
        rec = recs.get(lcsc)
        if not rec:
            #no mirror row: the live snapshot is the authority
            sn = snap.get(lcsc)
            if sn:
                spec_pads = pads_from_spec(sn[1])
                rec = (sn[0], spec_pads)
                descs[lcsc] = sn[1] or ""
            elif lcsc in MIRROR_GAPS:
                notes.append(f"{ref} ({lcsc}): {MIRROR_GAPS[lcsc]}")
                print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                      f"{'(gap)':>5}  -- known gap, verify at jlcpcb.com/partdetail")
                continue
            else:
                notes.append(f"{ref} ({lcsc}): in neither the mirror nor the snapshot - "
                             f"check jlcpcb.com/partdetail/{lcsc} by hand")
                print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                      f"{'?':>5}  -- NO AUTHORITY")
                continue
        mfr, joints = rec
        #a token with no count in it ('SMD') compares nothing
        if joints is None:
            notes.append(f"{ref} ({lcsc}): JLCPCB package string '{descs.get(lcsc)}' "
                         f"states no pin count - pad count UNVERIFIED for this part")
            print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
                  f"{'--':>5}  {str(mfr)[:30]}  -- no count in package string")
            continue
        flag = ""
        if joints and lcsc in THERMAL_PAD and len(elec) == joints + 1:
            notes.append(f"{ref} ({lcsc}): {joints} joints + the exposed pad - {THERMAL_PAD[lcsc]}")
            flag = "  (+ exposed pad, datasheet)"
            ok += 1
        elif joints and len(elec) != joints:
            flag = "  <-- MISMATCH: wrong package variant scraps the board"
            fails.append(f"{ref} ({lcsc}, {mfr}): footprint has {len(elec)} electrical "
                         f"pad(s), JLCPCB says the part has {joints} joint(s). "
                         f"Footprint is {fp.GetFPIDAsString()}")
        else:
            ok += 1
        print(f"{ref:6} {lcsc:11} {len(allp):5} {mech:5} {len(elec):5} "
              f"{str(joints):>5}  {str(mfr)[:30]}{flag}")

    #package family
    #pad count catches SOT-23-5 vs SOT-23-6
    print()
    print("=== package family and pitch ===")
    pkg_ok = 0
    for ref, lcsc in sorted(want.items()):
        fp = on_board[ref]
        if len(electrical_pads(fp)) < 3:
            continue                      #a 2-pad passive has no meaningful pitch
        fpname = fp.GetFPIDAsString().split(":")[-1]
        desc = descs.get(lcsc) or ""
        ds = DATASHEET_PACKAGE.get(lcsc)
        if not desc:
            desc = (snap.get(lcsc) or (None, ""))[1] or ""
        jl_fam = family_of(desc)
        fp_fam = family_of(fpname)
        pitch = measured_pitch(fp)
        src = "JLC"
        if ds and not jl_fam:
            jl_fam, src = ds[0], "datasheet"
        #strongest first: is the footprint named after the exact part number?
        mfr = (recs.get(lcsc) or ("", None))[0]
        if not mfr:
            mfr = (snap.get(lcsc) or (None, ""))[0]
        if not mfr and lcsc in DATASHEET_PACKAGE:
            mfr = DATASHEET_PACKAGE[lcsc][0]
        if mpn_matches(fpname, mfr):
            pkg_ok += 1
            print(f"  {ref:5} {fpname[:38]:38} {'part-specific':11} pitch "
                  f"{pitch:.3f} mm  [named for {str(mfr)[:20]}]")
            continue
        if jl_fam and dims_agree(desc, fpname):
            pkg_ok += 1
            print(f"  {ref:5} {fpname[:38]:38} {jl_fam:11} pitch {pitch:.3f} mm  "
                  f"[body dims agree]")
            continue
        if not jl_fam:
            notes.append(f"{ref} ({lcsc}): JLCPCB publishes no package string, the "
                         f"footprint is not named for the part, and there is no "
                         f"DATASHEET_PACKAGE entry - {fpname} is UNVERIFIED")
            print(f"  {ref:5} {fpname[:38]:38} -- no outside package string")
            continue
        if fp_fam != jl_fam and not (fp_fam and jl_fam.startswith(fp_fam)) \
           and not (fp_fam and fp_fam.startswith(jl_fam)):
            fails.append(f"{ref} ({lcsc}): {src} says package '{jl_fam}', footprint is "
                         f"'{fpname}' - different package family")
            print(f"  {ref:5} {fpname[:38]:38} FAMILY MISMATCH: {src} says {jl_fam}")
            continue
        want_p = FAMILY_PITCH.get(jl_fam) or FAMILY_PITCH.get((fp_fam or "")[:6])
        if want_p and pitch and abs(pitch - want_p) > 0.03:
            #SOT-23-3 is the documented exception
            if not (jl_fam.startswith("SOT-23") and abs(pitch - 1.90) < 0.05):
                fails.append(f"{ref} ({lcsc}): {jl_fam} is a {want_p} mm pitch package, "
                             f"footprint measures {pitch:.3f} mm")
                print(f"  {ref:5} {fpname[:38]:38} PITCH {pitch:.3f} vs {want_p} expected")
                continue
        pkg_ok += 1
        print(f"  {ref:5} {fpname[:38]:38} {jl_fam:11} pitch {pitch:.3f} mm  [{src}]")
    print(f"  {pkg_ok} package(s) agree with an outside package string")

    print("-" * 78)
    print(f"{ok} footprint(s) agree with an outside pad count, {len(fails)} mismatch(es), "
          f"{len(notes)} needing a manual look")
    for n in notes:
        print(f"  note {n}")
    for f in fails:
        print(f"  FAIL {f}")
    print("\nWhat this now covers: pad COUNT against JLCPCB's joint count, and package "
          "FAMILY\nand PITCH against an outside string - JLC's own, the datasheet, or the "
          "part number\nthe footprint is named after.\n"
          "\nWhat it still does not cover: individual pad LAND SIZE and the paste "
          "aperture.\nA 0.50 mm-pitch part can have correct pitch and undersized pads. "
          "Two things close\nthat and both are free: JLCPCB's DFM review on upload, and "
          "printing the fab\ndrawing 1:1 on paper and sitting the real parts on it.")
    return 1 if fails else 0


#libraries

#[(num, x, y, size, size)] in library coordinates, sorted, to 0.01 mm
def geometry(fp):
    out = []
    for p in fp.Pads():
        q = p.GetFPRelativePosition()          #mirrored on a flipped footprint
        y = -q.y if fp.IsFlipped() else q.y
        s = p.GetSize()
        out.append((p.GetNumber(), round(q.x / 1e6, 2), round(y / 1e6, 2) + 0.0,
                    *sorted((round(s.x / 1e6, 2), round(s.y / 1e6, 2)))))
    return sorted(out)


def lib_geometry(info):
    return sorted((p["num"], round(p["x"], 2), round(p["y"], 2) + 0.0,
                   *sorted((round(p["sx"], 2), round(p["sy"], 2)))) for p in info["pads"])


#usage: python3 check.py libraries
def run_libraries():
    print(f"symbols    : {project.SYMBOLS}")
    print(f"footprints : {project.FOOTPRINTS}")
    print(f"3d models  : {project.MODELS}  (NOT vendored - reported only)")
    print()

    fp_refs = collections.defaultdict(list)      #footprint id -> [refs]
    sym_refs = collections.defaultdict(list)     #symbol id -> [refs]
    for ref, v in design.COMPONENTS.items():
        sym, fp = v[0], v[1]
        if fp.startswith("jlc:"):
            fp_refs[fp].append(ref)
        if sym.startswith("jlc_parts:"):
            sym_refs[sym].append(ref)

    fails = []

    #1. complete
    resolved = {}
    for fpid, refs in sorted(fp_refs.items()):
        path = fplib.find(fpid)
        if path is None:
            fails.append(f"{fpid}: referenced by {','.join(sorted(refs))} but not in "
                         f"{os.path.relpath(project.FOOTPRINTS)}")
            continue
        resolved[fpid] = path

    syms = symlib.load()
    for sid, refs in sorted(sym_refs.items()):
        name = sid.split(":", 1)[1]
        if name not in syms:
            fails.append(f"{sid}: referenced by {','.join(sorted(refs))} but not in "
                         f"{os.path.basename(project.SYMBOLS)}")

    print(f"referenced : {len(fp_refs)} footprint(s), {len(sym_refs)} symbol(s)")
    print(f"resolved   : {len(resolved)} footprint(s), "
          f"{len([s for s in sym_refs if s.split(':', 1)[1] in syms])} symbol(s)")

    #2. identical
    board_pads, board_geom = {}, {}
    if os.path.exists(BOARD):
        bd = pcbnew.LoadBoard(BOARD)
        for f in bd.GetFootprints():
            board_pads[f.GetReference()] = sorted(p.GetNumber() for p in f.Pads())
            board_geom[f.GetReference()] = geometry(f)
    else:
        fails.append(f"{BOARD} not found - cannot compare the library to the board")

    checked = 0
    for fpid, refs in sorted(fp_refs.items()):
        if fpid not in resolved:
            continue
        info = fplib.load(fpid)
        lib_pads = sorted(p["num"] for p in info["pads"])
        for ref in refs:
            if ref not in board_pads:
                fails.append(f"{ref} ({fpid}): in design.py but has no footprint on "
                             f"{BOARD}")
                continue
            checked += 1
            if board_pads[ref] != lib_pads:
                only_lib = sorted(set(lib_pads) - set(board_pads[ref]))
                only_brd = sorted(set(board_pads[ref]) - set(lib_pads))
                detail = []
                if only_lib:
                    detail.append(f"in library only: {only_lib}")
                if only_brd:
                    detail.append(f"on board only: {only_brd}")
                fails.append(f"{ref} ({fpid}): pads differ - "
                             + "; ".join(detail or
                                         [f"same numbers, different order? lib={lib_pads} "
                                          f"board={board_pads[ref]}"]))
            elif board_geom[ref] != lib_geometry(info):
                #same pad numbers is not the same land
                diff = [(b, l) for b, l in zip(board_geom[ref], lib_geometry(info)) if b != l]
                fails.append(f"{ref} ({fpid}): pad geometry differs from the library, first "
                             f"pad board {diff[0][0]} vs library {diff[0][1]} - swap_footprint")
    print(f"compared   : {checked} ref(s) library pads vs board pads (numbers, positions, sizes)")

    wired = 0
    for netname, specs in design.NETS.items():
        for sp in specs:
            if "." not in sp:
                continue
            ref, pin = sp.split(".", 1)
            v = design.COMPONENTS.get(ref)
            if not v or not v[0].startswith("jlc_parts:"):
                continue
            pins = syms.get(v[0].split(":", 1)[1])
            if pins is None:
                continue          #already reported under complete
            wired += 1
            if symlib.resolve(pins, pin) is None:
                fails.append(f"{netname}: {sp} is wired, but {v[0]} has no pin {pin!r}")
    print(f"wired pins : {wired} spec(s) resolved against the vendored symbols")

    #4. tidy
    vendored = {f[:-len(".kicad_mod")] for f in os.listdir(project.FOOTPRINTS)
                if f.endswith(".kicad_mod")}
    used = {fpid.split(":", 1)[1] for fpid in fp_refs}
    orphans = sorted(vendored - used)
    print(f"vendored   : {len(vendored)} file(s), {len(orphans)} unreferenced")
    for o in orphans:
        fails.append(f"{o}.kicad_mod is vendored but no design.py part uses it")

    #3D models: report only
    have_models = sum(1 for u in used
                      if os.path.exists(os.path.join(project.MODELS, "packages3d",
                                                     u + ".step")))
    print(f"3d bodies  : {have_models}/{len(used)} present under MODEL_ROOT "
          f"(not required here)")

    print()
    if fails:
        print(f"FAIL - {len(fails)} problem(s) with the vendored library:")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("vendored library is complete, agrees with the board, and nothing is orphaned")
    return 0


#geometry

JOG_MAX = 0.6          #mm: a shorter sidestep between two parallel runs is a jog
THIN_POWER = 0.2       #mm: power copper narrower than this, over THIN_RUN in a run
THIN_RUN = 1.0


#(acute, right, jogs) as [(net, layer, x, y)]
def corners(board):
    ends = collections.defaultdict(list)
    tracks = [t for t in board.GetTracks() if t.Type() != pcbnew.PCB_VIA_T]   #one wrapper per track
    for t in tracks:
        a, c = t.GetStart(), t.GetEnd()
        for p, q in ((a, c), (c, a)):
            ends[(t.GetNetCode(), t.GetLayer(), p.x // 1000, p.y // 1000)].append((q.x - p.x, q.y - p.y, t))
    acute, right, jogs = [], [], []
    for (code, lay, x, y), arms in ends.items():
        if len(arms) != 2:
            continue                          #a junction or an end: not a corner
        (x1, y1, t1), (x2, y2, t2) = arms
        l1, l2 = math.hypot(x1, y1), math.hypot(x2, y2)
        if not (l1 and l2):
            continue
        cos = (x1 * x2 + y1 * y2) / (l1 * l2)
        where = (t1.GetNetname(), board.GetLayerName(lay), x / 1000, y / 1000)
        #an arm shorter than the track is wide leaves the corner inside the round end: no notch
        buried = min(l1, l2) < max(t1.GetWidth(), t2.GetWidth())
        if cos > 0.05 and not buried:
            acute.append(where)
        elif abs(cos) <= 0.05 and not buried:
            right.append(where)
    for t in tracks:
        L = T(t.GetLength())
        if not 0.02 < L < JOG_MAX:
            continue
        nb = []
        for p in (t.GetStart(), t.GetEnd()):
            o = [w for w in ends[(t.GetNetCode(), t.GetLayer(), p.x // 1000, p.y // 1000)] if w[2] is not t]
            if len(o) == 1:
                nb.append(o[0])
        if len(nb) == 2:
            (x1, y1, s1), (x2, y2, s2) = nb
            l1, l2 = math.hypot(x1, y1), math.hypot(x2, y2)
            if l1 and l2 and (x1 * x2 + y1 * y2) / (l1 * l2) < -0.99 \
                    and T(s1.GetLength()) > 2 * L and T(s2.GetLength()) > 2 * L:
                m = t.GetCenter()
                jogs.append((t.GetNetname(), t.GetLayerName(), T(m.x), T(m.y)))
    return acute, right, jogs


SHORT_SEG = 0.1        #mm: a segment shorter than this, outside a pad, is listed


#(mixed, short, cover) for the geometry notes
def run_notes(board):
    mixed, short, cover = [], [], []
    pads = collections.defaultdict(list)
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            for l in pd.GetLayerSet().CuStack():
                pads[(pd.GetNetCode(), l)].append(pd)
    per = collections.defaultdict(list)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        if t.IsLocked():
            continue
        per[(t.GetNetCode(), t.GetLayer())].append(t)
    for (code, lay), tracks in per.items():
        segs, adj = runs.net_graph(board, code, lay)
        vias = {runs._node((T(v.GetPosition().x), T(v.GetPosition().y)))
                for v in board.GetTracks()
                if v.Type() == pcbnew.PCB_VIA_T and v.GetNetCode() == code}
        ends = runs.pad_nodes(board, code, lay, segs)
        for chain in runs.net_runs(segs, adj, vias, ends):
            if len({round(segs[i][2], 4) for i in chain}) > 1:
                a = segs[chain[0]][0]
                mixed.append((board.FindNet(code).GetNetname(), board.GetLayerName(lay),
                              round(a[0], 2), round(a[1], 2)))
        for t in tracks:
            if T(t.GetLength()) >= SHORT_SEG:
                continue
            a, c = t.GetStart(), t.GetEnd()
            mid = pcbnew.VECTOR2I((a.x + c.x) // 2, (a.y + c.y) // 2)
            if not any(pd.HitTest(mid, 0) for pd in pads[(code, lay)]):
                short.append((t.GetNetname(), t.GetLayerName(), round(T(a.x), 2), round(T(a.y), 2)))
        geom = [((T(t.GetStart().x), T(t.GetStart().y)), (T(t.GetEnd().x), T(t.GetEnd().y)),
                 T(t.GetWidth()), t) for t in tracks]
        hidden = runs.covered_indices(geom)
        for i, t in enumerate(tracks):
            if i in hidden:
                cover.append((t.GetNetname(), t.GetLayerName(), round(T(t.GetStart().x), 2),
                              round(T(t.GetStart().y), 2)))
    return mixed, short, cover


#vias whose drill hole touches or enters any pad's solder mask opening on F.Mask
def vias_in_pad_mask(board):
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    pads = list(board.GetPads())
    bad = []
    for layer in (pcbnew.F_Mask, pcbnew.B_Mask):
        pads_on_layer = [p for p in pads if p.GetLayerSet().Contains(layer)]
        for p in pads_on_layer:
            pbb = p.GetBoundingBox()
            s = None
            fp = p.GetParentFootprint()
            ref = fp.GetReference() if fp else "?"
            for v in vias:
                vp = v.GetPosition()
                r_drill = pcbnew.ToMM(v.GetDrill() // 2)
                dx = max(0, pbb.GetLeft() - vp.x, vp.x - pbb.GetRight())
                dy = max(0, pbb.GetTop() - vp.y, vp.y - pbb.GetBottom())
                if pcbnew.ToMM(max(dx, dy)) > 0.5:
                    continue
                if s is None:
                    s = p.GetEffectiveShape(layer)
                    if not s or s.IsNull():
                        break
                dist_mm = pcbnew.ToMM(s.Distance(vp))
                #drill hole touches or penetrates the pad mask opening
                if dist_mm < r_drill:
                    bad.append((f"{ref}.{p.GetNumber()}", board.GetLayerName(layer),
                                round(pcbnew.ToMM(vp.x), 2), round(pcbnew.ToMM(vp.y), 2)))
    return bad


#usage: python3 check.py geometry [-v] [--board PATH] Fails on acute corners
def run_geometry():
    b = pcbnew.LoadBoard(BOARD)
    acute, right, jogs = corners(b)
    mixed, short, cover = run_notes(b)
    vips = vias_in_pad_mask(b)
    _e, _u, rpt = pcb.drc(BOARD, everything=True)
    dangling = [blk.splitlines()[0] + " " + " ".join(l.strip() for l in blk.splitlines()[2:3])
                for blk in re.split(r"\n(?=\[)", rpt) if blk.startswith(("[track_dangling", "[via_dangling"))]
    dead_t, dead_v = pcb.dead_copper(b)
    dead = [(t.GetNetname(), t.GetLayerName(), T(t.GetCenter().x), T(t.GetCenter().y)) for t in dead_t] + \
           [(v.GetNetname(), "via", T(v.GetPosition().x), T(v.GetPosition().y)) for v in dead_v]
    power = set(getattr(design, "PLANES", {})) | set(getattr(design, "NET_CURRENT", {}))
    thin = collections.defaultdict(float)
    for t in b.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T and t.GetNetname() in power and T(t.GetWidth()) < THIN_POWER:
            thin[t.GetNetname()] += T(t.GetLength())
    thin = {n: L for n, L in thin.items() if L > THIN_RUN}
    every = "-v" in sys.argv

    def show(title, items, fail):
        print(f"{'FAIL' if fail and items else 'note' if items else ' ok '} {len(items):4} {title}")
        for it in items if every or fail else items[:5]:
            print(f"         {it[0]} on {it[1]} at ({it[2]:.2f}, {it[3]:.2f})" if isinstance(it, tuple) else f"         {it}")
        if not (every or fail) and len(items) > 5:
            print(f"         ... and {len(items) - 5} more (-v lists them)")
    show("acute corners", acute, True)
    show("dangling tracks and vias", dangling, True)
    show("dead copper, leading to no pad or pour (copper.py dead_ends)", dead, True)
    show("vias inside pad mask openings", vips, True)
    show("mixed-width runs", mixed, False)
    show(f"segments under {SHORT_SEG} mm outside pads", short, False)
    show("segments covered by a wider same-net one", cover, False)
    show("right-angle corners", right, False)
    show(f"jogs (sidesteps under {JOG_MAX} mm)", jogs, False)
    print(f"{'note' if thin else ' ok '} {len(thin):4} power nets with over {THIN_RUN} mm of track under {THIN_POWER} mm")
    for n, L in sorted(thin.items(), key=lambda kv: -kv[1]):
        print(f"         {n}: {L:.1f} mm")
    if acute or dangling or dead or vips:
        print(f"\nFAIL - {len(acute)} acute corner(s), {len(dangling)} dangling item(s), "
              f"{len(dead)} dead copper item(s), {len(vips)} via(s) in pad mask openings")
        return 1
    print("\nno acute corners, nothing dangling, no dead copper and no vias in pads")
    return 0


COMMANDS = {
    "backside": run_backside,
    "silk_owner": run_silk_owner,
    "model_alignment": run_model_alignment,
    "cpl": run_cpl,
    "footprints": run_footprints,
    "libraries": run_libraries,
    "geometry": run_geometry,
}

if __name__ == "__main__":
    sys.exit(project.main(COMMANDS, __doc__))
