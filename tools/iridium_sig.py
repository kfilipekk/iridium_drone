#iridium simplex-channel facts and this board's capture plan, in one place

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
UNIQUE_WORD_DL = "022220002002"   #downlink unique word, as DQPSK phase steps (x 90 deg)
MAX_BURST_S = SIMPLEX_SLOT_S      #a simplex burst never outlasts its slot

C_LIGHT = 299_792_458.0
MAX_DOPPLER_HZ = 41_000.0         #f * v / c at the worst-case LEO range rate, rounded up

#this board's capture
FS_CAPTURE = 500_000.0            #complex samples/s out of the ADC pair (after oversampling)
ADC_RAW_RATE = 2_000_000.0        #per ADC, before the x4 hardware oversampler
LO_OFFSET_HZ = 62_500.0           #LO above Ring Alert: RA lands at -62.5 kHz baseband
TCXO_PPM = 2.5                    #Y2, at the carrier: +-4 kHz
MCU_PPM = 20.0                    #Y1, the sample clock
DC_NOTCH_HZ = 400.0               #MAX2112 DC-offset loop corner with 47 nF (datasheet)
OPA_POLE_HZ = 1.0 / (2 * 3.141592653589793 * 10e3 * 100e-12)   #R50/C76, ~159 kHz
ADC_FULL_SCALE = 32767            #16-bit, centred


#where an RF frequency lands in the complex capture
def baseband_hz(rf_hz, lo_hz=F_RING_ALERT + LO_OFFSET_HZ):
    return rf_hz - lo_hz


#the Ring Alert band - Doppler plus the TCXO
def lo_plan_ok():
    ra = baseband_hz(F_RING_ALERT)
    worst = MAX_DOPPLER_HZ + TCXO_PPM * 1e-6 * F_RING_ALERT
    lo_edge, hi_edge = ra - worst, ra + worst
    return (hi_edge < -10 * DC_NOTCH_HZ and lo_edge > -FS_CAPTURE / 2,
            (lo_edge, hi_edge))
