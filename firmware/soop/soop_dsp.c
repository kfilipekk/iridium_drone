//soop_dsp.c - Iridium simplex burst detection and carrier measurement
#include "soop_dsp.h"
#include "soop_signal.h"

#include <math.h>
#include <string.h>

#define N      SOOP_DSP_NFFT
#define RMASK  (SOOP_DSP_RING - 1)
#define FSD    ((float)(SOOP_FS / SOOP_DSP_DEC))      //125 kHz
#define PI_F   3.14159265358979f

//a tone must stand 12 dB over the noise across its three Hann bins, 10 dB over the largest bin
#define TONE_SNR_MIN   15.85f
#define TONE_NARROW    10.0f
#define MIN_FRAMES     4
#define PRE_COH_MIN    0.15f           //coherent share of the preamble window's energy
#define BAND_HZ        52000.0f        //Ring Alert band after the mix
#define SETTLE_FRAMES  64              //filters and noise estimate settling at start

static float bessel_i0(float x)
{
    float s = 1.0f, t = 1.0f;
    for (int k = 1; k < 30; k++) {
        t *= (x / (2.0f * k)) * (x / (2.0f * k));
        s += t;
        if (t < 1e-9f * s)
            break;
    }
    return s;
}

//second half-band: Kaiser-windowed sinc at fs/4, beta 6
static void design_halfband(float *h2)
{
    const int n = SOOP_DSP_H2TAPS, c = (n - 1) / 2;
    const float beta = 6.0f;
    float full[SOOP_DSP_H2TAPS], sum = 0.0f;
    for (int i = 0; i < n; i++) {
        int x = i - c;
        float s = (x == 0) ? 0.5f : sinf(PI_F * x / 2.0f) / (PI_F * x);
        float r = 2.0f * x / (n - 1);
        full[i] = s * bessel_i0(beta * sqrtf(fmaxf(0.0f, 1.0f - r * r))) / bessel_i0(beta);
        sum += full[i];
    }
    for (int k = 0; k < c / 2 + 1; k++)
        h2[k] = full[c + 2 * k + 1] / sum;
    h2[(n + 1) / 2 - 1] = full[c] / sum;
}

void soop_dsp_init(soop_dsp_t *d)
{
    memset(d, 0, sizeof(*d));
    design_halfband(d->h2);
    for (int n = 0; n < N; n++)
        d->win[n] = 0.5f - 0.5f * cosf(2.0f * PI_F * n / N);
    for (int k = 0; k < N / 2; k++) {
        d->cosw[k] = cosf(2.0f * PI_F * k / N);
        d->sinw[k] = sinf(2.0f * PI_F * k / N);
    }
    d->m_next_frame = N;
}

static void fft(float *re, float *im, const float *cw, const float *sw)
{
    for (int i = 1, j = 0; i < N; i++) {
        int bit = N >> 1;
        for (; j & bit; bit >>= 1)
            j ^= bit;
        j ^= bit;
        if (i < j) {
            float t = re[i]; re[i] = re[j]; re[j] = t;
            t = im[i]; im[i] = im[j]; im[j] = t;
        }
    }
    for (int len = 2; len <= N; len <<= 1) {
        int step = N / len;
        for (int i = 0; i < N; i += len) {
            for (int k = 0; k < len / 2; k++) {
                float wr = cw[k * step], wi = -sw[k * step];
                int a = i + k, b = a + len / 2;
                float xr = re[b] * wr - im[b] * wi;
                float xi = re[b] * wi + im[b] * wr;
                re[b] = re[a] - xr; im[b] = im[a] - xi;
                re[a] += xr;        im[a] += xi;
            }
        }
    }
}

//k-th smallest of n values (a is scrambled)
static float select_k(float *a, int n, int k)
{
    int lo = 0, hi = n - 1;
    while (lo < hi) {
        float pv = a[(lo + hi) / 2];
        int i = lo, j = hi;
        while (i <= j) {
            while (a[i] < pv) i++;
            while (a[j] > pv) j--;
            if (i <= j) { float t = a[i]; a[i] = a[j]; a[j] = t; i++; j--; }
        }
        if (k <= j) hi = j;
        else if (k >= i) lo = i;
        else break;
    }
    return a[k];
}

