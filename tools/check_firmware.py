#!/usr/bin/env python3
"""Firmware checks: the hwdef, parameters, features, BDShot and SITL.

Usage:  python3 tools/check_firmware.py CHECK [options]

Checks:
  hwdef              Cross-check the generated hwdef against the netlist it is supposed to describe.
  params             Check that every parameter this board ships actually exists in the firmware it targets.
  features           Assert that the features defaults.parm enables are actually in the binary.
  bdshot             Can the four motors run bidirectional DShot on this board, as built?
  soop_backend       Gate the SoOP GPS backend: registered in the tree, and really in the firmware.
  sitl               The SITL suite is green, and it is green against the firmware that actually ships.
  soop_sitl          Gate the SoOP backend's fix reaching the EKF in SITL.
"""
import ast, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile
import design, kt   #kt puts kicad-tools on the path
from kicadtools import symlib
import xml.etree.ElementTree as ET
import install_soop_backend as inst
from hwdef_pinmap import parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOARD = (sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv
         else os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb"))

AP = os.environ.get('AP_DIR', os.path.expanduser('~/.cache/navcore/ardupilot'))
PARM = 'firmware/NAVCORE_SoOP/defaults.parm'


#hwdef

"""Cross-check the generated hwdef against the netlist it is supposed to describe."""

HW = "firmware/NAVCORE_SoOP/hwdef.dat"


def run_hwdef():
    pins, _alts = parse(HW)
    txt = open(HW).read()

    syms = symlib.load()
    h7 = {p['num']: p['name'] for p in syms["STM32H743VIT6_C114409"]}
    used = set()
    for net, specs in design.NETS.items():
        for sp in specs:
            ref, pin = sp.split(".", 1)
            if ref != "U1": continue
            nm = h7.get(pin, pin).split("-")[0]
            #the H7's analogue-switch pads (PC2_C, PC3_C ...) are their GPIO in a hwdef
            used.add(nm[:-2] if nm.endswith("_C") else nm)
    for pin in list(pins):
        pass

    errs, warns = [], []

    #1. every pin the hwdef declares must be wired on the board
    for p in pins:
        if p not in used:
            errs.append(f"hwdef declares {p} ({pins[p]['label']}) but the netlist does not wire it")

    #2. every SPIDEV must name a CS pin the hwdef declares
    cs_pins = {v['label'] for v in pins.values() if v['periph'] == 'CS'}
    for m in re.finditer(r'^SPIDEV\s+(\S+)\s+(\S+)\s+\S+\s+(\S+)', txt, re.M):
        dev, bus, cs = m.groups()
        if cs not in cs_pins:
            errs.append(f"SPIDEV {dev} uses CS '{cs}' which the hwdef never declares")

    #3. every IMU/BARO must reference a device that exists
    spidevs = set(re.findall(r'^SPIDEV\s+(\S+)', txt, re.M))
    for m in re.finditer(r'^IMU\s+\S+\s+SPI:(\S+)', txt, re.M):
        if m.group(1) not in spidevs:
            errs.append(f"IMU references SPIDEV '{m.group(1)}' which is not declared")
    baros = re.findall(r'^BARO\s+(\S+)\s+(\S+)', txt, re.M)

    #4. sensors declared vs sensors actually on the BOM
    fitted = {v[2] for v in design.COMPONENTS.values()}
    if not any("42688" in f for f in fitted):
        warns.append("hwdef expects ICM-42688-P but it is not in the BOM")
    if not any("MS5611" in f for f in fitted):
        warns.append("hwdef expects MS5611 but it is not in the BOM")

    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, HWDEF_OUT=td)
        r = subprocess.run([sys.executable, os.path.join(here, "gen_hwdef.py")],
                           capture_output=True, text=True, env=env, timeout=300)
        if r.returncode != 0:
            errs.append(f"gen_hwdef.py failed, so the generated files cannot be "
                        f"verified: {r.stderr.strip()[:160]}")
        else:
            for name in ("hwdef.dat", "defaults.parm"):
                gen = os.path.join(td, name)
                cur = os.path.join(os.path.dirname(HW), name)
                if not os.path.exists(gen):
                    errs.append(f"gen_hwdef.py did not write {name} into HWDEF_OUT, so "
                                f"this check cannot see it - fix the tool, do not skip")
                elif open(gen).read() != open(cur).read():
                    errs.append(f"{name} DIFFERS from what tools/gen_hwdef.py produces. "
                                f"A hand edit here is reverted by the next regeneration "
                                f"- move the change into gen_hwdef.py and re-run it")

    #each IMU's rotation
    import pcbnew, gen_hwdef
    brd = pcbnew.LoadBoard(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        "NAVCORE-SoOP.kicad_pcb"))
    for ref, (dev, *_axes) in design.IMU_AXES.items():
        m = re.search(rf"^IMU \S+ SPI:{dev} ROTATION_(\S+)", txt, re.M)
        want = gen_hwdef.imu_rotation(brd, ref)
        if not m:
            errs.append(f"{ref} ({dev}) has no IMU line in the hwdef")
        elif m.group(1) != want:
            errs.append(f"{ref} ({dev}) is ROTATION_{m.group(1)} in the hwdef but its pads say "
                        f"ROTATION_{want} (forward = design.BOARD_FORWARD)")
        else:
            print(f"IMU {ref:3s} rotation    : ROTATION_{want}, matches its pads")

    #each IMU's SPI lines, followed from its pads to the MCU
    for ref, (dev, *_axes) in design.IMU_AXES.items():
        m = re.search(rf"^SPIDEV\s+{dev}\s+(\S+)\s+\S+\s+(\S+)", txt, re.M)
        if not m:
            errs.append(f"{ref} ({dev}) has no SPIDEV line in the hwdef")
            continue
        bus, cs = m.groups()
        wired = gen_hwdef.imu_spi_ports(brd, ref)
        want = {"cs": cs, "sck": f"{bus}_SCK", "miso": f"{bus}_MISO", "mosi": f"{bus}_MOSI"}
        bad = [f"{role} pad goes to {wired[role] or 'no single MCU pin'} "
               f"({pins.get(wired[role], {}).get('label', 'undeclared')}), hwdef expects {lab}"
               for role, lab in want.items()
               if pins.get(wired[role], {}).get("label") != lab]
        if bad:
            errs.append(f"{ref} ({dev}) SPI wiring disagrees with the hwdef: " + "; ".join(bad))
        else:
            print(f"IMU {ref:3s} SPI         : {bus}, CS {cs} on {wired['cs']}, matches its pads")

    print(f"hwdef pins declared : {len(pins)}")
    print(f"netlist MCU pins    : {len(used)}")
    print(f"SPI devices         : {len(spidevs)}  ({', '.join(sorted(spidevs))})")
    print(f"barometers          : {len(baros)}  ({', '.join(b[0]+' '+b[1] for b in baros)})")
    print(f"IMUs                : {len(re.findall(r'^IMU ', txt, re.M))}")
    print(f"board id            : {(re.search(r'APJ_BOARD_ID (\S+)', txt) or ['','?'])[1]}")
    if warns:
        print(f"\nWARNINGS ({len(warns)}):")
        for w in warns: print("  ", w)
    if errs:
        print(f"\nERRORS ({len(errs)}):")
        for e in errs: print("  ", e)
        return 1
    print("\nhwdef is consistent with the netlist.")
    return 0


