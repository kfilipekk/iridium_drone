#include "AP_SoOP.h"
#include "AP_SoOP_MAX2112.h"
#include "AP_SoOP_Capture.h"

extern "C" {
#include "soop_signal.h"
}

#include <AP_AHRS/AP_AHRS.h>
#include <AP_Baro/AP_Baro.h>
#include <AP_Filesystem/AP_Filesystem.h>
#include <AP_GPS/AP_GPS.h>
#include <AP_GPS/AP_SoOPFix.h>
#include <AP_Logger/AP_Logger.h>
#include <GCS_MAVLink/GCS.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern const AP_HAL::HAL& hal;

//ArduPilot compiles with -fsingle-precision-constant
static const uint64_t UNIX_J2000_US = 946728000ULL * 1000000ULL;   //12:00 UTC
static const uint64_t GPS_UNIX_S = 315964800ULL;                     //1980-01-06 00:00 UTC
static const uint32_t LEAP_S = 18;                                   //GPS - UTC since 2017
static const char *DIR = "APM/SOOP";

static AP_SoOP_MAX2112 tuner;
static AP_SoOP_Capture capture;

AP_SoOP *AP_SoOP::get_singleton()
{
    static AP_SoOP singleton;
    return &singleton;
}

namespace AP {
AP_SoOP *soop() { return AP_SoOP::get_singleton(); }
};

//main thread
void AP_SoOP::update()
{
    if (!_started) {
        _started = true;
        if (!hal.scheduler->thread_create(FUNCTOR_BIND_MEMBER(&AP_SoOP::thread_main, void),
                                          "SoOP", 8192, AP_HAL::Scheduler::PRIORITY_STORAGE, 1)) {
            GCS_SEND_TEXT(MAV_SEVERITY_ERROR, "SoOP: no thread");
        }
        return;
    }

    if (_guard_state == SOOP_G_SPOOFED && !_spoof_handled) {
        //the real GPS disagrees with Iridium: stop the autopilot following it
        _spoof_handled = true;
        GCS_SEND_TEXT(MAV_SEVERITY_CRITICAL, "SoOP: GPS spoofed, %.0f m from Iridium - using SoOP",
                      double(_guard_dist));
        if (!AP_Param::set_by_name("GPS_AUTO_SWITCH", 0) || !AP_Param::set_by_name("GPS_PRIMARY", 1)) {
            GCS_SEND_TEXT(MAV_SEVERITY_CRITICAL, "SoOP: could not switch GPS - take manual control");
        }
    }

    veh_t v {};
    v.t = AP_HAL::micros64() / double(1000000);
    v.armed = hal.util->get_soft_armed();

    Vector3f vel;
    const AP_AHRS &ahrs = AP::ahrs();
    v.vel_ok = ahrs.get_velocity_NED(vel);
    v.vn = vel.x;
    v.ve = vel.y;
    v.vd = vel.z;

    //the real GPS, only while it is good enough to calibrate against
    const AP_GPS &gps = AP::gps();
    float hacc = 99.0f, und = 0.0f;
    const bool good = _guard_state != SOOP_G_SPOOFED
                      && gps.status(0) >= AP_GPS::GPS_OK_FIX_3D && gps.num_sats(0) >= 6
                      && gps.horizontal_accuracy(0, hacc) && hacc < 5.0f;
    if (good) {
        if (gps.get_undulation(0, und)) {
            _undulation = und;
        }
        const Location &loc = gps.location(0);
        const double h = loc.alt / double(100) + _undulation;
        soop_ecef(loc.lat / double(10000000), loc.lng / double(10000000), h, v.gps_ecef);
        v.gps_utc = (gps.time_epoch_usec(0) - UNIX_J2000_US) / double(1000000);
        v.gps_ok = true;
        const float b = AP::baro().get_altitude();
        const float off = h - b;                    //baro is relative: tie it to the GPS
        _baro_offset = _have_baro_offset ? 0.98f * _baro_offset + 0.02f * off : off;
        _have_baro_offset = true;
    }
    if (_have_baro_offset && AP::baro().healthy()) {
        v.baro_h = AP::baro().get_altitude() + _baro_offset;
        v.baro_ok = true;
    }

    WITH_SEMAPHORE(_sem);
    const uint16_t next = (_veh_head + 1) % AP_SOOP_VEH_QUEUE;
    if (next != _veh_tail) {
        _veh[_veh_head] = v;
        _veh_head = next;
    }
}

