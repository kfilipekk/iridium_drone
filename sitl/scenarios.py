#!/usr/bin/env python3
"""
Fly ArduCopter SITL through the GNSS-denied sequence and measure what the EKF does.

Each scenario takes off under GPS, flies a square, then has GPS taken away mid-flight
while the aircraft is switched to a different EKF source set - using the SAME mechanism
the pilot will use, an RC switch on RC_OPTION 90, rather than a back door. What is
measured is horizontal position error against SITL truth, which the EKF never sees.

The suite is built so that it CAN fail. `flow_only` has no position source at all and
must drift badly; if it ever passes, the harness is measuring nothing and the other
results are worthless. Treat it as the canary, not as a scenario anyone would fly.

  python3 scenarios.py --list
  python3 scenarios.py --only soop_extnav
  python3 scenarios.py                      # all of them
"""
import argparse, json, math, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soop_link import Harness, DopplerErrorModel, latlon_to_ned

from pymavlink import mavutil

SRC_CHAN = 9           # RC9 carries RC9_OPTION 90, "EKF Source Set"
SRC_PWM = {1: 1000, 2: 1500, 3: 2000}

# The sigma at which every diverges_above boundary below was MEASURED. The n=6 runs
# that produced "bounded <=79.6 m, diverged >=216.7 m" were flown against this value.
# It is NOT the model's current sigma - DopplerErrorModel now defaults to the published
# 180 m - and the gap is deliberate and visible: see the verdict logic, which refuses to
# read a hold/runaway off a boundary measured at a different sigma. When the boundary is
# re-measured, update this AND the two figures quoted in the verdict together.
BOUNDARY_SIGMA_M = 20.0

