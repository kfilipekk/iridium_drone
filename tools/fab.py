#!/usr/bin/env python3
"""Ordering from JLCPCB: BOM and CPL, part checks, the order bundle, renders and 3D export.

Usage:  python3 fab.py COMMAND [options]
"""
import csv, datetime, io, json, math, os, re, shutil, subprocess, sys, tempfile
import time, urllib.error, urllib.request, zipfile
import pcbnew
from kicadtools import pcb, project
from kicadtools.project import design

BOARD = project.board_path()
ROOT, NAME, FAB = project.ROOT, project.NAME, project.FAB


#bom

#parts held back from an economic assembly order: {ref: why}
STANDARD_ONLY = getattr(design, "STANDARD_ONLY", {})
VARIANTS = ("", "-economic") if STANDARD_ONLY else ("",)


#JLCPCB rotation for a placed footprint
def cpl_rotation(fp):
    rot = fp.GetOrientationDegrees()
    if fp.GetLayerName() == "B.Cu":
        rot = 180.0 - rot              #the bottom side is seen mirrored
    return rot % 360.0


#usage: python3 fab.py bom [--economic] BOM and pick-and-place for JLCPCB
def run_bom():
    economic = "--economic" in sys.argv
    suffix = "-economic" if economic else ""

    def is_dnp(ref, dnp):
        return bool(dnp)

    b = pcbnew.LoadBoard(BOARD)
    placed = {fp.GetReference(): fp for fp in b.GetFootprints()}

    groups = {}
    skip = getattr(design, "NOT_A_PART", set())
    for ref, (sym, fp, val, lcsc, dnp) in design.COMPONENTS.items():
        #bare copper pads and test points are board features, not parts to buy
        if not fp or ref not in placed or ref in skip: continue
        key = (val, lcsc, fp.split(":")[-1],
               is_dnp(ref, dnp) or (economic and ref in STANDARD_ONLY))
        groups.setdefault(key, []).append(ref)

    os.makedirs(FAB, exist_ok=True)
    with open(f"{FAB}/BOM-{NAME}{suffix}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC", "Qty", "DNP"])
        for (val, lcsc, fpn, dnp), refs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            w.writerow([val, ",".join(sorted(refs)), fpn, lcsc, len(refs),
                        "DNP" if dnp else ""])

    n_cpl = n_fit = 0
    jlc_db = load_footprints()
    with open(f"{FAB}/CPL-{NAME}{suffix}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for ref, fp in sorted(placed.items()):
            if ref in skip: continue      #nothing to pick and place
            if economic and ref in STANDARD_ONLY: continue
            #a DNP part is not placed
            _c = design.COMPONENTS.get(ref)
            if _c and is_dnp(ref, _c[4]): continue
            p = fp.GetPosition()
            x, y, rot = pcbnew.ToMM(p.x), -pcbnew.ToMM(p.y), cpl_rotation(fp)
            fit = (solve(fp, jlc_db[_c[3]])
                   if _c and _c[3] in jlc_db else None)
            if fit:
                rot, (x, y) = round(fit[0]) % 360, fit[1]
                n_fit += 1
            #JLCPCB's engineers turn a non-polar part on the back at 90 or 270 degrees half
            if fp.GetLayerName() == "B.Cu" and pcb.nonpolar(ref) and \
                    round(fp.GetOrientationDegrees()) % 180 == 90:
                rot = (rot + 180) % 360
            w.writerow([ref, f"{x:.4f}mm", f"{y:.4f}mm",
                        "bottom" if fp.GetLayerName() == "B.Cu" else "top",
                        f"{rot:.1f}"])
            n_cpl += 1

    n_lines = len(groups)
    n_parts = sum(len(r) for r in groups.values())
    n_dnp = sum(len(r) for (v, l, fpn, d), r in groups.items() if d)
    no_lcsc = [v for (v, l, fpn, d), r in groups.items()
               if not l or str(l).startswith("LOOKUP:")]
    print(f"BOM: {n_lines} lines, {n_parts} parts ({n_dnp} DNP)")
    #count the rows actually written
    print(f"CPL: {n_cpl} placements, {n_fit} placed from JLCPCB's own footprint "
          f"(fab.py orientation), {n_cpl - n_fit} from the footprint rules")
    if economic:
        print("ECONOMIC variant - these are left off for hand-fitting:")
        for r, why in sorted(STANDARD_ONLY.items()):
            print(f"   {r:4} {why}")
    pend = [v for (v, l, fpn, d), r in groups.items()
            if str(l).startswith("LOOKUP:")]
    print(f"lines without an LCSC code: {len(no_lcsc)}"
          + (f"  ({len(pend)} awaiting an lcsc.com lookup by MPN)" if pend else ""))
    for v in sorted(no_lcsc):
        print(f"   {v}")


#orientation

CACHE = os.path.join(ROOT, "libraries", "jlc_footprints.json")
APIS = ["https://easyeda.com/api/products/{}/components?version=6.4.19.5",
        "https://lceda.cn/api/products/{}/components?version=6.4.19.5"]
UNIT = 0.254              #EasyEDA footprint units are 10 mil
#the fit is accepted when its RMS residual is under a quarter of the pattern's own RMS radius
RESIDUAL_RATIO = 0.25


def fetch_one(code):
    err = None
    for api in APIS:
        try:
            req = urllib.request.Request(api.format(code), headers={"User-Agent": "curl/8.5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
            break
        except Exception as e:
            err = e
    else:
        raise err
    if not d.get("success"):
        raise ValueError(d.get("message", "no success flag"))
    pkg = d["result"]["packageDetail"]
    head = pkg["dataStr"]["head"]
    ox, oy = float(head["x"]), float(head["y"])
    pads = {}
    for s in pkg["dataStr"]["shape"]:
        if not s.startswith("PAD~"):
            continue
        f = s.split("~")
        x, y, num = float(f[2]), float(f[3]), f[8]
        pads.setdefault(num, []).append([round((x - ox) * UNIT, 4), round((y - oy) * UNIT, 4)])
    #one centre per number
    return {"package": pkg["title"],
            "pads": {n: [round(sum(p[0] for p in v) / len(v), 4),
                         round(sum(p[1] for p in v) / len(v), 4)] for n, v in pads.items()}}


def board_codes():
    return sorted({c[3] for c in design.COMPONENTS.values()
                   if c[3] and str(c[3]).startswith("C") and not str(c[3]).startswith("LOOKUP")})


#resumable: codes already in the cache are skipped unless --refresh
def fetch(refresh=False):
    db = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [c for c in board_codes() if refresh or c not in db]
    refused = 0
    for code in todo:
        try:
            db[code] = fetch_one(code)
            refused = 0
            print(f"  {code:10s} {db[code]['package']:40s} {len(db[code]['pads'])} pads")
        except Exception as e:
            print(f"  {code:10s} FAILED: {e}")
            refused += 1
            if refused >= 3:
                print("  three refusals in a row - rate-limited; saving and stopping. "
                      "Re-run later: it resumes where it stopped.")
                break
        time.sleep(6.0)
    db = dict(sorted(db.items()))
    with open(CACHE, "w") as f:
        json.dump(db, f, indent=1)
        f.write("\n")
    missing = [c for c in board_codes() if c not in db]
    print(f"wrote {os.path.relpath(CACHE, ROOT)} ({len(db)} footprints"
          + (f", {len(missing)} still to fetch)" if missing else ", complete)"))


def load_footprints():
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {}


#rigid 2D fit dst ~ R(a) src + t over matched points
def fit_pads(src, dst):
    n = len(src)
    sx = sum(p[0] for p in src) / n; sy = sum(p[1] for p in src) / n
    dx = sum(p[0] for p in dst) / n; dy = sum(p[1] for p in dst) / n
    num = den = 0.0
    for (ax, ay), (bx, by) in zip(src, dst):
        ax -= sx; ay -= sy; bx -= dx; by -= dy
        num += ax * by - ay * bx
        den += ax * bx + ay * by
    a = math.atan2(num, den)
    c, s = math.cos(a), math.sin(a)
    tx, ty = dx - (c * sx - s * sy), dy - (s * sx + c * sy)
    rms = math.sqrt(sum((c * x - s * y + tx - u) ** 2 + (s * x + c * y + ty - v) ** 2
                        for (x, y), (u, v) in zip(src, dst)) / n)
    return math.degrees(a), (tx, ty), rms


#fit() plus the RESIDUAL_RATIO test; (deg, t, rms) or None
def _accept(src, dst):
    #two distinct pad centres fix an angle; fewer (or all coincident) do not
    if len(src) < 2 or max(math.dist(src[0], p) for p in src) < 0.05:
        return None
    deg, t, rms = fit_pads(src, dst)
    cx, cy = sum(p[0] for p in src) / len(src), sum(p[1] for p in src) / len(src)
    radius = math.sqrt(sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in src) / len(src))
    return (deg, t, rms) if rms <= RESIDUAL_RATIO * radius else None


#fallback for footprints that number their pads differently
def _by_geometry(epads, opads):
    if len(epads) != len(opads):
        return None
    ocx = sum(p[1][0] for p in opads) / len(opads)
    ocy = sum(p[1][1] for p in opads) / len(opads)
    ecx = sum(p[1][0] for p in epads) / len(epads)
    ecy = sum(p[1][1] for p in epads) / len(epads)
    best = None
    for q in range(4):
        a = math.radians(90 * q)
        c, s_ = math.cos(a), math.sin(a)
        free, pairs = list(range(len(opads))), []
        for n, (x, y) in epads:
            u = c * (x - ecx) - s_ * (y - ecy) + ocx
            v = s_ * (x - ecx) + c * (y - ecy) + ocy
            j = min(free, key=lambda k: math.dist((u, v), opads[k][1]))
            free.remove(j)
            pairs.append(((x, y), opads[j][1], n, opads[j][0]))
        if any(n == "1" and m != "1" for _, _, n, m in pairs):
            continue
        got = _accept([p[0] for p in pairs], [p[1] for p in pairs])
        if got and (best is None or got[2] < best[2]):
            best = got
    return best


#(rotation_deg, (mid_x_mm, mid_y_mm), rms_mm, n_pads) for one placed footprint
def solve(fp, entry):
    T = pcbnew.ToMM
    bottom = fp.GetLayerName() == "B.Cu"
    ours, opads = {}, []
    for p in fp.Pads():
        n = p.GetNumber()
        if n:
            q = p.GetPosition()
            pt = (-T(q.x) if bottom else T(q.x), -T(q.y))
            ours.setdefault(n, []).append(pt)
            opads.append((n, pt))
    epads = [(n, (ex, -ey)) for n, (ex, ey) in entry["pads"].items()]  #EasyEDA is y-down
    src, dst = [], []
    for n, e in epads:
        if n in ours:
            v = ours[n]
            src.append(e)
            dst.append((sum(a for a, _ in v) / len(v), sum(b for _, b in v) / len(v)))
    got, n_used = _accept(src, dst), len(src)
    if got is None:
        got, n_used = _by_geometry(epads, opads), len(opads)
    if got is None:
        return None
    deg, (tx, ty), rms = got
    #EasyEDA origin (0,0) lands at t in the fitted frame
    mx = -tx if bottom else tx
    return round(deg, 3) % 360.0, (mx, ty), rms, n_used


#usage: python3 fab.py orientation --fetch [--refresh] # download JLC's footprints
def run_orientation():
    if "--fetch" in sys.argv:
        fetch(refresh="--refresh" in sys.argv)
        return 0
    db = load_footprints()
    if not db:
        print(f"no {os.path.relpath(CACHE, ROOT)} - run with --fetch first")
        return 1
    b = pcbnew.LoadBoard(BOARD)
    rows, unsolved = [], []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        c = design.COMPONENTS.get(ref)
        if not c or not c[3] or c[3] not in db:
            continue
        s = solve(fp, db[c[3]])
        old = cpl_rotation(fp)
        if s is None:
            unsolved.append(ref)
            continue
        rot, (mx, my), rms, n = s
        p = fp.GetPosition()
        off = math.hypot(mx - pcbnew.ToMM(p.x), my + pcbnew.ToMM(p.y))
        d = (rot - old + 180) % 360 - 180
        rows.append((ref, c[3], db[c[3]]["package"], old, rot, d, off, rms, n))
    changed = [r for r in rows if abs(r[5]) > 1 or r[6] > 0.05]
    print(f"{len(rows)} parts solved from JLCPCB's own footprints; "
          f"{len(changed)} differ from the placed orientation/origin:")
    for ref, code, pkg, old, rot, d, off, rms, n in changed:
        print(f"  {ref:5s} {code:9s} {pkg[:34]:34s} placed {old:6.1f} -> JLC {rot:6.1f} "
              f"({d:+6.1f})  centre moves {off:.2f} mm  [fit {rms*1000:.0f} um, {n} pads]")
    same = len(rows) - len(changed)
    print(f"{same} agree with the rules-based rotation and origin - a cross-check of both")
    if unsolved:
        print(f"not solvable by pad number (placed orientation kept): {', '.join(unsolved)}")
    return 0


#paste

GAP = 0.40
BIG_PAD_MM2 = 6.0
EXPOSED_MM2 = 4.0     #what counts as a thermal slug worth windowpaning
MIN_PADS_FOR_SLUG = 5 #below this a big pad is a termination, not a slug


#every SMD pad big enough to be a thermal slug
def scan(b):
    hits = []
    for fp in b.GetFootprints():
        pads = list(fp.Pads())
        for pad in pads:
            sz = pad.GetSize()
            area = pcbnew.ToMM(sz.x) * pcbnew.ToMM(sz.y)
            if area < EXPOSED_MM2 or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            lay = pcbnew.B_Paste if fp.IsFlipped() else pcbnew.F_Paste
            slug = len(pads) >= MIN_PADS_FOR_SLUG
            hits.append((fp.GetReference(), pad.GetNumber(), area,
                         pad.IsOnLayer(lay), slug, len(pads)))
    return hits


#usage: python3 fab.py paste --scan find pads that need it python3 fab.py paste U13
def run_paste():
    apply = '--apply' in sys.argv
    b = pcbnew.LoadBoard(BOARD)
    if '--scan' in sys.argv:
        print(f"{'ref':6} {'pad':4} {'area':>8} {'pads':>5}  verdict")
        need = 0
        for ref, pn, area, solid, slug, npads in scan(b):
            if not slug:
                verdict = "termination on a 2-pad part - LEAVE ALONE"
            elif solid:
                verdict = "THERMAL SLUG, solid 100% aperture - NEEDS WINDOWPANING"
                need += 1
            else:
                verdict = "thermal slug, already windowpaned"
            print(f"{ref:6} {pn:4} {area:7.2f}mm2 {npads:5}  {verdict}")
        print(f"\n{need} pad(s) need windowpaning")
        return 1 if need else 0
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        print("usage: fab.py paste <REF> <PAD> [--apply]   (or --scan)")
        return 2
    REF, PAD = args
    fp = b.FindFootprintByReference(REF)
    if fp is None:
        print(f"{REF} is not on the board")
        return 1
    pad = next((p for p in fp.Pads() if p.GetNumber() == PAD), None)
    if pad is None:
        print(f"{REF}.{PAD} not found")
        return 1

    paste_layer = pcbnew.B_Paste if fp.IsFlipped() else pcbnew.F_Paste
    if not pad.IsOnLayer(paste_layer):
        print(f"{REF}.{PAD} already has no paste on its own layer - looks done")
        return 0

    sz = pad.GetSize()
    w_mm, h_mm = pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)
    n = 3 if w_mm * h_mm >= BIG_PAD_MM2 else 2
    aw = (w_mm - (n - 1) * GAP) / n
    ah = (h_mm - (n - 1) * GAP) / n
    cov = n * n * aw * ah / (w_mm * h_mm) * 100
    c = pad.GetPosition()
    print(f"{REF}.{PAD}  {w_mm:.2f} x {h_mm:.2f} mm = {w_mm*h_mm:.2f} mm2, "
          f"one 100% aperture")
    print(f"  -> {n}x{n} of {aw:.2f} x {ah:.2f} mm on "
          f"{b.GetLayerName(paste_layer)}, {GAP:.2f} mm gaps = {cov:.1f}% coverage "
          f"(IPC-7093: 50-80%)")
    if not 50.0 <= cov <= 80.0:
        print(f"  REFUSING: {cov:.1f}% is outside IPC-7093's 50-80% band")
        return 1

    if not apply:
        print("\ndry run - pass --apply")
        return 0

    ls = pad.GetLayerSet()
    ls.removeLayer(paste_layer)
    pad.SetLayerSet(ls)

    off = [(i - (n - 1) / 2.0) for i in range(n)]
    for ix in off:
        for iy in off:
            cx = c.x + pcbnew.FromMM(ix * (aw + GAP))
            cy = c.y + pcbnew.FromMM(iy * (ah + GAP))
            s = pcbnew.PCB_SHAPE(fp)
            s.SetShape(pcbnew.SHAPE_T_RECT)
            s.SetStart(pcbnew.VECTOR2I(cx - pcbnew.FromMM(aw / 2),
                                       cy - pcbnew.FromMM(ah / 2)))
            s.SetEnd(pcbnew.VECTOR2I(cx + pcbnew.FromMM(aw / 2),
                                     cy + pcbnew.FromMM(ah / 2)))
            s.SetLayer(paste_layer)
            s.SetFilled(True)
            s.SetWidth(0)
            fp.Add(s)

    b.Save(BOARD)
    print("saved - now diff the B_Paste gerber; nothing else may change")
    return 0


#lcsc

PROP = re.compile(r'^(\t+)\(property "LCSC" "([^"]*)"')
REF = re.compile(r'\(property "Reference" "([^"]+)"')
BODY = re.compile(r'^\t\(symbol |^\t\(footprint ')


#yield the line range of every symbol/footprint instance block
def instance_blocks(text):
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if BODY.match(line):
            if start is not None:
                yield start, i
            start = i
    if start is not None:
        yield start, len(lines)
    return


#return (text, changes, unknown) with each block's LCSC set from `want`
def retag(text, want):
    lines = text.split("\n")
    changes, unknown = [], []
    for lo, hi in instance_blocks(text):
        ref = None
        lcsc_line = None
        for i in range(lo, hi):
            if ref is None:
                m = REF.search(lines[i])
                if m:
                    ref = m.group(1)
            if lcsc_line is None and PROP.match(lines[i]):
                lcsc_line = i
        if ref is None or lcsc_line is None or not re.match(r"^[A-Z]+\d", ref):
            continue
        have = PROP.match(lines[lcsc_line]).group(2)
        code = design.COMPONENTS.get(ref, (None, None, None, None))[3]
        if not code:
            if have:
                unknown.append((ref, have))
            continue
        if have != code:
            changes.append((ref, have, code))
            lines[lcsc_line] = PROP.sub(
                lambda m: f'{m.group(1)}(property "LCSC" "{code}"', lines[lcsc_line])
    return "\n".join(lines), changes, unknown


#the LCSC property of every schematic symbol and board footprint
def run_lcsc():
    write = "--write" in sys.argv
    rc = 0
    for name in (f"{NAME}.kicad_sch", f"{NAME}.kicad_pcb"):
        path = BOARD if name.endswith(".kicad_pcb") else os.path.join(ROOT, name)
        text = open(path, encoding="utf-8").read()
        new, changes, unknown = retag(text, design.COMPONENTS)
        print(f"{name}: {len(changes)} LCSC field(s) disagree with design.py")
        for ref, have, code in sorted(changes):
            print(f"   {ref:5} {have:12} -> {code}")
        if unknown:
            print(f"   {len(unknown)} footprint(s) carry an LCSC code design.py "
                  f"no longer assigns: {', '.join(sorted(r for r, _ in unknown))}")
        if changes:
            rc = 1
            if write:
                open(path, "w", encoding="utf-8").write(new)
                print("   written")
    if rc and not write:
        print("\nre-run with --write to fix")
    return 0 if (not rc or write) else 1


#offsets

#(dx, dy, dz) of a STEP file's point cloud
def step_extent(path):
    try:
        txt = open(path, 'r', errors='ignore').read()
    except OSError:
        return None
    xs, ys, zs = [], [], []
    for m in re.finditer(r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*"
                         r"([-0-9.Ee+]+)\s*,\s*([-0-9.Ee+]+)\s*,\s*([-0-9.Ee+]+)", txt):
        xs.append(float(m.group(1)))
        ys.append(float(m.group(2)))
        zs.append(float(m.group(3)))
    if not xs:
        return None
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def set_offset(board, ref, off, apply):
    fp = board.FindFootprintByReference(ref)
    if fp is None or not len(fp.Models()):
        print(f"FAIL: {ref} has no 3D model")
        return 1
    m = fp.Models()[0]
    print(f"{ref}: model offset ({m.m_Offset.x:.3f}, {m.m_Offset.y:.3f}, {m.m_Offset.z:.3f}) "
          f"-> ({off[0]:.3f}, {off[1]:.3f}, {off[2]:.3f})")
    if not apply:
        print("dry run - pass --apply")
        return 0
    pos = (fp.GetPosition().x, fp.GetPosition().y, fp.GetOrientation().AsDegrees())
    m.m_Offset = pcbnew.VECTOR3D(*off)
    if pos != (fp.GetPosition().x, fp.GetPosition().y, fp.GetOrientation().AsDegrees()):
        print("FAIL: the footprint moved; nothing written")
        return 1
    board.Save(BOARD)
    print("written; the footprint's position, rotation and pads are unchanged")
    return 0


#usage: python3 fab.py offsets [--apply] python3 fab.py offsets --set REF X Y Z
def run_offsets():
    apply = '--apply' in sys.argv
    board = pcbnew.LoadBoard(BOARD)
    JLC = project.MODELS
    if '--set' in sys.argv:
        i = sys.argv.index('--set')
        ref, off = sys.argv[i + 1], [float(v) for v in sys.argv[i + 2:i + 5]]
        return set_offset(board, ref, off, apply)

    bad, checked = [], 0
    for fp in board.GetFootprints():
        for idx, m in enumerate(fp.Models()):
            p = m.m_Filename.replace('${JLC_LIB}', JLC)
            p = os.path.expandvars(p)
            if '${' in p or not p.lower().endswith('.step'):
                continue
            ext = step_extent(p)
            if ext is None:
                continue
            checked += 1
            for axis, dim, val in (('x', ext[0], m.m_Offset.x),
                                   ('y', ext[1], m.m_Offset.y),
                                   ('z', ext[2], m.m_Offset.z)):
                #an offset bigger than the part itself cannot be an alignment
                if abs(val) > max(dim, 1.0):
                    bad.append((fp.GetReference(), fp.GetFPIDAsString(),
                                axis, val, dim, fp, idx))
                    break

    print(f"{checked} resolvable STEP model(s) measured; "
          f"{len(bad)} with an offset larger than the part\n")
    for ref, fid, axis, val, dim, _, _ in bad:
        print(f"  {ref:5s} {str(fid).split(':')[-1][:40]:40s} "
              f"offset.{axis} = {val:10.3f} mm, part is {dim:5.2f} mm")

    if not bad:
        return 0
    if not apply:
        print("\ndry run - pass --apply")
        return 0

    #electrical state must not move
    def electrical(): return [(fp.GetReference(),
                               fp.GetPosition().x, fp.GetPosition().y,
                               fp.GetOrientation().AsDegrees(),
                               sorted(str(p.GetNetname()) for p in fp.Pads()))
                              for fp in board.GetFootprints()]

    before = electrical()

    for _, _, _, _, _, fp, idx in bad:
        mods = fp.Models()
        old = mods[idx]
        nm = pcbnew.FP_3DMODEL()
        nm.m_Filename = old.m_Filename
        nm.m_Offset = pcbnew.VECTOR3D(0.0, 0.0, 0.0)
        nm.m_Scale = pcbnew.VECTOR3D(old.m_Scale.x, old.m_Scale.y, old.m_Scale.z)
        nm.m_Rotation = pcbnew.VECTOR3D(old.m_Rotation.x, old.m_Rotation.y, old.m_Rotation.z)
        nm.m_Show = old.m_Show
        while len(mods):
            mods.pop()
        mods.push_back(nm)

    after = electrical()
    if before != after:
        print("FAIL: repair moved electrical state; nothing written")
        return 1

    board.Save(BOARD)
    print(f"\nzeroed {len(bad)} model offset(s); position, rotation and every pad net "
          f"unchanged")
    return 0


#stock

BOM = os.path.join(FAB, f"BOM-{NAME}.csv")
SNAP = os.path.join(FAB, "stock-snapshot.json")

API = ("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/"
       "smtGood/selectSmtComponentList")

#stock decays; a week-old count is a starting point, not a fact
MAX_AGE_DAYS = 7

#boards being assembled, so the stock must cover qty x this
ASSEMBLED_BOARDS = getattr(design, "ASSEMBLED_BOARDS", 2)

#codes JLCPCB assembles but its API does not carry: {code: note}
KNOWN = getattr(design, "JLC_KNOWN", {})


def _post(code):
    body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 10,
                       "searchSource": "search"}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        d = json.loads(r.read().decode())
    lst = ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []
    for row in lst:
        if str(row.get("componentCode", "")).upper() == code.upper():
            return row
    return None


