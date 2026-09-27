#!/usr/bin/env python3
"""A sky to test the Iridium chain against, with the truth written alongside.

Usage:
  soop_scenario.py iq  OUTDIR [--slots N] [--seed S] [--cn0 LO HI] [--noise-counts N]
  soop_scenario.py obs OUTDIR [--minutes M] [--speed V] [--seed S] ...   (see obs --help)
  soop_scenario.py rtl OUTDIR [--seconds S] [--seed S]
"""
import argparse
import cmath
import datetime
import json
import math
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iridium_sig as sig

FS = sig.FS_CAPTURE
SPS = int(round(FS / sig.SYMBOL_RATE))          #20 samples per symbol


#burst waveform
#Root-raised-cosine pulse, unit energy, `span` symbols either side
def rrc_taps(sps=SPS, span=4, alpha=sig.RRC_ALPHA):
    taps = []
    for n in range(-span * sps, span * sps + 1):
        t = n / sps
        if abs(t) < 1e-12:
            h = 1.0 - alpha + 4 * alpha / math.pi
        elif abs(abs(t) - 1 / (4 * alpha)) < 1e-9:
            h = (alpha / math.sqrt(2)) * ((1 + 2 / math.pi) * math.sin(math.pi / (4 * alpha))
                                          + (1 - 2 / math.pi) * math.cos(math.pi / (4 * alpha)))
        else:
            h = (math.sin(math.pi * t * (1 - alpha)) + 4 * alpha * t
                 * math.cos(math.pi * t * (1 + alpha))) / (math.pi * t * (1 - (4 * alpha * t) ** 2))
        taps.append(h)
    e = math.sqrt(sum(h * h for h in taps))
    return [h / e for h in taps]


RRC = rrc_taps()


#preamble (unmodulated carrier), the downlink unique word
def burst_symbols(n_data, rng, modulation="dqpsk"):
    phase, out = 0.0, []
    for _ in range(sig.PREAMBLE_SYMBOLS):
        out.append(cmath.exp(1j * phase))
    for d in sig.UNIQUE_WORD_DL:
        phase += int(d) * math.pi / 2
        out.append(cmath.exp(1j * phase))
    for _ in range(n_data):
        if modulation == "bpsk":
            out.append(cmath.exp(1j * (phase + math.pi * rng.randrange(2))))
        else:
            phase += rng.randrange(4) * math.pi / 2
            out.append(cmath.exp(1j * phase))
    return out


#RRC-shaped symbols at SPS, rotated to `f_hz` with a linear Doppler rate
def burst_waveform(symbols, f_hz, fdot_hz_s, phase0):
    n = (len(symbols) - 1) * SPS + len(RRC)
    x = [0j] * n
    for k, s in enumerate(symbols):
        base = k * SPS
        for j, h in enumerate(RRC):
            x[base + j] += s * h
    p = sum(abs(c) ** 2 for c in x) / n
    g = 1.0 / math.sqrt(p * (1.0 * len(symbols) * SPS / n)) if p > 0 else 1.0
    out, dt = [], 1.0 / FS
    for i, c in enumerate(x):
        t = i * dt
        out.append(c * g * cmath.exp(1j * (phase0 + 2 * math.pi * (f_hz * t + 0.5 * fdot_hz_s * t * t))))
    return out


