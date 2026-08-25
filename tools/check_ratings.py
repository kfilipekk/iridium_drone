#!/usr/bin/env python3
"""Is every part actually rated for the net it is soldered to?

Usage: python3 tools/check_ratings.py
"""
import os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

DERATE = 2.0          # warn below this multiple of the working voltage
# Package power ratings, W. [D] generic chip-resistor ratings; conservative.
R_POWER = {"0402": 0.0625, "0603": 0.10, "0805": 0.125, "1206": 0.25}
# Capacitors that must not be a Class II dielectric, and why.
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
    for p in ("0402", "0603", "0805", "1206", "1210"):
        if p in footprint: return p
    return None


def _is_dnp(ref):
    """A part that is not fitted cannot be over-rated or the wrong size for its land."""
    c = design.COMPONENTS.get(ref)
    return bool(c and c[4])


def main():
    # net -> refs, and ref -> nets
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
        # package agreement between the footprint and the part
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
        p = v * v / ohms                      # conservative: full rail across the part
        pk = pkg_of(fp); lim = R_POWER.get(pk)
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
        # the land pattern the board actually has
        land = pkg_of(fp)
        LAND_MM = {"1210": (3.2, 2.5), "0805": (2.0, 1.25), "1206": (3.2, 1.6)}
        lm = LAND_MM.get(land)
        # Does the part actually fit?
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
                # terminal footprint implied by the part's body
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

    # Parts explicitly marked unverified are reported whether or not the checker reached them.
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


main()
