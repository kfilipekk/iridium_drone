#include "AP_SoOPFix.h"

#include <AP_HAL/AP_HAL.h>

#if CONFIG_HAL_BOARD == HAL_BOARD_SITL
#include <SITL/SITL.h>
#include <AP_Math/AP_Math.h>
#endif

AP_SoOPFix *AP_SoOPFix::get_singleton()
{
    static AP_SoOPFix _singleton;
    return &_singleton;
}

void AP_SoOPFix::set(const fix_t &f)
{
    _sem.take_blocking();
    _fix = f;
    _fix.produced_ms = AP_HAL::millis();
    _have_fix = true;
    _sem.give();
}

bool AP_SoOPFix::get(fix_t &f) const
{
    bool ok = false;
    _sem.take_blocking();
    if (_have_fix && (AP_HAL::millis() - _fix.produced_ms) < FIX_STALE_MS) {
        f = _fix;
        ok = true;
    }
    _sem.give();
    return ok;
}

#if CONFIG_HAL_BOARD == HAL_BOARD_SITL
/*
  SITL stand-in for the solve. The simulated truth is degraded to the quality the repo
  models for an Iridium Doppler solution (sitl/soop_link.py: ~180 m mean east error, a
  correlated wandering bias rather than white noise, and a ~1 Hz rate). This is not the
  solver - it is here so the backend->EKF hand-off can be exercised without I/Q. A green
  SITL run therefore says the fix reaches the EKF, and nothing about the solve.
 */
void AP_SoOPFix::update_from_sitl(uint32_t now_ms)
{
    static uint32_t last_ms;
    static float bias_n, bias_e;          // wandering bias, metres
    if (last_ms != 0 && now_ms - last_ms < 1000) {   // ~1 Hz, like a real fix
        return;
    }
    last_ms = now_ms;

    auto *sitl = AP::sitl();
    if (sitl == nullptr) {
        return;
    }

    // random walk on the bias, capped, with gravity-model-style white noise on top
    const float walk = 1.5f;              // m per fix
    const float cap = 40.0f;              // m
    bias_n = constrain_float(bias_n + walk * rand_float(), -cap, cap);
    bias_e = constrain_float(bias_e + walk * rand_float(), -cap, cap);

    const float sigma = 180.0f;           // SIGMA_IRIDIUM_NO_ELEV, sitl/soop_link.py
    const float dn = bias_n + sigma * rand_float();
    const float de = bias_e + sigma * rand_float();

    // metre offsets -> degrees, locally
    const double m_per_deg_lat = 111320.0;
    const double m_per_deg_lon = 111320.0 * cos(radians(sitl->state.latitude));

    fix_t f {};
    f.lat_deg = sitl->state.latitude + dn / m_per_deg_lat;
    f.lon_deg = sitl->state.longitude + de / m_per_deg_lon;
    f.alt_m = sitl->state.altitude + 2.0f * sigma * rand_float();
    f.vn = sitl->state.speedN;
    f.ve = sitl->state.speedE;
    f.vd = sitl->state.speedD;
    f.hacc_m = 400.0f;
    f.vacc_m = 700.0f;
    f.num_sats = 6;                       // Iridium sats in the arc, not GPS sats
    f.fix_type = 3;
    set(f);
}
#endif