#the analogue chain between the antenna and the ADC
class FrontEnd:

    def __init__(self, rng, noise_counts=600.0):
        self.amp_err = 10 ** (rng.uniform(-1.0, 1.0) / 20) - 1      #+-1 dB (MAX2112 spec)
        self.phase_err = math.radians(rng.uniform(-3.5, 3.5))        #3.5 deg (MAX2112 spec)
        self.dc = complex(rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05))   #x noise rms
        self.scale = noise_counts / math.sqrt(0.5)    #unit complex noise -> counts per rail
        self.a_hp = 1.0 / (1.0 + 2 * math.pi * sig.DC_NOTCH_HZ / FS)
        rc = 1.0 / (2 * math.pi * sig.OPA_POLE_HZ)
        self.b_lp = (1.0 / FS) / (rc + 1.0 / FS)
        self.x_prev = 0j
        self.y_hp = 0j
        self.y_lp = 0j
        self.clipped = 0

    def run(self, x):
        out = []
        for c in x:
            self.y_hp = self.a_hp * (self.y_hp + c - self.x_prev)       #DC-offset loop
            self.x_prev = c
            i, q = self.y_hp.real, self.y_hp.imag
            q = (1 + self.amp_err) * (q * math.cos(self.phase_err) - i * math.sin(self.phase_err))
            v = complex(i, q) + self.dc                                  #i/Q imbalance, DC
            self.y_lp += self.b_lp * (v - self.y_lp)                     #OPA2374 pole
            ri = int(round(self.y_lp.real * self.scale))
            rq = int(round(self.y_lp.imag * self.scale))
            if abs(ri) > sig.ADC_FULL_SCALE or abs(rq) > sig.ADC_FULL_SCALE:
                self.clipped += 1
            out.append((max(-sig.ADC_FULL_SCALE, min(sig.ADC_FULL_SCALE, ri)),
                        max(-sig.ADC_FULL_SCALE, min(sig.ADC_FULL_SCALE, rq))))
        return out


#iq mode
def make_iq(outdir, slots, seed, cn0_lo, cn0_hi, noise_counts, max_bursts=3):
    rng = random.Random(seed)
    os.makedirs(outdir, exist_ok=True)
    fe = FrontEnd(rng, noise_counts)
    tcxo_hz = rng.uniform(-1, 1) * sig.TCXO_PPM * 1e-6 * sig.F_RING_ALERT
    mcu_ppm = rng.uniform(-1, 1) * sig.MCU_PPM
    margin = int(0.001 * FS)
    slot_len = int(sig.SIMPLEX_SLOT_S * FS) + 2 * margin
    bursts = []
    with open(os.path.join(outdir, "iq.bin"), "wb") as f:
        for s in range(slots):
            buf = [complex(rng.gauss(0, math.sqrt(0.5)), rng.gauss(0, math.sqrt(0.5)))
                   for _ in range(slot_len)]
            for _ in range(rng.randrange(max_bursts + 1)):
                ch = sig.RING_ALERT_INDEX if rng.random() < 0.7 else rng.randrange(4)
                n_data = rng.randrange(120, 200)
                syms = burst_symbols(n_data, rng, rng.choice(("dqpsk", "bpsk")))
                doppler = rng.uniform(-sig.MAX_DOPPLER_HZ, sig.MAX_DOPPLER_HZ)
                fdot = rng.uniform(-400.0, 0.0)          #Doppler only ever falls during a pass
                #what the capture sees: RF offset from the LO, the TCXO
                f_phys = sig.baseband_hz(sig.SIMPLEX_CHANNELS[ch]) + doppler + tcxo_hz
                f_meas = f_phys / (1 + mcu_ppm * 1e-6)
                cn0 = rng.uniform(cn0_lo, cn0_hi)
                amp = math.sqrt(10 ** (cn0 / 10) / FS)
                wave = burst_waveform(syms, f_meas, fdot, rng.uniform(0, 2 * math.pi))
                start = margin + rng.randrange(max(1, slot_len - 2 * margin - len(wave)))
                for i, c in enumerate(wave):
                    if start + i < slot_len:
                        buf[start + i] += amp * c
                sym0 = start + (len(RRC) - 1) // 2          #centre of the first symbol
                n_sym = len(syms)
                bursts.append(dict(
                    slot=s, start=s * slot_len + sym0, n_samples=n_sym * SPS,
                    centre=s * slot_len + sym0 + n_sym * SPS // 2,
                    channel=ch, f_hz=f_meas + fdot * (n_sym / sig.SYMBOL_RATE) / 2,
                    fdot=fdot, cn0_dbhz=cn0, doppler_hz=doppler, symbols=n_sym))
            for i, q in fe.run(buf):
                f.write(struct.pack("<hh", i, q))
    truth = dict(fs=FS, slot_len=slot_len, slots=slots, seed=seed, tcxo_hz=tcxo_hz,
                 mcu_ppm=mcu_ppm, lo_offset_hz=sig.LO_OFFSET_HZ,
                 iq_imbalance=dict(amp_db=20 * math.log10(1 + fe.amp_err),
                                   phase_deg=math.degrees(fe.phase_err)),
                 noise_counts=noise_counts, clipped_samples=fe.clipped,
                 channels_hz=[sig.baseband_hz(c) for c in sig.SIMPLEX_CHANNELS],
                 bursts=bursts)
    json.dump(truth, open(os.path.join(outdir, "truth.json"), "w"), indent=1)
    return truth