#params

"""Check that every parameter this board ships actually exists in the firmware it targets.

Usage:  python3 tools/check_firmware.py params [-v] [--regen]
"""

VENV  = os.environ.get("VENV_DIR", os.path.expanduser("~/.cache/navcore/apvenv"))
PDEF  = os.path.join(AP, "apm.pdef.xml")
VEHICLE = "ArduCopter"


def ap_version():
    try:
        v = open(os.path.join(AP, "ArduCopter/version.h")).read()
        m = re.search(r'THISFIRMWARE\s+"([^"]+)"', v)
        #several tags point at the same release commit (Copter-, Plane-, Rover-...)
        tags = subprocess.run(["git", "tag", "--points-at", "HEAD"], cwd=AP,
                              capture_output=True, text=True).stdout.split()
        tag = next((t for t in tags if t.startswith("Copter-")), None) \
            or (tags[0] if tags else "detached")
        return (m.group(1) if m else "?"), tag
    except Exception:
        return "?", "?"


def build_metadata():
    """Ask ArduPilot to describe its own parameters."""
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
        #a library parameter appears once; a vehicle one is prefixed
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


def run_params():
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


#features

"""Assert that the features defaults.parm enables are actually in the binary.

Usage:  python3 tools/check_firmware.py features
"""

ELF = os.path.join(AP, "build/NAVCORE_SoOP/bin/arducopter")
STUB_FLOOR = 16          #bytes; an "enabled 2" dummy is 2-4

