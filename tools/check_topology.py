#!/usr/bin/env python3
"""Assert that each IC has the external components its datasheet requires."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
NET = "/tmp/nav/net.net"
SCH = os.path.join(REPO, "NAVCORE-SoOP.kicad_sch")
if "--sch" in sys.argv:                      # check another schematic (negative tests)
    SCH = sys.argv[sys.argv.index("--sch") + 1]
    NET = "/tmp/nav/net-alt.net"

fails = []


def check(ok, name, detail, cite=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:44} {detail}")
    if cite:
        print(f"        {cite}")
    if not ok:
        fails.append(name)


def netlist():
    if "--sch" in sys.argv or not os.path.exists(NET) or os.path.getmtime(NET) < os.path.getmtime(SCH):
        os.makedirs(os.path.dirname(NET), exist_ok=True)
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr",
                        "-o", NET, SCH], capture_output=True, timeout=600)
    t = open(NET).read()
    nets = {}
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]+)"\)(.*?)(?=\(net \(code|\Z)',
                         t, re.S):
        nets[m.group(1)] = {f"{r}.{p}" for r, p
                            in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)',
                                          m.group(2))}
    comps = dict(re.findall(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]+)"\)', t))
    return nets, comps


# part -> list of (description, predicate over (nets, comps, ref), datasheet citation)
def tps54331_catch_diode(nets, comps, ref, ph_net):
    """A diode, anode to GND, cathode to PH. Look for any non-LED, non-TVS diode on PH."""
    on_ph = nets.get(ph_net, set())
    diodes = {r for r in (n.split(".")[0] for n in on_ph)
              if r.startswith("D") and comps.get(r, "") not in ("BLUE", "GREEN", "RED")}
    return diodes


def ohms(v):
    """'4k7' -> 4700, '330R' -> 330, '1k' -> 1000, '10' -> 10."""
    m = re.fullmatch(r"(\d+)([kKmMR]?)(\d*)", v.strip())
    if not m:
        return None
    mult = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6, "R": 1, "": 1}[m.group(2)]
    return float(f"{m.group(1)}.{m.group(3) or 0}") * mult


def main():
    nets, comps = netlist()
    # Whether A catch diode is required is A property of the part, not of the board.
    NEEDS_CATCH_DIODE = {
        "TPS54331": ('[D] TI TPS54331 datasheet: "The TPS54331 device is designed to '
                     'operate using an external catch diode between the PH and GND pins."'),
    }
    SYNCHRONOUS = {
        "TPS54202": ('[D] TI TPS54202 SLVSD26C: "two integrated switching FETs" - the '
                     'low-side FET IS the freewheel path, so no catch diode exists to '
                     'forget. Vref 0.596 V, internal compensation, 5 ms internal '
                     'soft-start.'),
        "LMR33630A": ('[D] TI SNVSAN3F: "3.8-V to 36-V, 3-A synchronous buck converter" '
                      'with R(HSD) and R(LSD) integrated (7.5 lists both) - the low-side '
                      'FET IS the freewheel path, so no catch diode exists to forget. '
                      'Vref 1.000 V, internally compensated. The RNX variant additionally '
                      'ties the SW pin to the NC pin on the PCB (10.1).'),
    }
    print("=== buck regulators: is the required freewheel path present? ===")
    for ref, ph, boot, out in (("U8", "BUCK_PH", "BUCK_BOOT", "+5V"),
                               ("U18", "BUCK9_PH", "BUCK9_BOOT", "+9V")):
        if ref not in comps:
            continue
        part = comps[ref]
        if part in SYNCHRONOUS:
            check(True, f"{ref} ({part}) freewheel path",
                  "SYNCHRONOUS - the low-side FET is internal, no catch diode required",
                  SYNCHRONOUS[part])
        elif part in NEEDS_CATCH_DIODE:
            d = tps54331_catch_diode(nets, comps, ref, ph)
            check(bool(d), f"{ref} ({part}) catch diode on {ph}",
                  f"found {sorted(d)}" if d else
                  "MISSING - inductor current has no freewheel path when the high-side "
                  "FET turns off. The rail will not start and the IC is likely destroyed",
                  NEEDS_CATCH_DIODE[part])
        else:
            check(False, f"{ref} ({part}) topology",
                  "UNKNOWN PART - add it to NEEDS_CATCH_DIODE or SYNCHRONOUS with its "
                  "datasheet citation. An unclassified regulator is not a passing one")
        # bootstrap cap between PH and boot
        bc = nets.get(boot, set()) & {n for n in nets.get(ph, set())
                                      if n.split(".")[0].startswith("C")}
        shared = {n.split(".")[0] for n in nets.get(boot, set()) if n.startswith("C")} & \
                 {n.split(".")[0] for n in nets.get(ph, set()) if n.startswith("C")}
        check(bool(shared), f"{ref} bootstrap cap {ph}-{boot}",
              f"found {sorted(shared)}" if shared else "MISSING")
        check(bool(nets.get(out)), f"{ref} output net {out} exists",
              f"{len(nets.get(out, []))} nodes")

    print("\n=== STM32H743: externals without which the MCU does not run ===")
    for net, what, cite in (
        ("VCAP1", "core LDO decoupling", "[D] RM0433 / DS12110: VCAP1 and VCAP2 each need "
                                         "a 2.2 uF ceramic. The internal core regulator "
                                         "does not start without them"),
        ("VCAP2", "core LDO decoupling", "[D] as VCAP1"),
        ("NRST",  "reset filter",        "[D] DS12110 recommends a 100 nF on NRST"),
    ):
        caps = {n.split(".")[0] for n in nets.get(net, set()) if n.startswith("C")}
        check(bool(caps), f"{net} has a capacitor", f"found {sorted(caps)}" if caps
              else "MISSING", cite)
    pulls = {n.split(".")[0] for n in nets.get("BOOT0", set()) if n.startswith("R")}
    check(bool(pulls), "BOOT0 has a defined level", f"found {sorted(pulls)}" if pulls
          else "FLOATING - the MCU may boot to the system bootloader at random",
          "[D] AN2606: BOOT0 must be driven, not left floating")

    # ------------------------------------------------------------------
    # The gate must be defined, or the board is dead with a correct battery connected.
    print("\n=== P-FET reverse-polarity protection: is the gate defined? ===")
    AND90146 = ('[D] ON Semi AND90146/D "Reverse Polarity Protection using a '
                'P-Channel MOSFET" (Fig. 4): "When the battery is properly connected, '
                'the intrinsic body diode is conductive till the MOSFET\'s channel is '
                'turned ON... When the battery is reversely connected, the body diode '
                'is reversed biased, gate and source have the same voltage thus turning '
                'OFF the P-Channel MOSFET. An additional Zener diode is used to clamp '
                'the gate of the P-Channel MOSFET and protect it in the case of a too '
                'high voltage." docs/datasheets/AND90146-D.pdf')
    # Do not skip when the ref is absent.
    for ref, part in (("Q4", "WST4041"),):
        if ref not in comps:
            check(False, f"{ref} ({part}) is present",
                  "ABSENT - the reverse-polarity FET is not in the netlist at all. "
                  "Nothing else in this toolchain needs it, so nothing else will "
                  "notice: a reversed pack forward-biases D1, which clamps at -0.7 V "
                  "and dies shorting the rail.", AND90146)
            continue
        if comps[ref] != part:
            check(False, f"{ref} is not {part}",
                  f"found {comps[ref]} - the protection FET changed; re-verify the rule")
            continue
        # the gate net is whatever sits on the FET's gate pin (pin 1)
        gate_nets = [n for n, pins in nets.items() if f"{ref}.1" in pins]
        if not gate_nets:
            check(False, f"{ref} gate is wired", "MISSING - the gate pin has no net",
                  AND90146)
            continue
        gn = gate_nets[0]
        src = [n for n, pins in nets.items() if f"{ref}.2" in pins]
        drn = [n for n, pins in nets.items() if f"{ref}.3" in pins]
        on_gn = {x.split(".")[0] for x in nets.get(gn, set())}
        # 1. the pull-down: a resistor with its other leg on GND. A floating gate
        #    means the FET never turns on - a correct battery, dead board.
        gnd_refs = {x.split(".")[0] for x in nets.get("GND", set())}
        pulls = sorted(on_gn & {r for r in gnd_refs if r.startswith("R")})
        check(bool(pulls), f"{ref} ({part}) gate pull-down to GND",
              f"found {pulls}" if pulls else
              "MISSING PULL-DOWN - the gate floats and the P-FET never conducts, so "
              "the board is dead with a CORRECT battery connected. R46 (100k) is the "
              "gate-to-GND resistor.", AND90146)
        # 2. the clamp: a zener with one leg on the gate net and one on the source
        #    (cathode to source, anode to gate - AND90146 Fig. 4).
        if src:
            src_refs = {x.split(".")[0] for x in nets.get(src[0], set())}
            zs = sorted(r for r in on_gn if r.startswith("D") and r in src_refs)
            check(bool(zs), f"{ref} ({part}) gate-source zener clamp",
                  f"found {zs}" if zs else
                  "MISSING - nothing clamps Vgs. A 4S pack alone is -16.8 V (inside "
                  "the WST4041's +-20 V), but a surge on the battery side can exceed "
                  "it; DZ1 (BZT52C15) clamps at ~15 V.", AND90146)
        check(bool(src and drn and "VBAT" in src and "VBAT_IN" in drn),
              f"{ref} ({part}) oriented drain->battery, source->load",
              f"source on {', '.join(src)}, drain on {', '.join(drn)}", AND90146)

    # The PLL shipped with its loop filter hanging off CPOUT and VTUNE on a capacitor of its
    # own - the two never met, so the VCO could not be steered and the tuner never locks.
    # Every consistency check passed it, because design.py itself had the two nets apart.
    print("\n=== MAX2112 tuner: PLL loop filter and gain control ===")
    MAX2112 = ('[D] MAX2112 datasheet, Pin Description: "VTUNE: connect the PLL loop filter '
               'output directly to this pin"; "CPOUT: connect to the PLL loop filter input"; '
               '"GC1: 0.5 V to 2.7 V operating range". Typical Application Circuit: shunt C '
               'and series R-C at CPOUT, series R to VTUNE, shunt C at VTUNE.')
    for ref in [r for r, v in comps.items() if v.startswith("MAX2112")]:
        def pin_net(p):
            return next((n for n, pins in nets.items() if f"{ref}.{p}" in pins), None)
        cp, vt, gc = pin_net(12), pin_net(9), pin_net(5)
        gnd = nets.get("GND", set())
        def two_pin(r, a, b):
            pa = {x for x in nets.get(a, set()) if x.split(".")[0] == r}
            pb = {x for x in nets.get(b, set()) if x.split(".")[0] == r}
            return pa and pb
        refs_on = lambda n: {x.split(".")[0] for x in nets.get(n, set())}
        linked = cp is not None and (cp == vt or any(
            r.startswith("R") and two_pin(r, cp, vt) for r in refs_on(cp)))
        check(linked, f"{ref} VTUNE driven by the loop filter",
              f"CPOUT {cp} -> VTUNE {vt}" if linked else
              f"NOT CONNECTED - CPOUT ({cp}) has no path to VTUNE ({vt}); the VCO cannot "
              "be steered and the PLL never locks", MAX2112)
        c1 = sorted(r for r in refs_on(cp) if r.startswith("C") and two_pin(r, cp, "GND"))
        check(bool(c1), f"{ref} CPOUT shunt capacitor", f"found {c1}" if c1 else "MISSING")
        zero = []
        for r in refs_on(cp):
            if not r.startswith("R"):
                continue
            other = [n for n, pins in nets.items() if any(x.startswith(r + ".") for x in pins)
                     and n not in (cp, vt)]      # R3 into VTUNE is not the zero
            for o in other:
                if any(c.startswith("C") and two_pin(c, o, "GND") for c in refs_on(o)):
                    zero.append(r)
        check(bool(zero), f"{ref} CPOUT series R-C (the loop zero)",
              f"found {sorted(zero)}" if zero else "MISSING - without the zero the loop is "
              "unstable")
        c3 = sorted(r for r in refs_on(vt) if r.startswith("C") and two_pin(r, vt, "GND"))
        check(bool(c3), f"{ref} VTUNE shunt capacitor", f"found {c3}" if c3 else "MISSING")
        # GC1 bias from its divider: resistors to GND against resistors to the RF supply.
        down = [ohms(comps[r]) for r in refs_on(gc) if r.startswith("R") and two_pin(r, gc, "GND")]
        up = [ohms(comps[r]) for r in refs_on(gc) if r.startswith("R")
              and any(two_pin(r, gc, n) for n in ("VCC_RF", "+3V3A", "+3V3"))]
        par = lambda rs: 1 / sum(1 / x for x in rs) if rs and all(rs) else None
        rd, ru = par(down), par(up)
        v = 3.3 * rd / (rd + ru) if rd and ru else (0.0 if rd else None)
        ok = v is not None and 0.5 <= v <= 2.7
        check(ok, f"{ref} GC1 within 0.5-2.7 V",
              f"{v:.2f} V from the divider" if v is not None else "undriven")

    print("\n=== LDOs: a wrong or absent output cap makes an LDO oscillate ===")
    for ref, part, vin, vout in (("U9", "AP2112K-3.3", "+5V", "+3V3"),
                                 ("U10", "TLV75533", "+5V", "+3V3A")):
        if ref not in comps:
            continue
        for net, role in ((vin, "input"), (vout, "output")):
            caps = {n.split(".")[0] for n in nets.get(net, set()) if n.startswith("C")}
            check(bool(caps), f"{ref} {part} {role} cap on {net}",
                  f"{len(caps)} capacitor(s) on the rail" if caps else "MISSING",
                  "[D] both parts specify >=1 uF in and out; ceramic, close to the pins. "
                  "Presence is checkable here, PROXIMITY is not - that is a layout review")

    print()
    if fails:
        print(f"FAIL - {len(fails)} required external component(s) absent: "
              f"{', '.join(fails)}")
        print("THIS IS NOT FIXABLE IN SOFTWARE. Do not order the board.")
        return 1
    print("every datasheet-required external is present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
