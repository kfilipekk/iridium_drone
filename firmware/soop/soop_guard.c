//soop_guard.c - see soop_guard.h
//ArduPilot compiles every source with -fsingle-precision-constant
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize ("no-single-precision-constant")
#endif
typedef char soop_needs_double_constants[((long)299792458.0 == 299792458L) ? 1 : -1];

#include "soop_guard.h"

#include <math.h>
#include <string.h>

void soop_guard_default_cfg(soop_guard_cfg_t *c)
{
    c->jump_sigma = 6.0;  c->jump_m = 50.0;  c->jump_n = 5;
    c->k = 3.0;           c->floor_m = 150.0;    //clean flights reach ~2x: see the gate
    c->hold_s = 5.0;
    //tighter than main's 1.5: free then follows a dragged velocity less
    c->free_vel_sigma = 1.0;
}

void soop_guard_init(soop_guard_t *g, const soop_nav_cfg_t *nav_cfg,
                     const soop_guard_cfg_t *cfg, const soop_sat_t *cat, int n_cat,
                     double t_now_utc)
{
    memset(g, 0, sizeof *g);
    g->cfg = *cfg;
    soop_nav_init(&g->main, nav_cfg, cat, n_cat, t_now_utc);
    soop_nav_init(&g->free, nav_cfg, cat, n_cat, t_now_utc);
    g->state = SOOP_G_UNARMED;
}

void soop_guard_arm(soop_guard_t *g, double t_board)
{
    (void)t_board;
    if (g->state == SOOP_G_SPOOFED)
        return;
    g->free = g->main;                //from here, free never hears the GPS
    if (g->cfg.free_vel_sigma > 0.0)
        g->free.cfg.vel_sigma = g->cfg.free_vel_sigma;
    g->state = SOOP_G_TRUSTED;
}

//free runs only once armed; before that it would just be a copy of main
#define FREE_RUNS(g) ((g)->state != SOOP_G_UNARMED)

void soop_guard_velocity(soop_guard_t *g, double t, float vn, float ve, float vd)
{
    soop_nav_velocity(&g->main, t, vn, ve, vd);
    if (FREE_RUNS(g))
        soop_nav_velocity(&g->free, t, vn, ve, vd);
}

void soop_guard_baro(soop_guard_t *g, double t, double h_m)
{
    soop_nav_baro(&g->main, t, h_m);
    if (FREE_RUNS(g))
        soop_nav_baro(&g->free, t, h_m);
}

void soop_guard_set_position(soop_guard_t *g, double t, const double ecef[3], double sigma_m)
{
    soop_nav_set_position(&g->main, t, ecef, sigma_m);
    if (FREE_RUNS(g))
        soop_nav_set_position(&g->free, t, ecef, sigma_m);
}

void soop_guard_set_time(soop_guard_t *g, double t, double t_utc)
{
    soop_nav_set_time(&g->main, t, t_utc);
    if (FREE_RUNS(g))
        soop_nav_set_time(&g->free, t, t_utc);
}

int soop_guard_burst(soop_guard_t *g, double t, double f_hz, double sigma_hz)
{
    if (FREE_RUNS(g))
        soop_nav_burst(&g->free, t, f_hz, sigma_hz);
    return soop_nav_burst(&g->main, t, f_hz, sigma_hz);
}

//horizontal distance between two ECEF points, at a
static double horiz(const double a[3], const double b[3])
{
    const double r = sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
    double d[3], up = 0.0;
    for (int i = 0; i < 3; i++) {
        d[i] = b[i] - a[i];
        up += d[i] * a[i] / r;
    }
    double h2 = 0.0;
    for (int i = 0; i < 3; i++) {
        const double e = d[i] - up * a[i] / r;
        h2 += e * e;
    }
    return sqrt(h2);
}

int soop_guard_gps(soop_guard_t *g, double t, double t_utc, const double ecef[3])
{
    const soop_guard_cfg_t *c = &g->cfg;
    if (g->state == SOOP_G_SPOOFED)
        return g->state;

    //jump: against main's own prediction
    soop_fix_t fm;
    if (g->main.anchored && soop_nav_fix(&g->main, t, &fm)) {
        const double s = hypot(fm.hacc_m, g->main.cfg.gps_sigma);
        if (horiz(fm.ecef, ecef) > fmax(c->jump_m, c->jump_sigma * s)) {
            g->n_jumps++;
            if (++g->n_jumps_run >= (uint32_t)c->jump_n) {
                g->state = SOOP_G_SPOOFED;
                g->t_spoofed = t;
            }
            return g->state;
        }
    }
    g->n_jumps_run = 0;

    //drag: against free, which the GPS has not touched since arming
    soop_fix_t ff;
    if (FREE_RUNS(g) && soop_nav_fix(&g->free, t, &ff)) {
        g->dist_m = horiz(ff.ecef, ecef);
        g->limit_m = fmax(c->floor_m, c->k * ff.hacc_m);
        if (g->dist_m > g->limit_m) {
            if (g->state != SOOP_G_SUSPECT) {
                g->state = SOOP_G_SUSPECT;
                g->since = t;
            } else if (t - g->since >= c->hold_s) {
                g->state = SOOP_G_SPOOFED;
                g->t_spoofed = t;
                g->main = g->free;          //the estimate the spoofer never reached
                return g->state;
            }
            return g->state;                //suspect: not fused while it is decided
        }
        g->state = SOOP_G_TRUSTED;
    }
    soop_nav_gps(&g->main, t, t_utc, ecef);
    return g->state;
}

int soop_guard_fix(soop_guard_t *g, double t, soop_fix_t *fix)
{
    return soop_nav_fix(&g->main, t, fix);
}
