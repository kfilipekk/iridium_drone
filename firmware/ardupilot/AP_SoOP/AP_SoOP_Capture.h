//AP_SoOP_Capture - the MAX2112's I and Q, sampled together, into memory
#pragma once

#include <AP_HAL/AP_HAL.h>

#ifndef SOOP_CAPTURE_RAW_HZ
#define SOOP_CAPTURE_RAW_HZ 1000000U
#endif
#define SOOP_CAPTURE_OVS    2U
#define SOOP_CAPTURE_BLOCK  4096U        //samples per half-buffer: 8.2 ms at 500 kSPS

class AP_SoOP_Capture
{
public:
    //true if this build and board can capture at all
    static bool supported();

    bool start(bool swap_iq);
    void stop();

    //wait up to timeout_ms for the next half-buffer
    bool next_block(int16_t *iq, uint64_t &first_sample, uint32_t timeout_ms);

    uint64_t start_us() const { return _start_us; }      //board time of sample 0
    uint32_t overruns() const { return _overruns; }

private:
    uint64_t _start_us;
    uint32_t _overruns;
    uint64_t _next_block;
    bool     _swap;
};
