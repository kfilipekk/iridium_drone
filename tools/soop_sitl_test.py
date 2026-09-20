#!/usr/bin/env python3
"""Prove the SoOP backend's fix actually reaches the EKF, in SITL."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

AP = os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot"))
BIN = os.path.join(AP, "build/sitl/bin/arducopter")
BASE = os.path.join(AP, "Tools/autotest/default_params/copter.parm")
HOME = "51.5074,-0.1278,20,0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120.0)
    a = ap.parse_args()

    try:
        from pymavlink import mavutil
    except ImportError:
        print("SOOP-SITL FAILED - pymavlink is not importable; run under the ArduPilot venv")
        return 1
    if not os.path.exists(BIN):
        print(f"SOOP-SITL FAILED - no SITL binary at {BIN}")
        return 1

    work = tempfile.mkdtemp(prefix="soop_sitl_")
    parm = os.path.join(work, "soop.parm")
    with open(parm, "w") as f:
        f.write("GPS_TYPE 27\n")            # GPS_TYPE_SOOP, forced

    logf = open(os.path.join(work, "sitl.log"), "w")
    proc = subprocess.Popen(
        [BIN, "--model", "quad", "--home", HOME,
         "--defaults", f"{BASE},{parm}", "--sysid", "1"],
        cwd=work, stdout=logf, stderr=subprocess.STDOUT)
    try:
        m = mavutil.mavlink_connection("tcp:127.0.0.1:5760", timeout=90)
        m.wait_heartbeat(timeout=90)
        m.mav.request_data_stream_send(
            m.target_system, m.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)

        fix_type = None
        pos = None
        t0 = time.time()
        while time.time() - t0 < a.seconds:
            msg = m.recv_match(blocking=True, timeout=5)
            if msg is None:
                continue
            t = msg.get_type()
            if t == "GPS_RAW_INT":
                fix_type = msg.fix_type
            elif t == "GLOBAL_POSITION_INT" and (msg.lat or msg.lon):
                pos = (msg.lat * 1e-7, msg.lon * 1e-7, msg.alt * 1e-3)
            if fix_type == 3 and pos is not None:
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()

    near_home = pos is not None and abs(pos[0] - 51.5074) < 0.02 and abs(pos[1] + 0.1278) < 0.02
    ok = fix_type == 3 and near_home
    print(f"  {'ok  ' if fix_type == 3 else 'FAIL'}  GPS_RAW_INT reported a 3D fix "
          f"from the SoOP backend (fix_type={fix_type})")
    print(f"  {'ok  ' if near_home else 'FAIL'}  the EKF published a global position near "
          f"home: {pos if pos else 'none'}")
    print("\n" + ("SOOP-SITL OK - the fix reaches the EKF"
                  if ok else "SOOP-SITL FAILED - the fix did not reach the EKF"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
