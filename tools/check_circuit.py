#!/usr/bin/env python3
"""Schematic and electrical checks on design.py and the parts it names.

Usage:  python3 tools/check_circuit.py CHECK [options]

Checks:
  design             Validate tools/design.py before anything is generated from it.
  topology           Assert that each IC has the external components its datasheet requires.
  electrical         Check the analogue reality: decoupling, dividers, pull-ups, protection.
  esd                Does every signal that leaves the board on a cable have a clamp at its connector?
  ratings            Is every part actually rated for the net it is soldered to?
  symbol_pinout      Compare every active part's symbol pinout against an authority that is not this project.
  pin_semantics      Check that every MCU pin is wired to the right end of the thing it talks to.
  thermal            Thermal check for the switching regulators and the 3V3 rail.
"""
import collections, math, os, re, subprocess, sys
import design, jlcpaths, pcbnew, symlib
from hwdef_pinmap import parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOARD = (sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv
         else os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb"))



#design

"""Validate tools/design.py before anything is generated from it."""

STOCK = "/usr/share/kicad/symbols"


def load_all_symbols():
    syms = symlib.load()
    #every stock library a component names
    used = {c[0].split(":", 1)[0] for c in design.COMPONENTS.values() if ":" in c[0]}
    for libfile in sorted(used - {"jlc_parts"}):
        p = f"{STOCK}/{libfile}.kicad_sym"
        if os.path.exists(p):
            for k, v in symlib.load(p).items():
                syms[f"{libfile}:{k}"] = v
    return syms


def resolve(syms, ref, pinspec):
    symname = design.COMPONENTS[ref][0]
    key = symname.split(":", 1)[1] if symname.startswith("jlc_parts:") else symname
    pins = syms.get(key) or syms.get(symname)
    if pins is None:
        return None, f"symbol not found: {symname}"
    for p in pins:
        if p['num'] == pinspec:
            return p['num'], None
    named = [p for p in pins if p['name'] == pinspec]
    if len(named) == 1:
        return named[0]['num'], None
    if len(named) > 1:
        return None, f"pin name '{pinspec}' is ambiguous on {symname} ({len(named)} matches)"
    #allow "PC15" to match a pin named "PC15-OSC32_OUT"
    pre = [p for p in pins if p['name'].split('-')[0] == pinspec]
    if len(pre) == 1:
        return pre[0]['num'], None
    return None, f"no pin '{pinspec}' on {symname}"


def run_design():
    syms = load_all_symbols()
    errors, warnings = [], []
    owner, resolved = {}, {}

    for netname, pins in design.NETS.items():
        for spec in pins:
            if "." not in spec:
                errors.append(f"{netname}: malformed pin spec '{spec}'"); continue
            ref, pin = spec.split(".", 1)
            if ref not in design.COMPONENTS:
                errors.append(f"{netname}: unknown component '{ref}'"); continue
            num, err = resolve(syms, ref, pin)
            if err:
                errors.append(f"{netname}: {spec} -> {err}"); continue
            key = (ref, num)
            if key in owner and owner[key] != netname:
                errors.append(f"SHORT: {ref}.{num} on both '{owner[key]}' and '{netname}'")
            owner[key] = netname
            resolved.setdefault(netname, []).append((ref, num))

    #unconnected pins
    for ref, (symname, *_rest) in design.COMPONENTS.items():
        key = symname.split(":", 1)[1] if symname.startswith("jlc_parts:") else symname
        pins = syms.get(key) or syms.get(symname)
        if not pins: continue
        unconn = [p['num'] for p in pins
                  if (ref, p['num']) not in owner and p['name'] not in ("NC", "DNC", "RESV")]
        if unconn:
            warnings.append(f"{ref} ({design.COMPONENTS[ref][2]}): unconnected {','.join(unconn)}")

    #MCU vs hwdef
    hw, _alts = parse("firmware/reference/MatekH743-hwdef.dat")
    sym_h7 = syms.get("STM32H743VIT6_C114409", [])
    num2name = {p['num']: p['name'] for p in sym_h7}
    used = {num2name[n] for (r, n) in owner if r == "U1" and n in num2name}
    gpio_used = {u for u in used if re.match(r'^P[A-H]\d', u)}
    gpio_used = {u.split('-')[0] for u in gpio_used}
    hwdef_pins = set(hw)
    missing = sorted(hwdef_pins - gpio_used)
    OUTSIDE_HWDEF = {"PH0","PH1",          #HSE crystal - hwdef declares OSCILLATOR_HZ, not pins
                     "PB2","PE15","PC2_C","PC3_C"}   #spare pins broken out to test pads
    extra   = sorted(gpio_used - hwdef_pins - OUTSIDE_HWDEF)

    print(f"components : {len(design.COMPONENTS)}")
    print(f"nets       : {len(design.NETS)}")
    print(f"connections: {sum(len(v) for v in resolved.values())}")
    print(f"\nMCU vs MatekH743 hwdef:")
    print(f"  hwdef assigns {len(hwdef_pins)} pins; design uses {len(gpio_used)}")
    print(f"  in hwdef but NOT wired : {len(missing)}  {missing if missing else ''}")
    print(f"  wired but NOT in hwdef : {len(extra)}  {extra if extra else ''}")

    #board value fields vs design.py
    try:
        import pcbnew
        _b = pcbnew.LoadBoard(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "NAVCORE-SoOP.kicad_pcb"))
        #the set comparison
        board_refs = {fp.GetReference() for fp in _b.GetFootprints()}
        fitted = {r for r, c in design.COMPONENTS.items() if not c[4] and c[1]}
        placed = {r for r, c in design.COMPONENTS.items() if c[1]}   #incl
        missing_from_board = sorted(fitted - board_refs)
        stale_on_board     = sorted(board_refs - placed)
        if missing_from_board:
            errors.append(f"BOARD IS BEHIND design.py: {len(missing_from_board)} fitted "
                          f"part(s) have no footprint on the artwork - "
                          f"{', '.join(missing_from_board)}")
        if stale_on_board:
            errors.append(f"BOARD IS AHEAD OF design.py: {len(stale_on_board)} footprint(s) "
                          f"on the artwork are in no longer in the design - "
                          f"{', '.join(stale_on_board)}")

        for fp in _b.GetFootprints():
            ref = fp.GetReference()
            comp = design.COMPONENTS.get(ref)
            if not comp or not comp[2]:
                continue
            if fp.GetValue() != comp[2]:
                errors.append(f"{ref}: board says {fp.GetValue()!r}, "
                              f"design.py says {comp[2]!r}")

        #pad by pad
        single = {n for n, pins in design.NETS.items() if len(set(pins)) == 1}
        pad_diff = []
        for fp in _b.GetFootprints():
            ref = fp.GetReference()
            if ref not in design.COMPONENTS:
                continue
            for pad in fp.Pads():
                num = pad.GetNumber()
                if not num:
                    continue
                have = pad.GetNetname()
                if have.startswith(("unconnected-", "Net-(")):
                    have = ""
                want = owner.get((ref, num), "")
                if want in single:
                    want = ""
                if have != want:
                    pad_diff.append(f"{ref}.{num} is {have or 'unconnected'} on the board, "
                                    f"{want or 'unconnected'} in design.py")
        if pad_diff:
            errors.append(f"BOARD AND design.py DISAGREE on {len(pad_diff)} pad(s) - "
                          + "; ".join(sorted(set(pad_diff))[:6])
                          + (" ..." if len(set(pad_diff)) > 6 else ""))
    except ImportError:
        warnings.append("pcbnew unavailable - board value fields NOT checked")

    #the same comparison, for the schematic
    #nothing checked it
    SCH_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "NAVCORE-SoOP.kicad_sch")
    DESIGN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "design.py")
    if not os.path.exists(SCH_FILE):
        errors.append("NAVCORE-SoOP.kicad_sch is missing - run tools/gen_sch.py")
    else:
        #Mtime is advisory, not a gate
        if os.path.getmtime(SCH_FILE) < os.path.getmtime(DESIGN_FILE):
            warnings.append("schematic mtime is older than design.py - harmless after a "
                            "clone or a rebase, but regenerate it if you edited design.py "
                            "by hand (the content check below is the authority)")
        try:
            sch_nets, sch_comps = netlist()
            sch_refs = set(sch_comps)
            #PWR_FLAG symbols are schematic-only (no footprint) and legitimately absent
            want_refs = {r for r, c in design.COMPONENTS.items() if c[1]}
            sch_refs = {r for r in sch_refs if r in design.COMPONENTS and
                        design.COMPONENTS[r][1]}
            missing_sch = sorted(want_refs - sch_refs)
            extra_sch = sorted(r for r in sch_comps
                               if r not in design.COMPONENTS)
            if missing_sch:
                errors.append(f"SCHEMATIC IS BEHIND design.py: {len(missing_sch)} "
                              f"part(s) are in the design and not in the schematic - "
                              f"{', '.join(missing_sch)}")
            if extra_sch:
                errors.append(f"SCHEMATIC IS AHEAD OF design.py: {len(extra_sch)} "
                              f"symbol(s) are in the schematic and in no design - "
                              f"{', '.join(extra_sch)}")
            want_nets = {n for n, pins in design.NETS.items() if len(set(pins)) > 1}
            missing_nets = sorted(want_nets - set(sch_nets))
            if missing_nets:
                errors.append(f"SCHEMATIC IS MISSING {len(missing_nets)} net(s) the "
                              f"design declares - {', '.join(missing_nets[:12])}"
                              + (" ..." if len(missing_nets) > 12 else ""))
            #net membership, not just net NAMES
            flags = set(getattr(design, "PWR_FLAGS", {}).values())
            wrong = []
            for n in sorted(want_nets & set(sch_nets)):
                want_pins = {f"{r}.{num}" for r, num in resolved.get(n, [])
                             if r not in flags}
                if want_pins and want_pins != sch_nets[n]:
                    only_design = sorted(want_pins - sch_nets[n])[:4]
                    only_sch = sorted(sch_nets[n] - want_pins)[:4]
                    wrong.append(f"{n} (design has {only_design or 'nothing extra'}, "
                                 f"schematic has {only_sch or 'nothing extra'})")
            if wrong:
                errors.append(f"SCHEMATIC DISAGREES with design.py on {len(wrong)} net(s) "
                              f"- {'; '.join(wrong[:4])}"
                              + (" ..." if len(wrong) > 4 else ""))
            print(f"schematic  : {len(sch_refs)} symbols, {len(sch_nets)} nets")
        except Exception as e:
            warnings.append(f"schematic netlist could not be exported ({e}) - "
                            "kicad-cli needed; schematic NOT set-checked")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings: print("  ", w)
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors: print("  ", e)
        return 1
    print("\nno errors.")
    return 0


#topology

"""Assert that each IC has the external components its datasheet requires."""

NET = "/tmp/nav/net.net"
SCH = os.path.join(REPO, "NAVCORE-SoOP.kicad_sch")
if "--sch" in sys.argv:                      #check another schematic (negative tests)
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
        r = subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr",
                            "-o", NET, SCH], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            #an old netlist left in place would be checked instead of the schematic
            if os.path.exists(NET):
                os.remove(NET)
            raise SystemExit(f"kicad-cli cannot export the netlist from {SCH}: "
                             f"{(r.stderr or r.stdout).strip()}")
    t = open(NET).read()
    nets = {}
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]+)"\)(.*?)(?=\(net \(code|\Z)',
                         t, re.S):
        nets[m.group(1)] = {f"{r}.{p}" for r, p
                            in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)',
                                          m.group(2))}
    comps = dict(re.findall(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]+)"\)', t))
    return nets, comps


