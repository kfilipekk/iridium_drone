#!/usr/bin/env python3
"""Doppler positioning from signals of opportunity: the solver, and proof it works."""
import datetime
import math
import os
import random
import sys

C = 299_792_458.0
F_IRIDIUM = 1_626_270_000.0      # Ring Alert channel, Hz
R_EARTH = 6_378_137.0
MU = 3.986004418e14              # WGS84 gravitational parameter
IRIDIUM_ALT = 780_000.0
IRIDIUM_INC = math.radians(86.4)


# ----------------------------------------------------------------- linear algebra
def solve4(A, b):
    """Gauss-Jordan with partial pivoting on a small dense system. Returns None if singular
    - a degenerate geometry must report failure, not a plausible number.
    """
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        p = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[p][col]) < 1e-12:
            return None
        M[col], M[p] = M[p], M[col]
        piv = M[col][col]
        M[col] = [v / piv for v in M[col]]
        for r in range(n):
            if r != col and M[r][col] != 0.0:
                f = M[r][col]
                M[r] = [v - f * w for v, w in zip(M[r], M[col])]
    return [M[i][n] for i in range(n)]


def normal_equations(H, y, w=None):
    """Form H^T W H and H^T W y for a weighted least-squares step."""
    m, n = len(H), len(H[0])
    w = w or [1.0] * m
    A = [[sum(w[k] * H[k][i] * H[k][j] for k in range(m)) for j in range(n)]
         for i in range(n)]
    b = [sum(w[k] * H[k][i] * y[k] for k in range(m)) for i in range(n)]
    return A, b


# ----------------------------------------------------------------- geometry
def geodetic_to_ecef(lat_deg, lon_deg, h):
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    a, f = R_EARTH, 1 / 298.257223563
    e2 = f * (2 - f)
    N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return ((N + h) * math.cos(lat) * math.cos(lon),
            (N + h) * math.cos(lat) * math.sin(lon),
            (N * (1 - e2) + h) * math.sin(lat))


def circular_orbit(t, raan, arg0, alt=IRIDIUM_ALT, inc=IRIDIUM_INC):
    """Position and velocity of a satellite on a circular orbit, in an inertial frame. Good
    enough to invert the geometry; not an ephemeris.
    """
    r = R_EARTH + alt
    n = math.sqrt(MU / r ** 3)
    u = arg0 + n * t
    # in-plane, then rotate by inclination and RAAN
    px, py = r * math.cos(u), r * math.sin(u)
    vx, vy = -r * n * math.sin(u), r * n * math.cos(u)
    ci, si = math.cos(inc), math.sin(inc)
    px2, py2, pz2 = px, py * ci, py * si
    vx2, vy2, vz2 = vx, vy * ci, vy * si
    cr, sr = math.cos(raan), math.sin(raan)
    return ((px2 * cr - py2 * sr, px2 * sr + py2 * cr, pz2),
            (vx2 * cr - vy2 * sr, vx2 * sr + vy2 * cr, vz2))


def range_rate(rs, vs, rr, vr=(0.0, 0.0, 0.0)):
    d = [rs[i] - rr[i] for i in range(3)]
    rho = math.sqrt(sum(x * x for x in d))
    u = [x / rho for x in d]
    return sum((vs[i] - vr[i]) * u[i] for i in range(3)), rho, u


def predict_df(rs, vs, rr, clock_hz, f_tx=F_IRIDIUM):
    """Observed frequency offset from nominal. clock_hz is the receiver's oscillator error
    expressed at the carrier, in Hz - see the header on why not a fraction.
    """
    rdot, _, _ = range_rate(rs, vs, rr)
    return f_tx * (-rdot / C) + clock_hz


