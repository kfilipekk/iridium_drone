#!/usr/bin/env python3
"""
Read every parameter defaults.parm ships back from a RUNNING ArduPilot, and fail on any
the firmware does not actually have.

WHY THIS EXISTS, WHEN tools/check_params.py ALREADY CHECKS NAMES
---------------------------------------------------------------
That one validates against the metadata ArduPilot generates from the pinned tree, which
is the right idea and still missed a real fault.

ArduPilot renamed the GPS parameters in 4.6 - AP_GPS.cpp registers the instances as
subgroups "1_" and "2_", so the name is GPS2_TYPE. The pre-4.6 spelling GPS_TYPE2 is
kept in the generated metadata as a conversion alias for ground stations. A metadata
check therefore PASSES GPS_TYPE2 while the firmware silently declines to set it, and the
board ships quietly unconfigured - which is the exact failure mode check_params.py was
written to prevent.

Metadata presence is not runtime settability. The only authority on what a build accepts
is the build. This asks it.

Usage:
  ./run_scenarios.sh --params        # via the launcher, which starts SITL
  python3 check_params_live.py       # against a SITL already listening on 5760
"""
import os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymavlink import mavutil

# A MISMATCH IS A FAILURE UNLESS IT IS LISTED HERE.
#
# This used to print "differs" and carry on, with a comment saying SITL overrides some
# values and a vehicle may clamp others - true, and it turned a material fault into a
# cosmetic-looking note. DR_ENABLE_DIST was shipped at 30 and running at 50, and
# DR_NEXT_MODE was shipped at -1 and running at 6, for as long as the applet has been
# fitted. Both were printed on every run and neither failed anything.
#
# The cause: DR_* parameters do not exist until copter-deadreckon-home.lua creates them,
# and the boot defaults file is parsed before scripting starts, so those lines are
# discarded. DR_ENABLE_DIST gates whether the applet arms at all, so the aircraft's whole
# GPS-loss mitigation was running on a value nobody chose.
#
# Add a name here only with a reason. "It differs" is not one.
MISMATCH_OK = {
    # (empty - every current mismatch was a real fault and has been fixed at source)
}

PARM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "firmware", "NAVCORE_SoOP", "defaults.parm")


def shipped():
    out = []
    for n, raw in enumerate(open(PARM), 1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) == 2:
            out.append((n, parts[0], float(parts[1])))
    return out


def main():
    conn = mavutil.mavlink_connection(
        os.environ.get("SITL_CONNECT", "tcp:127.0.0.1:5760"),
        source_system=255, source_component=190)
    if not conn.wait_heartbeat(timeout=60):
        print("no heartbeat - is SITL running?")
        return 2

    want = shipped()
    print(f"checking {len(want)} shipped parameters against a running build\n")

    # TARGETED READS WITH PATIENT RETRIES, not PARAM_REQUEST_LIST.
    #
    # The bulk listing looked like the right tool and is not: it stalls partway, and
    # re-asking restarts it, so the received count can reach the advertised total while
    # individual parameters are still missing. That produced a "missing" list containing
    # RNGFND1_ORIENT, RELAY1_PIN and EK3_SRC3_YAW - all of which a targeted read returns
    # immediately, holding exactly the values this board ships.
    #
    # Asking for specific names, spaced out, and re-asking only for the ones still
    # outstanding, returns every parameter reliably.
    names = [n for _, n, _ in want]
    got = {}
    for attempt in range(10):
        outstanding = [n for n in names if n not in got]
        if not outstanding:
            break
        for n in outstanding:
            conn.mav.param_request_read_send(conn.target_system, conn.target_component,
                                             n.encode(), -1)
            time.sleep(0.03)
        end = time.time() + 5
        while time.time() < end:
            msg = conn.recv_match(blocking=False)
            if msg and msg.get_type() == "PARAM_VALUE" and msg.param_id in names:
                got[msg.param_id] = msg.param_value
            time.sleep(0.002)
    total = len(names)

    # The launcher strips hardware-only lines (SERIALn_, RNGFNDn_ADDR, BRD_, NTF_,
    # SERVOn_) before SITL loads them, because SITL has no such drivers. Their values
    # legitimately differ from what the board ships, so comparing them reports noise.
    STRIPPED = re.compile(r'^(SERIAL[0-9]_|RNGFND[0-9]_ADDR|BRD_|NTF_LED_TYPES|SERVO13_)')

    # Absent from SITL builds only, and present on real hardware. Not board faults.
    #
    # The WHOLE AP_BLHeli group is compiled out of SITL, not just one parameter of it.
    # SERVO_BLH_AUTO was listed alone, so SERVO_BLH_BDMASK - its sibling, registered at
    # AP_BLHeli.cpp:150 as AP_GROUPINFO("BDMASK", 11, ...) and therefore unquestionably
    # real on the H743 build - was reported as "the firmware has no such parameter" on
    # every run. A skip list that covers one member of an absent group and not the rest
    # produces a permanent false FAIL, and a permanent false FAIL is how a real one gets
    # ignored. Match the prefix instead of enumerating members.
    SITL_ABSENT_RE = re.compile(r'^SERVO_BLH_')

    missing, mismatched = [], []
    for line, name, value in want:
        if STRIPPED.match(name):
            continue
        if SITL_ABSENT_RE.match(name):
            if name not in got:
                print(f"  (skipped   {name} - absent from SITL builds, present on hardware)")
            continue
        if name not in got:
            missing.append((line, name, value))
        elif abs(got[name] - value) > max(1e-4, abs(value) * 1e-4):
            mismatched.append((line, name, value, got[name]))

    for line, name, value in missing:
        print(f"  MISSING   defaults.parm:{line}  {name} {value:g}"
              f"   - the firmware has no such parameter")
    for line, name, value, actual in mismatched:
        print(f"  DIFFERS   defaults.parm:{line}  {name} shipped {value:g}, "
              f"build reports {actual:g}"
              + ("   (allowed)" if name in MISMATCH_OK else
                 "   - THE SHIPPED VALUE DID NOT TAKE EFFECT"))

    checked = [w for w in want if not STRIPPED.match(w[1])]
    present = sum(1 for w in checked if w[1] in got)
    print(f"\n{present}/{len(checked)} shipped parameters found in the running build "
          f"({len(want) - len(checked)} stripped for SITL, not compared)")
    bad = [m for m in mismatched if m[1] not in MISMATCH_OK]
    if missing or bad:
        if missing:
            print(f"FAIL - {len(missing)} parameter(s) would be silently ignored "
                  f"on the board")
        if bad:
            print(f"FAIL - {len(bad)} parameter(s) are shipped at one value and running "
                  f"at another: {', '.join(b[1] for b in bad)}")
        return 1
    print("every shipped parameter is real, settable, and actually set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