def fetch_stock(lines):
    out = {}
    for code, want in lines.items():
        try:
            row = _post(code)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"  !! network error for {code}: {e}")
            return None
        if row is None:
            out[code] = {"found": False}
            continue
        out[code] = {
            "found": True,
            "mpn": row.get("componentModelEn") or row.get("componentName"),
            "spec": row.get("componentSpecificationEn"),
            "library": row.get("componentLibraryType"),
            "stock": row.get("stockCount"),
            "min_purchase": row.get("minPurchaseNum"),
            "least_patch": row.get("leastPatchNumber"),
            "price_usd": row.get("initialPrice"),
            "lcsc_url": row.get("lcscGoodsUrl"),
            "describe": row.get("describe"),
        }
    return out


#a passive's value
_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6,
       "R": 1.0, "Ω": 1.0}


def bom_value(text):
    m = re.fullmatch(r"(\d+)([pnuµkKMR])(\d*)(?:H|F)?(?:@100MHz)?(?: x\d+)?", text.strip())
    if not m:
        return None
    return float(m.group(1) + "." + (m.group(3) or "0")) * _SI[m.group(2)]


#kind 'R', 'C' or 'L'; a bead's impedance is read as ohms
def jlc_value(describe, kind):
    pat = {"R": r"([\d.]+)\s*([kKMm]?)Ω(?!@)", "C": r"([\d.]+)\s*([pnuµ])F",
           "L": r"([\d.]+)\s*([pnuµ])H", "B": r"([\d.]+)\s*([kK]?)Ω@100MHz"}[kind]
    m = re.search(pat, describe or "")
    if not m:
        return None
    return float(m.group(1)) * (_SI.get(m.group(2), 1.0) if m.group(2) else 1.0)