//|sum z[n] exp(-j 2 pi f n / FSD)|^2, n over
static float dft_power(const float *zi, const float *zq, int len, float f)
{
    float w = -2.0f * PI_F * f / FSD, sr = 0.0f, si = 0.0f;
    float cs = cosf(w), sn = sinf(w), er = 1.0f, ei = 0.0f;
    for (int n = 0; n < len; n++) {
        sr += zi[n] * er - zq[n] * ei;
        si += zi[n] * ei + zq[n] * er;
        float t = er * cs - ei * sn;
        ei = er * sn + ei * cs;
        er = t;
        if ((n & 63) == 63) {                       //keep the rotator on the unit circle
            float r = 1.0f / sqrtf(er * er + ei * ei);
            er *= r; ei *= r;
        }
    }
    return sr * sr + si * si;
}

//golden-section maximum of dft_power over [a, b]
static float peak_freq(const float *zi, const float *zq, int len, float a, float b, float *pmax)
{
    const float g = 0.618034f;
    float c = b - g * (b - a), e = a + g * (b - a);
    float fc = dft_power(zi, zq, len, c), fe = dft_power(zi, zq, len, e);
    for (int it = 0; it < 48 && (b - a) > 0.01f; it++) {
        if (fc > fe) { b = e; e = c; fe = fc; c = b - g * (b - a); fc = dft_power(zi, zq, len, c); }
        else         { a = c; c = e; fc = fe; e = a + g * (b - a); fe = dft_power(zi, zq, len, e); }
    }
    float f = 0.5f * (a + b);
    if (pmax)
        *pmax = dft_power(zi, zq, len, f);
    return f;
}

//copy ring samples
static void grab(const soop_dsp_t *d, uint64_t m0, int len, float f, float *zi, float *zq)
{
    float w = -2.0f * PI_F * f / FSD, cs = cosf(w), sn = sinf(w), er = 1.0f, ei = 0.0f;
    for (int n = 0; n < len; n++) {
        uint32_t k = (uint32_t)((m0 + n) & RMASK);
        float xi = d->ring_i[k], xq = d->ring_q[k];
        zi[n] = xi * er - xq * ei;
        zq[n] = xi * ei + xq * er;
        float t = er * cs - ei * sn;
        ei = er * sn + ei * cs;
        er = t;
        if ((n & 63) == 63) {
            float r = 1.0f / sqrtf(er * er + ei * ei);
            er *= r; ei *= r;
        }
    }
}

#define MAX_SEG 2600    //the slot at 125 kSPS, rounded up

