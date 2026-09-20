#!/usr/bin/env python3
"""Burst detection and carrier-frequency estimation from I/Q: the DSP the solver requires."""
import cmath
import math
import random
import sys

# ------------------------------------------------------------------- signal constants
SYMBOL_RATE = 25_000.0        # baud
BURST_SYMBOLS = 207           # ~8.28 ms
F_CARRIER = 1_626_270_000.0   # Hz, Ring Alert
MAX_DOPPLER = 40_700.0        # Hz, f*v/c at the worst-case range rate
SAMPLE_RATE = 400_000.0       # Hz


# ---------------------------------------------------------------------- a tiny FFT
def fft(a):
    """Iterative radix-2 FFT. Pure Python on purpose: this repo carries no numpy, and the
    transform here is small (<= 4096 points) so the cost is milliseconds. Used only for
    coarse acquisition; the precision comes from the direct periodogram below.
    """
    n = len(a)
    if n & (n - 1):
        raise ValueError("fft length must be a power of two")
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    length = 2
    while length <= n:
        wl = cmath.exp(-2j * math.pi / length)
        for i in range(0, n, length):
            w = 1 + 0j
            for k in range(i, i + length // 2):
                u, v = a[k], a[k + length // 2] * w
                a[k], a[k + length // 2] = u + v, u - v
                w *= wl
        length <<= 1
    return a


def _dft_mag(z, fs, f):
    """|sum z[n] exp(-j2pi f n/fs)| evaluated directly. Renormalises the progressive phasor
    every 256 samples so accumulated rounding cannot bias the peak.
    """
    w = 2 * math.pi * f / fs
    acc, e, step = 0j, 1 + 0j, cmath.exp(-1j * w)
    for i, c in enumerate(z):
        acc += c * e
        e *= step
        if i % 256 == 255:
            e = cmath.exp(-1j * w * (i + 1))
    return abs(acc)


# ------------------------------------------------------------------- synthesis
def make_burst(fs=SAMPLE_RATE, rs=SYMBOL_RATE, n_sym=BURST_SYMBOLS, f_off=0.0,
               snr_db=10.0, rng=None):
    """One complex-baseband QPSK burst at carrier offset `f_off`, plus AWGN."""
    rng = rng or random.Random(0)
    sps = int(round(fs / rs))
    n = n_sym * sps
    amp = 1.0
    # QPSK: one of four constellation points, Gray-labelled but the estimator does not
    # care about labelling - only that the modulation is constant-modulus and 4-fold.
    pts = [complex(math.cos(a), math.sin(a))
           for a in (math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4)]
    x = []
    for k in range(n_sym):
        s = pts[rng.randrange(4)]
        for _ in range(sps):
            x.append(s)
    # carrier offset
    w = 2 * math.pi * f_off / fs
    x = [x[i] * cmath.exp(1j * w * i) for i in range(n)]
    # AWGN at the requested per-sample SNR
    sigma = amp / math.sqrt(10 ** (snr_db / 10.0))
    x = [c + complex(rng.gauss(0, sigma / math.sqrt(2)), rng.gauss(0, sigma / math.sqrt(2)))
         for c in x]
    return x


def make_recording(burst, lead_samples, total_samples, snr_db, rng):
    """A longer I/Q capture with the burst at a known position and noise before/after."""
    sigma = 1.0 / math.sqrt(10 ** (snr_db / 10.0))
    rec = [complex(rng.gauss(0, sigma / math.sqrt(2)), rng.gauss(0, sigma / math.sqrt(2)))
           for _ in range(total_samples)]
    for i, c in enumerate(burst):
        if lead_samples + i < total_samples:
            rec[lead_samples + i] += c
    return rec


# ------------------------------------------------------------------- detection
def detect_burst(rec, win, threshold_db=6.0):
    """Sliding-window energy detector. Returns the start index of the strongest window, or
    None if nothing rises `threshold_db` above the median noise floor.
    """
    n = len(rec)
    if n < win:
        return None
    e = [abs(c) ** 2 for c in rec]
    run = sum(e[:win])
    energies = [run]
    for i in range(1, n - win + 1):
        run += e[i + win - 1] - e[i - 1]
        energies.append(run)
    floor = sorted(energies)[max(1, len(energies) // 10)] or 1e-12
    peak = max(energies)
    if peak < floor * (10 ** (threshold_db / 10.0)):
        return None
    return energies.index(peak)


# ------------------------------------------------------------------- estimation
def estimate_offset(burst_slice, fs=SAMPLE_RATE):
    """Carrier offset in Hz from a burst's samples: 4th-power modulation removal to
    collapse QPSK, then an FFT peak for coarse acquisition, then PERIODOGRAM refinement.
    """
    z = [c ** 4 for c in burst_slice]      # QPSK -> a single tone at 4x the offset
    n = len(z)
    nfft = 1
    while nfft < n:
        nfft <<= 1
    mag = [abs(c) for c in fft(z + [0j] * (nfft - n))]
    k = mag.index(max(mag))
    # signed frequency: the 4x tone spans +/-4*f_off, so a negative offset lands above
    # fs/2 and would otherwise be reported as a positive alias
    bin_ = fs / nfft
    f4 = (k if k <= nfft // 2 else k - nfft) * bin_
    lo, hi, steps = f4 - 3 * bin_, f4 + 3 * bin_, 180
    best = max(((_dft_mag(z, fs, lo + (hi - lo) * j / steps), lo + (hi - lo) * j / steps)
                for j in range(steps + 1)), key=lambda t: t[0])
    return best[1] / 4.0


def run(snr_db, seed, fs=SAMPLE_RATE, rs=SYMBOL_RATE):
    """One end-to-end trial: synthesise, detect, estimate. Returns (detected_ok,
    frequency_error_hz).
    """
    rng = random.Random(seed)
    f_off = rng.uniform(-MAX_DOPPLER, MAX_DOPPLER)
    sps = int(round(fs / rs))
    n = BURST_SYMBOLS * sps
    burst = make_burst(fs, rs, BURST_SYMBOLS, f_off, snr_db, rng)
    # capture: the burst starts somewhere inside a window ~4x its length
    lead = rng.randrange(n, 3 * n)
    total = lead + n + 2 * n
    rec = make_recording(burst, lead, total, snr_db, rng)
    start = detect_burst(rec, n)
    if start is None:
        return False, None
    det_ok = abs(start - lead) <= 2 * sps          # within two symbols
    # Estimate over the true burst extent (detection error would add its own bias; the
    # detector's job is asserted above, the estimator's job is asserted here).
    s = estimate_offset(rec[lead:lead + n], fs)
    return det_ok, abs(s - f_off)


def selftest(seeds=60, snr_db=6.0, fail_hz=5.0):
    """Assert the detector finds the burst and the estimator meets the solver's 5 Hz."""
    print("=== burst detection + carrier estimation, against a KNOWN offset ===")
    cn0 = snr_db + 10 * math.log10(SAMPLE_RATE)
    print(f"    {SYMBOL_RATE/1e3:.0f} kbaud QPSK, {BURST_SYMBOLS} symbols "
          f"({BURST_SYMBOLS/SYMBOL_RATE*1e3:.2f} ms), fs {SAMPLE_RATE/1e3:.0f} kHz")
    print(f"    SNR {snr_db:.0f} dB/sample  =  C/N0 {cn0:.0f} dB-Hz in this bandwidth")
    detected, errs = 0, []
    for s in range(seeds):
        d, e = run(snr_db, s)
        if d:
            detected += 1
        if e is not None:
            errs.append(e)
    checks = []
    good = detected == seeds
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  burst detected within 2 symbols in "
          f"{detected}/{seeds} captures")
    if not errs:
        print("  FAIL  no frequency estimate produced")
        return dict(ok=False, checks=(0, 1), n=0, rms_hz=None, p90_hz=None, snr_db=snr_db)
    errs.sort()
    rms = math.sqrt(sum(e * e for e in errs) / len(errs))
    p90 = errs[int(len(errs) * 0.9)]
    good = p90 < fail_hz
    checks.append(good)
    print(f"  {'ok  ' if good else 'FAIL'}  carrier error: RMS {rms:5.2f} Hz, p90 "
          f"{p90:5.2f} Hz over {len(errs)} bursts (solver needs < {fail_hz:.0f} Hz)")
    print("\n  NOTE: synthetic I/Q only - rectangular QPSK, AWGN, no multipath, no "
          "adjacent\n  channel. It proves the ALGORITHM reaches the solver's precision, "
          "NOT that the\n  receiver does on a real sky; that is T3b plus recorded I/Q.")
    ok = all(checks)
    print("\n" + (f"BURST DSP OK - {sum(checks)}/{len(checks)} assertions, "
                  f"p90 {p90:.2f} Hz < {fail_hz:.0f} Hz" if ok else "BURST DSP FAILED"))
    return dict(ok=ok, checks=(sum(checks), len(checks)), n=len(errs),
                rms_hz=rms, p90_hz=p90, snr_db=snr_db)


def sweep():
    print("=== carrier-frequency error vs SNR (RMS / p90 over 200 bursts) ===")
    print(f"    {'SNR dB':>7} {'detected':>9} {'RMS Hz':>9} {'p90 Hz':>9}")
    for snr in (0.0, 3.0, 6.0, 10.0, 14.0):
        detected, errs = 0, []
        for s in range(200):
            d, e = run(snr, s)
            if d:
                detected += 1
            if e is not None:
                errs.append(e)
        if not errs:
            print(f"    {snr:7.0f} {detected:6d}/200        -         -")
            continue
        errs.sort()
        rms = math.sqrt(sum(e * e for e in errs) / len(errs))
        print(f"    {snr:7.0f} {detected:6d}/200 {rms:9.2f} {errs[int(len(errs)*0.9)]:9.2f}")
    print("\n    The 5 Hz requirement is met down to the SNR where the 4th-power line "
          "is still\n    coherent; below that the detection rate, not the precision, "
          "is the failure mode.")
    return 0


def main():
    if "--sweep" in sys.argv:
        return sweep()
    r = selftest()
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
