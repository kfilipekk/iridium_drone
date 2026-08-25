#!/usr/bin/env python3
"""
Check the analogue reality: decoupling, dividers, pull-ups, protection.

Everything else in tools/ checks topology - that nets exist, that pins are wired, that
copper is manufacturable. None of it checks whether the VALUES are right, and a board
can pass every one of those and still not start: a regulator divider set for the wrong
rail, a power pin with no decoupling, an ADC scale that disagrees with the resistors
actually fitted.

That is not hypothetical here. The 5 V buck's divider was originally 10k2/3k24, which
is 3.32 V - a 3.3 V rail where 5 V was intended. It was caught by hand while sourcing
parts. This tool exists so the next one is caught by a script.

Values come from design.COMPONENTS AFTER all of design.py's late corrections, not from
the RES()/CAP() calls, because those get overridden further down the file. Distances
come from the actual PCB, not from the adjacency targets - the target is the intent,
the board is the fact.

Usage:  python3 tools/check_electrical.py [-v]
"""
import os, re, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design, symlib, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
RAILS = {"+3V3", "+3V3A", "+5V", "+9V", "VBAT", "VDDA", "VBUS"}
DECOUPLE_NEAR = 3.0        # mm; beyond this a 100n is not doing its job at 100 MHz
DECOUPLE_FAR  = 6.0        # mm; beyond this it is decoration

