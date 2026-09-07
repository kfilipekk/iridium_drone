#!/usr/bin/env python3
"""
Parse an ArduPilot hwdef.dat into a canonical {PIN: signal} map.

Purpose: the NAVCORE-SoOP schematic must match MatekH743's pinout exactly, so that
stock ArduPilot binaries run on the board unmodified. This turns the hwdef
into machine-readable truth so the schematic can be checked against it rather than
transcribed by hand.

Usage:
  ./hwdef_pinmap.py firmware/reference/MatekH743-hwdef.dat            # table
  ./hwdef_pinmap.py firmware/reference/MatekH743-hwdef.dat --json     # machine readable
  ./hwdef_pinmap.py A.dat --diff B.dat                                # compare two hwdefs
"""
import re, sys, json

PIN_RE = re.compile(r'^(P[A-K]\d{1,2})\s+(\S+)\s+(\S+)(.*)$')

def parse(path):
    pins, alts = {}, {}
    for raw in open(path):
        line = raw.split('#')[0].strip()
        if not line:
            continue
        m = PIN_RE.match(line)
        if not m:
            continue
        pin, label, periph, rest = m.groups()
        entry = {'label': label, 'periph': periph, 'opts': rest.split()}
        # ALT(n) lines are alternate pin functions, not the primary assignment
        if 'ALT(' in rest:
            alts.setdefault(pin, []).append(entry)
        else:
            pins[pin] = entry
    return pins, alts

def sort_key(p):
    return (p[1], int(p[2:]))

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)
    pins, alts = parse(args[0])

    if '--json' in args:
        print(json.dumps({'pins': pins, 'alts': alts}, indent=2, sort_keys=True)); return

    if '--diff' in args:
        other, _ = parse(args[args.index('--diff') + 1])
        only_a = sorted(set(pins) - set(other), key=sort_key)
        only_b = sorted(set(other) - set(pins), key=sort_key)
        changed = sorted([p for p in set(pins) & set(other)
                          if pins[p]['label'] != other[p]['label']], key=sort_key)
        for title, items in (('only in A', only_a), ('only in B', only_b)):
            print(f"\n{title}: {len(items)}")
            for p in items:
                src = pins if items is only_a else other
                print(f"  {p:6s} {src[p]['label']}")
        print(f"\nreassigned: {len(changed)}")
        for p in changed:
            print(f"  {p:6s} {pins[p]['label']:22s} -> {other[p]['label']}")
        return

    print(f"{len(pins)} pins assigned in {args[0]}\n")
    print(f"{'PIN':6s} {'SIGNAL':24s} {'PERIPH':10s} OPTIONS")
    print('-' * 72)
    for p in sorted(pins, key=sort_key):
        e = pins[p]
        print(f"{p:6s} {e['label']:24s} {e['periph']:10s} {' '.join(e['opts'])}")
    if alts:
        print(f"\nalternate functions ({len(alts)} pins):")
        for p in sorted(alts, key=sort_key):
            for e in alts[p]:
                print(f"  {p:6s} {e['label']:22s} {' '.join(e['opts'])}")

if __name__ == '__main__':
    main()
