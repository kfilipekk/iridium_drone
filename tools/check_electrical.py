#!/usr/bin/env python3
"""Check the analogue reality: decoupling, dividers, pull-ups, protection.

Usage:  python3 tools/check_electrical.py [-v]
"""
import os, re, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design, symlib, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
RAILS = {"+3V3", "+3V3A", "+3V3_CAN", "+5V", "+5V_PAYLOAD", "+9V", "VBAT", "VDDA", "VBUS"}
DECOUPLE_NEAR = 3.0        # mm; beyond this a 100n is not doing its job at 100 MHz
DECOUPLE_FAR  = 6.0        # mm; beyond this it is decoration

# Datasheet-mandated externals and strapping, beyond plain decoupling.
REQUIRED = [
    # STM32H743VIT6 core regulator: VCAP1/VCAP2 each need their own capacitor to GND.
    ("U1",  "VCAP1/VCAP2 on the internal LDO",
     {"48": "VCAP1", "73": "VCAP2"}),
    # VDDA must reach the MCU through a ferrite from +3V3, not straight off the rail.
    ("U1",  "VDDA filtered from +3V3 by a ferrite",
     {"21": "VDDA", "20": "VDDA"}),
    ("L1",  "the VDDA ferrite bridges +3V3 to VDDA",
     {"1": "+3V3", "2": "VDDA"}),
    # 2 = PS (high selects I2C), 5 = CSB.
    ("U4",  "MS5611 strapped for I2C at 0x77 (PS high, CSB low)",
     {"2": "+3V3A", "5": "GND"}),
    # 8 = Rs.
    ("U11", "SN65HVD230 Rs is driven, not floating",
     {"8": None}),
    # USBLC6-2SC6 must sit between the connector and the MCU: 1/3 face the connector,
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
    # The reference is A property of the part, and hardcoding it hid a real error.
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
    # Enable dividers set the undervoltage lockout.
    PACK_EMPTY_V = design.CELLS * 3.3       # 4S at 3.3 V/cell - land well before this
    # The lower bound is A property of the part TOO.
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
            # The binding part is the one with the lowest absolute maximum.
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
    # Reverse-polarity protection: a P-FET wired between VBAT_IN (battery) and VBAT (rail).
    prot = any(
        design.COMPONENTS[r][2] == "WST4041"
        and npad.get(f"{r}.2") == "VBAT"      # source -> protected rail
        and npad.get(f"{r}.3") == "VBAT_IN"   # drain  -> battery side
        for r in design.COMPONENTS if r.startswith("Q"))
    if not prot:
        warns.append("no reverse-polarity protection on VBAT - a TVS clamps a reversed "
                     "pack at -0.7 V and dies, taking the rail with it")

    # ---------------------------------------------------------- 6. crystal
    # The oscillator sees CL = (C15*C16)/(C15+C16) + stray.
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