#part -> list of (description, predicate over (nets, comps, ref), datasheet citation)
def tps54331_catch_diode(nets, comps, ref, ph_net):
    """A diode, anode to GND, cathode to PH."""
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


def run_topology():
    nets, comps = netlist()
    #whether a catch diode is required is a property of the part
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
        #bootstrap cap between PH and boot
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

    #the gate must be defined
    print("\n=== P-FET reverse-polarity protection: is the gate defined? ===")
    AND90146 = ('[D] ON Semi AND90146/D "Reverse Polarity Protection using a '
                'P-Channel MOSFET" (Fig. 4): "When the battery is properly connected, '
                'the intrinsic body diode is conductive till the MOSFET\'s channel is '
                'turned ON... When the battery is reversely connected, the body diode '
                'is reversed biased, gate and source have the same voltage thus turning '
                'OFF the P-Channel MOSFET. An additional Zener diode is used to clamp '
                'the gate of the P-Channel MOSFET and protect it in the case of a too '
                'high voltage." docs/datasheets/AND90146-D.pdf')
    #do not skip when the ref is absent
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
        #the gate net is whatever sits on the FET's gate pin (pin 1)
        gate_nets = [n for n, pins in nets.items() if f"{ref}.1" in pins]
        if not gate_nets:
            check(False, f"{ref} gate is wired", "MISSING - the gate pin has no net",
                  AND90146)
            continue
        gn = gate_nets[0]
        src = [n for n, pins in nets.items() if f"{ref}.2" in pins]
        drn = [n for n, pins in nets.items() if f"{ref}.3" in pins]
        on_gn = {x.split(".")[0] for x in nets.get(gn, set())}
        #1. the pull-down: a resistor with its other leg on GND
        gnd_refs = {x.split(".")[0] for x in nets.get("GND", set())}
        pulls = sorted(on_gn & {r for r in gnd_refs if r.startswith("R")})
        check(bool(pulls), f"{ref} ({part}) gate pull-down to GND",
              f"found {pulls}" if pulls else
              "MISSING PULL-DOWN - the gate floats and the P-FET never conducts, so "
              "the board is dead with a CORRECT battery connected. R46 (100k) is the "
              "gate-to-GND resistor.", AND90146)
        #2. the clamp
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

    #the PLL shipped with its loop filter hanging off CPOUT and VTUNE on a capacitor of its own
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
                     and n not in (cp, vt)]      #R3 into VTUNE is not the zero
            for o in other:
                if any(c.startswith("C") and two_pin(c, o, "GND") for c in refs_on(o)):
                    zero.append(r)
        check(bool(zero), f"{ref} CPOUT series R-C (the loop zero)",
              f"found {sorted(zero)}" if zero else "MISSING - without the zero the loop is "
              "unstable")
        c3 = sorted(r for r in refs_on(vt) if r.startswith("C") and two_pin(r, vt, "GND"))
        check(bool(c3), f"{ref} VTUNE shunt capacitor", f"found {c3}" if c3 else "MISSING")
        #GC1 bias from its divider
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
    for ref, part, vin, vout in (("U9", "TLV75733P", "+5V", "+3V3"),
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


#electrical

"""Check the analogue reality: decoupling, dividers, pull-ups, protection.

Usage:  python3 tools/check_circuit.py electrical [-v]
"""

electrical_RAILS = {"+3V3", "+3V3A", "+3V3_CAN", "+5V", "+5V_PAYLOAD", "+9V", "VBAT", "VDDA", "VBUS"}
DECOUPLE_NEAR = 3.0        #mm; beyond this a 100n is not doing its job at 100 MHz
DECOUPLE_FAR  = 6.0        #mm; beyond this it is decoration

#datasheet-mandated externals and strapping, beyond plain decoupling
REQUIRED = [
    #STM32H743VIT6 core regulator
    ("U1",  "VCAP1/VCAP2 on the internal LDO",
     {"48": "VCAP1", "73": "VCAP2"}),
    #VDDA must reach the MCU through a ferrite from +3V3
    ("U1",  "VDDA filtered from +3V3 by a ferrite",
     {"21": "VDDA", "20": "VDDA"}),
    ("L1",  "the VDDA ferrite bridges +3V3 to VDDA",
     {"1": "+3V3", "2": "VDDA"}),
    #2 = PS (high selects I2C), 5 = CSB
    ("U4",  "MS5611 strapped for I2C at 0x77 (PS high, CSB low)",
     {"2": "+3V3A", "5": "GND"}),
    ("U11", "SN65HVD230 Rs is driven, not floating",
     {"8": None}),
    #USBLC6-2SC6 must sit between the connector and the MCU
    ("U12", "USBLC6 on the connector side of D+/D-",
     {"1": "USB_DP_CON", "3": "USB_DM_CON", "6": "USB_DP", "4": "USB_DM"}),
]


def value_of(ref):
    c = design.COMPONENTS.get(ref)
    return c[2] if c else None


def to_farads(v):
    if not v: return None
    m = re.fullmatch(r'(\d+)(p|n|u)(\d*)', v.strip())
    if not m: return None
    whole, unit, frac = m.groups()
    num = float(f"{whole}.{frac}" if frac else whole)
    return num * {"p": 1e-12, "n": 1e-9, "u": 1e-6}[unit]


def to_ohms(v):
    if not v: return None
    m = re.fullmatch(r'(\d+)(R|k|M)?(\d*)', v.strip())
    if not m: return None
    whole, unit, frac = m.groups()
    num = float(f"{whole}.{frac}" if frac else whole)
    return num * {"R": 1, None: 1, "k": 1e3, "M": 1e6}[unit]


def net_of_pad():
    out = {}
    for net, specs in design.NETS.items():
        for sp in specs:
            out[sp] = net
    return out


def electrical_positions():
    """Pad centre for every ref.pad, in mm, from the real board."""
    try:
        import pcbnew
    except ImportError:
        return None
    b = pcbnew.LoadBoard(BOARD)
    out = {}
    for fp in b.GetFootprints():
        r = fp.GetReference()
        for pad in fp.Pads():
            p = pad.GetPosition()
            out[f"{r}.{pad.GetNumber()}"] = (p.x / 1e6, p.y / 1e6)
    return out


def run_electrical():
    verbose = "-v" in sys.argv
    npad = net_of_pad()
    pos = electrical_positions()
    errs, warns, notes = [], [], []

    #what each ref's pads connect to
    pads_of = {}
    for sp in npad:
        ref, pad = sp.split(".", 1)
        pads_of.setdefault(ref, []).append(pad)

    #a decoupling cap is a two-pad capacitor with one leg on a rail and one on GND
    caps = {}
    for ref in design.COMPONENTS:
        if not ref.startswith("C"):
            continue
        legs = [(npad.get(f"{ref}.1"), npad.get(f"{ref}.2"))]
        (a, b), = legs
        if a in electrical_RAILS and b == "GND":
            caps.setdefault(a, []).append(ref)
        elif b in electrical_RAILS and a == "GND":
            caps.setdefault(b, []).append(ref)

    syms = symlib.load()
    ptype = {}
    for ref, c in design.COMPONENTS.items():
        nm = c[0].split(":")[-1]
        for pn in syms.get(nm, []):
            ptype[f"{ref}.{pn['num']}"] = pn.get("type")

    ics = sorted({r for r in design.COMPONENTS
                  if r.startswith("U") and not design.COMPONENTS[r][4]})
    worst = []
    for ic in ics:
        for pad in pads_of.get(ic, []):
            rail = npad.get(f"{ic}.{pad}")
            if rail not in electrical_RAILS:
                continue
            if ptype.get(f"{ic}.{pad}") != "power_in":
                continue                      #strapped logic pin, not a supply
            here = pos.get(f"{ic}.{pad}") if pos else None
            best, bref = None, None
            for cref in caps.get(rail, []):
                if to_farads(value_of(cref)) is None:
                    continue
                cp = pos.get(f"{cref}.1") if pos else None
                if here and cp:
                    d = math.hypot(here[0]-cp[0], here[1]-cp[1])
                    if best is None or d < best:
                        best, bref = d, cref
            if best is None:
                errs.append(f"{ic}.{pad} on {rail} has no decoupling capacitor at all")
            else:
                worst.append((best, f"{ic}.{pad}", rail, bref, value_of(bref)))
    worst.sort(reverse=True)
    for d, where, rail, cref, val in worst:
        if d > DECOUPLE_FAR:
            errs.append(f"{where} ({rail}): nearest cap {cref} {val} is {d:.1f} mm away")
        elif d > DECOUPLE_NEAR:
            warns.append(f"{where} ({rail}): nearest cap {cref} {val} is {d:.1f} mm away")

    #1b. datasheet-mandated externals
    for ref, what, pins in REQUIRED:
        if ref not in design.COMPONENTS:
            errs.append(f"{what}: {ref} is not in the design at all")
            continue
        for pin, want_net in (pins or {}).items():
            got = npad.get(f"{ref}.{pin}")
            if got is None:
                errs.append(f"{what}: {ref}.{pin} is not connected to any net")
            elif want_net is not None and got != want_net:
                errs.append(f"{what}: {ref}.{pin} is on '{got}', expected "
                            f"'{want_net}'")
        else:
            if pins:
                notes.append(f"{what}: {ref} " +
                             ", ".join(f"{k}->{npad.get(f'{ref}.{k}') or '(open)'}"
                                       for k in pins))

    #2. buck dividers
    #the reference is a property of the part
    VREF = design.VREF_V
    for ref, rail, vout_declared, rtop, rbot, _ind in design.BUCK_RAILS:
        name = f"{rail} buck ({ref})"
        _ref_part = design.COMPONENTS[ref][2]
        if _ref_part not in VREF:
            errs.append(f"{name}: regulator {_ref_part} has no reference voltage in "
                        f"design.VREF_V - add it with its datasheet citation before "
                        f"trusting this divider")
            continue
        vref = VREF[_ref_part][0]
        a, b = to_ohms(value_of(rtop)), to_ohms(value_of(rbot))
        if not a or not b:
            notes.append(f"{name}: cannot read {rtop}/{rbot}")
            continue
        vout = vref * (1 + a / b)
        want = {"+5V": 5.0, "+9V": 9.0, "+5V_PAYLOAD": 5.0}[rail]
        detail = (f"{name}: {value_of(rtop)}/{value_of(rbot)} on a {vref:.3f} V "
                  f"reference -> {vout:.3f} V (design.BUCK_RAILS declares "
                  f"{vout_declared:.3f} V, nominal {want} V)")
        if abs(vout - vout_declared) / vout_declared > 0.01:
            errs.append(detail + " - THE DECLARED RAIL VOLTAGE AND THE FITTED DIVIDER "
                                 "DISAGREE by more than 1%; one of the two is stale, "
                                 "and a thermal or load budget built on the stale one "
                                 "is built on a rail that does not exist")
        elif abs(vout - want) / want > 0.10:
            errs.append(detail + " - more than 10% off")
        elif abs(vout - want) / want > 0.05:
            warns.append(detail)
        else:
            notes.append(detail)
    #enable dividers set the undervoltage lockout
    PACK_EMPTY_V = design.CELLS * 3.3       #4S at 3.3 V/cell - land well before this
    #the lower bound is a property of the part too
    MIN_VIN = {"TPS54331": (3.5, "[D] TI TPS54331 datasheet"),
               "TPS54202": (4.5, "[D] SLVSD26C recommended operating conditions, "
                                 "VIN 4.5-28 V"),
               "LMR33630A": (3.8, "[D] SNVSAN3F 7.3 Recommended Operating Conditions, "
                                  "VIN 3.8-36 V")}
    for name, ref, rtop, rbot in (("5 V buck EN", "U8", "R4", "R5"),
                                  ("Payload 5 V buck EN", "U20", "R40", "R41")):
        a, b = to_ohms(value_of(rtop)), to_ohms(value_of(rbot))
        if not (a and b):
            notes.append(f"{name}: cannot read {rtop}/{rbot}")
            continue
        part = design.COMPONENTS[ref][2]
        ent = design.EN_THRESHOLD_V.get(part)
        if not ent:
            errs.append(f"{name}: regulator {part} has no EN threshold in "
                        f"design.EN_THRESHOLD_V - an unclassified regulator is not a "
                        f"checked one; add it with its datasheet citation")
            continue
        if part not in MIN_VIN:
            errs.append(f"{name}: regulator {part} has no minimum input voltage recorded, "
                        f"so there is nothing to say where this UVLO must sit")
            continue
        vth, confirmed, src = ent
        BUCK_MIN_VIN = MIN_VIN[part][0]
        uvlo = vth * (a + b) / b
        line = (f"{name}: {value_of(rtop)}/{value_of(rbot)} at a {vth} V threshold "
                f"-> starts at {uvlo:.1f} V in")
        if uvlo >= PACK_EMPTY_V:
            errs.append(line + f" - that is AT OR ABOVE a flat {design.CELLS}S pack "
                               f"({PACK_EMPTY_V:.1f} V); the rail would drop out in "
                               f"flight")
        elif uvlo <= BUCK_MIN_VIN:
            errs.append(line + f" - below {part}'s own {BUCK_MIN_VIN} V minimum "
                               f"input, so the UVLO does nothing")
        else:
            notes.append(line + f" (window {BUCK_MIN_VIN}-{PACK_EMPTY_V:.1f} V)")
        if not confirmed:
            warns.append(f"{name}: the {vth} V EN threshold for {part} is {src} - the "
                         f"UVLO figure above inherits that uncertainty")

    #3
    a, b = to_ohms(value_of("R18")), to_ohms(value_of("R19"))
    hw = open("firmware/NAVCORE_SoOP/hwdef.dat").read()
    m = re.search(r'define HAL_BATT_VOLT_SCALE\s+([\d.]+)', hw)
    if a and b and m:
        ratio = (a + b) / b
        declared = float(m.group(1))
        line = (f"battery divider {value_of('R18')}/{value_of('R19')} = {ratio:.2f}:1 "
                f"vs HAL_BATT_VOLT_SCALE {declared}")
        if abs(ratio - declared) / declared > 0.02:
            errs.append(line + " - MISMATCH, the reported pack voltage will be wrong")
        else:
            notes.append(line + " - agree")
        vmax = 3.3 * ratio
        notes.append(f"divider saturates the 3.3 V ADC at {vmax:.1f} V "
                     f"({vmax/4.2:.1f}S max, {vmax/3.7:.1f}S nominal)")

    #4. bus pull-ups
    pulls = {}
    for ref in design.COMPONENTS:
        if not ref.startswith("R"):
            continue
        a, b = npad.get(f"{ref}.1"), npad.get(f"{ref}.2")
        for sig, rail in ((a, b), (b, a)):
            if rail in electrical_RAILS and sig and sig not in electrical_RAILS and sig != "GND":
                pulls.setdefault(sig, []).append((ref, value_of(ref)))
    for bus in ("I2C1_SCL", "I2C1_SDA", "I2C2_SCL", "I2C2_SDA"):
        if bus not in pulls:
            errs.append(f"{bus} has no pull-up - an open-drain bus cannot idle high")
        else:
            r = to_ohms(pulls[bus][0][1])
            if r and not (1000 <= r <= 10000):
                warns.append(f"{bus} pull-up is {pulls[bus][0][1]} - outside 1k-10k")
    for cs in ("IMU1_CS", "IMU2_CS", "EXT_CS1", "EXT_CS2"):
        if cs not in pulls:
            notes.append(f"{cs} has no idle pull-up; it floats until the MCU drives it")

    #5. protection
    tvs = value_of("D1")
    if tvs:
        mv = re.search(r'SMBJ(\d+)', tvs or "")
        standoff = int(mv.group(1)) if mv else None
        clamp = design.TVS_CLAMP_V.get(tvs)
        #everything sitting directly on VBAT that has a declared maximum
        downstream = {}
        for ref, comp in design.COMPONENTS.items():
            if comp[4]:                                   #DNP parts still get fitted
                pass                                      #on the FPV variant - include
            part = comp[2]
            vmax = design.VBAT_PART_VMAX.get(part)
            if vmax and any(npad.get(f"{ref}.{pn}") == "VBAT"
                            for pn in (pads_of.get(ref) or [])):
                downstream[ref] = (part,) + vmax
        if standoff is not None:
            pack_max = design.CELLS * 4.2
            if standoff < pack_max:
                errs.append(f"D1 {tvs}: {standoff} V standoff is BELOW a full "
                            f"{design.CELLS}S pack ({pack_max:.1f} V) - it would "
                            f"conduct continuously")
        if not clamp:
            warns.append(f"D1 {tvs} has no clamping voltage in design.TVS_CLAMP_V - "
                         f"without it nothing can say whether this TVS protects "
                         f"anything; add it with its datasheet citation")
        elif not downstream:
            warns.append(f"D1 {tvs}: clamps at {clamp[0]} V, but no part on VBAT "
                         f"declares a maximum in design.VBAT_PART_VMAX - the "
                         f"comparison that matters cannot be made")
        else:
            vc, _vstand, _vbr, _ipp, vc_src = clamp
            #the binding part is the one with the lowest absolute maximum
            worst_ref, (worst_part, rec_v, abs_v, abs_ok, worst_src) = min(
                downstream.items(), key=lambda kv: kv[1][2])
            pack_max = design.CELLS * 4.2
            if vc > abs_v:
                cand = sorted(
                    (v[0], k) for k, v in design.TVS_CLAMP_V.items()
                    if v[0] <= abs_v and re.search(r'SMBJ(\d+)', k)
                    and int(re.search(r'SMBJ(\d+)', k).group(1)) >= pack_max)
                fix = (", ".join(f"{n} (clamps {c} V)" for c, n in cand)
                       if cand else "nothing in design.TVS_CLAMP_V qualifies - the input "
                                    "needs more than a TVS")
                errs.append(
                    f"D1 {tvs} clamps at {vc} V, ABOVE {worst_ref} ({worst_part}) whose "
                    f"absolute maximum input is {abs_v} V - a surge big enough to make "
                    f"this TVS conduct is passed to the regulator {vc - abs_v:.1f} V over "
                    f"its destruct limit, so the part it is placed to protect dies "
                    f"anyway. A {tvs} on a {design.CELLS}S ({pack_max:.1f} V) rail is "
                    f"simply oversized: it does nothing until ~37 V. Candidates that "
                    f"stand off the pack AND clamp under {abs_v} V: {fix}. "
                    f"{vc_src}; {worst_src}")
            else:
                notes.append(f"D1 {tvs}: clamps at {vc} V, under {worst_ref} "
                             f"({worst_part}) at {abs_v} V absolute - protects it. "
                             f"{vc_src}")
            if not abs_ok:
                warns.append(f"{worst_ref} ({worst_part}) absolute maximum input is "
                             f"{abs_v} V but that value is ASSUMED - the TVS verdict "
                             f"above rests on it. {worst_src}")
    #reverse-polarity protection
    prot = any(
        design.COMPONENTS[r][2] == "WST4041"
        and npad.get(f"{r}.2") == "VBAT"      #source -> protected rail
        and npad.get(f"{r}.3") == "VBAT_IN"   #drain -> battery side
        for r in design.COMPONENTS if r.startswith("Q"))
    if not prot:
        warns.append("no reverse-polarity protection on VBAT - a TVS clamps a reversed "
                     "pack at -0.7 V and dies, taking the rail with it")

    #6. crystal
    #the oscillator sees CL = (C15*C16)/(C15+C16) + stray
    c15, c16 = to_farads(value_of("C15")), to_farads(value_of("C16"))
    cl_spec = getattr(design, "Y1_CL_PF", None)
    stray = getattr(design, "Y1_STRAY_PF", 5.0)
    if c15 and c16:
        if abs(c15 - c16) > 1e-15:
            errs.append(f"crystal load caps differ: C15 {value_of('C15')} "
                        f"vs C16 {value_of('C16')} - they must match")
        presented = ((c15 * c16) / (c15 + c16)) * 1e12 + stray
        if cl_spec:
            if abs(presented - cl_spec) > 1.0:
                errs.append(f"C15/C16 {value_of('C15')} present {presented:.1f} pF but "
                            f"Y1 is declared CL = {cl_spec:.1f} pF - "
                            f"fit {int(round(2*(cl_spec-stray)))}p instead")
            else:
                notes.append(f"crystal load: {value_of('C15')} x2 present "
                             f"{presented:.1f} pF against Y1's declared "
                             f"CL = {cl_spec:.1f} pF")
    #an active oscillator fits this footprint and would have its supply grounded
    y1_lcsc = design.COMPONENTS["Y1"][3]
    allow = getattr(design, "Y1_PASSIVE_LCSC", set())
    if allow and y1_lcsc not in allow:
        errs.append(f"Y1 is {y1_lcsc}, which is not a known passive crystal. An active "
                    f"oscillator shares this SMD3225-4P land pattern and would have its "
                    f"VDD pin tied to ground here - the board would not start. Confirm "
                    f"the part is a two-terminal resonator and add it to "
                    f"design.Y1_PASSIVE_LCSC")
    want = {"1": "OSC_IN", "3": "OSC_OUT", "2": "GND", "4": "GND"}
    for pin, net in want.items():
        got = npad.get(f"Y1.{pin}")
        if got != net:
            errs.append(f"Y1 pin {pin} is on '{got}', expected '{net}' - that is not the "
                        f"passive-crystal wiring this footprint is drawn for")
    if c15 and c16:
        if not getattr(design, "Y1_CL_CONFIRMED", False):
            warns.append("Y1's load capacitance is ASSUMED, not read from a datasheet. "
                         "Wrong load is the one fault that can stop a board booting - "
                         "confirm it and set Y1_CL_CONFIRMED = True in design.py")

    notes.append("current capacity is checked by tools/check_board.py power_cut")

    #8
    #the ANT_IN feed rides the 1616-1626.5 MHz carrier
    rf = getattr(design, "RF_PARTS", None)
    if not rf:
        errs.append("design.RF_PARTS is missing: nothing states the ANT_IN ESD capacitance "
                    "or the bias choke's self-resonance, so neither limit is checked")
    else:
        e = rf["ant_esd"]
        if e["cj_pf"] > e["cj_max_pf"]:
            errs.append(f"ANT_IN ESD {e['part']} ({e['lcsc']}) has Cd = {e['cj_pf']} pF, "
                        f"over the {e['cj_max_pf']} pF limit - it shunts the 1.6 GHz feed. "
                        f"{e['src']}")
        else:
            notes.append(f"ANT_IN ESD {e['part']} ({e['lcsc']}): Cd {e['cj_pf']} pF <= "
                         f"{e['cj_max_pf']} pF, {e['standoff_v']:.0f} V standoff")
        c = rf["bias_choke"]
        x_ohm = 2.0 * math.pi * c["f_carrier_ghz"] * 1e9 * c["inductance_nh"] * 1e-9
        if c["srf_ghz"] < c["srf_min_ghz"]:
            errs.append(f"bias choke {c['part']} ({c['lcsc']}) self-resonates at "
                        f"{c['srf_ghz']} GHz, below the {c['srf_min_ghz']} GHz minimum - "
                        f"above resonance it is a capacitor, not the bias feed. {c['src']}")
        elif x_ohm < c["x_min_ohm"]:
            errs.append(f"bias choke {c['part']} ({c['lcsc']}) presents only {x_ohm:.0f} ohm "
                        f"at {c['f_carrier_ghz']} GHz (2*pi*f*L), under the "
                        f"{c['x_min_ohm']:.0f} ohm the front end needs - too little RF "
                        f"isolation from the bias-tee supply. {c['src']}")
        else:
            notes.append(f"bias choke {c['part']} ({c['lcsc']}): SRF {c['srf_ghz']} GHz "
                         f">= {c['srf_min_ghz']} GHz, X {x_ohm:.0f} ohm at "
                         f"{c['f_carrier_ghz']} GHz")
        for key in ("ant_esd", "bias_choke"):
            r = rf[key]
            if not any(v[3] == r["lcsc"] for v in design.COMPONENTS.values()):
                notes.append(f"{r['part']} ({r['lcsc']}) is not fitted in design.COMPONENTS "
                             f"yet - the limits above are checked against the sourcing "
                             f"record, not the layout, until Stage 2")

    #report
    print(f"ICs checked            : {len(ics)}")
    print(f"power pins examined    : {len(worst) + sum(1 for e in errs if 'no decoupling' in e)}")
    print(f"decoupled within {DECOUPLE_NEAR} mm : "
          f"{sum(1 for w in worst if w[0] <= DECOUPLE_NEAR)}/{len(worst)}")
    if verbose:
        print("\nfurthest decoupling:")
        for d, where, rail, cref, val in worst[:12]:
            print(f"   {where:10} {rail:6} -> {cref} {val:5} at {d:.2f} mm")
    for title, items in (("NOTES", notes), ("WARNINGS", warns), ("ERRORS", errs)):
        if items:
            print(f"\n{title} ({len(items)}):")
            for it in items:
                print(f"   {it}")
    if errs:
        return 1
    print("\nno electrical errors found.")
    return 0


#esd

"""Does every signal that leaves the board on a cable have a clamp at its connector?

Usage:  python3 tools/check_circuit.py esd [--self-test]

For each connector (J*) that is not exempt (design.ESD['exempt'] says why), each pin on a
signal net - not a supply or ground - must share its net with a pad of one of the clamps in
design.ESD['clamps'], and that clamp must sit within design.ESD['max_mm'] of the pin on the
board. Where the line has a series resistor (design.SERIES), the MCU's pin must not be on
the connector's net: the resistor has to be in the path, not beside it.

--self-test removes a clamp from a net, moves a clamp away and bridges a series resistor,
and exits 0 only if each is caught.
"""

SUPPLY = {"GND", "+5V", "+5V_PAYLOAD", "+3V3", "+3V3A", "VBAT", "VBAT_IN", "VBUS"}


def esd_positions():
    import pcbnew
    b = pcbnew.LoadBoard(BOARD)
    T = pcbnew.ToMM
    pads, parts = {}, {}
    for f in b.GetFootprints():
        p = f.GetPosition()
        parts[f.GetReference()] = (T(p.x), T(p.y))
        for q in f.Pads():
            c = q.GetPosition()
            pads[f"{f.GetReference()}.{q.GetNumber()}"] = (T(c.x), T(c.y))
    return pads, parts


def evaluate(nets, series, pads, parts):
    E = design.ESD
    fails, n = [], 0
    owner = {}
    for name, pins in nets.items():
        for p in pins:
            owner[p] = name
    for p, name in sorted(owner.items()):
        ref = p.split(".")[0]
        if not (ref.startswith("J") and ref[1:].isdigit()) or ref in E["exempt"]:
            continue
        if name in SUPPLY or name.startswith(("GND", "+")) or name in E.get("exempt_nets", {}):
            continue
        n += 1
        clamps = [q for q in nets[name] if q.split(".")[0] in E["clamps"]]
        if not clamps:
            fails.append(f"{p} ({name}) has no clamp on its net")
            continue
        if p in pads:
            #pin to the clamp's own pad on this net: the length the surge runs along
            d = min(math.dist(pads[p], pads.get(c, parts[c.split(".")[0]])) for c in clamps)
            lim = E.get("port_max_mm", {}).get(ref, (E["max_mm"],))[0]
            if d > lim:
                fails.append(f"{p} ({name}): nearest clamp {d:.1f} mm away (limit {lim:.0f})")
    for mcu_net, (part, jn) in series.items():
        if any(q.startswith("U1.") for q in nets.get(jn, [])):
            fails.append(f"{jn}: the MCU is on the connector's net - {part} is bypassed")
        if not any(q.startswith(part + ".") for q in nets.get(mcu_net, [])):
            fails.append(f"{mcu_net}: {part} does not reach the MCU's side")
    return fails, n


def self_test(pads, parts):
    import copy
    ok = not evaluate(design.NETS, design.SERIES, pads, parts)[0]
    print(f"  {'clean' if ok else 'NOT CLEAN'}  the board as designed")
    a = copy.deepcopy(design.NETS)
    a["M1_J"] = [q for q in a["M1_J"] if not q.startswith("U26.")]
    far = dict(pads)
    for k in [k for k in far if k.startswith("U28.")]:
        x, y = far[k]
        far[k] = (x + 25.0, y)
    c = copy.deepcopy(design.NETS)
    mcu = next(q for q in design.NETS["M2"] if q.startswith("U1."))
    c["M2_J"].append(mcu)
    for name, args in (("a clamp taken off M1", (a, design.SERIES, pads, parts)),
                       ("U28 moved 25 mm away", (design.NETS, design.SERIES, far, parts)),
                       ("RN1 bridged on M2", (c, design.SERIES, pads, parts))):
        caught = bool(evaluate(*args)[0])
        ok &= caught
        print(f"  {'caught' if caught else 'MISSED'}  {name}")
    print("self-test passed: every break is caught" if ok else "SELF-TEST FAILED")
    return 0 if ok else 1


def run_esd():
    pads, parts = esd_positions()
    if "--self-test" in sys.argv:
        return self_test(pads, parts)
    fails, n = evaluate(design.NETS, design.SERIES, pads, parts)
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} unprotected or bypassed line(s)")
        return 1
    print(f"{n} off-board signal pin(s), each clamped within its port's limit "
          f"({design.ESD['max_mm']:.0f} mm unless design.ESD says why); "
          f"{len(design.SERIES)} behind a series resistor")
    return 0


