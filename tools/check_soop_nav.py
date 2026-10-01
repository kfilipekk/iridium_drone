#!/usr/bin/env python3
"""Gate the on-board navigation (firmware/soop/soop_nav.c) against simulated flights.

Usage:  python3 tools/check_soop_nav.py [--quick] [--keep DIR]
"""
import csv
import json
import math
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOOP = os.path.join(ROOT, "firmware", "soop")
sys.path.insert(0, HERE)
import soop_scenario
import soop_solver as sol

TLE = os.path.join(ROOT, "sitl", "tle", "iridium-next.tle")
SRC = ["nav_host.c", "soop_guard.c", "soop_nav.c", "soop_ephem.c", "sgp4.c"]

FINE = "flow-grade velocity, 0.1 m/s"
OP = dict(orbits="operator")
#(name, seeds, scenario arguments)
FLIGHTS = (
    ("15 min denied, 15 m/s, 1-day orbits", (1, 2, 3, 4, 5, 6), OP),
    ("30 min denied", (7, 8), dict(OP, denial_min=30.0)),
    ("3-day-old orbits", (9, 10), dict(OP, tle_age_d=3.0)),
    ("hovering (static)", (11, 12), dict(OP, static=True)),
    ("10x the false bursts", (13,), dict(OP, false_rate=0.5)),
    ("a third of the bursts", (14,), dict(OP, rate=0.3)),
    ("public TLEs, the fallback", (15, 16, 17, 18), dict()),
    (FINE, (19, 20, 21, 22), dict(OP, vel_sigma=0.1)),
)
#--quick flies the design case alone
QUICK = FLIGHTS[:1]

#the spoofing guard (soop_guard.c)
SPOOF_CLEAN = (41, 42, 43, 44)
SPOOF_BACK = (55, 56, 57, 58)      #honest GPS returning after a 15 min denial
SPOOFS = (
    ("jump 500 m", (45, 46), dict(start_s=300.0, jump_m=500.0), 5.0),
    ("drag 10 m/s", (47, 48), dict(start_s=300.0, rate=10.0), 300.0),
    ("drag 5 m/s", (49, 50), dict(start_s=300.0, rate=5.0), 420.0),
    ("drag 2 m/s", (53, 54), dict(start_s=300.0, rate=2.0), 1500.0),
)

GATES = dict(median_m=400.0,       #horizontal error over every denied second, all flights
             p95_m=1200.0,
             max_m=2500.0,
             within2_min=0.90,     #fixes inside 2 x reported hacc (a 2-D Gaussian gives 0.86+)
             avail_min=0.95,       #denied seconds with a valid fix
             wrong_max=0.002,      #fused bursts credited to the wrong satellite or channel
             false_max=0.02,       #false bursts that got fused
             #the way toward 20 m (docs/IRIDIUM-RESEARCH.md)
             fine_median_m=60.0,
             fine_p95_m=200.0)


def build(tmp):
    """Host and H743 builds, both with ArduPilot's -fsingle-precision-constant."""
    exe = os.path.join(tmp, "nav_host")
    r = subprocess.run(["cc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Wshadow", "-Werror", "-pedantic",
                        "-fsingle-precision-constant", "-o", exe]
                       + [os.path.join(SOOP, f) for f in SRC] + ["-lm"],
                       capture_output=True, text=True)
    if r.returncode:
        return None, r.stderr
    sizes = []
    for f in ("soop_guard.c", "soop_nav.c", "soop_ephem.c", "sgp4.c"):
        obj = os.path.join(tmp, f[:-2] + ".o")
        r = subprocess.run(["arm-none-eabi-gcc", "-c", "-O2", "-std=c99", "-Wall", "-Wextra",
                            "-Werror", "-mcpu=cortex-m7", "-mthumb", "-mfpu=fpv5-d16",
                            "-mfloat-abi=hard", "-fsingle-precision-constant", "-o", obj,
                            os.path.join(SOOP, f)],
                           capture_output=True, text=True)
        if r.returncode:
            return exe, "arm: " + r.stderr
        sz = subprocess.run(["arm-none-eabi-size", obj], capture_output=True, text=True).stdout
        sizes.append(int(sz.splitlines()[1].split()[0]))
    #the navigation's RAM is one soop_guard_t (two filters); ask the compiler
    probe = os.path.join(tmp, "probe.c")
    open(probe, "w").write('#include "soop_guard.h"\nunsigned long nav_size = sizeof(soop_guard_t);\n')
    r = subprocess.run(["arm-none-eabi-gcc", "-c", "-O2", "-std=c99", "-I", SOOP,
                        "-mcpu=cortex-m7", "-mthumb", "-o", probe + ".o", probe,
                        "-mfpu=fpv5-d16", "-mfloat-abi=hard"], capture_output=True, text=True)
    ram = None
    if r.returncode == 0:
        d = subprocess.run(["arm-none-eabi-objdump", "-s", "-j", ".data", probe + ".o"],
                           capture_output=True, text=True).stdout
        words = [ln.split()[1] for ln in d.splitlines() if ln.startswith(" 0000")]
        if words:
            ram = int.from_bytes(bytes.fromhex(words[0]), "little")
    return exe, (sum(sizes), ram)


