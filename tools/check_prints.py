#!/usr/bin/env python3
"""Is every printed part in cad/print, and is each STL the part as it is now designed?

Usage:  python3 tools/check_prints.py [--self-test]
"""
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design             # noqa: E402
import gen_scad_mounts    # noqa: E402

PRINT_DIR = gen_scad_mounts.PRINT_DIR
#design.py dicts that declare a printed part
PRINTED_BY_FLAG = {"SKID": "skid"}


def required():
    names = set(design.MOUNTS) | {"gps_pod", "gps_lid", "xiao_lid", "rx_cover", "range_lid",
                                  "rid_cover"}
    for attr, name in PRINTED_BY_FLAG.items():
        if getattr(design, attr, {}).get("printed"):
            names.add(name)
    flagged = sorted(k for k, v in vars(design).items()
                     if isinstance(v, dict) and v.get("printed") is True)
    unmapped = [k for k in flagged if k not in PRINTED_BY_FLAG]
    return names, unmapped


def shape(path):
    """(triangle count, bbox, volume) of an ASCII STL - order-free."""
    pts = [tuple(map(float, m)) for m in re.findall(
        r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", open(path, errors="ignore").read())]
    tris = [pts[i:i + 3] for i in range(0, len(pts) - len(pts) % 3, 3)]
    if not tris:
        return (0, None, 0.0)
    lo = tuple(min(p[i] for p in pts) for i in range(3))
    hi = tuple(max(p[i] for p in pts) for i in range(3))
    vol = sum((a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
               + a[2] * (b[0] * c[1] - b[1] * c[0])) for a, b, c in tris) / 6.0
    return (len(tris), lo + hi, abs(vol))


def same(a, b):
    (na, ba, va), (nb, bb, vb) = shape(a), shape(b)
    return (na == nb and na > 0 and all(abs(x - y) < 1e-3 for x, y in zip(ba, bb))
            and abs(va - vb) <= 1e-4 * max(va, 1.0))


def compare(fresh, committed):
    fails = []
    names, unmapped = required()
    for k in unmapped:
        fails.append(f"design.{k} says printed=True but no print_ module is mapped to it")
    for n in sorted(names - set(gen_scad_mounts.PRINTED)):
        fails.append(f"{n} is printed but not in gen_scad_mounts.PRINTED")
    for n in gen_scad_mounts.PRINTED:
        a, b = os.path.join(fresh, n + ".stl"), os.path.join(committed, n + ".stl")
        if not os.path.exists(b):
            fails.append(f"cad/print/{n}.stl is missing")
        elif not same(a, b):
            fails.append(f"cad/print/{n}.stl is not today's design - run "
                         f"tools/gen_scad_mounts.py --stl")
    return fails


def main():
    with tempfile.TemporaryDirectory() as fresh:
        gen_scad_mounts.export_stl(fresh, quiet=True)
        if "--self-test" in sys.argv:
            ok = not compare(fresh, PRINT_DIR)
            print(f"  {'clean' if ok else 'NOT CLEAN'}  cad/print as committed")
            with tempfile.TemporaryDirectory() as t:
                for name, brk in (("a part deleted", lambda d: os.unlink(os.path.join(d, "skid.stl"))),
                                  ("a part truncated", lambda d: open(os.path.join(d, "gps_lid.stl"), "w").close()),
                                  ("a part edited", lambda d: open(os.path.join(d, "range_lid.stl"), "w").write(
                                      open(os.path.join(PRINT_DIR, "range_lid.stl")).read().replace("vertex", "vertex 1", 3)))):
                    shutil.rmtree(t); shutil.copytree(PRINT_DIR, t)
                    brk(t)
                    caught = bool(compare(fresh, t))
                    ok &= caught
                    print(f"  {'caught' if caught else 'MISSED'}  {name}")
            print("self-test passed: every break is caught" if ok else "SELF-TEST FAILED")
            return 0 if ok else 1
        fails = compare(fresh, PRINT_DIR)
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} printed part(s) missing or stale")
        return 1
    print(f"{len(gen_scad_mounts.PRINTED)} printed parts, each STL the solid today's design exports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
