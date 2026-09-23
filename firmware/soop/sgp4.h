/* sgp4.h  -  Near-Earth SGP4 for the NAVCORE H743 board.
 *
 * The Doppler solve (soop_solve.c) takes satellite ECEF position and
 * velocity as input.  On the aircraft those come from propagating a TLE with SGP4 at
 * the current time.  This is that propagator.
 *
 * Near-Earth only.  Iridium NEXT orbits at ~780 km altitude (mean motion ≈
 * 14.34 rev/day, eccentricity < 1e-3).  Deep-space resonance effects appear only for
 * periods > 225 min (mean motion < 0.0042 rad/min), so the deep-space branch of SGP4
 * is dead code for this constellation and is intentionally absent.  Calling sgp4_init()
 * on a TLE that would need the deep-space branch returns SGP4_ERR_DEEP_SPACE so the
 * caller can reject it rather than silently compute garbage.
 *
 * The algorithm runs in double throughout.  Single precision accumulates
 * ~10 km error at 3 days for Iridium-class orbits, which is far outside the tolerance
 * derived in firmware/soop/sgp4.c.  The H743 FPU covers double (fpv5-d16), so double
 * costs only a small latency penalty versus single and is worth it.
 *
 * tolerance rationale (derived in sgp4_host_test.py and recorded here).
 *   5 Hz Doppler precision (the solve requirement) ⇒ velocity tolerance 0.92 m/s
 *   (c × 5 / f_Iridium).  Position error maps to velocity error at the orbital period
 *   timescale: ≈ pos_err × 2π / T_orbit.  For T_orbit ≈ 6000 s the position tolerance
 *   is ≈ 880 m.  We gate against 1.0 km and 1.5 m/s at ±3 days to give headroom.
 *
 * No malloc, no libc beyond <math.h>.  Input is a parsed TLE
 * (sgp4_tle_t), output is ECEF km / km·s⁻¹ matching the Python sgp4.api.Satrec
 * convention.
 *
 * Vallado et al. 2006, "Revisiting Spacetrack Report #3", AIAA 2006-6753.
 */
#ifndef SGP4_H
#define SGP4_H

#ifdef __cplusplus
extern "C" {
#endif

/* Parsed TLE elements - fill by calling sgp4_parse_tle(). */
typedef struct {
    double epoch_jd;        /* Julian date of epoch (integer + fraction) */
    double epoch_jd_frac;
    double no_kozai;        /* mean motion, rad/min (Kozai) */
    double ecco;            /* eccentricity */
    double inclo;           /* inclination, rad */
    double mo;              /* mean anomaly at epoch, rad */
    double argpo;           /* argument of perigee at epoch, rad */
    double nodeo;           /* right ascension of ascending node at epoch, rad */
    double bstar;           /* drag term (B*), 1/earth_radii */
    double ndot;            /* first derivative of mean motion / 2, rad/min^2 */
    double nddot;           /* second derivative of mean motion / 6, rad/min^3 */
} sgp4_tle_t;

/* Pre-computed internal state - fill by calling sgp4_init(). */
typedef struct {
    /* Elements kept from TLE */
    double ecco, inclo, nodeo, argpo, mo;
    double bstar, no_kozai;
    double epoch_jd, epoch_jd_frac;

    /* Derived quantities computed once at init */
    double no;              /* mean motion, rad/min (un-Kozai'd Brouwer) */
    double a;               /* semi-major axis, earth_radii */
    double alta, altp;      /* apogee/perigee altitude above surface, earth_radii */
    double perige;          /* perigee altitude, km */
    int    isimp;           /* 1 = simplified drag (low perigee) */

    /* Secular drag terms */
    double cc1, cc4, cc5;
    double d2, d3, d4;
    double omgcof, xmcof;   /* omgcof = bstar*cc3*cos(argpo), xmcof for delm */
    double nodecf;           /* nodal secular rate correction */
    double t2cof, t3cof, t4cof, t5cof;

    /* Secular gravity rates */
    double mdot, omgdot, xnodot;

    /* Short-period / orientation */
    double x1mth2, x7thm1;
    double xlcof, aycof;
    double cosio, sinio, cosio2;
    double con41, con42;

    /* Long-period periodics at epoch */
    double delmo, sinmao, eta;
} sgp4_t;

/* Return codes */
#define SGP4_OK           0
#define SGP4_ERR_PARSE    (-1)   /* bad TLE line format */
#define SGP4_ERR_ECCEN    (-2)   /* eccentricity out of range */
#define SGP4_ERR_DEEP_SPACE (-3) /* near-Earth only: period > 225 min */
#define SGP4_ERR_DECAY    (-4)   /* satellite decayed (r < 1 earth radii) */
#define SGP4_ERR_SINGULAR (-5)   /* singular Kepler loop */

/*
 * Parse a three-line TLE (name line optional, pass null; line1 and line2 required).
 * Does not compute derived quantities - call sgp4_init() next.
 * Returns SGP4_OK or SGP4_ERR_PARSE.
 */
int sgp4_parse_tle(const char *line1, const char *line2, sgp4_tle_t *tle);

/*
 * Initialise a propagator from a parsed TLE.  Must be called before sgp4_propagate().
 * Returns SGP4_OK, SGP4_ERR_DEEP_SPACE, or SGP4_ERR_ECCEN.
 */
int sgp4_init(const sgp4_tle_t *tle, sgp4_t *s);

/*
 * Propagate to time tsince minutes after TLE epoch.
 * r_km[3]  : ECEF position, km  (same frame as Python sgp4.api.Satrec)
 * v_km_s[3]: ECEF velocity, km/s
 * Returns SGP4_OK, SGP4_ERR_DECAY, or SGP4_ERR_SINGULAR.
 */
int sgp4_propagate(const sgp4_t *s, double tsince, double r_km[3], double v_km_s[3]);

/* Convenience: Julian date from calendar date. */
double sgp4_jday(int year, int mon, int day, int hr, int minute, double sec);

#ifdef __cplusplus
}
#endif

#endif /* SGP4_H */
