/*
   In-process hand-off for an on-board Doppler fix.

   why this EXISTS. The NAVCORE board solves its own position from Iridium Doppler on the
   H743 (tools/soop_solver.py validated; firmware/soop/soop_solve.c is the port). The
   repo's register is explicit that the route into the EKF "does not exist yet", because
   GPS_INPUT (#232) is the path for an external computer and this aircraft solves on
   board - routing a locally computed fix out over MAVLink and back would be absurd.

   So the solve writes here, in-process, and AP_GPS_SoOP reads it. This is the whole
   point of a backend rather than a MAVLink message: the fix never leaves the vehicle.

   the producer is not written YET. Nothing on the aircraft calls set() - the I/Q
   capture, the in-C ephemeris and the task that runs the solve each cycle are the
   remaining firmware work. What is proven here is the sink: a solver's output can be
   handed to the EKF as a GPS-class fix.
 */
#pragma once

#include <AP_HAL/AP_HAL.h>

class AP_SoOPFix
{
public:
    static AP_SoOPFix *get_singleton();

    struct fix_t {
        double   lat_deg;
        double   lon_deg;
        float    alt_m;          // AMSL
        float    vn, ve, vd;     // m/s, NED
        float    hacc_m, vacc_m;
        uint8_t  num_sats;
        uint8_t  fix_type;       // 0 none, 3 = 3D, aligned with AP_GPS::GPS_Status
        // GPS time, which the solve knows from the TLE epoch. not AP_HAL::millis():
        // boot time is not GPS time, and feeding it as such would corrupt the EKF clock.
        uint16_t time_week;
        uint32_t time_week_ms;
        uint32_t produced_ms;    // AP_HAL::millis() when the solve produced it
    };

    // Called by the solve task each time it produces a fix.
    void set(const fix_t &f);

    // Returns false if there is no fix or it is older than FIX_STALE_MS - a stale fix
    // must not be served as a current one, which is the failure that would look like a
    // working system right up until the first position glitch.
    bool get(fix_t &f) const;

    static const uint32_t FIX_STALE_MS = 5000;

#if CONFIG_HAL_BOARD == HAL_BOARD_SITL
    // SITL stand-in for the solve task: there is no I/Q in the simulator, so this
    // synthesises a fix from the simulated truth, degraded to the quality
    // sitl/soop_link.py models. It exists only to exercise the backend->EKF hand-off in
    // SITL; it is not the solve and must never run on hardware.
    void update_from_sitl(uint32_t now_ms);
#endif

private:
    fix_t _fix {};
    bool  _have_fix = false;
    mutable HAL_Semaphore _sem;
};
