//host harness for soop_max2112
#include <stdio.h>
#include <string.h>
#include "soop_max2112.h"

int main(void)
{
    char line[128];
    while (fgets(line, sizeof line, stdin)) {
        double lo, ref, out = 0.0;
        unsigned bbg, s1, s2;
        if (sscanf(line, "regs %lf %lf %u", &lo, &ref, &bbg) == 3) {
            uint8_t r[SOOP_MAX2112_NREGS];
            memset(r, 0, sizeof r);
            int rc = soop_max2112_regs(lo, ref, (uint8_t)bbg, r, &out);
            printf("%d", rc);
            for (int i = 0; i < SOOP_MAX2112_NREGS; i++) {
                printf(" %02x", r[i]);
            }
            printf(" %.6f\n", out);
        } else if (sscanf(line, "lock %x %x", &s1, &s2) == 2) {
            uint8_t vco, adc;
            int ok = soop_max2112_locked((uint8_t)s1, (uint8_t)s2, &vco, &adc);
            printf("%d %u %u\n", ok, vco, adc);
        }
    }
    return 0;
}
