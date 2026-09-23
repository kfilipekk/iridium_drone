//sgp4.h - Near-Earth SGP4 for the NAVCORE H743 board
#ifndef SGP4_H
#define SGP4_H

#ifdef __cplusplus
extern "C" {
#endif

//parsed TLE elements - fill by calling sgp4_parse_tle()
typedef struct {
    double epoch_jd;        //Julian date of epoch (integer + fraction)
    double epoch_jd_frac;
    double no_kozai;        //mean motion, rad/min (Kozai)
    double ecco;            //eccentricity
    double inclo;           //inclination, rad
    double mo;              //mean anomaly at epoch, rad
    double argpo;           //argument of perigee at epoch, rad
    double nodeo;           //right ascension of ascending node at epoch, rad
    double bstar;           //drag term (B*), 1/earth_radii
    double ndot;            //first derivative of mean motion / 2, rad/min^2
    double nddot;           //second derivative of mean motion / 6, rad/min^3
} sgp4_tle_t;

//pre-computed internal state - fill by calling sgp4_init()
typedef struct {
    //elements kept from TLE
    double ecco, inclo, nodeo, argpo, mo;
    double bstar, no_kozai;
    double epoch_jd, epoch_jd_frac;

    //derived quantities computed once at init
    double no;              //mean motion, rad/min (un-Kozai'd Brouwer)
    double a;               //semi-major axis, earth_radii
    double alta, altp;      //apogee/perigee altitude above surface, earth_radii
    double perige;          //perigee altitude, km
    int    isimp;           //1 = simplified drag (low perigee)

    //secular drag terms
    double cc1, cc4, cc5;
    double d2, d3, d4;
    double omgcof, xmcof;   //omgcof = bstar*cc3*cos(argpo), xmcof for delm
    double nodecf;           //nodal secular rate correction
    double t2cof, t3cof, t4cof, t5cof;

    //secular gravity rates
    double mdot, omgdot, xnodot;

    //short-period / orientation
    double x1mth2, x7thm1;
    double xlcof, aycof;
    double cosio, sinio, cosio2;
    double con41, con42;

    //long-period periodics at epoch
    double delmo, sinmao, eta;
} sgp4_t;

//return codes
#define SGP4_OK           0
#define SGP4_ERR_PARSE    (-1)   //bad TLE line format
#define SGP4_ERR_ECCEN    (-2)   //eccentricity out of range
#define SGP4_ERR_DEEP_SPACE (-3) //near-Earth only: period > 225 min
#define SGP4_ERR_DECAY    (-4)   //satellite decayed (r < 1 earth radii)
#define SGP4_ERR_SINGULAR (-5)   //singular Kepler loop

//parse a three-line TLE (name line optional, pass null; line1 and line2 required)
int sgp4_parse_tle(const char *line1, const char *line2, sgp4_tle_t *tle);

//Initialise a propagator from a parsed TLE
int sgp4_init(const sgp4_tle_t *tle, sgp4_t *s);

//propagate to time tsince minutes after TLE epoch
int sgp4_propagate(const sgp4_t *s, double tsince, double r_km[3], double v_km_s[3]);

//convenience: Julian date from calendar date
double sgp4_jday(int year, int mon, int day, int hr, int minute, double sec);

#ifdef __cplusplus
}
#endif

#endif //SGP4_H