#(parameter, predicate on its value, what it turns on, [(demangled symbol, min bytes)])
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


def run_features():
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
    print("    That is runbook T3 (docs/navcore-runbook.tex Part 9), not a desk check.")
    print("  - it only covers the features listed in FEATURES. A parameter added to")
    print("    defaults.parm without a row here is not traced.")
    if fails:
        print()
        print(f"FAIL - {len(fails)} enabled feature(s) are not in the firmware:")
        for f in fails:
            print(f"   - {f}")
        return 1
    return 0


#bdshot

"""Can the four motors run bidirectional DShot on this board, as built?

Usage:  python3 tools/check_firmware.py bdshot [--self-test]

BDShot reads each ESC's reply by input capture on the motor's own timer channel, so it
needs, for every motor on J2:
  - a timer channel that is not a complementary output (TIMx_CHyN cannot capture);
  - a BIDIR line on the same timer and channel pair (1/2 or 3/4) - one per pair reads both;
  - a DMA stream for that timer's UP and for each BIDIR channel, shared with nothing else
    (the dma_resolver map in the build's hwdef.h, which must be newer than hwdef.dat);
and defaults.parm must ship SERVO_BLH_BDMASK as either off or exactly the motor mask, with
the motors' pole count, so RPM telemetry is scaled right once Bluejay is flashed.

--self-test breaks each input in turn and exits 0 only if every break is caught.
"""

HWDEF = os.path.join(REPO, "firmware", "NAVCORE_SoOP", "hwdef.dat")
DEFAULTS = os.path.join(REPO, "firmware", "NAVCORE_SoOP", "defaults.parm")
BUILT = os.path.join(os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot")),
                     "build", "NAVCORE_SoOP", "hwdef.h")
MOTORS = ("M1", "M2", "M3", "M4")


def motor_pins():
    """M1..M4 -> the MCU pin each reaches (design.NETS: J2.3-6 to U1.Pxn)."""
    out = {}
    for m in MOTORS:
        pin = next((p.split(".", 1)[1] for p in design.NETS[m] if p.startswith("U1.")), None)
        out[m] = pin
    return out


def lines(hwdef):
    """Active (uncommented) PWM lines."""
    out = {}
    for ln in hwdef.splitlines():
        ln = ln.split("#", 1)[0].strip()
        m = re.match(r"^(P[A-K]\d+)\s+TIM(\d+)_CH(\d)(N?)\s+TIM\d+\s+PWM\((\d+)\)(.*)$", ln)
        if m:
            out[m.group(1)] = (int(m.group(2)), int(m.group(3)), bool(m.group(4)),
                               int(m.group(5)), "BIDIR" in m.group(6).split())
    return out


