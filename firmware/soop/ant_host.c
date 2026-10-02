//host harness for soop_ant: reads "t ma fault" lines
#include <stdio.h>
#include <string.h>
#include "soop_ant.h"

int main(void)
{
    char line[128];
    soop_ant_cfg_t cfg;
    soop_ant_t a;
    int started = 0;

    soop_ant_default_cfg(&cfg);
    while (fgets(line, sizeof line, stdin)) {
        double t;
        float ma;
        int fault;
        if (!started && strncmp(line, "cfg", 3) == 0) {
            printf("open_ma %g\nshort_ma %g\nsettle_s %g\nretry_after_s %g\nretry_off_s %g\n",
                   cfg.open_ma, cfg.short_ma, cfg.settle_s, cfg.retry_after_s,
                   cfg.retry_off_s);
            return 0;
        }
        if (!started && strncmp(line, "off", 3) == 0) {
            cfg.feed_enabled = 0;
            continue;
        }
        if (sscanf(line, "%lf %f %d", &t, &ma, &fault) != 3) {
            continue;
        }
        if (!started) {
            soop_ant_init(&a, &cfg, t);
            started = 1;
        }
        int en = soop_ant_step(&a, t, ma, fault);
        printf("%.2f %s %d\n", t, soop_ant_name(a.state), en);
    }
    return 0;
}
