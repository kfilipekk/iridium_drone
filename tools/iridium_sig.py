"""Iridium simplex-channel facts and this board's capture plan, in one place."""
import math

#the air interface
SYMBOL_RATE = 25_000.0            #symbols/s, all Iridium channels
RRC_ALPHA = 0.4                   #root-raised-cosine roll-off
CHANNEL_SPACING = 41_666.667      #Hz
F_RING_ALERT = 1_626_270_833.0    #Hz, the Ring Alert simplex channel (IRA)
#the four simplex messaging channels sit below it, one spacing apart
SIMPLEX_CHANNELS = tuple(F_RING_ALERT - k * CHANNEL_SPACING for k in range(4, -1, -1))
RING_ALERT_INDEX = 4              #SIMPLEX_CHANNELS[4] is the Ring Alert channel

FRAME_S = 0.090                   #TDMA frame
SIMPLEX_SLOT_S = 0.02032          #the simplex slot at the start of every frame
PREAMBLE_SYMBOLS = 64             #downlink: unmodulated carrier before the unique word
UNIQUE_WORD_DL = "022220002002"   #downlink unique word, absolute phases (x 90 deg) after the preamble
RA_BCH_POLY = 1207                #BCH(31,21) generator of the Ring Alert blocks (iridium-toolkit)
MAX_BURST_S = SIMPLEX_SLOT_S      #a simplex burst never outlasts its slot

C_LIGHT = 299_792_458.0
MAX_DOPPLER_HZ = 41_000.0         #f * v / c at the worst-case LEO range rate, rounded up

#this board's capture
FS_CAPTURE = 500_000.0            #complex samples/s out of the ADC pair (after oversampling)
ADC_RAW_RATE = 1_000_000.0        #per ADC: PA4 is a slow channel, 1 MSPS at most
ADC_OVS = 2                       #hardware oversampler: pairs averaged down to FS_CAPTURE
TUNER_LPF_HZ = 4_000_000.0        #MAX2112 baseband filter at its minimum
LO_OFFSET_HZ = 62_500.0           #LO above Ring Alert: RA lands at -62.5 kHz baseband
TCXO_PPM = 0.5                    #Y2, at the carrier: +-0.8 kHz
MCU_PPM = 20.0                    #Y1, the sample clock
DC_NOTCH_HZ = 400.0               #MAX2112 DC-offset loop corner with 47 nF (datasheet)
def _ohms(v):
    """'4k7' -> 4700, '220p' -> 2.2e-10."""
    mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "k": 1e3, "M": 1e6, "R": 1.0}
    for k, m in mult.items():
        if k in v:
            a, _, b = v.partition(k)
            return float((a or "0") + "." + (b or "0")) * m
    return float(v)


import design as _design
OPA_POLE_HZ = 1.0 / (2 * 3.141592653589793 * _ohms(_design.COMPONENTS["R50"][2])
                     * _ohms(_design.COMPONENTS["C76"][2]))   #R50/C76
ADC_FULL_SCALE = 32767            #16-bit, centred


#the duplex band below the simplex band, on the same 41.667 kHz grid
DUPLEX_CHANNELS = tuple(1_616_020_833.0 + k * CHANNEL_SPACING for k in range(240))
DUPLEX_PREAMBLE_SYMBOLS = 16


def amp_gain(f):
    """The difference amp's response re dc: Cf filters only the -IN leg, so it floors."""
    rin, rf = _ohms(_design.COMPONENTS["R36"][2]), _ohms(_design.COMPONENTS["R50"][2])
    w = 2j * math.pi * abs(f)
    zf = rf / (1 + w * rf * _ohms(_design.COMPONENTS["C76"][2]))
    h = 0.5 * rf / (rin + rf) * (1 + zf / rin) + 0.5 * zf / rin
    return abs(h) / (rf / rin)


def amp_args():
    """iq_import's board model of the same amp: its pole's time constant and its floor."""
    rin, rf = _ohms(_design.COMPONENTS["R36"][2]), _ohms(_design.COMPONENTS["R50"][2])
    k, a = rf / (rin + rf), rf / rin
    return ["--amp-tau", f"{rf * _ohms(_design.COMPONENTS['C76'][2]):.4g}",
            "--amp-floor", f"{k / (k + a * (k + 1)):.4f}"]


def fold(f_bb):
    """Where a baseband frequency lands after the ADC's raw sampling and the oversampler's."""
    def wrap(f, fs):
        return (f + fs / 2) % fs - fs / 2
    f_raw = wrap(f_bb, ADC_RAW_RATE)
    pole = amp_gain(f_bb)
    box = abs(math.cos(math.pi * f_raw / ADC_RAW_RATE)) if ADC_OVS == 2 else 1.0
    return wrap(f_raw, FS_CAPTURE), pole * box


def baseband_hz(rf_hz, lo_hz=F_RING_ALERT + LO_OFFSET_HZ):
    """Where an RF frequency lands in the complex capture."""
    return rf_hz - lo_hz


def lo_plan_ok():
    """The Ring Alert band - Doppler plus the TCXO."""
    ra = baseband_hz(F_RING_ALERT)
    worst = MAX_DOPPLER_HZ + TCXO_PPM * 1e-6 * F_RING_ALERT
    lo_edge, hi_edge = ra - worst, ra + worst
    return (hi_edge < -10 * DC_NOTCH_HZ and lo_edge > -FS_CAPTURE / 2,
            (lo_edge, hi_edge))


#Ring Alert frames, laid out as iridium-toolkit's bitsparser reads them
def bch_word(data21):
    """21 data bits -> the 32-bit block: data, 10 check bits, even parity."""
    r = int(data21, 2) << 10
    for b in range(30, 9, -1):
        if r >> b & 1:
            r ^= RA_BCH_POLY << (b - 10)
    w = data21 + format(r, "010b")
    return w + str(w.count("1") % 2)


def ra_header(sv, beam, xyz, interval=0, ts=0, eip=0, sb=0):
    """The 63-bit Ring Alert header: SV and beam, the position in 4 km units, the rest."""
    def s12(v):
        return ("1" if v < 0 else "0") + format(v + (1 << 11) if v < 0 else v, "011b")
    return (format(sv, "07b") + format(beam, "06b") + "".join(s12(v) for v in xyz)
            + format(interval, "07b") + str(ts) + str(eip) + format(sb, "05b"))


def ra_bits(header63):
    """The 96 bits after the unique word: three BCH blocks interleaved three ways."""
    blocks = [bch_word(header63[21 * i:21 * i + 21]) for i in range(3)]
    sym = [None] * 48
    for i in range(16):
        for b, blk in enumerate(blocks):
            sym[47 - b - 3 * i] = blk[2 * i:2 * i + 2]
    return "".join(x[1] + x[0] for x in sym)


#bit pair -> phase change in quarter turns (Gray), and back
DQPSK_STEP = {"00": 0, "01": 1, "11": 2, "10": 3}