#rtl mode
#A recording as the bench kit makes it
def make_rtl(outdir, seconds=0.6, seed=5, fc=1_626_000_000.0, fs=2_000_000.0, n_bursts=8,
             noise_counts=12.0):
    rng = random.Random(seed)
    os.makedirs(outdir, exist_ok=True)
    sps = int(round(fs / sig.SYMBOL_RATE))
    rrc = rrc_taps(sps=sps)
    n = int(seconds * fs)
    sd = math.sqrt(0.5)
    buf = [complex(rng.gauss(0, sd), rng.gauss(0, sd)) for _ in range(n)]
    bursts = []
    slot = int(0.020 * fs)
    for k in range(n_bursts):
        ch = sig.RING_ALERT_INDEX if k % 3 else 3
        f_rf = sig.SIMPLEX_CHANNELS[ch] + rng.uniform(-30_000.0, 30_000.0)
        if ch == 3:                      #a messaging burst the Ring Alert band still holds
            f_rf = sig.SIMPLEX_CHANNELS[ch] + rng.uniform(15_000.0, 30_000.0)
        cn0 = rng.uniform(56.0, 66.0)
        syms = burst_symbols(rng.randrange(120, 180), rng)
        x = [0j] * ((len(syms) - 1) * sps + len(rrc))
        for i, s_ in enumerate(syms):
            for j, h in enumerate(rrc):
                x[i * sps + j] += s_ * h
        p = sum(abs(c) ** 2 for c in x) / (len(syms) * sps)
        amp = math.sqrt(10 ** (cn0 / 10) / fs / p)
        start = int((0.05 + k * (seconds - 0.1) / n_bursts) * fs) + rng.randrange(slot)
        w = 2 * math.pi * (f_rf - fc) / fs
        ph = rng.uniform(0, 2 * math.pi)
        for i, c in enumerate(x):
            if start + i < n:
                buf[start + i] += amp * c * cmath.exp(1j * (ph + w * (start + i)))
        bursts.append(dict(start=(start + (len(rrc) - 1) // 2) / fs, f_rf=f_rf, cn0=cn0,
                           channel=ch, symbols=len(syms)))
    scale, dc = noise_counts, (rng.uniform(-2, 2), rng.uniform(-2, 2))
    raw = bytearray(2 * n)
    for i, c in enumerate(buf):
        raw[2 * i] = max(0, min(255, int(round(127.5 + dc[0] + scale * c.real))))
        raw[2 * i + 1] = max(0, min(255, int(round(127.5 + dc[1] + scale * c.imag))))
    open(os.path.join(outdir, "rec.cu8"), "wb").write(raw)
    truth = dict(fs=fs, fc=fc, seconds=seconds, bursts=bursts)
    json.dump(truth, open(os.path.join(outdir, "truth.json"), "w"), indent=1)
    return truth


#obs mode
#what the DSP delivers, per burst, as a function of C/N0
DSP_TABLE = ((45.0, 0.00, 20.0), (47.5, 0.44, 13.0), (52.5, 0.76, 5.4),
             (57.5, 0.92, 1.6), (62.5, 0.94, 1.15), (68.0, 1.00, 0.83))
DSP_BAND_HZ = 50_000.0            #the DSP searches the Ring Alert channel +-this


#(detection probability, 1-sigma Hz) at a C/N0, interpolated in the table
def dsp_response(cn0):
    t = DSP_TABLE
    if cn0 <= t[0][0]:
        return 0.0, t[0][2]
    for (c0, p0, s0), (c1, p1, s1) in zip(t, t[1:]):
        if cn0 <= c1:
            w = (cn0 - c0) / (c1 - c0)
            return p0 + w * (p1 - p0), math.exp(math.log(s0) + w * (math.log(s1) - math.log(s0)))
    return t[-1][1], t[-1][2]


#First-order Gauss-Markov: stationary sigma, correlation time tau
class GaussMarkov:

    def __init__(self, rng, sigma, tau, x0=None):
        self.rng, self.sigma, self.tau = rng, sigma, tau
        self.x = rng.gauss(0, sigma) if x0 is None else x0

    def step(self, dt):
        a = math.exp(-dt / self.tau)
        self.x = a * self.x + math.sqrt(1 - a * a) * self.sigma * self.rng.gauss(0, 1)
        return self.x


#unit north, east, down vectors in ECEF
def ned_axes(lat_deg, lon_deg):
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    n = (-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la))
    e = (-math.sin(lo), math.cos(lo), 0.0)
    d = (-math.cos(la) * math.cos(lo), -math.cos(la) * math.sin(lo), -math.sin(la))
    return n, e, d


