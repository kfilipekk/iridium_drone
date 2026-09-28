#!/usr/bin/env python3
"""Gate the on-board Iridium DSP (firmware/soop/soop_dsp.c) against a simulated sky.

Usage:  python3 tools/check_soop_dsp.py [--slots N] [--keep DIR]
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
import iridium_sig as sig
import soop_scenario

GATES = dict(detect_min=0.90,      #of eligible bursts at C/N0 >= strong
             strong_dbhz=55.0,
             false_max=0.01,       #of all detections
             p90_hz=5.0,           #carrier error, C/N0 >= strong: the solver's budget
             within3_min=0.95,     #errors inside 3 reported sigma
             timing_samples=20)    #median preamble-start error: one symbol


def check_constants():
    h = open(os.path.join(SOOP, "soop_signal.h")).read()
    want = dict(SOOP_SYMBOL_RATE=sig.SYMBOL_RATE, SOOP_CH_SPACING=sig.CHANNEL_SPACING,
                SOOP_F_RING_ALERT=sig.F_RING_ALERT, SOOP_PREAMBLE_SYMS=sig.PREAMBLE_SYMBOLS,
                SOOP_MAX_BURST_S=sig.MAX_BURST_S, SOOP_FS=sig.FS_CAPTURE,
                SOOP_LO_OFFSET_HZ=sig.LO_OFFSET_HZ)
    bad = []
    for k, v in want.items():
        m = re.search(rf"#define\s+{k}\s+([0-9.eE+-]+)", h)
        if not m or abs(float(m.group(1)) - v) > 1e-6 * max(1.0, abs(v)):
            bad.append(f"{k}: header {m.group(1) if m else 'missing'}, python {v}")
    return bad


def build(tmp):
    exe = os.path.join(tmp, "dsp_host")
    r = subprocess.run(["cc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror", "-o", exe,
                        os.path.join(SOOP, "dsp_host.c"), os.path.join(SOOP, "soop_dsp.c"), "-lm"],
                       capture_output=True, text=True)
    if r.returncode:
        return None, r.stderr
    obj = os.path.join(tmp, "soop_dsp.o")
    r = subprocess.run(["arm-none-eabi-gcc", "-c", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-mcpu=cortex-m7", "-mthumb", "-mfpu=fpv5-d16", "-mfloat-abi=hard",
                        "-fsingle-precision-constant", "-o", obj, os.path.join(SOOP, "soop_dsp.c")],
                       capture_output=True, text=True)
    if r.returncode:
        return exe, "arm: " + r.stderr
    sz = subprocess.run(["arm-none-eabi-size", obj], capture_output=True, text=True).stdout
    return exe, sz


def check_import(tmp, dsp_exe):
    """A synthetic bench recording through iq_import and the DSP."""
    exe = os.path.join(tmp, "iq_import")
    r = subprocess.run(["cc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Werror", "-o", exe,
                        os.path.join(SOOP, "iq_import.c"), "-lm"], capture_output=True, text=True)
    if r.returncode:
        return False, "iq_import build: " + r.stderr.strip()[:300]
    d = os.path.join(tmp, "rtl")
    truth = soop_scenario.make_rtl(d)
    board = os.path.join(d, "board.iq")
    r = subprocess.run([exe, os.path.join(d, "rec.cu8"), board, "--format", "cu8",
                        "--fs", str(truth["fs"]), "--fc", str(truth["fc"])],
                       capture_output=True, text=True)
    if r.returncode:
        return False, "iq_import: " + r.stderr.strip()[:300]
    out = subprocess.run([dsp_exe, board], capture_output=True, text=True)
    rows = list(csv.DictReader(out.stdout.splitlines()))
    lo = sig.F_RING_ALERT + sig.LO_OFFSET_HZ
    worst_f = worst_t = 0.0
    found = 0
    for b in truth["bursts"]:
        m = [x for x in rows if abs((int(x["t_start"]) - 12) / sig.FS_CAPTURE - b["start"]) < 0.003]
        if len(m) != 1:
            continue
        found += 1
        worst_f = max(worst_f, abs(float(m[0]["f_hz"]) - (b["f_rf"] - lo)))
        worst_t = max(worst_t, abs((int(m[0]["t_start"]) - 12) / sig.FS_CAPTURE - b["start"]))
    n = len(truth["bursts"])
    ok = found == n and len(rows) == n and worst_f < 5.0 and worst_t < 100e-6
    return ok, (f"a bench recording (cu8, 2 MSPS, centred {truth['fc'] / 1e6:.1f} MHz) converts to "
                f"the board's capture: {found}/{n} bursts at RF - LO to {worst_f:.1f} Hz and "
                f"{worst_t * 1e6:.0f} us ({len(rows)} detections)")


def score(truth, rows):
    fs = truth["fs"]
    tr = truth["bursts"]

    def f_at(b, ts):
        return b["f_hz"] + b["fdot"] * (ts - b["centre"]) / fs

    def eligible(b):      #inside the processed band (Ring Alert +-50 kHz)
        f0 = b["f_hz"] - b["fdot"] * (b["symbols"] / sig.SYMBOL_RATE) / 2
        return b["start"] > 20000 and abs(f0 - sig.baseband_hz(sig.F_RING_ALERT)) < 50000

    matched, false, errs, dts = {}, 0, [], []
    for x in rows:
        ts, f = int(x["t_sample"]), float(x["f_hz"])
        best = None
        for i, b in enumerate(tr):
            if b["start"] - 800 <= ts <= b["start"] + b["n_samples"] + 800:
                e = f - f_at(b, ts)
                if abs(e) < 800 and (best is None or abs(e) < abs(best[1])):
                    best = (i, e)
        if best is None:
            false += 1
            continue
        i, e = best
        matched[i] = True
        errs.append((tr[i]["cn0_dbhz"], e, float(x["f_sigma_hz"])))
        dts.append(int(x["t_start"]) - tr[i]["start"])
    el = [i for i, b in enumerate(tr) if eligible(b)]
    strong = [i for i in el if tr[i]["cn0_dbhz"] >= GATES["strong_dbhz"]]
    det_strong = sum(1 for i in strong if i in matched)
    e_strong = sorted(abs(e) for c, e, _ in errs if c >= GATES["strong_dbhz"])
    within = sum(1 for _, e, s in errs if abs(e) < 3 * s)
    dts.sort()
    bands = []
    for lo, hi in ((45, 50), (50, 55), (55, 60), (60, 65), (65, 72)):
        tb = [i for i in el if lo <= tr[i]["cn0_dbhz"] < hi]
        e = sorted(abs(v) for c, v, _ in errs if lo <= c < hi)
        bands.append((lo, hi, sum(1 for i in tb if i in matched), len(tb),
                      e[int(0.9 * len(e))] if e else float("nan")))
    return dict(n_truth=len(tr), n_eligible=len(el), n_det=len(rows), false=false,
                det_strong=det_strong, n_strong=len(strong),
                p90_strong=e_strong[int(0.9 * len(e_strong))] if e_strong else float("inf"),
                within3=within / max(1, len(errs)), dt_median=dts[len(dts) // 2] if dts else 1e9,
                bands=bands)


def main():
    slots = int(sys.argv[sys.argv.index("--slots") + 1]) if "--slots" in sys.argv else 300
    keep = sys.argv[sys.argv.index("--keep") + 1] if "--keep" in sys.argv else None
    print("=== on-board Iridium DSP against a simulated sky ===")
    checks = []

    bad = check_constants()
    checks.append(not bad)
    print(f"  {'ok  ' if not bad else 'FAIL'}  soop_signal.h agrees with iridium_sig.py"
          + ("".join(f"\n        {b}" for b in bad)))

    tmp = keep or tempfile.mkdtemp(prefix="soop_dsp_")
    os.makedirs(tmp, exist_ok=True)
    exe, info = build(tmp)
    ok = exe is not None and not info.startswith("arm:")
    checks.append(ok)
    if ok:
        text = info.splitlines()[1].split()
        print(f"  ok    builds on the host with -Werror, and for the H743 (text {text[0]} B, "
              f"static data {int(text[1]) + int(text[2])} B)")
    else:
        print(f"  FAIL  build: {info.strip()[:400]}")
        return 1

    truth = soop_scenario.make_iq(tmp, slots, seed=21, cn0_lo=42.0, cn0_hi=70.0,
                                  noise_counts=600.0)
    out = subprocess.run([exe, os.path.join(tmp, "iq.bin")], capture_output=True, text=True)
    rows = list(csv.DictReader(out.stdout.splitlines()))
    r = score(truth, rows)
    secs = truth["slots"] * truth["slot_len"] / truth["fs"]
    print(f"    {slots} simplex slots ({secs:.1f} s), {r['n_truth']} bursts, {r['n_eligible']} in "
          f"the Ring Alert band; I/Q imbalance {truth['iq_imbalance']['amp_db']:+.2f} dB / "
          f"{truth['iq_imbalance']['phase_deg']:+.2f} deg, TCXO {truth['tcxo_hz']:+.0f} Hz, "
          f"sample clock {truth['mcu_ppm']:+.1f} ppm")
    print(f"    {'C/N0 dB-Hz':>12} {'detected':>10} {'p90 error':>10}")
    for lo, hi, d, n, p90 in r["bands"]:
        print(f"    {lo:>5}-{hi:<6} {d:>5}/{n:<4} {p90:>8.2f} Hz")

    g = GATES
    rate = r["det_strong"] / max(1, r["n_strong"])
    for good, text in (
            (rate >= g["detect_min"], f"detects {r['det_strong']}/{r['n_strong']} = {rate:.0%} of "
             f"bursts at >= {g['strong_dbhz']:.0f} dB-Hz (need {g['detect_min']:.0%})"),
            (r["false"] <= g["false_max"] * max(1, r["n_det"]), f"{r['false']} false detections "
             f"of {r['n_det']} (limit {g['false_max']:.0%})"),
            (r["p90_strong"] <= g["p90_hz"], f"carrier error p90 {r['p90_strong']:.2f} Hz at >= "
             f"{g['strong_dbhz']:.0f} dB-Hz (solver budget {g['p90_hz']:.0f} Hz)"),
            (r["within3"] >= g["within3_min"], f"{r['within3']:.1%} of errors inside 3 reported sigma "
             f"(need {g['within3_min']:.0%}): the solver can trust the weights"),
            (abs(r["dt_median"]) <= g["timing_samples"], f"median preamble-start error "
             f"{r['dt_median']:+d} samples (limit one symbol, {g['timing_samples']})")):
        checks.append(good)
        print(f"  {'ok  ' if good else 'FAIL'}  {text}")

    good, text = check_import(tmp, exe)
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  {text}")

    print("\n  NOTE: a simulated sky with the board's impairments. It proves the DSP meets the")
    print("  solver's needs on signals built to the Iridium air interface - not that the real")
    print("  sky looks like this; that is the bench recordings (runbook) and T3b.")
    ok = all(checks)
    print("\n" + (f"SOOP-DSP OK - {sum(checks)}/{len(checks)} assertions" if ok else
                  f"SOOP-DSP FAILED - {len(checks) - sum(checks)} of {len(checks)} assertions"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