static int estimate(soop_dsp_t *d, const soop_pending_t *p, soop_burst_t *o)
{
    static float zi[MAX_SEG], zq[MAX_SEG];
    const float sumw2 = 0.375f * N;                 //Hann: sum of w^2
    const float sigma2 = d->noise / sumw2;          //complex noise power per sample
    const float bin = FSD / N;

    //1. the preamble
    grab(d, p->pre_m, N, p->f_coarse, zi, zq);
    float pk;
    float f_pre = p->f_coarse + peak_freq(zi, zq, N, -0.6f * bin, 0.6f * bin, &pk);
    const int pre_len = (int)(SOOP_PREAMBLE_SYMS * FSD / SOOP_SYMBOL_RATE);      //320
    uint64_t best_m0 = p->pre_m;
    int best_len = N;
    float best_metric = -1.0f;
    for (int off = -128; off <= 128; off += 16) {
        if ((int64_t)p->pre_m + off < 0)
            continue;
        uint64_t m0 = p->pre_m + off;
        for (int L = N; L <= pre_len; L += pre_len - N) {
            grab(d, m0, L, f_pre, zi, zq);
            float metric = dft_power(zi, zq, L, 0.0f) / L;
            if (metric > best_metric) { best_metric = metric; best_m0 = m0; best_len = L; }
        }
    }
    grab(d, best_m0, best_len, f_pre, zi, zq);
    float lb = FSD / best_len;
    f_pre += peak_freq(zi, zq, best_len, -0.6f * lb, 0.6f * lb, &pk);
    float tot = 0;
    for (int n = 0; n < best_len; n++)
        tot += zi[n] * zi[n] + zq[n] * zq[n];
    float coh_pre = pk / ((float)best_len * tot);
    if (!(coh_pre > PRE_COH_MIN))
        return 0;                                   //not a carrier: burst data, or noise
    float amp2 = pk / ((float)best_len * best_len);
    //noise as this burst sees it
    float resid = (tot - pk / best_len) / (best_len - 1);
    float rho = amp2 / fmaxf(sigma2, resid);
    if (!(rho > 0.0f))
        return 0;
    float s_pre = FSD * sqrtf(6.0f / (rho * (float)best_len * best_len * best_len)) / (2.0f * PI_F);
    float e_pre = (float)best_m0 + best_len / 2.0f;
    float cn0 = 10.0f * log10f(amp2 / sigma2 * FSD);

    //2. the burst after the preamble: follow its energy in 64-sample blocks
    uint64_t d0 = best_m0 + best_len;
    int maxlen = (int)(SOOP_MAX_BURST_S * FSD);
    if (maxlen > MAX_SEG) maxlen = MAX_SEG;
    grab(d, d0, maxlen, f_pre, zi, zq);
    //one-symbol boxcar (5 samples): close to the matched filter
    float ai = 0, aq = 0, hi5[5] = {0}, hq5[5] = {0};
    for (int n = 0; n < maxlen; n++) {
        ai += zi[n] - hi5[n % 5];
        aq += zq[n] - hq5[n % 5];
        hi5[n % 5] = zi[n];
        hq5[n % 5] = zq[n];
        zi[n] = ai * 0.2f;
        zq[n] = aq * 0.2f;
    }
    int len = 0;
    const float floor_b = sigma2 * 64.0f / 5.0f;
    for (int b = 0; b + 64 <= maxlen; b += 64) {
        float e = 0;
        for (int n = b; n < b + 64; n++)
            e += zi[n] * zi[n] + zq[n] * zq[n];
        if (e < floor_b + 0.25f * amp2 * 64.0f)
            break;
        len = b + 64;
    }

    //3. the data: 4th power strips DQPSK/BPSK to a tone at 4x the residual offset
    float f = f_pre, s_f = s_pre, epoch = e_pre;
    o->used_data = 0;
    if (len >= 256) {
        float tot = 0;
        for (int n = 0; n < len; n++) {
            float a = zi[n], b = zq[n];
            float r2 = a * a - b * b, i2 = 2 * a * b;
            float r4 = r2 * r2 - i2 * i2, i4 = 2 * r2 * i2;
            zi[n] = r4; zq[n] = i4;
            tot += r4 * r4 + i4 * i4;
        }
        float w = fmaxf(5.0f * s_pre, 60.0f) * 4.0f;
        float p4;
        float f4 = peak_freq(zi, zq, len, -w, w, &p4);
        float coh = p4 / ((float)len * tot);
        if (coh > 0.02f && coh < 0.999f) {
            float rho4 = coh / (1.0f - coh);
            float s4 = FSD * sqrtf(6.0f / (rho4 * (float)len * len * len)) / (2.0f * PI_F) / 4.0f;
            float f_d = f_pre + f4 / 4.0f;
            float e_d = (float)d0 + len / 2.0f;
            if (fabsf(f_d - f_pre) < fmaxf(4.0f * sqrtf(s_pre * s_pre + s4 * s4), 20.0f)) {
                float wp = 1.0f / (s_pre * s_pre), wd = 1.0f / (s4 * s4);
                f = (f_pre * wp + f_d * wd) / (wp + wd);
                epoch = (e_pre * wp + e_d * wd) / (wp + wd);
                s_f = 1.0f / sqrtf(wp + wd);
                o->used_data = 1;
            }
        }
    }

    //4. back to the capture: undo the mix, and the decimator's group delay
    float t_in = epoch * SOOP_DSP_DEC - SOOP_DSP_DELAY;
    o->t_sample = (uint64_t)(t_in > 0 ? t_in + 0.5f : 0);
    float t_st = (float)best_m0 * SOOP_DSP_DEC - SOOP_DSP_DELAY;
    o->t_start = (uint64_t)(t_st > 0 ? t_st + 0.5f : 0);
    o->f_hz = f - (float)SOOP_LO_OFFSET_HZ;
    o->f_sigma_hz = s_f;
    o->cn0_dbhz = cn0;
    o->len_s = (best_len + len) / FSD;
    return 1;
}