# ----------------------------------------------------------------- the solve
def solve(obs, guess, f_tx=F_IRIDIUM, iters=40, tol=1e-4):
    """obs: list of (r_sat, v_sat, df_measured). guess: (x, y, z, delta)."""
    x = list(guess)
    for it in range(iters):
        H, y = [], []
        for rs, vs, df in obs:
            rdot, rho, u = range_rate(rs, vs, (x[0], x[1], x[2]))
            pred = f_tx * (-rdot / C) + x[3]
            y.append(df - pred)
            # d(df)/d(r_rx) = (f_tx/c) * (v_sat)^T (I - u u^T) / rho ; d/d(clock) = 1
            vdotu = sum(vs[i] * u[i] for i in range(3))
            row = [(f_tx / C) * (vs[i] - vdotu * u[i]) / rho for i in range(3)]
            row.append(1.0)
            H.append(row)
        A, b = normal_equations(H, y)
        step = solve4(A, b)
        if step is None:
            return None, None, it
        for i in range(4):
            x[i] += step[i]
        if max(abs(s) for s in step[:3]) < tol:
            break
    rms = math.sqrt(sum((df - predict_df(rs, vs, (x[0], x[1], x[2]), x[3])) ** 2
                        for rs, vs, df in obs) / len(obs))
    return x, rms, it + 1


# ----------------------------------------------------------------- the self-test
def constellation(t, n_planes=6, per_plane=11):
    """Iridium-like: 6 planes, 11 satellites each, near-polar. Positions only - this is a
    geometry generator, not an ephemeris. See the header.
    """
    out = []
    for p in range(n_planes):
        raan = 2 * math.pi * p / n_planes
        for k in range(per_plane):
            arg0 = 2 * math.pi * k / per_plane + (math.pi / per_plane) * (p % 2)
            out.append(circular_orbit(t, raan, arg0))
    return out


def visible(rs, rr, min_elev_deg=8.0):
    """Elevation above the local horizon at the receiver."""
    d = [rs[i] - rr[i] for i in range(3)]
    rho = math.sqrt(sum(x * x for x in d))
    rmag = math.sqrt(sum(x * x for x in rr))
    up = [rr[i] / rmag for i in range(3)]
    sin_el = sum(d[i] * up[i] for i in range(3)) / rho
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_el)))) >= min_elev_deg


def make_pass(rr_true, clock_hz, n_obs, sigma_hz, seed, span_s=600.0):
    """n_obs usable observations - ones from satellites actually above 8 degrees."""
    rng = random.Random(seed)
    obs, tries, t = [], 0, 0.0
    step = span_s / max(1, n_obs)
    while len(obs) < n_obs and tries < n_obs * 40:
        tries += 1
        sats = constellation(t)
        vis = [(rs, vs) for rs, vs in sats if visible(rs, rr_true)]
        if vis:
            rs, vs = vis[rng.randrange(len(vis))]
            df = predict_df(rs, vs, rr_true, clock_hz) + rng.gauss(0, sigma_hz)
            obs.append((rs, vs, df))
        t += step
    return obs


def run(sigma_hz, n_obs, seed, verbose=False):
    lat, lon, h = 52.2053, 0.1218, 60.0          # Cambridge
    rr = geodetic_to_ecef(lat, lon, h)
    clock_hz = 2.5e-6 * F_IRIDIUM                # the TCXO's +-2.5 ppm at the carrier
    obs = make_pass(rr, clock_hz, n_obs, sigma_hz, seed)
    if len(obs) < 6:
        return None
    guess = (rr[0] + 50_000, rr[1] - 50_000, rr[2] + 50_000, 0.0)
    x, rms, it = solve(obs, guess)
    if x is None:
        return None
    err = math.sqrt(sum((x[i] - rr[i]) ** 2 for i in range(3)))
    if verbose:
        print(f"    {len(obs):3d} obs, sigma {sigma_hz:5.1f} Hz -> "
              f"{err:8.1f} m, clock {x[3]:+9.1f} Hz (true {clock_hz:+.1f}), "
              f"resid {rms:5.1f} Hz, {it} iters")
    return err


# ----------------------------------------------------------------- real ephemeris

TLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "sitl", "tle", "iridium-next.tle")
OMEGA_EARTH = 7.2921150e-5        # rad/s, WGS84 nominal rotation rate
J2000 = 2451545.0


