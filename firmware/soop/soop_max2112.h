//soop_max2112 - the tuner's (U13) register image and status decode
#ifndef SOOP_MAX2112_H
#define SOOP_MAX2112_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SOOP_MAX2112_NREGS 12
#define SOOP_MAX2112_N_MIN 19
#define SOOP_MAX2112_N_MAX 251

//the write image for registers 0x00-0x0B
int soop_max2112_regs(double lo_hz, double ref_hz, uint8_t bbg,
                      uint8_t regs[SOOP_MAX2112_NREGS], double *lo_out);

//status bytes 0x0C/0x0D
int soop_max2112_locked(uint8_t s1, uint8_t s2, uint8_t *vco, uint8_t *adc);

#ifdef __cplusplus
}
#endif

#endif
