#!/usr/bin/env python3
"""Compare every active part's symbol pinout against an authority that is not this project.

THE LAYER UNDERNEATH EVERY OTHER CHECK. design.py wires parts by pin NUMBER. The
schematic, the board, the netlist, the firmware pin map and all 71 preflight checks are
derived from it. Every one of those therefore inherits whatever the SYMBOL says pin 12
is called - and nothing, anywhere, has ever compared that against the manufacturer.

All 20 active parts on this board use symbols from jlc_parts.kicad_sym, which is
auto-generated from EasyEDA data. It is vendored in this repo at libraries/symbols/ so
the check reads a versioned file rather than whatever is in the fetch directory - and
because "auto-generated" means nobody has compared it to a datasheet. A symbol whose pin
numbering is wrong produces a schematic that passes ERC, a board that passes DRC, a
netlist that passes check_design, and a scrapped fabrication run. It is the repo's
signature defect one layer deeper than any previous instance of it: every check measures
something derived from the thing that is wrong.

So this compares pin number -> pin name against KiCad's official symbol libraries, on
the same principle as check_footprints.py using JLCPCB's joint count: consult an
OUTSIDE authority, because agreement between two independent sources is evidence and
agreement with yourself is not.

Parts with no KiCad equivalent are NOT silently skipped - they are listed as requiring
datasheet verification, and DATASHEET_VERIFIED records the ones done by hand, with the
document and the date, so the work cannot quietly rot into an assumption.

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
}

# Parts with no KiCad equivalent, verified by hand against the manufacturer document.
# Each entry is (document, what was compared, date). An entry here is a claim that a
# human read the pinout table and compared every USED pin - not that the part looks fine.
DATASHEET_VERIFIED = {
    # symbol: (document, what was compared, date)
    "TLV75533PDBVR": ("docs/datasheets/TLV755P-SBVS293.pdf Figure 4-2, DBV package",
                      "all 5 pins: IN GND EN NC OUT", "2026-09-17"),
    "MAX2112ETI+T": ("docs/datasheets/MAX2112.pdf pin description table",
                     "all 28 pins + EP, every one wired", "2026-09-17"),
    "OPA2374M{slash}TR": ("docs/datasheets/OPA2374-TI.pdf, D package, Pin Functions: OPA2374",
                          "all 8 pins", "2026-09-17"),
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
    # Y2, the 25 MHz TCXO, is the one entry that rests on the CLASS rather than on the
    # maker's own sheet, and it was re-verified on 2026-09-18 when the PART changed
    # (C22381771 -> C5563878, because the original was down to 1 unit in stock; see
    # design.py for why the replacement was chosen on land pattern rather than spec).
    #
    # Neither YXC nor HCI publishes a pin table that could be reached from here - the
    # same dead end the previous YXC part hit. What was compared instead:
    #   * pin NAMES from the JLCPCB/EasyEDA symbol for C5563878:
    #       1 = "GND or N.C.", 2 = GND, 3 = "OUTPUT RF", 4 = VCC
    #     which wire 2/3/4 exactly as this board does.
    #   * pin 1 is the only real risk, because the board TIES PIN 1 TO GND. That is
    #     correct if pin 1 is GND and harmless if it is genuinely no-connect, and Epson
    #     states the latter explicitly of the same 4-pad TCXO class: "Please keep 'N.C.'
    #     pin OPEN condition or GND connection".
    #   * it is only dangerous where pin 1 is a Disable/Enable or a Vcon - Kyocera's
    #     KT1612A is "#1pin Disable Function", NDK's catalogue lists "Enable/Disable" -
    #     and this is a PLAIN TCXO, not a VC-TCXO, so pin 1 is neither. That is also why
    #     C19674258 (pin 1 = "OE/NC") was rejected in favour of this part.
    #   * output format: JLCPCB's own record for C5563878 states "Clipped sine wave",
    #     which is required because U13's reference input is AC-coupled by C58; HCI's
    #     8132S series description independently confirms clipped-sine for this family.
    #
    # RESIDUAL: HCI's own T132S4 document was not obtained. The pin NAMES come from the
    # JLCPCB symbol, not from the maker, and the safety argument is from the class. If an
    # HCI sheet is ever found, compare it here rather than assuming this entry is best.
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
    """Every spelling of a pin name that should count as the same pin.

    Two CORRECT symbols for one part still disagree cosmetically, in ways that are
    predictable and must not be reported as pinout errors:

        active low     CS#      ~{CS}       CSn
        alternates     DO/IO_{1}            DO, IO1
        subscripts     IO_{2}   IO2
        ST alt-func    PC14-OSC32_IN        PC14
        vendor synonym VSS      GND

    Everything NOT in that list survives normalisation and is reported. The rule is
    deliberately generous about SPELLING and strict about IDENTITY: a real swap, such
    as MOSI and MISO exchanged, produces disjoint sets and fails.
    """
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
    syn = {"VSS": "GND", "GND": "VSS", "VDD": "VCC", "VCC": "VDD"}
    for v in list(out):
        if v in syn:
            out.add(syn[v])
    return {x for x in out if x and x not in ("NC", "DNC")}


def main():
    verbose = "-v" in sys.argv
    actives = {r: v for r, v in design.COMPONENTS.items()
               if r.startswith(("U", "Q", "Y"))}
    # which pins does the netlist actually rely on?
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