def check_ephemeris(exe):
    """C against Python on every satellite at three times."""
    tles = {s.satnum: s for _, s, _ in sol.load_tles()}
    t0 = max(ep for _, _, ep in sol.load_tles())
    ts = []
    import datetime
    for h in (0.0, 13.7, 49.3):
        dt = t0 + datetime.timedelta(hours=h)
        jd, fr = sol._jday(dt)
        ts.append(((jd - sol.J2000) + fr) * 86400.0)
    out = subprocess.run([exe, TLE, "--ephem"] + [f"{t:.3f}" for t in ts],
                         capture_output=True, text=True).stdout.split("\n")
    worst_r = worst_v = 0.0
    n = 0
    for ln in out:
        p = ln.split()
        if len(p) != 9:
            continue
        num, t = int(p[1]), float(p[2])
        dt = sol._jd_to_datetime(sol.J2000 + t / 86400.0)
        ref = sol.sat_state_ecef(tles[num], dt)
        worst_r = max(worst_r, math.dist(ref[0], [float(x) for x in p[3:6]]))
        worst_v = max(worst_v, math.dist(ref[1], [float(x) for x in p[6:9]]))
        n += 1
    #Vallado (AIAA 2006-6753) at 07:51:28.386009 UTC, UT1 = UTC - 0.4399619 s
    jd, fr = 2453101.5, (7 * 3600 + 51 * 60 + 28.386009 - 0.4399619) / 86400.0
    t_ut1 = ((jd - sol.J2000) + fr) * 86400.0
    e = subprocess.run([exe, TLE, "--teme", f"{t_ut1:.6f}", "5094180.16210", "6127644.65950",
                        "6380344.53270", "-4746.131487", "785.818041", "5531.931288"],
                       capture_output=True, text=True).stdout.split()
    dr = math.dist([float(x) for x in e[1:4]], (-1033479.3830, 7901295.2754, 6380356.5958))
    dv = math.dist([float(x) for x in e[4:7]], (-3225.636520, -2872.451450, 5531.924446))
    ok = n >= 200 and worst_r < 1.0 and worst_v < 1e-3 and dr < 50.0 and dv < 0.1
    return ok, (f"C ephemeris = Python on {n} satellite-epochs to {worst_r * 1000:.0f} mm, "
                f"{worst_v * 1e6:.0f} um/s; Vallado example {dr:.1f} m, {dv * 1000:.0f} mm/s")


def cat_age(exe, t_utc):
    """soop_nav's view of the catalogue at UTC t_utc (s since J2000)."""
    out = subprocess.run([exe, TLE, "--cat-age", f"{t_utc:.1f}"], capture_output=True,
                         text=True).stdout.split()
    return int(out[1]), float(out[3])


def check_catalogue_age(exe):
    """A catalogue whose newest epoch is past max_tle_age_d (7 d) must be reported stale."""
    _, newest = cat_age(exe, 0.0)
    if newest <= 0.0:
        return False, "could not read the catalogue's newest epoch"
    cases = ((1.0, 0), (6.0, 0), (8.0, 1), (30.0, 1))
    got = [(d, cat_age(exe, newest + d * 86400.0)[0], want) for d, want in cases]
    ok = all(g == w for _, g, w in got)
    return ok, ("catalogue staleness vs max_tle_age_d 7: "
                + ", ".join(f"+{d:.0f}d={g}" for d, g, _ in got)
                + " (want 0,0,1,1)")


