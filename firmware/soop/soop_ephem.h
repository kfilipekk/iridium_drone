//soop_ephem.h - Iridium satellite states in the Earth-fixed frame
#ifndef SOOP_EPHEM_H
#define SOOP_EPHEM_H

#include <stdint.h>
#include "sgp4.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SOOP_J2000_JD      2451545.0
#define SOOP_OMEGA_EARTH   7.2921150e-5     //rad/s

typedef struct {
    uint32_t norad;
    double   epoch_s;       //TLE epoch, UTC s since J2000.0
    sgp4_t   sgp;
    char     name[25];
} soop_sat_t;

//parse a catalogue in the usual three-line form
int soop_ephem_parse(const char *text, soop_sat_t *out, int max_sats);

//Greenwich mean sidereal time (IAU 1982) at UT1 seconds since J2000.0
double soop_gmst(double t_ut1);

//TEME -> ECEF at sidereal angle theta; metres in, metres out
void soop_teme_to_ecef(const double rt[3], const double vt[3], double theta,
                       double r[3], double v[3]);

//satellite position (m) and velocity (m/s) in ECEF at UTC time t
int soop_ephem_state(const soop_sat_t *s, double t_utc, double dut1, double r[3], double v[3]);

//Julian date (split, as SGP4 carries it) -> UTC seconds since J2000.0
double soop_jd_to_j2000(double jd, double jd_frac);

#ifdef __cplusplus
}
#endif

#endif //SOOP_EPHEM_H