#ratings

"""Is every part actually rated for the net it is soldered to?

Usage: python3 tools/check_circuit.py ratings
"""

DERATE = 2.0          #warn below this multiple of the working voltage
#package power ratings, W
R_POWER = {"0402": 0.0625, "0603": 0.10, "0805": 0.125, "1206": 0.25}
#parts rated above their package's generic figure, by LCSC code
R_POWER_PART = {}
#capacitors that must not be a Class II dielectric, and why
CLASS1_REQUIRED = {
    "C15": "crystal load cap - a Class II part pulls the oscillator with temperature",
    "C16": "crystal load cap - a Class II part pulls the oscillator with temperature",
}

fails, warns, notes = [], [], []


def ohms_of(val):
    """Parse RKM notation: 5k1 is 5.1 kohm, not 5e31."""
    t = str(val).strip()
    m = re.fullmatch(r"(\d*)([RrKkMmGg])(\d*)", t)
    if m:
        whole, mult, frac = m.group(1) or "0", m.group(2).upper(), m.group(3)
        scale = {"R": 1.0, "K": 1e3, "M": 1e6, "G": 1e9}[mult]
        return float(f"{whole}.{frac}" if frac else whole) * scale
    try:
        return float(t)
    except ValueError:
        return None


def pkg_of(footprint):
    #the imperial code, not the metric one (C_0201_0603Metric is an 0201)
    m = re.search(r"(?<!\d)(0201|0402|0603|0805|1206|1210)(?!\d|Metric)", footprint)
    return m.group(1) if m else None


