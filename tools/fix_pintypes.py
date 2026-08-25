#!/usr/bin/env python3
"""
Correct electrical pin types in the shared jlc_parts library.

JLC2KiCadLib derives symbols from EasyEDA, which carries no electrical pin type, so
pins land as 'unspecified'. KiCad's ERC then cannot tell a driver from a load and warns
on essentially every connection, which drowns real findings.

Classifying by pin name restores a usable ERC. Conservative on purpose: GPIO ->
bidirectional, recognised supply names -> power_in, everything else -> passive (passive
never triggers a conflict, so a misclassification cannot mask a real error).

OVERRIDES carries the cases a name cannot settle - e.g. TPS54331 'PH' is the switch
node, an output, but reads like a supply.

Idempotent: reclassifies every pin from its name each run, so re-running is safe.
"""
import re, sys, os, shutil

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "..", ".libraries", "symbols", "jlc_parts.kicad_sym")

GPIO  = re.compile(r'^P[A-K]\d{1,2}(-|$)')
POWER = re.compile(r'^(VDD|VSS|VCC|VEE|GND|AVDD|AVSS|VBAT|VIN|VBUS|VDDA|VSSA|'
                   r'VDDIO|AGND|DGND|VREF\+|VREF-|VCC_\w+|EP)$', re.I)

# (symbol, pin name) -> electrical type
OVERRIDES = {
    ("TPS54331DR", "PH"): "passive",   # switch node: an output, not a supply input
}

PIN_RE = re.compile(r'\(pin\s+(\w+)\s+(\w+)((?:.|\n)*?\(number\s+"[^"]*"[^)]*\))')

def top_blocks(s):
    out, i = [], 0
    while True:
        m = re.compile(r'^  \(symbol "([^"]+)"', re.M).search(s, i)
        if not m: break
        d, j = 0, m.start()
        while j < len(s):
            if s[j] == '(': d += 1
            elif s[j] == ')':
                d -= 1
                if d == 0: break
            j += 1
        out.append((m.group(1), m.start(), j + 1))
        i = j + 1
    return out

def classify(sym, name):
    if (sym, name) in OVERRIDES: return OVERRIDES[(sym, name)]
    if GPIO.match(name):  return 'bidirectional'
    if POWER.match(name): return 'power_in'
    return 'passive'

def main(path=LIB):
    src = open(path).read()
    counts, changed = {}, 0
    pieces, last = [], 0
    for symname, a, b in top_blocks(src):
        pieces.append(src[last:a]); blk = src[a:b]

        def repl(m):
            nonlocal changed
            cur, shape, body = m.group(1), m.group(2), m.group(3)
            nm = re.search(r'\(name "([^"]*)"', body)
            want = classify(symname, nm.group(1) if nm else "")
            counts[want] = counts.get(want, 0) + 1
            if want != cur: changed += 1
            return f'(pin {want} {shape}{body}'

        pieces.append(PIN_RE.sub(repl, blk)); last = b
    pieces.append(src[last:])
    out = "".join(pieces)

    if out != src:
        shutil.copy(path, path + ".bak")
        open(path, "w").write(out)
    print(f"{sum(counts.values())} pins classified, {changed} changed: " +
          ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0

if __name__ == "__main__":
    sys.exit(main())
