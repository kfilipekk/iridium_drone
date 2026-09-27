//dsp_host.c - run soop_dsp over an I/Q file (interleaved int16) and print the bursts
#include "soop_dsp.h"
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s iq.bin\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 1; }
    static soop_dsp_t d;
    soop_dsp_init(&d);
    static int16_t buf[2 * 4096];
    soop_burst_t out[32];
    size_t got;
    printf("t_sample,t_start,f_hz,f_sigma_hz,cn0_dbhz,len_s,used_data\n");
    while ((got = fread(buf, 4, 4096, f)) > 0) {
        size_t n = soop_dsp_push(&d, buf, got, out, 32);
        for (size_t i = 0; i < n; i++)
            printf("%" PRIu64 ",%" PRIu64 ",%.3f,%.3f,%.2f,%.5f,%u\n", out[i].t_sample, out[i].t_start, out[i].f_hz,
                   out[i].f_sigma_hz, out[i].cn0_dbhz, out[i].len_s, out[i].used_data);
    }
    //flush: feed silence long enough for the last slot to complete
    static int16_t zero[2 * 4096];
    for (int k = 0; k < 8; k++) {
        size_t n = soop_dsp_push(&d, zero, 4096, out, 32);
        for (size_t i = 0; i < n; i++)
            printf("%" PRIu64 ",%" PRIu64 ",%.3f,%.3f,%.2f,%.5f,%u\n", out[i].t_sample, out[i].t_start, out[i].f_hz,
                   out[i].f_sigma_hz, out[i].cn0_dbhz, out[i].len_s, out[i].used_data);
    }
    fprintf(stderr, "frames %u, tones %u, bursts %u, noise %.1f\n", d.n_frames, d.n_tones,
            d.n_bursts, d.noise);
    fclose(f);
    return 0;
}