def _is_dnp(ref):
    """A part that is not fitted cannot be over-rated or the wrong size for its land."""
    c = design.COMPONENTS.get(ref)
    return bool(c and c[4])


def run_ratings():
    #net -> refs, and ref -> nets
    ref_nets = collections.defaultdict(set)
    for net, pins in design.NETS.items():
        for pin in pins:
            ref_nets[pin.split(".")[0]].add(net)

    BOOT_PAIRS = [("BUCK_BOOT", "BUCK_PH"), ("BUCK9_BOOT", "BUCK9_PH")]

    def working_voltage(nets):
        """Volts across the part, not volts at a node."""
        for a, b in BOOT_PAIRS:
            if {a, b} <= nets:
                return design.NET_VMAX[a], f"{a}-{b} bootstrap"
        known = {n: design.NET_VMAX[n] for n in nets if n in design.NET_VMAX}
        if len(known) < len(nets): return None, None
        if not known: return None, None
        hi = max(known.values()); lo = min(known.values())
        return hi - lo, "/".join(sorted(known, key=lambda n: -known[n]))

    caps = sorted(r for r in design.COMPONENTS if r.startswith("C"))
    res  = sorted(r for r in design.COMPONENTS if r.startswith("R"))
    unrated, unknown_net = [], []

    print("=== capacitors ===")
    for ref in caps:
        spec = design.COMPONENTS[ref]
        fp, val, lcsc = spec[1], spec[2], spec[3]
        if ref in design.NOT_A_PART or not lcsc: continue
        nets = ref_nets.get(ref, set())
        v, via = working_voltage(nets)
        if v is None:
            unknown_net.append((ref, sorted(nets))); continue
        rat = design.RATINGS.get(lcsc)
        if rat is None:
            unrated.append((ref, lcsc, val, round(v, 1))); continue
        _v, vr, diel, _tol, pk, _tmin, _tmax, _src = rat
        #package agreement between the footprint and the part
        fpk = pkg_of(fp)
        if fpk and pk and fpk != pk:
            fails.append(f"{ref}: footprint is {fpk} but {lcsc} is a {pk} part")
        if v > 0 and vr < v:
            fails.append(f"{ref} ({val}, {lcsc}): rated {vr} V, sits on {via} at "
                         f"{v:.1f} V - OVER ITS RATING")
        elif v > 0 and vr < v * DERATE:
            warns.append(f"{ref} ({val}, {lcsc}): rated {vr} V on {v:.1f} V "
                         f"= {vr/v:.1f}x. {diel} loses much of its value at rating")
        if ref in CLASS1_REQUIRED and diel not in ("NP0", "C0G"):
            fails.append(f"{ref}: dielectric is {diel} - {CLASS1_REQUIRED[ref]}")
    print(f"  {len(caps)} capacitors, {len(unrated)} with no recorded rating")

    print("\n=== resistors: worst-case dissipation ===")
    r_checked, r_worst = 0, None
    for ref in res:
        spec = design.COMPONENTS[ref]
        fp, val, lcsc = spec[1], spec[2], spec[3]
        if ref in design.NOT_A_PART or not lcsc: continue
        nets = ref_nets.get(ref, set())
        known = {n: design.NET_VMAX[n] for n in nets if n in design.NET_VMAX}
        if not known: continue
        v = max(known.values())
        via = max(known, key=lambda n: known[n]) + " (worst case, far end at 0 V)"
        if v <= 0: continue
        ohms = ohms_of(val)
        if ohms is None or ohms <= 0: continue
        p = v * v / ohms                      #conservative: full rail across the part
        pk = pkg_of(fp); lim = R_POWER_PART.get(lcsc, (R_POWER.get(pk),))[0]
        r_checked += 1
        if lim and (r_worst is None or p/lim > r_worst[1]):
            r_worst = (ref, p/lim, p, lim, val, v)
        if lim and p > lim:
            fails.append(f"{ref} ({val}): {p*1000:.0f} mW worst case across {via} "
                         f"at {v:.1f} V, {pk} rated {lim*1000:.0f} mW")
        elif lim and p > lim * 0.5:
            warns.append(f"{ref} ({val}): {p*1000:.0f} mW of a {lim*1000:.0f} mW {pk}")

    if r_worst:
        ref, frac, p, lim, val, v = r_worst
        print(f"  {r_checked} resistors checked against their package rating")
        print(f"  worst: {ref} ({val}) at {p*1000:.1f} mW = {frac*100:.0f}% of a "
              f"{lim*1000:.0f} mW part, with {v:.1f} V assumed across it")
    else:
        print("  none could be bounded - no resistor touches a declared rail")

    print("\n=== inductors ===")
    for ref in sorted(r for r in design.COMPONENTS if r.startswith("L")):
        spec = design.COMPONENTS[ref]
        fp, val, lcsc = spec[1], spec[2], spec[3]
        if ref in design.NOT_A_PART or not lcsc: continue
        ind = design.INDUCTORS.get(lcsc)
        if ind is None:
            notes.append(f"{ref} ({lcsc}) has no recorded inductor rating"); continue
        _v, isat, irms, dcr, body, _src = ind
        load = design.INDUCTOR_LOAD_A.get(ref)
        #the land pattern the board actually has
        land = pkg_of(fp)
        LAND_MM = {"1210": (3.2, 2.5), "0805": (2.0, 1.25), "1206": (3.2, 1.6)}
        lm = LAND_MM.get(land)
        #does the part actually fit?
        if lm and body:
            _bd = globals().get('_BOARD')
            if _bd is None:
                _bd = pcbnew.LoadBoard('NAVCORE-SoOP.kicad_pcb'); globals()['_BOARD'] = _bd
            _fp = _bd.FindFootprintByReference(ref)
            pads = list(_fp.Pads()) if _fp else []
            if len(pads) >= 2:
                xs = sorted(q.GetPosition().x/1e6 for q in pads)
                pitch = abs(xs[-1] - xs[0])
                pw = max(q.GetSizeX()/1e6 for q in pads)
                ph = max(q.GetSizeY()/1e6 for q in pads)
                #terminal footprint implied by the part's body
                term_w, term_h = body[0]*0.28, body[1]*0.75
                if term_w > pw + 0.35 or term_h > ph + 0.60:
                    fails.append(f"{ref}: {lcsc}'s terminals (~{term_w:.1f}x{term_h:.1f} mm) "
                                 f"do not register on the {pw:.2f}x{ph:.2f} mm pads")
                elif term_h > ph:
                    notes.append(f"{ref}: {lcsc}'s terminal overhangs the pad by "
                                 f"{(term_h-ph)/2:.2f} mm in Y - solderable, check the fillet")

        if load and irms and load > irms:
            msg = (f"{ref}: carries {load:.2f} A but {lcsc} is rated {irms:.1f} A RMS "
                   f"({load/irms*100:.0f}% of rating); I2R = {load*load*dcr:.2f} W")
            (notes if _is_dnp(ref) else fails).append(
                msg + (" (DNP on this build)" if _is_dnp(ref) else ""))
        elif load and irms and load > irms * 0.85:
            warns.append(f"{ref}: carries {load:.2f} A of a {irms:.1f} A RMS rating")
        if load and isat and load * 1.15 > isat:
            warns.append(f"{ref}: peak with ripple approaches Isat {isat:.1f} A")
        if load:
            print(f"  {ref}: {load:.2f} A through {lcsc} "
                  f"(Isat {isat}, Irms {irms}, {body[0]}x{body[1]}x{body[2]} mm)")

    if unrated:
        print("\n=== NO RECORDED RATING - read the datasheet, do not assume ===")
        seen = set()
        for ref, lcsc, val, v in unrated:
            if lcsc in seen: continue
            seen.add(lcsc)
            usedby = sorted({r for r, l, _v, _w in unrated if l == lcsc})
            mx = max(w for _r, l, _v, w in unrated if l == lcsc)
            print(f"  {lcsc:10s} {val:6s} up to {mx:5.1f} V   {', '.join(usedby[:8])}")
            notes.append(f"{lcsc} ({val}) has no recorded rating; highest net is {mx:.1f} V")
    if unknown_net:
        print("\n=== net voltage not declared in design.NET_VMAX ===")
        for ref, nets in unknown_net[:12]:
            print(f"  {ref:6s} {nets}")

    #parts explicitly marked unverified are reported whether or not the checker reached them
    still = sorted(design.RATINGS_UNVERIFIED - set(design.RATINGS))
    if still:
        print("\n=== ratings never read off a datasheet ===")
        for lcsc in still:
            used = sorted(r for r in design.COMPONENTS
                          if len(design.COMPONENTS[r]) > 3
                          and design.COMPONENTS[r][3] == lcsc)
            nets = sorted({n for r in used for n in ref_nets.get(r, ())})
            print(f"  {lcsc:10s} {', '.join(used):28s} nets: {', '.join(nets)}")
            notes.append(f"{lcsc} unverified, fitted at {', '.join(used)}")

    print()
    for w in warns: print(f"  warn  {w}")
    for n in notes: print(f"  note  {n}")
    for f in fails: print(f"  FAIL  {f}")
    print(f"\n{len(fails)} failure(s), {len(warns)} warning(s), "
          f"{len(notes)} unrated part type(s)")
    sys.exit(1 if fails else 0)


