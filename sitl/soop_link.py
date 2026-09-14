#!/usr/bin/env python3
"""
Feed ArduCopter SITL a fix as bad as an Iridium Doppler solve, and measure the EKF.

Reads SITL ground truth, degrades it into something an Iridium Doppler solver could
plausibly produce, and feeds it back as MAVLink - then measures what the EKF makes of it
against the truth it never saw.

The point is NOT to prove the messages parse. It is to answer the question the whole
board rests on: can ArduPilot fly on a fix this bad, this late, this rarely?

WHAT THIS MODELS, AND WHAT IT NO LONGER MODELS. Read this before trusting it as a
rehearsal for the aircraft.

The ERROR MODEL is architecture-independent and still correct: how bad the fix is, how
late, how often, and what the EKF does with it does not depend on which processor
computed it. Everything this harness measures about flyability stands.

The DELIVERY MECHANISM does not. This was written when the SoOP chain was going to live
on a companion computer publishing GPS_INPUT (#232) over MAVLink, and the aircraft no
longer works that way: U13 (MAX2112) is ON the board and the H743 samples I/Q on PC4/PA4
and does the solve itself. An on-board solve does not arrive as GPS_INPUT from outside -
it needs an AP_GPS backend, or AP_ExternalAHRS, inside the firmware. That integration is
UNWRITTEN, and it is not a detail: the 5 Hz minimum and the hardcoded 50 m consistency
gate in AP_GPS::all_consistent() are properties of AP_GPS, so they still apply, but the
path a fix takes to reach them is different and has never been exercised.

So this remains the right tool for "can it fly on this", and is NOT a test of the
integration the board actually needs. Keeping the companion path modelled is still
worth it - SERIAL6 on P71-P74 means a companion remains a supported option - but do not
read a passing run as evidence that the on-board route works.

WHY THE ERROR MODEL LOOKS LIKE THIS
-----------------------------------
Signals-of-opportunity Doppler positioning is not GPS with bigger error bars. Three
properties matter and all three make life harder:

  * It is SLOW. A Doppler solution needs an observation arc across a satellite pass, so
    fixes arrive at ~1 Hz at best, not 5-10 Hz.
  * It is LATE. The arc has to be observed before it can be solved, so the fix describes
    where the aircraft WAS, by a second or more.
  * Its error is CORRELATED, not white. Geometry and clock error drift slowly, so the
    solution has a wandering bias. This is the one that matters most: white noise averages
    out inside the EKF and a naive simulation of it would flatter the design badly. The
    bias term here is a random walk for exactly that reason.

Defaults are deliberately pessimistic. If the aircraft flies on these, the real thing has
margin. Tighten them only against measured receiver performance, never to make a test pass.

MODES
-----
  --mode extnav    VISION_POSITION_ESTIMATE, local NED  (what defaults.parm ships)
  --mode gpsinput  GPS_INPUT, global lat/lon            (the alternative)

Both are implemented so the choice is settled on measured error rather than on argument.
See docs/SENSORS.md.

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
    """Latency, a slow random-walk bias, white noise and outages.

    THE SIGMA IS NOW SOURCED. It was `[A] 20 m` - an assumption, and the single number
    every SITL result in this project inherits. Checked against the literature on
    2026-09-04, 20 m turns out to be very close to the BEST published result rather than
    a typical one:

        ~180 m   mean eastward error, ~380 m MAE   Iridium NEXT, WITHOUT elevation aiding
         656 m   Doppler-only, a SINGLE Iridium NEXT satellite
       289.5 m   single satellite, Doppler + azimuth DOA
    400-1200 m   along-track, Iridium instantaneous positioning
        22.7 m   4 Iridium + 1 Orbcomm - FIVE satellites, TWO constellations, STATIC rx

    So 20 m described a five-satellite dual-constellation static solution, and was being
    applied to single-constellation Iridium on a moving quadcopter. Optimistic by roughly
    an order of magnitude.

    WHY THIS IS NOT FIXED BY BETTER HARDWARE. The dominant error is ephemeris, not the
    receiver: TLE orbit error "could be several kilometers and is considered the main
    source of positioning inaccuracy", and a 3 km / 3 m/s ephemeris error alone induces
    position errors "of more than several km". A better SDR, TCXO, LNA or antenna raises
    SNR - necessary to detect bursts at all - but does not move the accuracy ceiling.

    DEFAULT IS NOW 180 m, the published mean for Iridium NEXT without elevation aiding,
    which is the configuration this aircraft flies today. Two levers reduce it and the
    aircraft already carries both:

      * barometric elevation aiding - the 180 m figure is explicitly "without" it, and
        constraining altitude collapses a 3-unknown solve to 2. Pass sigma_m=<lower> once
        the solution actually uses the baro.
      * INS coupling - published as "up to 180% improvement" over Doppler alone. That is
        what the EKF does with EK3_SRC*; it is already the architecture.

    TWO STRUCTURAL LEVERS THE ABOVE UNDERSTATES (added 2026-09-04, docs/BENCHMARK.md).
    "Not fixed by better hardware" is true and stays true. It should NOT be read as
    "180 m is the floor" - the ephemeris term is closed by ARCHITECTURE, not by parts:

      * MULTI-CONSTELLATION. Iridium alone is 66 satellites in 6 planes and the geometry
        is the binding constraint. Published: 22.7 m with 4 Iridium + 1 Orbcomm, and
        5.1 m with 4 Starlink + 2 OneWeb + 1 Orbcomm + 1 Iridium, both static. The cost
        is receiver complexity, not a better antenna.
      * DIFFERENTIAL, against a base receiver at a KNOWN position. Reported 0.60-0.81 m
        RMSE over 33-36 km baselines. Note double-differencing alone does NOT cancel
        ephemeris error - it is non-linear in baseline - so a separate ephemeris
        correction step is required; differencing removes the CLOCK terms.

        This is architecturally available to this aircraft: the SDR chain is already
        laptop-side, and the ELRS MAVLink link (1470 B/s) carries base observables with
        room to spare - 6 satellites at 5 Hz is 324 B/s framed, 22% of the link.
        It costs the "autonomous" part of the claim: the system becomes dependent on a
        ground station and degrades to single-receiver 180 m out of range, exactly as
        RTK degrades to single-point GNSS. A real trade, not a free win.

    NONE of these figures is a measurement of this antenna on this airframe. They are
    literature. Phase 1 of the plan is what makes the number [M].

    Replace this with a MEASURED sigma as soon as the ground test runs: antenna +
    SAWbird + RTL-SDR + gr-iridium reports per-burst frequency, so the real number is
    obtainable on a desk without the aircraft. See docs/SENSORS.md.

    WHAT THIS MEANS FOR THE PROJECT'S CLAIM. Doppler at 180 m is not a precision sensor.
    It is a DRIFT-BOUNDING one: coarse, but absolute and non-divergent, where an IMU is
    precise and diverges quadratically. "Ultra precise GNSS-denied" is a precise relative
    sensor whose drift is bounded by a coarse absolute one - not either alone.
    """

    # Published figures, so nobody has to re-derive them. metres.
    SIGMA_IRIDIUM_NO_ELEV = 180.0    # mean eastward error, Iridium NEXT, no elev aiding
    SIGMA_IRIDIUM_MAE = 380.0        # mean absolute error, same conditions
    SIGMA_SINGLE_SAT = 656.0         # Doppler-only, one satellite
    SIGMA_SINGLE_SAT_DOA = 289.5     # one satellite, + azimuth DOA
    SIGMA_BEST_MULTI = 22.7          # 4 Iridium + 1 Orbcomm, static - BEST CASE, not typical

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
    # Doppler velocity is far more precise than Doppler position - the range-rate is
    # measured directly, while position accumulates geometry and clock error. 0.3 m/s is
    # a deliberately unflattering figure for a decent L-band receiver.
    VEL_SIGMA = 0.3
    FLOW_SIGMA = 0.02          # rad/s; a decent camera flow solution
    PRX_MAX_CM = 400           # sensor ceiling reported to ArduPilot, cm
    PRX_CLEAR_CM = 350         # "nothing there" reading, deliberately BELOW the max.
                               # Reporting exactly max_distance reads as an invalid
                               # sample rather than a clear one, and proximity then has
                               # no data at all.

    def rng_v(self):
        return self.model.rng.gauss(0.0, self.VEL_SIGMA)

    def __init__(self, conn, mode, model, flow_hz=20.0, flow_quality=180, bias_m=0.0,
                 honest_quality=False, mirror_gps=True):
        self.vel_sigma = self.VEL_SIGMA
        # MIRROR THE LIVE GPS ONTO INSTANCE 2 WHILE GPS1 IS HEALTHY.
        #
        # AP_Arming requires all GPS instances to agree within a hardcoded 50 m
        # (AP_GPS::all_consistent, AP_GPS.cpp:1520). A companion that publishes its own
        # raw Doppler solution from boot - sigma 180 m against a healthy receiver -
        # breaches that gate on roughly half of ground arming attempts, which measured
        # 2026-09-05 as 'Arm: GPS positions differ by 129.2m'. No real companion would
        # publish a solution it knows is worse than the GPS already on the aircraft:
        # it mirrors the live fix (this aircraft is NOT GNSS-denied while GPS1 is up)
        # and switches to the Doppler solution only when GPS1 dies. That is also exactly
        # what GPS_AUTO_SWITCH 1 (UseBest) expects at the moment of denial.
        #
        # The denied-phase measurements are unaffected: from the denial instant this
        # behaves byte-for-byte as it did before, so the recorded bimodal distributions
        # in scenarios.py remain valid for what they measured.
        self.mirror_gps = mirror_gps
        # Last time a 3D fix arrived on GPS1 (GPS_RAW_INT = instance 0 = the real
        # receiver; the injected instance reports as GPS2_RAW). Tracked in pump() off
        # the harness's own clock instead of msg._timestamp, whose units differ across
        # pymavlink versions and connection types - exactly the silent assumption this
        # project keeps getting burned by.
        self._gps1_rx_t = None
        # HONEST QUALITY REPORTING. See send_position for why this exists and what it
        # changes; in short, the dead-reckon applet can only see the quality fields the
        # companion CHOOSES to publish, and publishing a flattering constant makes the
        # aircraft's entire GPS-loss mitigation unreachable.
        self.honest_quality = honest_quality
        # A deliberate constant offset, used only to prove the error measurement is real.
        # If the harness reports roughly this much error, it is genuinely comparing the
        # EKF against truth. If it reports ~0, it is comparing something to itself.
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
        self.truth_track = []         # (n, e) of where the aircraft REALLY was
        self.track = []               # (t, truth_n, truth_e, est_n, est_e) for inspection
        self.alt_track = []           # height above launch, for the flow-ceiling test
        self.alt_track_denied = None  # set to [] at denial; only these count for a ceiling
        self.t0 = time.time()

    # ---- inbound -------------------------------------------------------
    def pump(self):
        """Read everything pending. THE ONLY READER - see the note in scenarios.py.

        Returns the number of real (non-BAD_DATA) messages consumed, so the caller can
        run its link watchdog off this instead of reading in parallel.
        """
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
                # NOTE: msg.vx/vy/vz are the EKF's OWN velocity estimate. They must never
                # be injected back - see _truth_velocity below.
            elif t == "GPS_RAW_INT":
                if getattr(msg, "fix_type", 0) >= 3:
                    self._gps1_rx_t = time.time()
            elif t == "ATTITUDE":
                self.yaw = msg.yaw

    def _truth_velocity(self, new):
        """Differentiate SIMSTATE to get TRUE velocity.

        This must not come from GLOBAL_POSITION_INT. That message's vx/vy/vz are the
        EKF's own velocity estimate, and injecting them back as a GPS measurement closes
        a positive feedback loop: any estimator error is fed in as independent evidence
        for itself and grows without bound.

        The symptom was spectacular and easy to misread. Over 70 s it looked like a clean
        20 m hold. Over 340 s the aircraft sat still while its estimated position ran away
        to several kilometres - and because the divergence depended on the noise
        realisation, some seeds stayed bounded and it looked like marginal stability in
        the vehicle's control loop rather than a fault in the test rig.

        SIMSTATE carries no velocity field, so differentiate its position. Truth is noise
        free, which makes a plain difference quotient perfectly adequate.
        """
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
        # GPS1 alive? A 3D fix seen within the last 2 s on the harness's own clock.
        # Stale means GPS_RAW_INT stopped updating - exactly the state right after
        # SIM_GPS1_ENABLE 0 at denial.
        gps1_alive = (self._gps1_rx_t is not None
                      and (time.time() - self._gps1_rx_t) < 2.0)
        for _ready, dn, de, dd in self.model.due(now):
            # The offset is applied only once armed. On the ground ArduPilot requires all
            # GPS instances to agree within 50 m (AP_Arming.cpp:741, hardcoded), so a
            # deliberate 100 m bias makes the aircraft refuse to arm and the canary never
            # gets to measure anything.
            dn += self.bias_m if self.bias_active else 0.0
            usec = int(now * 1e6)
            if self.mode == "extnav":
                self.m.mav.vision_position_estimate_send(
                    usec, dn, de, dd, 0.0, 0.0, 0.0,
                    reset_counter=self.model.resets)
            else:
                # Mirror decision per published fix. While GPS1 is healthy and no
                # deliberate canary bias is active, instance 2 carries the LIVE fix
                # (truth here) so arming's 50 m consistency gate sees two agreeing
                # receivers. At denial GPS1 goes stale and the SAME publish path
                # hands over to the Doppler solution - the switchover a real
                # companion performs, exercised for free.
                mirror = (self.mirror_gps and not self.bias_active and gps1_alive)
                if mirror:
                    mlat, mlon = self.truth[0], self.truth[1]
                    malt = self.truth[2]
                    # HEALTHY, SOURCE-FAITHFUL quality for a mirrored fix: the
                    # companion is repeating a live GNSS receiver, so it publishes
                    # GNSS-class numbers, not the Doppler solution's sigma. Anything
                    # worse would make GPS_AUTO_SWITCH 1 (UseBest) and the EKF blend
                    # weights treat the MIRROR as the degraded source while the real
                    # receiver is still the best one available.
                    msacc, mhacc, mnsats = 0.3, 2.0, 12
                else:
                    mlat, mlon = ned_to_latlon(dn, de, self.origin[0], self.origin[1])
                    malt = self.origin[2] - dd
                    msacc, mhacc, mnsats = self._quality(now)
                lat, lon = mlat, mlon
                # KEYWORDS, not positional. gps_input_send takes 18 required arguments and
                # getting the order wrong is silent: an earlier version put fix_type into
                # the time_week slot, which raised only because the count was also wrong.
                # Had the count matched, it would have injected garbage that looked fine.
                #
                # ignore_flags tells ArduPilot which fields to disregard. A Doppler solver
                # produces position, not velocity, so the velocity fields and their
                # accuracy are marked absent rather than sent as a confident zero -
                # claiming "velocity is exactly 0" would be worse than saying nothing.
                # VELOCITY IS REPORTED, NOT IGNORED - and that is the physics, not a
                # convenience. Doppler measures range-rate, so velocity is the NATIVE
                # observable of a signals-of-opportunity receiver; position is what you
                # derive from it over a pass. Reporting position while declaring velocity
                # unknown gets it backwards.
                #
                # It does NOT measurably improve accuracy - measured over four seeds it
                # was a wash (30.7 m mean with, 30.9 m without). The EKF derives velocity
                # from successive positions and the IMU perfectly well. Sent because it is
                # what the instrument measures, not because the estimator needs it. See
                # the soop_no_velocity scenario and docs/SENSORS.md.
                vn = self.vel[0] + self.rng_v()
                ve = self.vel[1] + self.rng_v()
                vd = self.vel[2] + self.rng_v()
                self.m.mav.gps_input_send(
                    time_usec=usec,
                    # ZERO-BASED INSTANCE INDEX, and it must match the instance whose
                    # GPS_TYPEn is 14. AP_GPS_MAV.cpp:51 does
                    #     if (state.instance != packet.gps_id) return;
                    # so sending gps_id 0 against GPS2_TYPE targets the REAL receiver,
                    # whose driver is not AP_GPS_MAV, and every message is dropped in
                    # silence - no error, no warning, just no second GPS ever appearing.
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
        """The quality fields the companion publishes - and they are a DESIGN DECISION.

        WHY THIS MATTERS MORE THAN IT LOOKS. copter-deadreckon-home.lua decides the fix
        has gone bad from exactly two GPS quantities:

            gps:speed_accuracy(primary) > DR_GPS_SACC_MAX   (0.8 m/s as shipped)
            gps:num_sats(primary)       < DR_GPS_SAT_MIN    (6 as shipped)

        Both come straight from the GPS_INPUT message the companion sends. A companion
        that publishes a flattering constant - as this harness did, 8 satellites and
        0.3 m/s forever - reports a PERFECTLY HEALTHY GPS no matter how bad its Doppler
        solution actually is. The applet's GPS-bad path then never fires, and the only
        remaining trigger is the EKF failsafe, which is stochastic.

        That is measurable, and it was measured: across 32 runs, EVERY run in which the
        applet completed its return to RTL stayed bounded (13/13) and every run in which
        it did not diverged (0/13 held), Fisher exact p = 0.00012. The "divergence rate"
        was the applet-trigger rate.

        So the honest mode degrades the published quality when the solution IS degraded -
        which is what docs/SENSORS.md means by "honest accuracy fields", made concrete.
        A real Doppler solver knows this: residuals, satellite count in the solve, and
        geometry all tell it when the fix is weak.
        """
        if not self.honest_quality:
            return self.vel_sigma, self.model.sigma, 8
        # In or just out of an outage the solution is stale or reacquiring. Report it.
        stale = now < self.model.outage_until + 2.0
        if stale:
            return 3.0, self.model.sigma * 3.0, 4
        return self.vel_sigma, self.model.sigma, 8

    def send_flow(self, now):
        """Emit flow derived from the vehicle's actual motion.

        This used to send flow_rate 0.0 on every message, which is NOT "no flow" - it is a
        confident claim that the aircraft is not moving. The EKF fuses that as a
        zero-velocity update, so the very scenario meant to show flow-only navigation
        drifting instead held position beautifully, on a measurement that was a fiction.

        Optical flow is the angular rate at which ground features cross the sensor:

            flow_rate ~ horizontal velocity / height above ground

        so it needs both the body-frame velocity and the height - which is the same
        coupling docs/SENSORS.md is about. Below a metre the quotient explodes, so
        quality is reported as 0 rather than emitting a huge bogus rate.
        """
        if now < self.next_flow:
            return
        self.next_flow = now + self.flow_dt

        vn, ve, _vd = self.vel
        c, s_ = math.cos(self.yaw), math.sin(self.yaw)
        vx_body = vn * c + ve * s_          # forward
        vy_body = -vn * s_ + ve * c         # right

        if self.agl < 1.0:
            rate_x = rate_y = 0.0
            quality = 0                     # honest: no usable scale this low
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
        """Emit OBSTACLE_DISTANCE as the 8-sensor ToF ring would.

        Eight sectors at 45 deg, which is exactly what AP_Proximity_Boundary_3D bins into
        (PROXIMITY_NUM_SECTORS 8), so the ring's geometry and ArduPilot's internal model
        line up one-to-one rather than being resampled.

        `wall_at_m` puts an obstacle in the forward sector only, which is how the avoidance
        behaviour is actually exercised: the aircraft should refuse to continue toward it
        while remaining free to move any other way.
        """
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
        # KEYWORDS. This message takes nine required arguments and an earlier positional
        # call silently put the frame id into angle_offset - the same class of bug that
        # made gps_input_send inject garbage. Name every field.
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
    # THE CLASS DEFAULT IS 180 (SIGMA_IRIDIUM_NO_ELEV, the published Iridium NEXT
    # figure). This CLI default stayed at the retracted 20.0, so running soop_link.py
    # standalone silently reproduced the optimistic model that scenarios.py had already
    # stopped using - the same figure docs/SENSORS.md records as "optimistic by roughly
    # an order of magnitude, and every SITL number in this repository inherited it".
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

    # SITL sends almost nothing until asked; GPS_GLOBAL_ORIGIN is requested separately
    # by the harness, since it is not part of any stream group.
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