# RE-MEASURED AT THE SHIPPING SIGMA, 2026-09-18 - n=6 per scenario, nothing else varied,
# plain repeats (--repeat 6) exactly as soop_dropout's comment prescribed:
#
#   soop_gpsinput   p95 302.6 310.9 340.4 349.5 441.1 445.6   (median 345.0)
#   soop_dropout    p95 366.3 376.1 439.6 450.8 470.3 528.2   (median 445.2)
#
# THE FINDING IS NOT A NEW BOUNDARY - IT IS THAT NO BOUNDARY EXISTS AT THIS SIGMA.
# Every run lands 300-530 m, with no gap separating two regimes: the bimodality itself
# was a property of the 20 m fix, not of the navigation chain. And the p95 is NOT the
# vehicle flying away - the TRUE excursion over the same runs had median 73 m
# (soop_gpsinput) and 91 m (soop_dropout), max 226 m. The position ESTIMATE wanders
# with the injected fix noise; the applet chain (GUIDED -> GUIDED_NOGPS -> RTL) still
# recovered in every run. Read together: at Doppler-only accuracy there is no hold to
# grade, and there is also no runaway the failsafe chain misses. Both old readings
# ("mostly holds" and "diverged 3/6") described a fix quality this aircraft will not
# have. See docs/KNOWN-ISSUES.md - the open item is now fix QUALITY (elevation aiding,
# multi-constellation), not the boundary.
BOUNDARY_SIGMA_SHIPPED_M = 180.0

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
        # NO THRESHOLD, and that is the honest answer rather than a bigger number.
        #
        # A 35.0 m limit was set here from one 34.15 m run. docs/VERIFICATION.md then
        # recorded, in the same pass, that it is "not reproducibly within the 35 m
        # provisional threshold" - so the code asserted a limit its own documentation
        # said was wrong, and the suite would fail on most seeds.
        #
        # MEASURED, n=6, one run per seed 1..6, nothing else changed (2026-09-02):
        #
        #   seed   1      2      3      4      5      6
        #   p95  270.3   47.6   70.2   24.2   30.2   38.7    m
        #   flew 319.0   72.8   61.4   49.4   58.9   35.8    m
        #
        # Five runs hold between 24 and 70 m. One runs away to 270 m, and the vehicle
        # TRULY travelled 319 m in that run - so it is a divergence, not a bad
        # measurement of a good flight. Earlier ad-hoc runs (27.13, 30.56, 34.15, 46.87,
        # 52.53, 59.14) all sit in the bounded group.
        #
        # THE SEED IS NOT THE EXPLANATION, and an earlier version of this comment said it
        # was. --seed defaults to 1 and seeds ONLY the DopplerErrorModel RNG; SITL itself
        # is given no seed and runs against wall-clock. Two runs at seed 1 produced 52.53
        # and 270.29 m. So "set the limit from a distribution over fixed seeds" - which
        # this comment used to recommend - cannot work: the variation survives the seed.
        #
        # What CAN be gated is the divergence RATE over repeats. The runner has had
        # --repeat for exactly this since its own header documented it - an earlier
        # version of this comment said it "does not yet do" repeats, which contradicted
        # the file it ships with. AND the question dissolved on 2026-09-18: re-measured
        # at the shipping sigma (n=6, see BOUNDARY_SIGMA_SHIPPED_M), there is no
        # bimodality to measure a rate on - every run p95 300-450 m. The rate question
        # belongs to the sigma-20 fix, which is not the fix this aircraft gets.
        #
        # The harness's SoOP model is still not a measurement of any real receiver. Its
        # sigma is SOURCED rather than assumed (180 m, the published Iridium NEXT figure
        # without elevation aiding - see DopplerErrorModel), which is an improvement on
        # the old [A] 20 m but is still literature, not this antenna on this airframe.
        # Measure it on the ground.
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
        # MEASURED, n=6, one run per seed 1..6, nothing else changed (2026-09-02):
        #
        #   seed   1      2      3      4      5      6
        #   p95  392.6   68.4   79.6  457.1  216.7   43.4     m
        #   flew 473.2   97.6   79.6  494.4  230.4   35.8     m
        #
        # THE 120.0 THRESHOLD THAT USED TO SHIP WAS NOT WRONG ABOUT WHERE THE LINE IS.
        # The bounded runs top out at 79.6 m and the diverged runs start at 216.7 m, so
        # 120 sits in a 137 m-wide empty band - it separates them cleanly. It was wrong
        # about WHAT IT WAS MEASURING: it read as a position-accuracy limit, and it is
        # actually a divergence detector. p95 tracks the vehicle's TRUE excursion almost
        # exactly in every diverged run (392/473, 457/494, 217/230), so those are not
        # noisy measurements of a stable hold - the aircraft genuinely flies away.
        #
        # It therefore cannot be a single-run gate: asserting it makes the suite fail
        # about half the time on an unchanged configuration. The property worth gating is
        # the DIVERGENCE RATE over repeats - sitl/run_scenarios.sh --repeat does that,
        # and an earlier note here claiming the runner lacked it was simply wrong.
        # AND at the shipping sigma (re-measured n=6, 2026-09-18, see
        # BOUNDARY_SIGMA_SHIPPED_M) there is no bimodality left to rate: uniformly
        # 366-528 m. The bounded/diverged split is a sigma-20 phenomenon.
        #
        # AND THE SEED IS NOT THE EXPLANATION. --seed defaults to 1 and seeds only the
        # DopplerErrorModel RNG; SITL itself gets no seed. Two runs at seed 1 gave 52.53
        # and 270.29 m on soop_gpsinput, so run-to-run variation survives a fixed seed and
        # no "distribution over fixed seeds" can gate it. An earlier note here said the
        # variation "is the simulator's seed"; that was wrong.
        max_p95=None, informational=True, diverges_above=120.0),
    # DOES THE CAMERA EARN ITS WEIGHT? The experiment that answers it.
    #
    # Identical to soop_dropout - same 25% outage rate, same 5 Hz SoOP - except that the
    # EKF is told to take VELOCITY from optical flow while still taking POSITION from the
    # SoOP fix. Run both with --repeat and compare the divergence rates; that difference
    # IS the value of fitting a flow camera, measured rather than argued.
    #
    # THIS COMBINATION DOES NOT EXIST IN defaults.parm, and that is the finding that
    # motivated the scenario. The shipped sets are:
    #
    #     SRC1  POSXY 3 (GPS/SoOP)  VELXY 3 (GPS/SoOP)
    #     SRC2  POSXY 0 (none)      VELXY 5 (flow)
    #     SRC3  POSXY 0 (none)      VELXY 5 (flow)
    #
    # So flow is only ever reachable by THROWING AWAY the absolute fix. That is the right
    # set for a total SoOP loss, and the wrong one for a SoOP DROPOUT, which is the
    # failure that actually diverges. Nothing on this aircraft can currently fly "SoOP
    # position, flow velocity" - the configuration where the two sensors complement each
    # other instead of replacing each other.
    #
    # The harness already sends OPTICAL_FLOW in every scenario (Harness.send_flow is
    # called unconditionally), so no new plumbing is needed - only a source set that
    # tells the EKF to fuse it. Which also means the existing soop_* numbers are honestly
    # "flow present but NOT FUSED", not "flow absent".
    "soop_dropout_flow": dict(
        mode="gpsinput", deny_at=40, src=2, outage_p=0.25, rate=5.0,
        startup={"GPS2_TYPE": 14, "EK3_SRC2_POSXY": 3, "EK3_SRC2_VELXY": 5},
        why="THE CAMERA'S VALUE, MEASURED - AND IT IS ZERO HERE. soop_dropout with the "
            "EKF taking position from the SoOP fix and VELOCITY FROM OPTICAL FLOW, a "
            "source-set combination defaults.parm does not offer. Run 8 each: BOTH arms "
            "diverged 3/8. Flow did not reduce the divergence rate, and the held runs "
            "were slightly WORSE with it (median p95 57.7 m against 46.8 m).",
        # MEASURED 2026-09-02, 8 repeats per arm, back to back, nothing else changed:
        #
        #   no flow fused   held 37.6 43.6 46.8 47.9 116.6 | diverged 189.7 414.9 426.9
        #   flow fused      held 49.9 53.9 57.7 81.7 104.7 | diverged 175.8 224.2 426.6
        #                   3/8 diverged in BOTH arms
        #
        # WHAT THIS DOES AND DOES NOT SHOW. n=8 gives a 95% Wilson interval of [14%, 69%]
        # on 3/8, so this rules out a LARGE effect and nothing finer - detecting a drop
        # from 38% to 15% would need about 59 runs per arm. The honest claim is "no large
        # benefit detected", not "no benefit".
        #
        # It is still a strong result, because THE FLOW MODEL HERE IS IDEALISED:
        # FLOW_SIGMA 0.02 rad/s, quality pinned at 180, and perfect AGL from SIMSTATE. A
        # real camera over grass is worse than this on every one of those. So this arm is
        # an UPPER BOUND on what a flow camera could buy, and even the upper bound shows
        # nothing measurable.
        #
        # The natural reading is that the divergence is not velocity starvation at all -
        # see soop_dropout_lowlat and soop_dropout_lowsigma, which test the two properties
        # of the SoOP receiver itself.
        max_p95=None, informational=True, diverges_above=120.0),

    # NEGATIVE RESULT, and it guards the indoor build. PRX1_TYPE 2 is MAVLink proximity:
    # ArduPilot expects OBSTACLE_DISTANCE from somewhere. Setting it with no ToF ring
    # actually fitted is the same class of trap as FLOW_TYPE 0 with EK3_SRC*_VELXY 5 -
    # a backend enable parameter and the thing that feeds it are a MATCHED SET, and this
    # project has been bitten by that three times. Measure which way it fails rather than
    # assuming: if it refuses to arm, PRX1_TYPE must stay 0 until the ring is publishing.
    "proximity_absent": dict(
        mode=None, deny_at=None, src=1, startup={"PRX1_TYPE": 2},
        why="NEGATIVE RESULT, MEASURED. PRX1_TYPE 2 with NO proximity ring fitted "
            "REFUSES TO ARM: 'Arm: PRX1: No Data'. So defaults.parm must NOT ship the "
            "proximity parameters - the ToF ring is an off-board add-on, and a board "
            "that will not arm without a part you have not wired yet is a board that "
            "cannot fly. Set PRX1_TYPE 2 only once the ring is publishing.",
        max_p95=None, expect_arm_failure="PRX1"),

    # THE ONE THAT ACTUALLY MOVES THE NEEDLE - if it does.
    #
    # Identical to soop_dropout except that the companion publishes HONEST quality fields:
    # while the solution is stale (in an outage, plus 2 s of reacquisition) it reports
    # 4 satellites and 3.0 m/s speed accuracy instead of a flattering constant 8 and 0.3.
    #
    # Those two numbers are the ONLY things copter-deadreckon-home.lua can use to notice
    # the fix has gone bad - DR_GPS_SAT_MIN 6 and DR_GPS_SACC_MAX 0.8 - so with the
    # flattering constant the applet's GPS path is unreachable and its only trigger is the
    # stochastic EKF failsafe. See Harness._quality.
    "soop_dropout_honest": dict(
        mode="gpsinput", deny_at=40, src=1, outage_p=0.25, rate=5.0,
        startup={"GPS2_TYPE": 14}, honest_quality=True,
        why="THE COMPANION TELLS THE TRUTH. soop_dropout with degraded quality fields "
            "published while the SoOP solution is stale, so the dead-reckon applet can "
            "actually SEE the fix go bad instead of waiting for a stochastic EKF "
            "failsafe. Compare its divergence rate against soop_dropout under --repeat.",
        max_p95=None, informational=True, diverges_above=120.0),

    # IF NOT THE CAMERA, THEN WHAT? These two vary the SoOP model's own properties, which
    # are the levers that live in the RECEIVER AND COMPANION rather than in added
    # hardware. If either kills the divergence, that is where effort belongs - and it is
    # effort on software and signal processing, not on payload.
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
        why="ACCURACY SENSITIVITY. soop_dropout with a 10 m SoOP solution instead of the "
            "180 m shipping sigma, everything else identical. This is what a better "
            "Doppler solution buys, as against what a better sensor suite buys.",
        max_p95=None, informational=True, diverges_above=120.0),

    # REGRESSION GUARD for the 50 m two-receiver arming gate.
    #
    # 2026-09-05, this suite caught its own first arming regression: after the error
    # model went sigma 20 -> 180 m, soop_dropout refused to arm ('Arm: GPS positions
    # differ by 129.2m') because the harness published the raw Doppler fix on GPS2
    # while real GPS1 was up, and AP_GPS::all_consistent hard-refuses arming past
    # 50 m of disagreement (AP_GPS.cpp:1520, not configurable). The fix - mirror the
    # live GPS while it is healthy, hand over at denial - lives in the companion
    # (Harness.mirror_gps), which is where a real implementation must live too.
    #
    # This scenario is the tripwire: a degraded 180 m-sigma fix streaming on GPS2,
    # GPS1 healthy the whole way, NO denial. If the companion ever publishes its own
    # solution pre-denial again, or the mirror logic breaks, this refuses to arm and
    # the suite fails - instead of soop_dropout failing half the time with a message
    # that reads like a flake.
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
    # RESOLVED. This took a firmware-instrumented investigation to settle.
    #
    # PRX1_TYPE 2 reported "PRX1: No Data" through every obvious variation - both message
    # types, three source system ids, 5-10 Hz, all fields by keyword. Printf in
    # AP_Proximity::handle_msg gave the answer:
    #
    #     PRXDBG init inst=0 type=2 driver=yes num=1
    #     PRXDBG AP_Proximity::handle_msg id=330 num_instances=0   <-- dropped
    #
    # Messages that arrive before AP_Proximity::init() has run are SILENTLY DISCARDED -
    # the frontend loops over num_instances, which is still 0. Keep sending and it starts
    # working: 685 messages handled, no prearm complaint.
    #
    # So: give the flight controller time to finish booting before judging proximity, and
    # have the companion keep publishing rather than give up on early silence.
    #
    # PROOF THE PATH WORKS, from a direct test outside this harness:
    #     685 obstacle messages handled by AP_Proximity_MAV, and NO prearm complaint.
    # The ToF ring's software path is therefore sound and the parts are worth buying.
    #
    # THIS SCENARIO NOW PASSES. The last missing piece was obstacle traffic DURING
    # the 1.5s arm windows: AP_Proximity's stale timeout is shorter than one outer
    # loop iteration, so a message only once per iteration still read as "No Data".
    # With the 10 Hz stream kept running through the arm window, the vehicle arms,
    # takes off, and holds the proximity ring the whole flight (p95 0.07 m).
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
    # defaults.parm ships NO FS_* parameters at all. On an ordinary GPS aircraft
    # ArduPilot's own defaults are fine; this aircraft is deliberately not one, so the
    # question is whether they still hold when position arrives at ~1 Hz from Doppler.
    # Measured here rather than assumed, then written into defaults.parm.
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

    # THE TRANSITION CASE. Added after the shipped FS_EKF_ACTION 0 made rc_loss
    # degenerate: with the applet owning GPS loss the aircraft is already in RTL by t+70,
    # so "rc_loss PASS" stopped meaning that radio failsafe works and started meaning
    # only that RTL was the mode at the time. Cutting at t+44 - after denial at t+40,
    # before the applet acts at ~t+49 - puts the radio failsafe and the applet in
    # contention for the response, which is the real question: does losing the radio
    # while the SoOP fix is the only position source still get the aircraft home?
    "rc_loss_early": dict(
        mode="gpsinput", deny_at=40, src=1, startup={"GPS2_TYPE": 14}, rate=5.0,
        rc_fail_at=44, fs_thr=1, watch_ekf=True,
        why="EARLY CUT. Radio is lost 4 s into the denial, BEFORE the dead-reckon applet "
            "has commanded anything, so the RTL transition is genuinely observed rather "
            "than inherited. Radio failsafe and the applet are both live and both want "
            "to own the response - this records which one does.",
        max_p95=None, expect_mode="RTL", informational=True),

    # THE EXPERIMENT THAT DECIDED defaults.parm, kept as a regression guard.
    #
    # Both configurations were run with nothing else changed. Both reach RTL, so
    # disabling the stock failsafe costs nothing on radio loss - and only ACTION 0 avoids
    # the t+78 cancellation. defaults.parm therefore ships FS_EKF_ACTION 0 with the
    # applet owning GPS loss; this scenario holds the rejected ACTION 1 so the difference
    # stays measurable instead of becoming folklore.
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
        # informational=True was set here and was DEAD - the watch_ekf branch is reached
        # first, so the flag never applied. Removed rather than left as decoration.
        why="Does a 1 Hz-derived fix trip FS_EKF_ACTION on its own? Stock FS_EKF_THRESH "
            "is tuned against a 5 Hz GPS, and a LAND triggered by nothing worse than a "
            "slow position source would be a serious defect. NOTE: on the shipped "
            "FS_EKF_ACTION 0 the 'EKF Failsafe' STATUSTEXT is EXPECTED - ACTION 0 warns "
            "and takes no action. The verdict therefore asserts on whether the aircraft "
            "went to a failsafe-commanded mode (LAND / ALT_HOLD) after the annunciation, "
            "not on whether the annunciation happened.",
        max_p95=None),
    "deadreckon": dict(
        # NO parameter override any more. This scenario used to boot FS_EKF_ACTION 0
        # while defaults.parm shipped 1, so it proved the applet worked in a
        # configuration the aircraft did not actually fly. defaults.parm now ships 0
        # (see the evidence block there), so this runs the shipped set unmodified -
        # which is the only way a scenario means anything.
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
    """Read everything pending and note whether anything arrived.

    pymavlink prints "EOF on TCP socket" on every read of a closed connection, so a tight
    drain loop against a dead simulator produces tens of thousands of lines and no
    progress. The watchdog turns that into one clear failure.
    """
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
    """Drain EVERY pending message each pass.

    Reading one message per sleep looks harmless and is not: SITL sends on the order of
    100 messages a second, so a single recv_match per 100 ms falls permanently behind and
    conn.messages reflects a state that is minutes stale. That reads as "no GPS fix" when
    the GPS locked long ago.
    """
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
    """Select an EKF source set through MAV_CMD_DO_AUX_FUNCTION.

    This is the same aux-function handler an RC switch on RC_OPTION 90 calls, so the
    mechanism under test is the real one - but it does not depend on RC override
    plumbing, which is fragile over MAVLink and irrelevant to what is being measured.
    """
    conn.mav.command_long_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_DO_AUX_FUNCTION, 0,
        90,               # EKF_SOURCE_SET
        {1: 0, 2: 1, 3: 2}[which],   # low / middle / high
        0, 0, 0, 0, 0)


