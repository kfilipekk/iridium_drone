#!/usr/bin/env python3
"""tools/check_soop_sgp4.py - Gate: C SGP4 agrees with Python sgp4.api.Satrec."""

import subprocess
import sys
import os
import math
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TLE  = os.path.join(REPO, "sitl", "tle", "iridium-next.tle")
SRC_C  = os.path.join(REPO, "firmware", "soop", "sgp4.c")
SRC_T  = os.path.join(REPO, "firmware", "soop", "sgp4_host_test.c")

OFFSETS_DAYS = [0.0, +1.0, -1.0, +3.0, -3.0]
POS_TOL_M  = 1000.0   # 1 km
VEL_TOL_MS = 1.5      # m/s


def load_tles(path):
    """Return list of (name, line1, line2) tuples."""
    sats = []
    with open(path) as fh:
        lines = [l.rstrip() for l in fh if l.strip() and not l.startswith("#")]
    i = 0
    while i + 2 < len(lines):
        name = lines[i]
        l1   = lines[i + 1]
        l2   = lines[i + 2]
        if l1.startswith("1") and l2.startswith("2"):
            sats.append((name, l1, l2))
            i += 3
        else:
            i += 1
    return sats


def generate_reference(sats):
    """Return list of (norad, offset_days, r_km[3], v_km_s[3]) from Python sgp4."""
    from sgp4.api import Satrec
    rows = []
    for name, l1, l2 in sats:
        norad = int(l1[2:7])
        sat = Satrec.twoline2rv(l1, l2)
        for od in OFFSETS_DAYS:
            e, r, v = sat.sgp4(sat.jdsatepoch + od, sat.jdsatepochF)
            if e != 0:
                print(f"  [skip] NORAD {norad} {name.strip()} offset {od:+g}: sgp4 error {e}",
                      file=sys.stderr)
                continue
            rows.append((norad, od, list(r), list(v)))
    return rows


def build_host_binary(build_dir):
    """Compile sgp4.c + sgp4_host_test.c -> binary. Returns path."""
    exe = os.path.join(build_dir, "sgp4_host_test")
    cmd = [
        "gcc", "-O2", "-std=c99",
        "-Wno-unused-variable", "-Wno-unused-function",
        "-I", os.path.join(REPO, "firmware", "soop"),
        "-o", exe,
        SRC_C, SRC_T,
        "-lm",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("BUILD FAILED:", r.stderr, file=sys.stderr)
        sys.exit(1)
    return exe


def write_ref_file(rows, path):
    with open(path, "w") as fh:
        for norad, od, r, v in rows:
            fh.write(f"{norad} {od:.1f} "
                     f"{r[0]:.10f} {r[1]:.10f} {r[2]:.10f} "
                     f"{v[0]:.12f} {v[1]:.12f} {v[2]:.12f}\n")


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump-ref", action="store_true",
                    help="Print reference table to stdout and exit")
    ap.add_argument("--tle", default=TLE, help="TLE file (default: sitl/tle/iridium-next.tle)")
    args = ap.parse_args()

    sats = load_tles(args.tle)
    print(f"Loaded {len(sats)} satellites", file=sys.stderr)

    rows = generate_reference(sats)
    print(f"Generated {len(rows)} reference points", file=sys.stderr)

    if args.dump_ref:
        for norad, od, r, v in rows:
            print(f"{norad} {od:.1f} "
                  f"{r[0]:.10f} {r[1]:.10f} {r[2]:.10f} "
                  f"{v[0]:.12f} {v[1]:.12f} {v[2]:.12f}")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        ref_path = os.path.join(tmpdir, "sgp4_ref.txt")
        write_ref_file(rows, ref_path)

        exe = build_host_binary(tmpdir)
        r = subprocess.run([exe, args.tle, ref_path],
                           capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            print("SGP4-C GATE FAILED", file=sys.stderr)
            sys.exit(1)
        print("SGP4-C GATE OK")


if __name__ == "__main__":
    main()
