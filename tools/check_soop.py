#!/usr/bin/env python3
"""Checks on the Iridium receiver chain, the on-board C and the SPICE decks.

Usage:  python3 tools/check_soop.py CHECK [options]

Checks:
  max2112            Does the tuner driver program the MAX2112 the way its datasheet says?
  antenna            The antenna feed monitor reads the fitted parts right and does what its header says.
  dsp                Gate the on-board Iridium DSP (firmware/soop/soop_dsp.c) against a simulated sky.
  burst              Gate the burst DSP: detection and carrier-frequency estimation from I/Q.
  ephemeris          Gate the real Iridium ephemeris: SGP4 + TLE, with the TEME->ECEF frame conversion.
  sgp4               Gate: C SGP4 agrees with Python sgp4.api.Satrec.
  solver             Prove the on-board C solver agrees with the Python reference, and compiles for the H743.
  nav                Gate the on-board navigation (firmware/soop/soop_nav.c) against simulated flights.
  spice              Gate wrapper around the SPICE suite in sim/ (see sim/run_suite.py).
"""
import csv, json, math, os, re, shutil, subprocess, sys, tempfile
import design, soop_burst, soop_scenario, soop_solver
import iridium_sig as sig
import soop_solver as sol

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOARD = (sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv
         else os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb"))

SOOP = os.path.join(REPO, 'firmware', 'soop')


#max2112

"""Does the tuner driver program the MAX2112 the way its datasheet says?

Usage:  python3 tools/check_soop.py max2112 [--self-test]

firmware/soop/soop_max2112.c builds the 12-byte register image AP_SoOP_MAX2112 writes
and decodes the two status bytes. This runs it on the host through max2112_host and
decodes every byte again here, field by field, from docs/datasheets/MAX2112.pdf:

1. Tables 2-13: FRAC = 1, CPMP = 00, CPLIN = 01, XD = /1, R = 1, D24 by the 1125 MHz
   rule, CPS = ICP = 0 (600 uA, sim/pll.py's loop), VCO start 11001 with VAS on, LPF at
   its 4 MHz minimum, STBY/PWDN = 0, BBG as asked, nothing shut down, TURBO = 1;
2. the LO the bytes program is within half a 2^-20 step of the one asked for, and is
   the one reported back - over the Iridium band, at the flight LO from soop_signal.h,
   and just under a multiple of the reference, where the fraction must carry into N;
3. the datasheet's own example: F = 194,180 packs as 0010 / 11110110 / 10000100;
4. N outside 19-251 is refused;
5. Tables 14-15: every pair of status bytes decodes to locked exactly when VASE, VASA
   and LD are set and the VTUNE ADC is off both rails;
6. soop_max2112.c compiles for the H743 (make arm).

--self-test compiles mutants of soop_max2112.c (no carry, TURBO off, CPLIN wrong,
ADC 111 read as locked, D24 inverted) and exits 0 only if each one fails.
"""

REF = 25.0e6                      #Y2, the TCXO
STEP = REF / 2 ** 20


def flight_lo():
    sig = open(os.path.join(SOOP, "soop_signal.h")).read()
    ring = float(re.search(r"#define SOOP_F_RING_ALERT\s+([\d.eE+]+)", sig).group(1))
    off = float(re.search(r"#define SOOP_LO_OFFSET_HZ\s+\(?([-\d.eE+]+)", sig).group(1))
    return ring + off


def soop_max2112_build(src_dir, out):
    r = subprocess.run(["cc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Wshadow", "-o", out,
                        os.path.join(SOOP, "max2112_host.c"),
                        os.path.join(src_dir, "soop_max2112.c"), "-I", SOOP, "-lm"],
                       capture_output=True, text=True)
    return r.returncode == 0, r.stderr


def query(host, lines):
    r = subprocess.run([host], input="\n".join(lines) + "\n", capture_output=True,
                       text=True, check=True)
    return r.stdout.split("\n")[:len(lines)]


def decode(regs):
    """The datasheet's fields, from the bytes alone."""
    r = regs
    return dict(
        FRAC=r[0] >> 7, N=((r[0] & 0x7F) << 8) | r[1],
        CPMP=r[2] >> 6, CPLIN=(r[2] >> 4) & 3, F=((r[2] & 0x0F) << 16) | (r[3] << 8) | r[4],
        XD=r[5] >> 5, R=r[5] & 0x1F,
        D24=r[6] >> 7, CPS=(r[6] >> 6) & 1, ICP=(r[6] >> 5) & 1,
        VCO=r[7] >> 3, VAS=(r[7] >> 2) & 1, ADL=(r[7] >> 1) & 1, ADE=r[7] & 1,
        LPF=r[8], STBY=r[9] >> 7, PWDN=(r[9] >> 5) & 1, BBG=r[9] & 0x0F,
        SHDN=r[10] & 0x7F, CPTST=r[11] >> 5, TURBO=(r[11] >> 3) & 1, LDMUX=r[11] & 7,
    )


def evaluate(host):
    fails = []
    lo_f = flight_lo()
    cases = [(lo, bbg) for lo in (1616.0e6, 1621.25e6, 1626.5e6, lo_f) for bbg in (0, 4, 15)]
    cases += [(1625.0e6 - 3.0, 4), (1600.0e6 - 1.0, 4), (1000.0e6, 4)]
    out = query(host, [f"regs {lo!r} {REF!r} {bbg}" for lo, bbg in cases])
    for (lo, bbg), line in zip(cases, out):
        p = line.split()
        if p[0] != "0":
            fails.append(f"LO {lo / 1e6:.6f} MHz refused")
            continue
        d = decode([int(x, 16) for x in p[1:13]])
        want = dict(FRAC=1, CPMP=0, CPLIN=1, XD=0, R=1, D24=int(lo < 1125e6), CPS=0, ICP=0,
                    VCO=0b11001, VAS=1, ADL=0, ADE=0, LPF=12, STBY=0, PWDN=0, BBG=bbg,
                    SHDN=0, CPTST=0, TURBO=1, LDMUX=0)
        for k, v in want.items():
            if d[k] != v:
                fails.append(f"LO {lo / 1e6:.6f} MHz bbg {bbg}: {k} = {d[k]}, datasheet wants {v}")
        prog = REF * (d["N"] + d["F"] / 2 ** 20)
        if abs(prog - lo) > STEP / 2 + 1e-6:
            fails.append(f"LO {lo / 1e6:.6f} MHz: the bytes program {prog / 1e6:.6f} MHz, "
                         f"{prog - lo:+.1f} Hz off (half a step is {STEP / 2:.1f} Hz)")
        if abs(prog - float(p[13])) > 1e-3:
            fails.append(f"LO {lo / 1e6:.6f} MHz: reports {float(p[13]) / 1e6:.6f} MHz but "
                         f"programs {prog / 1e6:.6f} MHz")
    #the datasheet example: F = 194,180 = 0x2F684
    lo_ex = REF * (65 + 194180 / 2 ** 20)
    p = query(host, [f"regs {lo_ex!r} {REF!r} 0"])[0].split()
    if [p[3][1], p[4], p[5]] != ["2", "f6", "84"]:
        fails.append(f"F = 194,180 packs as {p[3][1]} {p[4]} {p[5]}, the datasheet's default "
                     f"is 2 f6 84")
    #n limits
    for n, ok in ((18, False), (19, True), (251, True), (252, False)):
        rc = query(host, [f"regs {REF * n + 1000.0!r} {REF!r} 0"])[0].split()[0]
        if (rc == "0") != ok:
            fails.append(f"N = {n} {'refused' if ok else 'accepted'}; the datasheet allows 19-251")
    #every status pair
    pairs = [(s1, s2) for s1 in range(0, 256, 16) for s2 in range(256)]
    got = query(host, [f"lock {s1:x} {s2:x}" for s1, s2 in pairs])
    bad = 0
    for (s1, s2), line in zip(pairs, got):
        lk, vco, adc = (int(x) for x in line.split())
        want = (s1 & 0x60) == 0x60 and bool(s1 & 0x10) and (s2 & 7) not in (0, 7)
        if lk != int(want) or vco != s2 >> 3 or adc != s2 & 7:
            bad += 1
            if bad <= 3:
                fails.append(f"status {s1:02x} {s2:02x}: locked {lk} vco {vco} adc {adc}, "
                             f"Tables 14-15 say locked {int(want)} vco {s2 >> 3} adc {s2 & 7}")
    return fails, len(cases), len(pairs), lo_f


MUTANTS = [
    ("no carry from F into N",
     r"const double steps = floor\(lo_hz / ref_hz \* 1048576.0 \+ 0.5\);\n"
     r"    const uint32_t N = \(uint32_t\)\(steps / 1048576.0\);\n"
     r"    const uint32_t F = \(uint32_t\)\(steps - \(double\)N \* 1048576.0\);",
     "const uint32_t N = (uint32_t)(lo_hz / ref_hz);\n"
     "    const uint32_t F = (uint32_t)floor((lo_hz / ref_hz - N) * 1048576.0 + 0.5) & 0xFFFFF;"),
    ("TURBO off", r"regs\[0x0B\] = 0x08;", "regs[0x0B] = 0x00;"),
    ("CPLIN 10", r"0x10 \| \(\(F >> 16\)", "0x20 | ((F >> 16)"),
    ("ADC 111 read as locked", r" && a != 7;", ";"),
    ("D24 inverted", r"lo_hz < 1125.0e6 \? 0x80 : 0x00", "lo_hz < 1125.0e6 ? 0x00 : 0x80"),
]


def self_test():
    src = open(os.path.join(SOOP, "soop_max2112.c")).read()
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for name, pat, rep in MUTANTS:
            mut, n = re.subn(pat, lambda _m: rep, src)
            if n != 1:
                print(f"  STALE  {name}: the pattern no longer matches soop_max2112.c")
                ok = False
                continue
            open(os.path.join(tmp, "soop_max2112.c"), "w").write(mut)
            host = os.path.join(tmp, "mutant")
            built, err = soop_max2112_build(tmp, host)
            caught = not built or bool(evaluate(host)[0])
            ok &= caught
            print(f"  {'caught' if caught else 'MISSED'}  {name}")
    return ok


def run_max2112():
    host = os.path.join(SOOP, "max2112_host")
    r = subprocess.run(["make", "-s", "max2112_host"], cwd=SOOP, capture_output=True, text=True)
    if r.returncode:
        print(f"MAX2112 CHECK FAILED - max2112_host did not build:\n{r.stderr}")
        return 1
    fails, n_lo, n_st, lo_f = evaluate(host)
    if shutil.which("arm-none-eabi-gcc"):
        r = subprocess.run(["make", "-s", "arm"], cwd=SOOP, capture_output=True, text=True)
        if r.returncode or not os.path.exists(os.path.join(SOOP, "soop_max2112.o")):
            fails.append(f"soop_max2112.c does not compile for the H743: {r.stderr.strip()[:200]}")
    else:
        fails.append("arm-none-eabi-gcc not found, so the H743 build is unproven")
    if "--self-test" in sys.argv:
        print(f"  {'clean' if not fails else 'NOT CLEAN'}  the driver as written")
        ok = not fails and self_test()
        print("self-test passed: every mutant is caught" if ok else "SELF-TEST FAILED")
        return 0 if ok else 1
    for f in fails:
        print(f"  FAIL  {f}")
    print(f"MAX2112 CHECK {'FAILED' if fails else 'PASSED'}: {len(fails)} failure(s); "
          f"{n_lo} register images and {n_st} status pairs against the datasheet; "
          f"flight LO {lo_f / 1e6:.6f} MHz")
    return 1 if fails else 0


#antenna

"""The antenna feed monitor reads the fitted parts right and does what its header says.

Usage: python3 tools/check_soop.py antenna

1. firmware/soop/soop_ant.c's defaults are design.ANT_FEED's;
2. the thresholds fit the parts: the HC610's 15 mA reads OK with room both ways, the
   short threshold sits under the INA180's saturation, and U24's short-circuit current
   lands above it;
3. the state machine, run on the host through ant_host, goes open -> ok -> short -> feed
   off -> retry, ignores a glitch shorter than settle_s, and stays off when disabled;
4. soop_ant.c compiles for the H743 (make arm).
"""

def ohms(v):
    return float(v.replace("R", ".")) if "R" in v else float(v)


def run(lines):
    r = subprocess.run([os.path.join(SOOP, "ant_host")], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, check=True)
    return [l.split() for l in r.stdout.splitlines()]


def run_antenna():
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


#dsp

"""Gate the on-board Iridium DSP (firmware/soop/soop_dsp.c) against a simulated sky.

The sky comes from tools/soop_scenario.py with the board's impairments, and its truth file
is the oracle: every detection is matched to a real burst by time and frequency, so a
detection that is not a burst counts as false, and a frequency is judged against what was
actually transmitted. Also asserts the C and Python constants agree, and that the DSP
compiles freestanding for the H743. Last, a bench-kit recording (rtl_sdr cu8 at 2 MSPS,
centred off the board's LO) goes through firmware/soop/iq_import.c into the same DSP: every
burst must come out at its RF frequency less the LO, at its time - which proves the shift,
its sign, the decimation and the delay that tools/soop_bench.py relies on.

Usage:  python3 tools/check_soop.py dsp [--slots N] [--keep DIR]
"""

soop_dsp_GATES = dict(detect_min=0.90,      #of eligible bursts at C/N0 >= strong
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


def soop_dsp_build(tmp):
    exe = os.path.join(tmp, "dsp_host")
    r = subprocess.run(["cc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Wshadow", "-Werror", "-o", exe,
                        os.path.join(SOOP, "dsp_host.c"), os.path.join(SOOP, "soop_dsp.c"), "-lm"],
                       capture_output=True, text=True)
    if r.returncode:
        return None, r.stderr
    obj = os.path.join(tmp, "soop_dsp.o")
    r = subprocess.run(["arm-none-eabi-gcc", "-c", "-O2", "-std=c99", "-Wall", "-Wextra", "-Wshadow", "-Werror",
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
    r = subprocess.run(["cc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Wshadow", "-Werror", "-o", exe,
                        os.path.join(SOOP, "iq_import.c"), "-lm"], capture_output=True, text=True)
    if r.returncode:
        return False, "iq_import build: " + r.stderr.strip()[:300]
    d = os.path.join(tmp, "rtl")
    truth = soop_scenario.make_rtl(d)
    board = os.path.join(d, "board.iq")
    r = subprocess.run([exe, os.path.join(d, "rec.cu8"), board, "--format", "cu8",
                        "--fs", str(truth["fs"]), "--fc", str(truth["fc"])] + sig.amp_args(),
                       capture_output=True, text=True)
    if r.returncode:
        return False, "iq_import: " + r.stderr.strip()[:300]
    lag = int(re.search(r"delays by (\d+)", r.stderr).group(1))   #the import's own filter delay
    out = subprocess.run([dsp_exe, board], capture_output=True, text=True)
    rows = list(csv.DictReader(out.stdout.splitlines()))
    lo = sig.F_RING_ALERT + sig.LO_OFFSET_HZ
    worst_f = worst_t = 0.0
    found = 0
    for b in truth["bursts"]:
        m = [x for x in rows if abs((int(x["t_start"]) - lag) / sig.FS_CAPTURE - b["start"]) < 0.003]
        if len(m) != 1:
            continue
        found += 1
        worst_f = max(worst_f, abs(float(m[0]["f_hz"]) - (b["f_rf"] - lo)))
        worst_t = max(worst_t, abs((int(m[0]["t_start"]) - lag) / sig.FS_CAPTURE - b["start"]))
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
    strong = [i for i in el if tr[i]["cn0_dbhz"] >= soop_dsp_GATES["strong_dbhz"]]
    det_strong = sum(1 for i in strong if i in matched)
    e_strong = sorted(abs(e) for c, e, _ in errs if c >= soop_dsp_GATES["strong_dbhz"])
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


def run_dsp():
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
    exe, info = soop_dsp_build(tmp)
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

    g = soop_dsp_GATES
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

    #the same sky plus a steady spur and one drifting through the band, as a buck's harmonic would
    ra = sig.baseband_hz(sig.F_RING_ALERT)
    spurs = ((ra - 30_000.0, 0.0, 60.0), (ra + 20_000.0, -300.0, 60.0))
    sp = soop_scenario.make_iq(os.path.join(tmp, "spur"), slots, seed=21, cn0_lo=42.0, cn0_hi=70.0,
                               noise_counts=600.0, spurs=spurs)
    out = subprocess.run([exe, os.path.join(tmp, "spur", "iq.bin")], capture_output=True, text=True)
    rows_s = list(csv.DictReader(out.stdout.splitlines()))
    rs = score(sp, rows_s)

    def clear(b):         #a burst whose own spectrum the spur does not sit on
        t = b["centre"] / sp["fs"]
        return all(abs(b["f_hz"] - (f0 + drift * t)) > 5000 for f0, drift, _ in spurs)
    rc = score(dict(sp, bursts=[b for b in sp["bursts"] if clear(b)]), rows_s)
    rate_s = rc["det_strong"] / max(1, rc["n_strong"])
    good = rs["false"] <= g["false_max"] * max(1, rs["n_det"]) and rate_s >= g["detect_min"]
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  with two 60 dB-Hz spurs in the band, one drifting "
          f"300 Hz/s: {rs['false']} false of {rs['n_det']}; {rate_s:.0%} of bursts over 5 kHz "
          f"from a spur detected at >= {g['strong_dbhz']:.0f} dB-Hz "
          f"({rs['det_strong'] / max(1, rs['n_strong']):.0%} counting those on it)")

    #Iridium's duplex channels about 1 MHz below the LO fold onto Ring Alert at the 1 MSPS raw
    dup = soop_scenario.make_duplex(os.path.join(tmp, "duplex"), max(20, slots // 3), seed=22,
                                    cn0_lo=42.0, cn0_hi=70.0, noise_counts=600.0)
    out = subprocess.run([exe, os.path.join(tmp, "duplex", "iq.bin")], capture_output=True, text=True)
    n_false = len(list(csv.DictReader(out.stdout.splitlines())))
    good = n_false <= g["false_max"] * dup["bursts"]
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  {n_false} detections from {dup['bursts']} duplex bursts "
          f"folded onto Ring Alert from {dup['channels']} channels (limit {g['false_max']:.0%})")

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


#burst

"""Gate the burst DSP: detection and carrier-frequency estimation from I/Q."""

def run_burst():
    try:
        r = soop_burst.selftest()
    except Exception as e:                      #a numeric blow-up must read as a failure
        print(f"BURST DSP CHECK FAILED - {type(e).__name__}: {e}")
        return 1

    passed, total = r["checks"]
    if r["ok"]:
        cn0 = r["snr_db"] + 10 * math.log10(soop_burst.SAMPLE_RATE)
        print(f"BURST DSP OK - {passed}/{total} assertions, p90 {r['p90_hz']:.2f} Hz < 5 Hz "
              f"at C/N0 {cn0:.0f} dB-Hz ({r['n']} bursts)")
        return 0
    print(f"BURST DSP CHECK FAILED - {passed}/{total} assertions hold")
    return 1


#ephemeris

"""Gate the real Iridium ephemeris: SGP4 + TLE, with the TEME->ECEF frame conversion."""

def run_ephemeris():
    try:
        r = soop_solver.ephemeris_test()
    except RuntimeError as e:
        print(f"EPHEMERIS CHECK FAILED - {e}")
        return 1
    except Exception as e:                       #a malformed catalogue, a bad TLE
        print(f"EPHEMERIS CHECK FAILED - {type(e).__name__}: {e}")
        return 1

    passed, total = r["checks"]
    med = r["median_m"]
    if r["ok"]:
        print(f"EPHEMERIS OK - {passed}/{total} assertions on {r['n_sats']} real "
              f"satellites" + (f", {med:.0f} m median recovery at 5 Hz / 60 bursts"
                               if med is not None else ""))
        return 0
    print(f"EPHEMERIS CHECK FAILED - {passed}/{total} assertions hold")
    return 1


#sgp4

"""Gate: C SGP4 agrees with Python sgp4.api.Satrec."""

soop_sgp4_TLE  = os.path.join(REPO, "sitl", "tle", "iridium-next.tle")
SRC_C  = os.path.join(REPO, "firmware", "soop", "sgp4.c")
SRC_T  = os.path.join(REPO, "firmware", "soop", "sgp4_host_test.c")

OFFSETS_DAYS = [0.0, +1.0, -1.0, +3.0, -3.0]
POS_TOL_M  = 1000.0   #1 km
VEL_TOL_MS = 1.5      #m/s


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
    """Compile sgp4.c + sgp4_host_test.c -> binary."""
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


def run_sgp4():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump-ref", action="store_true",
                    help="Print reference table to stdout and exit")
    ap.add_argument("--tle", default=soop_sgp4_TLE, help="TLE file (default: sitl/tle/iridium-next.tle)")
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


#solver

"""Prove the on-board C solver agrees with the Python reference, and compiles for the H743."""

SOLVE_DIR = os.path.join(REPO, "firmware", "soop")
TOL_M = 1e-3          #metres; both sides are double precision and run the same algorithm
CFLAGS = ["-O2", "-std=c99", "-Wall", "-Wextra"]


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def run_solver():
    cc = os.environ.get("CC", "cc")
    arm = os.environ.get("ARMGCC", "arm-none-eabi-gcc")
    tmp = tempfile.mkdtemp(prefix="soop_c_")
    obs = os.path.join(tmp, "obs.txt")
    exe = os.path.join(tmp, "soop_host")
    armobj = os.path.join(tmp, "soop_solve_arm.o")

    #1. the reference solution and the identical inputs
    r = _run([sys.executable, "tools/soop_solver.py", "--emit-obs", obs], cwd=REPO)
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

    #2. host build + the differential comparison
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

    #3. cross-compile for the actual target silicon
    a = _run([arm, "-c", *CFLAGS, "-mcpu=cortex-m7", "-mthumb", "-mfpu=fpv5-d16",
              "-mfloat-abi=hard", "-o", armobj, "soop_solve.c"], cwd=SOLVE_DIR)
    built = a.returncode == 0 and os.path.exists(armobj)
    print(f"  {'ok  ' if built else 'FAIL'}  cross-compiles for the H743 (Cortex-M7, "
          f"hard float)" + ("" if built else f": {a.stderr.strip()[:200]}"))

    ok = agree and built
    print("\n" + (f"SOOP-C OK - C solver agrees with Python to {dpos:.2e} m and builds "
                  f"for the target" if ok else "SOOP-C CHECK FAILED"))
    return 0 if ok else 1


#nav

"""Gate the on-board navigation (firmware/soop/soop_nav.c) against simulated flights.

Each flight comes from tools/soop_scenario.py obs: real Iridium orbits displaced by an
ephemeris error the filter is not told (public TLEs', or Iridium's own orbits' where the
catalogue marks them so), a drone flying 15 m/s legs, a TCXO that wanders with
temperature, a sample clock and GPS time tags that are both off, a flight-EKF velocity that
drifts once GNSS goes, the DSP's error at each burst's C/N0, outliers and false bursts. The
truth file is the oracle: every fix is compared with where the aircraft was, and every burst
the filter used with the satellite and channel that actually sent it.

Also checks the C ephemeris against the Python reference (tools/soop_solver.py) and both
against Vallado's published TEME->ITRF example, and that the code builds for the H743.

Usage:  python3 tools/check_soop.py nav [--quick] [--keep DIR]
"""

soop_nav_TLE = os.path.join(REPO, "sitl", "tle", "iridium-next.tle")
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

soop_nav_GATES = dict(median_m=400.0,       #horizontal error over every denied second, all flights
             p95_m=1200.0,
             max_m=2500.0,
             within2_min=0.90,     #fixes inside 2 x reported hacc (a 2-D Gaussian gives 0.86+)
             avail_min=0.95,       #denied seconds with a valid fix
             wrong_max=0.002,      #fused bursts credited to the wrong satellite or channel
             false_max=0.02,       #false bursts that got fused
             #the way toward 20 m (docs/IRIDIUM-RESEARCH.md)
             fine_median_m=60.0,
             fine_p95_m=200.0)


def soop_nav_build(tmp):
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
    out = subprocess.run([exe, soop_nav_TLE, "--ephem"] + [f"{t:.3f}" for t in ts],
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
    e = subprocess.run([exe, soop_nav_TLE, "--teme", f"{t_ut1:.6f}", "5094180.16210", "6127644.65950",
                        "6380344.53270", "-4746.131487", "785.818041", "5531.931288"],
                       capture_output=True, text=True).stdout.split()
    dr = math.dist([float(x) for x in e[1:4]], (-1033479.3830, 7901295.2754, 6380356.5958))
    dv = math.dist([float(x) for x in e[4:7]], (-3225.636520, -2872.451450, 5531.924446))
    ok = n >= 200 and worst_r < 1.0 and worst_v < 1e-3 and dr < 50.0 and dv < 0.1
    return ok, (f"C ephemeris = Python on {n} satellite-epochs to {worst_r * 1000:.0f} mm, "
                f"{worst_v * 1e6:.0f} um/s; Vallado example {dr:.1f} m, {dv * 1000:.0f} mm/s")


def cat_age(exe, t_utc):
    """soop_nav's view of the catalogue at UTC t_utc (s since J2000)."""
    out = subprocess.run([exe, soop_nav_TLE, "--cat-age", f"{t_utc:.1f}"], capture_output=True,
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


def run_nav():
    keep = sys.argv[sys.argv.index("--keep") + 1] if "--keep" in sys.argv else None
    flights = QUICK if "--quick" in sys.argv else FLIGHTS
    print("=== on-board Iridium navigation against simulated GNSS-denied flights ===")
    checks = []
    tmp = keep or tempfile.mkdtemp(prefix="soop_nav_")
    os.makedirs(tmp, exist_ok=True)
    exe, info = soop_nav_build(tmp)
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

    g = soop_nav_GATES
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


#spice

"""Gate wrapper around the SPICE suite in sim/ (see sim/run_suite.py).

The suite itself lives beside the decks it runs; this wrapper exists so the
preflight gate can treat the simulation as one more tool that prints a line and
exits nonzero when a bound is violated.

    python3 tools/check_soop.py spice
"""

def run_spice():
    sys.path.insert(0, os.path.join(REPO, "sim"))
    import run_suite
    chk, failed = run_suite.run()
    return run_suite.report(chk, failed)


CHECKS = {
    "max2112": run_max2112,
    "antenna": run_antenna,
    "dsp": run_dsp,
    "burst": run_burst,
    "ephemeris": run_ephemeris,
    "sgp4": run_sgp4,
    "solver": run_solver,
    "nav": run_nav,
    "spice": run_spice,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        print(__doc__)
        return 2
    return CHECKS[sys.argv.pop(1)]()


if __name__ == "__main__":
    sys.exit(main())
