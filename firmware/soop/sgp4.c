/* sgp4.c  -  Near-Earth SGP4 propagator, direct C port of Vallado 2006.
 *
 * This is a line-by-line transcription of the Python sgp4 library's
 * propagation.py (itself a faithful translation of Vallado's C++ reference).
 * Near-Earth only; deep-space branch is absent — see sgp4.h.
 *
 * 1.0 km position, 1.5 m/s velocity at ±3 days for Iridium NEXT.
 *             Derivation: 5 Hz Doppler at 1626.27 MHz => 0.92 m/s velocity
 *             tolerance; position tolerance ≈ v_tol × T_orbit / 2π ≈ 880 m.
 *             Gate uses 1.0 km / 1.5 m/s for headroom.
 *
 * double throughout.  H743 fpv5-d16 FPU handles double natively.
 *             Single precision degrades to ~10 km at 3 days for Iridium.
 *
 * TEME frame, km and km/s — same as Python sgp4.api.Satrec.
 */

#include "sgp4.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

/* ---- WGS-72 constants (Vallado uses WGS-72 for SGP4) ---- */
#define PI         3.14159265358979323846
#define TWOPI      (2.0 * PI)
#define DEG2RAD    (PI / 180.0)
#define X2O3       (2.0 / 3.0)
#define XKE        0.0743669161         /* sqrt(GM), (er)^1.5/min, WGS-72 */
#define J2         1.082616e-3
#define J3         (-2.53881e-6)
#define J4         (-1.65597e-6)
#define J3OJ2      (J3 / J2)
#define RE_KM      6378.135             /* earth equatorial radius, km WGS-72 */
#define VKMPERSEC  (RE_KM * XKE / 60.0)/* km/s per (er/min) */

/* ---- jday ---- */
double sgp4_jday(int yr, int mo, int day, int hr, int min, double sec)
{
    return 367.0 * yr
         - floor(7.0 * (yr + floor((mo + 9.0) / 12.0)) * 0.25)
         + floor(275.0 * mo / 9.0)
         + day + 1721013.5
         + ((sec / 60.0 + min) / 60.0 + hr) / 24.0;
}

/* ---- Parse packed TLE exponent field, e.g. " 27422-4" -> 2.7422e-5 ---- */
static double packed_exp(const char *s)
{
    while (*s == ' ') s++;
    double msign = 1.0;
    if      (*s == '-') { msign = -1.0; s++; }
    else if (*s == '+') { s++; }
    char mbuf[8]; int mi = 0;
    while (*s && *s != '-' && *s != '+' && mi < 6) mbuf[mi++] = *s++;
    mbuf[mi] = '\0';
    double mant = msign * atof(mbuf) * pow(10.0, -(double)mi);
    int esign = 1;
    if      (*s == '-') { esign = -1; s++; }
    else if (*s == '+') { s++; }
    int exp = 0;
    while (*s >= '0' && *s <= '9') exp = exp * 10 + (*s++ - '0');
    return mant * pow(10.0, esign * exp);
}

