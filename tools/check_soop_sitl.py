#!/usr/bin/env python3
"""Gate the SoOP backend's fix reaching the EKF in SITL.

Usage:
    python3 tools/check_soop_sitl.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PY", os.path.expanduser("~/.cache/navcore/apvenv/bin/python3"))
TEST = os.path.join(ROOT, "tools", "soop_sitl_test.py")


def main():
    if not os.path.exists(PY):
        print(f"SOOP SITL CHECK FAILED - no python venv at {PY}")
        return 1
    if not os.path.exists(TEST):
        print(f"SOOP SITL CHECK FAILED - no test script at {TEST}")
        return 1

    r = subprocess.run([PY, TEST, "--seconds", "60"], cwd=ROOT)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
