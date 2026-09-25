#!/usr/bin/env python3
"""Cross-check the generated hwdef against the netlist it is supposed to describe."""
import os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design, symlib
from hwdef_pinmap import parse

HW = "firmware/NAVCORE_SoOP/hwdef.dat"


def main():
    pins, _alts = parse(HW)
    txt = open(HW).read()

    syms = symlib.load()
    h7 = {p['num']: p['name'] for p in syms["STM32H743VIT6_C114409"]}
    used = set()
    for net, specs in design.NETS.items():
        for sp in specs:
            ref, pin = sp.split(".", 1)
            if ref != "U1": continue
            nm = h7.get(pin, pin)
            used.add(nm.split("-")[0])
    for pin in list(pins):
        pass

    errs, warns = [], []

    # 1. every pin the hwdef declares must be wired on the board
    for p in pins:
        if p not in used:
            errs.append(f"hwdef declares {p} ({pins[p]['label']}) but the netlist does not wire it")

    # 2. every SPIDEV must name a CS pin the hwdef declares
    cs_pins = {v['label'] for v in pins.values() if v['periph'] == 'CS'}
    for m in re.finditer(r'^SPIDEV\s+(\S+)\s+(\S+)\s+\S+\s+(\S+)', txt, re.M):
        dev, bus, cs = m.groups()
        if cs not in cs_pins:
            errs.append(f"SPIDEV {dev} uses CS '{cs}' which the hwdef never declares")

    # 3. every IMU/BARO must reference a device that exists
    spidevs = set(re.findall(r'^SPIDEV\s+(\S+)', txt, re.M))
    for m in re.finditer(r'^IMU\s+\S+\s+SPI:(\S+)', txt, re.M):
        if m.group(1) not in spidevs:
            errs.append(f"IMU references SPIDEV '{m.group(1)}' which is not declared")
    baros = re.findall(r'^BARO\s+(\S+)\s+(\S+)', txt, re.M)

    # 4. sensors declared vs sensors actually on the BOM
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

    # Each IMU's rotation, recomputed from its pads and the board's forward edge. The first
    # hwdef copied MatekH743's rotations and flipped them for the bottom side - both IMUs
    # came out upside down, and 90 degrees apart although they are placed identically.
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

    # Each IMU's SPI lines, followed from its pads to the MCU. Check 2 only asked that a CS
    # label exists; U3 was addressed through PC13 while its CS pad is wired to PE11.
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


if __name__ == "__main__":
    sys.exit(main())