def blind_start(exe, tmp, seed=31):
    """A flight whose GPS never came: the filter starts from a guess 5 km out."""
    d = os.path.join(tmp, "blind")
    soop_scenario.make_obs(d, seed=seed, gps_min=0.5, denial_min=10.0)
    lines = open(os.path.join(d, "obs.txt")).read().splitlines()
    g0 = next(ln for ln in lines if ln.startswith("G")).split()
    guess = [float(v) + 3000.0 for v in g0[3:6]]
    out = [ln for ln in lines if ln.startswith("H")]
    out += [f"U {g0[1]} {g0[2]}", "P %s %.3f %.3f %.3f 7500" % (g0[1], *guess)]
    out += [ln for ln in lines if ln[0] in "EAD"]
    log = os.path.join(d, "blind.txt")
    open(log, "w").write("\n".join(out) + "\n")
    r = subprocess.run([exe, os.path.join(d, "iridium.tle"), log], capture_output=True,
                       text=True)
    rows = [ln.split(",") for ln in r.stdout.splitlines() if ln.startswith("F,")]
    return sum(int(p[12]) for p in rows), len(rows)


def fly(exe, tmp, name, seed, kw):
    d = os.path.join(tmp, f"flight_{seed}")
    truth = soop_scenario.make_obs(d, seed=seed, **kw)
    #the filter assumes half as much again of the velocity error as the flight has
    vel = ["--vel-sigma", f"{1.5 * kw['vel_sigma']:g}"] if "vel_sigma" in kw else []
    r = subprocess.run([exe, os.path.join(d, "iridium.tle"), os.path.join(d, "obs.txt")] + vel,
                       capture_output=True, text=True)
    rows = list(csv.reader(r.stdout.splitlines()[1:]))
    track = truth["track"]
    tb = [p["board"] for p in track]
    t_den = next(p["board"] for p in track if p["t"] >= truth["gps_s"])

    fixes, errs, within, valid = [], [], 0, 0
    j = 0
    for row in rows:
        if row[0] != "F":
            continue
        t = float(row[1])
        if t < t_den or t > tb[-1]:
            continue
        while j < len(tb) - 2 and tb[j + 1] <= t:
            j += 1
        w = (t - tb[j]) / (tb[j + 1] - tb[j])
        la, lo = (track[j][k] + w * (track[j + 1][k] - track[j][k]) for k in ("lat", "lon"))
        dn = math.radians(float(row[2]) - la) * 6371000.0
        de = math.radians(float(row[3]) - lo) * 6371000.0 * math.cos(math.radians(la))
        e = math.hypot(dn, de)
        fixes.append((t - t_den, e, float(row[8]), int(row[12])))
        if int(row[12]):
            valid += 1
            errs.append(e)
            within += e < 2.0 * float(row[8])
    alarms = sum(1 for row in rows if row[0] == "F" and int(row[13]) == 3)
    m = re.search(r"gps jumps (\d+)", r.stderr)
    alarms += int(m.group(1)) if m else 1
    bursts = [row for row in rows if row[0] == "B"]
    fused = wrong = false_fused = n_false = 0
    for row, b in zip(bursts, truth["bursts"]):
        n_false += b["false"]
        if int(row[2]) != 0:
            continue
        fused += 1
        if b["false"]:
            false_fused += 1
        elif (int(row[3]), int(row[4])) != (b["sat"], b["ch"]):
            wrong += 1
    return dict(name=name, seed=seed, errs=errs, within=within, valid=valid, n=len(fixes),
                final=fixes[-1][1] if fixes else float("nan"), fused=fused, wrong=wrong,
                false_fused=false_fused, n_false=n_false, alarms=alarms, stderr=r.stderr.strip())