//set-up
void AP_SoOP::load_config()
{
    //"key value" per line; unknown keys are reported, not ignored silently
    char path[40];
    snprintf(path, sizeof(path), "%s/soop.cfg", DIR);
    const int fd = AP::FS().open(path, O_RDONLY);
    if (fd < 0) {
        return;
    }
    char buf[512];
    const int32_t n = AP::FS().read(fd, buf, sizeof(buf) - 1);
    AP::FS().close(fd);
    if (n <= 0) {
        return;
    }
    buf[n] = 0;
    soop_nav_cfg_t &c = _nav->cfg;
    struct { const char *key; double *val; } dbl[] = {
        { "beta_sigma", &c.beta_sigma }, { "clkd_q", &c.clkd_q }, { "clk_q", &c.clk_q },
        { "vel_sigma", &c.vel_sigma }, { "vel_tau", &c.vel_tau }, { "dut1", &c.dut1 },
        { "mask_deg", &c.mask_deg }, { "max_tle_age_d", &c.max_tle_age_d },
        { "fix_max_hacc", &c.fix_max_hacc },
        { "along_m_per_day", &c.orbit[SOOP_ORBIT_TLE].along_m_per_day },
        { "guard_k", &_gcfg.k }, { "guard_floor_m", &_gcfg.floor_m },
        { "guard_hold_s", &_gcfg.hold_s }, { "guard_free_vel", &_gcfg.free_vel_sigma },
    };
    //no scanf here: ArduPilot's C library has none with floating point
    char *save = nullptr;
    for (char *line = strtok_r(buf, "\n", &save); line; line = strtok_r(nullptr, "\n", &save)) {
        char *key = line;
        while (*key == ' ' || *key == '\t') {
            key++;
        }
        char *sp = strpbrk(key, " \t");
        if (key[0] == '#' || key[0] == 0 || sp == nullptr) {
            continue;
        }
        *sp = 0;
        char *end = nullptr;
        const double val = strtod(sp + 1, &end);
        if (end == sp + 1) {
            continue;
        }
        bool known = true;
        if (!strcmp(key, "replay")) {
            _replay = val != 0;
        } else if (!strcmp(key, "swap_iq")) {
            _swap_iq = val != 0;
        } else if (!strcmp(key, "bbg")) {
            _bbg = uint8_t(constrain_int16(int16_t(val), 0, 15));
        } else {
            known = false;
            for (auto &d : dbl) {
                if (!strcmp(key, d.key)) {
                    *d.val = val;
                    known = true;
                }
            }
        }
        if (!known) {
            GCS_SEND_TEXT(MAV_SEVERITY_WARNING, "SoOP: unknown soop.cfg key %s", key);
        }
    }
}

int AP_SoOP::load_catalogue()
{
    char path[40];
    snprintf(path, sizeof(path), "%s/iridium.tle", DIR);
    struct stat st;
    if (AP::FS().stat(path, &st) != 0 || st.st_size <= 0 || st.st_size > 64 * 1024) {
        return 0;
    }
    char *text = (char *)malloc(st.st_size + 1);
    if (text == nullptr) {
        return 0;
    }
    const int fd = AP::FS().open(path, O_RDONLY);
    const int32_t n = fd >= 0 ? AP::FS().read(fd, text, st.st_size) : -1;
    if (fd >= 0) {
        AP::FS().close(fd);
    }
    int count = 0;
    if (n > 0) {
        text[n] = 0;
        for (const char *p = text; *p; p++) {           //size the table by its "1 " lines
            if ((p == text || p[-1] == '\n') && p[0] == '1' && p[1] == ' ') {
                count++;
            }
        }
        _cat = (soop_sat_t *)calloc(count, sizeof(soop_sat_t));
        count = _cat ? soop_ephem_parse(text, _cat, count) : 0;
    }
    free(text);
    return count;
}