def kind_of(footprint, comment):
    if "@100MHz" in comment:
        return "B"
    if footprint.startswith(("R_", "RES")) or "x4" in comment:
        return "R"
    if footprint.startswith("C_"):
        return "C"
    if footprint.startswith("L_") or footprint == "L0402":
        return "L"
    return None


#every BOM line is buyable
def run_stock():
    argv = [a for a in sys.argv[1:] if a != "--fetch"]
    do_fetch = "--fetch" in sys.argv
    bom = argv[0] if argv else BOM
    if not os.path.isabs(bom):
        bom = os.path.join(ROOT, bom)

    rows = list(csv.DictReader(open(bom)))
    #DNP lines are not placed, so they are reported but never block
    lines, dnp, said = {}, set(), {}
    for r in rows:
        code = (r.get("LCSC") or "").strip()
        if not code:
            continue
        said[code] = (r.get("Comment") or "", r.get("Footprint") or "")
        qty = int((r.get("Qty") or "0").strip() or 0)
        if (r.get("DNP") or "").strip():
            dnp.add(code)
        lines[code] = lines.get(code, 0) + qty
    print(f"BOM        : {os.path.relpath(bom, ROOT)} - {len(rows)} lines, "
          f"{len(lines)} distinct codes ({len(dnp)} DNP)")

    if do_fetch:
        print(f"source     : {API.split('/api')[0]} (live)")
        data = fetch_stock(lines)
        if data is None:
            print("\nFAIL - could not reach JLCPCB; nothing was verified")
            return 1
        payload = {"date": datetime.date.today().isoformat(),
                   "source": API,
                   "assembled_boards": ASSEMBLED_BOARDS,
                   "lines": data}
        with open(SNAP, "w") as f:
            json.dump(payload, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"snapshot   : wrote {os.path.relpath(SNAP, ROOT)}")
    else:
        if not os.path.exists(SNAP):
            print(f"\nFAIL - no snapshot at {os.path.relpath(SNAP, ROOT)}; "
                  f"run: python3 fab.py stock --fetch")
            return 1
        payload = json.load(open(SNAP))
        print(f"source     : {os.path.relpath(SNAP, ROOT)} (no network this run)")

    held = datetime.date.fromisoformat(payload["date"])
    age = (datetime.date.today() - held).days
    stale = age > MAX_AGE_DAYS
    print(f"snapshot   : {held.isoformat()} ({age} day(s) old, max {MAX_AGE_DAYS})"
          + ("  ** STALE **" if stale else ""))
    data = payload["lines"]
    print()

    fails, notes = [], []
    covered = 0
    for code, qty in sorted(lines.items()):
        need = qty * ASSEMBLED_BOARDS
        rec = data.get(code)
        tag = "DNP" if code in dnp else f"x{qty}"
        if rec is None:
            fails.append(f"{code:11} ({tag:5}) not in the snapshot - run "
                         f"fab.py stock --fetch")
            continue
        if not rec.get("found"):
            if code in KNOWN:
                notes.append(f"{code:11} ({tag:5}) not carried by the API - {KNOWN[code]}")
            else:
                fails.append(f"{code:11} ({tag:5}) NOT FOUND at JLCPCB - check "
                             f"jlcpcb.com/partdetail/{code} by hand")
            continue
        #the part's own value, not the line's label
        comment, fp = said.get(code, ("", ""))
        kind = kind_of(fp, comment)
        if kind and rec.get("describe") is None:
            fails.append(f"{code:11} ({tag:5}) the snapshot has no description to check "
                         f"{comment} against - run fab.py stock --fetch")
        elif kind:
            want, got = bom_value(comment.split("@")[0] if kind != "B" else comment.split("@")[0]), \
                jlc_value(rec.get("describe"), kind)
            if want is None or got is None:
                notes.append(f"{code:11} ({tag:5}) value not compared: BOM {comment!r}, "
                             f"JLCPCB {str(rec.get('describe'))[:40]!r}")
            elif abs(got - want) > 0.005 * max(want, 1e-15) and not (want == 0 and got == 0):
                fails.append(f"{code:11} ({tag:5}) {rec.get('mpn')} is {got:g}, the BOM says "
                             f"{comment} ({want:g})")
        stock = rec.get("stock") or 0
        lib = (rec.get("library") or "?").lower()
        tier = {"base": "Basic", "expand": "Extended"}.get(lib, lib)
        bad = []
        if stock < need:
            bad.append(f"stock {stock} < {need} needed")
        if bad and code not in dnp:
            fails.append(f"{code:11} ({tag:5}) {rec.get('mpn')}: " + "; ".join(bad))
        elif bad:
            notes.append(f"{code:11} ({tag:5}) DNP and short ({stock} < {need}) - only "
                         f"matters if it is ever populated")
        else:
            covered += 1
        print(f"  {code:11} {tag:5} {tier:9} stock {stock:>7}  "
              f"{str(rec.get('mpn'))[:28]:28} {str(rec.get('spec'))[:20]}")

    if stale:
        fails.append(f"the stock snapshot is {age} days old (max {MAX_AGE_DAYS}) - "
                     f"run: python3 fab.py stock --fetch")

    print()
    for n in notes:
        print(f"  note: {n}")
    print(f"{covered}/{len(lines)} line(s) resolved with stock >= {ASSEMBLED_BOARDS} boards")
    if fails:
        print(f"\nFAIL - {len(fails)} problem(s):")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("every BOM line resolves to the intended part and covers the order")
    return 0