#A multirotor sortie: loiter with GPS
def trajectory(rng, lat0, lon0, h0, gps_s, denial_s, speed, dt=0.1):
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    lat, lon, h = lat0, lon0, h0
    vn = ve = vd = 0.0
    out, t = [], 0.0
    goal, hold, alt_goal = (0.0, 0.0), 0.0, h0
    pn = pe = 0.0
    while t <= gps_s + denial_s + 1e-9:
        if t < gps_s * 0.5:
            cmd = (0.0, 0.0)                              #hover on the pad, GPS good
        else:
            if hold > 0:
                hold -= dt
                cmd = (0.0, 0.0)
            else:
                dn, de = goal[0] - pn, goal[1] - pe
                dist = math.hypot(dn, de)
                if dist < 30.0:
                    r, b = rng.uniform(300, 2500), rng.uniform(0, 2 * math.pi)
                    goal = (pn + r * math.cos(b), pe + r * math.sin(b))
                    alt_goal = h0 + rng.uniform(-40, 60)
                    hold = rng.uniform(5, 40) if rng.random() < 0.3 else 0.0
                    cmd = (0.0, 0.0)
                else:
                    v = min(speed, 0.2 * dist)
                    cmd = (v * dn / dist, v * de / dist)
        k = 1 - math.exp(-dt / 3.0)                        #airframe lag
        vn += k * (cmd[0] - vn)
        ve += k * (cmd[1] - ve)
        vd += k * (max(-3.0, min(3.0, -(alt_goal - h) * 0.1)) - vd)
        out.append((t, lat, lon, h, vn, ve, vd))
        la = math.radians(lat)
        N = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
        M = N * (1 - e2) / (1 - e2 * math.sin(la) ** 2)
        lat += math.degrees(vn * dt / (M + h))
        lon += math.degrees(ve * dt / ((N + h) * math.cos(la)))
        h -= vd * dt
        pn += vn * dt
        pe += ve * dt
        t += dt
    return out


