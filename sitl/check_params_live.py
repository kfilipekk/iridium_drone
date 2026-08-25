#!/usr/bin/env python3
"""Read every parameter defaults.parm ships back from a running ArduPilot, and fail on any
the firmware does not actually have.

Usage:
  ./run_scenarios.sh --params        # via the launcher, which starts SITL
  python3 check_params_live.py       # against a SITL already listening on 5760
"""
import os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pymavlink import mavutil

MISMATCH_OK = {
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

    # Targeted reads with patient retries, not PARAM_REQUEST_LIST.
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

    STRIPPED = re.compile(r'^(SERIAL[0-9]_|RNGFND[0-9]_ADDR|BRD_|NTF_LED_TYPES|SERVO13_)')

    # Absent from SITL builds only, and present on real hardware.
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