#variants

BOM_COLS = ["Comment", "Designator", "Footprint", "LCSC", "Qty", "DNP"]
CPL_COLS = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]


def read(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def split(refs):
    return [r.strip() for r in refs.split(",") if r.strip()]


#every BOM/CPL variant describes this board, or it does not ship
def run_variants():
    os.chdir(ROOT)
    fab = os.path.relpath(FAB)
    problems = []

    design_by_ref = design.COMPONENTS
    skip = getattr(design, "NOT_A_PART", set())

    #the design's own truth for each ref: LCSC code, and whether it is fitted
    want_code, want_dnp = {}, {}
    for ref, (_sym, _fp, _val, lcsc, dnp) in design_by_ref.items():
        if ref in skip or not _fp:
            continue
        want_code[ref] = lcsc
        want_dnp[ref] = bool(dnp)

    #the default pair is the reference the variants are subsets of
    base_cpl = {r["Designator"]: r for r in read(f"{fab}/CPL-{NAME}.csv")}

    n_checked = 0
    for suf in VARIANTS:
        bom_p = f"{fab}/BOM-{NAME}{suf}.csv"
        cpl_p = f"{fab}/CPL-{NAME}{suf}.csv"
        label = suf.lstrip("-") or "default"
        for p in (bom_p, cpl_p):
            if not os.path.exists(p):
                problems.append(f"{label}: {p} is missing")
        if problems and not os.path.exists(bom_p):
            continue
        if not (os.path.exists(bom_p) and os.path.exists(cpl_p)):
            continue

        bom, cpl = read(bom_p), read(cpl_p)

        for got, want, kind in ((list(bom[0]), BOM_COLS, "BOM"), (list(cpl[0]), CPL_COLS, "CPL")):
            if got != want:
                problems.append(f"{label}: {kind} header is {got}, expected {want}")

        cpl_refs = {r["Designator"] for r in cpl}
        bom_refs = {}
        for r in bom:
            dnp = bool(r.get("DNP", "").strip())
            for ref in split(r["Designator"]):
                bom_refs[ref] = dnp
                if ref in want_code and str(r["LCSC"]).strip() != str(want_code[ref]).strip():
                    problems.append(
                        f"{label}: {ref} carries LCSC {r['LCSC']}, design says {want_code[ref]}")
                if ref not in want_code and not ref.startswith("PV"):
                    problems.append(f"{label}: {ref} is in the BOM but not in the design")
            #3. DNP still names a real part
            if dnp and str(r["LCSC"]).strip().startswith("LOOKUP:"):
                problems.append(f"{label}: DNP line '{r['Designator']}' has no real LCSC code")

        #3. a DNP part must not be placed
        for ref in sorted(cpl_refs):
            if bom_refs.get(ref):
                problems.append(f"{label}: {ref} is marked DNP but the CPL places it")
        #fitted parts must appear in the CPL
        for ref, dnp in sorted(bom_refs.items()):
            if not dnp and ref not in cpl_refs:
                problems.append(f"{label}: {ref} is fitted in the BOM but missing from the CPL")

        #2. sides - a variant may drop a part, never move one
        for r in cpl:
            ref = r["Designator"]
            b = base_cpl.get(ref)
            if b is None:
                problems.append(f"{label}: {ref} is placed but absent from the default CPL")
                continue
            if (r["Mid X"], r["Mid Y"], r["Layer"], r["Rotation"]) != \
               (b["Mid X"], b["Mid Y"], b["Layer"], b["Rotation"]):
                problems.append(
                    f"{label}: {ref} sits at {r['Mid X']},{r['Mid Y']} {r['Rotation']} but the "
                    f"board's CPL puts it at {b['Mid X']},{b['Mid Y']} {b['Rotation']} "
                    f"- a variant omits parts, it does not move them")

        n_checked += 1
        print(f"  {label:9} BOM {len(bom):3} lines / CPL {len(cpl):3} placements")

    print(f"\n{n_checked} variant pair(s) checked against the board")
    if problems:
        print(f"\nFAIL - {len(problems)} problem(s):")
        for p in problems[:40]:
            print(f"   - {p}")
        if len(problems) > 40:
            print(f"   ... and {len(problems) - 40} more")
        return 1
    print("every variant matches the board and the design")
    return 0


#check_bundle

BUNDLE = os.path.join(FAB, f"{NAME}-order-bundle.zip")
GERBERS = os.path.join(FAB, "gerbers")

FLAT = [f"{k}-{NAME}{v}.csv" for v in ("", "-economic") for k in ("BOM", "CPL")]
REQUIRED = ["HOW-TO-ORDER.txt", "gerbers.zip", f"BOM-{NAME}.csv", f"CPL-{NAME}.csv"]


#the order bundle matches the board that was verified
def run_check_bundle():
    fails = []
    if not os.path.exists(BUNDLE):
        print(f"FAIL - {os.path.relpath(BUNDLE, ROOT)} does not exist; "
              f"run fab.py bundle")
        return 1

    zf = zipfile.ZipFile(BUNDLE)
    names = set(zf.namelist())

    #1. present
    missing = [n for n in REQUIRED if n not in names]
    for n in missing:
        fails.append(f"the bundle does not contain {n}")
    print(f"bundle     : {os.path.relpath(BUNDLE, ROOT)} ({len(names)} member(s))")

    #2. identical
    flat_ok = flat_bad = 0
    for name in FLAT:
        if name not in names:
            continue                      #the *-economic variant is optional
        disk = os.path.join(FAB, name)
        if not os.path.exists(disk):
            fails.append(f"{name} is in the bundle but not on disk - cannot verify it")
            continue
        if zf.read(name) != open(disk, "rb").read():
            fails.append(f"{name} in the bundle DIFFERS from fab/{name} - the bundle is "
                         f"stale; re-run fab.py bundle")
            flat_bad += 1
        else:
            flat_ok += 1

    ger_ok = ger_bad = ger_missing = 0
    if "gerbers.zip" in names:
        inner = zipfile.ZipFile(io.BytesIO(zf.read("gerbers.zip")))
        disk_gerbers = sorted(f for f in os.listdir(GERBERS)) if os.path.isdir(GERBERS) else []
        for member in inner.namelist():
            if member.endswith("/"):
                continue
            base = os.path.basename(member)
            disk = os.path.join(GERBERS, base)
            if not os.path.exists(disk):
                ger_missing += 1
                fails.append(f"gerbers/{base} is in the bundle but not in fab/gerbers/")
            elif inner.read(member) != open(disk, "rb").read():
                ger_bad += 1
                fails.append(f"gerbers/{base} in the bundle DIFFERS from fab/gerbers/ - "
                             f"the bundle is stale; re-run fab.py bundle")
            else:
                ger_ok += 1
        bundled = {os.path.basename(m) for m in inner.namelist() if not m.endswith("/")}
        for base in disk_gerbers:
            if base not in bundled:
                fails.append(f"fab/gerbers/{base} is NOT in the bundle - the bundle is "
                             f"missing a layer; re-run fab.py bundle")

    print(f"csv files  : {flat_ok} identical, {flat_bad} diverged")
    print(f"gerbers    : {ger_ok} identical, {ger_bad} diverged, {ger_missing} absent on disk")

    #3. derived
    if "HOW-TO-ORDER.txt" in names and f"CPL-{NAME}.csv" in names:
        txt = zf.read("HOW-TO-ORDER.txt").decode()
        rows = list(csv.DictReader(
            io.StringIO(zf.read(f"CPL-{NAME}.csv").decode())))
        top = sum(1 for r in rows if (r.get("Layer") or "").strip().lower() == "top")
        bot = sum(1 for r in rows if (r.get("Layer") or "").strip().lower() == "bottom")
        m = re.search(r"(\d+)\s+top,\s+(\d+)\s+bottom", txt)
        if not m:
            fails.append("HOW-TO-ORDER.txt does not state a placement count - the "
                         "@@SIDES@@ placeholder may never have been substituted")
            print("placements : NOT FOUND in HOW-TO-ORDER.txt")
        else:
            got = (int(m.group(1)), int(m.group(2)))
            print(f"placements : HOW-TO-ORDER.txt says {got[0]} top / {got[1]} bottom; "
                  f"the bundled CPL says {top} top / {bot} bottom")
            if got != (top, bot):
                fails.append(f"HOW-TO-ORDER.txt says {got[0]} top / {got[1]} bottom but "
                             f"the CPL in the same bundle has {top} top / {bot} bottom")

        m = re.search(r"Dimensions\s+([\d.]+)\s*x\s*([\d.]+)\s*mm", txt)
        if m:
            w, h = outline_mm(pcbnew.LoadBoard(BOARD))
            ok = abs(float(m.group(1)) - w) < 0.1 and abs(float(m.group(2)) - h) < 0.1
            print(f"dimensions : HOW-TO-ORDER.txt says {m.group(1)} x {m.group(2)} mm; "
                  f"the board is {w:.1f} x {h:.1f} mm")
            if not ok:
                fails.append(f"HOW-TO-ORDER.txt gives {m.group(1)} x {m.group(2)} mm but the "
                             f"board is {w:.1f} x {h:.1f} mm")

    print()
    if fails:
        print(f"FAIL - {len(fails)} problem(s) with the order bundle:")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("order bundle is present, matches the tree it was built from, and is self-consistent")
    return 0


#bundle

#the board's width and height from Edge.Cuts, mm
def outline_mm(board):
    bb = board.GetBoardEdgesBoundingBox()
    lw = max((d.GetWidth() for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts),
             default=0)
    return pcbnew.ToMM(bb.GetWidth() - lw), pcbnew.ToMM(bb.GetHeight() - lw)


#vias whose centre lies in an SMD pad: each needs filling and capping
def vias_in_pads(board):
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    return sum(1 for v in board.GetTracks() if v.Type() == pcbnew.PCB_VIA_T
               and any(p.HitTest(v.GetPosition()) for p in pads))


#usage: python3 fab.py bundle Build the self-contained order bundle
def run_bundle():
    copper = pcb.copper(BOARD)
    gerbers = os.path.join(FAB, "gerbers")
    print(f"regenerating gerbers from {os.path.relpath(BOARD)} ...")
    shutil.rmtree(gerbers, ignore_errors=True)
    os.makedirs(gerbers)
    cli = lambda *a: subprocess.run(["kicad-cli", "pcb", "export", *a, BOARD],
                                    capture_output=True, check=True)
    cli("gerbers", "--output", gerbers + "/", "--no-protel-ext", "--layers",
        ",".join(copper + ["F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask",
                           "Edge.Cuts"]))
    cli("drill", "--output", gerbers + "/", "--format", "excellon", "--drill-origin", "absolute",
        "--excellon-units", "mm", "--generate-map", "--map-format", "gerberx2")
    #assembly drawings: every reference designator, on the Fab layers
    for side, fab, extra in (("top", "F.Fab", []), ("bottom", "B.Fab", ["--mirror"])):
        cli("svg", "--mode-single", "--layers", f"{fab},Edge.Cuts",
            "--fit-page-to-board", *extra, "--exclude-drawing-sheet",
            "--sketch-pads-on-fab-layers", "--crossout-DNP-footprints-on-fab-layers",
            "--black-and-white", "--drill-shape-opt", "0", "-o",
            os.path.join(FAB, f"assembly-{side}.svg"))
    n_cu = sum(1 for f in os.listdir(gerbers) if f.endswith("_Cu.gbr"))
    if n_cu != len(copper):
        raise SystemExit(f"REFUSING: {n_cu} copper layers exported, expected {len(copper)}. "
                         "A board fabricated without its planes does not work.")
    print(f"  {n_cu} copper layers ok")

    print(f"regenerating BOM and CPL, {len(VARIANTS)} variant(s) ...")
    for v in VARIANTS:
        subprocess.run([sys.executable, os.path.abspath(__file__), "bom"]
                       + (["--economic"] if v else []), capture_output=True, check=True)
    flat = [f"{k}-{NAME}{v}.csv" for v in VARIANTS for k in ("BOM", "CPL")]
    for f in flat:
        if not os.path.exists(os.path.join(FAB, f)):
            raise SystemExit(f"REFUSING: fab/{f} is missing - the bundle would ship without it.")

    #the DNP list and the placement counts are derived from the files that ship
    bom = list(csv.DictReader(open(os.path.join(FAB, f"BOM-{NAME}.csv"))))
    dnp = [f"      {x.strip():5s} {r['Comment']}" for r in bom if r.get("DNP", "").strip()
           for x in r["Designator"].split(",") if x.strip()]
    cpl = list(csv.DictReader(open(os.path.join(FAB, f"CPL-{NAME}.csv"))))
    top = sum(1 for r in cpl if "top" in r["Layer"].lower())
    bot = sum(1 for r in cpl if "bottom" in r["Layer"].lower())
    snap = os.path.join(FAB, "stock-snapshot.json")
    if os.path.exists(snap):
        d = json.load(open(snap))
        stock = f"snapshot {d['date']}: " + ", ".join(
            f"{name} {d['lines'].get(code, {}).get('stock', '?')}"
            for code, name in getattr(design, "SOLE_SOURCE", {}).items())
    else:
        stock = "(no snapshot on disk - run fab.py stock --fetch)"
    template = os.path.join(FAB, "HOW-TO-ORDER.in")
    sheet = open(template).read() if os.path.exists(template) else \
        "Upload gerbers.zip as the PCB, and the BOM and CPL for assembly (@@SIDES@@).\n" \
        "Absent by design:\n@@DNP@@\nSole source: @@STOCK@@\n"
    w, h = outline_mm(pcbnew.LoadBoard(BOARD))
    sheet = (sheet.replace("@@SIDES@@", f"{top} top, {bot} bottom")
             .replace("@@SIZE@@", f"{w:.1f} x {h:.1f} mm")
             .replace("@@VIAS_IN_PADS@@", str(vias_in_pads(pcbnew.LoadBoard(BOARD))))
             .replace("@@DNP@@", "\n".join(dnp) or "      (none - every line in the BOM is placed)")
             .replace("@@STOCK@@", stock))
    if "@@" in sheet:
        raise SystemExit("REFUSING: unsubstituted placeholder left in HOW-TO-ORDER.txt")

    out = os.path.join(FAB, f"{NAME}-order-bundle.zip")
    with tempfile.TemporaryDirectory() as stage:
        shutil.make_archive(os.path.join(stage, "gerbers"), "zip", FAB, "gerbers")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(os.path.join(stage, "gerbers.zip"), "gerbers.zip")
            for f in flat + ["assembly-top.svg", "assembly-bottom.svg"]:
                z.write(os.path.join(FAB, f), f)
            z.writestr("HOW-TO-ORDER.txt", sheet)
    print(f"wrote {os.path.relpath(out)} ({os.path.getsize(out) // 1024}K)")
    for n in zipfile.ZipFile(out).namelist():
        print(f"  {n}")
    return 0


#render

#(parts with a body that loads, [refs without one])
def models_resolve(board):
    present, missing = 0, []
    for fp in board.GetFootprints():
        fid = fp.GetFPIDAsString()
        if 'TestPoint' in fid or 'Fiducial' in fid or fp.IsExcludedFromPosFiles():
            continue                   #bare copper: nothing is placed there to draw
        if any(os.path.exists(os.path.expandvars(m.m_Filename.replace('${JLC_LIB}', project.MODELS)))
               for m in fp.Models()):
            present += 1
        else:
            missing.append(f"{fp.GetReference()} {fid}")
    return present, missing


#usage: python3 fab.py render Render the board the way the tracked pictures are made
def run_render():
    if not os.path.isdir(os.path.join(project.MODELS, "packages3d")):
        print(f"no packages3d under {project.MODELS} - set JLC_LIB", file=sys.stderr)
        return 1
    img = os.path.join(ROOT, "docs", "img")
    os.makedirs(img, exist_ok=True)
    print("=== 1. the tracked renders ===")

    def render(out, side, *extra):
        subprocess.run(["kicad-cli", "pcb", "render", "--output", os.path.join(img, out),
                        "--side", side, "-D", f"JLC_LIB={project.MODELS}", *extra, BOARD],
                       capture_output=True)
        print(f"  docs/img/{out}")
    square = ("--width", "1400", "--height", "1400", "--quality", "high")
    pres = ("--width", "2016", "--height", "1512", "--quality", "high", "--background", "opaque",
            "--floor")
    iso = ("--rotate", "-45,0,45", "--perspective")
    render("board-top.png", "top", *square)
    render("board-bottom.png", "bottom", *square)
    render("render-top-flat.png", "top", *pres)
    render("render-bottom-flat.png", "bottom", *pres)
    render("render-iso.png", "top", *pres, *iso)
    render("render-iso-bottom.png", "bottom", *pres, *iso)

    #the layout as the pcb editor shows it, bottom up, each layer see-through
    from PIL import Image
    copper = pcb.copper(BOARD)
    alpha = {"B.Cu": .55, "F.Cu": .7, "F.Silkscreen": 1, "Edge.Cuts": 1}
    layers = copper[::-1] + ["F.Silkscreen", "Edge.Cuts"]
    bb = pcbnew.LoadBoard(BOARD).GetBoardEdgesBoundingBox()
    dpi = 760
    px = lambda mm: round(mm * dpi / 25.4)
    x0, y0 = bb.GetLeft() / 1e6 - 1.5, bb.GetTop() / 1e6 - 1.5
    w, h = bb.GetWidth() / 1e6 + 3.0, bb.GetHeight() / 1e6 + 3.0
    with tempfile.TemporaryDirectory() as lay:
        subprocess.run(["kicad-cli", "pcb", "export", "pdf", "--mode-separate", "--theme",
                        "_builtin_default", "--drill-shape-opt", "2", "--layers", ",".join(layers),
                        "-o", lay + "/", BOARD], capture_output=True)
        out = Image.new("RGBA", (px(w), px(h)), (0, 16, 35, 255))     #the editor's background
        for name in layers:
            png = os.path.join(lay, name.replace(".", "_"))
            subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-r", str(dpi),
                            "-x", str(px(x0)), "-y", str(px(y0)), "-W", str(px(w)), "-H",
                            str(px(h)), os.path.join(lay, f"{NAME}-{name.replace('.', '_')}.pdf"),
                            png], check=True)
            im = Image.open(png + ".png").convert("RGBA")
            a = alpha.get(name, .35)
            im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
            out = Image.alpha_composite(out, im)
    out = out.convert("RGB")
    out.resize((1400, round(1400 * out.height / out.width)),
               Image.LANCZOS).save(os.path.join(img, "layout.png"))
    print("  docs/img/layout.png")

    print("\n=== 2. does every body sit on its own footprint? ===")
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     "check.py"), "model_alignment"],
                       capture_output=True, text=True)
    print("\n".join([l for l in r.stdout.splitlines() if l.strip()][-4:]))

    print("\n=== 3. did any parts actually render? ===")
    present, missing = models_resolve(pcbnew.LoadBoard(BOARD))
    for m in missing:
        print(f"  no body: {m}")
    print(f"parts with a body that loads: {present}; without: {len(missing)}")
    return 1 if missing else 0