def _satrec_class():
    """The SGP4 propagator, or a refusal."""
    try:
        from sgp4.api import Satrec
    except ImportError as e:
        raise RuntimeError(
            "the SGP4 propagator is not installed, so the real ephemeris cannot run. "
            "Install it (`pip install sgp4`). Do NOT fall back to the synthetic "
            "circular propagator for anything downstream of this tool.") from e
    return Satrec


def _jday(dt):
    from sgp4.api import jday
    return jday(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                dt.second + dt.microsecond * 1e-6)


def _jd_to_datetime(jd):
    """Julian date -> aware UTC datetime (Fliegel-Van Flandern)."""
    jd += 0.5
    Z, F = int(jd), jd - int(jd)
    alpha = int((Z - 1867216.25) / 36524.25)
    A = Z + 1 + alpha - alpha // 4 if Z >= 2299161 else Z
    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E = int((B - D) / 30.6001)
    day = B - D - int(30.6001 * E) + F
    month = E - 1 if E < 14 else E - 13
    year = C - 4716 if month > 2 else C - 4715
    d, frac = int(day), day - int(day)
    return (datetime.datetime(year, month, d, tzinfo=datetime.timezone.utc)
            + datetime.timedelta(days=frac))


def load_tles(path=TLE_PATH):
    """Parse the vendored catalogue, skipping '#' provenance lines. Returns [(name, satrec,
    epoch_datetime), ...].
    """
    Satrec = _satrec_class()
    path = os.path.normpath(path)
    if not os.path.exists(path):
        raise RuntimeError(f"no TLE catalogue at {path} - run "
                           f"`bash sitl/tle/fetch_iridium_tle.sh`")
    lines = [ln.rstrip("\r") for ln in open(path)]
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) \
                and lines[i + 1].startswith("2 "):
            name = lines[i - 1].strip() if i > 0 else "?"
            sat = Satrec.twoline2rv(lines[i], lines[i + 1])
            out.append((name, sat, _jd_to_datetime(sat.jdsatepoch + sat.jdsatepochF)))
            i += 2
        else:
            i += 1
    if len(out) < 60:
        raise RuntimeError(f"only {len(out)} satellites in {path}; the full Iridium NEXT "
                           f"constellation is ~80 and a short catalogue narrows the "
                           f"geometry silently")
    return out


def gmst_rad(jd):
    """Greenwich Mean Sidereal Time, IAU 1982 (UT1 ~ UTC to well inside this budget).
    Returns radians. At J2000.0 the result is 280.46061837 deg.
    """
    d = jd - J2000
    T = d / 36525.0
    g = (280.46061837 + 360.98564736629 * d
         + 0.000387933 * T * T - T * T * T / 38710000.0)
    return math.radians(g % 360.0)


def teme_to_ecef(r, v, theta):
    """Rotate a TEME state into Earth-fixed coordinates at Greenwich sidereal angle
    `theta`. r, v in metres; returns (r_ecef, v_ecef).
    """
    c, s = math.cos(theta), math.sin(theta)
    rx = c * r[0] + s * r[1]
    ry = -s * r[0] + c * r[1]
    vz = v[2]
    vx = c * v[0] + s * v[1]
    vy = -s * v[0] + c * v[1]
    return (rx, ry, r[2]), (vx + OMEGA_EARTH * ry, vy - OMEGA_EARTH * rx, vz)


def ecef_to_teme(r, v, theta):
    """Inverse of teme_to_ecef: Rz(-theta) with the Earth-rotation term added back. Exists
    so the round trip can be asserted rather than assumed.
    """
    c, s = math.cos(theta), math.sin(theta)
    vx, vy = v[0] - OMEGA_EARTH * r[1], v[1] + OMEGA_EARTH * r[0]
    return ((c * r[0] - s * r[1], s * r[0] + c * r[1], r[2]),
            (c * vx - s * vy, s * vx + c * vy, v[2]))


