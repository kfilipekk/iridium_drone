//iq_import.c - turn a bench recording into what the board's ADC pair would have captured
#include "soop_signal.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PI    3.14159265358979323846
#define NTAPS_PER 24                     //FIR taps per unit of decimation
#define MAXDEC 12

int main(int argc, char **argv)
{
    const char *fmt = "cu8";
    double fs = 0.0, fc = 0.0, gain = 1.0;
    if (argc < 3) {
        fprintf(stderr, "usage: %s in out --format cu8|cs16|cf32 --fs HZ --fc HZ [--gain G]\n",
                argv[0]);
        return 2;
    }
    for (int i = 3; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--format")) fmt = argv[i + 1];
        else if (!strcmp(argv[i], "--fs")) fs = atof(argv[i + 1]);
        else if (!strcmp(argv[i], "--fc")) fc = atof(argv[i + 1]);
        else if (!strcmp(argv[i], "--gain")) gain = atof(argv[i + 1]);
        else { fprintf(stderr, "unknown option %s\n", argv[i]); return 2; }
    }
    const int dec = (int)lround(fs / SOOP_FS);
    if (dec < 1 || dec > MAXDEC || fabs(dec * SOOP_FS - fs) > 1.0) {
        fprintf(stderr, "fs %.0f is not a whole multiple of %.0f (record at 2000000)\n", fs, SOOP_FS);
        return 2;
    }
    int bps;                             //bytes per complex sample
    double scale;                        //to the board's int16 counts, before gain
    if (!strcmp(fmt, "cu8")) { bps = 2; scale = 256.0; }
    else if (!strcmp(fmt, "cs16")) { bps = 4; scale = 1.0; }
    else if (!strcmp(fmt, "cf32")) { bps = 8; scale = 32767.0; }
    else { fprintf(stderr, "unknown format %s\n", fmt); return 2; }
    scale *= gain;

    //windowed-sinc low-pass, cut at 220 kHz
    const int nt = dec == 1 ? 1 : NTAPS_PER * dec + 1;
    double h[NTAPS_PER * MAXDEC + 1];
    double hs = 0.0;
    for (int k = 0; k < nt; k++) {
        const double m = k - (nt - 1) / 2.0, fcut = 220e3 / fs;
        const double sinc = m == 0.0 ? 2.0 * fcut : sin(2.0 * PI * fcut * m) / (PI * m);
        const double w = 0.42 - 0.5 * cos(2.0 * PI * k / (nt - 1 > 0 ? nt - 1 : 1))
                         + 0.08 * cos(4.0 * PI * k / (nt - 1 > 0 ? nt - 1 : 1));
        h[k] = nt == 1 ? 1.0 : sinc * w;
        hs += h[k];
    }
    for (int k = 0; k < nt; k++)
        h[k] /= hs;

    FILE *in = fopen(argv[1], "rb"), *out = fopen(argv[2], "wb");
    if (!in || !out) {
        perror(!in ? argv[1] : argv[2]);
        return 2;
    }
    //RF f sits at f - fc in the recording and must land at f - LO
    const double w = 2.0 * PI * (fc - (SOOP_F_RING_ALERT + SOOP_LO_OFFSET_HZ)) / fs;
    double pr = 1.0, pi_ = 0.0;
    const double cr = cos(w), ci = sin(w);
    double *bi = calloc((size_t)nt, sizeof *bi), *bq = calloc((size_t)nt, sizeof *bq);
    unsigned char raw[8 * 4096];
    long long n_in = 0, n_out = 0, clipped = 0;
    int pos = 0;
    size_t got;
    while ((got = fread(raw, (size_t)bps, sizeof raw / (size_t)bps, in)) > 0) {
        for (size_t s = 0; s < got; s++) {
            double i, q;
            const unsigned char *p = raw + s * (size_t)bps;
            if (bps == 2) {
                i = p[0] - 127.5;
                q = p[1] - 127.5;
            } else if (bps == 4) {
                i = (int16_t)(p[0] | p[1] << 8);
                q = (int16_t)(p[2] | p[3] << 8);
            } else {
                float fi, fq;
                memcpy(&fi, p, 4);
                memcpy(&fq, p + 4, 4);
                i = fi;
                q = fq;
            }
            const double yr = i * pr - q * pi_, yq = i * pi_ + q * pr;
            const double npr = pr * cr - pi_ * ci, npi = pr * ci + pi_ * cr;
            pr = npr;
            pi_ = npi;
            if ((++n_in & 0xFFFF) == 0) {
                const double m = sqrt(pr * pr + pi_ * pi_);
                pr /= m;
                pi_ /= m;
            }
            bi[pos] = yr;
            bq[pos] = yq;
            pos = (pos + 1) % nt;
            if (n_in % dec)
                continue;
            double oi = 0.0, oq = 0.0;
            for (int k = 0; k < nt; k++) {
                const int j = (pos + k) % nt;
                oi += h[k] * bi[j];
                oq += h[k] * bq[j];
            }
            long ri = lround(oi * scale), rq = lround(oq * scale);
            if (labs(ri) > 32767 || labs(rq) > 32767)
                clipped++;
            ri = ri > 32767 ? 32767 : ri < -32767 ? -32767 : ri;
            rq = rq > 32767 ? 32767 : rq < -32767 ? -32767 : rq;
            const int16_t o[2] = { (int16_t)ri, (int16_t)rq };
            fwrite(o, sizeof o, 1, out);
            n_out++;
        }
    }
    fclose(in);
    fclose(out);
    free(bi);
    free(bq);
    fprintf(stderr, "%lld samples at %.0f -> %lld at %.0f, %lld clipped; the filter delays "
            "by %d output samples\n", n_in, fs, n_out, SOOP_FS, clipped, (nt - 1) / 2 / dec);
    return 0;
}
