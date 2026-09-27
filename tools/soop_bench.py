#!/usr/bin/env python3
"""Run a bench recording of the real Iridium sky through the flight code, and measure it.

Usage:
  soop_bench.py REC --start UTC --site LAT LON H [--fc HZ] [--fs HZ] [--format cu8]
                [--offset-km K] [--tle FILE] [--out DIR]
"""
import argparse
import datetime
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOOP = os.path.join(ROOT, "firmware", "soop")
sys.path.insert(0, HERE)
import iridium_sig as sig
import soop_solver as sol

F_LO = sig.F_RING_ALERT + sig.LO_OFFSET_HZ
IMPORT_DELAY = 12          #iq_import's filter delay, output samples


def build(tmp):
    cc = ["cc", "-O2", "-std=c99", "-Wall", "-Wextra"]
    bins = dict(iq_import=["iq_import.c"], dsp_host=["dsp_host.c", "soop_dsp.c"],
                nav_host=["nav_host.c", "soop_nav.c", "soop_ephem.c", "sgp4.c"])
    out = {}
    for name, srcs in bins.items():
        exe = os.path.join(tmp, name)
        r = subprocess.run(cc + ["-o", exe] + [os.path.join(SOOP, s) for s in srcs] + ["-lm"],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"build of {name} failed:\n{r.stderr}")
        out[name] = exe
    return out


def dsp_bursts(exe, board_iq):
    r = subprocess.run([exe, board_iq], capture_output=True, text=True)
    rows = []
    for ln in r.stdout.splitlines()[1:]:
        p = ln.split(",")
        rows.append(dict(t=(int(p[0]) - IMPORT_DELAY) / sig.FS_CAPTURE, f=float(p[2]),
                         sigma=float(p[3]), cn0=float(p[4])))
    return rows


def nav_log(path, start, site_ecef, sigma_m, bursts, seconds):
    jd, fr = sol._jday(start)
    lines = [f"H {jd:.1f} {fr:.12f}", "U 0.0 0.0",
             "P 0.0 %.3f %.3f %.3f %.1f" % (*site_ecef, sigma_m)]
    ev = [(k * 0.1, f"E {k * 0.1:.3f} 0 0 0") for k in range(int(seconds * 10) + 1)]
    ev += [(b["t"], f"D {b['t']:.6f} {b['f']:.3f} {b['sigma']:.3f} {b['cn0']:.2f}")
           for b in bursts]
    ev.sort(key=lambda e: e[0])
    open(path, "w").write("\n".join(lines + [e[1] for e in ev]) + "\n")


def run_nav(exe, tle, log, extra=()):
    r = subprocess.run([exe, tle, log, "--static", "--sats"] + list(extra),
                       capture_output=True, text=True)
    fixes, bursts, sats = [], [], {}
    for ln in r.stdout.splitlines()[1:]:
        p = ln.split(",")
        if p[0] == "F":
            fixes.append(p)
        elif p[0] == "B":
            bursts.append(p)
        elif p[0] == "T":
            sats[int(p[2])] = dict(beta=float(p[3]), beta_sd=float(p[4]),
                                   tau_ms=float(p[5]) * 1e3, tau_sd_ms=float(p[6]) * 1e3)
    return fixes, bursts, sats, r.stderr.strip()