#symbol_pinout

"""Compare every active part's symbol pinout against an authority that is not this project.

Usage:  python3 tools/check_circuit.py symbol_pinout [-v]
"""

JLC_SYM = jlcpaths.SYMBOLS
KICAD_SYM_DIRS = ["/usr/share/kicad/symbols", "/usr/local/share/kicad/symbols"]

#our symbol name -> (kicad library file, kicad symbol name)
CROSS_CHECK = {
    "STM32H743VIT6_C114409": ("MCU_ST_STM32H7", "STM32H743VITx"),
    "SN65HVD230DR":          ("Interface_CAN_LIN", "SN65HVD230"),
    "USBLC6-2SC6_C2687116":  ("Power_Protection", "USBLC6-2SC6"),
    "W25Q128JVPIQTR":        ("Memory_Flash", "W25Q128JVP"),
    "TPS54202DDCR":          ("Regulator_Switching", "TPS54202DDC"),
    "SRV05-4-P-T7_C6454456": ("Power_Protection", "SRV05-4"),
    "MS561101BA03-50":       ("Sensor_Pressure", "MS5611-01BA"),
    "AO3400A":               ("Transistor_FET", "AO3400A"),
    "TMP119AIYBGR":          ("Sensor_Temperature", "TMP119AIYBGR"),
    #added after this part turned out to be wired backwards on the board
    "XC6206P332MR":          ("Regulator_Linear", "XC6206PxxxMR"),
    #diodes (added for the D/L pinout pass)
    "SMBJ22A_C113993":       ("Device", "D_Zener"),
    "1N4148W_C81598":        ("Device", "D"),
    "BZT52C15":              ("Device", "D_Zener"),
    "B5819W_C8598":          ("Device", "D_Schottky"),
}

#parts with no KiCad equivalent
DATASHEET_VERIFIED = {
    #KiCad's own symbol is the one placed
    "TPD4E05U06DQA": ("TI TPD4E05U06 datasheet (SLVSBN9, 2024) Table 4-2 Pin Functions and "
                      "Figure 4-3, DQA 10-pin USON top view",
                      "1 D1+, 2 D1-, 3 GND, 4 D2+, 5 D2-, 6/7/9/10 NC, 8 GND - four "
                      "independent clamps on 1, 2, 4, 5 (design.TVS4_IO)",
                      "2026-10-02"),
    #KiCad has the TLV757P only in DBV and DRV
    "TLV75733PDYDR": ("docs/datasheets/TLV757P-TI.pdf Table 4-1 Pin Functions, DYD column, "
                      "and Figure 4-2",
                      "all 6 pads: 1 IN, 2 GND, 3 EN, 4 NC, 5 OUT, 6 (thermal pad) GND",
                      "2026-09-29"),
    "TLV75533PDBVR": ("docs/datasheets/TLV755P-SBVS293.pdf Figure 4-2, DBV package",
                      "all 5 pins: IN GND EN NC OUT", "2026-09-17"),
    "MAX2112ETI+T": ("docs/datasheets/MAX2112.pdf pin description table",
                     "all 28 pins + EP, every one wired", "2026-09-17"),
    "OPA2374M{slash}TR": ("docs/datasheets/OPA2374-TI.pdf, D package, Pin Functions: OPA2374",
                          "all 8 pins", "2026-09-17"),
    "LMR33630ARNXR": ("docs/datasheets/LMR33630-SNVSAN3F.pdf Table 6-1 Pin Functions "
                      "(VQFN column) + Figure 6-2 RNX top view + 7.4/7.5",
                      "all 12 pins. Pin 3 is 'NC' in the table and is TIED TO SW on the "
                      "PCB per 10.1 guideline 3; pin 8 (PG) is left open, which the "
                      "pin-table note permits; pin 5 (VCC) carries the 1 uF bypass",
                      "2026-09-20"),
    "SN74LVC1G17DBVR": ("docs/datasheets/SN74LVC1G17-TI.pdf Pin Functions, DBV column",
                        "all 5 pins: NC A GND Y VCC", "2026-09-18"),
    "ICM-42688-P": ("docs/datasheets/ICM-42688-P-TDK.pdf DS-000347 pin table, and an "
                    "independent KiCad symbol (hub.allspice.io MUREX/electrical)",
                    "all 14 pins. FOUND pin 7 RESV 'Connect to GND' floating - fixed",
                    "2026-09-18"),
    "ICM-42605": ("docs/datasheets/ICM-42605-TDK.pdf DS-000292 pin table",
                  "all 14 pins. Same pin 7 finding as the ICM-42688-P - fixed",
                  "2026-09-18"),
    "WST4041": ("docs/datasheets/WST4041_WINSOK.pdf SOT-23-3L Pin Configuration figure",
                "G S D on 1 2 3, and P-channel as the topology needs", "2026-09-18"),
    "X32258MSB4SI": ("docs/datasheets/YSX321SL-YXC.pdf 'Top View Crystal Connection'",
                     "#1/#3 crystal, #2/#4 GND; the SMD3225 series this part belongs to",
                     "2026-09-18"),
    "T132S4-25000ML33DTL": (
        "JLCPCB part record for C5563878 (MPN, spec, 'Clipped sine wave', +/-2ppm, "
        "3.3V, -40..+85C) + the JLCPCB/EasyEDA symbol's pin names; HCI's own sheet NOT "
        "obtained",
        "all 4 pins used. pin 1 'GND or N.C.' grounded on purpose - safe by class "
        "(neither Disable nor Vcon; Epson TG2016SMN permits N.C. to GND)",
        "2026-09-18"),
    #fetched for the Rev C connector/protection pass (Stage 1) and verified before the parts
    "INA180A2IDBVR": (
        "TI INAx180 datasheet, 'Pin Configuration and Functions', DBV (SOT-23-5) "
        "pinout A; the datasheet's note (1): 'INA180A devices use pinout A. INA180B "
        "devices use pinout B' - this is an A2, so pinout A",
        "all 5 pins: 1 OUT, 2 GND, 3 IN+, 4 IN-, 5 VS. The fetched EasyEDA symbol "
        "matches pinout A, not the B ordering (which puts OUT on pin 4)",
        "2026-09-30"),
    "AP22653W6-7": (
        "Diodes AP22652/AP22653/AP22652A/AP22653A datasheet DS41186 Rev 2-2, "
        "'Pin Assignments', SOT26 (Type A1)",
        "all 6 pins: 1 IN, 2 GND, 3 EN/EN, 4 FAULT, 5 ILIM, 6 OUT. AP22653 = active-high "
        "enable, which the plan's default-on pull-up needs. NOTE the current limit is set "
        "by an external resistor and is 125 mA to 2665 mA - it cannot be programmed to the "
        "plan's 50-100 mA, so the real choice is 125 mA or another part",
        "2026-09-30"),
    #d/L parts KiCad's Device library cannot corroborate
    "LED": (
        "0603 LED: pin 1 is the cathode and pin 2 the anode, the same polarity the "
        "vendored 0603 LED footprint marks; the board sinks pin 1 (LED0_K/LED1_K) "
        "with pin 2 on +3V3, so the LED lights when the MCU pulls low",
        "2 used pins: 1 = K, 2 = A", "2026-10-01"),
    "L": (
        "two-terminal inductor/ferrite: not polarised, so pin 1 and pin 2 are "
        "interchangeable; KiCad's Device:L names them 1 and 2, which is all that "
        "matters here (L1 ferrite +3V3->VDDA, L2/L5 buck phase->rail)",
        "2 used pins: 1, 2", "2026-10-01"),
    "PESD2CANFD24LT-QR": (
        "Nexperia PESD2CANFD24LT-Q datasheet, SOT-23 pinout: pins 1 and 2 are the two "
        "protected lines and pin 3 is the common/GND (the sheet measures capacitance "
        "'from pin 1 or 2 to pin 3')",
        "all 3 pins: 1 = I/O1 (CANH), 2 = I/O2 (CANL), 3 = common (GND). The vendored "
        "symbol's combined 1=C/2=C/3=A common-node topology matches a device that "
        "clamps each line to the shared pin 3",
        "2026-10-01"),
    "LQW15AN27NH00D": (
        "Murata LQW15AN27N datasheet, 0402 wirewound RF inductor, 2 terminals, non-polarised",
        "2 used pins: 1, 2",
        "2026-10-01"),
    "PTVS5V0S1UR": (
        "Nexperia PTVS5V0S1UR datasheet, SOD-123FL unidirectional TVS clamp: "
        "pin 1 is the cathode (banded, +5V_PAYLOAD) and pin 2 is the anode (GND)",
        "2 used pins: 1 = K, 2 = A",
        "2026-10-01"),
    "D_TVS": (
        "KiCad Device:D_TVS bidirectional TVS diode symbol, 2 passive terminals",
        "2 used pins: 1 = A1, 2 = A2",
        "2026-10-01"),
}


