#!/usr/bin/env python3
"""Feed ArduCopter SITL a fix as bad as an Iridium Doppler solve, and measure the EKF.

Usage:
  soop_link.py --mode extnav --duration 120 --report /tmp/nav/sitl/extnav.json
"""
import argparse, json, math, os, random, sys, time
from collections import deque

try:
    from pymavlink import mavutil
except ImportError:
    sys.exit("pymavlink missing - pip install pymavlink into the venv")

EARTH_R = 6378137.0


def latlon_to_ned(lat, lon, alt, olat, olon, oalt):
    """Small-angle equirectangular projection about the origin. Good to <1 cm/km here."""
    dlat = math.radians(lat - olat)
    dlon = math.radians(lon - olon)
    n = dlat * EARTH_R
    e = dlon * EARTH_R * math.cos(math.radians(olat))
    d = -(alt - oalt)
    return n, e, d


def ned_to_latlon(n, e, olat, olon):
    lat = olat + math.degrees(n / EARTH_R)
    lon = olon + math.degrees(e / (EARTH_R * math.cos(math.radians(olat))))
    return lat, lon


class DopplerErrorModel:
    """Latency, a slow random-walk bias, white noise and outages."""

    SIGMA_IRIDIUM_NO_ELEV = 180.0    # mean eastward error, Iridium NEXT, no elev aiding
    SIGMA_IRIDIUM_MAE = 380.0        # mean absolute error, same conditions
    SIGMA_SINGLE_SAT = 656.0         # Doppler-only, one satellite
    SIGMA_SINGLE_SAT_DOA = 289.5     # one satellite, + azimuth doa
    SIGMA_BEST_MULTI = 22.7          # 4 Iridium + 1 Orbcomm, static - best case, not typical

    def __init__(self, sigma_m=SIGMA_IRIDIUM_NO_ELEV, bias_walk_m_s=1.5, bias_cap_m=40.0,
                 latency_s=2.0, rate_hz=1.0, outage_p=0.05, outage_len_s=8.0,
                 seed=None):
        self.sigma = sigma_m
        self.walk = bias_walk_m_s
        self.cap = bias_cap_m
        self.latency = latency_s
        self.period = 1.0 / rate_hz
        self.outage_p = outage_p
        self.outage_len = outage_len_s
        self.rng = random.Random(seed)
        self.bias = [0.0, 0.0]
        self.buf = deque()            # (ready_at, n, e, d) - the latency line
        self.next_emit = 0.0
        self.outage_until = 0.0
        self.resets = 0
        self._last_bias_t = None

    def _advance_bias(self, now):
        """Random walk, reflected at the cap so the bias wanders but stays bounded."""
        dt = 0.0 if self._last_bias_t is None else now - self._last_bias_t
        self._last_bias_t = now
        for i in (0, 1):
            self.bias[i] += self.rng.gauss(0.0, self.walk * math.sqrt(max(dt, 0.0)))
            if abs(self.bias[i]) > self.cap:
                self.bias[i] = math.copysign(self.cap, self.bias[i])

    def offer(self, now, n, e, d):
        """Feed truth in; it comes out later, or not at all."""
        if now >= self.next_emit:
            self.next_emit = now + self.period
            if now < self.outage_until:
                return
            if self.rng.random() < self.outage_p:
                self.outage_until = now + self.outage_len
                # An outage means the next fix is a discontinuity; the EKF must be told.
                self.resets += 1
                return
            self._advance_bias(now)
            self.buf.append((now + self.latency,
                             n + self.bias[0] + self.rng.gauss(0, self.sigma),
                             e + self.bias[1] + self.rng.gauss(0, self.sigma),
                             d + self.rng.gauss(0, self.sigma * 0.5)))

    def due(self, now):
        while self.buf and self.buf[0][0] <= now:
            yield self.buf.popleft()


