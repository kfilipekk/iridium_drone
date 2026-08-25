#!/usr/bin/env python3
"""Parse a .kicad_sym library into {symbol: [(number, name, type, x, y, rot), ...]}."""
import re, sys, os

LIB = os.path.join(os.path.dirname(__file__), "..", "..", ".libraries", "symbols", "jlc_parts.kicad_sym")

def _blocks(s, start):
    """Yield (name, body) for each top-level (symbol "...") at nesting depth `start`."""
    out, i = [], 0
    while True:
        m = re.compile(r'\(symbol "([^"]+)"').search(s, i)
        if not m: break
        depth, j = 0, m.start()
        while j < len(s):
            if s[j] == '(': depth += 1
            elif s[j] == ')':
                depth -= 1
                if depth == 0: break
            j += 1
        out.append((m.group(1), s[m.start():j+1]))
        i = m.end()
    return out

def load(path=LIB):
    s = open(path).read()
    syms = {}
    for name, body in _blocks(s, 0):
        if re.match(r'.*_\d+_\d+$', name):   # sub-unit graphic blocks
            continue
        pins = []
        # sub-blocks are named NAME_<unit>_<style>; track which unit each pin is in
        unit_of = {}
        for um in re.finditer(r'\(symbol "%s_(\d+)_\d+"' % re.escape(name), body):
            u = int(um.group(1)); d, j = 0, um.start()
            while j < len(body):
                if body[j] == '(': d += 1
                elif body[j] == ')':
                    d -= 1
                    if d == 0: break
                j += 1
            for k in range(um.start(), j+1): unit_of[k] = u
        for pm in re.finditer(
            r'\(pin\s+(\S+)\s+(\S+)\s*\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\)'
            r'.*?\(name "([^"]*)".*?\(number "([^"]*)"', body, re.S):
            etype, shape, x, y, rot, pname, pnum = pm.groups()
            pins.append({'num': pnum, 'name': pname, 'type': etype,
                         'x': float(x), 'y': float(y), 'rot': float(rot),
                         'unit': unit_of.get(pm.start(), 1)})
        if pins:
            syms[name] = sorted(pins, key=lambda p: (len(p['num']), p['num']))
    return syms

if __name__ == '__main__':
    syms = load()
    if len(sys.argv) > 1:
        for want in sys.argv[1:]:
            hits = [k for k in syms if want.lower() in k.lower()]
            for h in hits:
                print(f"\n=== {h}  ({len(syms[h])} pins) ===")
                for p in syms[h]:
                    print(f"  {p['num']:>4s}  {p['name']:<28s} {p['type']:<12s} @({p['x']},{p['y']}) r{p['rot']:.0f}")
    else:
        for k in sorted(syms):
            print(f"{len(syms[k]):>4d} pins  {k}")