def spoof_flight(exe, tmp, name, seed, spoof, **kw):
    """One flight on GPS throughout, armed at 60 s, optionally spoofed."""
    d = os.path.join(tmp, f"spoof_{seed}")
    kw = dict(dict(gps_min=30.0, denial_min=0.0), **kw)
    truth = soop_scenario.make_obs(d, seed=seed, orbits="operator", spoof=spoof, **kw)
    r = subprocess.run([exe, os.path.join(d, "iridium.tle"), os.path.join(d, "obs.txt")],
                       capture_output=True, text=True)
    track = truth["track"]
    tb = [p["board"] for p in track]
    t_sp = truth["boot"] + (spoof["start_s"] if spoof else 1e9)
    seen, early, errs, j = None, 0, [], 0
    for row in (ln.split(",") for ln in r.stdout.splitlines() if ln.startswith("F,")):
        t, state = float(row[1]), int(row[13])
        if state == 3 and seen is None:
            if t < t_sp:
                early += 1
            else:
                seen = t - t_sp
        if seen is not None and t <= tb[-1]:
            while j < len(tb) - 2 and tb[j + 1] <= t:
                j += 1
            w = (t - tb[j]) / (tb[j + 1] - tb[j])
            la, lo = (track[j][k] + w * (track[j + 1][k] - track[j][k]) for k in ("lat", "lon"))
            dn = math.radians(float(row[2]) - la) * 6371000.0
            de = math.radians(float(row[3]) - lo) * 6371000.0 * math.cos(math.radians(la))
            errs.append(math.hypot(dn, de))
    m = re.search(r"gps jumps (\d+)", r.stderr)
    if not spoof:
        early += int(m.group(1)) if m else 1
    return seen, early, errs


def check_spoofing(exe, tmp):
    lines, good = [], True
    alarms = sum(spoof_flight(exe, tmp, "clean", s, None)[1] for s in SPOOF_CLEAN)
    ok = alarms == 0
    good &= ok
    lines.append(f"  {'ok  ' if ok else 'FAIL'}  {len(SPOOF_CLEAN)} flights on honest GPS for 30 "
                 f"minutes: {alarms} spoofing alarm(s)")
    alarms = sum(spoof_flight(exe, tmp, "back", s, None, gps_min=5.0, denial_min=15.0,
                              back_min=5.0)[1] for s in SPOOF_BACK)
    ok = alarms == 0
    good &= ok
    lines.append(f"  {'ok  ' if ok else 'FAIL'}  {len(SPOOF_BACK)} flights whose honest GPS comes "
                 f"back after a 15 minute denial: {alarms} spoofing alarm(s)")
    for name, seeds, spoof, deadline in SPOOFS:
        res = [spoof_flight(exe, tmp, name, s, spoof) for s in seeds]
        lat = [r[0] for r in res]
        ok = all(x is not None and x <= deadline for x in lat) and not any(r[1] for r in res)
        good &= ok
        moved = [spoof.get("jump_m", 0.0) + spoof.get("rate", 0.0) * x for x in lat
                 if x is not None]
        lines.append(f"  {'ok  ' if ok else 'FAIL'}  spoofer, {name}: caught after "
                     f"{', '.join('never' if x is None else f'{x:.0f} s' for x in lat)} "
                     f"(limit {deadline:.0f} s), the GPS by then {max(moved or [0]):.0f} m off"
                     + (f"; the fix after it is {pct([e for r in res for e in r[2]], 0.5):.0f} m "
                        f"median from the truth" if "jump_m" in spoof and any(r[2] for r in res)
                        else ""))
    lines.append("        (after a drag is caught the simulation still feeds the dragged EKF velocity,")
    lines.append("        which the aircraft stops using once it drops the GPS - so it is not measured)")
    return good, lines


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else float("inf")


