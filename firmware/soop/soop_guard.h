//soop_guard.h - GPS spoofing guard
#ifndef SOOP_GUARD_H
#define SOOP_GUARD_H

#include "soop_nav.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    double jump_sigma, jump_m;   //a jump: beyond this many sigma of main, and this far
    int    jump_n;               //this many jumps in a row is a spoofer, not a glitch
    double k, floor_m;           //a drag: further from free than k x its hacc, and floor_m
    double hold_s;               //... continuously for this long
    double free_vel_sigma;       //free's flight-EKF velocity error, m/s (0: as main's)
} soop_guard_cfg_t;

enum { SOOP_G_UNARMED = 0, SOOP_G_TRUSTED, SOOP_G_SUSPECT, SOOP_G_SPOOFED };

typedef struct {
    soop_guard_cfg_t cfg;
    soop_nav_t main, free;
    int      state;              //SOOP_G_
    double   since;              //board s the disagreement began
    double   dist_m, limit_m;    //the last GPS fix against free
    double   t_spoofed;
    uint32_t n_jumps, n_jumps_run;
} soop_guard_t;

void soop_guard_default_cfg(soop_guard_cfg_t *c);
void soop_guard_init(soop_guard_t *g, const soop_nav_cfg_t *nav_cfg,
                     const soop_guard_cfg_t *cfg, const soop_sat_t *cat, int n_cat,
                     double t_now_utc);

//arming: from here on free is on its own
void soop_guard_arm(soop_guard_t *g, double t_board);

//as soop_nav_*: fed to both filters
void soop_guard_velocity(soop_guard_t *g, double t_board, float vn, float ve, float vd);
void soop_guard_baro(soop_guard_t *g, double t_board, double h_m);
void soop_guard_set_position(soop_guard_t *g, double t_board, const double ecef[3],
                             double sigma_m);
void soop_guard_set_time(soop_guard_t *g, double t_board, double t_utc);
int  soop_guard_burst(soop_guard_t *g, double t_board, double f_hz, double sigma_hz);

//a GPS fix the autopilot trusts
int  soop_guard_gps(soop_guard_t *g, double t_board, double t_utc, const double ecef[3]);

//main's fix
int  soop_guard_fix(soop_guard_t *g, double t_board, soop_fix_t *fix);

#ifdef __cplusplus
}
#endif

#endif //SOOP_GUARD_H
