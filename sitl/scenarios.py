#!/usr/bin/env python3
"""Fly ArduCopter SITL through the GNSS-denied sequence and measure what the EKF does."""
import argparse, json, math, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soop_link import Harness, DopplerErrorModel, latlon_to_ned

from pymavlink import mavutil

SRC_CHAN = 9           # RC9 carries RC9_OPTION 90, "EKF Source Set"
SRC_PWM = {1: 1000, 2: 1500, 3: 2000}

BOUNDARY_SIGMA_M = 20.0

SCENARIOS = {
    "baseline_gps": dict(
        mode=None, deny_at=None, src=1,
        why="GPS throughout. The floor - anything worse than this is the chain's fault.",
        max_p95=3.0),
    "soop_gpsinput": dict(
        mode="gpsinput", deny_at=40, src=1, startup={"GPS2_TYPE": 14}, rate=5.0,
        why="THE SHIPPED CONFIGURATION. GPS denied; SoOP arrives as GPS_INPUT on instance 2 "
            "at 5 Hz - the companion interpolates up from the ~1 Hz Doppler solution. "
            "INFORMATIONAL, not pass/fail. The outcome is BIMODAL - it holds (24-70 m) "
            "or it runs away (270 m), and it ran away on 1 seed of 6. See the "
            "distribution below, and soop_dropout for the same effect at 3 of 6.",
        max_p95=None, informational=True, diverges_above=120.0),
    "soop_raw_1hz": dict(
        mode="gpsinput", deny_at=40, src=1, startup={"GPS2_TYPE": 14}, rate=1.0,
        why="NEGATIVE RESULT. Publishing at the raw ~1 Hz solution rate must FAIL to arm: "
            "ArduPilot's GPS arming check rejects it as 'GPS 2: Bad fix'. 2 Hz also fails; "
            "5 Hz passes. This is why the companion must interpolate.",
        max_p95=None, expect_arm_failure="GPS 2"),
    "soop_no_velocity": dict(
        mode="gpsinput", deny_at=40, src=1, startup={"GPS2_TYPE": 14}, rate=5.0,
        no_velocity=True,
        why="What sending velocity is worth. Identical to soop_gpsinput but with the "
            "GPS_INPUT velocity fields marked ignored, as a position-only solver would. "
            "Classified against the same divergence boundary: it has read 138.5 and "
            "161.8 m, i.e. DIVERGED both times, where soop_gpsinput mostly holds. Note "
            "soop_link.py records an earlier four-seed comparison finding velocity made "
            "no difference (30.7 vs 30.9 m mean) - with a bimodal outcome, neither n=2 "
            "nor n=4 settles it. Needs --repeat.",
        max_p95=None, informational=True, diverges_above=120.0),
    "soop_dropout": dict(
        mode="gpsinput", deny_at=40, src=1, outage_p=0.25, startup={"GPS2_TYPE": 14},
        rate=5.0,
        why="SoOP itself drops out repeatedly during denial. THE OUTCOME IS BIMODAL - it "
            "either holds (43-80 m) or runs away (217-457 m), and it ran away on 3 of 6 "
            "seeds. A single run is a coin toss, so this is INFORMATIONAL with the "
            "divergence classification reported. See the measured distribution below. "
            "AND SINCE SIGMA WENT 20 -> 180 m IT USED TO USUALLY CANNOT ARM: pre-streaming "
            "a 180 m-sigma fix as GPS2 while real GPS1 was up tripped AP_Arming's "
            "hardcoded 50 m two-receiver consistency gate (measured 2026-09-05: 'Arm: "
            "GPS positions differ by 129.2m'). FIXED the same day in soop_link.py - the "
            "harness now MIRRORS the live GPS onto instance 2 while GPS1 is healthy and "
            "hands over at denial, like a real companion. soop_arming_180m is the "
            "tripwire for that mirror; a failed-to-arm run here now means IT regressed.",
        max_p95=None, informational=True, diverges_above=120.0),
    # Does the camera earn its weight?
    "soop_dropout_flow": dict(
        mode="gpsinput", deny_at=40, src=2, outage_p=0.25, rate=5.0,
        startup={"GPS2_TYPE": 14, "EK3_SRC2_POSXY": 3, "EK3_SRC2_VELXY": 5},
        why="THE CAMERA'S VALUE, MEASURED - AND IT IS ZERO HERE. soop_dropout with the "
            "EKF taking position from the SoOP fix and VELOCITY FROM OPTICAL FLOW, a "
            "source-set combination defaults.parm does not offer. Run 8 each: BOTH arms "
            "diverged 3/8. Flow did not reduce the divergence rate, and the held runs "
            "were slightly WORSE with it (median p95 57.7 m against 46.8 m).",
        max_p95=None, informational=True, diverges_above=120.0),

    # Negative result, and it guards the indoor build.
    "proximity_absent": dict(
        mode=None, deny_at=None, src=1, startup={"PRX1_TYPE": 2},
        why="NEGATIVE RESULT, MEASURED. PRX1_TYPE 2 with NO proximity ring fitted "
            "REFUSES TO ARM: 'Arm: PRX1: No Data'. So defaults.parm must NOT ship the "
            "proximity parameters - the ToF ring is an off-board add-on, and a board "
            "that will not arm without a part you have not wired yet is a board that "
            "cannot fly. Set PRX1_TYPE 2 only once the ring is publishing.",
        max_p95=None, expect_arm_failure="PRX1"),

    # If it does.
    "soop_dropout_honest": dict(
        mode="gpsinput", deny_at=40, src=1, outage_p=0.25, rate=5.0,
        startup={"GPS2_TYPE": 14}, honest_quality=True,
        why="THE COMPANION TELLS THE TRUTH. soop_dropout with degraded quality fields "
            "published while the SoOP solution is stale, so the dead-reckon applet can "
            "actually SEE the fix go bad instead of waiting for a stochastic EKF "
            "failsafe. Compare its divergence rate against soop_dropout under --repeat.",
        max_p95=None, informational=True, diverges_above=120.0),

    # IF not the camera, then what?
    "soop_dropout_lowlat": dict(
        mode="gpsinput", deny_at=40, src=1, outage_p=0.25, rate=5.0, latency=0.5,
        startup={"GPS2_TYPE": 14},
        why="LATENCY SENSITIVITY. soop_dropout with the SoOP fix arriving 0.5 s late "
            "instead of 2.0 s, everything else identical. Latency is the property most "
            "likely to drive a position-loop instability, and it is fixable in the "
            "companion - timestamp at capture, do not timestamp at publish.",
        max_p95=None, informational=True, diverges_above=120.0),
    "soop_dropout_lowsigma": dict(
        mode="gpsinput", deny_at=40, src=1, outage_p=0.25, rate=5.0, sigma=10.0,
        startup={"GPS2_TYPE": 14},
        why="ACCURACY SENSITIVITY. soop_dropout with a 10 m SoOP solution instead of "
            "20 m, everything else identical. This is what a better Doppler solution "
            "buys, as against what a better sensor suite buys.",
        max_p95=None, informational=True, diverges_above=120.0),

    # Regression guard for the 50 m two-receiver arming gate.
    "soop_arming_180m": dict(
        mode="gpsinput", deny_at=None, src=1, startup={"GPS2_TYPE": 14}, rate=5.0,
        why="ARMING REGRESSION at sigma 180 m. GPS2 carries the SoOP fix and GPS1 "
            "stays healthy throughout; arming must succeed because the companion "
            "mirrors the live GPS onto instance 2 while it is healthy (the 50 m gate, "
            "AP_GPS.cpp:1520). Failed-to-arm here means the mirror regressed - NOT a "
            "flake, and not the same failure as soop_dropout's denial-phase modes.",
        max_p95=None, informational=True),

    "extnav_1hz": dict(
        mode="extnav", deny_at=40, src=3, rate=1.0,
        startup={"VISO_TYPE": 1, "EK3_SRC3_POSXY": 6},
        why="Why the SoOP fix is a GPS and not ExternalNav. AP_VISUALODOM_TIMEOUT_MS is "
            "300 ms, so at 1 Hz VisOdom health FLAPS - arming is intermittent and fusion "
            "drops out constantly. Recorded, not asserted.",
        max_p95=None, informational=True),
    "measurement_canary": dict(
        mode="gpsinput", deny_at=40, src=1, startup={"GPS2_TYPE": 14}, rate=5.0,
        bias_m=100.0,
        why="CANARY. Injects a deliberate 100 m north offset. The harness MUST report "
            "roughly 100 m of error - if it reports a small number it is comparing the "
            "EKF against itself and every other figure in this report is meaningless.",
        max_p95=None, expect_error_near=(100.0, 40.0)),
    "proximity_ring": dict(
        mode=None, deny_at=None, src=1, startup={"PRX1_TYPE": 2},
        obstacle_m=2.0, push_forward=True, prestream_s=30,
        why="Proximity ring end-to-end: MAVLink OBSTACLE_DISTANCE must produce a "
            "healthy PRX1 backend, clear prearm, and airborne flight with live "
            "proximity data. Validates the ToF ring software path before ordering "
            "the sensors.",
        max_p95=None, informational=True),
    "rangefinder_ceiling": dict(
        mode=None, deny_at=25, src=2, rngfnd_max=15.0, climb_to=25.0, takeoff_alt=4,
        why="INVESTIGATION. The flow altitude ceiling is real but is enforced through "
            "AC_Avoid's velocity limiting, which a GUIDED position command bypasses - so "
            "this scenario cannot demonstrate it. Recorded, with the mechanism traced.",
        max_p95=None, informational=True),
    "flow_only": dict(
        mode=None, deny_at=40, src=2,
        why="No position source at all: flow and baro only. Drifts in XY by design - "
            "recorded to show how far, not as a pass/fail.",
        max_p95=None, informational=True),

    # --- control-link failsafes ------------------------------------------------------
    # Defaults.parm ships no FS_* parameters at all.
    "rc_loss": dict(
        mode="gpsinput", deny_at=40, src=1, startup={"GPS2_TYPE": 14}, rate=5.0,
        rc_fail_at=70, fs_thr=1,
        why="LATE CUT. Manual control is lost while the aircraft is flying on a SoOP "
            "fix, at t+70 - by which time the applet has ALREADY taken it to RTL (~t+60 "
            "on the shipped FS_EKF_ACTION 0). So this measures that radio loss does not "
            "DISTURB an applet-commanded recovery; it does NOT exercise the radio "
            "failsafe transition, because there is no transition left to make. "
            "rc_loss_early is the scenario that tests the transition.",
        max_p95=None, expect_mode="RTL", informational=True),

    "rc_loss_early": dict(
        mode="gpsinput", deny_at=40, src=1, startup={"GPS2_TYPE": 14}, rate=5.0,
        rc_fail_at=44, fs_thr=1, watch_ekf=True,
        why="EARLY CUT. Radio is lost 4 s into the denial, BEFORE the dead-reckon applet "
            "has commanded anything, so the RTL transition is genuinely observed rather "
            "than inherited. Radio failsafe and the applet are both live and both want "
            "to own the response - this records which one does.",
        max_p95=None, expect_mode="RTL", informational=True),

    # The experiment that decided defaults.parm, kept as a regression guard.
    "rc_loss_dr": dict(
        mode="gpsinput", deny_at=40, src=1,
        startup={"GPS2_TYPE": 14, "FS_EKF_ACTION": 1}, rate=5.0,
        rc_fail_at=70, fs_thr=1, watch_ekf=True,
        why="THE REJECTED ALTERNATIVE, kept as a counter-example. Boots the stock EKF "
            "failsafe (FS_EKF_ACTION 1) that this board no longer ships, and shows why: "
            "the aircraft reaches RTL at t+70 and the failsafe CANCELS it into LAND at "
            "t+78. rc_loss still reports PASS on it, because it asserts RTL was entered "
            "rather than that it survived - which is exactly how the defect hid. Compare "
            "against rc_loss/deadreckon on the shipped FS_EKF_ACTION 0.",
        max_p95=None, expect_mode="RTL", informational=True),
    "ekf_failsafe": dict(
        mode="gpsinput", deny_at=40, src=1, startup={"GPS2_TYPE": 14}, rate=5.0,
        watch_ekf=True,
        why="Does a 1 Hz-derived fix trip FS_EKF_ACTION on its own? Stock FS_EKF_THRESH "
            "is tuned against a 5 Hz GPS, and a LAND triggered by nothing worse than a "
            "slow position source would be a serious defect. NOTE: on the shipped "
            "FS_EKF_ACTION 0 the 'EKF Failsafe' STATUSTEXT is EXPECTED - ACTION 0 warns "
            "and takes no action. The verdict therefore asserts on whether the aircraft "
            "went to a failsafe-commanded mode (LAND / ALT_HOLD) after the annunciation, "
            "not on whether the annunciation happened.",
        max_p95=None),
    "deadreckon": dict(
        mode="gpsinput", deny_at=40, src=1,
        startup={"GPS2_TYPE": 14}, rate=5.0,
        watch_ekf=True, dr_scenario=True,
        why="The dead-reckon applet end-to-end. With DR_ENABLE 1 fitted and the stock "
            "EKF failsafe DISABLED at boot (the applet REPLACES it as this board's "
            "GPS-loss response - the matched-set decision in defaults.parm), denying "
            "GPS mid-flight must produce Guided_NoGPS with the applet flying home, then "
            "DR_NEXT_MODE -1 restoring the prior mode when GPS recovers. Verdict text "
            "reports the DR mode transitions.",
        max_p95=None, informational=True),
}


