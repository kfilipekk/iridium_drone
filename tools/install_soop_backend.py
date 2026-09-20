#!/usr/bin/env python3
"""Install the SoOP GPS backend into the pinned ArduPilot tree."""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "firmware", "ardupilot")

# (file, unique anchor, text inserted after the anchor)
EDITS = [
    ("libraries/AP_GPS/AP_GPS.h",
     "    friend class AP_GPS_UBLOX_CFGv2;\n",
     "    friend class AP_GPS_SoOP;\n"),
    ("libraries/AP_GPS/AP_GPS.h",
     "        GPS_TYPE_SBF_DUAL_ANTENNA = 26,\n",
     "        GPS_TYPE_SOOP = 27, // NAVCORE on-board Iridium Doppler solve\n"),
    ("libraries/AP_GPS/AP_GPS.cpp",
     '#include "AP_GPS_ExternalAHRS.h"\n',
     '#include "AP_GPS_SoOP.h"\n'),
    ("libraries/AP_GPS/AP_GPS.cpp",
     "    case GPS_TYPE_EXTERNAL_AHRS:\n        return false;\n",
     "    case GPS_TYPE_SOOP:\n        return false;\n"),
    ("libraries/AP_GPS/AP_GPS.cpp",
     "#if AP_SIM_GPS_ENABLED\n    case GPS_TYPE_SITL:\n"
     "#endif  // AP_SIM_GPS_ENABLED\n        // none of these GPSs have initialisation blobs\n",
     "    case GPS_TYPE_SOOP:\n"),
    ("libraries/AP_GPS/AP_GPS.cpp",
     "#if AP_SIM_GPS_ENABLED\n    case GPS_TYPE_SITL:\n"
     "        return NEW_NOTHROW AP_GPS_SITL(*this, params[instance], state[instance], port);\n"
     "#endif  // AP_SIM_GPS_ENABLED\n",
     "\n    case GPS_TYPE_SOOP:\n"
     "        return NEW_NOTHROW AP_GPS_SoOP(*this, params[instance], state[instance], port);\n"),
    ("libraries/AP_GPS/AP_GPS.cpp",
     "            if (type == GPS_TYPE_MAV ||\n",
     "                type == GPS_TYPE_SOOP ||\n"),
]

FILES = ["AP_SoOPFix.h", "AP_SoOPFix.cpp", "AP_GPS_SoOP.h", "AP_GPS_SoOP.cpp"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ap-dir", default=os.environ.get(
        "AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot")))
    a = ap.parse_args()

    gps = os.path.join(a.ap_dir, "libraries", "AP_GPS")
    if not os.path.isdir(gps):
        print(f"FAILED - no AP_GPS directory under {a.ap_dir}")
        return 1

    for f in FILES:
        shutil.copyfile(os.path.join(SRC, f), os.path.join(gps, f))
    print(f"copied {len(FILES)} backend file(s) into {gps}")

    changed = 0
    for rel, anchor, ins in EDITS:
        path = os.path.join(a.ap_dir, rel)
        s = open(path).read()
        if ins and (anchor + ins) in s:
            continue                                  # already installed
        if s.count(anchor) != 1:
            print(f"FAILED - anchor not unique in {rel}: {anchor!r} "
                  f"({s.count(anchor)} matches)")
            return 1
        open(path, "w").write(s.replace(anchor, anchor + ins, 1))
        changed += 1
    print(f"applied {changed} registration edit(s) "
          f"({len(EDITS) - changed} already present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
