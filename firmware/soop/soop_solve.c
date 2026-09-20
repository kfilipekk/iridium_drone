/* soop_solve.c - see soop_solve.h. Numerically mirrors tools/soop_solver.py:
 *
 *   df = f_tx * (-rdot/c + delta)      carried as clock_hz = f_tx*delta, in Hz
 *   d(df)/d(r_rx) = (f_tx/c) * v^T (I - u u^T) / rho
 *   d(df)/d(clock_hz) = 1
 *
 * The clock is carried in Hz, not as a fraction, for the reason recorded in the Python
 * header: as a fraction its Jacobian column is ~1.6e9 while the position columns are
 * ~1e-4, and the normal matrix spans 23 orders of magnitude - the position is then
 * numerically invisible next to the clock.
 */
#include "soop_solve.h"
#include <math.h>

double soop_predict_df(const double r[3], const double v[3], const double rx[3],
                       double clock_hz)
{
    const double d0 = r[0] - rx[0], d1 = r[1] - rx[1], d2 = r[2] - rx[2];
    const double rho = sqrt(d0 * d0 + d1 * d1 + d2 * d2);
    const double u0 = d0 / rho, u1 = d1 / rho, u2 = d2 / rho;
    const double rdot = v[0] * u0 + v[1] * u1 + v[2] * u2;
    return SOOP_F_IRIDIUM * (-rdot / SOOP_CLIGHT) + clock_hz;
}

/* Gauss-Jordan with partial pivoting on a 4x4 system. */
static int solve4(double A[4][4], double b[4], double x[4])
{
    for (int col = 0; col < 4; col++) {
        int piv = col;
        double best = fabs(A[col][col]);
        for (int r = col + 1; r < 4; r++) {
            const double a = fabs(A[r][col]);
            if (a > best) { best = a; piv = r; }
        }
        if (best < 1e-12)
            return -1;                        /* singular: report, do not invent */
        if (piv != col) {
            for (int c = 0; c < 4; c++) {
                const double t = A[col][c]; A[col][c] = A[piv][c]; A[piv][c] = t;
            }
            const double t = b[col]; b[col] = b[piv]; b[piv] = t;
        }
        const double d = A[col][col];
        for (int c = col; c < 4; c++) A[col][c] /= d;
        b[col] /= d;
        for (int r = 0; r < 4; r++) {
            if (r == col) continue;
            const double f = A[r][col];
            if (f == 0.0) continue;
            for (int c = col; c < 4; c++) A[r][c] -= f * A[col][c];
            b[r] -= f * b[col];
        }
    }
    for (int i = 0; i < 4; i++) x[i] = b[i];
    return 0;
}

int soop_solve(const soop_obs_t *obs, size_t n, const double guess[4],
               soop_state_t *out, double *resid_rms)
{
    double x[4] = { guess[0], guess[1], guess[2], guess[3] };

    for (int iter = 0; iter < SOOP_MAX_ITERS; iter++) {
        double A[4][4], b[4], H[4];
        for (int i = 0; i < 4; i++) {
            b[i] = 0.0;
            for (int j = 0; j < 4; j++) A[i][j] = 0.0;
        }
        for (size_t k = 0; k < n; k++) {
            const double *rs = obs[k].r, *vs = obs[k].v;
            const double d0 = rs[0] - x[0], d1 = rs[1] - x[1], d2 = rs[2] - x[2];
            const double rho = sqrt(d0 * d0 + d1 * d1 + d2 * d2);
            const double u0 = d0 / rho, u1 = d1 / rho, u2 = d2 / rho;
            const double vdotu = vs[0] * u0 + vs[1] * u1 + vs[2] * u2;
            const double y = obs[k].df - (SOOP_F_IRIDIUM * (-vdotu / SOOP_CLIGHT) + x[3]);
            H[0] = (SOOP_F_IRIDIUM / SOOP_CLIGHT) * (vs[0] - vdotu * u0) / rho;
            H[1] = (SOOP_F_IRIDIUM / SOOP_CLIGHT) * (vs[1] - vdotu * u1) / rho;
            H[2] = (SOOP_F_IRIDIUM / SOOP_CLIGHT) * (vs[2] - vdotu * u2) / rho;
            H[3] = 1.0;
            for (int i = 0; i < 4; i++) {
                b[i] += H[i] * y;
                for (int j = 0; j < 4; j++) A[i][j] += H[i] * H[j];
            }
        }
        double step[4];
        if (solve4(A, b, step) != 0)
            return -1;
        for (int i = 0; i < 4; i++) x[i] += step[i];
        double m = 0.0;
        for (int i = 0; i < 3; i++) { const double a = fabs(step[i]); if (a > m) m = a; }
        if (m < SOOP_TOL)
            break;
    }

    double ss = 0.0;
    for (size_t k = 0; k < n; k++) {
        const double r = obs[k].df - soop_predict_df(obs[k].r, obs[k].v, x, x[3]);
        ss += r * r;
    }
    if (resid_rms)
        *resid_rms = sqrt(ss / (double)n);
    out->pos[0] = x[0];
    out->pos[1] = x[1];
    out->pos[2] = x[2];
    out->clock_hz = x[3];
    return 0;
}