def evaluate(hwdef, built, defaults, built_fresh=True):
    fails = []
    pins = motor_pins()
    pwm = lines(hwdef)
    bidir = {(t, (c + 1) // 2) for t, c, n, _, b in pwm.values() if b}
    timers, chans = set(), set()
    mask = 0
    for m, pin in pins.items():
        if pin not in pwm:
            fails.append(f"{m} ({pin}) has no PWM line in hwdef.dat")
            continue
        t, c, comp, n, _ = pwm[pin]
        mask |= 1 << (n - 1)
        timers.add(t)
        if comp:
            fails.append(f"{m} ({pin}) is TIM{t}_CH{c}N - a complementary output cannot "
                         "capture the ESC's reply")
        if (t, (c + 1) // 2) not in bidir:
            fails.append(f"{m} ({pin}) on TIM{t}_CH{c}: no BIDIR on that timer's channel "
                         f"pair {2 * ((c + 1) // 2) - 1}/{2 * ((c + 1) // 2)}")
    for t, c, comp, n, b in pwm.values():
        if b:
            chans.add((t, c))
    if not built_fresh:
        fails.append("the build's hwdef.h is older than hwdef.dat - run tools/build_firmware.sh")
    for t in sorted(timers):
        for what in [f"TIM{t}_UP"] + [f"TIM{t}_CH{c}" for tt, c in sorted(chans) if tt == t]:
            m = re.search(rf"^#define STM32_TIM_{what}_DMA_STREAM\s+\S+(.*)$", built, re.M)
            if not m:
                fails.append(f"{what} has no DMA stream in the build")
            elif "shared" in m.group(1):
                fails.append(f"{what}'s DMA stream is shared:{m.group(1).strip()[2:]}")
    d = dict(re.findall(r"^(\w+)\s+([-\d.]+)", defaults, re.M))
    bd = int(float(d.get("SERVO_BLH_BDMASK", "0")))
    if bd not in (0, mask):
        fails.append(f"SERVO_BLH_BDMASK {bd} is neither off nor the motor mask {mask}")
    if "SERVO_BLH_POLES" not in d:
        fails.append("SERVO_BLH_POLES is not set, so ESC RPM would rest on the default")
    return fails, mask


def self_test(hwdef, built, defaults):
    pin1 = motor_pins()["M1"]
    breaks = [
        ("BIDIR removed", hwdef.replace(" BIDIR", ""), built, defaults, True),
        ("M1 back on TIM8_CH2N",
         re.sub(rf"^{pin1}\s+TIM3_CH3 TIM3", f"{pin1}  TIM8_CH2N TIM8", hwdef, flags=re.M),
         built, defaults, True),
        ("TIM3_CH3 stream missing",
         hwdef, re.sub(r"^#define STM32_TIM_TIM3_CH3_DMA_STREAM.*$", "", built, flags=re.M),
         defaults, True),
        ("TIM5_UP stream shared",
         hwdef, re.sub(r"^(#define STM32_TIM_TIM5_UP_DMA_STREAM\s+\S+).*$",
                       r"\1 // shared SPI1_RX,TIM5_UP", built, flags=re.M), defaults, True),
        ("BDMASK 3", hwdef, built, re.sub(r"^SERVO_BLH_BDMASK .*$", "SERVO_BLH_BDMASK 3",
                                          defaults, flags=re.M), True),
        ("stale build", hwdef, built, defaults, False),
    ]
    ok = True
    for name, h, b, d, fresh in breaks:
        caught = bool(evaluate(h, b, d, fresh)[0])
        ok &= caught
        print(f"  {'caught' if caught else 'MISSED'}  {name}")
    return ok


def run_bdshot():
    hwdef = open(HWDEF).read()
    defaults = open(DEFAULTS).read()
    built = open(BUILT).read() if os.path.exists(BUILT) else ""
    fresh = bool(built) and os.path.getmtime(BUILT) >= os.path.getmtime(HWDEF)
    if "--self-test" in sys.argv:
        clean = not evaluate(hwdef, built, defaults, fresh)[0]
        print(f"  {'clean' if clean else 'NOT CLEAN'}  the board as built")
        ok = clean and self_test(hwdef, built, defaults)
        print("self-test passed: every break is caught" if ok else "SELF-TEST FAILED")
        return 0 if ok else 1
    fails, mask = evaluate(hwdef, built, defaults, fresh)
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} reason(s) BDShot cannot run on the motors")
        return 1
    print(f"BDShot ready on motors 1-4 (mask {mask}): BIDIR timers with DMA of their own; "
          f"enable after flashing Bluejay")
    return 0


#soop_backend

"""Gate the SoOP GPS backend: registered in the tree, and really in the firmware."""

FLOOR = 64          #bytes; a `return false` stub is a handful
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


def run_soop_backend():
    ok = True

    #1. registration present in the tree
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

    #2 + 3. in the board firmware, with a real body and a selectable type
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

    #2b. antenna monitor symbols and SOA log format in the ELF
    ant_up_size = _nm_size(elf, "AP_SoOP::ant_update")
    soop_ant_size = _nm_size(elf, "soop_ant_step")
    has_ant_syms = ant_up_size is not None and ant_up_size >= FLOOR and soop_ant_size is not None and soop_ant_size >= FLOOR
    ok &= has_ant_syms
    print(f"  {'ok  ' if has_ant_syms else 'FAIL'}  antenna monitor in firmware: "
          f"AP_SoOP::ant_update is {ant_up_size if ant_up_size is not None else 'absent'} bytes, "
          f"soop_ant_step is {soop_ant_size if soop_ant_size is not None else 'absent'} bytes")

    s_out = subprocess.run(["strings", "-a", "-n", "3", elf], capture_output=True, text=True).stdout
    has_soa = "SOA" in s_out.splitlines() and "TimeUS,St,mA,En,Flt,Rt" in s_out
    ok &= has_soa
    print(f"  {'ok  ' if has_soa else 'FAIL'}  firmware logs active antenna telemetry: "
          f"SOA format string {'present' if has_soa else 'missing'}")

    #2c. hwdef configures BIAS_EN on PC5 driven HIGH
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hwdef_file = os.path.join(repo_root, "firmware/NAVCORE_SoOP/hwdef.dat")
    hwdef_txt = open(hwdef_file).read() if os.path.exists(hwdef_file) else ""
    bias_en_match = bool(re.search(r"^\s*PC5\s+BIAS_EN\s+OUTPUT\s+HIGH", hwdef_txt, re.M))
    ok &= bias_en_match
    print(f"  {'ok  ' if bias_en_match else 'FAIL'}  hwdef drives antenna feed: "
          f"PC5 BIAS_EN OUTPUT HIGH {'present' if bias_en_match else 'missing'}")

    #the SITL binary must carry it too, or the EKF test is testing nothing
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


#sitl

"""The SITL suite is green, and it is green against the firmware that actually ships.

Usage:
    python3 tools/check_firmware.py sitl                  # validate (no network, no SITL)
    python3 tools/check_firmware.py sitl --record         # fold the newest run into the result
"""

RESULT = os.path.join(REPO, "sitl", "sitl-results.json")
LOGS = os.path.join(REPO, "sitl", "logs")


def defaults_sha():
    """The parameter set the firmware ships, identified by content."""
    for p in (os.path.join(REPO, "firmware", "NAVCORE_SoOP", "defaults.parm"),
              os.path.join(REPO, "firmware", "defaults.parm")):
        if os.path.exists(p):
            raw = hashlib.sha256(open(p, "rb").read()).hexdigest()
            params = {}
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            params[parts[0].strip()] = parts[1].strip()
            canon = "".join(f"{k}={params[k]}\n" for k in sorted(params.keys()))
            sem = hashlib.sha256(canon.encode()).hexdigest()
            return raw, sem, p
    return None, None, None


AP_DIR = os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot"))
API_BIN = os.path.join(AP_DIR, "build", "sitl", "bin", "arducopter")


def sitl_binary():
    """(sha256, mtime) of the SITL binary, or (None, None) if it is not built."""
    if not os.path.exists(API_BIN):
        return None, None
    with open(API_BIN, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest(), int(os.path.getmtime(API_BIN))


def ap_head():
    """The ArduPilot revision the SITL binary was built from, or None."""
    try:
        return subprocess.run(["git", "-C", AP_DIR, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=20
                              ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def declared():
    """Scenario names declared in sitl/scenarios.py's scenarios dict."""
    src = open(os.path.join(REPO, "sitl", "scenarios.py")).read()
    body = src.split("SCENARIOS = {", 1)[1] if "SCENARIOS = {" in src else ""
    return set(re.findall(r'^\s{4}"([a-z0-9_]+)":\s*dict\(', body, re.M))


#not every scenario is a gate
ASSERT_KEYS = ("expect_arm_failure", "max_p95", "expect_ceiling")


def expectations():
    """{scenario: 'asserting'|'measuring'} read from scenarios.py."""
    try:
        tree = ast.parse(open(os.path.join(REPO, "sitl", "scenarios.py")).read())
    except (OSError, SyntaxError):
        return {}
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "SCENARIOS" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if not isinstance(k, ast.Constant):
                continue
            if isinstance(v, ast.Call):
                keys = {kw.arg for kw in v.keywords if kw.arg}
            elif isinstance(v, ast.Dict):
                keys = {kk.value for kk in v.keys
                        if isinstance(kk, ast.Constant) and isinstance(kk.value, str)}
            else:
                continue
            if "informational" in keys:
                out[k.value] = "measuring"
            elif keys & set(ASSERT_KEYS):
                out[k.value] = "asserting"
            else:
                out[k.value] = "undeclared"
        break
    return out


SITL_OUT = os.environ.get("OUT", "/tmp/nav/sitl")


def newest_report():
    cands = glob.glob(os.path.join(SITL_OUT, "report.json"))
    cands += glob.glob(os.path.join(LOGS, "**", "report.json"), recursive=True)
    cands = [c for c in cands if os.path.exists(c)]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def record():
    rep = newest_report()
    if not rep:
        print(f"no report.json in {SITL_OUT} or under "
              f"{os.path.relpath(LOGS, REPO)} - nothing to record. Run "
              f"sitl/run_scenarios.sh first (or set OUT to its output directory).")
        return 1
    merged = json.load(open(rep))
    sha, sem_sha, path = defaults_sha()
    bsha, bmtime = sitl_binary()
    rel = os.path.relpath(rep, REPO)
    out = {"source": rel if not rel.startswith("..") else rep,
           "defaults_sha256": sha,
           "defaults_semantic_sha256": sem_sha,
           "defaults_path": os.path.relpath(path, REPO) if path else None,
           "sitl_binary_sha256": bsha,
           "sitl_binary_mtime": bmtime,
           "ardupilot_head": ap_head(),
           "scenarios": {}}
    for r in merged:
        name = r.get("scenario") or "?"
        out["scenarios"][name] = r.get("verdict") or r.get("error") or "NO VERDICT"
    with open(RESULT, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"recorded {len(out['scenarios'])} scenario(s) -> "
          f"{os.path.relpath(RESULT, REPO)}")
    return 0


def run_sitl():
    if "--record" in sys.argv:
        return record()

    want = declared()
    print(f"declared   : {len(want)} scenario(s) in sitl/scenarios.py")
    if not os.path.exists(RESULT):
        print(f"\nFAIL - no result at {os.path.relpath(RESULT, REPO)}. The suite has not "
              f"been run; run sitl/run_scenarios.sh, then "
              f"python3 tools/check_firmware.py sitl --record")
        return 1

    res = json.load(open(RESULT))
    have = set(res.get("scenarios") or {})
    cur, cur_sem, path = defaults_sha()

    problems = []
    if want - have:
        problems.append(f"scenarios declared but absent from the result: "
                        f"{', '.join(sorted(want - have))}")
    if have - want:
        problems.append(f"scenarios in the result that no longer exist: "
                        f"{', '.join(sorted(have - want))}")

    bsha, _ = sitl_binary()
    recorded_b = res.get("sitl_binary_sha256")
    if bsha is None:
        problems.append("the SITL binary is not built, so no result can be trusted "
                        "until it is")
    elif recorded_b is None:
        problems.append("the result does not record which SITL binary produced it - "
                        "re-record with `python3 tools/check_firmware.py sitl --record`")
    elif recorded_b != bsha:
        problems.append(
            "the result was produced by a DIFFERENT SITL binary "
            f"(recorded {str(recorded_b)[:12]}, now {bsha[:12]}). The flight logic has "
            "been rebuilt since these scenarios ran, so a green result says nothing "
            "about the binary that exists now. Re-run sitl/run_scenarios.sh")

    recorded_head = res.get("ardupilot_head")
    cur_head = ap_head()
    if recorded_head and cur_head and recorded_head != cur_head:
        problems.append(f"the ArduPilot source moved since these scenarios ran "
                        f"(recorded {recorded_head[:12]}, now {cur_head[:12]})")

    recorded_sha = res.get("defaults_sha256")
    recorded_sem = res.get("defaults_semantic_sha256")
    param_match = (recorded_sha == cur) or (recorded_sem and recorded_sem == cur_sem)
    if cur is None:
        problems.append("cannot find defaults.parm to compare against")
    elif not param_match:
        problems.append(
            "the result was produced against a DIFFERENT parameter set "
            f"(recorded {str(recorded_sha)[:12]}, now {cur[:12]}) - the flight parameters have "
            "changed since these scenarios ran, so a green result says nothing about "
            "what ships. Re-run sitl/run_scenarios.sh")

    kind = expectations()
    if not kind:
        problems.append("cannot read scenario expectations from sitl/scenarios.py")

    #a verdict is a failure when it contradicts what the scenario declared it would do
    bad, measuring = {}, {}
    for n, v in (res.get("scenarios") or {}).items():
        up = str(v).upper()
        k = kind.get(n)
        failed = up.startswith("FAIL") or up.startswith("UNEXPECTED")
        if k == "measuring":
            (bad if failed else measuring)[n] = v
        elif k == "asserting":
            if not up.startswith("PASS"):
                bad[n] = v
        elif k == "undeclared":
            bad[n] = (f"declares neither {'/'.join(ASSERT_KEYS)} nor informational=True, "
                      f"so this result asserts nothing: {v}")
        else:
            bad[n] = f"no expectation found in sitl/scenarios.py: {v}"
    for n, v in sorted(bad.items()):
        problems.append(f"{n}: {v}")

    print(f"result     : {os.path.relpath(RESULT, REPO)} "
          f"({len(have)} scenario(s), from {res.get('source')})")
    print(f"parameters : {'matches' if param_match else 'DIFFERS from'} "
          f"{os.path.relpath(path, REPO) if path else 'defaults.parm'}"
          f"{' (byte-identical)' if recorded_sha == cur else ' (semantic match)' if param_match else ''}")
    print(f"binary     : {'matches' if recorded_b == bsha else 'DIFFERS from'} "
          f"build/sitl/bin/arducopter ({str(bsha)[:12]})")
    print(f"source     : ArduPilot {str(recorded_head or 'unrecorded')[:12]}")
    n_assert = sum(1 for n in have if kind.get(n) == "asserting")
    print(f"mechanisms : {n_assert - len([n for n in bad if kind.get(n) == 'asserting'])}"
          f"/{n_assert} asserting scenario(s) PASS (arming refusals, RTL, failsafe, "
          f"measurement canary)")
    print(f"measurement: {len(measuring)} informational scenario(s) - reported, not "
          f"gated, because they declare no pass criterion")
    for n, v in sorted(measuring.items()):
        print(f"     ~ {n:20} {str(v)[:74]}")

    if problems:
        print(f"\nFAIL - {len(problems)} problem(s):")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("\nSITL is green against the parameters that ship")
    return 0


#soop_sitl

"""Gate the SoOP backend's fix reaching the EKF in SITL.

Usage:
    python3 tools/check_firmware.py soop_sitl
"""

PY = os.environ.get("PY", os.path.expanduser("~/.cache/navcore/apvenv/bin/python3"))
TEST = os.path.join(REPO, "tools", "soop_sitl_test.py")


def run_soop_sitl():
    if not os.path.exists(PY):
        print(f"SOOP SITL CHECK FAILED - no python venv at {PY}")
        return 1
    if not os.path.exists(TEST):
        print(f"SOOP SITL CHECK FAILED - no test script at {TEST}")
        return 1

    r = subprocess.run([PY, TEST, "--seconds", "60"], cwd=REPO)
    return r.returncode


CHECKS = {
    "hwdef": run_hwdef,
    "params": run_params,
    "features": run_features,
    "bdshot": run_bdshot,
    "soop_backend": run_soop_backend,
    "sitl": run_sitl,
    "soop_sitl": run_soop_sitl,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        print(__doc__)
        return 2
    return CHECKS[sys.argv.pop(1)]()


if __name__ == "__main__":
    sys.exit(main())
