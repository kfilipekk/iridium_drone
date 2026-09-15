#!/usr/bin/env python3
"""Doppler positioning from signals of opportunity: the solver, and proof it works."""
import math
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


def main():
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
        print("\n    Read this as the GEOMETRY's contribution only. It assumes the")
        print("    ephemeris is exact; with TLEs it is not, and that error adds.")
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
    sys.exit(main())