#bursts gr-iridium finds in the same recording: (t s, RF Hz), or None
def gr_iridium(rec, fc, fs, fmt):
    exe = shutil.which("iridium-extractor")
    if not exe:
        return None
    gfmt = {"cu8": "rtl", "cs16": "sc16", "cf32": "fc32"}[fmt]
    r = subprocess.run([exe, "--offline", "-c", str(int(fc)), "-r", str(int(fs)), "-f", gfmt,
                        rec], capture_output=True, text=True)
    out = []
    for ln in r.stdout.splitlines():
        p = ln.split()
        if len(p) > 3 and p[0] == "RAW:":
            out.append((float(p[2]) / 1000.0, float(p[3])))
    return out


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rec")
    ap.add_argument("--start", required=True, help="UTC of the first sample, ISO 8601")
    ap.add_argument("--site", type=float, nargs=3, required=True, metavar=("LAT", "LON", "H"))
    ap.add_argument("--fc", type=float, default=F_LO)
    ap.add_argument("--fs", type=float, default=2_000_000.0)
    ap.add_argument("--format", default="cu8", choices=("cu8", "cs16", "cf32"))
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--offset-km", type=float, default=5.0)
    ap.add_argument("--tle", default=sol.TLE_PATH)
    ap.add_argument("--out")
    a = ap.parse_args()

    start = datetime.datetime.fromisoformat(a.start.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=datetime.timezone.utc)
    tmp = a.out or tempfile.mkdtemp(prefix="soop_bench_")
    os.makedirs(tmp, exist_ok=True)
    exe = build(tmp)
    board = os.path.join(tmp, "board.iq")
    r = subprocess.run([exe["iq_import"], a.rec, board, "--format", a.format,
                        "--fs", str(a.fs), "--fc", str(a.fc), "--gain", str(a.gain)],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)
    seconds = os.path.getsize(board) / 4 / sig.FS_CAPTURE
    print(f"=== bench recording: {seconds:.0f} s from {start.isoformat()} ===")
    print(f"    {r.stderr.strip()}")

    bursts = dsp_bursts(exe["dsp_host"], board)
    cn0 = [b["cn0"] for b in bursts]
    print(f"    DSP: {len(bursts)} bursts, {60 * len(bursts) / max(seconds, 1):.0f}/min; C/N0 "
          f"p10 {pct(cn0, .1):.1f} / median {pct(cn0, .5):.1f} / p90 {pct(cn0, .9):.1f} dB-Hz")
    tles = sol.load_tles(a.tle)
    newest = max(ep for _, _, ep in tles)
    age = (start - newest).total_seconds() / 86400.0
    print(f"    TLEs: {len(tles)} satellites, newest epoch {age:+.2f} days from the recording"
          + ("  <- older than 3 days: refresh them (runbook)" if age > 3 else ""))

    site = sol.geodetic_to_ecef(*a.site)
    #1. anchored at the site: measure the sky and the model fit
    log = os.path.join(tmp, "anchored.txt")
    nav_log(log, start, site, 5.0, bursts, seconds)
    fixes, brs, sats, stats = run_nav(exe["nav_host"], a.tle, log)
    fused = sum(1 for b in brs if b[2] == "0")
    nis = float(fixes[-1][10]) if fused else float("nan")
    print(f"\n  anchored at the site: {stats}")
    print(f"    {fused} of {len(brs)} bursts fused ({fused / max(1, len(brs)):.0%}); NIS {nis:.2f} "
          f"(1 = the filter's noise model fits this sky)")
    if sats:
        betas = [s["beta"] for s in sats.values()]
        rms = math.sqrt(sum(b * b for b in betas) / len(betas))
        print(f"    satellite transmit offsets, {len(sats)} satellites: rms {rms:.1f} Hz "
              f"(the filter assumes beta_sigma 60 Hz; set it from this)")
        for num, s in sorted(sats.items()):
            print(f"      {num}: beta {s['beta']:+7.1f} +- {s['beta_sd']:4.1f} Hz, along-track "
                  f"{s['tau_ms']:+6.1f} +- {s['tau_sd_ms']:5.1f} ms")

    #2. started away from the site: does it find it?
    if a.offset_km > 0:
        lat, lon, h = a.site
        start_pos = sol.geodetic_to_ecef(lat + a.offset_km / 111.32 / math.sqrt(2),
                                         lon + a.offset_km / 111.32 / math.sqrt(2)
                                         / math.cos(math.radians(lat)), h)
        log = os.path.join(tmp, "offset.txt")
        nav_log(log, start, start_pos, a.offset_km * 1500.0, bursts, seconds)
        fixes, brs, _, stats = run_nav(exe["nav_host"], a.tle, log)
        print(f"\n  started {a.offset_km:g} km away: {stats}")
        #a guess this far out does not anchor the filter
        live = [p for p in fixes if int(p[11]) > 0]
        print("    (a blind start: converging, not trusted - the aircraft anchors on GPS first)")
        if not live:
            print("    nothing tracked: too few bursts, or the clock was never acquired")
        for p in live[::max(1, len(live) // 8)] + live[-1:]:
            e = math.dist(sol.geodetic_to_ecef(float(p[2]), float(p[3]), float(p[4])), site)
            print(f"    t {float(p[1]):6.0f} s  error {e:7.0f} m  hacc {float(p[8]):7.0f} m")

    gr = gr_iridium(a.rec, a.fc, a.fs, a.format)
    if gr is None:
        print("\n  gr-iridium not installed: no independent burst count")
    else:
        ra = [(t, f) for t, f in gr if abs(f - sig.F_RING_ALERT) < 50e3]
        hit = sum(1 for t, f in ra if any(abs(b["t"] - t) < 0.01 and abs(b["f"] + F_LO - f) < 500
                                          for b in bursts))
        print(f"\n  gr-iridium: {len(gr)} bursts, {len(ra)} within the DSP's band; the DSP found "
              f"{hit} of those ({hit / max(1, len(ra)):.0%})")
    print(f"\n  files in {tmp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