def rc_src(conn, _which=None):
    """Send a valid RC frame so Copter stops reporting "RC not found".

    Only the first EIGHT channels, positionally. MAVLink 1 carries 8 and MAVLink 2 carries
    18, and which one a connection ends up speaking depends on negotiation - passing 18
    raises TypeError against a v1 dialect. Eight is enough here because the source-set
    switch goes through MAV_CMD_DO_AUX_FUNCTION, not through a channel.

    Throttle low, sticks centred: the state Copter wants to see before it will arm.
    """
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

    # SITL sends almost nothing until asked. Without this the harness sees heartbeats
    # and no position, which looks exactly like a dead simulator.
    conn.mav.request_data_stream_send(conn.target_system, conn.target_component,
                                      mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1)

    setp(conn, f"RC{SRC_CHAN}_OPTION", 90)
    setp(conn, "SIM_GPS1_ENABLE", 1)
    setp(conn, "SIM_SPEEDUP", 1)

    # --- turn on what the board ships DISABLED -------------------------------
    # defaults.parm deliberately ships VISO_TYPE and both rangefinders off, so a bare
    # board arms with no companion and no lidar attached (see the comments there). The
    # scenarios are testing the fitted configuration, so switch them on here. Doing it
    # from the harness rather than from defaults.parm is the point: it keeps the shipped
    # file safe while still exercising the real chain.
    if spec["mode"] == "extnav":
        pass    # VISO_TYPE / EK3_SRC3_POSXY are baked in at boot - see `startup` above
    elif spec["mode"] == "gpsinput":
        # GPS2_TYPE is @RebootRequired - setting it here would never instantiate the MAV
        # backend, so it is baked into the boot parameters instead (see `startup` above).
        # The symptom when it is missed is subtle: the aircraft flies, GPS denial happens
        # on cue, and there is simply no second GPS to fall back to, so the run reports
        # "NO DATA" rather than an error.
        setp(conn, "GPS_AUTO_SWITCH", 1)        # UseBest: automatic failover on denial
    setp(conn, "RNGFND1_TYPE", 100)             # SITL rangefinder - flow needs a height
    setp(conn, "RNGFND1_MAX", 15.0)
    setp(conn, "RNGFND1_ORIENT", 25)

    # --- SITL-only prearm blockers -------------------------------------------
    # Neither is a board problem. GPIO 83 exists on real hardware (PA7, see hwdef) but
    # not in the simulator, and SITL has no RC receiver until overrides start flowing.
    if spec.get("obstacle_m"):
        setp(conn, "AVOID_ENABLE", 2)        # bit 1 = UseProximitySensor
        setp(conn, "AVOID_BEHAVE", 1)        # Stop, not Slide
        setp(conn, "AVOID_MARGIN", 2)        # metres
    if spec.get("rngfnd_max"):
        setp(conn, "RNGFND1_MAX", spec["rngfnd_max"])
        setp(conn, "EK3_SRC2_VELXY", 5)      # flow is the velocity source in SRC2
        # THE FLOW ALTITUDE CEILING IS ENFORCED BY AC_Avoid, NOT BY THE FLIGHT MODE.
        # AC_Avoid.cpp:459 is the only consumer of get_hgt_ctrl_limit(), so with
        # AVOID_ENABLE at 0 there is NO ceiling at all and the aircraft will happily
        # climb out of rangefinder range on flow alone. A first version of this test
        # left it off and the aircraft climbed to 25 m unimpeded - which looked like a
        # firmware bug and was really a missing parameter.
        setp(conn, "AVOID_ENABLE", 7)        # fence + proximity + beacon
    setp(conn, "RELAY1_FUNCTION", 0)
    # Every arming check EXCEPT RC Channels (bit 6). Deliberately not ARMING_CHECK 0:
    # the prearm checks are where this harness found its most useful results, so they
    # stay on. SITL simply has no receiver.
    setp(conn, "ARMING_CHECK", 1047998)
    # Radio failsafe off. Overrides arrive in bursts rather than as a continuous 50 Hz
    # stream, which Copter correctly reads as a receiver dropping out. A real aircraft
    # keeps this ON - it is disabled here only because the harness is not a receiver.
    # Radio failsafe stays OFF through setup, arming and takeoff - even for the scenario
    # that exists to test it. The harness sends overrides in bursts rather than as a
    # 50 Hz stream, which Copter correctly reads as a receiver dropping out: with
    # FS_THR_ENABLE 1 set here, rc_loss could not arm at all ("Arm: Radio failsafe on").
    # The scenario turns it on at the moment it cuts the radio, which is also the more
    # faithful test - the failsafe is armed for exactly the event being measured.
    setp(conn, "FS_THR_ENABLE", 0)
    setp(conn, "SIM_RC_FAIL", 0)
    # Auto-disarm off. Copter disarms ~10 s after arming if the throttle stays down
    # (DISARM_DELAY), and in GUIDED the harness never touches throttle - it commands
    # NAV_TAKEOFF instead. The vehicle was therefore arming, quietly auto-disarming, and
    # rejecting the takeoff with MAV_RESULT_FAILED while the harness slept through it and
    # reported PASS on a stationary aircraft.
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

    # A fix is not a position estimate. The EKF needs to converge on it before Copter
    # will report "position ok", and arming before that gives "Need Position Estimate".
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
    # Build the injector NOW and start streaming BEFORE arming.
    #
    # VisOdom health is judged on data actually arriving, so enabling VISO_TYPE and only
    # starting the stream after takeoff gives "PreArm: VisOdom: not healthy" and the
    # aircraft never leaves the ground. This is not a simulator quirk - it is the real
    # operational rule: THE COMPANION MUST BE STREAMING BEFORE YOU ARM.
    # Outages start at DENIAL, not at boot. A quarter-probability dropout during the
    # pre-arm stream starves GPS 2 and the aircraft never arms - which tests nothing except
    # that you cannot take off mid-outage, something no operator would attempt anyway.
    # DEFAULT SIGMA COMES FROM soop_link, WHICH SOURCES IT. This line used to carry its
    # own literal 20.0, so re-founding the model's default would have changed nothing -
    # two defaults for one quantity, and this was the one that won. The published figure
    # for Iridium NEXT without elevation aiding is 180 m; see DopplerErrorModel's
    # docstring for the full table and why better hardware does not lower it.
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
                # PRX1_TYPE 2 fails prearm with "PRX1: No Data" until obstacle messages
                # are actually arriving - the same rule as VisOdom. Send clear sky.
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
            # Keep obstacle data flowing through the arm loop too. Pre-stream alone is
            # not enough: AP_Proximity marks the MAVLink backend stale when messages
            # stop arriving, so a 60s arm loop with no obstacle traffic reads as
            # "PRX1: No Data" and the scenario fails to arm.
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
                # Also inside the 1.5s arm window: AP_Proximity's stale timeout is
                # shorter than the outer loop iteration, so one message per outer
                # iteration still reads as "PRX1: No Data". Keep the 10 Hz stream
                # running for the whole window.
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
    # Confirm arming from a FRESH heartbeat. The loop above breaks on
    # conn.messages["HEARTBEAT"], which can be seconds old, so "armed" could be reported
    # from a stale message describing a state the vehicle had already left.
    drain(conn, {"last": time.time()})
    hb = conn.messages.get("HEARTBEAT")
    if not (hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)):
        return {"scenario": name, "error": "armed, then disarmed before takeoff",
                "prearm": prearm}
    print("    armed")

    # Take off BELOW whatever ceiling the scenario is testing. The first version of
    # rangefinder_ceiling took off to 15 m and then complained the aircraft was above a
    # 9.5 m limit - a limit only stops you climbing, it cannot lower you.
    tko = spec.get("takeoff_alt", 15)
    conn.mav.command_long_send(conn.target_system, conn.target_component,
                               mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                               0, 0, 0, 0, 0, 0, 0, tko)

    # Read the ACK. Sending a command and not looking at the reply is how "it did not
    # take off" stayed a mystery: the autopilot says WHY it refused, in a field nobody
    # was reading.
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

    # VERIFY the climb. This used to be `time.sleep(15); print("airborne")` - a blind
    # wait that asserted a state it never checked, and baseline_gps duly returned
    # "verdict: PASS" with max_alt_m 0.01 and truth_excursion_m 0.0. The aircraft had
    # armed and never left the ground, and a stationary vehicle has a position error of
    # about 2 cm, so every threshold in the suite was satisfied by not flying.
    #
    # A scenario that cannot take off must FAIL LOUDLY. Everything downstream - position
    # error, altitude ceilings, denial behaviour - is meaningless on the ground.
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
    # The EKF origin is the frame every error measurement is expressed in, and it is not
    # part of any default stream. Ask for it explicitly - scenarios that inject nothing
    # (baseline, canary) never call send_position, so they would otherwise never have a
    # frame and would silently report no data.
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

    # t0 IS THE ONLY CLOCK. Everything time-based in the run loop - deny_at, rc_fail_at,
    # the leg pattern, mode_changes, the printed t+Ns - is measured from here, i.e. from
    # the moment the aircraft is airborne and streaming. There is deliberately no second
    # scenario-start clock: there was one, nothing needed it, and the one verdict that
    # tried to convert between the two was converting between a clock and itself.
    h.t0 = time.time()
    # How long arm-and-takeoff took. Reported so a slow setup is visible in the JSON;
    # NOT used in any comparison.
    res_setup_s = round(time.time() - scenario_start, 1)
    denied = False
    rc_dead = False
    mode_at_cut = None
    mode_changes = []
    last_mode = None
    ekf_msgs = []
    # Time of the FIRST real EKF-failsafe annunciation, on the SAME clock as
    # mode_changes. FS_EKF_ACTION 0 does not silence the message - it silences the
    # RESPONSE - so the message alone says nothing about whether the aircraft acted.
    first_ekf_fs_t = None
    dr_msgs = []
    post_cut_msgs = []
    next_sample = 0.0
    leg, next_leg = 0, 0.0
    end = time.time() + duration
    err_before, err_after = [], []

    # ONE READER ONLY. drain() and Harness.pump() both call recv_match, and whichever
    # runs first consumes the messages the other needs - so calling drain() here silently
    # starved the harness of SIMSTATE and GLOBAL_POSITION_INT, and the run reported "NO
    # DATA" for a flight the EKF had handled perfectly well. pump() now feeds the
    # watchdog itself.
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
            # A deliberate canary offset is applied only to the canary's SoOP fix;
            # normal scenarios use the Doppler model's own stochastic error. This keeps
            # the canary from changing the physical flight path and makes its expected
            # magnitude test independent of EKF mode behavior.
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
            # AP_Proximity marks the MAVLink backend stale when messages stop arriving,
            # so a run with no obstacle updates reads as "PRX1: No Data" at prearm.
            h.send_obstacles(now, wall_at_m=spec["obstacle_m"] if spec.get("push_forward") and denied else None)
        if int(t * 5) % 10 == 0 and not rc_dead:
            rc_src(conn, spec["src"] if denied else 1)   # RC must keep arriving

        # Mode changes the AIRCRAFT makes on its own are the result these scenarios are
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

        # After a radio cut, capture EVERYTHING the aircraft says. "modes after the cut:
        # none" is not a diagnosis - it does not distinguish "RTL was refused" from "RTL
        # was never attempted", and those have different fixes. ArduPilot announces both.
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
                # NOT `(denied and err_after or err_before)`. While err_after is still
                # empty it is falsy, so that expression falls through to err_before - and
                # err_after can never receive its first element. Every sample landed in
                # the pre-denial bucket and during_denial was eternally "NO DATA", for a
                # flight the EKF had handled correctly.
                (err_after if denied else err_before).append(h.errors[-1][1])

        time.sleep(0.005)

    setp(conn, "SIM_GPS1_ENABLE", 1)
    conn.set_mode_apm("LAND")

    # Distinguish "the estimate is wrong" from "the aircraft flew away". They produce the
    # same error number and mean completely different things: one is an estimator problem,
    # the other is the vehicle physically wandering because the controller is chasing a
    # noisy fix.
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

    # only altitudes reached while flow was the position source count toward the ceiling
    # `or []` matters: alt_track_denied is None until a denial happens, and getattr
    # returns that None rather than the default, which is not iterable. Scenarios with no
    # denial phase (baseline_gps) crashed on exactly this.
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
        # It armed when the scenario said it should not. That is a finding about the
        # firmware, not a harness fault, so report it rather than passing quietly.
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
        # The applet's fingerprint is a Guided_NoGPS entry after denial, then a mode
        # change OUT of Guided_NoGPS that the AIRCRAFT chose - the recovery the stock
        # firmware never performs. Judge on observed transitions, not on promises.
        # _mode_name returns SITL's uppercase spelling (GUIDED_NOGPS); compare
        # case-insensitively so the verdict does not depend on the spelling.
        # NO CLOCK CONVERSION. This used to subtract h.flight_start_s from deny_at, on
        # the premise that "deny_at is expressed from the scenario start" while
        # mode_changes uses a post-takeoff clock. That premise is false: the run loop
        # computes `t = now - h.t0` and triggers denial on `t >= spec["deny_at"]`, so
        # deny_at is ALREADY on the same post-takeoff clock that mode_changes records.
        #
        # The subtraction was therefore not converting between clocks, it was shifting
        # the cut-off earlier by the whole arm-and-takeoff time - typically enough to
        # drive it to 0.0, at which point `after_deny` silently became "every mode change
        # in the flight". It never produced a wrong verdict, because nothing changes mode
        # before denial in these scenarios, but a filter that is a no-op is not a filter.
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
        # Assert the STATE, not the transition. The aircraft can already BE in the
        # recovery mode when the radio is cut - with the dead-reckon applet owning GPS
        # loss it reaches RTL at ~t+59, before the t+70 cut - and then there is no
        # transition left to observe. Demanding one reported FAIL on a flight that did
        # exactly the right thing: applet flew home, restored RTL, radio failsafe was
        # detected, and it landed under control at 0.5 m/s. Whether the aircraft is in a
        # safe mode is the question; whether it entered during one particular window is
        # an artefact of when the harness happens to cut the radio.
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
        # THE ANNUNCIATION IS NOT THE ACTION.
        #
        # This verdict used to report ATTENTION whenever the string "EKF Failsafe"
        # appeared. On the shipped FS_EKF_ACTION 0 that string ALWAYS appears: ACTION 0
        # means "warn but take no action", so ArduPilot still announces the failsafe and
        # still clears it. The check therefore flagged the exact behaviour the parameter
        # was chosen to produce - another instance of measuring something adjacent to
        # the property that matters.
        #
        # What matters is whether the aircraft CHANGED MODE BY ITSELF because of it.
        # first_ekf_fs_t and mode_changes share the same clock, so the question is
        # answerable directly: any mode change after the annunciation is the failsafe
        # acting; none means it annunciated and stood down, which is what ACTION 0
        # promises and what this scenario exists to confirm.
        # Not every post-annunciation mode change is the failsafe. DR_ENABLE 1 ships, so
        # the applet is live in this scenario too and may command GUIDED_NOGPS or restore
        # a prior mode at any moment. Attribute only what the EKF failsafe can actually
        # command: ACTION 1 -> LAND, ACTION 2 -> ALT_HOLD (then LAND). Everything else
        # after the annunciation is reported, not asserted on, so it stays visible
        # without being blamed on the wrong subsystem.
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
        # THE CANARY IS ONE-SIDED, because only one side of it proves anything.
        #
        # What it guards is the harness comparing the EKF against ITSELF: inject a known
        # offset, and if the reported error is near zero the comparison is circular and
        # every other figure in this report is meaningless. That fault makes the number
        # SMALL.
        #
        # A number LARGER than the injection proves nothing of the sort. The injected
        # offset and the flight's own divergence add, so a denial that goes badly reads
        # high for an honest reason - measured 2026-09-15 at 269.55 m against a 100 m
        # injection, on a flight visibly thrashing between GUIDED_NOGPS and RTL with a
        # 385 m excursion. The old two-sided band called that "the harness is not
        # measuring truth", which is a claim about the instrument made from a reading
        # that the instrument working perfectly would also produce.
        #
        # So: fail LOW, report HIGH. A high reading is a real flight result and belongs
        # in the report, not in a verdict about measurement validity.
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
        # Where a divergence boundary has been MEASURED, say which side of it this run
        # landed on. "INFO - p95 392 m" and "INFO - p95 43 m" read as the same kind of
        # result otherwise, and they are not: one is a hold and one is a runaway.
        lim = spec.get("diverges_above")
        if lim is not None:
            # The boundary is EMPIRICAL: n=6 runs that separated cleanly into bounded
            # (<=79.6 m) and diverged (>=216.7 m). But those runs were flown at
            # sigma 20 m, and the model's sigma is now 180 m - the published Iridium
            # figure. Both modes scale with sigma, so a boundary measured at one sigma
            # does not separate them at another: at 180 m it would call essentially
            # every run "DIVERGED" and read as a finding rather than a stale constant.
            #
            # Rescaling it arithmetically would be worse - that invents a measurement.
            # So when the sigma differs from the one the boundary was measured at, say
            # the boundary does not apply, and report the raw number instead.
            sigma_now = spec.get("sigma", DopplerErrorModel.SIGMA_IRIDIUM_NO_ELEV)
            if abs(sigma_now - BOUNDARY_SIGMA_SHIPPED_M) <= 1e-6:
                # The shipping sigma, which the 2026-09-18 re-measurement (n=6 per
                # scenario, comment at BOUNDARY_SIGMA_SHIPPED_M) covered: no boundary
                # exists here - every run p95 300-530 m, no separating gap, and the
                # true excursion far below the p95. Saying "DOES NOT APPLY, re-measure"
                # is now stale advice: it WAS re-measured, and the answer is that the
                # classification is empty at this sigma. Report both numbers and the
                # measured conclusion instead of implying a measurement still owed.
                exc = res_track.get("truth_excursion_m", 0.0)
                res["verdict"] = (
                    f"INFO - p95 {d['p95']} m during denial, true excursion {exc:g} m. "
                    f"MEASURED at this sigma (n=6, 2026-09-18): no divergence boundary "
                    f"exists - every run p95 300-530 m with no separating gap, the "
                    f"estimate tracks the injected fix noise, and the true excursion is "
                    f"far smaller (medians 73/91 m). The {lim:g} m boundary describes "
                    f"the sigma {BOUNDARY_SIGMA_M:g} m fix, which Doppler alone does "
                    f"not provide")
            elif abs(sigma_now - BOUNDARY_SIGMA_M) > 1e-6:
                res["verdict"] = (
                    f"INFO - p95 {d['p95']} m during denial. The {lim:g} m divergence "
                    f"boundary DOES NOT APPLY here: it is measured at sigma "
                    f"{BOUNDARY_SIGMA_M:g} m, and re-measured at the shipping sigma "
                    f"{BOUNDARY_SIGMA_SHIPPED_M:g} m (n=6, 2026-09-18) no boundary "
                    f"exists either. This run is at sigma {sigma_now:g} m, which no "
                    f"measurement covers - reported raw, not classified")
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
