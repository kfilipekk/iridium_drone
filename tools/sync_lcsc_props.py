#!/usr/bin/env python3
#rewrite the LCSC property of every schematic symbol / board footprint to the
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import design  # noqa: E402

PROP = re.compile(r'^(\t+)\(property "LCSC" "([^"]*)"')
REF = re.compile(r'\(property "Reference" "([^"]+)"')
BODY = re.compile(r'^\t\(symbol |^\t\(footprint ')


#yield the line range of every symbol/footprint instance block
def blocks(text):
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if BODY.match(line):
            if start is not None:
                yield start, i
            start = i
    if start is not None:
        yield start, len(lines)
    return


#return (text, changes, unknown) with each block's LCSC set from `want`
def retag(text, want):
    lines = text.split("\n")
    changes, unknown = [], []
    for lo, hi in blocks(text):
        ref = None
        lcsc_line = None
        for i in range(lo, hi):
            if ref is None:
                m = REF.search(lines[i])
                if m:
                    ref = m.group(1)
            if lcsc_line is None and PROP.match(lines[i]):
                lcsc_line = i
        if ref is None or lcsc_line is None or not re.match(r"^[A-Z]+\d", ref):
            continue
        have = PROP.match(lines[lcsc_line]).group(2)
        code = design.COMPONENTS.get(ref, (None, None, None, None))[3]
        if not code:
            if have:
                unknown.append((ref, have))
            continue
        if have != code:
            changes.append((ref, have, code))
            lines[lcsc_line] = PROP.sub(
                lambda m: f'{m.group(1)}(property "LCSC" "{code}"', lines[lcsc_line])
    return "\n".join(lines), changes, unknown


def main():
    write = "--write" in sys.argv
    rc = 0
    for name in ("NAVCORE-SoOP.kicad_sch", "NAVCORE-SoOP.kicad_pcb"):
        path = os.path.join(ROOT, name)
        text = open(path, encoding="utf-8").read()
        new, changes, unknown = retag(text, design.COMPONENTS)
        print(f"{name}: {len(changes)} LCSC field(s) disagree with design.py")
        for ref, have, code in sorted(changes):
            print(f"   {ref:5} {have:12} -> {code}")
        if unknown:
            print(f"   {len(unknown)} footprint(s) carry an LCSC code design.py "
                  f"no longer assigns: {', '.join(sorted(r for r, _ in unknown))}")
        if changes:
            rc = 1
            if write:
                open(path, "w", encoding="utf-8").write(new)
                print("   written")
    if rc and not write:
        print("\nre-run with --write to fix")
    return 0 if (not rc or write) else 1


if __name__ == "__main__":
    sys.exit(main())