bool AP_SoOP::setup()
{
    _dsp = (soop_dsp_t *)hal.util->malloc_type(sizeof(soop_dsp_t), AP_HAL::Util::MEM_FAST);
    _guard = (soop_guard_t *)calloc(1, sizeof(soop_guard_t));
    _nav = _guard ? &_guard->main : nullptr;
    _block = (int16_t *)calloc(2 * SOOP_CAPTURE_BLOCK, sizeof(int16_t));
    if (!_dsp || !_guard || !_block) {
        GCS_SEND_TEXT(MAV_SEVERITY_ERROR, "SoOP: out of memory");
        return false;
    }
    soop_dsp_init(_dsp);
    _bbg = 4;
    soop_nav_cfg_t cfg;
    soop_nav_default_cfg(&cfg);
    _nav->cfg = cfg;
    soop_guard_default_cfg(&_gcfg);
    load_config();
    cfg = _nav->cfg;

    _n_cat = load_catalogue();
    if (_n_cat < 60) {
        //a short catalogue narrows the geometry silently
        GCS_SEND_TEXT(MAV_SEVERITY_ERROR, "SoOP: %d satellites in %s/iridium.tle - need the full catalogue",
                      _n_cat, DIR);
        return false;
    }

    if (_replay) {
        GCS_SEND_TEXT(MAV_SEVERITY_INFO, "SoOP: replay of %s/replay.iq, %d satellites", DIR, _n_cat);
    } else {
        // the LO the C side asks for, and the one the synthesiser can actually make
        if (!tuner.init(0, cfg.f_lo, _bbg)) {
            GCS_SEND_TEXT(MAV_SEVERITY_ERROR, "SoOP: MAX2112 not locked (VCO %u, VTUNE ADC %u)",
                          tuner.vco(), tuner.vtune_adc());
            return false;
        }
        cfg.f_lo = tuner.lo_hz();
        if (!AP_SoOP_Capture::supported() || !capture.start(_swap_iq)) {
            GCS_SEND_TEXT(MAV_SEVERITY_ERROR, "SoOP: no I/Q capture on this build");
            return false;
        }
        _capturing = true;
        GCS_SEND_TEXT(MAV_SEVERITY_INFO, "SoOP: tuner locked, VCO %u, %d satellites",
                      tuner.vco(), _n_cat);
    }
    soop_guard_init(_guard, &cfg, &_gcfg, _cat, _n_cat, 0.0);
    _fs = SOOP_FS;
    return true;
}

void AP_SoOP::thread_main()
{
    while (!hal.scheduler->is_system_initialized()) {
        hal.scheduler->delay(100);
    }
    hal.scheduler->delay(2000);                     //let the SD card and sensors settle
    if (!setup()) {
        return;
    }
    int fd = -1;
    uint64_t replay_sample = 0;
    if (_replay) {
        char path[40];
        snprintf(path, sizeof(path), "%s/replay.iq", DIR);
        fd = AP::FS().open(path, O_RDONLY);
        _t0 = AP_HAL::micros64() / double(1000000);
    } else {
        _t0 = capture.start_us() / double(1000000);
    }

    while (true) {
        uint64_t first = 0;
        if (_replay) {
            const int32_t want = 4 * SOOP_CAPTURE_BLOCK;
            if (fd < 0 || AP::FS().read(fd, _block, want) != want) {
                if (fd >= 0) {
                    AP::FS().close(fd);
                    fd = -1;
                    GCS_SEND_TEXT(MAV_SEVERITY_INFO, "SoOP: replay done");
                }
                hal.scheduler->delay(1000);
                continue;
            }
            first = replay_sample;
            replay_sample += SOOP_CAPTURE_BLOCK;
            //hold real time, so the CPU figure means what it will mean in flight
            const double due = _t0 + replay_sample / _fs;
            const double now = AP_HAL::micros64() / double(1000000);
            if (due > now) {
                hal.scheduler->delay_microseconds(uint16_t(MIN((due - now) * 1e6, 60000.0f)));
            }
        } else if (!capture.next_block(_block, first, 50)) {
            continue;
        }
        run_block(_block, first);
    }
}

void AP_SoOP::run_block(const int16_t *iq, uint64_t first_sample)
{
    soop_burst_t out[8];
    const uint32_t t_start = AP_HAL::micros();
    const size_t n = soop_dsp_push(_dsp, iq, SOOP_CAPTURE_BLOCK, out, 8);
    _cpu_us += AP_HAL::micros() - t_start;
    _samples_s += SOOP_CAPTURE_BLOCK;
    for (size_t i = 0; i < n; i++) {
        if (_bq_n == AP_SOOP_BURST_QUEUE) {
            break;
        }
        burst_t &b = _bq[_bq_n++];
        b.t = _t0 + out[i].t_sample / _fs;
        b.f = out[i].f_hz;
        b.sigma = out[i].f_sigma_hz;
        b.cn0 = out[i].cn0_dbhz;
        _bursts_s++;
    }
    //bursts come out up to one simplex slot after their preamble
    const double newest = _t0 + (first_sample + SOOP_CAPTURE_BLOCK) / _fs;
    feed_until(newest - 0.05);
    if (newest - _last_fix_t >= 0.2) {
        publish(newest - 0.05);
        _last_fix_t = newest;
    }
    if (newest - _last_status_t >= 1.0) {
        log_status(newest);
        _last_status_t = newest;
    }
}

