#!/usr/bin/env python3
"""Run a bench recording of the real Iridium sky through the flight code, and measure it.

Usage:
  soop_bench.py REC --start UTC --site LAT LON H [--fc HZ] [--fs HZ] [--format cu8]
                [--gain G|auto] [--lo-search] [--offset-km K] [--tle FILE] [--out DIR]

A receiver without a TCXO - the ADALM-Pluto's crystal is +-25 ppm, +-40 kHz at 1626 MHz -
needs --lo-search: the recording is tried at LO corrections across +-40 kHz, the one the
navigation fuses most bursts at is kept, and its clock estimate refines it. The sample
clock shares the crystal, so the same ppm corrects the time base. A Pluto recording:
  rx_sdr -d driver=plutosdr -f 1626333333 -s 2000000 -g 40 -F CS16 rec.cs16
  soop_bench.py rec.cs16 --format cs16 --gain auto --lo-search --start ... --site ...
"""
import argparse
import array
import datetime
import math
import os
import re
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
                nav_host=["nav_host.c", "soop_guard.c", "soop_nav.c", "soop_ephem.c", "sgp4.c"])
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


def nav_log(path, start, site_ecef, sigma_m, bursts, seconds, ppm=0.0):
    jd, fr = sol._jday(start)
    #a recording clock fast by ppm stretches board time: the second tag says by how much
    lines = [f"H {jd:.1f} {fr:.12f}", "U 0.0 0.0",
             f"U {seconds:.3f} {seconds / (1 + ppm * 1e-6):.6f}",
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


BYTES = {"cu8": 2, "cs16": 4, "cf32": 8}
LO_STEPS = [k * 10_000.0 for k in range(-4, 5)]   #+-40 kHz, gaps inside the filter's +-6 kHz search


def import_rec(exe, rec, out, a, fc, gain):
    r = subprocess.run([exe, rec, out, "--format", a.format, "--fs", str(a.fs), "--fc", str(fc),
                        "--gain", str(gain)] + sig.amp_args(), capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)
    return r.stderr.strip()


def board_rms(path, n=2_000_000):
    """Per-rail rms of the first n samples of a board capture, in counts."""
    a = array.array("h")
    with open(path, "rb") as f:
        a.frombytes(f.read(4 * n))
    return math.sqrt(sum(v * v for v in a) / max(1, len(a)))


def target_rms():
    """What the board's own chain puts on the ADC, after the amp's pole (check_soop.py gain);
    on a board without a gain plan, the 600 counts the DSP gates run at."""
    import check_soop
    import design
    counts = 600.0
    if hasattr(check_soop, "gain_plan") and "antenna" in getattr(design, "RF_PARTS", {}):
        A, T = design.RF_PARTS["antenna"], design.RF_PARTS["tuner"]
        _, gc = check_soop.gc_loss_max()
        counts = check_soop.gain_plan(A["t_ant_k"], A["gain_db"], T["ref_bbg"], gc / 2)["counts"]
    band = sum(sig.amp_gain((k + 0.5) * sig.FS_CAPTURE / 200) ** 2 for k in range(100)) / 100
    return counts * math.sqrt(band)


def clock_of(stats):
    m = re.search(r"clock (-?[\d.]+) Hz \(sd ([\d.]+)\)", stats)
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, float("inf"))


def lo_search(trial, steps=LO_STEPS):
    """trial(shift) -> (fused, clock Hz, clock sd): the shift fusing most bursts, refined by its clock.
    Returns the total correction to add to fc, the fused count, and every trial."""
    tried = [(s,) + tuple(trial(s)) for s in steps]
    s, fused, clock, sd = max(tried, key=lambda t: t[1])
    return s - clock, fused, tried


def gr_iridium(rec, fc, fs, fmt):
    """Bursts gr-iridium finds in the same recording: (t s, RF Hz), or None."""
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
    ap.add_argument("--gain", default="1", help="scale to board counts, or auto")
    ap.add_argument("--lo-search", action="store_true",
                    help="the receiver has no TCXO: find its LO error first")
    ap.add_argument("--search-seconds", type=float, default=240.0)
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
    site = sol.geodetic_to_ecef(*a.site)
    fc, ppm = a.fc, 0.0

    #the first minutes only, for the gain and the LO search
    head = os.path.join(tmp, "head." + a.format)
    with open(a.rec, "rb") as fi, open(head, "wb") as fo:
        fo.write(fi.read(int(a.search_seconds * a.fs) * BYTES[a.format]))
    if a.gain == "auto":
        import_rec(exe["iq_import"], head, board, a, fc, 1.0)
        gain = target_rms() / max(board_rms(board), 1e-3)
        print(f"=== gain {gain:.1f}: the recording's noise scaled to the board chain's "
              f"{target_rms():.0f} counts ===")
    else:
        gain = float(a.gain)
    if a.lo_search:
        def trial(shift):
            import_rec(exe["iq_import"], head, board, a, fc + shift, gain)
            sec = os.path.getsize(board) / 4 / sig.FS_CAPTURE
            log = os.path.join(tmp, "search.txt")
            nav_log(log, start, site, 5.0, dsp_bursts(exe["dsp_host"], board), sec)
            _, brs, _, stats = run_nav(exe["nav_host"], a.tle, log)
            return (sum(1 for b in brs if b[2] == "0"),) + clock_of(stats)
        corr, fused, tried = lo_search(trial)
        if fused < 20:
            sys.exit("LO search: no correction fused 20 bursts - record longer, or check the "
                     "antenna and the start time\n" + "\n".join(
                         f"  {s / 1e3:+.0f} kHz: {n} fused" for s, n, _, _ in tried))
        fc += corr
        ppm = corr / a.fc * 1e6
        print(f"=== LO search: the recording's LO is {corr:+.0f} Hz off ({ppm:+.2f} ppm), "
              f"{fused} bursts fused in the first {a.search_seconds:.0f} s ===")
    os.remove(head)

    info = import_rec(exe["iq_import"], a.rec, board, a, fc, gain)
    seconds = os.path.getsize(board) / 4 / sig.FS_CAPTURE
    print(f"=== bench recording: {seconds:.0f} s from {start.isoformat()} ===")
    print(f"    {info}")

    bursts = dsp_bursts(exe["dsp_host"], board)
    cn0 = [b["cn0"] for b in bursts]
    print(f"    DSP: {len(bursts)} bursts, {60 * len(bursts) / max(seconds, 1):.0f}/min; C/N0 "
          f"p10 {pct(cn0, .1):.1f} / median {pct(cn0, .5):.1f} / p90 {pct(cn0, .9):.1f} dB-Hz")
    tles = sol.load_tles(a.tle)
    newest = max(ep for _, _, ep in tles)
    age = (start - newest).total_seconds() / 86400.0
    print(f"    TLEs: {len(tles)} satellites, newest epoch {age:+.2f} days from the recording"
          + ("  <- older than 3 days: refresh them (runbook)" if age > 3 else ""))

    #1. anchored at the site: measure the sky and the model fit
    log = os.path.join(tmp, "anchored.txt")
    nav_log(log, start, site, 5.0, bursts, seconds, ppm)
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
        nav_log(log, start, start_pos, a.offset_km * 1500.0, bursts, seconds, ppm)
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

    gr = gr_iridium(a.rec, fc, a.fs, a.format)
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
