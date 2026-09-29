//AP_SoOP - position from Iridium, on the aircraft
#pragma once

#include <AP_HAL/AP_HAL.h>

extern "C" {
#include "soop_dsp.h"
#include "soop_nav.h"
}

#define AP_SOOP_VEH_QUEUE 64
#define AP_SOOP_BURST_QUEUE 32

class AP_SoOP
{
public:
    static AP_SoOP *get_singleton();

    //main thread, from AP_GPS_SoOP::read()
    void update();

private:
    struct veh_t {
        double t;                //board s
        float  vn, ve, vd;       //flight-EKF velocity, NED
        bool   vel_ok;
        float  baro_h;           //ellipsoid-referenced height from the baro
        bool   baro_ok;
        bool   gps_ok;           //the real GPS, trusted this instant
        double gps_utc;          //UTC s since J2000
        double gps_ecef[3];
    };
    struct burst_t {
        double t;
        float  f, sigma, cn0;
    };

    void thread_main();
    bool setup();
    void load_config();
    int  load_catalogue();
    void run_block(const int16_t *iq, uint64_t first_sample);
    void feed_until(double horizon);
    void publish(double t);
    void log_status(double t);

    bool     _started;
    HAL_Semaphore _sem;
    veh_t    _veh[AP_SOOP_VEH_QUEUE];
    uint16_t _veh_head, _veh_tail;
    burst_t  _bq[AP_SOOP_BURST_QUEUE];
    uint16_t _bq_n;

    //set up in the thread
    soop_dsp_t *_dsp;
    soop_nav_t *_nav;
    soop_sat_t *_cat;
    int16_t    *_block;
    int        _n_cat;
    bool       _replay, _swap_iq, _capturing;
    uint8_t    _bbg;
    double     _t0;              //board s of capture sample 0
    double     _fs;
    double     _undulation;      //m, geoid above ellipsoid, from the GPS when it says
    float      _baro_offset;     //ellipsoidal height minus baro altitude, learnt on GPS
    bool       _have_baro_offset;
    double     _last_fix_t, _last_status_t;
    uint32_t   _cpu_us, _bursts_s;
    uint64_t   _samples_s;
};

namespace AP {
    AP_SoOP *soop();
};
