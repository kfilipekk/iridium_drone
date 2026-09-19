#!/usr/bin/env python3
"""The order bundle matches the board that was verified.

Usage: python3 tools/check_order_bundle.py
"""
import csv
import io
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BUNDLE = os.path.join(REPO, "fab", "NAVCORE-SoOP-order-bundle.zip")
GERBERS = os.path.join(REPO, "fab", "gerbers")

FLAT = ["BOM-NAVCORE-SoOP.csv", "CPL-NAVCORE-SoOP.csv",
        "BOM-NAVCORE-SoOP-economic.csv", "CPL-NAVCORE-SoOP-economic.csv",
        "BOM-NAVCORE-SoOP-nofpv.csv", "CPL-NAVCORE-SoOP-nofpv.csv"]
REQUIRED = ["HOW-TO-ORDER.txt", "gerbers.zip", "BOM-NAVCORE-SoOP.csv",
            "CPL-NAVCORE-SoOP.csv"]


def main():
    fails = []
    if not os.path.exists(BUNDLE):
        print(f"FAIL - {os.path.relpath(BUNDLE, REPO)} does not exist; "
              f"run tools/make_order_bundle.sh")
        return 1

    zf = zipfile.ZipFile(BUNDLE)
    names = set(zf.namelist())

    # ---- 1. present ----------------------------------------------------------
    missing = [n for n in REQUIRED if n not in names]
    for n in missing:
        fails.append(f"the bundle does not contain {n}")
    print(f"bundle     : {os.path.relpath(BUNDLE, REPO)} ({len(names)} member(s))")

    # ---- 2. identical --------------------------------------------------------
    flat_ok = flat_bad = 0
    for name in FLAT:
        if name not in names:
            continue                      # the *-economic/-nofpv variants are optional
        disk = os.path.join(REPO, "fab", name)
        if not os.path.exists(disk):
            fails.append(f"{name} is in the bundle but not on disk - cannot verify it")
            continue
        if zf.read(name) != open(disk, "rb").read():
            fails.append(f"{name} in the bundle DIFFERS from fab/{name} - the bundle is "
                         f"stale; re-run tools/make_order_bundle.sh")
            flat_bad += 1
        else:
            flat_ok += 1

    ger_ok = ger_bad = ger_missing = 0
    if "gerbers.zip" in names:
        inner = zipfile.ZipFile(io.BytesIO(zf.read("gerbers.zip")))
        disk_gerbers = sorted(f for f in os.listdir(GERBERS)) if os.path.isdir(GERBERS) else []
        for member in inner.namelist():
            if member.endswith("/"):
                continue
            base = os.path.basename(member)
            disk = os.path.join(GERBERS, base)
            if not os.path.exists(disk):
                ger_missing += 1
                fails.append(f"gerbers/{base} is in the bundle but not in fab/gerbers/")
            elif inner.read(member) != open(disk, "rb").read():
                ger_bad += 1
                fails.append(f"gerbers/{base} in the bundle DIFFERS from fab/gerbers/ - "
                             f"the bundle is stale; re-run tools/make_order_bundle.sh")
            else:
                ger_ok += 1
        bundled = {os.path.basename(m) for m in inner.namelist() if not m.endswith("/")}
        for base in disk_gerbers:
            if base not in bundled:
                fails.append(f"fab/gerbers/{base} is NOT in the bundle - the bundle is "
                             f"missing a layer; re-run tools/make_order_bundle.sh")

    print(f"csv files  : {flat_ok} identical, {flat_bad} diverged")
    print(f"gerbers    : {ger_ok} identical, {ger_bad} diverged, {ger_missing} absent on disk")

    # ---- 3. derived ----------------------------------------------------------
    if "HOW-TO-ORDER.txt" in names and "CPL-NAVCORE-SoOP.csv" in names:
        txt = zf.read("HOW-TO-ORDER.txt").decode()
        rows = list(csv.DictReader(
            io.StringIO(zf.read("CPL-NAVCORE-SoOP.csv").decode())))
        top = sum(1 for r in rows if (r.get("Layer") or "").strip().lower() == "top")
        bot = sum(1 for r in rows if (r.get("Layer") or "").strip().lower() == "bottom")
        m = re.search(r"(\d+)\s+top,\s+(\d+)\s+bottom", txt)
        if not m:
            fails.append("HOW-TO-ORDER.txt does not state a placement count - the "
                         "@@SIDES@@ placeholder may never have been substituted")
            print("placements : NOT FOUND in HOW-TO-ORDER.txt")
        else:
            got = (int(m.group(1)), int(m.group(2)))
            print(f"placements : HOW-TO-ORDER.txt says {got[0]} top / {got[1]} bottom; "
                  f"the bundled CPL says {top} top / {bot} bottom")
            if got != (top, bot):
                fails.append(f"HOW-TO-ORDER.txt says {got[0]} top / {got[1]} bottom but "
                             f"the CPL in the same bundle has {top} top / {bot} bottom")

    print()
    if fails:
        print(f"FAIL - {len(fails)} problem(s) with the order bundle:")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("order bundle is present, matches the tree it was built from, and is self-consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
