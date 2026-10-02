#!/usr/bin/env python3
"""The antenna feed monitor reads the fitted parts right and does what its header says.

Usage: python3 tools/check_soop_ant.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import design

SOOP = os.path.join(ROOT, "firmware", "soop")


def ohms(v):
    return float(v.replace("R", ".")) if "R" in v else float(v)


def run(lines):
    r = subprocess.run([os.path.join(SOOP, "ant_host")], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, check=True)
    return [l.split() for l in r.stdout.splitlines()]


def main():
    fails = []
    A = design.ANT_FEED
    r = subprocess.run(["make", "-s", "ant_host"], cwd=SOOP, capture_output=True, text=True)
    if r.returncode:
        print(f"ANT CHECK FAILED - ant_host did not build:\n{r.stderr}")
        return 1

    #1. C defaults
    got = {k: float(v) for k, v in (l for l in run(["cfg"]))}
    for k in ("open_ma", "short_ma", "settle_s", "retry_after_s", "retry_off_s"):
        if abs(got[k] - A[k]) > 1e-6:
            fails.append(f"soop_ant.c {k} = {got[k]}, design.ANT_FEED says {A[k]}")

    #2. thresholds against the parts
    sense = ohms(design.COMPONENTS[A["sense_ref"]][2])
    sat_ma = (A["vs"] - A["swing_v"]) / (sense * A["gain"]) * 1000
    lna_v = A["lna_ma"] / 1000 * sense * A["gain"]
    print(f"sense {sense} ohm x {A['gain']:.0f}: the LNA's {A['lna_ma']} mA reads {lna_v:.2f} V,"
          f" saturation at {sat_ma:.1f} mA")
    if not A["open_ma"] <= A["lna_ma"] / 2:
        fails.append(f"open threshold {A['open_ma']} mA is not under half the LNA's current")
    if not A["short_ma"] >= A["lna_ma"] * 1.5:
        fails.append(f"short threshold {A['short_ma']} mA is under 1.5x the LNA's current")
    if not A["short_ma"] < sat_ma:
        fails.append(f"short threshold {A['short_ma']} mA is above the amplifier's "
                     f"{sat_ma:.1f} mA saturation - a short would never read as one")
    if not A["short_circuit_ma"] > A["short_ma"]:
        fails.append(f"U24 folds back to {A['short_circuit_ma']} mA, under the short threshold")

    #3. scenarios, 0.1 s steps
    def series(segments):
        out, t = [], 0.0
        for dur, ma, fault in segments:
            for _ in range(int(round(dur / 0.1))):
                out.append(f"{t:.2f} {ma} {fault}")
                t += 0.1
        return out

    def state_at(res, t):
        return next(r for r in res if abs(float(r[0]) - t) < 1e-6)

    res = run(series([(1.0, 0.0, 0), (1.0, A["lna_ma"], 0), (0.2, 0.0, 0), (1.0, A["lna_ma"], 0),
                      (A["retry_after_s"] + 1.5, 0.0, 1), (A["retry_off_s"] + 1.0, 0.0, 0),
                      (1.0, A["lna_ma"], 0)]))
    want = [(0.9, "open", "1"), (1.9, "ok", "1"),
            (2.1, "ok", "1"),                                   #a 0.2 s dip is ignored
            (3.3, "ok", "1"), (4.0, "short", "1"),
            (3.2 + A["retry_after_s"] + 1.0, "short", "0"),      #feed off after the retry delay
            ]
    for t, st, en in want:
        r = state_at(res, round(t, 2))
        if (r[1], r[2]) != (st, en):
            fails.append(f"at {t:.1f} s: {r[1]}/en {r[2]}, expected {st}/en {en}")
    back_on = [float(r[0]) for r in res if r[2] == "1" and float(r[0]) > 3.2 + A["retry_after_s"]]
    if not back_on:
        fails.append("the feed never came back on after the short")
    final = res[-1]
    if (final[1], final[2]) != ("ok", "1"):
        fails.append(f"after the short cleared: {final[1]}/en {final[2]}, expected ok/en 1")
    off = run(["off"] + series([(1.0, A["lna_ma"], 0)]))
    if any((r[1], r[2]) != ("off", "0") for r in off):
        fails.append("with the feed disabled the monitor still drives the enable")

    #4. the target
    r = subprocess.run(["make", "-s", "arm"], cwd=SOOP, capture_output=True, text=True)
    if r.returncode or not os.path.exists(os.path.join(SOOP, "soop_ant.o")):
        fails.append(f"soop_ant.c does not compile for the H743: {r.stderr.strip()[:200]}")

    for f in fails:
        print(f"  FAIL  {f}")
    print(f"ANT CHECK {'FAILED' if fails else 'PASSED'}: {len(fails)} failure(s), "
          f"{len(res) + len(off)} steps simulated")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