class LinkDead(Exception):
    """The simulator stopped talking. Fail the scenario rather than spin on it."""


def drain(conn, state):
    """Read everything pending and note whether anything arrived."""
    got = 0
    while True:
        m = conn.recv_match(blocking=False)
        if m is None:
            break
        # BAD_DATA is what a dead or desynced socket produces endlessly. Counting it as
        # traffic keeps the watchdog permanently satisfied while nothing real arrives.
        if m.get_type() != "BAD_DATA":
            got += 1
    now = time.time()
    if got:
        state["last"] = now
    elif now - state.get("last", now) > 15:
        raise LinkDead(f"no MAVLink for {now - state['last']:.0f}s - simulator gone")
    return got


def wait_for(conn, cond, timeout, what):
    """Drain every pending message each pass."""
    end = time.time() + timeout
    state = {"last": time.time()}
    while time.time() < end:
        drain(conn, state)
        if cond():
            return True
        time.sleep(0.02)
    print(f"    timed out waiting for {what}")
    return False


def setp(conn, name, value):
    conn.mav.param_set_send(conn.target_system, conn.target_component,
                            name.encode(), float(value),
                            mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    time.sleep(0.05)


def src_set(conn, which):
    """Select an EKF source set through MAV_CMD_DO_AUX_FUNCTION."""
    conn.mav.command_long_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_DO_AUX_FUNCTION, 0,
        90,               # EKF_SOURCE_SET
        {1: 0, 2: 1, 3: 2}[which],   # low / middle / high
        0, 0, 0, 0, 0)


