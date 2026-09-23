#include "AP_GPS_SoOP.h"

#include "AP_SoOPFix.h"

bool AP_GPS_SoOP::read(void)
{
    const uint32_t now = AP_HAL::millis();

#if CONFIG_HAL_BOARD == HAL_BOARD_SITL
    // stand-in for the solve task; see AP_SoOPFix.cpp
    AP_SoOPFix::get_singleton()->update_from_sitl(now);
#endif

    AP_SoOPFix::fix_t f {};
    if (!AP_SoOPFix::get_singleton()->get(f)) {
        // No fix, or the last one is stale. Report NO_FIX rather than holding the last
        // position: a stale fix served as current is the failure that looks like a
        // working system until the first position glitch.
        state.status = AP_GPS::NO_FIX;
        state.num_sats = 0;
        state.last_gps_time_ms = now;
        return false;
    }

    state.status = (f.fix_type >= 3) ? AP_GPS::GPS_OK_FIX_3D : AP_GPS::NO_FIX;
    state.num_sats = f.num_sats;
    state.time_week = f.time_week;
    state.time_week_ms = f.time_week_ms;

    state.location = Location{
        int32_t(f.lat_deg * 1e7),
        int32_t(f.lon_deg * 1e7),
        int32_t(f.alt_m * 100.0f),
        Location::AltFrame::ABSOLUTE
    };

    state.velocity.x = f.vn;
    state.velocity.y = f.ve;
    state.velocity.z = f.vd;
    state.have_vertical_velocity = true;
    velocity_to_speed_course(state);

    // The solve knows its own accuracy; publish it rather than a hardcoded DOP.
    state.have_horizontal_accuracy = true;
    state.have_vertical_accuracy = true;
    state.have_speed_accuracy = true;
    state.horizontal_accuracy = f.hacc_m;
    state.vertical_accuracy = f.vacc_m;
    state.speed_accuracy = 0.3f;          // Doppler solve natively measures velocity

    state.hdop = 100;
    state.vdop = 100;

    state.last_gps_time_ms = now;

    return true;
}
