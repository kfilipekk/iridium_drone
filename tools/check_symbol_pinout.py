#!/usr/bin/env python3
"""Compare every active part's symbol pinout against an authority that is not this project.

Usage:  python3 tools/check_symbol_pinout.py [-v]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design, jlcpaths

JLC_SYM = jlcpaths.SYMBOLS
KICAD_SYM_DIRS = ["/usr/share/kicad/symbols", "/usr/local/share/kicad/symbols"]

# our symbol name -> (kicad library file, kicad symbol name)
CROSS_CHECK = {
    "STM32H743VIT6_C114409": ("MCU_ST_STM32H7", "STM32H743VITx"),
    "SN65HVD230DR":          ("Interface_CAN_LIN", "SN65HVD230"),
    "USBLC6-2SC6_C2687116":  ("Power_Protection", "USBLC6-2SC6"),
    "W25Q128JVSIQTR":        ("Memory_Flash", "W25Q128JVS"),
    "TPS54202DDCR":          ("Regulator_Switching", "TPS54202DDC"),
    "AP2112K-3_3TRG1":       ("Regulator_Linear", "AP2112K-3.3"),
    "MS561101BA03-50":       ("Sensor_Pressure", "MS5611-01BA"),
    "AO3400A":               ("Transistor_FET", "AO3400A"),
    "TMP119AIYBGR":          ("Sensor_Temperature", "TMP119AIYBGR"),
    # Added after this part turned out to be wired backwards on the board.
    "XC6206P332MR":          ("Regulator_Linear", "XC6206PxxxMR"),
}

# Parts with no KiCad equivalent, verified by hand against the manufacturer document.
DATASHEET_VERIFIED = {
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
}


def _blocks(text):
    for m in re.finditer(r'\(symbol\s+"([^"]+)"', text):
        i = m.start(); d = 0; j = i
        while j < len(text):
            if text[j] == '(':
                d += 1
            elif text[j] == ')':
                d -= 1
                if d == 0:
                    break
            j += 1
        yield m.group(1), text[i:j + 1]


def pinmap(path, name):
    """{pin number: pin name} for a symbol, following extends and unit children."""
    if not os.path.exists(path):
        return None, f"library missing: {path}"
    blocks = dict(_blocks(open(path).read()))
    if name not in blocks:
        return None, f"symbol {name!r} not in {os.path.basename(path)}"
    base = name
    ext = re.search(r'\(extends\s+"([^"]+)"', blocks[name])
    if ext:
        base = ext.group(1)
    out = {}
    for nm, b in blocks.items():
        if nm == base or nm.startswith(base + "_"):
            for m in re.finditer(
                    r'\(pin\s+\S+\s+\S+.*?\(name\s+"([^"]*)".*?\(number\s+"([^"]*)"',
                    b, re.S):
                out[m.group(2)] = m.group(1)
    return out, None


def variants(name):
    """Every spelling of a pin name that should count as the same pin."""
    n = name.upper().strip()
    n = re.sub(r'~\{([^}]*)\}', r'\1', n)        # KiCad inversion -> bare name
    n = re.sub(r'_\{([^}]*)\}', r'\1', n)        # subscript IO_{1} -> IO1
    n = n.replace("{", "").replace("}", "")
    n = re.sub(r'\s', '', n)

    out = set()
    for alt in n.split("/"):                      # alternate function names
        if not alt:
            continue
        for form in (alt, alt.rstrip("#"), alt.rstrip("N") if alt.endswith("N") else alt):
            f = form.replace("_", "").replace("-", "")
            if f:
                out.add(f)
        if "-" in alt:                            # PC14-OSC32_IN -> PC14
            head = alt.split("-", 1)[0]
            if head:
                out.add(head.replace("_", ""))
    syn = {"VSS": "GND", "GND": "VSS", "VDD": "VCC", "VCC": "VDD",
           "VI": "VIN", "VIN": "VI", "VO": "VOUT", "VOUT": "VO"}
    for v in list(out):
        if v in syn:
            out.add(syn[v])
    return {x for x in out if x and x not in ("NC", "DNC")}


def main():
    verbose = "-v" in sys.argv
    actives = {r: v for r, v in design.COMPONENTS.items()
               if r.startswith(("U", "Q", "Y"))}
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
        by_symbol.setdefault(v[0].split(":", 1)[1], []).append(ref)

    fails, unverified = [], []
    print(f"jlc symbols : {JLC_SYM}")
    print(f"{'symbol':34} {'refs':14} {'pins':>5}  verdict")
    print("-" * 78)

    for sym in sorted(by_symbol):
        refs = ",".join(sorted(by_symbol[sym]))
        ours, err = pinmap(JLC_SYM, sym)
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
        # only pins the netlist actually uses can scrap a board; report all, fail on used
        relied = set()
        for r in by_symbol[sym]:
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
                net = next((used[r][num] for r in by_symbol[sym]
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


if __name__ == "__main__":
    raise SystemExit(main())