def sat_eci(sat, dt):
    """TEME position and velocity in METRES. python-sgp4 returns km, and mixing the two
    units is a silent factor-of-1000 error in every range rate, so the conversion lives
    here and nowhere else.
    """
    jd, fr = _jday(dt)
    e, r, v = sat.sgp4(jd, fr)
    if e != 0:
        return None                       # sgp4 error codes: decayed, bad elements
    return ((r[0] * 1000.0, r[1] * 1000.0, r[2] * 1000.0),
            (v[0] * 1000.0, v[1] * 1000.0, v[2] * 1000.0))


def sat_state_ecef(sat, dt):
    """(r, v) in the Earth-fixed frame, metres and m/s, or None if SGP4 fails."""
    s = sat_eci(sat, dt)
    if s is None:
        return None
    jd, _ = _jday(dt)
    return teme_to_ecef(s[0], s[1], gmst_rad(jd))


def tle_observations(tles, rr_true, t0, clock_hz, n_obs, sigma_hz, seed,
                     span_s=1800.0, min_elev_deg=8.0):
    """n_obs usable observations from real orbits. Each carries the satellite's ECEF state
    and the Doppler the true receiver would measure, plus noise. No satellite state is
    supplied by the caller - that is the point.
    """
    rng = random.Random(seed)
    obs, steps = [], n_obs * 12
    for k in range(steps):
        if len(obs) >= n_obs:
            break
        t = t0 + datetime.timedelta(seconds=span_s * k / max(1, steps - 1))
        vis = []
        for _, sat, _ in tles:
            st = sat_state_ecef(sat, t)
            if st and visible(st[0], rr_true, min_elev_deg):
                vis.append(st)
        if not vis:
            continue
        rs, vs = vis[rng.randrange(len(vis))]
        obs.append((rs, vs, predict_df(rs, vs, rr_true, clock_hz) + rng.gauss(0, sigma_hz)))
    return obs


def run_tle(tles, sigma_hz, n_obs, seed, span_s=1800.0, verbose=False):
    """Recover a known position from observations built from real TLE orbits."""
    lat, lon, h = 52.2053, 0.1218, 60.0          # Cambridge
    rr = geodetic_to_ecef(lat, lon, h)
    clock_hz = 2.5e-6 * F_IRIDIUM               # the TCXO's +-2.5 ppm at the carrier
    t0 = max(ep for _, _, ep in tles)            # the freshest epoch in the catalogue
    obs = tle_observations(tles, rr, t0, clock_hz, n_obs, sigma_hz, seed, span_s)
    if len(obs) < 6:
        return None, len(obs)
    guess = (rr[0] + 50_000.0, rr[1] - 50_000.0, rr[2] + 50_000.0, 0.0)
    x, rms, it = solve(obs, guess)
    if x is None:
        return None, len(obs)
    err = math.sqrt(sum((x[i] - rr[i]) ** 2 for i in range(3)))
    if verbose:
        print(f"    {len(obs):3d} obs, sigma {sigma_hz:5.1f} Hz -> {err:8.1f} m, "
              f"clock {x[3]:+9.1f} Hz (true {clock_hz:+.1f}), resid {rms:5.1f} Hz, "
              f"{it} iters")
    return err, len(obs)