static void frame(soop_dsp_t *d, uint64_t m0)
{
    float re[N], im[N], p[N], tmp[N];
    for (int n = 0; n < N; n++) {
        uint32_t k = (uint32_t)((m0 + n) & RMASK);
        re[n] = d->ring_i[k] * d->win[n];
        im[n] = d->ring_q[k] * d->win[n];
    }
    fft(re, im, d->cosw, d->sinw);
    for (int k = 0; k < N; k++) {
        p[k] = re[k] * re[k] + im[k] * im[k];
        tmp[k] = p[k];
    }
    //noise: 30th percentile of an exponential is 0.357 x its mean
    float q = select_k(tmp, N, (int)(0.3f * N)) / 0.3567f;
    if (!d->noise_init) { d->noise = q; d->noise_init = 1; }
    else if (q < 4.0f * d->noise) d->noise += 0.02f * (q - d->noise);
    d->n_frames++;

    int seen[SOOP_DSP_MAX_TONES] = {0};
    if (d->n_frames > SETTLE_FRAMES) {
        const int kmax = (int)(BAND_HZ / (FSD / N));
        for (int kk = -kmax; kk <= kmax; kk++) {
            int k = (kk + N) % N, kl = (kk - 1 + N) % N, kr = (kk + 1 + N) % N;
            if (!(p[k] >= p[kl] && p[k] > p[kr]))
                continue;
            float pk = p[kl] + p[k] + p[kr];
            if (pk < TONE_SNR_MIN * 3.0f * d->noise)
                continue;
            float sh = 0;
            for (int s = 3; s <= 8; s++) {
                sh = fmaxf(sh, p[(kk + s + N) % N]);
                sh = fmaxf(sh, p[(kk - s + N) % N]);
            }
            if (p[k] < TONE_NARROW * fmaxf(sh, d->noise))
                continue;
            float den = p[kl] - 2 * p[k] + p[kr];
            float kf = kk + ((den != 0.0f) ? 0.5f * (p[kl] - p[kr]) / den : 0.0f);
            //join a live tone within 2.5 bins, or start one
            int slot = -1;
            for (int t = 0; t < SOOP_DSP_MAX_TONES; t++)
                if (d->tones[t].live && fabsf(d->tones[t].best_bin_f - kf) <= 2.5f) { slot = t; break; }
            if (slot < 0) {
                for (int t = 0; t < SOOP_DSP_MAX_TONES; t++)
                    if (!d->tones[t].live) { slot = t; break; }
                if (slot < 0)
                    continue;
                memset(&d->tones[slot], 0, sizeof(d->tones[slot]));
                d->tones[slot].live = 1;
                d->tones[slot].first_m = m0;
                d->tones[slot].best_bin_f = kf;
                d->n_tones++;
            }
            soop_tone_t *t = &d->tones[slot];
            t->last_m = m0;
            t->frames++;
            t->missed = 0;
            if (pk > t->best_p) { t->best_p = pk; t->best_m = m0; t->best_bin_f = kf; }
            seen[slot] = 1;
        }
    }
    for (int s = 0; s < SOOP_DSP_MAX_TONES; s++) {
        soop_tone_t *t = &d->tones[s];
        if (!t->live || seen[s])
            continue;
        if (++t->missed < 2)
            continue;
        t->live = 0;
        if (t->frames < MIN_FRAMES)
            continue;
        for (int j = 0; j < SOOP_DSP_MAX_PEND; j++) {
            if (d->pend[j].live)
                continue;
            d->pend[j].live = 1;
            d->pend[j].pre_m = t->best_m;
            d->pend[j].f_coarse = t->best_bin_f * FSD / N;
            d->pend[j].tone_snr = t->best_p / (3.0f * d->noise);
            d->pend[j].ready_m = t->best_m + N + (uint64_t)(SOOP_MAX_BURST_S * FSD) + 8;
            break;
        }
    }
}

