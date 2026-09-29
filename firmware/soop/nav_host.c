//nav_host.c - run the on-board navigation
#include "soop_guard.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SATS 128

static soop_sat_t cat[MAX_SATS];
static soop_guard_t guard;
static soop_nav_t *const nav_ = &guard.main;

static char *slurp(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc((size_t)n + 1);
    if (buf && fread(buf, 1, (size_t)n, f) != (size_t)n) {
        free(buf);
        buf = NULL;
    }
    if (buf)
        buf[n] = '\0';
    fclose(f);
    return buf;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s catalogue.tle obs.txt [--static] [--sats] [--vel-sigma M/S]\n", argv[0]);
        return 2;
    }
    char *tle = slurp(argv[1]);
    if (!tle) {
        perror(argv[1]);
        return 2;
    }
    const int n_cat = soop_ephem_parse(tle, cat, MAX_SATS);
    free(tle);
    if (!strcmp(argv[2], "--ephem")) {
        for (int k = 3; k < argc; k++)
            for (int i = 0; i < n_cat; i++) {
                double r[3], v[3];
                const double t = atof(argv[k]);
                if (soop_ephem_state(&cat[i], t, 0.0, r, v) == 0)
                    printf("S %u %.3f %.4f %.4f %.4f %.6f %.6f %.6f\n", (unsigned)cat[i].norad,
                           t, r[0], r[1], r[2], v[0], v[1], v[2]);
            }
        return 0;
    }
    if (!strcmp(argv[2], "--teme") && argc >= 10) {
        double rt[3], vt[3], r[3], v[3];
        for (int i = 0; i < 3; i++) {
            rt[i] = atof(argv[4 + i]);
            vt[i] = atof(argv[7 + i]);
        }
        soop_teme_to_ecef(rt, vt, soop_gmst(atof(argv[3])), r, v);
        printf("E %.4f %.4f %.4f %.6f %.6f %.6f\n", r[0], r[1], r[2], v[0], v[1], v[2]);
        return 0;
    }
    FILE *f = fopen(argv[2], "r");
    if (!f) {
        perror(argv[2]);
        return 2;
    }
    int sats = 0;
    soop_nav_cfg_t cfg;
    soop_nav_default_cfg(&cfg);
    for (int k = 3; k < argc; k++) {
        if (!strcmp(argv[k], "--static")) {
            cfg.vel_sigma = cfg.velz_sigma = 0.02;
        } else if (!strcmp(argv[k], "--sats")) {
            sats = 1;
        } else if (!strcmp(argv[k], "--vel-sigma") && k + 1 < argc) {
            cfg.vel_sigma = atof(argv[++k]);
        }
    }
    soop_guard_cfg_t gcfg;
    soop_guard_default_cfg(&gcfg);
    soop_guard_init(&guard, &cfg, &gcfg, cat, n_cat, 0.0);

    printf("kind,t,a,b,c,d,e,f,g,h,i,j,k\n");
    char line[256];
    double utc0 = 0.0, next_fix = -1.0;
    while (fgets(line, sizeof line, f)) {
        double t, a, b, c, d;
        if (line[0] == 'H') {
            if (sscanf(line + 1, "%lf %lf", &a, &b) == 2)
                utc0 = soop_jd_to_j2000(a, b);
            continue;
        }
        if (!strchr("EAGDPUR", line[0]) || sscanf(line + 1, "%lf", &t) != 1)
            continue;
        if (next_fix < 0.0)
            next_fix = t;
        while (t >= next_fix) {                  //fixes due before this record
            soop_fix_t fx;
            soop_guard_fix(&guard, next_fix, &fx);
            printf("F,%.3f,%.9f,%.9f,%.2f,%.3f,%.3f,%.3f,%.1f,%.1f,%.2f,%d,%d,%d,%.1f,%.1f\n",
                   fx.t, fx.lat_deg, fx.lon_deg, fx.h_m, fx.vn, fx.ve, fx.vd, fx.hacc_m,
                   fx.vacc_m, fx.nis, fx.n_track, fx.valid, guard.state, guard.dist_m,
                   guard.limit_m);
            if (sats && fmod(next_fix - 1.0, 10.0) < 1.0 - 1e-9)
                for (int k = 0; k < nav_->n_track; k++) {
                    const int o = SOOP_NAV_NBASE + SOOP_NAV_NS * k;
                    printf("T,%.3f,%u,%.2f,%.2f,%.5f,%.5f\n", fx.t,
                           (unsigned)cat[nav_->track[k]].norad, nav_->x[o], sqrt(nav_->P[o][o]),
                           nav_->x[o + 1], sqrt(nav_->P[o + 1][o + 1]));
                }
            next_fix += 1.0;
        }
        switch (line[0]) {
        case 'P': {
            double r[3];
            if (sscanf(line + 1, "%lf %lf %lf %lf %lf", &t, &r[0], &r[1], &r[2], &a) == 5)
                soop_guard_set_position(&guard, t, r, a);
            break;
        }
        case 'U':
            if (sscanf(line + 1, "%lf %lf", &t, &a) == 2)
                soop_guard_set_time(&guard, t, utc0 + a);
            break;
        case 'E':
            if (sscanf(line + 1, "%lf %lf %lf %lf", &t, &a, &b, &c) == 4)
                soop_guard_velocity(&guard, t, (float)a, (float)b, (float)c);
            break;
        case 'A':
            if (sscanf(line + 1, "%lf %lf", &t, &a) == 2)
                soop_guard_baro(&guard, t, a);
            break;
        case 'G': {
            double r[3];
            if (sscanf(line + 1, "%lf %lf %lf %lf %lf", &t, &a, &r[0], &r[1], &r[2]) == 5)
                soop_guard_gps(&guard, t, utc0 + a, r);
            break;
        }
        case 'R':
            soop_guard_arm(&guard, t);
            break;
        case 'D':
            if (sscanf(line + 1, "%lf %lf %lf %lf", &t, &a, &b, &d) == 4) {
                const int res = soop_guard_burst(&guard, t, a, b);
                printf("B,%.6f,%d,%d,%d,%.2f,%.2f\n", t, res,
                       res == SOOP_B_FUSED ? nav_->last_sat : 0,
                       res == SOOP_B_FUSED ? nav_->last_ch : -1,
                       res == SOOP_B_FUSED ? nav_->last_y : 0.0,
                       res == SOOP_B_FUSED ? nav_->last_sd : 0.0);
            }
            break;
        }
    }
    fclose(f);
    fprintf(stderr, "catalogue %d; bursts fused %u ambiguous %u unmatched %u pending %u "
            "acquiring %u no-time %u; resets %u; clock tries %u; gps jumps %u; guard %d "
            "at %.1f\n", n_cat,
            nav_->count[SOOP_B_FUSED], nav_->count[SOOP_B_AMBIGUOUS], nav_->count[SOOP_B_UNMATCHED],
            nav_->count[SOOP_B_PENDING], nav_->count[SOOP_B_ACQUIRING], nav_->count[SOOP_B_NO_TIME],
            nav_->n_resets, nav_->n_acq_tries, guard.n_jumps, guard.state, guard.t_spoofed);
    return 0;
}