def ephemeris_test(seeds=6, sigma_hz=5.0, n_obs=60, fail_m=1000.0):
    """Validate the real-ephemeris path: the propagator, the frames, and an end-to-end
    position recovery from real orbits. Prints a report and returns a result dict: {ok,
    checks: (passed, total), n_sats, median_m}.
    """
    print("=== real ephemeris: SGP4 + TEME->ECEF, against the vendored catalogue ===")
    tles = load_tles()
    print(f"  ok    {len(tles)} satellites loaded, freshest epoch "
          f"{max(ep for _, _, ep in tles).isoformat()}")
    checks = []

    # 1. GMST anchor: the accepted value at J2000.0 is 280.46061837 deg.
    g = math.degrees(gmst_rad(J2000))
    good = abs(g - 280.46061837) < 1e-6
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  GMST at J2000.0 = {g:.8f} deg "
          f"(expected 280.46061837)")

    # 2. The propagator puts every satellite in a plausible Iridium orbit, and the ECEF
    #    speed differs from the inertial speed by the Earth-rotation term.
    t0 = max(ep for _, _, ep in tles)
    bad, speeds = [], []
    for name, sat, _ in tles:
        eci = sat_eci(sat, t0)
        ecef = sat_state_ecef(sat, t0)
        if eci is None or ecef is None:
            bad.append(name)
            continue
        rmag = math.sqrt(sum(c * c for c in eci[0]))
        s_eci = math.sqrt(sum(c * c for c in eci[1]))
        s_ecef = math.sqrt(sum(c * c for c in ecef[1]))
        speeds.append((rmag, s_eci, s_ecef, eci[0][2] / rmag))
    in_band = all(7.0e6 < rm < 7.35e6 and 7.2e3 < se < 7.8e3 for rm, se, _, _ in speeds)
    rot_seen = all(abs(se - sc) > 1.0 for _, se, sc, _ in speeds)
    good = not bad and in_band and rot_seen
    checks.append(good)
    lo = min(rm for rm, _, _, _ in speeds) / 1e3
    hi = max(rm for rm, _, _, _ in speeds) / 1e3
    print(f"  {'ok  ' if good else 'FAIL'}  radii {lo:.0f}-{hi:.0f} km, all near-circular; "
          f"ECEF speed differs from TEME by the Earth-rotation term"
          + (f"; SGP4 failed for {bad}" if bad else ""))

    r = (4.1e6, 3.2e6, 4.9e6)
    v = (-4.0e3, 5.1e3, -1.0e3)
    th = gmst_rad(J2000)
    r2, v2 = ecef_to_teme(*teme_to_ecef(r, v, th), th)
    good = (all(abs(r2[i] - r[i]) < 1e-3 for i in range(3))
            and all(abs(v2[i] - v[i]) < 1e-3 for i in range(3)))
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  TEME->ECEF->TEME round-trips position "
          f"and velocity to 1 mm / 1 mm-per-s")

    # 4. End to end: recover a known position from real orbits at the solver's target
    #    precision (5 Hz, 40-80 bursts). This is the number the whole chain rests on.
    errs, ns = [], []
    for s in range(seeds):
        e, n = run_tle(tles, sigma_hz, n_obs, s, verbose=(s == 0))
        if e is not None:
            errs.append(e)
            ns.append(n)
    if not errs:
        print(f"  FAIL  no convergent solution from real geometry")
        return dict(ok=False, checks=(0, 1), n_sats=len(tles), median_m=None)
    med = sorted(errs)[len(errs) // 2]
    good = med < fail_m
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  {sigma_hz:.0f} Hz / {min(ns)}-{max(ns)} bursts "
          f"-> median {med:6.1f} m over {len(errs)} seeds (limit {fail_m:.0f} m)")

    print("\n  NOTE: this isolates the SOLVER and the GEOMETRY. The observations are")
    print("  generated from the same TLEs the solver uses, so the ephemeris is exact by")
    print("  construction - SGP4 propagation error is a SEPARATE budget term and is not")
    print("  measured here. What is proven is that real Iridium geometry inverts, and")
    print("  that the frame conversion carries the Earth's rotation.")
    ok = all(checks)
    print("\n" + (f"EPHEMERIS OK - real SGP4 geometry inverts "
                  f"({sum(checks)}/{len(checks)} assertions)" if ok else
                  "EPHEMERIS FAILED"))
    return dict(ok=ok, checks=(sum(checks), len(checks)), n_sats=len(tles), median_m=med)