#export

#usage: python3 fab.py export Export the board to cad/<name>.step and .glb with every
def run_export():
    if not os.path.isdir(os.path.join(project.MODELS, "packages3d")):
        print(f"no packages3d under {project.MODELS}")
        return 1
    os.makedirs(os.path.join(ROOT, "cad"), exist_ok=True)
    for fmt in ("step", "glb"):
        print(f"=== {fmt}")
        subprocess.run(["kicad-cli", "pcb", "export", fmt, "--force", "--subst-models", "--no-dnp",
                        "-D", f"JLC_LIB={project.MODELS}", "--include-tracks", "--include-pads",
                        "--include-zones", "--include-silkscreen", "--include-soldermask",
                        "-o", os.path.join(ROOT, "cad", f"{NAME}.{fmt}"), BOARD], check=True)
    #a STEP without its parts is still large, so count the parts
    n = open(os.path.join(ROOT, "cad", f"{NAME}.step")).read().count("PRODUCT(")
    present, missing = models_resolve(pcbnew.LoadBoard(BOARD))
    print(f"components in the STEP: {n} products; {present} parts with a model that loads, "
          f"{len(missing)} without")
    if n <= 1 or missing:
        print("FAIL: component models missing - check JLC_LIB")
        return 1
    return 0


COMMANDS = {
    "bom": run_bom,
    "orientation": run_orientation,
    "paste": run_paste,
    "lcsc": run_lcsc,
    "offsets": run_offsets,
    "stock": run_stock,
    "variants": run_variants,
    "bundle": run_bundle,
    "check_bundle": run_check_bundle,
    "render": run_render,
    "export": run_export,
}

if __name__ == "__main__":
    sys.exit(project.main(COMMANDS, __doc__))
