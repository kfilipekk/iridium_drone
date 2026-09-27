//soop_dsp.h - find Iridium simplex bursts in the I/Q stream and measure their carriers
#ifndef SOOP_DSP_H
#define SOOP_DSP_H

#include <stdint.h>
#include <stddef.h>

#define SOOP_DSP_DEC        4
#define SOOP_DSP_H2TAPS     47            //second half-band
#define SOOP_DSP_DELAY      46            //capture samples: decimated m is capture 4m - 46
#define SOOP_DSP_NFFT       256
#define SOOP_DSP_HOP        64
#define SOOP_DSP_RING       4096          //decimated samples: 32.8 ms of history
#define SOOP_DSP_MAX_TONES  12
#define SOOP_DSP_MAX_PEND   12

typedef struct {
    uint64_t t_sample;     //capture sample index of the measurement epoch
    uint64_t t_start;      //capture sample index where the preamble window starts
    float    f_hz;         //carrier in the capture, Hz (Ring Alert sits at -LO offset)
    float    f_sigma_hz;   //estimated 1-sigma of f_hz
    float    cn0_dbhz;     //estimated C/N0 from the preamble tone
    float    len_s;        //burst length found after the preamble
    uint8_t  used_data;    //1 if the 4th-power data fit contributed
} soop_burst_t;

typedef struct {
    int      bin;           //last FFT bin
    uint64_t first_m, last_m, best_m;   //decimated indices of frame starts
    float    best_p;        //strongest tone power seen
    float    best_bin_f;    //interpolated bin of the strongest frame
    int      frames, missed;
    int      live;
} soop_tone_t;

typedef struct {
    uint64_t ready_m;       //process once the stream reaches this decimated index
    uint64_t pre_m;         //start of the best preamble window
    float    f_coarse;      //Hz, decimated frame
    float    tone_snr;      //bin power over noise
    int      live;
} soop_pending_t;

typedef struct {
    //decimators; histories are doubled so every window is contiguous
    uint64_t n_in;                   //capture samples consumed
    float    h1i[14], h1q[14];       //stage 1: 7 taps
    int      p1;
    float    h2[(SOOP_DSP_H2TAPS + 1) / 2];   //stage 2: taps at odd offsets, centre last
    float    h2i[2 * SOOP_DSP_H2TAPS], h2q[2 * SOOP_DSP_H2TAPS];
    int      p2;
    uint64_t n1;                     //stage-1 outputs produced
    //decimated ring
    float    ring_i[SOOP_DSP_RING], ring_q[SOOP_DSP_RING];
    uint64_t m;                      //decimated samples produced
    uint64_t m_next_frame;
    //STFT
    float    win[SOOP_DSP_NFFT];
    float    cosw[SOOP_DSP_NFFT / 2], sinw[SOOP_DSP_NFFT / 2];
    float    noise;                  //long-term noise power per bin
    int      noise_init;
    soop_tone_t    tones[SOOP_DSP_MAX_TONES];
    soop_pending_t pend[SOOP_DSP_MAX_PEND];
    //statistics
    uint32_t n_frames, n_tones, n_bursts;
} soop_dsp_t;

void   soop_dsp_init(soop_dsp_t *d);

//push n interleaved I,Q pairs
size_t soop_dsp_push(soop_dsp_t *d, const int16_t *iq, size_t n,
                     soop_burst_t *out, size_t max_out);

#endif //SOOP_DSP_H
