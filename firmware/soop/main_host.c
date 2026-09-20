/* main_host.c - run the on-board solver on a desktop, on an observation file produced by
 * `python3 tools/soop_solver.py --emit-obs file`. This exists so the C solver can be
 * checked against the Python reference on identical inputs (tools/check_soop_c.py); it
 * is not the flight entry point - that is the hardware glue the firmware still needs.
 *
 *   ./soop_host obs.txt gx gy gz gc
 */
#include "soop_solve.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    if (argc < 6) {                       /* program + obs + 4-element guess */
        fprintf(stderr, "usage: %s obs.txt gx gy gz gc\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "r");
    if (!f) { perror("obs"); return 2; }

    size_t n = 0;
    if (fscanf(f, "%zu", &n) != 1 || n == 0) {
        fprintf(stderr, "bad observation header\n");
        fclose(f);
        return 2;
    }
    soop_obs_t *obs = malloc(n * sizeof(*obs));
    if (!obs) { fclose(f); return 2; }
    for (size_t i = 0; i < n; i++) {
        if (fscanf(f, "%lf %lf %lf %lf %lf %lf %lf",
                   &obs[i].r[0], &obs[i].r[1], &obs[i].r[2],
                   &obs[i].v[0], &obs[i].v[1], &obs[i].v[2], &obs[i].df) != 7) {
            fprintf(stderr, "bad observation line %zu\n", i);
            free(obs);
            fclose(f);
            return 2;
        }
    }
    fclose(f);

    const double guess[4] = { atof(argv[2]), atof(argv[3]), atof(argv[4]), atof(argv[5]) };
    soop_state_t s;
    double rms = 0.0;
    if (soop_solve(obs, n, guess, &s, &rms) != 0) {
        printf("singular\n");
        free(obs);
        return 1;
    }
    printf("solution %.9f %.9f %.9f %.9f\n", s.pos[0], s.pos[1], s.pos[2], s.clock_hz);
    printf("resid_rms %.6f\n", rms);
    free(obs);
    return 0;
}
