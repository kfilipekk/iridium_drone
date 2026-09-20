//soop_solve.h - the Doppler least-squares solve, in C, for the H743
#ifndef SOOP_SOLVE_H
#define SOOP_SOLVE_H

#include <stddef.h>

#define SOOP_F_IRIDIUM 1626270000.0   //Hz, Iridium Ring Alert
#define SOOP_CLIGHT    299792458.0    //m/s
#define SOOP_MAX_ITERS 40
#define SOOP_TOL       1e-4           //m, convergence on the position step

typedef struct {
    double r[3];      //satellite position, ECEF, m
    double v[3];      //satellite velocity, ECEF, m/s
    double df;        //measured carrier offset, Hz
} soop_obs_t;

typedef struct {
    double pos[3];    //receiver position, ECEF, m
    double clock_hz;  //receiver clock offset expressed at the carrier, Hz
} soop_state_t;

//predicted carrier offset for one observation at receiver position rx
double soop_predict_df(const double r[3], const double v[3], const double rx[3],
                       double clock_hz);

//Gauss-Newton over position and clock
int soop_solve(const soop_obs_t *obs, size_t n, const double guess[4],
               soop_state_t *out, double *resid_rms);

#endif //SOOP_SOLVE_H
