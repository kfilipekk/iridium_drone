//soop_max2112.c - see soop_max2112.h
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize ("no-single-precision-constant")
#endif
typedef char soop_max2112_needs_double[((long)1125000001.0 == 1125000001L) ? 1 : -1];
#include "soop_max2112.h"

#include <math.h>

int soop_max2112_regs(double lo_hz, double ref_hz, uint8_t bbg,
                      uint8_t regs[SOOP_MAX2112_NREGS], double *lo_out)
{
    //round the whole ratio to the 2^-20 grid first
    const double steps = floor(lo_hz / ref_hz * 1048576.0 + 0.5);
    const uint32_t N = (uint32_t)(steps / 1048576.0);
    const uint32_t F = (uint32_t)(steps - (double)N * 1048576.0);

    if (!(lo_hz > 0.0) || N < SOOP_MAX2112_N_MIN || N > SOOP_MAX2112_N_MAX) {
        return -1;
    }
    regs[0x00] = (uint8_t)(0x80 | ((N >> 8) & 0x7F));    //FRAC = 1, N[14:8]
    regs[0x01] = (uint8_t)(N & 0xFF);                    //n[7:0]
    regs[0x02] = (uint8_t)(0x10 | ((F >> 16) & 0x0F));   //CPMP = 00, CPLIN = 01, F[19:16]
    regs[0x03] = (uint8_t)((F >> 8) & 0xFF);             //f[15:8]
    regs[0x04] = (uint8_t)(F & 0xFF);                    //f[7:0] - loading it starts VAS
    regs[0x05] = 0x01;                                   //XD = /1, R = 1
    //D24 = 0 divides the VCO by 2 for an LO at or above 1125 MHz, 1 by 4 below it
    regs[0x06] = (uint8_t)(lo_hz < 1125.0e6 ? 0x80 : 0x00);
    regs[0x07] = (uint8_t)((0x19 << 3) | 0x04);          //VCO start 11001, VAS = 1
    regs[0x08] = 12;                                     //LPF: 4 MHz, the minimum
    regs[0x09] = (uint8_t)(bbg & 0x0F);                  //STBY = 0, PWDN = 0, BBG
    regs[0x0A] = 0x00;                                   //everything powered
    regs[0x0B] = 0x08;                                   //CPTST = 000, TURBO = 1, LDMUX = 000
    if (lo_out) {
        *lo_out = ref_hz * ((double)N + (double)F / 1048576.0);
    }
    return 0;
}

int soop_max2112_locked(uint8_t s1, uint8_t s2, uint8_t *vco, uint8_t *adc)
{
    const int vas_done = (s1 & 0x20) && (s1 & 0x40);    //VASE and VASA
    const int ld = (s1 & 0x10) != 0;
    const uint8_t a = s2 & 0x07;
    if (vco) {
        *vco = (uint8_t)(s2 >> 3);
    }
    if (adc) {
        *adc = a;
    }
    return vas_done && ld && a != 0 && a != 7;
}
