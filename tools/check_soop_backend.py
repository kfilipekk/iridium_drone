#!/usr/bin/env python3
"""Gate the SoOP GPS backend: registered in the tree, and really in the firmware."""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import install_soop_backend as inst

AP = os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot"))
FLOOR = 64          # bytes; a `return false` stub is a handful
READ = "AP_GPS_SoOP::read()"


def _nm_size(elf, substr):
    nm = "arm-none-eabi-nm" if "NAVCORE" in elf else "nm"
    try:
        r = subprocess.run([nm, "--print-size", "--demangle", elf],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in r.stdout.splitlines():
        if substr in line:
            parts = line.split()
            if len(parts) >= 4:
                try:
                    return int(parts[1], 16)
                except ValueError:
                    continue
    return None


def main():
    ok = True

    # 1. registration present in the tree
    missing = []
    for rel, anchor, ins in inst.EDITS:
        path = os.path.join(AP, rel)
        if not os.path.exists(path) or (anchor + ins) not in open(path).read():
            missing.append(rel)
    reg = not missing
    ok &= reg
    print(f"  {'ok  ' if reg else 'FAIL'}  registration present in the tree"
          + (f" (missing in {sorted(set(missing))})" if missing else
             f" (all {len(inst.EDITS)} edits)"))

    # 2 + 3. in the board firmware, with a real body and a selectable type
    elf = os.path.join(AP, "build/NAVCORE_SoOP/bin/arducopter")
    if not os.path.exists(elf):
        print(f"  FAIL  no firmware at {elf} - run tools/build_firmware.sh")
        return 1
    size = _nm_size(elf, READ)
    in_elf = size is not None and size >= FLOOR
    ok &= in_elf
    ty = subprocess.run(["strings", elf], capture_output=True, text=True).stdout.count("SoOP")
    print(f"  {'ok  ' if in_elf else 'FAIL'}  board firmware carries the backend: "
          f"{READ} is {size if size is not None else 'absent'} bytes "
          f"(floor {FLOOR}), GPS_TYPE_SOOP selectable ({ty} SoOP strings)")

    # the SITL binary must carry it too, or the EKF test is testing nothing
    self_elf = os.path.join(AP, "build/sitl/bin/arducopter")
    if os.path.exists(self_elf):
        ssize = _nm_size(self_elf, READ)
        in_sitl = ssize is not None and ssize >= FLOOR
        ok &= in_sitl
        print(f"  {'ok  ' if in_sitl else 'FAIL'}  SITL binary carries the backend "
              f"({ssize if ssize is not None else 'absent'} bytes)")
    else:
        print("  FAIL  no SITL binary - run `./waf configure --board sitl && ./waf copter`")
        ok = False

    print("\n" + ("SOOP BACKEND OK - registered, in the firmware, and selectable"
                  if ok else "SOOP BACKEND CHECK FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