def main():
    keep = sys.argv[sys.argv.index("--keep") + 1] if "--keep" in sys.argv else None
    flights = QUICK if "--quick" in sys.argv else FLIGHTS
    print("=== on-board Iridium navigation against simulated GNSS-denied flights ===")
    checks = []
    tmp = keep or tempfile.mkdtemp(prefix="soop_nav_")
    os.makedirs(tmp, exist_ok=True)
    exe, info = build(tmp)
    ok = exe is not None and not isinstance(info, str)
    checks.append(ok)
    if not ok:
        print(f"  FAIL  build: {str(info).strip()[:400]}")
        return 1
    text, ram = info
    print(f"  ok    builds on the host with -Werror -pedantic, and for the H743 "
          f"(text {text} B, filter state {ram} B)")

    good, msg = check_ephemeris(exe)
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  {msg}")

    good, msg = check_catalogue_age(exe)
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  {msg}")

    results = []
    print(f"    {'flight':34s} {'median':>7s} {'p95':>7s} {'max':>7s} {'final':>7s} "
          f"{'in 2 hacc':>9s} {'valid':>6s} {'fused':>6s} {'wrong':>5s}")
    for name, seeds, kw in flights:
        rs = [fly(exe, tmp, name, s, kw) for s in seeds]
        results += rs
        e = [x for r in rs for x in r["errs"]]
        n = sum(r["n"] for r in rs)
        print(f"    {name:34s} {pct(e, 0.5):6.0f}m {pct(e, 0.95):6.0f}m {max(e or [0]):6.0f}m "
              f"{pct([r['final'] for r in rs], 0.5):6.0f}m "
              f"{sum(r['within'] for r in rs) / max(1, len(e)):9.1%} "
              f"{sum(r['valid'] for r in rs) / max(1, n):6.1%} {sum(r['fused'] for r in rs):6d} "
              f"{sum(r['wrong'] for r in rs):5d}")

    g = GATES
    e = [x for r in results for x in r["errs"]]
    n = sum(r["n"] for r in results)
    within = sum(r["within"] for r in results) / max(1, len(e))
    avail = sum(r["valid"] for r in results) / max(1, n)
    fused = sum(r["fused"] for r in results)
    wrong = sum(r["wrong"] for r in results)
    ff, nf = sum(r["false_fused"] for r in results), sum(r["n_false"] for r in results)
    for good, text in (
            (pct(e, 0.5) <= g["median_m"] and pct(e, 0.95) <= g["p95_m"]
             and max(e or [1e9]) <= g["max_m"],
             f"horizontal error over {len(e)} denied seconds: median {pct(e, 0.5):.0f} m, "
             f"p95 {pct(e, 0.95):.0f} m, max {max(e or [0]):.0f} m (limits {g['median_m']:.0f} / "
             f"{g['p95_m']:.0f} / {g['max_m']:.0f})"),
            (within >= g["within2_min"], f"{within:.1%} of fixes inside 2 x their reported "
             f"accuracy (need {g['within2_min']:.0%}): the flight EKF can trust hacc"),
            (avail >= g["avail_min"], f"a valid fix for {avail:.1%} of denied seconds "
             f"(need {g['avail_min']:.0%})"),
            (wrong <= g["wrong_max"] * fused, f"{wrong} of {fused} fused bursts credited to the "
             f"wrong satellite or channel (limit {g['wrong_max']:.1%})"),
            (ff <= g["false_max"] * max(1, nf), f"{ff} of {nf} false bursts fused "
             f"(limit {g['false_max']:.0%})")):
        checks.append(good)
        print(f"  {'ok  ' if good else 'FAIL'}  {text}")

    fine = [x for r in results if r["name"] == FINE for x in r["errs"]]
    if fine:
        good = pct(fine, 0.5) <= g["fine_median_m"] and pct(fine, 0.95) <= g["fine_p95_m"]
        checks.append(good)
        print(f"  {'ok  ' if good else 'FAIL'}  with 0.1 m/s velocity: median {pct(fine, 0.5):.0f} m, "
              f"p95 {pct(fine, 0.95):.0f} m (limits {g['fine_median_m']:.0f} / "
              f"{g['fine_p95_m']:.0f}): the filter keeps what a better velocity gives it")

    al = sum(r["alarms"] for r in results)
    checks.append(al == 0)
    print(f"  {'ok  ' if al == 0 else 'FAIL'}  the spoofing guard raised {al} alarm(s) and "
          f"rejected no GPS fix across {len(results)} honest flights")

    if "--quick" not in sys.argv:
        good, lines = check_spoofing(exe, tmp)
        checks.append(good)
        for ln in lines:
            print(ln)

    nv, nf = blind_start(exe, tmp)
    checks.append(nf > 0 and nv == 0)
    print(f"  {'ok  ' if nv == 0 and nf else 'FAIL'}  with no GPS and no surveyed start, {nv} of {nf} "
          f"fixes offered: it does not hand the EKF a position it cannot vouch for")

    print("\n  NOTE: simulated flights. What they cannot settle: the real burst rate and C/N0 on")
    print("  the aircraft, how the real TCXO drifts with temperature, how far Iridium's own")
    print("  orbits are off, and the satellites' real transmit offsets. The bench recordings and T3b measure")
    print("  those, and the filter's parameters (soop_nav_default_cfg) are where they go.")
    ok = all(checks)
    print("\n" + (f"SOOP-NAV OK - {sum(checks)}/{len(checks)} assertions" if ok else
                  f"SOOP-NAV FAILED - {len(checks) - sum(checks)} of {len(checks)} assertions"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