/* ---- sgp4_parse_tle ---- */
int sgp4_parse_tle(const char *l1, const char *l2, sgp4_tle_t *t)
{
    if (!l1 || !l2 || !t) return SGP4_ERR_PARSE;
    if (l1[0] != '1' || l2[0] != '2') return SGP4_ERR_PARSE;
    memset(t, 0, sizeof(*t));

    /* Line 1: epoch */
    int yr2; double epoch_day;
    if (sscanf(l1 + 18, "%2d%12lf", &yr2, &epoch_day) != 2) return SGP4_ERR_PARSE;
    int yr = (yr2 < 57) ? (2000 + yr2) : (1900 + yr2);
    double jd_jan0 = sgp4_jday(yr, 1, 0, 0, 0, 0.0);  /* JD of Dec 31.0 of yr-1 */
    t->epoch_jd      = jd_jan0;
    t->epoch_jd_frac = epoch_day;

    /* ndot/2 */
    { char buf[12]; strncpy(buf, l1 + 33, 10); buf[10] = '\0'; t->ndot = atof(buf); }
    /* nddot/6 packed */
    { char buf[10]; strncpy(buf, l1 + 44, 8); buf[8] = '\0'; t->nddot = packed_exp(buf); }
    /* bstar packed */
    { char buf[10]; strncpy(buf, l1 + 53, 8); buf[8] = '\0'; t->bstar = packed_exp(buf); }

    /* Line 2 */
    double inc_deg, raan_deg, ecc_raw, argp_deg, ma_deg, no_rev;
    if (sscanf(l2 + 8, "%8lf %8lf %7lf %8lf %8lf %11lf",
               &inc_deg, &raan_deg, &ecc_raw, &argp_deg, &ma_deg, &no_rev) != 6)
        return SGP4_ERR_PARSE;

    t->inclo    = inc_deg  * DEG2RAD;
    t->nodeo    = raan_deg * DEG2RAD;
    t->ecco     = ecc_raw * 1.0e-7;
    t->argpo    = argp_deg * DEG2RAD;
    t->mo       = ma_deg   * DEG2RAD;
    t->no_kozai = no_rev * TWOPI / 1440.0;   /* rev/day -> rad/min */
    return SGP4_OK;
}

