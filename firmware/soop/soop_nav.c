//soop_nav.c - see soop_nav.h
//ArduPilot compiles every source with -fsingle-precision-constant
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize ("no-single-precision-constant")
#endif
typedef char soop_needs_double_constants[((long)299792458.0 == 299792458L) ? 1 : -1];
#include "soop_nav.h"
#include "soop_signal.h"
#include <math.h>
#include <string.h>

#define PI       3.14159265358979323846
#define CLIGHT   299792458.0
#define MU_EARTH 3.986004418e14
#define BAND_HZ  45000.0          //furthest a burst can sit from Ring Alert and be captured

enum { IP = 0, IV = 3, IC = 6, ICD = 7, IDT = 8, IBB = 9 };

void soop_nav_default_cfg(soop_nav_cfg_t *c)
{
    memset(c, 0, sizeof *c);
    c->vel_sigma = 1.5;   c->vel_tau = 300.0;
    c->velz_sigma = 0.5;  c->velz_tau = 60.0;
    c->clk_q = 0.3;       c->clkd_q = 0.08;
    c->clk_sigma_acq = 60.0;
    c->clkd_sigma0 = 1.0;
    c->dt_sigma0 = 0.03;
    c->baro_sigma = 0.5;  c->baro_bias_sigma = 3.0;  c->baro_bias_tau = 600.0;
    c->beta_sigma = 60.0;
    c->along0_m = 300.0;  c->along_m_per_day = 1000.0;
    c->cross_m = 200.0;   c->radial_m = 100.0;
    c->max_tle_age_d = 7.0;
    c->gps_sigma = 3.0;
    c->sig_floor = 1.0;
    c->gate = 5.0;
    c->amb_ratio = 9.0;
    c->confirm_n = 3;     c->confirm_s = 40.0;  c->confirm_spread = 40.0;
    c->mask_deg = 5.0;
    c->drop_s = 120.0;
    c->gps_min_dt = 0.4;  c->baro_min_dt = 1.0;
    c->acq_span = 6000.0; c->acq_bin = 100.0;   c->acq_min = 16;
    c->fix_max_age = 30.0;
    c->fix_max_hacc = 3000.0;
    c->dut1 = 0.0;
    c->f_lo = SOOP_F_RING_ALERT + SOOP_LO_OFFSET_HZ;
}

//geometry
void soop_ecef(double lat_deg, double lon_deg, double h, double r[3])
{
    const double a = 6378137.0, f = 1.0 / 298.257223563, e2 = f * (2.0 - f);
    const double la = lat_deg * PI / 180.0, lo = lon_deg * PI / 180.0;
    const double N = a / sqrt(1.0 - e2 * sin(la) * sin(la));
    r[0] = (N + h) * cos(la) * cos(lo);
    r[1] = (N + h) * cos(la) * sin(lo);
    r[2] = (N * (1.0 - e2) + h) * sin(la);
}

void soop_geodetic(const double r[3], double *lat_deg, double *lon_deg, double *h)
{
    const double a = 6378137.0, f = 1.0 / 298.257223563, e2 = f * (2.0 - f);
    const double b = a * (1.0 - f), ep2 = (a * a - b * b) / (b * b);
    const double p = sqrt(r[0] * r[0] + r[1] * r[1]);
    const double th = atan2(r[2] * a, p * b);
    const double st = sin(th), ct = cos(th);
    const double lat = atan2(r[2] + ep2 * b * st * st * st, p - e2 * a * ct * ct * ct);
    const double N = a / sqrt(1.0 - e2 * sin(lat) * sin(lat));
    *lat_deg = lat * 180.0 / PI;
    *lon_deg = atan2(r[1], r[0]) * 180.0 / PI;
    *h = p / cos(lat) - N;
}

//columns north, east, down: v_ecef = R v_ned
static void ned_matrix(const double r[3], double R[3][3])
{
    double lat, lon, h;
    soop_geodetic(r, &lat, &lon, &h);
    const double sl = sin(lat * PI / 180.0), cl = cos(lat * PI / 180.0);
    const double so = sin(lon * PI / 180.0), co = cos(lon * PI / 180.0);
    const double n[3] = { -sl * co, -sl * so, cl };
    const double e[3] = { -so, co, 0.0 };
    const double d[3] = { -cl * co, -cl * so, -sl };
    for (int i = 0; i < 3; i++) {
        R[i][0] = n[i];
        R[i][1] = e[i];
        R[i][2] = d[i];
    }
}

