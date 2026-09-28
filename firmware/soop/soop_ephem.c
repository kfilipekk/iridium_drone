//soop_ephem.c - see soop_ephem.h
//ArduPilot compiles every source with -fsingle-precision-constant
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize ("no-single-precision-constant")
#endif
typedef char soop_needs_double_constants[((long)299792458.0 == 299792458L) ? 1 : -1];
#include "soop_ephem.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define PI 3.14159265358979323846

double soop_jd_to_j2000(double jd, double jd_frac)
{
    return ((jd - SOOP_J2000_JD) + jd_frac) * 86400.0;
}

double soop_gmst(double t_ut1)
{
    const double d = t_ut1 / 86400.0;
    const double T = d / 36525.0;
    double g = 280.46061837 + 360.98564736629 * d + 0.000387933 * T * T
               - T * T * T / 38710000.0;
    g = fmod(g, 360.0);
    if (g < 0.0)
        g += 360.0;
    return g * PI / 180.0;
}

void soop_teme_to_ecef(const double rt[3], const double vt[3], double theta,
                       double r[3], double v[3])
{
    const double c = cos(theta), s = sin(theta);
    r[0] = c * rt[0] + s * rt[1];
    r[1] = -s * rt[0] + c * rt[1];
    r[2] = rt[2];
    //the frame turns under the satellite: v_ecef = R v_teme - omega x r_ecef
    v[0] = c * vt[0] + s * vt[1] + SOOP_OMEGA_EARTH * r[1];
    v[1] = -s * vt[0] + c * vt[1] - SOOP_OMEGA_EARTH * r[0];
    v[2] = vt[2];
}

int soop_ephem_state(const soop_sat_t *s, double t_utc, double dut1, double r[3], double v[3])
{
    double rk[3], vk[3], rt[3], vt[3];
    const double tsince = (t_utc - s->epoch_s) / 60.0;
    const int e = sgp4_propagate(&s->sgp, tsince, rk, vk);
    if (e != SGP4_OK)
        return e;
    for (int i = 0; i < 3; i++) {
        rt[i] = rk[i] * 1000.0;
        vt[i] = vk[i] * 1000.0;
    }
    soop_teme_to_ecef(rt, vt, soop_gmst(t_utc + dut1), r, v);
    return 0;
}

//copy one line of text (without its terminator) into buf
static const char *take_line(const char *p, char *buf, size_t n)
{
    size_t k = 0;
    while (*p && *p != '\n' && *p != '\r') {
        if (k + 1 < n)
            buf[k++] = *p;
        p++;
    }
    buf[k] = '\0';
    while (*p == '\n' || *p == '\r')
        p++;
    return p;
}

int soop_ephem_parse(const char *text, soop_sat_t *out, int max_sats)
{
    char prev[96] = "", line[96], l2[96];
    int n = 0;
    const char *p = text;
    while (*p && n < max_sats) {
        p = take_line(p, line, sizeof line);
        if (line[0] == '1' && line[1] == ' ') {
            p = take_line(p, l2, sizeof l2);
            if (!(l2[0] == '2' && l2[1] == ' '))
                continue;
            sgp4_tle_t tle;
            soop_sat_t *s = &out[n];
            if (sgp4_parse_tle(line, l2, &tle) != SGP4_OK || sgp4_init(&tle, &s->sgp) != SGP4_OK)
                continue;
            s->norad = (uint32_t)strtol(line + 2, NULL, 10);
            s->epoch_s = soop_jd_to_j2000(tle.epoch_jd, tle.epoch_jd_frac);
            size_t k = 0;
            if (prev[0] != '1' && prev[0] != '2' && prev[0] != '#')
                for (; k < sizeof s->name - 1 && prev[k]; k++)
                    s->name[k] = prev[k];
            while (k > 0 && s->name[k - 1] == ' ')
                k--;
            s->name[k] = '\0';
            n++;
            prev[0] = '\0';
        } else {
            memcpy(prev, line, sizeof prev);
        }
    }
    return n;
}