/* ---- sgp4_init  (mirrors sgp4init + _initl from propagation.py) ---- */
int sgp4_init(const sgp4_tle_t *tle, sgp4_t *s)
{
    memset(s, 0, sizeof(*s));

    if (tle->ecco >= 1.0 || tle->ecco < 0.0) return SGP4_ERR_ECCEN;

    s->ecco       = tle->ecco;
    s->inclo      = tle->inclo;
    s->nodeo      = tle->nodeo;
    s->argpo      = tle->argpo;
    s->mo         = tle->mo;
    s->bstar      = tle->bstar;
    s->no_kozai   = tle->no_kozai;
    s->epoch_jd      = tle->epoch_jd;
    s->epoch_jd_frac = tle->epoch_jd_frac;

    /* ---- _initl: un-Kozai mean motion ---- */
    const double eccsq  = tle->ecco * tle->ecco;
    const double omeosq = 1.0 - eccsq;
    const double rteosq = sqrt(omeosq);
    const double cosio  = cos(tle->inclo);
    const double cosio2 = cosio * cosio;
    const double sinio  = sin(tle->inclo);

    double no;  /* un-Kozai'd mean motion */
    double ao;  /* semi-major axis after un-Kozai */
    {
        const double ak   = pow(XKE / tle->no_kozai, X2O3);
        const double d1   = 0.75 * J2 * (3.0 * cosio2 - 1.0) / (rteosq * omeosq);
        double del_  = d1 / (ak * ak);
        const double adel = ak * (1.0 - del_ * del_ - del_ *
                            (1.0/3.0 + 134.0 * del_ * del_ / 81.0));
        del_ = d1 / (adel * adel);
        no   = tle->no_kozai / (1.0 + del_);
        ao   = pow(XKE / no, X2O3);
    }

    /* Guard: near-Earth only (period < 225 min => no > 2π/225) */
    if (TWOPI / no >= 225.0) return SGP4_ERR_DEEP_SPACE;

    const double con42 = 1.0 - 5.0 * cosio2;
    const double con41 = -con42 - cosio2 - cosio2;   /* = 3*cosio2 - 1 */
    const double posq  = ao * ao * omeosq * omeosq;  /* (ao*beta0)^2 */
    const double rp    = ao * (1.0 - tle->ecco);
    const double pinvsq = 1.0 / posq;

    s->no   = no;
    s->a    = ao;
    s->alta = ao * (1.0 + tle->ecco) - 1.0;
    s->altp = rp - 1.0;
    s->perige = (rp - 1.0) * RE_KM;
    s->cosio  = cosio;
    s->sinio  = sinio;
    s->cosio2 = cosio2;
    s->con41  = con41;
    s->con42  = con42;
    s->x1mth2 = 1.0 - cosio2;
    s->x7thm1 = 7.0 * cosio2 - 1.0;

    /* ---- sgp4init near-Earth branch ---- */
    int isimp = 0;
    if (rp < 220.0 / RE_KM + 1.0) isimp = 1;

    double sfour  = 78.0 / RE_KM + 1.0;
    double qzms24 = pow((120.0 - 78.0) / RE_KM, 4.0);

    const double perige_km = s->perige;
    if (perige_km < 156.0) {
        sfour = perige_km - 78.0;
        if (sfour < 20.0) sfour = 20.0;
        const double qzms24temp = (120.0 - sfour) / RE_KM;
        qzms24 = qzms24temp * qzms24temp * qzms24temp * qzms24temp;
        sfour  = sfour / RE_KM + 1.0;
    }

    const double tsi    = 1.0 / (ao - sfour);
    s->eta = ao * tle->ecco * tsi;
    const double etasq  = s->eta * s->eta;
    const double eeta   = tle->ecco * s->eta;
    const double psisq  = fabs(1.0 - etasq);
    const double coef   = qzms24 * pow(tsi, 4.0);
    const double coef1  = coef / pow(psisq, 3.5);

    const double cc2 = coef1 * no *
        (ao * (1.0 + 1.5 * etasq + eeta * (4.0 + etasq)) +
         0.375 * J2 * tsi / psisq * con41 *
         (8.0 + 3.0 * etasq * (8.0 + etasq)));
    s->cc1 = tle->bstar * cc2;

    double cc3 = 0.0;
    if (tle->ecco > 1.0e-4)
        cc3 = -2.0 * coef * tsi * J3OJ2 * no * sinio / tle->ecco;

    s->x1mth2 = 1.0 - cosio2;
    s->cc4 = 2.0 * no * coef1 * ao * omeosq *
        (s->eta * (2.0 + 0.5 * etasq) + tle->ecco *
         (0.5 + 2.0 * etasq) - J2 * tsi / (ao * psisq) *
         (-3.0 * con41 * (1.0 - 2.0 * eeta + etasq * (1.5 - 0.5 * eeta)) +
          0.75 * s->x1mth2 *
          (2.0 * etasq - eeta * (1.0 + etasq)) * cos(2.0 * tle->argpo)));
    s->cc5 = 2.0 * coef1 * ao * omeosq *
        (1.0 + 2.75 * (etasq + eeta) + eeta * etasq);

    const double cosio4 = cosio2 * cosio2;
    const double temp1  = 1.5 * J2 * pinvsq * no;
    const double temp2  = 0.5 * temp1 * J2 * pinvsq;
    const double temp3  = -0.46875 * J4 * pinvsq * pinvsq * no;
    s->mdot    = no + 0.5 * temp1 * rteosq * con41 +
                 0.0625 * temp2 * rteosq * (13.0 - 78.0 * cosio2 + 137.0 * cosio4);
    s->omgdot  = -0.5 * temp1 * con42 +
                 0.0625 * temp2 * (7.0 - 114.0 * cosio2 + 395.0 * cosio4) +
                 temp3 * (3.0 - 36.0 * cosio2 + 49.0 * cosio4);
    const double xhdot1 = -temp1 * cosio;
    s->xnodot  = xhdot1 + (0.5 * temp2 * (4.0 - 19.0 * cosio2) +
                 2.0 * temp3 * (3.0 - 7.0 * cosio2)) * cosio;
    s->omgcof  = tle->bstar * cc3 * cos(tle->argpo);
    s->xmcof   = (tle->ecco > 1.0e-4) ? -X2O3 * coef * tle->bstar / eeta : 0.0;
    s->nodecf  = 3.5 * omeosq * xhdot1 * s->cc1;
    s->t2cof   = 1.5 * s->cc1;

    if (fabs(cosio + 1.0) > 1.5e-12)
        s->xlcof = -0.25 * J3OJ2 * sinio * (3.0 + 5.0 * cosio) / (1.0 + cosio);
    else
        s->xlcof = -0.25 * J3OJ2 * sinio * (3.0 + 5.0 * cosio) / 1.5e-12;
    s->aycof = -0.5 * J3OJ2 * sinio;

    const double delmotemp = 1.0 + s->eta * cos(tle->mo);
    s->delmo  = delmotemp * delmotemp * delmotemp;
    s->sinmao = sin(tle->mo);
    s->x7thm1 = 7.0 * cosio2 - 1.0;

    /* Higher-order drag terms (isimp == 0 branch) */
    if (!isimp) {
        const double cc1sq = s->cc1 * s->cc1;
        s->d2 = 4.0 * ao * tsi * cc1sq;
        const double temp = s->d2 * tsi * s->cc1 / 3.0;
        s->d3  = (17.0 * ao + sfour) * temp;
        s->d4  = 0.5 * temp * ao * tsi * (221.0 * ao + 31.0 * sfour) * s->cc1;
        s->t3cof = s->d2 + 2.0 * cc1sq;
        s->t4cof = 0.25 * (3.0 * s->d3 + s->cc1 * (12.0 * s->d2 + 10.0 * cc1sq));
        s->t5cof = 0.2  * (3.0 * s->d4 + 12.0 * s->cc1 * s->d3 +
                           6.0 * s->d2 * s->d2 +
                           15.0 * cc1sq * (2.0 * s->d2 + cc1sq));
    }
    s->isimp = isimp;
    return SGP4_OK;
}