# Datasheet-mandated externals and strapping, beyond plain decoupling.
#
# THIS LIST USED TO BE DECLARED AND NEVER READ. It sat here as five entries with a
# "how to test" column that no code consulted - `grep -n REQUIRED` returned exactly one
# hit, this line - so it read as coverage while asserting nothing. A declared-but-unrun
# check is worse than no check, because it is counted.
#
# Each entry is now (ref, what, pins) where `pins` maps pad number -> the net that pad
# must be on, or None for "must be connected to something, value not asserted here".
# Pin numbers were read off the fitted parts' datasheets, not inferred from the netlist
# they are checking - inferring them from the thing under test is how a check ends up
# agreeing with a fault.
REQUIRED = [
    # STM32H743VIT6 core regulator: VCAP1/VCAP2 each need their own capacitor to GND.
    # (Capacitor VALUES are check_topology.py's; this asserts the pins exist and land.)
    ("U1",  "VCAP1/VCAP2 on the internal LDO",
     {"48": "VCAP1", "73": "VCAP2"}),
    # VDDA must reach the MCU through a ferrite from +3V3, not straight off the rail.
    ("U1",  "VDDA filtered from +3V3 by a ferrite",
     {"21": "VDDA", "20": "VDDA"}),
    ("L1",  "the VDDA ferrite bridges +3V3 to VDDA",
     {"1": "+3V3", "2": "VDDA"}),
    # MS5611-01BA03: 2 = PS (high selects I2C), 5 = CSB. The I2C address is 111011Cx
    # where C is the COMPLEMENT of CSB, so CSB low gives 0x77. Pin 6 is SDO, unused in
    # I2C mode and deliberately left open.
    ("U4",  "MS5611 strapped for I2C at 0x77 (PS high, CSB low)",
     {"2": "+3V3A", "5": "GND"}),
    # SN65HVD230: 8 = Rs. It must go somewhere - a slope-control resistor to GND, or a
    # GPIO for silent mode. Floating leaves the transceiver's mode undefined. This board
    # drives it from CAN1_SILENT, which is the GPIO option.
    ("U11", "SN65HVD230 Rs is driven, not floating",
     {"8": None}),
    # USBLC6-2SC6 must sit BETWEEN the connector and the MCU: 1/3 face the connector,
    # 6/4 face the MCU. Wired the other way round it protects nothing.
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


def positions():
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


def main():
    verbose = "-v" in sys.argv
    npad = net_of_pad()
    pos = positions()
    errs, warns, notes = [], [], []

    # what each ref's pads connect to
    pads_of = {}
    for sp in npad:
        ref, pad = sp.split(".", 1)
        pads_of.setdefault(ref, []).append(pad)

    # ---------------------------------------------------------------- 1. decoupling
    # A decoupling cap is a two-pad capacitor with one leg on a rail and one on GND.
    caps = {}
    for ref in design.COMPONENTS:
        if not ref.startswith("C"):
            continue
        legs = [(npad.get(f"{ref}.1"), npad.get(f"{ref}.2"))]
        (a, b), = legs
        if a in RAILS and b == "GND":
            caps.setdefault(a, []).append(ref)
        elif b in RAILS and a == "GND":
            caps.setdefault(b, []).append(ref)

    # Only genuine SUPPLY pins need decoupling. A logic pin strapped to a rail - the
    # W25Q128's /WP and /HOLD, the PMW3901's NRESET - sits on +3V3 but draws nothing,
    # and flagging it as an undecoupled power pin is noise that hides the real ones.
    # The symbol library already records pin type, so use it rather than guessing.
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
            if rail not in RAILS:
                continue
            if ptype.get(f"{ic}.{pad}") != "power_in":
                continue                      # strapped logic pin, not a supply
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

    # ------------------------------------------------ 1b. datasheet-mandated externals
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

    # ---------------------------------------------------------- 2. buck dividers
    # THE REFERENCE IS A PROPERTY OF THE PART, and hardcoding it hid a real error.
    # This read 0.800 V (TPS54331) and kept doing so after both bucks became TPS54202,
    # whose reference is 0.596 V - so it reported the CORRECT new divider as 6.67 V and
    # "more than 10% off". A checker that assumes the part is the same class of fault as
    # a design that assumes the datasheet. Look the reference up from what is fitted.
    VREF = {"TPS54331": 0.800,      # [D] TI TPS54331 datasheet
            "TPS54202": 0.596}      # [D] TI TPS54202 SLVSD26C, "typical voltage
                                    #     reference is designed at 0.596 V"
    for name, rail, rtop, rbot in (("5 V buck (U8)", "+5V", "R6", "R7"),
                                   ("9 V buck (U18)", "+9V", "R42", "R43")):
        _ref_part = design.COMPONENTS[name.split("(")[1].rstrip(")")][2]
        if _ref_part not in VREF:
            errs.append(f"{name}: regulator {_ref_part} has no reference voltage in "
                        f"VREF - add it with its datasheet citation before trusting "
                        f"this divider")
            continue
        vref = VREF[_ref_part]
        a, b = to_ohms(value_of(rtop)), to_ohms(value_of(rbot))
        if not a or not b:
            notes.append(f"{name}: cannot read {rtop}/{rbot}")
            continue
        vout = vref * (1 + a / b)
        want = {"+5V": 5.0, "+9V": 9.0}[rail]
        line = (f"{name}: {value_of(rtop)}/{value_of(rbot)} -> {vout:.2f} V "
                f"(target {want} V)")
        if abs(vout - want) / want > 0.10:
            errs.append(line + " - more than 10% off")
        elif abs(vout - want) / want > 0.05:
            warns.append(line)
        else:
            notes.append(line)
    # Enable dividers set the undervoltage lockout. This block hardcoded 1.25 V with the
    # comment "TPS54331 EN threshold is 1.25 V" on a board carrying TPS54202 - the exact
    # assume-the-part fault the VREF table above was written to end - and it appended to
    # `notes` only, so no combination of values could make it fail. Both fixed: the
    # threshold is looked up from what is FITTED, an unlisted regulator is an error, and
    # the UVLO is asserted against the window it actually has to sit in.
    #
    # The load-bearing property is not the threshold's exact value - it is that the rail
    # comes up before the pack is flat and stays above the regulator's own minimum input.
    PACK_EMPTY_V = design.CELLS * 3.3       # 4S at 3.3 V/cell - land well before this
    BUCK_MIN_VIN = 4.5                      # [D] SLVSD26C recommended minimum VIN
    for name, ref, rtop, rbot in (("5 V buck EN", "U8", "R4", "R5"),
                                  ("9 V buck EN", "U18", "R40", "R41")):
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
        vth, confirmed, src = ent
        uvlo = vth * (a + b) / b
        line = (f"{name}: {value_of(rtop)}/{value_of(rbot)} at a {vth} V threshold "
                f"-> starts at {uvlo:.1f} V in")
        if uvlo >= PACK_EMPTY_V:
            errs.append(line + f" - that is AT OR ABOVE a flat {design.CELLS}S pack "
                               f"({PACK_EMPTY_V:.1f} V); the rail would drop out in "
                               f"flight")
        elif uvlo <= BUCK_MIN_VIN:
            errs.append(line + f" - below the regulator's own {BUCK_MIN_VIN} V minimum "
                               f"input, so the UVLO does nothing")
        else:
            notes.append(line + f" (window {BUCK_MIN_VIN}-{PACK_EMPTY_V:.1f} V)")
        if not confirmed:
            warns.append(f"{name}: the {vth} V EN threshold for {part} is {src} - the "
                         f"UVLO figure above inherits that uncertainty")

    # ---------------------------------------------------------- 3. ADC scaling
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

    # ---------------------------------------------------------- 4. bus pull-ups
    pulls = {}
    for ref in design.COMPONENTS:
        if not ref.startswith("R"):
            continue
        a, b = npad.get(f"{ref}.1"), npad.get(f"{ref}.2")
        for sig, rail in ((a, b), (b, a)):
            if rail in RAILS and sig and sig not in RAILS and sig != "GND":
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

    # ---------------------------------------------------------- 5. protection
    # This used to compute CELL-COUNT HEADROOM - "33 V standoff, fine to 7.9S" - which is
    # the wrong question and was emitted as a note regardless of the answer. Standoff
    # says when the TVS starts conducting. What decides whether it protects anything is
    # its CLAMPING voltage against the absolute maximum of what sits downstream: a surge
    # clamped above the buck's rating destroys the buck with the TVS working perfectly.
    tvs = value_of("D1")
    if tvs:
        mv = re.search(r'SMBJ(\d+)', tvs or "")
        standoff = int(mv.group(1)) if mv else None
        clamp = design.TVS_CLAMP_V.get(tvs)
        # everything sitting directly on VBAT that has a declared maximum
        downstream = {}
        for ref, comp in design.COMPONENTS.items():
            if comp[4]:                                   # DNP parts still get fitted
                pass                                      # on the FPV variant - include
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
            # The binding part is the one with the LOWEST absolute maximum.
            worst_ref, (worst_part, rec_v, abs_v, abs_ok, worst_src) = min(
                downstream.items(), key=lambda kv: kv[1][2])
            pack_max = design.CELLS * 4.2
            if vc > abs_v:
                # Name the parts that would actually work, rather than only the fault.
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
    if not any(design.COMPONENTS[r][2].startswith(("AO34", "SI2", "IRF"))
               and "VBAT" in (npad.get(f"{r}.1"), npad.get(f"{r}.2"), npad.get(f"{r}.3"))
               for r in design.COMPONENTS if r.startswith("Q")):
        warns.append("no reverse-polarity protection on VBAT - a TVS clamps a reversed "
                     "pack at -0.7 V and dies, taking the rail with it")

    # ---------------------------------------------------------- 6. crystal
    # The oscillator sees CL = (C15*C16)/(C15+C16) + stray. design.py declares the
    # crystal's specified CL and derives the caps from it; this checks the board agrees,
    # so the two cannot drift apart the way the part number and the sourcing note did.
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
    # An active oscillator fits this footprint and would have its supply grounded.
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

    # ------------------------------------------------------- 7. current capacity
    # Deliberately NOT done here any more. This file used to judge each rail by the feed
    # to its weakest trace-fed pad, and that measure kept mistaking things for loads:
    # bypass capacitors, divider taps, and strapped logic pins like the flash's /WP,
    # which draws microamps and reported 0.00 A.
    #
    # tools/check_power_cut.py answers the same question without needing to know what a
    # pad is for: draw a line separating the regulator from its loads and add up every
    # piece of that net's copper crossing it. Current cannot exceed that sum whatever the
    # topology. One measure, and the trustworthy one - two overlapping checks that
    # disagree are worse than either alone.
    notes.append("current capacity is checked by tools/check_power_cut.py")

    # ---------------------------------------------------------------- report
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


if __name__ == "__main__":
    sys.exit(main())
