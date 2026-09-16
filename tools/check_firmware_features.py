#!/usr/bin/env python3
"""Assert that the features defaults.parm enables are actually in the binary.

Usage:  python3 tools/check_firmware_features.py
"""
import os
import re
import shutil
import subprocess
import sys

AP = os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot"))
ELF = os.path.join(AP, "build/NAVCORE_SoOP/bin/arducopter")
PARM = "firmware/NAVCORE_SoOP/defaults.parm"
STUB_FLOOR = 16          # bytes; an "enabled 2" dummy is 2-4

# (parameter, predicate on its value, what it turns on, [(demangled symbol, min bytes)])
FEATURES = [
    ("TEMP1_TYPE", lambda v: int(float(v)) == 10,
     "TMP119 driver for U19, the board's own thermometer",
     [("AP_TemperatureSensor_TMP119::init()", 32),
      ("AP_TemperatureSensor_TMP119::read_registers(unsigned char, unsigned short&) const", 8)]),
    ("TEMP_LOG", lambda v: int(float(v)) != 0,
     "the TEMP log message - without the subsystem it writes nothing",
     [("AP_TemperatureSensor::update()", STUB_FLOOR),
      ("AP_TemperatureSensor::init()", STUB_FLOOR)]),
    ("FLOW_TYPE", lambda v: int(float(v)) == 5,
     "MAVLink optical flow from the companion",
     [("AP_OpticalFlow_MAV::update()", STUB_FLOOR)]),
    ("BATT_MONITOR", lambda v: int(float(v)) == 4,
     "analogue voltage and current monitoring",
     [("AP_BattMonitor_Analog::read()", STUB_FLOOR)]),
    ("SCR_ENABLE", lambda v: int(float(v)) == 1,
     "Lua scripting, which the dead-reckon applet needs",
     [("AP_Scripting::init()", STUB_FLOOR)]),
]


def nm_symbols(elf):
    tool = shutil.which("arm-none-eabi-nm") or shutil.which("nm")
    if not tool:
        return None, "no arm-none-eabi-nm or nm on PATH"
    try:
        out = subprocess.run([tool, "-S", "-C", elf], capture_output=True,
                             text=True, timeout=180)
    except Exception as e:
        return None, str(e)
    if out.returncode != 0:
        return None, out.stderr.strip()[:200]
    syms = {}
    for line in out.stdout.splitlines():
        m = re.match(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+\S\s+(.*)$", line)
        if m:
            name = m.group(3).strip()
            syms[name] = max(syms.get(name, 0), int(m.group(2), 16))
    return syms, None


def shipped():
    vals = {}
    if not os.path.exists(PARM):
        return vals
    for line in open(PARM):
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            vals[parts[0]] = parts[1]
    return vals


def main():
    fails = []
    print(f"elf   : {ELF}")
    if not os.path.exists(ELF):
        print("\nFAIL - no linked firmware to inspect.")
        print("       This is a FAILURE and not a skip: the whole point of this check is")
        print("       that a parameter can name a driver the binary does not contain, so")
        print("       'could not look' must never read as 'looked and it was fine'.")
        print("       Build it first:  bash tools/build_firmware.sh")
        return 1

    syms, err = nm_symbols(ELF)
    if syms is None:
        print(f"\nFAIL - could not read symbols: {err}")
        return 1
    print(f"symbols: {len(syms)} sized symbols in the linked image")
    parms = shipped()
    print()

    checked = 0
    for pname, pred, what, required in FEATURES:
        if pname not in parms:
            continue
        try:
            if not pred(parms[pname]):
                continue
        except ValueError:
            continue
        checked += 1
        for sym, floor in required:
            size = syms.get(sym)
            if size is None:
                print(f"  FAIL  {pname} {parms[pname]:>4}  {what}")
                print(f"        symbol ABSENT from the image: {sym}")
                fails.append(f"{pname}: {sym} absent")
            elif size < floor:
                print(f"  FAIL  {pname} {parms[pname]:>4}  {what}")
                print(f"        {sym}")
                print(f"        is {size} bytes - a STUB. Needs >= {floor}. The parameter")
                print(f"        is set, the symbol exists, and the code does nothing.")
                fails.append(f"{pname}: {sym} is a {size}-byte stub")
            else:
                print(f"  ok    {pname} {parms[pname]:>4}  {what}")
                print(f"        {sym}  {size} bytes")
    print()
    print(f"{checked} enabled feature(s) traced from defaults.parm into the linked image")
    print()
    print("what this check cannot do:")
    print("  - it proves the CODE is present, not that the DEVICE answers. U19 not")
    print("    being fitted, or sitting at the wrong I2C address, looks identical here.")
    print("    That is BUILD.md T3, not a desk check.")
    print("  - it only covers the features listed in FEATURES. A parameter added to")
    print("    defaults.parm without a row here is not traced.")
    if fails:
        print()
        print(f"FAIL - {len(fails)} enabled feature(s) are not in the firmware:")
        for f in fails:
            print(f"   - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