#A flight under the real constellation
def make_obs(outdir, seed=1, gps_min=5.0, denial_min=15.0, speed=15.0, tle_age_d=1.0,
             lat=52.2053, lon=0.1218, h=160.0, rate=1.0, vel_sigma=1.0, beta_sigma=50.0,
             along0_m=300.0, along_km_per_day=1.0, radial_m=100.0, cross_m=200.0, false_rate=0.05, outlier_frac=0.01, static=False):
    import soop_solver as sol
    rng = random.Random(seed)
    os.makedirs(outdir, exist_ok=True)
    tles = sol.load_tles()
    t_utc0 = max(ep for _, _, ep in tles) + datetime.timedelta(days=tle_age_d)
    jd0, fr0 = sol._jday(t_utc0)
    gps_s, denial_s = gps_min * 60.0, denial_min * 60.0
    traj = trajectory(rng, lat, lon, h, gps_s, denial_s, 0.0 if static else speed)
    dt_tr = traj[1][0] - traj[0][0]

    def truth_at(t):
        i = max(0, min(len(traj) - 2, int(t / dt_tr)))
        w = (t - traj[i][0]) / dt_tr
        s = [a + w * (b - a) for a, b in zip(traj[i], traj[i + 1])]
        r = sol.geodetic_to_ecef(s[1], s[2], s[3])
        n, e, d = ned_axes(s[1], s[2])
        v = tuple(s[4] * n[k] + s[5] * e[k] + s[6] * d[k] for k in range(3))
        return r, v, s

    #the receiver's clocks
    f_lo = sig.F_RING_ALERT + sig.LO_OFFSET_HZ
    tcxo0 = rng.uniform(-1, 1) * sig.TCXO_PPM * 1e-6
    #board temperature, deg C
    temp_drive, temp = GaussMarkov(rng, 4.0, 600.0, 0.0), 0.0
    tcxo_walk = 0.0
    mcu0 = rng.uniform(-1, 1) * sig.MCU_PPM * 1e-6
    mcu_ramp = rng.uniform(-1, 1) * 0.3e-6 / 1800.0     #crystal warming, per second
    boot = rng.uniform(20.0, 60.0)                      #board time at t_utc = 0
    gps_lag = rng.uniform(-0.02, 0.02)                  #GPS time-tag error, s

    #the constellation's errors
    sats = {}
    for name, sat, ep in tles:
        age = (t_utc0 - ep).total_seconds() / 86400.0
        sats[sat.satnum] = dict(
            name=name, sat=sat, age_d=age,
            along_m=rng.gauss(0, along0_m + along_km_per_day * 1000.0 * age),
            radial_m=rng.gauss(0, radial_m), cross_m=rng.gauss(0, cross_m),
            beta_hz=rng.gauss(0, beta_sigma))

    #ECEF state of the real satellite at scenario time t (s after t_utc0)
    def sat_true(s, t):
        vs = sol.sat_state_ecef(s["sat"], t_utc0 + datetime.timedelta(seconds=t))
        if vs is None:
            return None
        r, v = vs
        speed_s = math.sqrt(sum(c * c for c in v))
        vs = sol.sat_state_ecef(s["sat"], t_utc0 + datetime.timedelta(
            seconds=t + s["along_m"] / speed_s))
        r, v = vs
        rm = math.sqrt(sum(c * c for c in r))
        ur = [c / rm for c in r]
        hx = (r[1] * v[2] - r[2] * v[1], r[2] * v[0] - r[0] * v[2], r[0] * v[1] - r[1] * v[0])
        hm = math.sqrt(sum(c * c for c in hx))
        uc = [c / hm for c in hx]
        return (tuple(r[k] + s["radial_m"] * ur[k] + s["cross_m"] * uc[k] for k in range(3)), v)

    def elevation(rs, rr):
        d = [rs[k] - rr[k] for k in range(3)]
        rho = math.sqrt(sum(c * c for c in d))
        _, _, dn = ned_axes(*geodetic(rr)[:2])
        return math.degrees(math.asin(-sum(d[k] * dn[k] for k in range(3)) / rho)), rho

    #bursts
    t_end = gps_s + denial_s
    bursts, truth_bursts = [], []
    mcu_err = lambda t: mcu0 + mcu_ramp * t
    board = lambda t: boot + t * (1 + mcu0) + 0.5 * mcu_ramp * t * t
    t_blk = 0.0
    while t_blk < t_end:
        rr_mid, _, _ = truth_at(min(t_end, t_blk + 5.0))
        vis = []
        for num, s in sats.items():
            st = sat_true(s, t_blk + 5.0)
            if st and elevation(st[0], rr_mid)[0] > 5.0:
                vis.append(num)
        for k in range(int(round(10.0 / sig.FRAME_S))):
            t_frame = t_blk + k * sig.FRAME_S
            if t_frame >= t_end:
                break
            for num in vis:
                if rng.random() > rate * sig.FRAME_S:
                    continue
                t = t_frame + rng.uniform(0.002, sig.SIMPLEX_SLOT_S - 0.002)
                rr, vr, _ = truth_at(t)
                s = sats[num]
                st = sat_true(s, t)
                el, rho = elevation(st[0], rr)
                if el < 8.0:
                    continue
                st = sat_true(s, t - rho / sig.C_LIGHT)          #light time
                rs, vs = st
                d = [rs[k] - rr[k] for k in range(3)]
                rho = math.sqrt(sum(c * c for c in d))
                rdot = sum((vs[k] - vr[k]) * d[k] / rho for k in range(3))
                ch = sig.RING_ALERT_INDEX if rng.random() < 0.5 else rng.randrange(4)
                f_ch = sig.SIMPLEX_CHANNELS[ch]
                f_rx = f_ch + s["beta_hz"] - f_ch * rdot / sig.C_LIGHT
                eps_t = tcxo0 + 0.03e-6 * temp + tcxo_walk
                f_meas = (f_rx - f_lo * (1 + eps_t)) / (1 + mcu_err(t))
                if abs(f_meas - sig.baseband_hz(sig.F_RING_ALERT)) > DSP_BAND_HZ:
                    continue
                #link: 62 dB-Hz at zenith, spreading loss, a patch's roll-off
                cn0 = (62.0 - 20 * math.log10(rho / 780e3)
                       - 8.0 * (1 - math.sin(math.radians(el))) ** 2 + rng.gauss(0, 3.0))
                p_det, sigma = dsp_response(cn0)
                if rng.random() > p_det:
                    continue
                err = rng.gauss(0, sigma)
                outlier = rng.random() < outlier_frac
                if outlier:
                    err = rng.uniform(-300, 300)
                bursts.append((board(t) + rng.gauss(0, 20e-6), f_meas + err,
                               sigma * math.exp(rng.gauss(0, 0.25)), cn0))
                truth_bursts.append(dict(t=t, sat=num, ch=ch, false=False, outlier=outlier,
                                         df=f_rx - f_ch - f_lo * eps_t, el=el))
            dt_f = sig.FRAME_S
            temp += (1 - math.exp(-dt_f / 120.0)) * (temp_drive.step(dt_f) - temp)
            tcxo_walk += rng.gauss(0, 0.3 / f_lo * math.sqrt(dt_f))
            if rng.random() < false_rate * dt_f:
                t = t_frame + rng.uniform(0, sig.SIMPLEX_SLOT_S)
                cn0 = rng.uniform(46, 54)
                bursts.append((board(t), sig.baseband_hz(sig.F_RING_ALERT)
                               + rng.uniform(-DSP_BAND_HZ, DSP_BAND_HZ),
                               dsp_response(cn0)[1], cn0))
                truth_bursts.append(dict(t=t, sat=0, ch=-1, false=True, outlier=False,
                                         df=0.0, el=0.0))
        t_blk += 10.0

    #the aircraft's other sensors
    vel_err = [GaussMarkov(rng, vel_sigma, 300.0, 0.0), GaussMarkov(rng, vel_sigma, 300.0, 0.0),
               GaussMarkov(rng, 0.3, 60.0, 0.0)]
    baro_err = GaussMarkov(rng, 3.0, 600.0, 0.0)
    lines = [f"# soop_scenario obs: seed {seed}, {gps_min:g} min GPS then {denial_min:g} min "
             f"denied, {0 if static else speed:g} m/s, TLE age {tle_age_d:g} d",
             f"H {jd0:.1f} {fr0:.12f}"]
    for t, la, lo, hh, vn, ve, vd in traj[::1]:
        tb = board(t)
        denied = t >= gps_s
        ve_ = [vel_err[i].step(dt_tr) if denied else 0.02 * rng.gauss(0, 1) for i in range(3)]
        lines.append(f"E {tb:.6f} {vn + ve_[0]:.4f} {ve + ve_[1]:.4f} {vd + ve_[2]:.4f}")
        if round(t / dt_tr) % 2 == 0:
            b = baro_err.step(2 * dt_tr) if denied else 0.0
            lines.append(f"A {tb:.6f} {hh + b + rng.gauss(0, 0.3):.3f}")
        if not denied and round(t / dt_tr) % 2 == 0:
            r = sol.geodetic_to_ecef(la, lo, hh)
            lines.append(f"G {tb:.6f} {t + gps_lag + rng.gauss(0, 0.002):.6f} "
                         + " ".join(f"{r[k] + rng.gauss(0, 1.5):.3f}" for k in range(3)))
    order = sorted(range(len(bursts)), key=lambda i: bursts[i][0])
    for i in order:
        tb, f, s, c = bursts[i]
        lines.append(f"D {tb:.6f} {f:.3f} {s:.3f} {c:.2f}")
    #the log is time-ordered, as the board would write it
    body = sorted(lines[2:], key=lambda ln: float(ln.split()[1]))
    open(os.path.join(outdir, "obs.txt"), "w").write("\n".join(lines[:2] + body) + "\n")

    truth = dict(seed=seed, jd0=jd0 + fr0, t_utc0=t_utc0.isoformat(), gps_s=gps_s,
                 denial_s=denial_s, boot=boot, mcu0=mcu0, mcu_ramp=mcu_ramp, gps_lag=gps_lag,
                 tcxo0_hz=-f_lo * tcxo0, speed=0 if static else speed, tle_age_d=tle_age_d,
                 rate=rate, vel_sigma=vel_sigma,
                 sats={str(k): dict(name=v["name"].strip(), age_d=v["age_d"],
                                    along_m=v["along_m"], cross_m=v["cross_m"],
                                    radial_m=v["radial_m"], beta_hz=v["beta_hz"])
                       for k, v in sats.items()},
                 bursts=[truth_bursts[i] for i in order],
                 track=[dict(t=t, board=board(t), lat=la, lon=lo, h=hh, vn=vn, ve=ve, vd=vd)
                        for t, la, lo, hh, vn, ve, vd in traj[::10]])
    json.dump(truth, open(os.path.join(outdir, "truth.json"), "w"))
    return truth


