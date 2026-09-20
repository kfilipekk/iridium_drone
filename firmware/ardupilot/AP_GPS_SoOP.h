/*
   AP_GPS_SoOP - feed an on-board Doppler fix to the EKF as a GPS-class fix.

   The fix is produced on this vehicle by the Iridium Doppler solve and handed over
   in-process by AP_SoOPFix (see firmware/ardupilot/AP_SoOPFix.h). This backend exists
   because the repo's register is right that the route did not: GPS_INPUT (#232) is for an
   external computer, and this aircraft solves on board.

   Registered as GPS_TYPE = 27 (GPS_TYPE_SOOP). On SITL the fix is synthesised from the
   simulated truth, degraded to the modelled Doppler quality, so the hand-off can be
   exercised without I/Q; that stand-in is not the solve.
 */
#pragma once

#include "GPS_Backend.h"

class AP_GPS_SoOP : public AP_GPS_Backend
{
public:
    using AP_GPS_Backend::AP_GPS_Backend;

    bool read() override;

    const char *name() const override { return "SoOP"; }

    // A Doppler solve is a 3D position fix; it does not do DGPS/RTK.
    AP_GPS::GPS_Status highest_supported_status(void) override { return AP_GPS::GPS_OK_FIX_3D; }

    // The solve is periodic and late by design (an arc must be observed first), so the
    // backend reports a real lag rather than the 0.2 s default.
    bool get_lag(float &lag) const override { lag = 1.0f; return true; }
};