def write_obs(path, seed=0, sigma_hz=5.0, n_obs=60):
    """Write a deterministic observation set from the real TLE geometry, for cross-
    checking the C solver in firmware/soop/ against this one.
    """
    tles = load_tles()
    lat, lon, h = 52.2053, 0.1218, 60.0
    rr = geodetic_to_ecef(lat, lon, h)
    clock_hz = 2.5e-6 * F_IRIDIUM
    t0 = max(ep for _, _, ep in tles)
    obs = tle_observations(tles, rr, t0, clock_hz, n_obs, sigma_hz, seed)
    with open(path, "w") as f:
        f.write(f"{len(obs)}\n")
        for rs, vs, df in obs:
            f.write("%.9f %.9f %.9f %.9f %.9f %.9f %.9f\n"
                    % (rs[0], rs[1], rs[2], vs[0], vs[1], vs[2], df))
    guess = (rr[0] + 50_000.0, rr[1] - 50_000.0, rr[2] + 50_000.0, 0.0)
    x, rms, it = solve(obs, guess)
    print(f"obs {len(obs)}")
    print("true %.9f %.9f %.9f %.9f" % (rr[0], rr[1], rr[2], clock_hz))
    print("guess %.9f %.9f %.9f %.9f" % guess)
    print("solution %.9f %.9f %.9f %.9f" % (x[0], x[1], x[2], x[3]))
    print("resid_rms %.6f" % rms)
    return 0


def main():
    if "--emit-obs" in sys.argv:
        return write_obs(sys.argv[sys.argv.index("--emit-obs") + 1])
    if "--sweep" in sys.argv:
        print("=== accuracy vs frequency-measurement noise and burst count ===")
        print("    (66-satellite Iridium-like constellation, 8 deg mask,")
        print("     10-minute window, 20 seeds each)\n")
        print(f"    {'sigma Hz':>9} {'bursts':>7} {'median err':>11} {'p90 err':>9}")
        for sigma in (1.0, 5.0, 20.0, 50.0):
            for n in (16, 40, 80):
                errs = sorted(e for e in (run(sigma, n, s) for s in range(20))
                              if e is not None)
                if not errs:
                    continue
                med = errs[len(errs) // 2]
                p90 = errs[int(len(errs) * 0.9)]
                print(f"    {sigma:9.1f} {n:7d} {med:10.1f} m {p90:8.1f} m")
        print("\n    Read this as the SOLVER's contribution on exact geometry. The")
        print("    synthetic constellation is exact by construction; real TLEs add")
        print("    propagation error on top. For the real geometry run --ephemeris.")
        print()
        print("    THE REQUIREMENT THIS SETS. Error scales as 1/sqrt(N) in burst count")
        print("    and linearly in frequency noise, so the literature's 100-200 m needs")
        print("    roughly 5 Hz of frequency-measurement precision over 40-80 bursts.")
        print("    That is the number the receiver has to hit, and it was never stated")
        print("    anywhere in this project before. An 8.28 ms Iridium burst has about")
        print("    120 Hz of raw FFT resolution, so 5 Hz means estimating the carrier")
        print("    well inside a bin - achievable, but it is a real design target and")
        print("    not a free one.")
        return 0

    print("=== solver self-test: recover a known position from clean geometry ===")
    ok = True
    for sigma, limit in ((0.0, 1.0), (1.0, 500.0), (10.0, 5000.0)):
        errs = [e for e in (run(sigma, 40, s, verbose=(s == 0)) for s in range(10))
                if e is not None]
        if not errs:
            print(f"  FAIL  sigma {sigma} Hz: no convergent solution")
            ok = False
            continue
        med = sorted(errs)[len(errs) // 2]
        good = med < limit
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'}  sigma {sigma:4.1f} Hz -> median "
              f"{med:8.1f} m over {len(errs)} seeds (limit {limit:.0f} m)")
    print("\n=== degenerate geometry must FAIL, not invent a number ===")
    rr = geodetic_to_ecef(52.2053, 0.1218, 60.0)
    rs, vs = circular_orbit(0.0, 0.0, 0.0)
    single = [(rs, vs, predict_df(rs, vs, rr, 0.0))] * 4      # one geometry, repeated
    x, _, _ = solve(single, (rr[0] + 1e4, rr[1], rr[2], 0.0))
    degen_ok = x is None
    print(f"  {'ok  ' if degen_ok else 'FAIL'}  four copies of one observation -> "
          f"{'reported singular' if degen_ok else 'returned a solution it cannot have'}")
    ok &= degen_ok
    print("\n" + ("SOLVER OK - the geometry inverts" if ok else "SOLVER FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--ephemeris" in sys.argv:
        sys.exit(0 if ephemeris_test()["ok"] else 1)
    sys.exit(main())
