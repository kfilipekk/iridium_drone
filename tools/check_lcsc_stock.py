#!/usr/bin/env python3
"""Check every LCSC code on the BOM against JLCPCB's own parts library."""
import csv, glob, gzip, json, sys, os

DATA = os.environ.get("JLC_DATA", "/tmp/nav/jlc")

# Codes the mirror does not carry but JLCPCB does. Verified individually at
# jlcpcb.com/partdetail/<code>; keep the quote so the next reader need not re-check.
MIRROR_GAPS = {
    "C51940119": "J3's JST-GH 6P. jlcpcb.com/partdetail/C51940119: "
                 "\"JLCPCB supports PCB assembly for the XY-SM06B-GHS-TB\", "
                 "Extended part, Economic and Standard PCBA. Verified 2026-09-03.",
}


def load_index(want):
    idx = {}
    for f in glob.glob(os.path.join(DATA, '*.gz')):
        try:
            with gzip.open(f, 'rt') as fh:
                hdr = None
                for line in fh:
                    line = line.strip()
                    if not line: continue
                    d = json.loads(line)
                    if hdr is None and isinstance(d, dict) and 'lcsc' in d:
                        hdr = d; continue
                    if not isinstance(d, list): continue
                    code = d[hdr['lcsc']]
                    key = f"C{code}" if not str(code).startswith('C') else str(code)
                    if key in want:
                        idx[key] = {k: (d[v] if v < len(d) else None) for k, v in hdr.items()}
        except Exception:
            continue
    return idx

bom = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
         'fab', 'BOM-NAVCORE-SoOP.csv')
rows = list(csv.DictReader(open(bom)))
want = {}
for r in rows:
    c = (r.get('LCSC') or '').strip()
    if c: want.setdefault(c, []).append(r)
print(f"{len(want)} distinct LCSC codes on {os.path.basename(bom)}")
if not glob.glob(os.path.join(DATA, '*.gz')):
    print(f"no jlcparts data in {DATA} - see this file's docstring for the fetch command")
    sys.exit(2)
idx = load_index(set(want))
missing, low, thin, ok = [], [], [], 0
# Parts that cannot be substituted without changing the board, with why.
CRITICAL = {
    "C5271084":  "STM32H743VIT6 - the MCU; a different package or family is a respin, "
                 "and this family has a shortage history",
    "C1850418":  "ICM-42688-P - primary IMU; the ICM-45686 drop-in is the documented "
                 "fallback on the same LGA-14 land",
    "C2655099":  "ICM-42605 - second IMU, same footprint family",
    "C15639":    "MS5611 barometer - the hwdef and I2C address assume this part",
    "C2765186":  "USB-C connector - a different footprint is a respin",
    "C160407":   "JST-SH 8P - must mate with the ESC's supplied cable",
}
# An absolute floor, not a multiple of this order.
CRITICAL_FLOOR = 2000

NEED = {}
for c, rs in want.items():
    qty = sum(int(r['Qty']) for r in rs if r.get('Qty', '').isdigit())
    NEED[c] = qty
print(f"{len(idx)} found in the JLCPCB library, {len(want)-len(idx)} not found\n")
print(f"{'LCSC':>9} {'need':>5} {'stock':>8}  value / part")
print("-" * 78)
for c in sorted(want, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0):
    rec = idx.get(c)
    need = NEED[c]
    val = want[c][0].get('Comment', '?')
    if not rec:
        if c in MIRROR_GAPS:
            print(f"{c:>9} {need:5d} {'(mirror)':>8}  {val}  -- known mirror gap, JLC has it")
            print(f"{'':>9} {'':>5} {'':>8}  {MIRROR_GAPS[c]}")
            ok += 1
            continue
        missing.append(c)
        print(f"{c:>9} {need:5d} {'NOT FOUND':>8}  {val}  <-- check jlcpcb.com/partdetail/{c}")
        continue
    st = rec.get('stock') or 0
    flag = ""
    if st == 0: flag = "  <-- OUT OF STOCK"; low.append((c, val, st))
    elif st < need * 10: flag = "  <-- LOW"; low.append((c, val, st))
    elif c in CRITICAL and st < CRITICAL_FLOOR:
        flag = f"  <-- THIN for a sole-source part ({CRITICAL[c]})"
        thin.append((c, val, st, CRITICAL[c]))
    else: ok += 1
    print(f"{c:>9} {need:5d} {st:8d}  {val}  [{rec.get('mfr')}]{flag}")
print("-" * 78)
print(f"{ok} comfortably in stock, {len(low)} low or out, {len(thin)} thin sole-source, "
      f"{len(missing)} not in the library")
if low:
    print("\nATTENTION:")
    for c, v, s in low: print(f"   {c}  {v}  stock={s}")
if thin:
    print(f"\nTHIN SOLE-SOURCE PARTS (under {CRITICAL_FLOOR} units and not substitutable):")
    for c, v, st, why in thin:
        print(f"   {c}  {v}  stock={st}")
        print(f"      {why}")
    print("   These pass the 'enough for this order' test and would still stall the")
    print("   project if they went. Buy spares with the boards, or check the count again")
    print("   on the day you order rather than trusting this snapshot.")
import sys
sys.exit(1 if (low or missing) else 0)
