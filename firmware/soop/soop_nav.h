//soop_nav.h - position from Iridium Doppler on a moving aircraft
#ifndef SOOP_NAV_H
#define SOOP_NAV_H

#include <stdint.h>
#include "soop_ephem.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SOOP_NAV_MAX_TRACK   12
#define SOOP_NAV_NS          4                   //states per tracked satellite
#define SOOP_NAV_NBASE       10
#define SOOP_NAV_NX          (SOOP_NAV_NBASE + SOOP_NAV_NS * SOOP_NAV_MAX_TRACK)
#define SOOP_NAV_MAX_VIS     20
#define SOOP_NAV_VEL_RING    128                 //flight-EKF velocity samples kept
#define SOOP_NAV_ACQ_MAX     128                 //bursts held for clock acquisition
#define SOOP_NAV_PEND        8                   //satellites being confirmed at once
#define SOOP_NAV_PEND_N      6

//how far a satellite's elements are off, 1 sigma, growing with their age
typedef struct {
    double along0_m, along_m_per_day;
    double cross0_m, cross_m_per_day;
    double radial0_m, radial_m_per_day;
} soop_orbit_err_t;

typedef struct {
    double vel_sigma, vel_tau;       //flight-EKF horizontal velocity error: m/s, s
    double velz_sigma, velz_tau;     //and vertical
    double clk_q;                    //TCXO frequency walk at the carrier, Hz/sqrt(s)
    double clkd_q;                   //its drift's walk, Hz/s/sqrt(s)
    double clk_sigma_acq;            //clock uncertainty after acquisition, Hz
    double clkd_sigma0;              //Hz/s
    double dt_sigma0;                //GPS time-tag error, s
    double baro_sigma, baro_bias_sigma, baro_bias_tau;
    double beta_sigma;               //satellite transmit offset, Hz
    soop_orbit_err_t orbit[SOOP_ORBIT_N];  //by where the elements came from
    double max_tle_age_d;            //refuse satellites with older elements
    double gps_sigma;                //m
    double sig_floor;                //Hz, added to the DSP's sigma
    double gate;                     //innovation gate, sigma
    double amb_ratio;                //runner-up must be this much worse (in NIS)
    int    confirm_n;                //bursts that must agree before a satellite joins
    double confirm_s, confirm_spread;//within this time, and this spread (Hz)
    double mask_deg;
    double drop_s;                   //forget a satellite not heard for this long
    double gps_min_dt, baro_min_dt;  //fuse at most this often: their errors are correlated
    double acq_span, acq_bin;        //clock search, Hz
    int    acq_min;                  //bursts needed to trust the clock histogram
    double fix_max_age;              //no fix without a Doppler update this recent, s
    double fix_max_hacc;             //m
    double dut1;                     //UT1-UTC, s
    double f_lo;                     //the tuner's LO, Hz (Ring Alert + the LO offset)
} soop_nav_cfg_t;

typedef struct {
    double t;                        //board s
    float  vn, ve, vd;
} soop_vel_t;

typedef struct {
    int    sat;                      //catalogue index
    int    n;
    double t[SOOP_NAV_PEND_N], y[SOOP_NAV_PEND_N];
} soop_pend_t;

typedef struct {
    double t;
    float  f, sigma;
} soop_acq_t;

enum {                               //what soop_nav_burst did with a burst
    SOOP_B_FUSED = 0, SOOP_B_REJECTED, SOOP_B_AMBIGUOUS, SOOP_B_UNMATCHED, SOOP_B_PENDING,
    SOOP_B_ACQUIRING, SOOP_B_NO_TIME, SOOP_B_N
};

typedef struct {
    soop_nav_cfg_t cfg;
    const soop_sat_t *cat;
    int    n_cat;
    uint8_t cat_ok[128];             //elements young enough to use

    //filter
    int    n;                        //state size now
    double x[SOOP_NAV_NX];
    double P[SOOP_NAV_NX][SOOP_NAV_NX];
    double t;                        //board time of x, P
    int    have_pos, have_clock;
    int    anchored;                 //position has been known: GPS, or a surveyed start
    int    track[SOOP_NAV_MAX_TRACK];//catalogue index of each tracked satellite
    double heard[SOOP_NAV_MAX_TRACK];
    int    n_track;

    //board time -> UTC, fitted on GPS time tags (exponentially weighted)
    double tb0, tu0, sw, sx, sy, sxx, sxy, tcal_last;
    double tc_a, tc_b;               //utc = tu0 + a + b (tb - tb0)
    int    have_time;
    double eps_mcu;                  //sample-clock error, fractional

    soop_vel_t vel[SOOP_NAV_VEL_RING];
    int    vel_head, vel_n;

    int    vis[SOOP_NAV_MAX_VIS];
    int    n_vis;
    double vis_t;

    soop_pend_t pend[SOOP_NAV_PEND], div[SOOP_NAV_PEND];
    soop_acq_t acq[SOOP_NAV_ACQ_MAX];
    int    n_acq;

    double last_gps, last_baro, last_fused;
    int    last_sat, last_ch;        //the last fused burst: NORAD number, channel 0-4
    double last_y, last_sd;          //and its innovation, Hz
    double nis_avg;
    int    gps_valid;
    uint32_t count[SOOP_B_N], n_resets, n_acq_tries;
} soop_nav_t;

typedef struct {
    double t;                        //board s
    double ecef[3];
    double lat_deg, lon_deg, h_m;    //WGS84, ellipsoidal height
    float  vn, ve, vd;               //m/s
    float  hacc_m, vacc_m, sacc_ms;  //1-sigma, horizontal from the major axis
    float  nis;                      //recent normalised innovation, ~1 when the model fits
    uint8_t n_track;
    uint8_t valid;                   //good enough to hand to the flight EKF
} soop_fix_t;

void soop_nav_default_cfg(soop_nav_cfg_t *c);

//cat must outlive nav
void soop_nav_init(soop_nav_t *nav, const soop_nav_cfg_t *cfg, const soop_sat_t *cat,
                   int n_cat, double t_now_utc);

//the flight EKF's velocity (NED, m/s), at whatever rate it runs
void soop_nav_velocity(soop_nav_t *nav, double t_board, float vn, float ve, float vd);

//a GPS fix while GPS is trusted
void soop_nav_gps(soop_nav_t *nav, double t_board, double t_utc, const double ecef[3]);

//ellipsoidal height from the baro (the caller ties baro to GPS height while it has it)
void soop_nav_baro(soop_nav_t *nav, double t_board, double h_m);

//a known position without GPS (bench, or a surveyed pad)
void soop_nav_set_position(soop_nav_t *nav, double t_board, const double ecef[3], double sigma_m);
void soop_nav_set_time(soop_nav_t *nav, double t_board, double t_utc);

//one burst from the DSP: carrier in the capture (Hz) and its sigma
int  soop_nav_burst(soop_nav_t *nav, double t_board, double f_hz, double sigma_hz);

//the current estimate, propagated to t_board
int  soop_nav_fix(soop_nav_t *nav, double t_board, soop_fix_t *fix);

//1 when the whole catalogue is older than max_tle_age_d
int  soop_nav_cat_stale(const soop_nav_t *nav);

//the newest TLE epoch in the catalogue, UTC s since J2000.0
double soop_nav_cat_newest_epoch(const soop_nav_t *nav);

//ECEF <-> geodetic (WGS84)
void soop_geodetic(const double r[3], double *lat_deg, double *lon_deg, double *h);
void soop_ecef(double lat_deg, double lon_deg, double h, double r[3]);

#ifdef __cplusplus
}
#endif

#endif //SOOP_NAV_H