def pinmap(path, name):
    """{pin number: pin name} for a symbol, following extends and unit children."""
    if not os.path.exists(path):
        return None, f"library missing: {path}"
    text = open(path).read()
    m = re.search(r'\(symbol\s+"%s"' % re.escape(name), text)
    if not m:
        return None, f"symbol {name!r} not in {os.path.basename(path)}"
    i = m.start(); d = 0; j = i
    while j < len(text):
        if text[j] == '(':
            d += 1
        elif text[j] == ')':
            d -= 1
            if d == 0:
                break
        j += 1
    sym_body = text[i:j + 1]
    ext = re.search(r'\(extends\s+"([^"]+)"', sym_body)
    if ext:
        base = ext.group(1)
        if base != name:
            return pinmap(path, base)
    out = {}
    for pm in re.finditer(
            r'\(pin\s+\S+\s+\S+.*?\(name\s+"([^"]*)".*?\(number\s+"([^"]*)"',
            sym_body, re.S):
        out[pm.group(2)] = pm.group(1)
    return out, None


def our_symbol_path(spec):
    """Resolve a design symbol spec ('lib:name') to its symbol-library file."""
    lib, _, name = spec.partition(":")
    if lib == "jlc_parts":
        return jlcpaths.SYMBOLS, name
    for d in KICAD_SYM_DIRS:
        p = os.path.join(d, lib + ".kicad_sym")
        if os.path.exists(p):
            return p, name
    return None, name


def variants(name):
    """Every spelling of a pin name that should count as the same pin."""
    n = name.upper().strip()
    n = re.sub(r'~\{([^}]*)\}', r'\1', n)        #KiCad inversion -> bare name
    n = re.sub(r'_\{([^}]*)\}', r'\1', n)        #subscript IO_{1} -> IO1
    n = n.replace("{", "").replace("}", "")
    n = re.sub(r'\s', '', n)

    out = set()
    for alt in n.split("/"):                      #alternate function names
        if not alt:
            continue
        if alt in ("-", "\u2212"):                  #bare polarity mark = cathode (K)
            out.add("K")
            continue
        if alt == "+":                             #bare polarity mark = anode (A)
            out.add("A")
            continue
        #active-low marks: CS#, #CS (EasyEDA), CSN
        for form in (alt, alt.strip("#"), alt.rstrip("N") if alt.endswith("N") else alt):
            f = form.replace("_", "").replace("-", "")
            if f:
                out.add(f)
        if "-" in alt:                            #PC14-OSC32_IN -> PC14
            head = alt.split("-", 1)[0]
            if head:
                out.add(head.replace("_", ""))
    syn = {"VSS": "GND", "GND": "VSS", "VDD": "VCC", "VCC": "VDD",
           "VI": "VIN", "VIN": "VI", "VO": "VOUT", "VOUT": "VO",
           "IN": "VIN", "OUT": "VOUT",
           #diode terminals: EasyEDA/JLC write C/A, KiCad writes K/A
           "C": "K", "K": "C",
           #protection arrays name their rails by polarity
           "VN": "GND", "VP": "VCC"}
    for v in list(out):
        if v in syn:
            out.add(syn[v])
    return {x for x in out if x and x not in ("NC", "DNC")}


def run_symbol_pinout():
    verbose = "-v" in sys.argv
    actives = {r: v for r, v in design.COMPONENTS.items()
               if r.startswith(("U", "Q", "Y", "D", "L"))}
    used = {}
    for net, specs in design.NETS.items():
        for sp in specs:
            if "." not in sp:
                continue
            ref, pin = sp.split(".", 1)
            if ref in actives:
                used.setdefault(ref, {})[pin] = net

    by_symbol = {}
    for ref, v in actives.items():
        by_symbol.setdefault(v[0], []).append(ref)

    fails, unverified = [], []
    print(f"jlc symbols : {JLC_SYM}")
    print(f"{'symbol':34} {'refs':14} {'pins':>5}  verdict")
    print("-" * 78)

    for spec in sorted(by_symbol):
        members = by_symbol[spec]
        sym = spec.split(":", 1)[1]
        refs = ",".join(sorted(members))
        ourpath, symname = our_symbol_path(spec)
        ours, err = (pinmap(ourpath, symname) if ourpath
                     else (None, f"library for {spec} not installed"))
        if ours is None:
            print(f"{sym[:34]:34} {refs[:14]:14} {'?':>5}  FAIL {err}")
            fails.append(f"{sym}: {err}")
            continue
        if sym not in CROSS_CHECK:
            tag = "datasheet-verified" if sym in DATASHEET_VERIFIED else "NO AUTHORITY"
            print(f"{sym[:34]:34} {refs[:14]:14} {len(ours):5}  {tag}")
            if sym not in DATASHEET_VERIFIED:
                unverified.append((sym, refs, len(ours)))
            continue
        libname, kname = CROSS_CHECK[sym]
        path = next((os.path.join(d, libname + ".kicad_sym")
                     for d in KICAD_SYM_DIRS
                     if os.path.exists(os.path.join(d, libname + ".kicad_sym"))), None)
        if path is None:
            print(f"{sym[:34]:34} {refs[:14]:14} {len(ours):5}  FAIL KiCad lib "
                  f"{libname} not installed - cannot verify, and 'cannot verify' "
                  f"is not 'verified'")
            fails.append(f"{sym}: KiCad library {libname} unavailable")
            continue
        theirs, err = pinmap(path, kname)
        if theirs is None:
            print(f"{sym[:34]:34} {refs[:14]:14} {len(ours):5}  FAIL {err}")
            fails.append(f"{sym}: {err}")
            continue
        #only pins the netlist actually uses can scrap a board; report all
        relied = set()
        for r in members:
            relied |= set(used.get(r, {}))
        bad_used, bad_other = [], []
        for num in sorted(set(ours) | set(theirs)):
            a, b = ours.get(num), theirs.get(num)
            if a is None or b is None:
                (bad_used if num in relied else bad_other).append((num, a, b))
            elif not (variants(a) & variants(b)):
                (bad_used if num in relied else bad_other).append((num, a, b))
        if bad_used:
            print(f"{sym[:34]:34} {refs[:14]:14} {len(ours):5}  FAIL "
                  f"{len(bad_used)} WIRED pin(s) disagree with {libname}:{kname}")
            for num, a, b in bad_used[:12]:
                net = next((used[r][num] for r in members
                            if num in used.get(r, {})), "?")
                print(f"{'':34} {'':14} {'':5}    pin {num:>4} carries {net:12} "
                      f"ours={a} kicad={b}")
            fails.append(f"{sym}: {len(bad_used)} wired pin(s) disagree")
        else:
            note = f", {len(bad_other)} unused pin name(s) differ" if bad_other else ""
            print(f"{sym[:34]:34} {refs[:14]:14} {len(ours):5}  ok  matches "
                  f"{libname}:{kname}{note}")
            if verbose and bad_other:
                for num, a, b in bad_other:
                    print(f"{'':34} {'':14} {'':5}    pin {num:>4} "
                          f"ours={a} kicad={b}")

    print()
    if unverified:
        print(f"{len(unverified)} symbol(s) have NO outside authority and no recorded "
              f"datasheet check:")
        for sym, refs, n in unverified:
            print(f"   {sym:34} {refs:14} {n} pins")
        print("   Each needs its pinout compared against the manufacturer document,")
        print("   then recorded in DATASHEET_VERIFIED. Until then this is an OPEN RISK:")
        print("   a wrong pin number here is invisible to every other check and is")
        print("   only discovered on an assembled board.")
        print()
    if fails:
        print(f"FAIL - {len(fails)} symbol(s) disagree with their authority:")
        for f in fails:
            print(f"   - {f}")
        return 1
    if unverified:
        return 2
    print("every active part's pinout agrees with an outside authority")
    return 0


#pin_semantics

"""Check that every MCU pin is wired to the right end of the thing it talks to.

Usage:  python3 tools/check_circuit.py pin_semantics [-v]
"""

HW = "firmware/NAVCORE_SoOP/hwdef.dat"
pin_semantics_RAILS = {"+3V3", "+3V3A", "+5V", "+9V", "VBAT", "VDDA", "VBUS"}
#peripheral labels that are inherently one-way, and which way
ROLE_DIR = [
    (re.compile(r'^(U(S)?ART\d+)_TX$'), "out"), (re.compile(r'^(U(S)?ART\d+)_RX$'), "in"),
    (re.compile(r'^(U(S)?ART\d+)_RTS$'), "out"), (re.compile(r'^(U(S)?ART\d+)_CTS$'), "in"),
    (re.compile(r'^SPI\d+_MOSI$'), "out"), (re.compile(r'^SPI\d+_MISO$'), "in"),
    (re.compile(r'^SPI\d+_SCK$'),  "out"),
    (re.compile(r'^CAN\d+_TX$'), "out"),  (re.compile(r'^CAN\d+_RX$'), "in"),
]