def rc_src(conn, _which=None):
    """Send a valid RC frame so Copter stops reporting "RC not found"."""
    conn.mav.rc_channels_override_send(
        conn.target_system, conn.target_component,
        1500, 1500, 1000, 1500, 1500, 1500, 1500, 1500)


def _mode_name(conn):
    """Current flight mode as a string, or None if no heartbeat has arrived yet."""
    hb = conn.messages.get("HEARTBEAT")
    if hb is None:
        return None
    try:
        return mavutil.mode_string_v10(hb)
    except Exception:
        return str(hb.custom_mode)


TRACK_PATH = None


def run(name, spec, connect, duration, seed):
    print(f"\n=== {name} ===\n    {spec['why']}")
    try:
        return _run(name, spec, connect, duration, seed)
    except LinkDead as e:
        print(f"    LINK DEAD: {e}")
        return {"scenario": name, "error": f"link dead: {e}"}


def _run(name, spec, connect, duration, seed):
    scenario_start = time.time()
    # sysid 255 = ground station. RC overrides sent from the vehicle's own system id are
    # ignored, which presents as an unshakeable "PreArm: RC not found".
    conn = mavutil.mavlink_connection(connect, source_system=255, source_component=190)
    if not conn.wait_heartbeat(timeout=60):
        return {"scenario": name, "error": "no heartbeat"}
    conn.wait_heartbeat()

    conn.mav.request_data_stream_send(conn.target_system, conn.target_component,
                                      mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1)

    setp(conn, f"RC{SRC_CHAN}_OPTION", 90)
    setp(conn, "SIM_GPS1_ENABLE", 1)
    setp(conn, "SIM_SPEEDUP", 1)

    # --- turn on what the board ships disabled -------------------------------
    if spec["mode"] == "extnav":
        pass    # VISO_TYPE / EK3_SRC3_POSXY are baked in at boot - see `startup` above
    elif spec["mode"] == "gpsinput":
        setp(conn, "GPS_AUTO_SWITCH", 1)        # UseBest: automatic failover on denial
    setp(conn, "RNGFND1_TYPE", 100)             # SITL rangefinder - flow needs a height
    setp(conn, "RNGFND1_MAX", 15.0)
    setp(conn, "RNGFND1_ORIENT", 25)

    # --- SITL-only prearm blockers -------------------------------------------
    # Neither is a board problem.
    if spec.get("obstacle_m"):
        setp(conn, "AVOID_ENABLE", 2)        # bit 1 = UseProximitySensor
        setp(conn, "AVOID_BEHAVE", 1)        # Stop, not Slide
        setp(conn, "AVOID_MARGIN", 2)        # metres
    if spec.get("rngfnd_max"):
        setp(conn, "RNGFND1_MAX", spec["rngfnd_max"])
        setp(conn, "EK3_SRC2_VELXY", 5)      # flow is the velocity source in SRC2
        # The flow altitude ceiling is enforced by AC_Avoid, not by the flight MODE.
        setp(conn, "AVOID_ENABLE", 7)        # fence + proximity + beacon
    setp(conn, "RELAY1_FUNCTION", 0)
    # Every arming check except RC Channels (bit 6).
    setp(conn, "ARMING_CHECK", 1047998)
    # Radio failsafe off.
    setp(conn, "FS_THR_ENABLE", 0)
    setp(conn, "SIM_RC_FAIL", 0)
    setp(conn, "DISARM_DELAY", 0)
    rc_src(conn, 1)
    time.sleep(3)

    # --- wait for a usable GPS position before doing anything ---
    ok = wait_for(conn, lambda: (conn.messages.get("GLOBAL_POSITION_INT") is not None
                                 and conn.messages.get("SIMSTATE") is not None),
                  90, "position messages")
    if not ok:
        return {"scenario": name, "error": "no position stream"}

    # A 3D fix takes ~30 s in SITL. Arming before it lands you in a prearm loop that
    # looks like a configuration fault and is really just impatience.
    ok = wait_for(conn, lambda: (conn.messages.get("GPS_RAW_INT") is not None
                                 and conn.messages["GPS_RAW_INT"].fix_type >= 3),
                  120, "GPS 3D fix")
    if not ok:
        return {"scenario": name, "error": "no GPS fix"}
    print("    GPS fix acquired")

    # A fix is not a position estimate.
    for _ in range(60):
        rc_src(conn, 1)
        while conn.recv_match(blocking=False) is not None:
            pass
        e = conn.messages.get("EKF_STATUS_REPORT")
        if e and (e.flags & 0x0C) == 0x0C:      # horiz pos abs + horiz vel
            break
        time.sleep(0.5)
    print("    EKF position estimate ready")

    # --- arm and take off ---
    # Build the injector now and start streaming before arming.
    model = DopplerErrorModel(sigma_m=spec.get("sigma",
                                               DopplerErrorModel.SIGMA_IRIDIUM_NO_ELEV),
                              latency_s=spec.get("latency", 2.0),
                              rate_hz=spec.get("rate", 1.0),
                              outage_p=0.0, seed=seed)
    h = Harness(conn, spec["mode"] or "extnav", model,
                bias_m=spec.get("bias_m", 0.0),
                honest_quality=spec.get("honest_quality", False))
    h.send_velocity = not spec.get("no_velocity", False)
    o = conn.messages.get("GPS_GLOBAL_ORIGIN")
    if o:
        h.origin = (o.latitude * 1e-7, o.longitude * 1e-7, o.altitude * 1e-3)
        print(f"    EKF origin {h.origin[0]:.6f}, {h.origin[1]:.6f}")

    if spec["mode"] or spec.get("obstacle_m"):
        print(f"    pre-streaming {spec.get('prestream_s', 12)}s so the estimator is "
              f"healthy at arm time")
        t_end = time.time() + spec.get("prestream_s", 12)
        while time.time() < t_end:
            h.pump()
            if spec["mode"]:
                h.send_position(time.time())
            h.send_flow(time.time())
            if spec.get("obstacle_m"):
                h.send_obstacles(time.time(), wall_at_m=None)
            time.sleep(0.005)

    if spec.get("obstacle_m"):
        print(f"      obstacle messages sent during pre-stream: "
              f"{getattr(h, 'obst_sent', 0)}")
    conn.set_mode_apm("GUIDED")
    time.sleep(1)
    prearm = []
    for _ in range(40):
        rc_src(conn, 1)
        if spec["mode"]:
            h.send_position(time.time())
            h.send_flow(time.time())
        if spec.get("obstacle_m"):
            # Keep obstacle data flowing through the arm loop too.
            h.send_obstacles(time.time(), wall_at_m=None)
        conn.mav.command_long_send(conn.target_system, conn.target_component,
                                   mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                                   0, 1, 0, 0, 0, 0, 0, 0)
        t_end = time.time() + 1.5
        while time.time() < t_end:
            msg = conn.recv_match(blocking=False)
            if msg and msg.get_type() == "STATUSTEXT":
                txt = msg.text.strip()
                if ("PreArm" in txt or "Arm" in txt) and txt not in prearm:
                    prearm.append(txt)
            if spec["mode"]:
                h.send_position(time.time())
            if spec.get("obstacle_m"):
                h.send_obstacles(time.time(), wall_at_m=None)
            time.sleep(0.005)
        hb = conn.messages.get("HEARTBEAT")
        if hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            break
    else:
        for t in prearm:
            print(f"      {t}")
        want = spec.get("expect_arm_failure")
        if want and any(want in t for t in prearm):
            print(f"    PASS (refused to arm, as it must: {want})")
            return {"scenario": name, "why": spec["why"], "prearm": prearm,
                    "verdict": f"PASS - refused to arm on {want}, which is the point"}
        return {"scenario": name, "error": "failed to arm", "prearm": prearm}
    # Confirm arming from a fresh heartbeat.
    drain(conn, {"last": time.time()})
    hb = conn.messages.get("HEARTBEAT")
    if not (hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)):
        return {"scenario": name, "error": "armed, then disarmed before takeoff",
                "prearm": prearm}
    print("    armed")

    # Take off below whatever ceiling the scenario is testing.
    tko = spec.get("takeoff_alt", 15)
    conn.mav.command_long_send(conn.target_system, conn.target_component,
                               mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                               0, 0, 0, 0, 0, 0, 0, tko)

    # Read the ACK.
    tko_ack, tko_txt = None, []
    t_ack = time.time()
    while time.time() - t_ack < 5:
        m = conn.recv_match(blocking=False)
        if m is None:
            time.sleep(0.02)
            continue
        if m.get_type() == "COMMAND_ACK" and m.command == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF:
            tko_ack = m.result
        elif m.get_type() == "STATUSTEXT":
            tko_txt.append(m.text)
    if tko_ack not in (None, mavutil.mavlink.MAV_RESULT_ACCEPTED):
        print(f"    takeoff REJECTED, MAV_RESULT={tko_ack}")
    for t in tko_txt[-6:]:
        print(f"      {t}")

    # Verify the climb.
    def rel_alt():
        m = conn.messages.get("GLOBAL_POSITION_INT")
        return None if m is None else m.relative_alt / 1000.0

    climbed = wait_for(conn, lambda: (rel_alt() or 0.0) >= 0.8 * tko,
                       45, f"climb to {0.8 * tko:.1f} m")
    if not climbed:
        got = rel_alt()
        print(f"    FAILED TO TAKE OFF - reached {got if got is not None else 0.0:.2f} m "
              f"of {tko} m")
        return {"scenario": name, "why": spec["why"],
                "error": f"armed but did not take off (reached "
                         f"{got if got is not None else 0.0:.2f} m of {tko} m)",
                "prearm": prearm}
    print(f"    airborne at {rel_alt():.1f} m")

    # --- the run ---
    for _ in range(40):
        conn.mav.command_long_send(
            conn.target_system, conn.target_component,
            mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
            mavutil.mavlink.MAVLINK_MSG_ID_GPS_GLOBAL_ORIGIN, 0, 0, 0, 0, 0, 0)
        time.sleep(0.25)
        while conn.recv_match(blocking=False) is not None:
            pass
        if conn.messages.get("GPS_GLOBAL_ORIGIN"):
            break

    # T0 is the only CLOCK.
    h.t0 = time.time()
    # How long arm-and-takeoff took. Reported so a slow setup is visible in the JSON;
    # not used in any comparison.
    res_setup_s = round(time.time() - scenario_start, 1)
    denied = False
    rc_dead = False
    mode_at_cut = None
    mode_changes = []
    last_mode = None
    ekf_msgs = []
    # Time of the first real EKF-failsafe annunciation, on the same clock as mode_changes.
    first_ekf_fs_t = None
    dr_msgs = []
    post_cut_msgs = []
    next_sample = 0.0
    leg, next_leg = 0, 0.0
    end = time.time() + duration
    err_before, err_after = [], []

    link = {"last": time.time()}
    while time.time() < end:
        now = time.time()
        t = now - h.t0
        if h.pump():
            link["last"] = now
        elif now - link["last"] > 15:
            raise LinkDead(f"no MAVLink for {now - link['last']:.0f}s - simulator gone")

        # push straight at the injected wall, or climb at the flow ceiling
        if spec.get("push_forward") and now >= next_leg and h.origin:
            next_leg = now + 10
            conn.mav.set_position_target_local_ned_send(
                0, conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                0b0000111111111000, 30, 0, -15, 0,0,0, 0,0,0, 0,0)
        elif spec.get("climb_to") and now >= next_leg and h.origin:
            next_leg = now + 10
            conn.mav.set_position_target_local_ned_send(
                0, conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                0b0000111111111000, 0, 0, -spec["climb_to"], 0,0,0, 0,0,0, 0,0)
        # square pattern, 25 m legs, so the estimator has motion to work with
        elif now >= next_leg and h.origin:
            next_leg = now + 20
            n, e = [(25, 0), (25, 25), (0, 25), (0, 0)][leg % 4]
            leg += 1
            conn.mav.set_position_target_local_ned_send(
                0, conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                0b0000111111111000, n, e, -15, 0,0,0, 0,0,0, 0,0)

        if spec["deny_at"] is not None and not denied and t >= spec["deny_at"]:
            denied = True
            setp(conn, "SIM_GPS1_ENABLE", 0)
            model.outage_p = spec.get("outage_p", 0.05)   # only now
            h.alt_track_denied = []                       # start the ceiling clock here
            h.bias_active = spec.get("bias_m", 0.0) != 0.0
            rc_src(conn, spec["src"])
            print(f"    t+{int(t)}s  GPS DENIED, source set -> {spec['src']}")

        # Cut the radio. SIM_RC_FAIL makes SITL stop producing RC, and the harness must
        # also stop sending overrides - an override keeps the failsafe from ever firing.
        if spec.get("rc_fail_at") is not None and not rc_dead and t >= spec["rc_fail_at"]:
            rc_dead = True
            mode_at_cut = _mode_name(conn)
            setp(conn, "FS_THR_ENABLE", spec.get("fs_thr", 1))
            setp(conn, "SIM_RC_FAIL", 1)
            print(f"    t+{int(t)}s  RC CUT, FS_THR_ENABLE="
                  f"{spec.get('fs_thr', 1)} (mode was {mode_at_cut})")

        if spec["mode"]:
            h.send_position(now)
        h.send_flow(now)
        if spec.get("obstacle_m"):
            # Keep obstacle traffic flowing through the whole run (not just pre-stream).
            h.send_obstacles(now, wall_at_m=spec["obstacle_m"] if spec.get("push_forward") and denied else None)
        if int(t * 5) % 10 == 0 and not rc_dead:
            rc_src(conn, spec["src"] if denied else 1)   # RC must keep arriving

        # Mode changes the aircraft makes on its own are the result these scenarios are
        # after: a failsafe is visible as a mode it chose without being asked.
        _st = conn.messages.get("STATUSTEXT")
        if _st is not None and spec.get("dr_scenario"):
            _t = _st.text.strip()
            if _t.startswith("DR:") and _t not in dr_msgs:
                dr_msgs.append(_t)
                print(f"    t+{int(t)}s  {_t}")
        if _st is not None and spec.get("watch_ekf"):
            _t = _st.text.strip()
            if ("EKF" in _t and ("ailsafe" in _t or "variance" in _t or "Bad" in _t)
                    and _t not in ekf_msgs):
                ekf_msgs.append(_t)
                if first_ekf_fs_t is None and "ailsafe" in _t and "leared" not in _t:
                    first_ekf_fs_t = round(t, 1)
                print(f"    t+{int(t)}s  {_t}")

        # After a radio cut, capture everything the aircraft says.
        if rc_dead and _st is not None:
            _t = _st.text.strip()
            if _t and _t not in post_cut_msgs:
                post_cut_msgs.append(_t)
                print(f"    t+{int(t)}s  [after cut] {_t}")

        _m = _mode_name(conn)
        if _m and _m != last_mode:
            if last_mode is not None:
                mode_changes.append((round(t, 1), last_mode, _m))
                print(f"    t+{int(t)}s  MODE {last_mode} -> {_m}")
            last_mode = _m

        if now >= next_sample:
            next_sample = now + 0.2
            before = len(h.errors)
            h.sample_error(now)
            if len(h.errors) > before:
                # Not `(denied and err_after or err_before)`.
                (err_after if denied else err_before).append(h.errors[-1][1])

        time.sleep(0.005)

    setp(conn, "SIM_GPS1_ENABLE", 1)
    conn.set_mode_apm("LAND")

    tr = [p for p in h.truth_track]
    if tr:
        n0, e0 = tr[0]
        excursion = max(math.hypot(n - n0, e - e0) for n, e in tr)
        res_track = {"truth_excursion_m": round(excursion, 1),
                     "truth_samples": len(tr)}
    else:
        res_track = {}

    def stats(v):
        if not v:
            return None
        s = sorted(v)
        return {"n": len(v), "mean": round(sum(v)/len(v), 2),
                "p95": round(s[int(len(s)*0.95)], 2), "max": round(max(s), 2)}

    denied_alts = getattr(h, "alt_track_denied", None) or []
    all_alts = getattr(h, "alt_track", None) or []
    alts = [a for a in denied_alts if a is not None] or [a for a in all_alts if a is not None]
    res = {"scenario": name, "why": spec["why"], "vehicle": res_track,
           "max_alt_m": max(alts) if alts else 0.0,
           "before_denial": stats(err_before), "during_denial": stats(err_after),
           "injected": {"sigma_m": model.sigma, "latency_s": model.latency,
                        "rate_hz": round(1/model.period, 2), "outages": model.resets}}

    # Scenarios that never deny GPS are judged on the whole flight, not on a phase
    # that does not exist.
    if spec.get("expect_arm_failure"):
        res["verdict"] = (f"UNEXPECTED - armed despite expecting refusal on "
                          f"{spec['expect_arm_failure']}")
    d = res["during_denial"] if spec["deny_at"] is not None else res["before_denial"]
    res["judged_on"] = "during_denial" if spec["deny_at"] is not None else "whole_flight"
    res["setup_s"] = res_setup_s
    if mode_changes:
        res["mode_changes"] = [{"t": t_, "from": a, "to": b} for t_, a, b in mode_changes]
    if spec.get("rc_fail_at") is not None:
        res["rc"] = {"cut_at_s": spec["rc_fail_at"], "mode_at_cut": mode_at_cut,
                     "fs_thr_enable": spec.get("fs_thr", 0),
                     "final_mode": _mode_name(conn)}
    if spec.get("watch_ekf"):
        res["ekf_failsafe_messages"] = ekf_msgs
    if post_cut_msgs:
        res["messages_after_rc_cut"] = post_cut_msgs

    if spec.get("dr_scenario") is not None:
        after_deny = [(t_, a, b) for t_, a, b in mode_changes
                      if t_ >= (spec["deny_at"] or 0)]
        _gng = "guided_nogps"
        entered_gng = any(b.lower() == _gng for _t_, _a, b in after_deny)
        left_gng = any(a.lower() == _gng for _t_, a, _b in after_deny)
        res["dr_messages"] = dr_msgs
        if not dr_msgs:
            res["verdict"] = ("FAIL - no DR: STATUSTEXT at all; the applet is not "
                              "running (script missing from APM/scripts/ or SCR params "
                              "not loaded)")
        elif not entered_gng:
            res["verdict"] = ("FAIL - DR messages present but the aircraft never "
                              "entered Guided_NoGPS; modes after denial: "
                              f"{[b for _t, _a, b in after_deny] or 'none'}")
        elif not left_gng:
            res["verdict"] = ("FAIL - entered Guided_NoGPS but never left it; the "
                              "applet never returned the prior mode")
        else:
            recovery = [b for _t, a, b in after_deny if a.lower() == _gng]
            res["verdict"] = (f"PASS - applet entered Guided_NoGPS and recovered to "
                              f"{recovery}")
    elif spec.get("expect_mode") is not None:
        want = spec["expect_mode"]
        after = [b for t_, a, b in mode_changes if t_ >= spec.get("rc_fail_at", 0)]
        # Assert the state, not the transition.
        entered = want in after
        was_already = (mode_at_cut == want)
        how = ("entered it after the cut" if entered
               else f"was already in {want} when the radio was cut")
        res["verdict"] = (
            f"PASS - radio lost, aircraft in {want} on a non-GPS position ({how})"
            if (entered or was_already) else
            f"FAIL - radio lost and the aircraft was not in {want}; "
            f"mode at cut {mode_at_cut}, modes after: {after or 'none'}"
            + (f"; it said: {post_cut_msgs[:4]}" if post_cut_msgs else
               "; and it said NOTHING - the failsafe never fired at all"))
    elif spec.get("watch_ekf"):
        _FS_COMMANDED = {"LAND", "ALT_HOLD"}
        after_fs = [(t_, a, b) for t_, a, b in mode_changes
                    if first_ekf_fs_t is not None and t_ >= first_ekf_fs_t]
        acted = [f"{a}->{b} at t+{t_:g}s" for t_, a, b in after_fs
                 if b.upper() in _FS_COMMANDED]
        res["ekf_failsafe_acted"] = acted or None
        res["mode_changes_after_ekf_fs"] = [f"{a}->{b} at t+{t_:g}s"
                                            for t_, a, b in after_fs] or None
        if acted:
            res["verdict"] = (
                f"FAIL - EKF failsafe fired at t+{first_ekf_fs_t:g}s and the aircraft "
                f"then went to a failsafe-commanded mode on its own: {acted}. On "
                f"FS_EKF_ACTION 0 it must annunciate and do nothing; this means the "
                f"applet was preempted or FS_EKF_ACTION is not 0 in the set under test")
        elif ekf_msgs:
            res["verdict"] = (
                f"PASS - EKF failsafe ANNUNCIATED on the SoOP fix but took no action, "
                f"which is what FS_EKF_ACTION 0 promises; said: {ekf_msgs[:3]}"
                + (f"; other modes after it (applet, not failsafe): "
                   f"{res['mode_changes_after_ekf_fs']}"
                   if res.get("mode_changes_after_ekf_fs") else ""))
        else:
            res["verdict"] = "PASS - a 1 Hz-derived fix did not trip an EKF failsafe"
    elif d is None:
        res["verdict"] = "NO DATA - the EKF published no absolute position to compare"
    elif spec.get("expect_error_near") is not None:
        # The canary is ONE-SIDED, because only one side of it proves anything.
        want, tol = spec["expect_error_near"]
        got = d["mean"]
        if got < want - tol:
            res["verdict"] = (f"FAIL - injected {want:g} m offset but measured only "
                              f"{got} m; the harness is comparing the EKF against "
                              f"itself and every other figure here is meaningless")
        elif got <= want + tol:
            res["verdict"] = (f"PASS - reported {got} m against a {want:g} m injected "
                              f"offset, so the measurement is real")
        else:
            res["verdict"] = (f"PASS - reported {got} m against a {want:g} m injected "
                              f"offset, so the measurement is real. The excess is the "
                              f"flight's own divergence on top of the injection, which "
                              f"is a result rather than a measurement fault")
    elif spec.get("harness_defect"):
        res["verdict"] = ("HARNESS DEFECT - the path is proven to work outside this "
                          "harness (685 msgs handled, no complaint); this scenario "
                          "does not reproduce it and the reason is unknown")
    elif spec.get("expect_blocked_within") is not None:
        moved = res_track.get("truth_excursion_m", 999)
        lim = spec["expect_blocked_within"]
        res["verdict"] = (f"PASS - avoidance held it to {moved} m against a 30 m command"
                          if moved <= lim else
                          f"FAIL - travelled {moved} m toward a wall 2 m away; "
                          f"AC_Avoid did not stop it")
    elif spec.get("expect_ceiling") is not None:
        alt = res.get("max_alt_m", 0)
        lim = spec["expect_ceiling"]
        res["verdict"] = (f"PASS - climbed to {alt:.1f} m, held under the {lim:.1f} m "
                          f"flow ceiling" if alt <= lim + 2.0 else
                          f"FAIL - reached {alt:.1f} m, above the {lim:.1f} m ceiling "
                          f"0.7*RNGFND1_MAX-1 should impose")
    elif spec.get("informational"):
        # Where a divergence boundary has been measured, say which side of it this run landed on.
        lim = spec.get("diverges_above")
        if lim is not None:
            sigma_now = spec.get("sigma", DopplerErrorModel.SIGMA_IRIDIUM_NO_ELEV)
            if abs(sigma_now - BOUNDARY_SIGMA_M) > 1e-6:
                res["verdict"] = (
                    f"INFO - p95 {d['p95']} m during denial. The {lim:g} m divergence "
                    f"boundary DOES NOT APPLY here: it was measured at sigma "
                    f"{BOUNDARY_SIGMA_M:g} m and this run is at sigma {sigma_now:g} m. "
                    f"Re-measure the boundary at the current sigma before reading a "
                    f"hold/runaway verdict off it")
            else:
                diverged = d["p95"] > lim
                res["diverged"] = diverged
                res["verdict"] = (
                    f"INFO - {'DIVERGED' if diverged else 'held'}: p95 {d['p95']} m "
                    f"({'above' if diverged else 'below'} the measured {lim:g} m boundary; "
                    f"bounded runs <=79.6 m, diverged runs >=216.7 m over n=6 at sigma "
                    f"{BOUNDARY_SIGMA_M:g} m). "
                    f"Not a gate - this run is one sample of a bimodal outcome")
        else:
            res["verdict"] = f"INFO - p95 {d['p95']} m during denial (no pass/fail)"
    elif spec.get("max_p95") is not None:
        res["verdict"] = ("PASS" if d["p95"] <= spec["max_p95"]
                          else f"FAIL - p95 {d['p95']} m > {spec['max_p95']} m")
    else:
        # A scenario with no pass criterion still has to report something. An earlier
        # version raised KeyError here and lost the whole run's result.
        res["verdict"] = f"INFO - no pass criterion; p95 {d['p95']} m"
    print(f"    {res['verdict']}   [{res['judged_on']}] {d}")
    if res_track:
        print(f"      vehicle actually moved {res_track['truth_excursion_m']} m "
              f"from where it started")
    if TRACK_PATH:
        with open(TRACK_PATH, "w") as f:
            f.write("t,truth_n,truth_e,est_n,est_e\n")
            for row in h.track:
                f.write(",".join(str(v) for v in row) + "\n")
        print(f"      trajectory -> {TRACK_PATH}")
    conn.close()          # SITL accepts one client; leaving it open blocks the next run
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", default="tcp:127.0.0.1:5760")
    ap.add_argument("--duration", type=float, default=110.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rate", type=float, default=None,
                    help="override the injection rate, to find what ArduPilot will accept")
    ap.add_argument("--only", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--startup-params", default=None,
                    help="print the parameters a scenario needs AT BOOT, and exit")
    ap.add_argument("--report", default="/tmp/nav/sitl/report.json")
    ap.add_argument("--track", default=None,
                    help="write the truth-vs-estimate trajectory to a CSV for inspection")
    a = ap.parse_args()

    if a.startup_params:
        for k, v in SCENARIOS[a.startup_params].get("startup", {}).items():
            print(f"{k} {v}")
        return 0

    if a.list:
        for k, v in SCENARIOS.items():
            print(f"{k:16} {v['why']}")
        return 0

    global TRACK_PATH
    TRACK_PATH = a.track
    names = [a.only] if a.only else list(SCENARIOS)
    specs = {n: dict(SCENARIOS[n]) for n in names}
    if a.rate is not None:
        for sp in specs.values():
            sp["rate"] = a.rate
    out = [run(n, specs[n], a.connect, a.duration, a.seed) for n in names]
    os.makedirs(os.path.dirname(a.report), exist_ok=True)
    json.dump(out, open(a.report, "w"), indent=2)
    print(f"\nreport: {a.report}")
    return 0 if all("FAIL" not in (r.get("verdict") or "") for r in out) else 1


if __name__ == "__main__":
    sys.exit(main())