/* ---- sgp4_propagate  (mirrors sgp4() in propagation.py, near-Earth) ---- */
int sgp4_propagate(const sgp4_t *s, double tsince, double r_km[3], double v_km_s[3])
{
    const double t  = tsince;
    const double t2 = t * t;

    /* --- secular gravity and atmospheric drag --- */
    const double xmdf   = s->mo    + s->mdot   * t;
    const double argpdf = s->argpo + s->omgdot  * t;
    const double nodedf = s->nodeo + s->xnodot  * t;
    double argpm = argpdf;
    double mm    = xmdf;
    double nodem = nodedf + s->nodecf * t2;
    double tempa = 1.0 - s->cc1 * t;
    double tempe = s->bstar * s->cc4 * t;
    double templ = s->t2cof * t2;

    if (!s->isimp) {
        const double t3     = t2 * t;
        const double t4     = t3 * t;
        const double delomg = s->omgcof * t;
        const double delmtemp = 1.0 + s->eta * cos(xmdf);
        const double delm   = s->xmcof *
                              (delmtemp * delmtemp * delmtemp - s->delmo);
        const double temp   = delomg + delm;
        mm    = xmdf + temp;
        argpm = argpdf - temp;
        tempa = tempa - s->d2 * t2 - s->d3 * t3 - s->d4 * t4;
        tempe = tempe + s->bstar * s->cc5 * (sin(mm) - s->sinmao);
        templ = templ + s->t3cof * t3 + t4 * (s->t4cof + t * s->t5cof);
    }

    const double nm  = s->no;      /* near-Earth: no dndt */
    const double em  = s->ecco;
    /* (deep-space dspace() call omitted — near-Earth only) */

    if (nm <= 0.0) return SGP4_ERR_DECAY;

    const double am = pow(XKE / nm, X2O3) * tempa * tempa;
    /* nm not updated for near-Earth */
    double emv = em - tempe;
    if (emv >= 1.0 || emv < -0.001) return SGP4_ERR_DECAY;
    if (emv < 1.0e-6) emv = 1.0e-6;

    mm = mm + s->no * templ;
    const double xlm  = mm + argpm + nodem;
    /* (emsq unused in near-Earth path; left commented to match Python variable list) */

    nodem = fmod(nodem, TWOPI);
    if (nodem < 0.0) nodem += TWOPI;
    argpm = fmod(argpm, TWOPI);
    const double xlmmod = fmod(xlm, TWOPI);
    mm    = fmod(xlmmod - argpm - nodem, TWOPI);
    if (mm < 0.0) mm += TWOPI;

    /* --- long-period periodics (near-Earth: inclm unchanged) --- */
    const double ep    = emv;
    const double xincp = s->inclo;
    const double argpp = argpm;
    const double nodep = nodem;
    const double mp    = mm;
    const double sinip = s->sinio;
    const double cosip = s->cosio;

    const double axnl = ep * cos(argpp);
    const double temp_lp = 1.0 / (am * (1.0 - ep * ep));
    const double aynl = ep * sin(argpp) + temp_lp * s->aycof;
    const double xl   = mp + argpp + nodep + temp_lp * s->xlcof * axnl;

    /* --- Kepler iteration --- */
    double u    = fmod(xl - nodep, TWOPI);
    if (u < 0.0) u += TWOPI;
    double eo1  = u, tem5 = 9999.9;
    double sineo1 = 0.0, coseo1 = 0.0;
    for (int ktr = 1; ktr <= 10 && fabs(tem5) >= 1.0e-12; ktr++) {
        sineo1 = sin(eo1); coseo1 = cos(eo1);
        tem5 = 1.0 - coseo1 * axnl - sineo1 * aynl;
        tem5 = (u - aynl * coseo1 + axnl * sineo1 - eo1) / tem5;
        if (fabs(tem5) >= 0.95) tem5 = (tem5 > 0.0) ? 0.95 : -0.95;
        eo1 += tem5;
    }

    /* --- short-period preliminary --- */
    const double ecose = axnl * coseo1 + aynl * sineo1;
    const double esine = axnl * sineo1 - aynl * coseo1;
    const double el2   = axnl * axnl + aynl * aynl;
    const double pl    = am * (1.0 - el2);
    if (pl < 0.0) return SGP4_ERR_DECAY;

    const double rl    = am * (1.0 - ecose);
    const double rdotl = sqrt(am) * esine / rl;
    const double rvdotl = sqrt(pl) / rl;
    const double betal  = sqrt(1.0 - el2);
    const double temp_s = esine / (1.0 + betal);
    const double sinu   = am / rl * (sineo1 - aynl - axnl * temp_s);
    const double cosu   = am / rl * (coseo1 - axnl + aynl * temp_s);
    const double su     = atan2(sinu, cosu);
    const double sin2u  = (cosu + cosu) * sinu;
    const double cos2u  = 1.0 - 2.0 * sinu * sinu;
    const double temp1v = 0.5 * J2 / pl;
    const double temp2v = temp1v / pl;

    /* --- short-period corrections (Vallado 2006 Eq 44-50) --- */
    const double mrt  = rl  * (1.0 - 1.5 * temp2v * betal * s->con41) +
                        0.5 * temp1v * s->x1mth2 * cos2u;
    const double su_c = su - 0.25 * temp2v * s->x7thm1 * sin2u;
    const double xnode_c = nodep + 1.5 * temp2v * cosip * sin2u;
    const double xinc_c  = xincp + 1.5 * temp2v * cosip * sinip * cos2u;
    const double mvt  = rdotl  - nm * temp1v * s->x1mth2 * sin2u  / XKE;
    const double rvdot = rvdotl + nm * temp1v *
                         (s->x1mth2 * cos2u + 1.5 * s->con41) / XKE;

    if (mrt < 1.0) return SGP4_ERR_DECAY;

    /* --- orientation vectors --- */
    const double sinsu = sin(su_c);
    const double cossu = cos(su_c);
    const double snod  = sin(xnode_c);
    const double cnod  = cos(xnode_c);
    const double sini  = sin(xinc_c);
    const double cosi  = cos(xinc_c);
    const double xmx   = -snod * cosi;
    const double xmy   =  cnod * cosi;
    const double ux    = xmx * sinsu + cnod * cossu;
    const double uy    = xmy * sinsu + snod * cossu;
    const double uz    = sini * sinsu;
    const double vx    = xmx * cossu - cnod * sinsu;
    const double vy    = xmy * cossu - snod * sinsu;
    const double vz    = sini * cossu;

    /* --- position (km) and velocity (km/s) --- */
    const double mr = mrt * RE_KM;
    r_km[0] = mr * ux;
    r_km[1] = mr * uy;
    r_km[2] = mr * uz;
    v_km_s[0] = (mvt * ux + rvdot * vx) * VKMPERSEC;
    v_km_s[1] = (mvt * uy + rvdot * vy) * VKMPERSEC;
    v_km_s[2] = (mvt * uz + rvdot * vz) * VKMPERSEC;

    return SGP4_OK;
}