def mcu_pin_nets():
    """{MCU pin name: [net, ...]} using the same symbol table as check_circuit.py design."""
    h7 = {p['num']: p['name'] for p in symlib.load()["STM32H743VIT6_C114409"]}
    out = {}
    for net, specs in design.NETS.items():
        for sp in specs:
            ref, pin = sp.split(".", 1)
            if ref != "U1":
                continue
            out.setdefault(h7.get(pin, pin).split("-")[0], []).append(net)
    return out


def pulls():
    """{net: [(ref, 'up'/'down', value), ...]} for resistors tying a net to a rail."""
    where = {}
    for net, specs in design.NETS.items():
        for sp in specs:
            ref, pad = sp.split(".", 1)
            where.setdefault(ref, []).append((net, pad))
    out = {}
    for ref, legs in where.items():
        if not ref.startswith("R") or len(legs) != 2:
            continue
        (na, _), (nb, _) = legs
        val = design.COMPONENTS.get(ref, ("", "", "?"))[2]
        for sig, rail in ((na, nb), (nb, na)):
            if rail in pin_semantics_RAILS and sig not in pin_semantics_RAILS:
                out.setdefault(sig, []).append(
                    (ref, "down" if rail == "GND" else "up", val))
            elif rail == "GND" and sig not in pin_semantics_RAILS:
                out.setdefault(sig, []).append((ref, "down", val))
    return out


def devices_on(net):
    """Non-MCU, non-passive endpoints of a net - the things that might drive it."""
    out = []
    for sp in design.NETS.get(net, []):
        ref = sp.split(".", 1)[0]
        if ref == "U1" or ref[0] in "RCL" and ref[1:].isdigit():
            continue
        out.append(sp)
    return out


def run_pin_semantics():
    verbose = "-v" in sys.argv
    pins, alts = parse(HW)
    nets_of = mcu_pin_nets()
    pl = pulls()
    intent = design.PIN_INTENT

    errs, warns, notes = [], [], []
    checked = 0

    for pin in sorted(pins):
        e = pins[pin]
        opts = " ".join(e["opts"])
        label, periph = e["label"], e["periph"]
        nets = [n for n in nets_of.get(pin, []) if n not in pin_semantics_RAILS]
        if not nets:
            continue
        net = nets[0]
        want = intent.get(net)
        if want is None:
            if devices_on(net):
                notes.append(f"{pin} ({net}) has a device on it but no PIN_INTENT entry")
            continue
        checked += 1
        mcu = want["mcu"]
        is_out = "OUTPUT" in opts or "OUTPUT" in periph
        od = "OPENDRAIN" in opts

        #1. contention - the firmware drives a pin the board expects to be driven
        if is_out and not od and mcu == "in":
            errs.append(f"{pin} ({net}): hwdef makes it a push-pull OUTPUT but "
                        f"{want['why']} - two drivers on one node")

        #2. boot level - the reset state is not the state the device needs
        if is_out and want.get("boot"):
            lvl = "high" if re.search(r'\bHIGH\b', opts) else \
                  "low" if re.search(r'\bLOW\b', opts) else None
            if lvl and lvl != want["boot"]:
                errs.append(f"{pin} ({net}): hwdef resets it {lvl.upper()} but it must "
                            f"be {want['boot'].upper()} - {want['why']}")

        for rx, direction in ROLE_DIR:
            if rx.match(label) and mcu in ("in", "out") and direction != mcu:
                errs.append(f"{pin} ({net}): hwdef uses it as {label} ({direction}) but "
                            f"the signal goes {mcu} - {want['why']}")
                break

        #4. pull fight - driving against a fitted resistor
        for ref, updown, val in pl.get(net, []):
            if not is_out:
                continue
            lvl = "high" if re.search(r'\bHIGH\b', opts) else \
                  "low" if re.search(r'\bLOW\b', opts) else None
            if lvl and ((lvl == "low" and updown == "up") or
                        (lvl == "high" and updown == "down")):
                warns.append(f"{pin} ({net}): driven {lvl.upper()} against {ref} "
                             f"({val} pull-{updown})")
        if verbose:
            print(f"  {pin:5} {net:12} {mcu:6} {label}")

    #5. intent declared for something that is not wired
    for net in intent:
        if net not in design.NETS:
            notes.append(f"PIN_INTENT names '{net}', which is not a net")

    print(f"pins with declared intent : {checked}")
    print(f"PIN_INTENT entries        : {len(intent)}")
    print(f"nets with a fitted pull   : {len(pl)}")
    for title, items, mark in (("NOTES", notes, "  "), ("WARNINGS", warns, "  "),
                               ("ERRORS", errs, "  ")):
        if items:
            print(f"\n{title} ({len(items)}):")
            for it in items:
                print(f"{mark} {it}")
    if errs:
        print(f"\n{len(errs)} pin(s) are wired or configured the wrong way round.")
        return 1
    print("\nevery declared pin runs the right way.")
    return 0


#thermal

"""Thermal check for the switching regulators and the 3V3 rail.

Run: python3 tools/check_circuit.py thermal
"""

VIN_4S = 16.8               #[M] 4S fully charged, design.BATT

T_EDGE = 10e-9
#[L] efficiency band for a 2-3 A synchronous buck at this step-down ratio
EFF_LO, EFF_HI = 0.85, 0.90
T_AMBIENT_STACK = 40.0      #[A] inside a stack between an ESC and a battery, no airflow

fails, notes = [], []


def line(status, name, detail, src=""):
    print(f"  {status:5s} {name:38s} {detail}")
    if src:
        print(f"        {src}")