//vehicle samples and bursts, merged by time into the navigation
void AP_SoOP::feed_until(double horizon)
{
    while (true) {
        veh_t v;
        bool have_v = false;
        {
            WITH_SEMAPHORE(_sem);
            if (_veh_tail != _veh_head && _veh[_veh_tail].t <= horizon) {
                v = _veh[_veh_tail];
                have_v = true;
            }
        }
        int bi = -1;
        for (uint16_t i = 0; i < _bq_n; i++) {
            if (_bq[i].t <= horizon && (bi < 0 || _bq[i].t < _bq[bi].t)) {
                bi = i;
            }
        }
        if (bi >= 0 && (!have_v || _bq[bi].t < v.t)) {
            const burst_t b = _bq[bi];
            _bq[bi] = _bq[--_bq_n];
            const int res = soop_guard_burst(_guard, b.t, b.f, b.sigma);
            AP::logger().WriteStreaming("SOB", "TimeUS,T,F,Sig,CN0,Res,Sat,Ch,Inn",
                                        "QdfffBIbf", AP_HAL::micros64(), b.t, b.f, b.sigma, b.cn0,
                                        uint8_t(res), uint32_t(res == SOOP_B_FUSED ? _nav->last_sat : 0),
                                        int8_t(res == SOOP_B_FUSED ? _nav->last_ch : -1),
                                        float(res == SOOP_B_FUSED ? _nav->last_y : 0.0f));
            continue;
        }
        if (!have_v) {
            return;
        }
        {
            WITH_SEMAPHORE(_sem);
            _veh_tail = (_veh_tail + 1) % AP_SOOP_VEH_QUEUE;
        }
        if (v.armed && !_was_armed) {
            soop_guard_arm(_guard, v.t);    //from here the GPS is checked against Iridium
        }
        _was_armed = v.armed;
        if (v.vel_ok) {
            soop_guard_velocity(_guard, v.t, v.vn, v.ve, v.vd);
        }
        if (v.gps_ok) {
            soop_guard_gps(_guard, v.t, v.gps_utc, v.gps_ecef);
            _guard_dist = float(_guard->dist_m);
            _guard_state = uint8_t(_guard->state);
        }
        if (v.baro_ok) {
            soop_guard_baro(_guard, v.t, v.baro_h);
        }
    }
}

void AP_SoOP::publish(double t)
{
    soop_fix_t f;
    const bool valid = soop_guard_fix(_guard, t, &f);
    AP::logger().WriteStreaming("SOF", "TimeUS,Lat,Lng,Alt,HAcc,VAcc,SAcc,NIS,NT,V",
                                "QLLffffBB" "B", AP_HAL::micros64(),
                                int32_t(f.lat_deg * 10000000), int32_t(f.lon_deg * 10000000),
                                float(f.h_m - _undulation), f.hacc_m, f.vacc_m, f.sacc_ms, f.nis,
                                f.n_track, f.valid);
    if (!valid || !_nav->have_time) {
        return;
    }
    AP_SoOPFix::fix_t out {};
    out.lat_deg = f.lat_deg;
    out.lon_deg = f.lon_deg;
    out.alt_m = f.h_m - _undulation;
    out.vn = f.vn;
    out.ve = f.ve;
    out.vd = f.vd;
    out.hacc_m = f.hacc_m;
    out.vacc_m = f.vacc_m;
    out.sacc_ms = f.sacc_ms;
    out.num_sats = f.n_track;
    out.fix_type = 3;
    //GPS time of the fix, from the navigation's own board-to-UTC mapping
    const double utc = _nav->tu0 + _nav->tc_a + (1 + _nav->tc_b) * (t - _nav->tb0);
    const uint64_t gps_ms = uint64_t((utc + 946728000.0L - GPS_UNIX_S + LEAP_S) * 1000);
    out.time_week = gps_ms / AP_MSEC_PER_WEEK;
    out.time_week_ms = gps_ms % AP_MSEC_PER_WEEK;
    AP_SoOPFix::get_singleton()->set(out);
}

void AP_SoOP::log_status(double t)
{
    const float cpu = _samples_s ? 100.0f * _cpu_us / (1e6f * _samples_s / float(SOOP_FS)) : 0;
    if (_capturing) {
        tuner.check_lock();
    }
    AP::logger().WriteStreaming("SOS", "TimeUS,CPU,Bps,Ovr,Lock,VT,NT,Clk,Fused,Amb,Unm,G,GD,GL",
                                "QfHIBBBfIIIBff", AP_HAL::micros64(), cpu, uint16_t(_bursts_s),
                                capture.overruns(), uint8_t(tuner.locked()), tuner.vtune_adc(),
                                uint8_t(_nav->n_track), float(_nav->x[6]),
                                _nav->count[SOOP_B_FUSED], _nav->count[SOOP_B_AMBIGUOUS],
                                _nav->count[SOOP_B_UNMATCHED], uint8_t(_guard->state),
                                float(_guard->dist_m), float(_guard->limit_m));
    _cpu_us = 0;
    _samples_s = 0;
    _bursts_s = 0;
    (void)t;
}
