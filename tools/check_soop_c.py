#!/usr/bin/env python3
"""Prove the on-board C solver agrees with the Python reference, and compiles for the H743."""
import math
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOLVE_DIR = os.path.join(ROOT, "firmware", "soop")
TOL_M = 1e-3          # metres; both sides are double precision and run the same algorithm
CFLAGS = ["-O2", "-std=c99", "-Wall", "-Wextra"]


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    cc = os.environ.get("CC", "cc")
    arm = os.environ.get("ARMGCC", "arm-none-eabi-gcc")
    tmp = tempfile.mkdtemp(prefix="soop_c_")
    obs = os.path.join(tmp, "obs.txt")
    exe = os.path.join(tmp, "soop_host")
    armobj = os.path.join(tmp, "soop_solve_arm.o")

    # 1. the reference solution and the identical inputs
    r = _run([sys.executable, "tools/soop_solver.py", "--emit-obs", obs], cwd=ROOT)
    if r.returncode != 0:
        print(f"SOOP-C CHECK FAILED - the Python emitter failed: {r.stderr.strip()}")
        return 1
    def grab(kind):
        m = re.search(rf"^{kind} (.+)$", r.stdout, re.M)
        return [float(v) for v in m.group(1).split()] if m else None
    py_sol, guess = grab("solution"), grab("guess")
    if not py_sol or not guess:
        print("SOOP-C CHECK FAILED - the Python emitter printed no solution")
        return 1

    # 2. host build + the differential comparison
    b = _run([cc, *CFLAGS, "-o", exe, "main_host.c", "soop_solve.c", "-lm"], cwd=SOLVE_DIR)
    if b.returncode != 0:
        print(f"SOOP-C CHECK FAILED - the C solver did not compile: {b.stderr.strip()[:400]}")
        return 1
    run = _run([exe, obs, *[repr(g) for g in guess]])
    m = re.search(r"^solution (.+)$", run.stdout, re.M)
    if not m:
        print(f"SOOP-C CHECK FAILED - the C solver printed no solution: "
              f"{(run.stdout + run.stderr).strip()[:200]}")
        return 1
    c_sol = [float(v) for v in m.group(1).split()]
    dpos = math.sqrt(sum((c_sol[i] - py_sol[i]) ** 2 for i in range(3)))
    dclk = abs(c_sol[3] - py_sol[3])
    agree = dpos < TOL_M
    print(f"  {'ok  ' if agree else 'FAIL'}  C and Python agree: position within "
          f"{dpos:.2e} m, clock within {dclk:.2e} Hz (limit {TOL_M:g} m)")

    # 3. cross-compile for the actual target silicon
    a = _run([arm, "-c", *CFLAGS, "-mcpu=cortex-m7", "-mthumb", "-mfpu=fpv5-d16",
              "-mfloat-abi=hard", "-o", armobj, "soop_solve.c"], cwd=SOLVE_DIR)
    built = a.returncode == 0 and os.path.exists(armobj)
    print(f"  {'ok  ' if built else 'FAIL'}  cross-compiles for the H743 (Cortex-M7, "
          f"hard float)" + ("" if built else f": {a.stderr.strip()[:200]}"))

    ok = agree and built
    print("\n" + (f"SOOP-C OK - C solver agrees with Python to {dpos:.2e} m and builds "
                  f"for the target" if ok else "SOOP-C CHECK FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