def run_thermal():
    print("=== switching regulator dissipation ===")
    print(f"      Vin {VIN_4S} V (4S), ambient {T_AMBIENT_STACK:.0f} C [A]")
    print(f"      every part-specific number comes from design.BUCK_THERMAL, keyed on the "
          f"fitted part,")
    print(f"      and every rail voltage from design.BUCK_RAILS (asserted against the "
          f"fitted divider by\n      check_circuit.py electrical section 2) - this file no longer "
          f"carries a copy of either\n")

    for ref, rail, vout, _rt, _rb, ind in design.BUCK_RAILS:
        part = design.COMPONENTS[ref][2]
        spec = design.BUCK_THERMAL.get(part)
        if not spec:
            fails.append(f"{ref}: {part} has no entry in design.BUCK_THERMAL - an "
                         f"unclassified regulator is not a checked one")
            line("FAIL", f"{ref} unclassified", f"{part} is not in design.BUCK_THERMAL")
            continue
        iout, dnp = design.INDUCTOR_LOAD_A[ind], design.buck_dnp(ref)
        fsw = spec["fsw"]
        rds_hs, rds_ls = spec["rds_hs"], spec["rds_ls"]
        theta_jedec = spec["theta_jedec"]
        theta_evm = spec["theta_evm"] or theta_jedec
        tj_max = spec["tj_max"]

        pout = vout * iout
        D = vout / VIN_4S
        p_comp = iout**2 * rds_hs * D + iout**2 * rds_ls * (1 - D) \
            + 0.5 * VIN_4S * iout * T_EDGE * fsw * 2
        p_lo = pout * (1 / EFF_HI - 1)      #90 % efficiency
        p_hi = pout * (1 / EFF_LO - 1)      #85 % efficiency
        #corners: best = most efficient on the best-copper board
        tj_lo = T_AMBIENT_STACK + p_lo * theta_evm       #best case
        tj_hi = T_AMBIENT_STACK + p_hi * theta_jedec     #worst case
        tj_mid_hi = T_AMBIENT_STACK + p_hi * theta_evm   #good copper, poor efficiency

        tag = " (DNP on this build)" if dnp else ""
        print(f"  {ref} {rail} {part}{tag}")
        print(f"      Pout {pout:.2f} W at {vout:.3f} V x {iout:.2f} A, D={D:.3f}, "
              f"fsw {fsw/1e3:.0f} kHz")
        print(f"      theta_JA {theta_evm:.1f}-{theta_jedec:.1f} C/W (good copper to JEDEC "
              f"board), limits {tj_max:.0f} C recommended / {spec['tj_absmax']:.0f} C "
              f"absolute / {spec['t_shutdown']:.0f} C shutdown")
        print(f"      Pd: {p_comp*1e3:.0f} mW component-level [D RDS(on), A edges]  vs  "
              f"{p_lo*1e3:.0f}-{p_hi*1e3:.0f} mW at {EFF_HI*100:.0f}-{EFF_LO*100:.0f}% "
              f"efficiency [L]")
        if theta_evm == theta_jedec:
            print(f"      junction {tj_lo:.0f} C best ({EFF_HI*100:.0f}%) .. {tj_hi:.0f} C "
                  f"worst ({EFF_LO*100:.0f}%) against {tj_max:.0f} C - the datasheet "
                  f"gives ONE theta_JA, so the spread here is the efficiency band alone")
        else:
            print(f"      junction {tj_lo:.0f} C best (EVM copper, {EFF_HI*100:.0f}%) .. "
                  f"{tj_mid_hi:.0f} C (EVM copper, {EFF_LO*100:.0f}%) .. "
                  f"{tj_hi:.0f} C worst (JEDEC copper, {EFF_LO*100:.0f}%), against "
                  f"{tj_max:.0f} C")
            print(f"      the spread IS the finding - it needs measuring, not more "
                  f"arithmetic")

        if dnp:
            line("note", f"{ref} not fitted",
                 f"DNP - no dissipation on this build, but if the VTX rail is ever "
                 f"populated this part reaches {tj_hi:.0f} C worst case "
                 + ("(over the "
                    f"{spec['t_shutdown']:.0f} C thermal shutdown - it would hiccup)"
                    if tj_hi >= spec['t_shutdown'] else
                    f"({'over' if tj_hi >= tj_max else 'under'} the "
                    f"{tj_max:.0f} C limit)"))
        elif tj_lo >= tj_max:
            fails.append(f"{ref}: even the best-case junction {tj_lo:.0f} C exceeds "
                         f"{tj_max:.0f} C")
            line("FAIL", f"{ref} junction temperature",
                 f"{tj_lo:.0f} C BEST case exceeds the {tj_max:.0f} C limit - "
                 f"no layout fixes this")
        elif tj_hi >= tj_max:
            notes.append(f"{ref}: worst-case junction {tj_hi:.0f} C exceeds "
                         f"{tj_max:.0f} C on JEDEC copper - MEASURE IT at T3")
            line("warn", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case EXCEEDS the {tj_max:.0f} C limit on "
                 f"JEDEC copper; {tj_mid_hi:.0f} C on EVM-class copper. This board is "
                 f"6-layer with planes, so the truth is nearer the low end - but that is "
                 f"an opinion until T3 measures it", spec["src"])
        elif tj_hi >= tj_max - 30:
            notes.append(f"{ref}: {tj_hi:.0f} C leaves under 30 C of margin")
            line("warn", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case - under 30 C of margin. MEASURE IT at T3",
                 spec["src"])
        else:
            line("ok", f"{ref} junction temperature",
                 f"{tj_hi:.0f} C worst case, {tj_max-tj_hi:.0f} C of margin", spec["src"])
        print()

    #the LDOs
    print("=== linear regulator dissipation ===")
    print(f"      both LDOs drop {design.LDO_DROP_V:.1f} V from +5V, ambient "
          f"{T_AMBIENT_STACK:.0f} C [A]\n")

    for ref, rail, loads in (("U9", "+3V3", design.LOADS_3V3),
                             ("U10", "+3V3A", design.LOADS_3V3A)):
        part = design.COMPONENTS[ref][2]
        spec = design.LDO_SPEC.get(part)
        if not spec:
            fails.append(f"{ref}: {part} has no entry in design.LDO_SPEC - an "
                         f"unclassified regulator is not a checked one")
            line("FAIL", f"{ref} unclassified", f"{part} is not in design.LDO_SPEC")
            continue
        pkg, theta_min, theta_good, theta_src, tj_max, i_max, spec_src = spec
        i_cont = sum(x[1] for x in loads)
        i_peak = sum(x[2] for x in loads)
        p_cont, p_peak = i_cont * design.LDO_DROP_V, i_peak * design.LDO_DROP_V
        #four corners, exactly as for the bucks
        tj_cont = T_AMBIENT_STACK + p_cont * theta_good     #best case
        tj_peak = T_AMBIENT_STACK + p_peak * theta_good     #good copper, peak load
        tj_cont_bad = T_AMBIENT_STACK + p_cont * theta_min
        tj_peak_bad = T_AMBIENT_STACK + p_peak * theta_min  #worst case

        print(f"  {ref} {rail}  {part} in {pkg}")
        for name, ic, ip, src in loads:
            print(f"      {name:34} {ic*1e3:6.0f} mA cont {ip*1e3:6.0f} mA peak  {src}")
        print(f"      {'TOTAL':34} {i_cont*1e3:6.0f} mA cont {i_peak*1e3:6.0f} mA peak")
        print(f"      Pd {p_cont*1e3:.0f} mW cont / {p_peak*1e3:.0f} mW peak at "
              f"{design.LDO_DROP_V:.1f} V drop")
        print(f"      theta_JA {theta_good} C/W (good copper) to {theta_min} C/W "
              f"(minimal copper)")
        print(f"      junction, good copper : {tj_cont:.0f} C cont / {tj_peak:.0f} C peak")
        print(f"      junction, min  copper : {tj_cont_bad:.0f} C cont / "
              f"{tj_peak_bad:.0f} C peak      against {tj_max:.0f} C")

        if i_peak > i_max:
            fails.append(f"{ref}: peak {i_peak*1e3:.0f} mA exceeds the part's "
                         f"{i_max*1e3:.0f} mA rating")
            line("FAIL", f"{ref} output current",
                 f"{i_peak*1e3:.0f} mA peak against a {i_max*1e3:.0f} mA part")
        else:
            line("ok", f"{ref} output current",
                 f"{i_peak*1e3:.0f} mA peak of {i_max*1e3:.0f} mA "
                 f"({i_peak/i_max*100:.0f}%)", spec_src)

        #fail only when no plausible copper saves it
        if tj_cont >= tj_max:
            fails.append(f"{ref}: CONTINUOUS junction {tj_cont:.0f} C exceeds "
                         f"{tj_max:.0f} C even on good copper")
            line("FAIL", f"{ref} junction temperature",
                 f"{tj_cont:.0f} C at the CONTINUOUS load on GOOD copper exceeds "
                 f"{tj_max:.0f} C - that is the steady state, not a transient, and no "
                 f"pour fixes it", theta_src)
        elif tj_peak >= tj_max:
            fails.append(f"{ref}: peak junction {tj_peak:.0f} C exceeds {tj_max:.0f} C "
                         f"on good copper")
            line("FAIL", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C at PEAK load on GOOD copper exceeds {tj_max:.0f} C",
                 theta_src)
        elif tj_peak_bad >= tj_max:
            notes.append(f"{ref}: peak junction reaches {tj_peak_bad:.0f} C on MINIMAL "
                         f"copper against {tj_max:.0f} C, {tj_peak:.0f} C on good copper "
                         f"- measure at T3a")
            line("warn", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C peak on good copper ({tj_max-tj_peak:.0f} C margin) "
                 f"but {tj_peak_bad:.0f} C on the datasheet's minimal-copper figure. On "
                 f"this board of solid planes the good end is the expected one - but "
                 f"{part} has thermal shutdown, so being wrong means a mid-flight "
                 f"BROWNOUT, not smoke. U19 (TMP119) sits beside it and logs this "
                 f"neighbourhood every flight - see TEMP_LOG in defaults.parm",
                 theta_src)
        elif tj_peak >= tj_max - 25:
            notes.append(f"{ref}: {tj_peak:.0f} C peak leaves under 25 C of margin")
            line("warn", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C peak - under 25 C of margin. MEASURE IT at T3",
                 theta_src)
        else:
            line("ok", f"{ref} junction temperature",
                 f"{tj_peak:.0f} C peak, {tj_max-tj_peak:.0f} C of margin", theta_src)
        print()

    print("=== active antenna bias feed dissipation ===")
    print(f"      U24 (AP22653W6-7) load switch and U25 (INA180A2) current sense amp,")
    print(f"      ambient {T_AMBIENT_STACK:.0f} C [A]\n")

    #U24: AP22653W6-7 in SOT-26
    u24_part = design.COMPONENTS["U24"][2]
    u24_theta = 120.0  #[D] Diodes DS41186 Dissipation Rating Table
    u24_tj_max = 125.0
    u24_p_rated_70c = 0.450
    u24_i_norm = 0.015
    u24_pd_norm = u24_i_norm**2 * 0.135
    u24_tj_norm = T_AMBIENT_STACK + u24_pd_norm * u24_theta
    u24_i_fold = 0.035
    u24_pd_fold = 5.0 * u24_i_fold
    u24_tj_fold = T_AMBIENT_STACK + u24_pd_fold * u24_theta

    print(f"  U24 +5V_BIAS_SW  {u24_part} in SOT-26")
    print(f"      normal LNA load    : {u24_i_norm*1e3:.0f} mA, Pd {u24_pd_norm*1e3:.2f} mW, Tj {u24_tj_norm:.0f} C")
    print(f"      dead short foldback: {u24_i_fold*1e3:.0f} mA at 5.0 V drop -> Pd {u24_pd_fold*1e3:.0f} mW")
    print(f"      theta_JA {u24_theta:.0f} C/W, limits {u24_tj_max:.0f} C recommended / 145 C shutdown / {u24_p_rated_70c*1e3:.0f} mW at 70 C")
    print(f"      junction, foldback : {u24_tj_fold:.0f} C against {u24_tj_max:.0f} C limit")

    if u24_tj_fold >= u24_tj_max:
        fails.append(f"U24: foldback junction {u24_tj_fold:.0f} C exceeds {u24_tj_max:.0f} C limit")
        line("FAIL", "U24 junction temperature", f"{u24_tj_fold:.0f} C in foldback exceeds {u24_tj_max:.0f} C")
    elif u24_tj_fold >= u24_tj_max - 30:
        notes.append(f"U24: foldback junction {u24_tj_fold:.0f} C leaves under 30 C of margin")
        line("warn", "U24 junction temperature", f"{u24_tj_fold:.0f} C in foldback - under 30 C of margin",
             "[D] Diodes DS41186 Dissipation Rating Table: SOT26 theta_JA 120 C/W")
    else:
        line("ok", "U24 junction temperature",
             f"{u24_tj_fold:.0f} C in foldback, {u24_tj_max-u24_tj_fold:.0f} C of margin ({u24_pd_fold*1e3:.0f} mW Pd)",
             "[D] Diodes DS41186 Dissipation Rating Table: SOT26 theta_JA 120 C/W")
    print()

    #U25: INA180A2IDBVR in SOT-23-5 (theta_JA 233.7 C/W, Iq 0.37 mA max, tj_max 125 C)
    u25_part = design.COMPONENTS["U25"][2]
    u25_theta = 233.7  #[D] TI SBOS853 Thermal Information
    u25_tj_max = 125.0
    u25_iq_max = 0.37e-3
    u25_pd = 3.3 * u25_iq_max
    u25_tj = T_AMBIENT_STACK + u25_pd * u25_theta

    print(f"  U25 ANT_CURRENT  {u25_part} in SOT-23-5")
    print(f"      quiescent draw     : {u25_iq_max*1e3:.2f} mA max from +3V3 -> Pd {u25_pd*1e3:.2f} mW")
    print(f"      theta_JA {u25_theta:.1f} C/W, limit {u25_tj_max:.0f} C recommended")
    print(f"      junction           : {u25_tj:.0f} C against {u25_tj_max:.0f} C limit")

    if u25_tj >= u25_tj_max:
        fails.append(f"U25: junction {u25_tj:.0f} C exceeds {u25_tj_max:.0f} C limit")
        line("FAIL", "U25 junction temperature", f"{u25_tj:.0f} C exceeds {u25_tj_max:.0f} C")
    else:
        line("ok", "U25 junction temperature",
             f"{u25_tj:.0f} C, {u25_tj_max-u25_tj:.0f} C of margin",
             "[D] TI INAx180 SBOS853 Thermal Information: DBV theta_JA 233.7 C/W")
    print()

    print("=== what this check cannot do ===")
    line("note", "RDS(on) and edge rate are [A]",
         "the component figure implies ~97% efficiency, optimistic for this part. "
         "RDS(on) is CONFIRMED [D] per part in design.BUCK_THERMAL (the fitted "
         "LMR33630A: SLVSD26 5.5 gives 148/78 mOhm, SNVSAN3F 7.5 gives 75/50 typ); "
         "T_EDGE is still [A] and "
         "gate-charge, dead-time and Coss losses are not modelled at all - which is why "
         "the efficiency-band figure, not this one, drives the verdict")
    line("note", "theta_JA is JEDEC-board, not THIS board",
         "the fitted LMR33630A carries ONE theta_JA from its own datasheet (72.5 C/W, "
         "RNX on a 4-layer JEDEC board - no EVM figure, so one honest number rather "
         "than a bracket invented from two). The copper under U8 and U20 here differs "
         "from that JEDEC board, so treat the figure as what the T3 measurement "
         "validates, not gospel")
    line("note", "airflow is assumed to be NONE",
         "the stack sits between the ESC and the battery. A hovering quad moves air "
         "downward past it, which helps, but by an amount nobody here has measured")
    line("note", "U19 watches U9, and ONLY U9",
         "U19 is 3.9 mm from U9 and 17.2 mm from U8, so it is a U9 sensor and not a "
         "board-wide one. It also reads the BOARD, not the junction: it cannot see "
         "through a package. What it gives is a logged trend from every flight instead "
         "of one bench reading, which is what turns this from an open question into a "
         "number that would have to get worse in front of you")
    line("note", "what still wants a thermocouple",
         "U8 has no sensor near it, and the board-to-junction offset at U9 is still "
         "unmeasured. Both are one bench session at runbook T3a - powered, stack "
         "assembled, logging to the card so U9 sees its real duty, 10 minutes. After "
         "that the offset is known and U19 carries it forward on its own")

    print()
    if fails:
        print(f"FAIL - {len(fails)} thermal problem(s)")
        for f in fails:
            print("  - " + f)
        return 1
    if notes:
        print(f"{len(notes)} margin warning(s) - measure before trusting:")
        for n in notes:
            print("  - " + n)
    print("no thermal limit exceeded on the stated assumptions")
    return 0


CHECKS = {
    "design": run_design,
    "topology": run_topology,
    "electrical": run_electrical,
    "esd": run_esd,
    "ratings": run_ratings,
    "symbol_pinout": run_symbol_pinout,
    "pin_semantics": run_pin_semantics,
    "thermal": run_thermal,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        print(__doc__)
        return 2
    return CHECKS[sys.argv.pop(1)]()


if __name__ == "__main__":
    sys.exit(main())