static double dot3(const double *a, const double *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
static double norm3(const double *a) { return sqrt(dot3(a, a)); }

static double f_channel(int ch)
{
    return SOOP_F_RING_ALERT - (double)(SOOP_N_SIMPLEX - 1 - ch) * SOOP_CH_SPACING;
}

//time
static double utc_of(const soop_nav_t *nav, double tb)
{
    return nav->tu0 + nav->tc_a + (1.0 + nav->tc_b) * (tb - nav->tb0);
}

static void screen_catalogue(soop_nav_t *nav, double t_utc)
{
    for (int i = 0; i < nav->n_cat && i < (int)sizeof nav->cat_ok; i++)
        nav->cat_ok[i] = t_utc == 0.0
            || fabs(t_utc - nav->cat[i].epoch_s) < nav->cfg.max_tle_age_d * 86400.0;
}

//board time -> UTC, a straight line through the GPS time tags
static void time_sample(soop_nav_t *nav, double tb, double tu)
{
    if (!nav->have_time) {
        nav->tb0 = tb;
        nav->tu0 = tu;
        nav->sw = nav->sx = nav->sy = nav->sxx = nav->sxy = 0.0;
        nav->tcal_last = tb;
        screen_catalogue(nav, tu);
    }
    const double k = exp(-(tb - nav->tcal_last) / 900.0);
    nav->sw *= k; nav->sx *= k; nav->sy *= k; nav->sxx *= k; nav->sxy *= k;
    nav->tcal_last = tb;
    const double X = tb - nav->tb0, Y = (tu - nav->tu0) - X;
    nav->sw += 1.0; nav->sx += X; nav->sy += Y; nav->sxx += X * X; nav->sxy += X * Y;
    const double den = nav->sw * nav->sxx - nav->sx * nav->sx;
    if (nav->sw > 10.0 && den > nav->sw * nav->sw) {          //spread over > ~2 s
        nav->tc_b = (nav->sw * nav->sxy - nav->sx * nav->sy) / den;
        nav->tc_a = (nav->sy - nav->tc_b * nav->sx) / nav->sw;
    } else {
        nav->tc_b = 0.0;
        nav->tc_a = nav->sy / nav->sw;
    }
    nav->eps_mcu = 1.0 / (1.0 + nav->tc_b) - 1.0;
    nav->have_time = 1;
}

void soop_nav_set_time(soop_nav_t *nav, double t_board, double t_utc)
{
    time_sample(nav, t_board, t_utc);
}

//set-up
static void base_init(soop_nav_t *nav, const double pos[3], double sigma, double t)
{
    soop_nav_cfg_t *c = &nav->cfg;
    nav->n = SOOP_NAV_NBASE;
    memset(nav->x, 0, sizeof nav->x);
    memset(nav->P, 0, sizeof nav->P);
    for (int i = 0; i < 3; i++) {
        nav->x[IP + i] = pos[i];
        nav->P[IP + i][IP + i] = sigma * sigma;
        nav->P[IV + i][IV + i] = 0.1 * 0.1;
    }
    nav->P[IC][IC] = c->acq_span * c->acq_span;
    nav->P[ICD][ICD] = c->clkd_sigma0 * c->clkd_sigma0;
    nav->P[IDT][IDT] = c->dt_sigma0 * c->dt_sigma0;
    nav->P[IBB][IBB] = c->baro_bias_sigma * c->baro_bias_sigma;
    nav->t = t;
    nav->n_track = 0;
    nav->have_pos = 1;
    nav->have_clock = 0;
    nav->n_acq = 0;
    nav->vis_t = -1e9;
}

void soop_nav_init(soop_nav_t *nav, const soop_nav_cfg_t *cfg, const soop_sat_t *cat,
                   int n_cat, double t_now_utc)
{
    memset(nav, 0, sizeof *nav);
    nav->cfg = *cfg;
    nav->cat = cat;
    nav->n_cat = n_cat < (int)sizeof nav->cat_ok ? n_cat : (int)sizeof nav->cat_ok;
    screen_catalogue(nav, t_now_utc);
    nav->last_gps = nav->last_baro = nav->last_fused = -1e9;
    nav->vis_t = -1e9;
    nav->nis_avg = 1.0;
}

void soop_nav_set_position(soop_nav_t *nav, double t_board, const double ecef[3], double sigma_m)
{
    base_init(nav, ecef, sigma_m, t_board);
    nav->anchored = sigma_m <= 50.0;
}

//the flight EKF's velocity
void soop_nav_velocity(soop_nav_t *nav, double t_board, float vn, float ve, float vd)
{
    soop_vel_t *s = &nav->vel[nav->vel_head];
    s->t = t_board;
    s->vn = vn;
    s->ve = ve;
    s->vd = vd;
    nav->vel_head = (nav->vel_head + 1) % SOOP_NAV_VEL_RING;
    if (nav->vel_n < SOOP_NAV_VEL_RING)
        nav->vel_n++;
}

static const soop_vel_t *vel_i(const soop_nav_t *nav, int i)   //0 = oldest
{
    return &nav->vel[(nav->vel_head - nav->vel_n + i + SOOP_NAV_VEL_RING) % SOOP_NAV_VEL_RING];
}

static void vel_at(const soop_nav_t *nav, double t, double v[3])
{
    v[0] = v[1] = v[2] = 0.0;
    if (nav->vel_n == 0)
        return;
    const soop_vel_t *a = vel_i(nav, 0), *b = vel_i(nav, nav->vel_n - 1);
    if (t <= a->t) { v[0] = a->vn; v[1] = a->ve; v[2] = a->vd; return; }
    if (t >= b->t) { v[0] = b->vn; v[1] = b->ve; v[2] = b->vd; return; }
    for (int i = nav->vel_n - 1; i > 0; i--) {
        a = vel_i(nav, i - 1);
        b = vel_i(nav, i);
        if (a->t <= t) {
            const double w = (b->t > a->t) ? (t - a->t) / (b->t - a->t) : 0.0;
            v[0] = a->vn + w * (b->vn - a->vn);
            v[1] = a->ve + w * (b->ve - a->ve);
            v[2] = a->vd + w * (b->vd - a->vd);
            return;
        }
    }
}

//propagation
static void step(soop_nav_t *nav, double dt, const double vned[3], double R[3][3])
{
    const soop_nav_cfg_t *c = &nav->cfg;
    const int n = nav->n;
    double *x = nav->x;
    double (*P)[SOOP_NAV_NX] = nav->P;
    double a[3], Rdt[3][3];
    for (int k = 0; k < 3; k++)
        a[k] = exp(-dt / (k < 2 ? c->vel_tau : c->velz_tau));
    const double ab = exp(-dt / c->baro_bias_tau);
    for (int i = 0; i < 3; i++)
        for (int k = 0; k < 3; k++)
            Rdt[i][k] = R[i][k] * dt;

    const double vt[3] = { vned[0] + x[IV], vned[1] + x[IV + 1], vned[2] + x[IV + 2] };
    for (int i = 0; i < 3; i++)
        x[IP + i] += dot3(R[i], vt) * dt;
    for (int k = 0; k < 3; k++)
        x[IV + k] *= a[k];
    x[IC] += x[ICD] * dt;
    x[IBB] *= ab;

    //p <- F P F^T, F = I except: p += R dt dv, dv *= a, c += dt cd, bb *= ab
    for (int j = 0; j < n; j++) {                  //rows
        for (int i = 0; i < 3; i++)
            P[IP + i][j] += Rdt[i][0] * P[IV][j] + Rdt[i][1] * P[IV + 1][j] + Rdt[i][2] * P[IV + 2][j];
        for (int k = 0; k < 3; k++)
            P[IV + k][j] *= a[k];
        P[IC][j] += dt * P[ICD][j];
        P[IBB][j] *= ab;
    }
    for (int j = 0; j < n; j++) {                  //columns
        double *r = P[j];
        for (int i = 0; i < 3; i++)
            r[IP + i] += Rdt[i][0] * r[IV] + Rdt[i][1] * r[IV + 1] + Rdt[i][2] * r[IV + 2];
        for (int k = 0; k < 3; k++)
            r[IV + k] *= a[k];
        r[IC] += dt * r[ICD];
        r[IBB] *= ab;
    }
    for (int k = 0; k < 3; k++) {
        const double s = k < 2 ? c->vel_sigma : c->velz_sigma;
        P[IV + k][IV + k] += s * s * (1.0 - a[k] * a[k]);
    }
    const double qc = c->clk_q * c->clk_q, qd = c->clkd_q * c->clkd_q;
    P[IC][IC] += qc * dt + qd * dt * dt * dt / 3.0;
    P[IC][ICD] += qd * dt * dt / 2.0;
    P[ICD][IC] += qd * dt * dt / 2.0;
    P[ICD][ICD] += qd * dt;
    P[IBB][IBB] += c->baro_bias_sigma * c->baro_bias_sigma * (1.0 - ab * ab);
}

static void propagate_to(soop_nav_t *nav, double t_new)
{
    if (!nav->have_pos || t_new <= nav->t)
        return;
    double R[3][3];
    ned_matrix(nav->x, R);
    double t = nav->t;
    int i = 0;
    while (t < t_new) {
        while (i < nav->vel_n && vel_i(nav, i)->t <= t + 1e-6)
            i++;
        double t_next = (i < nav->vel_n && vel_i(nav, i)->t < t_new) ? vel_i(nav, i)->t : t_new;
        double v[3];
        vel_at(nav, 0.5 * (t + t_next), v);
        step(nav, t_next - t, v, R);
        t = t_next;
    }
    nav->t = t_new;
}

//measurement updates
typedef struct {
    int    m;
    int    idx[16];
    double val[16];
} hrow_t;

static void hrow_add(hrow_t *h, int i, double v) { h->idx[h->m] = i; h->val[h->m] = v; h->m++; }

static double hph(const soop_nav_t *nav, const hrow_t *h)
{
    double s = 0.0;
    for (int a = 0; a < h->m; a++)
        for (int b = 0; b < h->m; b++)
            s += h->val[a] * nav->P[h->idx[a]][h->idx[b]] * h->val[b];
    return s;
}

static void kalman(soop_nav_t *nav, const hrow_t *h, double y, double r2)
{
    const int n = nav->n;
    double PH[SOOP_NAV_NX];
    for (int i = 0; i < n; i++) {
        double s = 0.0;
        for (int k = 0; k < h->m; k++)
            s += nav->P[i][h->idx[k]] * h->val[k];
        PH[i] = s;
    }
    double S = r2;
    for (int k = 0; k < h->m; k++)
        S += h->val[k] * PH[h->idx[k]];
    for (int i = 0; i < n; i++)
        nav->x[i] += PH[i] / S * y;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            nav->P[i][j] -= PH[i] * PH[j] / S;
}

void soop_nav_gps(soop_nav_t *nav, double t_board, double t_utc, const double ecef[3])
{
    time_sample(nav, t_board, t_utc);
    nav->gps_valid = 1;
    if (!nav->have_pos) {
        base_init(nav, ecef, 10.0, t_board);
        nav->last_gps = t_board;
        nav->anchored = 1;
        return;
    }
    if (t_board - nav->last_gps < nav->cfg.gps_min_dt)
        return;
    nav->last_gps = t_board;
    propagate_to(nav, t_board);
    for (int i = 0; i < 3; i++) {
        hrow_t h = { 0, {0}, {0} };
        hrow_add(&h, IP + i, 1.0);
        kalman(nav, &h, ecef[i] - nav->x[IP + i], nav->cfg.gps_sigma * nav->cfg.gps_sigma);
    }
}

void soop_nav_baro(soop_nav_t *nav, double t_board, double h_m)
{
    if (!nav->have_pos || t_board - nav->last_baro < nav->cfg.baro_min_dt)
        return;
    nav->last_baro = t_board;
    propagate_to(nav, t_board);
    double R[3][3], lat, lon, hh;
    ned_matrix(nav->x, R);
    soop_geodetic(nav->x, &lat, &lon, &hh);
    hrow_t h = { 0, {0}, {0} };
    for (int i = 0; i < 3; i++)
        hrow_add(&h, IP + i, -R[i][2]);          //up = -down
    hrow_add(&h, IBB, 1.0);
    kalman(nav, &h, h_m - (hh + nav->x[IBB]), nav->cfg.baro_sigma * nav->cfg.baro_sigma);
}

//satellites
static int slot_of(const soop_nav_t *nav, int sat)
{
    for (int k = 0; k < nav->n_track; k++)
        if (nav->track[k] == sat)
            return k;
    return -1;
}

static void sat_prior(const soop_nav_t *nav, int sat, double t_utc, double pr[4])
{
    const soop_nav_cfg_t *c = &nav->cfg;
    const double age = fabs(t_utc - nav->cat[sat].epoch_s) / 86400.0;
    const double s_tau = (c->along0_m + c->along_m_per_day * age) / 7400.0;
    pr[0] = c->beta_sigma * c->beta_sigma;
    pr[1] = s_tau * s_tau;
    pr[2] = c->cross_m * c->cross_m;
    pr[3] = c->radial_m * c->radial_m;
}

static void drop_slot(soop_nav_t *nav, int k)
{
    const int o = SOOP_NAV_NBASE + SOOP_NAV_NS * k, n = nav->n;
    for (int i = o; i < n - SOOP_NAV_NS; i++) {
        nav->x[i] = nav->x[i + SOOP_NAV_NS];
        for (int j = 0; j < n; j++)
            nav->P[i][j] = nav->P[i + SOOP_NAV_NS][j];
    }
    for (int j = o; j < n - SOOP_NAV_NS; j++)
        for (int i = 0; i < n - SOOP_NAV_NS; i++)
            nav->P[i][j] = nav->P[i][j + SOOP_NAV_NS];
    for (int q = k; q < nav->n_track - 1; q++) {
        nav->track[q] = nav->track[q + 1];
        nav->heard[q] = nav->heard[q + 1];
    }
    nav->n_track--;
    nav->n -= SOOP_NAV_NS;
}

static int add_slot(soop_nav_t *nav, int sat, double t_board, double t_utc)
{
    if (nav->n_track == SOOP_NAV_MAX_TRACK) {
        int old = 0;                              //make room: forget the least recent
        for (int k = 1; k < nav->n_track; k++)
            if (nav->heard[k] < nav->heard[old])
                old = k;
        drop_slot(nav, old);
    }
    const int k = nav->n_track++, o = nav->n;
    double pr[4];
    sat_prior(nav, sat, t_utc, pr);
    nav->n += SOOP_NAV_NS;
    for (int i = o; i < nav->n; i++) {
        nav->x[i] = 0.0;
        for (int j = 0; j < nav->n; j++)
            nav->P[i][j] = nav->P[j][i] = 0.0;
        nav->P[i][i] = pr[i - o];
    }
    nav->track[k] = sat;
    nav->heard[k] = t_board;
    return k;
}

//where satellite `sat` is as seen by a burst received at t_board
typedef struct {
    double r[3], v[3], a[3], uc[3], ur[3];
} satgeo_t;

static int sat_geometry(const soop_nav_t *nav, int sat, double t_utc, double tau, satgeo_t *g)
{
    double r[3], v[3], a[3];
    if (soop_ephem_state(&nav->cat[sat], t_utc, nav->cfg.dut1, r, v) != 0)
        return -1;
    //gravity plus the rotating frame's terms
    const double rm = norm3(r), w = SOOP_OMEGA_EARTH;
    const double k = -MU_EARTH / (rm * rm * rm);
    a[0] = k * r[0] + 2.0 * w * v[1] + w * w * r[0];
    a[1] = k * r[1] - 2.0 * w * v[0] + w * w * r[1];
    a[2] = k * r[2];
    double d[3] = { r[0] - nav->x[IP], r[1] - nav->x[IP + 1], r[2] - nav->x[IP + 2] };
    const double tt = tau - norm3(d) / CLIGHT;     //light time, then the timing states
    for (int i = 0; i < 3; i++) {
        g->r[i] = r[i] + v[i] * tt + 0.5 * a[i] * tt * tt;
        g->v[i] = v[i] + a[i] * tt;
        g->a[i] = a[i];
    }
    const double h[3] = { g->r[1] * g->v[2] - g->r[2] * g->v[1],
                          g->r[2] * g->v[0] - g->r[0] * g->v[2],
                          g->r[0] * g->v[1] - g->r[1] * g->v[0] };
    const double hm = norm3(h), gm = norm3(g->r);
    for (int i = 0; i < 3; i++) {
        g->uc[i] = h[i] / hm;
        g->ur[i] = g->r[i] / gm;
    }
    return 0;
}

//the Doppler of one burst against (satellite, channel)
typedef struct {
    hrow_t h;              //shared states
    double sat_h[4];
    double y, r2, S;
} pred_t;

static void predict(const soop_nav_t *nav, const satgeo_t *g0, int slot, int fresh, int sat,
                    double t_board, double t_utc, double f_hz, double sigma, int ch,
                    double R[3][3], const double vr_ned[3], pred_t *p)
{
    const double *x = nav->x;
    const int o = slot >= 0 ? SOOP_NAV_NBASE + SOOP_NAV_NS * slot : -1;
    const int own = o >= 0 && !fresh;
    double xs[4] = { 0, 0, 0, 0 };
    if (own)
        for (int i = 0; i < 4; i++)
            xs[i] = x[o + i];
    (void)t_board;
    //the satellite state was taken at the tracked timing
    satgeo_t g = *g0;
    const double dtau = (own ? 0.0 : -(o >= 0 ? x[o + 1] : 0.0));
    for (int i = 0; i < 3; i++) {
        g.r[i] += g0->v[i] * dtau + 0.5 * g0->a[i] * dtau * dtau;
        g.v[i] += g0->a[i] * dtau;
    }
    double rs[3], vr[3], d[3], dv[3];
    for (int i = 0; i < 3; i++) {
        rs[i] = g.r[i] + xs[2] * g.uc[i] + xs[3] * g.ur[i];
        vr[i] = R[i][0] * (vr_ned[0] + x[IV]) + R[i][1] * (vr_ned[1] + x[IV + 1])
              + R[i][2] * (vr_ned[2] + x[IV + 2]);
        d[i] = rs[i] - x[IP + i];
        dv[i] = g.v[i] - vr[i];
    }
    const double rho = norm3(d);
    double u[3] = { d[0] / rho, d[1] / rho, d[2] / rho };
    const double rdot = dot3(dv, u);
    const double fch = f_channel(ch), k = fch / CLIGHT;
    const double df = f_hz * (1.0 + nav->eps_mcu) + nav->cfg.f_lo - fch;
    const double h = -k * rdot + xs[0] + x[IC];
    double gr[3], gv[3];
    for (int i = 0; i < 3; i++) {
        gr[i] = k * (dv[i] - rdot * u[i]) / rho;       //d h / d receiver position
        gv[i] = k * u[i];                              //d h / d receiver velocity
    }
    const double dtau_h = -dot3(gr, g.v) - dot3(gv, g.a);
    p->h.m = 0;
    for (int i = 0; i < 3; i++)
        hrow_add(&p->h, IP + i, gr[i]);
    for (int j = 0; j < 3; j++)
        hrow_add(&p->h, IV + j, gv[0] * R[0][j] + gv[1] * R[1][j] + gv[2] * R[2][j]);
    hrow_add(&p->h, IC, 1.0);
    hrow_add(&p->h, IDT, dtau_h);
    p->sat_h[0] = 1.0;
    p->sat_h[1] = dtau_h;
    p->sat_h[2] = -dot3(gr, g.uc);
    p->sat_h[3] = -dot3(gr, g.ur);
    if (own)
        for (int i = 0; i < 4; i++)
            hrow_add(&p->h, o + i, p->sat_h[i]);
    p->y = df - h;
    p->r2 = sigma * sigma + nav->cfg.sig_floor * nav->cfg.sig_floor;
    p->S = hph(nav, &p->h) + p->r2;
    if (!own) {
        double pr[4];
        sat_prior(nav, sat, t_utc, pr);
        for (int i = 0; i < 4; i++)
            p->S += p->sat_h[i] * p->sat_h[i] * pr[i];
    }
}

static void refresh_visible(soop_nav_t *nav, double t_board)
{
    if (t_board - nav->vis_t < 10.0 && t_board >= nav->vis_t)
        return;
    nav->vis_t = t_board;
    const double tu = utc_of(nav, t_board);
    double R[3][3];
    ned_matrix(nav->x, R);
    const double smask = sin(nav->cfg.mask_deg * PI / 180.0);
    nav->n_vis = 0;
    for (int s = 0; s < nav->n_cat && nav->n_vis < SOOP_NAV_MAX_VIS; s++) {
        double r[3], v[3];
        if (!nav->cat_ok[s] || soop_ephem_state(&nav->cat[s], tu, nav->cfg.dut1, r, v) != 0)
            continue;
        double d[3] = { r[0] - nav->x[0], r[1] - nav->x[1], r[2] - nav->x[2] };
        const double up = -(d[0] * R[0][2] + d[1] * R[1][2] + d[2] * R[2][2]) / norm3(d);
        if (up > smask)
            nav->vis[nav->n_vis++] = s;
    }
}

//candidates for a burst: (NIS, sat, ch, y)
typedef struct {
    double q, y;
    int    sat, ch;
} cand_t;

static int candidates(soop_nav_t *nav, double tb, double f_hz, double sigma, int fresh_tracked,
                      cand_t *out, int max_out)
{
    const double tu = utc_of(nav, tb);
    double R[3][3], v_ned[3];
    ned_matrix(nav->x, R);
    vel_at(nav, tb, v_ned);
    int n = 0;
    const int nsrc = fresh_tracked ? nav->n_track : nav->n_vis;
    for (int j = 0; j < nsrc; j++) {
        const int sat = fresh_tracked ? nav->track[j] : nav->vis[j];
        const int slot = slot_of(nav, sat);
        const double tau = nav->x[IDT] + (slot >= 0 ? nav->x[SOOP_NAV_NBASE + SOOP_NAV_NS * slot + 1] : 0.0);
        satgeo_t g;
        if (sat_geometry(nav, sat, tu, tau, &g) != 0)
            continue;
        for (int ch = 0; ch < SOOP_N_SIMPLEX; ch++) {
            const double df = f_hz * (1.0 + nav->eps_mcu) + nav->cfg.f_lo - f_channel(ch);
            if (fabs(df) > BAND_HZ)
                continue;
            pred_t p;
            predict(nav, &g, slot, fresh_tracked, sat, tb, tu, f_hz, sigma, ch, R, v_ned, &p);
            const double q = p.y * p.y / p.S;
            if (q < nav->cfg.gate * nav->cfg.gate && n < max_out) {
                int i = n++;
                while (i > 0 && out[i - 1].q > q) {       //keep sorted
                    out[i] = out[i - 1];
                    i--;
                }
                out[i].q = q;
                out[i].y = p.y;
                out[i].sat = sat;
                out[i].ch = ch;
            }
        }
    }
    return n;
}

static void fuse(soop_nav_t *nav, double tb, double f_hz, double sigma, int sat, int ch)
{
    const double tu = utc_of(nav, tb);
    int slot = slot_of(nav, sat);
    if (slot < 0)
        slot = add_slot(nav, sat, tb, tu);
    double R[3][3], v_ned[3];
    ned_matrix(nav->x, R);
    vel_at(nav, tb, v_ned);
    satgeo_t g;
    const double tau = nav->x[IDT] + nav->x[SOOP_NAV_NBASE + SOOP_NAV_NS * slot + 1];
    if (sat_geometry(nav, sat, tu, tau, &g) != 0)
        return;
    pred_t p;
    predict(nav, &g, slot, 0, sat, tb, tu, f_hz, sigma, ch, R, v_ned, &p);
    const double q = p.y * p.y / p.S;
    if (q > nav->cfg.gate * nav->cfg.gate)
        return;
    kalman(nav, &p.h, p.y, p.r2);
    nav->last_sat = (int)nav->cat[sat].norad;
    nav->last_ch = ch;
    nav->last_y = p.y;
    nav->last_sd = sqrt(p.S);
    nav->heard[slot] = tb;
    nav->last_fused = tb;
    nav->nis_avg += 0.02 * (q - nav->nis_avg);
}

//a new satellite's (or a doubted track's) bursts
static int pend_push(soop_nav_t *nav, soop_pend_t *list, int sat, double t, double y)
{
    const soop_nav_cfg_t *c = &nav->cfg;
    soop_pend_t *e = NULL, *oldest = &list[0];
    for (int i = 0; i < SOOP_NAV_PEND; i++) {
        if (list[i].n && list[i].sat == sat)
            e = &list[i];
        if (list[i].n == 0 || (oldest->n && list[i].t[list[i].n - 1] < oldest->t[oldest->n - 1]))
            oldest = &list[i];
    }
    if (!e) {
        e = oldest;
        e->sat = sat;
        e->n = 0;
    }
    int m = 0;                                    //expire, then append
    for (int i = 0; i < e->n; i++)
        if (t - e->t[i] < c->confirm_s) {
            e->t[m] = e->t[i];
            e->y[m] = e->y[i];
            m++;
        }
    if (m == SOOP_NAV_PEND_N) {
        for (int i = 1; i < m; i++) {
            e->t[i - 1] = e->t[i];
            e->y[i - 1] = e->y[i];
        }
        m--;
    }
    e->t[m] = t;
    e->y[m] = y;
    e->n = m + 1;
    if (e->n < c->confirm_n)
        return 0;
    double lo = 1e30, hi = -1e30;
    for (int i = e->n - c->confirm_n; i < e->n; i++) {
        lo = fmin(lo, e->y[i]);
        hi = fmax(hi, e->y[i]);
    }
    if (hi - lo >= c->confirm_spread)
        return 0;
    e->n = 0;
    return 1;
}

//clock acquisition
static int acquire(soop_nav_t *nav)
{
    const soop_nav_cfg_t *c = &nav->cfg;
    enum { NB = 160 };
    int nb = (int)(2.0 * c->acq_span / c->acq_bin);
    if (nb > NB)
        nb = NB;
    uint16_t hist[NB];
    memset(hist, 0, sizeof hist);
    const double x_c = nav->x[IC];
    nav->x[IC] = 0.0;
    double R[3][3];
    ned_matrix(nav->x, R);
    for (int pass = 0; pass < 2; pass++) {
        int kpk = 0, best = 0, second = 0;
        if (pass == 1) {                          //find the peak pair, and the best elsewhere
            for (int k = 0; k + 1 < nb; k++)
                if (hist[k] + hist[k + 1] > best) {
                    best = hist[k] + hist[k + 1];
                    kpk = k;
                }
            for (int k = 0; k + 1 < nb; k++)
                if ((k < kpk - 2 || k > kpk + 2) && hist[k] + hist[k + 1] > second)
                    second = hist[k] + hist[k + 1];
            nav->n_acq_tries++;
            if (best < c->acq_min / 2 || best < 2 * second) {
                nav->x[IC] = x_c;
                return 0;
            }
        }
        double sum = 0.0;
        int cnt = 0;
        for (int b = 0; b < nav->n_acq; b++) {
            const soop_acq_t *a = &nav->acq[b];
            const double tu = utc_of(nav, a->t);
            double v_ned[3];
            vel_at(nav, a->t, v_ned);
            for (int j = 0; j < nav->n_vis; j++) {
                const int sat = nav->vis[j];
                satgeo_t g;
                if (sat_geometry(nav, sat, tu, nav->x[IDT], &g) != 0)
                    continue;
                for (int ch = 0; ch < SOOP_N_SIMPLEX; ch++) {
                    pred_t p;
                    predict(nav, &g, -1, 1, sat, a->t, tu, a->f, a->sigma, ch, R, v_ned, &p);
                    if (fabs(p.y) >= c->acq_span)
                        continue;
                    const int k = (int)((p.y + c->acq_span) / c->acq_bin);
                    if (k < 0 || k >= nb)
                        continue;
                    if (pass == 0) {
                        if (hist[k] < 0xFFFF)
                            hist[k]++;
                    } else if (k == kpk || k == kpk + 1) {
                        sum += p.y;
                        cnt++;
                    }
                }
            }
        }
        if (pass == 1) {
            nav->x[IC] = sum / cnt;
            nav->P[IC][IC] = c->clk_sigma_acq * c->clk_sigma_acq;
            for (int i = 0; i < nav->n; i++)
                if (i != IC)
                    nav->P[IC][i] = nav->P[i][IC] = 0.0;
            nav->have_clock = 1;
            nav->n_acq = 0;
            return 1;
        }
    }
    return 0;
}

int soop_nav_burst(soop_nav_t *nav, double t_board, double f_hz, double sigma_hz)
{
    const soop_nav_cfg_t *c = &nav->cfg;
    int res;
    if (!nav->have_time || !nav->have_pos) {
        res = SOOP_B_NO_TIME;
        goto done;
    }
    propagate_to(nav, t_board);
    refresh_visible(nav, t_board);
    if (!nav->have_clock) {
        if (nav->n_acq == SOOP_NAV_ACQ_MAX) {
            memmove(nav->acq, nav->acq + 1, (SOOP_NAV_ACQ_MAX - 1) * sizeof nav->acq[0]);
            nav->n_acq--;
        }
        nav->acq[nav->n_acq].t = t_board;
        nav->acq[nav->n_acq].f = (float)f_hz;
        nav->acq[nav->n_acq].sigma = (float)sigma_hz;
        nav->n_acq++;
        if (nav->n_acq >= c->acq_min && t_board - nav->acq[0].t > 10.0 && !acquire(nav)) {
            const int keep = nav->n_acq / 2;      //not yet: slide on
            memmove(nav->acq, nav->acq + nav->n_acq - keep, keep * sizeof nav->acq[0]);
            nav->n_acq = keep;
        }
        res = SOOP_B_ACQUIRING;
        goto done;
    }

    cand_t cd[8];
    const int nc = candidates(nav, t_board, f_hz, sigma_hz, 0, cd, 8);
    if (nc >= 1 && (nc == 1 || cd[1].q > c->amb_ratio * fmax(cd[0].q, 1.0))) {
        if (slot_of(nav, cd[0].sat) >= 0) {
            fuse(nav, t_board, f_hz, sigma_hz, cd[0].sat, cd[0].ch);
            res = SOOP_B_FUSED;
        } else if (pend_push(nav, nav->pend, cd[0].sat, t_board, cd[0].y)) {
            fuse(nav, t_board, f_hz, sigma_hz, cd[0].sat, cd[0].ch);
            res = SOOP_B_FUSED;
        } else {
            res = SOOP_B_PENDING;
        }
    } else if (nc > 1) {
        res = SOOP_B_AMBIGUOUS;
    } else {
        //nothing fits: is it a tracked satellite whose state has gone wrong?
        cand_t cf[2];
        if (candidates(nav, t_board, f_hz, sigma_hz, 1, cf, 2) == 1
            && pend_push(nav, nav->div, cf[0].sat, t_board, cf[0].y)) {
            const int k = slot_of(nav, cf[0].sat);
            if (k >= 0) {
                drop_slot(nav, k);
                nav->n_resets++;
            }
        }
        res = SOOP_B_UNMATCHED;
    }
    for (int k = nav->n_track - 1; k >= 0; k--)
        if (t_board - nav->heard[k] > c->drop_s)
            drop_slot(nav, k);
done:
    nav->count[res]++;
    return res;
}

//output
int soop_nav_fix(soop_nav_t *nav, double t_board, soop_fix_t *f)
{
    memset(f, 0, sizeof *f);
    f->t = t_board;
    if (!nav->have_pos)
        return 0;
    propagate_to(nav, t_board);
    double R[3][3], v[3];
    ned_matrix(nav->x, R);
    for (int i = 0; i < 3; i++)
        f->ecef[i] = nav->x[IP + i];
    soop_geodetic(f->ecef, &f->lat_deg, &f->lon_deg, &f->h_m);
    vel_at(nav, t_board, v);
    f->vn = (float)(v[0] + nav->x[IV]);
    f->ve = (float)(v[1] + nav->x[IV + 1]);
    f->vd = (float)(v[2] + nav->x[IV + 2]);
    double Pn[3][3];                              //r^T P R: position covariance in NED
    for (int a = 0; a < 3; a++)
        for (int b = 0; b < 3; b++) {
            double s = 0.0;
            for (int i = 0; i < 3; i++)
                for (int j = 0; j < 3; j++)
                    s += R[i][a] * nav->P[IP + i][IP + j] * R[j][b];
            Pn[a][b] = s;
        }
    const double tr = Pn[0][0] + Pn[1][1], det = Pn[0][0] * Pn[1][1] - Pn[0][1] * Pn[1][0];
    const double lmax = 0.5 * tr + sqrt(fmax(0.0, 0.25 * tr * tr - det));
    const double infl = sqrt(fmax(1.0, nav->nis_avg));   //the data disagree: say so
    f->hacc_m = (float)(sqrt(lmax) * infl);
    f->vacc_m = (float)(sqrt(fmax(0.0, Pn[2][2])) * infl);
    f->sacc_ms = (float)(sqrt(fmax(nav->P[IV][IV], nav->P[IV + 1][IV + 1])) * infl);
    f->nis = (float)nav->nis_avg;
    f->n_track = (uint8_t)nav->n_track;
    f->valid = nav->anchored && nav->have_clock && nav->have_time && nav->n_track > 0
               && t_board - nav->last_fused < nav->cfg.fix_max_age
               && f->hacc_m < nav->cfg.fix_max_hacc;
    return f->valid;
}
