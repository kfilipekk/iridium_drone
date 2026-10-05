#!/usr/bin/env python3
#install the SoOP GPS backend and the on-board Iridium navigation into the pinned ArduPilot tree
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "firmware", "ardupilot")

#(file, unique anchor, text inserted after the anchor)
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
     "    case GPS_TYPE_MAV:\n#if AP_GPS_MAV_ENABLED\n        dstate->auto_detected_baud = false; // specified, not detected\n        return NEW_NOTHROW AP_GPS_MAV(*this, params[instance], state[instance], nullptr);\n#endif //AP_GPS_MAV_ENABLED\n",
     "    case GPS_TYPE_SOOP:\n        dstate->auto_detected_baud = false;\n        return NEW_NOTHROW AP_GPS_SoOP(*this, params[instance], state[instance], port);\n"),
    ("libraries/AP_GPS/AP_GPS.cpp",
     "            if (type == GPS_TYPE_MAV ||\n",
     "                type == GPS_TYPE_SOOP ||\n"),
    ("Tools/ardupilotwaf/ardupilotwaf.py",
     "    'AP_GPS',\n",
     "    'AP_SoOP',\n"),
    #ArduPilot's H743 ADC3 table lists only the PF/PH pins
    ("libraries/AP_HAL_ChibiOS/AnalogIn.cpp",
     "void AnalogIn::setup_adc(uint8_t index)\n{\n",
     "#ifdef HAL_SOOP_CAPTURE_ENABLED\n    if (index == 0) {\n        return;     // ADC1/ADC2 sample the tuner (AP_SoOP_Capture)\n    }\n#endif\n"),
    ("libraries/AP_HAL_ChibiOS/AnalogIn.cpp",
     "void AnalogIn::timer_tick_adc(uint8_t index)\n{\n",
     "#ifdef HAL_SOOP_CAPTURE_ENABLED\n    if (index == 0) {\n        return;     // ADC1 was never started: AP_SoOP_Capture owns it\n    }\n#endif\n"),
    ("libraries/AP_HAL_ChibiOS/hwdef/scripts/STM32H743xx.py",
     "ADC3_map = {\n",
     '    "PC0"\t:\t10,\n    "PC1"\t:\t11,\n    "PC2"\t:\t0,\n'),
]

#(file, text, replacement) where an insertion cannot express it
REPLACE = [
    #AnalogIn checks ADC1 against ADC2's pin table whenever dual mode
    ("libraries/AP_HAL_ChibiOS/AnalogIn.cpp",
     "#if STM32_ADC_DUAL_MODE\n    // assert that ADC1 and ADC2 have the same number of channels\n",
     "#if STM32_ADC_DUAL_MODE && defined(HAL_ANALOG2_PINS)\n"
     "    // assert that ADC1 and ADC2 have the same number of channels\n"),
]

FILES = ["AP_SoOPFix.h", "AP_SoOPFix.cpp", "AP_GPS_SoOP.h", "AP_GPS_SoOP.cpp"]
SOOP_TASK = ["AP_SoOP.h", "AP_SoOP.cpp", "AP_SoOP_MAX2112.h", "AP_SoOP_MAX2112.cpp",
             "AP_SoOP_Capture.h", "AP_SoOP_Capture.cpp"]
SOOP_CORE = ["soop_signal.h", "soop_dsp.h", "soop_dsp.c", "sgp4.h", "sgp4.c",
             "soop_ephem.h", "soop_ephem.c", "soop_nav.h", "soop_nav.c", "soop_guard.h",
             "soop_guard.c", "soop_ant.h", "soop_ant.c", "soop_max2112.h", "soop_max2112.c"]


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
    lib = os.path.join(a.ap_dir, "libraries", "AP_SoOP")
    os.makedirs(lib, exist_ok=True)
    for f in SOOP_TASK:
        shutil.copyfile(os.path.join(SRC, "AP_SoOP", f), os.path.join(lib, f))
    for f in SOOP_CORE:
        shutil.copyfile(os.path.join(HERE, "firmware", "soop", f), os.path.join(lib, f))
    print(f"copied {len(SOOP_TASK)} task and {len(SOOP_CORE)} navigation file(s) into {lib}")

    changed = 0
    for rel, anchor, ins in EDITS:
        path = os.path.join(a.ap_dir, rel)
        s = open(path).read()
        if ins and (anchor + ins) in s:
            continue                                  #already installed
        if s.count(anchor) != 1:
            print(f"FAILED - anchor not unique in {rel}: {anchor!r} "
                  f"({s.count(anchor)} matches)")
            return 1
        open(path, "w").write(s.replace(anchor, anchor + ins, 1))
        changed += 1
    for rel, old, new in REPLACE:
        path = os.path.join(a.ap_dir, rel)
        s = open(path).read()
        if new in s:
            continue
        if s.count(old) != 1:
            print(f"FAILED - text not unique in {rel}: {old!r} ({s.count(old)} matches)")
            return 1
        open(path, "w").write(s.replace(old, new, 1))
        changed += 1
    print(f"applied {changed} registration edit(s) "
          f"({len(EDITS) + len(REPLACE) - changed} already present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