class Harness:
    VEL_SIGMA = 0.3
    FLOW_SIGMA = 0.02          # rad/s; a decent camera flow solution
    PRX_MAX_CM = 400           # sensor ceiling reported to ArduPilot, cm
    PRX_CLEAR_CM = 350

    def rng_v(self):
        return self.model.rng.gauss(0.0, self.VEL_SIGMA)

    def __init__(self, conn, mode, model, flow_hz=20.0, flow_quality=180, bias_m=0.0,
                 honest_quality=False, mirror_gps=True):
        self.vel_sigma = self.VEL_SIGMA
        # Mirror the live GPS onto instance 2 while GPS1 is HEALTHY.
        self.mirror_gps = mirror_gps
        self._gps1_rx_t = None
        self.honest_quality = honest_quality
        self.bias_m = bias_m
        self.bias_active = False
        self.m = conn
        self.mode = mode
        self.model = model
        self.flow_dt = 1.0 / flow_hz
        self.flow_quality = flow_quality
        self.origin = None            # (lat, lon, alt) of the EKF origin
        self.truth = None             # (lat, lon, alt) from SIMSTATE
        self.est = None               # (lat, lon, alt) from GLOBAL_POSITION_INT
        self.vel = (0.0, 0.0, 0.0)    # NED m/s
        self.agl = 0.0                # height above the launch point, m
        self._last_truth_t = None
        self.send_velocity = True     # cleared by the position-only comparison scenario
        self.yaw = 0.0                # rad
        self.next_flow = 0.0
        self.next_obst = 0.0
        self.errors = []              # (t, horizontal error m)
        self.truth_track = []
        self.track = []               # (t, truth_n, truth_e, est_n, est_e) for inspection
        self.alt_track = []           # height above launch, for the flow-ceiling test
        self.alt_track_denied = None  # set to [] at denial; only these count for a ceiling
        self.t0 = time.time()

    # ---- inbound -------------------------------------------------------
    def pump(self):
        """Read everything pending. the only reader - see the note in scenarios.py."""
        n = 0
        while True:
            msg = self.m.recv_match(blocking=False)
            if msg is None:
                return n
            if msg.get_type() != "BAD_DATA":
                n += 1
            t = msg.get_type()
            if t == "SIMSTATE":
                new = (msg.lat * 1e-7, msg.lng * 1e-7, getattr(msg, "alt", 0.0))
                self._truth_velocity(new)
                self.truth = new
            elif t == "GPS_GLOBAL_ORIGIN":
                self.origin = (msg.latitude * 1e-7, msg.longitude * 1e-7,
                               msg.altitude * 1e-3)
            elif t == "GLOBAL_POSITION_INT":
                self.est = (msg.lat * 1e-7, msg.lon * 1e-7, msg.alt * 1e-3)
                self.agl = max(msg.relative_alt / 1000.0, 0.0)
                self.alt_track.append(self.agl)
                if self.alt_track_denied is not None:
                    self.alt_track_denied.append(self.agl)
                # note: msg.vx/vy/vz are the EKF's own velocity estimate. They must never
                # be injected back - see _truth_velocity below.
            elif t == "GPS_RAW_INT":
                if getattr(msg, "fix_type", 0) >= 3:
                    self._gps1_rx_t = time.time()
            elif t == "ATTITUDE":
                self.yaw = msg.yaw

    def _truth_velocity(self, new):
        """Differentiate SIMSTATE to get true velocity."""
        now = time.time()
        if self.truth is not None and self._last_truth_t is not None:
            dt = now - self._last_truth_t
            if dt > 0.02:
                dn, de, dd = latlon_to_ned(*new, *self.truth)
                self.vel = (dn / dt, de / dt, dd / dt)
                self._last_truth_t = now
        else:
            self._last_truth_t = now

    # ---- outbound ------------------------------------------------------
    def send_position(self, now):
        if self.truth is None:
            return
        if self.origin is None:
            # No origin yet - ask for it. Without one, ExternalNav has no frame.
            self.m.mav.command_long_send(
                self.m.target_system, self.m.target_component,
                mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
                mavutil.mavlink.MAVLINK_MSG_ID_GPS_GLOBAL_ORIGIN, 0, 0, 0, 0, 0, 0)
            return
        n, e, d = latlon_to_ned(*self.truth, *self.origin)
        self.model.offer(now, n, e, d)
        gps1_alive = (self._gps1_rx_t is not None
                      and (time.time() - self._gps1_rx_t) < 2.0)
        for _ready, dn, de, dd in self.model.due(now):
            # The offset is applied only once armed.
            dn += self.bias_m if self.bias_active else 0.0
            usec = int(now * 1e6)
            if self.mode == "extnav":
                self.m.mav.vision_position_estimate_send(
                    usec, dn, de, dd, 0.0, 0.0, 0.0,
                    reset_counter=self.model.resets)
            else:
                # Mirror decision per published fix.
                mirror = (self.mirror_gps and not self.bias_active and gps1_alive)
                if mirror:
                    mlat, mlon = self.truth[0], self.truth[1]
                    malt = self.truth[2]
                    msacc, mhacc, mnsats = 0.3, 2.0, 12
                else:
                    mlat, mlon = ned_to_latlon(dn, de, self.origin[0], self.origin[1])
                    malt = self.origin[2] - dd
                    msacc, mhacc, mnsats = self._quality(now)
                lat, lon = mlat, mlon
                # Keywords, not positional.
                vn = self.vel[0] + self.rng_v()
                ve = self.vel[1] + self.rng_v()
                vd = self.vel[2] + self.rng_v()
                self.m.mav.gps_input_send(
                    time_usec=usec,
                    # ZERO-BASED instance index, and it must match the instance whose GPS_TYPEn is 14.
                    gps_id=1,
                    # 8|16|32 = ignore vel_horiz, vel_vert, speed_accuracy
                    ignore_flags=0 if self.send_velocity else (8 | 16 | 32),
                    time_week_ms=0,
                    time_week=0,
                    fix_type=3,                       # 3D
                    lat=int(lat * 1e7),
                    lon=int(lon * 1e7),
                    alt=malt,
                    hdop=1.0,
                    vdop=1.0,
                    vn=vn, ve=ve, vd=vd,
                    speed_accuracy=msacc,
                    horiz_accuracy=mhacc,             # the EKF weights on these
                    vert_accuracy=mhacc * 0.5,
                    satellites_visible=mnsats)

    def _quality(self, now):
        """The quality fields the companion publishes - and they are a design DECISION."""
        if not self.honest_quality:
            return self.vel_sigma, self.model.sigma, 8
        stale = now < self.model.outage_until + 2.0
        if stale:
            return 3.0, self.model.sigma * 3.0, 4
        return self.vel_sigma, self.model.sigma, 8

    def send_flow(self, now):
        """Emit flow derived from the vehicle's actual motion."""
        if now < self.next_flow:
            return
        self.next_flow = now + self.flow_dt

        vn, ve, _vd = self.vel
        c, s_ = math.cos(self.yaw), math.sin(self.yaw)
        vx_body = vn * c + ve * s_          # forward
        vy_body = -vn * s_ + ve * c         # right

        if self.agl < 1.0:
            rate_x = rate_y = 0.0
            quality = 0
        else:
            rate_x = vy_body / self.agl
            rate_y = -vx_body / self.agl
            n = self.model.rng.gauss
            rate_x += n(0.0, self.FLOW_SIGMA)
            rate_y += n(0.0, self.FLOW_SIGMA)
            quality = self.flow_quality

        self.m.mav.optical_flow_send(
            int(now * 1e6), 0,
            0, 0,                                 # flow_x/y unused; rates below win
            0.0, 0.0,
            quality,
            self.agl,                             # AP ignores it; sent for completeness
            flow_rate_x=rate_x, flow_rate_y=rate_y)

    def send_obstacles(self, now, wall_at_m=None):
        """Emit OBSTACLE_DISTANCE as the 8-sensor ToF ring would."""
        if now < self.next_obst:
            return
        self.next_obst = now + 0.1                     # 10 Hz
        self.obst_sent = getattr(self, "obst_sent", 0) + 1
        NOT_SEEN = 65535                               # "unknown", per the message spec
        d = [NOT_SEEN] * 72
        for i in range(8):
            if wall_at_m is not None and i == 0:       # sector 0 = straight ahead
                d[i] = int(wall_at_m * 100)            # centimetres
            else:
                d[i] = int(self.PRX_CLEAR_CM)          # clear, and inside the max
        self.m.mav.obstacle_distance_send(
            time_usec=int(now * 1e6),
            sensor_type=0,                             # MAV_DISTANCE_SENSOR_LASER
            distances=d,
            increment=45,                              # 8 sectors x 45 deg
            min_distance=20,                           # cm
            max_distance=int(self.PRX_MAX_CM),
            increment_f=0.0,                           # 0 = use the integer increment
            angle_offset=0.0,                          # sector 0 starts dead ahead
            frame=12)                                  # MAV_FRAME_BODY_FRD

    # ---- measurement ---------------------------------------------------
    def sample_error(self, now):
        if self.truth is None or self.est is None or self.origin is None:
            return
        tn, te, _ = latlon_to_ned(*self.truth, *self.origin)
        en, ee, _ = latlon_to_ned(*self.est, *self.origin)
        self.errors.append((now - self.t0, math.hypot(tn - en, te - ee)))
        self.truth_track.append((tn, te))
        self.track.append((round(now - self.t0, 1), round(tn, 1), round(te, 1),
                           round(en, 1), round(ee, 1)))

    def summary(self):
        if not self.errors:
            return {"samples": 0, "error": "no paired truth/estimate samples"}
        e = [v for _t, v in self.errors]
        e_sorted = sorted(e)
        return {
            "mode": self.mode,
            "samples": len(e),
            "mean_err_m": round(sum(e) / len(e), 2),
            "p50_err_m": round(e_sorted[len(e) // 2], 2),
            "p95_err_m": round(e_sorted[int(len(e) * 0.95)], 2),
            "max_err_m": round(max(e), 2),
            "injected_sigma_m": self.model.sigma,
            "injected_latency_s": self.model.latency,
            "injected_rate_hz": round(1.0 / self.model.period, 2),
            "outages": self.model.resets,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", default="tcp:127.0.0.1:5760")
    ap.add_argument("--mode", choices=["extnav", "gpsinput"], default="extnav")
    ap.add_argument("--duration", type=float, default=120.0)
    # The class default is 180 (SIGMA_IRIDIUM_NO_ELEV, the published Iridium NEXT figure).
    ap.add_argument("--sigma", type=float, default=DopplerErrorModel.SIGMA_IRIDIUM_NO_ELEV)
    ap.add_argument("--latency", type=float, default=2.0)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--outage-p", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--report", default=None)
    a = ap.parse_args()

    conn = mavutil.mavlink_connection(a.connect, source_system=1, source_component=191)
    print(f"waiting for heartbeat on {a.connect} ...", flush=True)
    conn.wait_heartbeat(timeout=60)
    print(f"connected: system {conn.target_system}", flush=True)

    conn.mav.request_data_stream_send(conn.target_system, conn.target_component,
                                      mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1)

    h = Harness(conn, a.mode,
                DopplerErrorModel(sigma_m=a.sigma, latency_s=a.latency,
                                  rate_hz=a.rate, outage_p=a.outage_p, seed=a.seed))
    end = time.time() + a.duration
    next_sample = 0.0
    while time.time() < end:
        now = time.time()
        h.pump()
        h.send_position(now)
        h.send_flow(now)
        if now >= next_sample:
            next_sample = now + 0.2
            h.sample_error(now)
        time.sleep(0.005)

    s = h.summary()
    print(json.dumps(s, indent=2))
    if a.report:
        os.makedirs(os.path.dirname(a.report), exist_ok=True)
        with open(a.report, "w") as f:
            json.dump(s, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
