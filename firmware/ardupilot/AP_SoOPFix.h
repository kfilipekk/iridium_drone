//in-process hand-off for an on-board Doppler fix
#pragma once

#include <AP_HAL/AP_HAL.h>

class AP_SoOPFix
{
public:
    static AP_SoOPFix *get_singleton();

    struct fix_t {
        double   lat_deg;
        double   lon_deg;
        float    alt_m;          //AMSL
        float    vn, ve, vd;     //m/s, NED
        float    hacc_m, vacc_m;
        float    sacc_ms;        //the fix's velocity is the flight EKF's plus a Doppler correction
        uint8_t  num_sats;
        uint8_t  fix_type;       //0 none, 3 = 3D, aligned with AP_GPS::GPS_Status
        //GPS time, which the solve knows from the TLE epoch
        uint16_t time_week;
        uint32_t time_week_ms;
        uint32_t produced_ms;    //AP_HAL::millis() when the solve produced it
    };

    //called by the solve task each time it produces a fix
    void set(const fix_t &f);

    //returns false if there is no fix or it is older than FIX_STALE_MS
    bool get(fix_t &f) const;

    static const uint32_t FIX_STALE_MS = 5000;

#if CONFIG_HAL_BOARD == HAL_BOARD_SITL
    //SITL stand-in for the solve task: there is no I/Q in the simulator
    // synthesises a fix from the simulated truth, degraded to the quality
    //sitl/soop_link.py models
    void update_from_sitl(uint32_t now_ms);
#endif

private:
    fix_t _fix {};
    bool  _have_fix = false;
    mutable HAL_Semaphore _sem;
};
