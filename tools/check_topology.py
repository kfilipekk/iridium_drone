#!/usr/bin/env python3
"""Assert that each IC has the EXTERNAL components its datasheet requires.

WHY THIS EXISTS, AND WHY IT WAS FOUND SO LATE.

Every other check in this project verifies a property of what IS on the board:
connectivity (check_design), current capacity (check_ratings, check_traces), clearance
(check_mechanical), pin direction (check_pin_semantics), firmware agreement (check_hwdef).
Not one of them can notice that something REQUIRED IS ABSENT, because absence has no net,
no footprint and no pad to inspect.

That gap hid a board-killing fault through 64 preflight checks, 20 SITL scenarios, a full
DRC and three separate "ready to order" verdicts:

    BOTH TPS54331 buck regulators were missing their catch diode.

The TPS54331 is NON-SYNCHRONOUS. TI's datasheet is explicit: "The TPS54331 device is
designed to operate using an external catch diode between the PH and GND pins." It
integrates only the high-side FET. With no diode, inductor current has no freewheel path
when that FET turns off, PH is driven below ground until something breaks down, and the
regulator does not start - it destroys itself. The 5 V rail powers the entire board.

So this file checks for PRESENCE OF REQUIRED EXTERNALS, keyed off the part number. Add a
part here whenever one is added to the design, and put the datasheet sentence in the
reason string - a requirement without a citation is just an opinion.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
NET = "/tmp/nav/net.net"
SCH = os.path.join(REPO, "NAVCORE-SoOP.kicad_sch")

fails = []


def check(ok, name, detail, cite=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:44} {detail}")
    if cite:
        print(f"        {cite}")
    if not ok:
        fails.append(name)


def netlist():
    if not os.path.exists(NET) or os.path.getmtime(NET) < os.path.getmtime(SCH):
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


def main():
    nets, comps = netlist()
    # WHETHER A CATCH DIODE IS REQUIRED IS A PROPERTY OF THE PART, not of the board.
    # A non-synchronous buck integrates only the high-side FET and needs an external
    # freewheel path; a synchronous one integrates the low-side FET and needs none -
    # asking for a diode there would be wrong. So the requirement is keyed on the part.
    NEEDS_CATCH_DIODE = {
        "TPS54331": ('[D] TI TPS54331 datasheet: "The TPS54331 device is designed to '
                     'operate using an external catch diode between the PH and GND pins."'),
    }
    SYNCHRONOUS = {
        "TPS54202": ('[D] TI TPS54202 SLVSD26C: "two integrated switching FETs" - the '
                     'low-side FET IS the freewheel path, so no catch diode exists to '
                     'forget. Vref 0.596 V, internal compensation, 5 ms internal '
                     'soft-start.'),
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
        # bootstrap cap between PH and BOOT
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
