//dsp_host.c - run soop_dsp over an I/Q file (interleaved int16) and print the bursts
#include "soop_dsp.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

//a predicted window: live for capture samples [a, b)
typedef struct { double a, b; float f, sd; } aid_t;

static void print(const soop_burst_t *out, size_t n)
{
    for (size_t i = 0; i < n; i++)
        printf("%" PRIu64 ",%" PRIu64 ",%.3f,%.3f,%.2f,%.5f,%u,%u,%u,%u,%u,%d,%d,%d\n", out[i].t_sample,
               out[i].t_start, out[i].f_hz, out[i].f_sigma_hz, out[i].cn0_dbhz, out[i].len_s,
               out[i].used_data, out[i].ira, out[i].ra_sv, out[i].ra_beam, out[i].ra_fixed,
               out[i].ra_pos[0], out[i].ra_pos[1], out[i].ra_pos[2]);
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s iq.bin [--lo HZ] [--aid FILE]\n"
                "FILE: 'start end f_hz sd_hz' per line, capture samples and Hz in the capture\n",
                argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 1; }
    static soop_dsp_t d;
    soop_dsp_init(&d);
    static aid_t aid[200000];
    int n_aid = 0;
    for (int k = 2; k + 1 < argc; k += 2) {
        if (!strcmp(argv[k], "--lo")) {
            soop_dsp_set_lo(&d, atof(argv[k + 1]));
        } else if (!strcmp(argv[k], "--aid")) {
            FILE *a = fopen(argv[k + 1], "r");
            if (!a) { perror(argv[k + 1]); return 1; }
            while (n_aid < 200000 && fscanf(a, "%lf %lf %f %f", &aid[n_aid].a, &aid[n_aid].b,
                                            &aid[n_aid].f, &aid[n_aid].sd) == 4)
                n_aid++;
            fclose(a);
        }
    }
    static int16_t buf[2 * 4096];
    soop_burst_t out[32];
    size_t got;
    uint64_t n0 = 0;
    printf("t_sample,t_start,f_hz,f_sigma_hz,cn0_dbhz,len_s,used_data,ira,ra_sv,ra_beam,ra_fixed,"
           "ra_x,ra_y,ra_z\n");
    while ((got = fread(buf, 4, 4096, f)) > 0) {
        if (n_aid) {                        //the windows live during this block, as the nav would hand them
            float fs[SOOP_DSP_MAX_AID], sd[SOOP_DSP_MAX_AID];
            int m = 0;
            for (int i = 0; i < n_aid && m < SOOP_DSP_MAX_AID; i++)
                if (aid[i].a < n0 + got && aid[i].b > n0) {
                    fs[m] = aid[i].f;
                    sd[m++] = aid[i].sd;
                }
            soop_dsp_aid(&d, fs, sd, m);
        }
        print(out, soop_dsp_push(&d, buf, got, out, 32));
        n0 += got;
    }
    //flush: feed silence long enough for the last slot to complete
    static int16_t zero[2 * 4096];
    for (int k = 0; k < 8; k++)
        print(out, soop_dsp_push(&d, zero, 4096, out, 32));
    fprintf(stderr, "frames %u, tones %u, bursts %u, noise %.1f\n", d.n_frames, d.n_tones,
            d.n_bursts, d.noise);
    fclose(f);
    return 0;
}
