#!/usr/bin/env python3
"""
Check that every parameter this board ships actually exists in the firmware it targets.

ArduPilot does not validate defaults.parm. `chibios_hwdef.py` only expands @include and
copies the file into ROMFS - it never asks whether a parameter name is real. A typo, or
a name that moved between releases, is therefore **silently ignored at runtime**: the
board boots, reports no error, and is quietly unconfigured. That is a worse failure than
a build error, because nothing tells you.

Parameter names DO move. `RNGFND1_MIN` / `RNGFND1_MAX` are metres in 4.6 onwards and
were `RNGFND1_MIN_CM` / `RNGFND1_MAX_CM` in centimetres before that. Shipping the wrong
spelling loses the setting without a word.

So this validates defaults.parm against the parameter metadata ArduPilot generates from
the exact tree tools/build_firmware.sh is pinned to - names, ranges, and enum values.

Usage:  python3 tools/check_params.py [-v] [--regen]
"""
import os, re, sys, subprocess
import xml.etree.ElementTree as ET

AP    = os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot"))
VENV  = os.environ.get("VENV_DIR", os.path.expanduser("~/.cache/navcore/apvenv"))
PARM  = "firmware/NAVCORE_SoOP/defaults.parm"
PDEF  = os.path.join(AP, "apm.pdef.xml")
VEHICLE = "ArduCopter"


def ap_version():
    try:
        v = open(os.path.join(AP, "ArduCopter/version.h")).read()
        m = re.search(r'THISFIRMWARE\s+"([^"]+)"', v)
        # Several tags point at the same release commit (Copter-, Plane-, Rover-...).
        # --exact-match returns whichever sorts first, which is misleading on a board
        # that targets Copter, so pick the Copter one when it is there.
        tags = subprocess.run(["git", "tag", "--points-at", "HEAD"], cwd=AP,
                              capture_output=True, text=True).stdout.split()
        tag = next((t for t in tags if t.startswith("Copter-")), None) \
            or (tags[0] if tags else "detached")
        return (m.group(1) if m else "?"), tag
    except Exception:
        return "?", "?"


def build_metadata():
    """Ask ArduPilot to describe its own parameters, for the tree we are pinned to."""
    py = os.path.join(VENV, "bin", "python3")
    py = py if os.path.exists(py) else sys.executable
    r = subprocess.run([py, "Tools/autotest/param_metadata/param_parse.py",
                        "--vehicle", VEHICLE, "--format", "xml"],
                       cwd=AP, capture_output=True, text=True, timeout=1800)
    return r.returncode == 0 and os.path.exists(PDEF)


def load_metadata():
    known = {}
    root = ET.parse(PDEF).getroot()
    for p in root.iter("param"):
        name = p.get("name", "")
        short = name.split(":")[-1]
        entry = {"range": None, "values": None, "bitmask": False}
        for f in p.findall("field"):
            if f.get("name") == "Range" and f.text:
                try:
                    lo, hi = f.text.split()
                    entry["range"] = (float(lo), float(hi))
                except ValueError:
                    pass
        vals = p.find("values")
        if vals is not None:
            entry["values"] = {v.get("code") for v in vals.findall("value")}
        if p.find("bitmask") is not None:
            entry["bitmask"] = True
        # A library parameter appears once; a vehicle one is prefixed. Keep the richest.
        if short not in known or (entry["range"] or entry["values"]):
            known[short] = entry
    return known


def read_defaults():
    out = []
    for n, raw in enumerate(open(PARM), 1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            out.append((n, line, None))
            continue
        out.append((n, parts[0], parts[1]))
    return out


def main():
    verbose = "-v" in sys.argv
    if not os.path.isdir(AP):
        print(f"no ArduPilot tree at {AP} - run tools/build_firmware.sh first")
        return 1
    if "--regen" in sys.argv or not os.path.exists(PDEF):
        print("generating parameter metadata from the pinned tree ...")
        if not build_metadata():
            print("could not generate apm.pdef.xml "
                  f"(needs lxml: {VENV}/bin/pip install lxml)")
            return 1

    fw, tag = ap_version()
    known = load_metadata()
    rows = read_defaults()
    errs, warns = [], []

    for lineno, name, value in rows:
        if value is None:
            errs.append(f"line {lineno}: '{name}' is not 'NAME VALUE'")
            continue
        meta = known.get(name)
        if meta is None:
            errs.append(f"line {lineno}: {name} does not exist in {fw} - "
                        f"ArduPilot would ignore it silently")
            continue
        try:
            v = float(value)
        except ValueError:
            errs.append(f"line {lineno}: {name} = '{value}' is not a number")
            continue
        if meta["range"]:
            lo, hi = meta["range"]
            if not (lo <= v <= hi):
                errs.append(f"line {lineno}: {name} = {value} is outside "
                            f"its documented range {lo}..{hi}")
        elif meta["values"] and not meta["bitmask"]:
            codes = meta["values"]
            if value not in codes and str(int(v)) not in codes:
                # DR_NEXT_MODE -1 is documented by the applet itself ("Set to -1 to
                # return to mode used before deadreckoning was triggered") but is
                # missing from the applet's @Values metadata block, so the generated
                # pdef does not list it. Known-good exception, not a data error.
                applet_documented = (name == "DR_NEXT_MODE" and int(v) == -1)
                if not applet_documented:
                    warns.append(f"line {lineno}: {name} = {value} is not one of the "
                                 f"documented values ({', '.join(sorted(codes))})")
        if verbose:
            print(f"  ok  {name:20} {value}")

    print(f"firmware   : {fw}  (tag {tag})")
    print(f"parameters : {len(rows)} shipped, {len(known)} known to this build")
    for title, items in (("WARNINGS", warns), ("ERRORS", errs)):
        if items:
            print(f"\n{title} ({len(items)}):")
            for it in items:
                print(f"   {it}")
    if errs:
        print(f"\n{len(errs)} parameter(s) would be silently ignored or rejected.")
        return 1
    print("\nevery shipped parameter exists in the firmware this board targets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
