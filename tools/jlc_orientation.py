#!/usr/bin/env python3
"""Solve each part's JLCPCB rotation and centre from JLCPCB's own footprint, not a table.

Usage:
  python3 tools/jlc_orientation.py --fetch [--refresh]   # download JLC's footprints
  python3 tools/jlc_orientation.py           # report the solved rotation and offset per part
"""
import json, math, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb")
CACHE = os.path.join(REPO, "libraries", "jlc_footprints.json")
APIS = ["https://easyeda.com/api/products/{}/components?version=6.4.19.5",
        "https://lceda.cn/api/products/{}/components?version=6.4.19.5"]
UNIT = 0.254              # EasyEDA footprint units are 10 mil
# The fit is accepted when its RMS residual is under a quarter of the pattern's own RMS radius.
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
    # One centre per number: shield tabs and split thermal pads repeat a number.
    return {"package": pkg["title"],
            "pads": {n: [round(sum(p[0] for p in v) / len(v), 4),
                         round(sum(p[1] for p in v) / len(v), 4)] for n, v in pads.items()}}


def board_codes():
    import design
    return sorted({c[3] for c in design.COMPONENTS.values()
                   if c[3] and str(c[3]).startswith("C") and not str(c[3]).startswith("LOOKUP")})


def fetch(refresh=False):
    """Resumable: codes already in the cache are skipped unless --refresh. Stops after
    three refusals in a row - both hosts rate-limit, and pressing on only extends the
    ban (the first full run earned 403s from one and 418s from the other).
    """
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
    print(f"wrote {os.path.relpath(CACHE, REPO)} ({len(db)} footprints"
          + (f", {len(missing)} still to fetch)" if missing else ", complete)"))


def load():
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def fit(src, dst):
    """Rigid 2D fit dst ~ R(a) src + t over matched points. Returns (deg, t, rms). R is the
    ordinary maths rotation in whatever frame the points are given in.
    """
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


def _accept(src, dst):
    """fit() plus the RESIDUAL_RATIO test; (deg, t, rms) or None."""
    # Two distinct pad centres fix an angle; fewer (or all coincident) do not.
    if len(src) < 2 or max(math.dist(src[0], p) for p in src) < 0.05:
        return None
    deg, t, rms = fit(src, dst)
    cx, cy = sum(p[0] for p in src) / len(src), sum(p[1] for p in src) / len(src)
    radius = math.sqrt(sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in src) / len(src))
    return (deg, t, rms) if rms <= RESIDUAL_RATIO * radius else None


def _by_geometry(epads, opads):
    """Fallback for footprints that number their pads differently - J12's U.FL calls both
    ground pads "2", JLC's calls them 2 and 3.
    """
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


def solve(fp, entry):
    """(rotation_deg, (mid_x_mm, mid_y_mm), rms_mm, n_pads) for one placed footprint, or
    None when the pads cannot be matched well enough to trust.
    """
    import pcbnew
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
    epads = [(n, (ex, -ey)) for n, (ex, ey) in entry["pads"].items()]  # EasyEDA is y-down
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
    # EasyEDA origin (0,0) lands at t in the fitted frame; undo the bottom mirror.
    mx = -tx if bottom else tx
    return round(deg, 3) % 360.0, (mx, ty), rms, n_used


def main():
    if "--fetch" in sys.argv:
        fetch(refresh="--refresh" in sys.argv)
        return 0
    import pcbnew, design
    db = load()
    if not db:
        print(f"no {os.path.relpath(CACHE, REPO)} - run with --fetch first")
        return 1
    b = pcbnew.LoadBoard(BOARD)
    import gen_bom
    rows, unsolved = [], []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        c = design.COMPONENTS.get(ref)
        if not c or not c[3] or c[3] not in db:
            continue
        s = solve(fp, db[c[3]])
        old = gen_bom.cpl_rotation(fp)[0]
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


if __name__ == "__main__":
    sys.exit(main())