#ECEF -> (lat deg, lon deg, h m), Bowring's closed form
def geodetic(r):
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    b = a * (1 - f)
    ep2 = (a * a - b * b) / (b * b)
    p = math.hypot(r[0], r[1])
    th = math.atan2(r[2] * a, p * b)
    lat = math.atan2(r[2] + ep2 * b * math.sin(th) ** 3, p - e2 * a * math.cos(th) ** 3)
    N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return math.degrees(lat), math.degrees(math.atan2(r[1], r[0])), p / math.cos(lat) - N


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("iq", help="simplex-slot I/Q recordings for the DSP")
    p.add_argument("outdir")
    p.add_argument("--slots", type=int, default=100)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cn0", type=float, nargs=2, default=(48.0, 70.0), metavar=("LO", "HI"))
    p.add_argument("--noise-counts", type=float, default=600.0)
    p = sub.add_parser("rtl", help="a bench-kit recording, rtl_sdr cu8 at 2 MSPS")
    p.add_argument("outdir")
    p.add_argument("--seconds", type=float, default=0.6)
    p.add_argument("--seed", type=int, default=5)
    p = sub.add_parser("obs", help="burst-level observations over a GNSS-denied flight")
    p.add_argument("outdir")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--gps-min", type=float, default=5.0)
    p.add_argument("--minutes", type=float, default=15.0, help="denial length")
    p.add_argument("--speed", type=float, default=15.0)
    p.add_argument("--static", action="store_true", help="stay on the pad (bench case)")
    p.add_argument("--tle-age", type=float, default=1.0, help="days, at take-off")
    p.add_argument("--rate", type=float, default=1.0, help="bursts/s per satellite")
    p.add_argument("--vel-sigma", type=float, default=1.0, help="EKF velocity error, m/s")
    a = ap.parse_args()
    if a.mode == "iq":
        t = make_iq(a.outdir, a.slots, a.seed, a.cn0[0], a.cn0[1], a.noise_counts)
        print(f"{a.slots} slots, {len(t['bursts'])} bursts, {t['clipped_samples']} clipped "
              f"samples -> {a.outdir}/iq.bin + truth.json")
    elif a.mode == "rtl":
        t = make_rtl(a.outdir, a.seconds, a.seed)
        print(f"{len(t['bursts'])} bursts in {a.seconds:g} s -> {a.outdir}/rec.cu8 + truth.json")
    else:
        t = make_obs(a.outdir, a.seed, a.gps_min, a.minutes, a.speed, a.tle_age,
                     rate=a.rate, vel_sigma=a.vel_sigma, static=a.static)
        n_false = sum(b["false"] for b in t["bursts"])
        print(f"{len(t['bursts'])} bursts ({n_false} false) from "
              f"{len({b['sat'] for b in t['bursts']} - {0})} satellites -> "
              f"{a.outdir}/obs.txt + truth.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