//one decimated (125 kSPS) sample into the ring
static size_t emit(soop_dsp_t *d, float yi, float yq, soop_burst_t *out, size_t max_out)
{
    size_t n_out = 0;
    uint32_t r = (uint32_t)(d->m & RMASK);
    d->ring_i[r] = yi;
    d->ring_q[r] = yq;
    d->m++;
    if (d->m >= d->m_next_frame) {
        frame(d, d->m - N);
        d->m_next_frame += SOOP_DSP_HOP;
    }
    for (int j = 0; j < SOOP_DSP_MAX_PEND; j++) {
        soop_pending_t *p = &d->pend[j];
        if (!p->live || d->m < p->ready_m)
            continue;
        p->live = 0;
        if (n_out < max_out && estimate(d, p, &out[n_out])) {
            n_out++;
            d->n_bursts++;
        }
    }
    return n_out;
}

size_t soop_dsp_push(soop_dsp_t *d, const int16_t *iq, size_t n, soop_burst_t *out, size_t max_out)
{
    static const float mix_c[8] = {1, 0.70710678f, 0, -0.70710678f, -1, -0.70710678f, 0, 0.70710678f};
    static const float mix_s[8] = {0, 0.70710678f, 1, 0.70710678f, 0, -0.70710678f, -1, -0.70710678f};
    const int n2 = SOOP_DSP_H2TAPS, c2 = (SOOP_DSP_H2TAPS - 1) / 2;
    size_t n_out = 0;
    for (size_t s = 0; s < n; s++) {
        float i = iq[2 * s], q = iq[2 * s + 1];
        int ph = (int)(d->n_in & 7);
        d->n_in++;
        //mix +FS/8: Ring Alert to 0 Hz
        float mi = i * mix_c[ph] - q * mix_s[ph];
        float mq = i * mix_s[ph] + q * mix_c[ph];
        d->h1i[d->p1] = d->h1i[d->p1 + 7] = mi;
        d->h1q[d->p1] = d->h1q[d->p1 + 7] = mq;
        d->p1 = (d->p1 + 1) % 7;
        if (d->n_in & 1)
            continue;
        //stage 1, [-1 0 9 16 9 0 -1]/32 over the last 7 inputs (oldest first)
        const float *xi = &d->h1i[d->p1], *xq = &d->h1q[d->p1];
        float ai = (16.0f * xi[3] + 9.0f * (xi[2] + xi[4]) - (xi[0] + xi[6])) * (1.0f / 32.0f);
        float aq = (16.0f * xq[3] + 9.0f * (xq[2] + xq[4]) - (xq[0] + xq[6])) * (1.0f / 32.0f);
        d->h2i[d->p2] = d->h2i[d->p2 + n2] = ai;
        d->h2q[d->p2] = d->h2q[d->p2 + n2] = aq;
        d->p2 = (d->p2 + 1) % n2;
        d->n1++;
        if (d->n1 & 1)
            continue;
        //stage 2: symmetric pairs at odd offsets, plus the centre
        const float *wi = &d->h2i[d->p2], *wq = &d->h2q[d->p2];
        float yi = d->h2[(n2 + 1) / 2 - 1] * wi[c2], yq = d->h2[(n2 + 1) / 2 - 1] * wq[c2];
        for (int k = 0; 2 * k + 1 <= c2; k++) {
            yi += d->h2[k] * (wi[c2 - 2 * k - 1] + wi[c2 + 2 * k + 1]);
            yq += d->h2[k] * (wq[c2 - 2 * k - 1] + wq[c2 + 2 * k + 1]);
        }
        size_t room = max_out - n_out;
        n_out += emit(d, yi, yq, out + n_out, room);
    }
    return n_out;
}
