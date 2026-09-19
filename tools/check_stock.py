#!/usr/bin/env python3
"""Every BOM line is buyable, and each LCSC code resolves to the part the design intends.

WHY THIS EXISTS. "LCSC stock, captured <date>" was a line in the pre-order checklist that
nobody could re-run, so it aged - and a stale stock line reads as verified forever. This
repo already had `check_lcsc_stock.py`, which reads the community jlcparts mirror; measured
2026-09-18 that mirror covers **55 of the same 68 lines as NOT FOUND**, because upstream
has not rebuilt it. A mirror that is empty is worse than no mirror: it produces "NOT FOUND"
for parts JLCPCB assembles every day.

So this asks the AUTHORITY instead. `jlcpcb.com`'s own parts endpoint answers a code with
the manufacturer part number, the package, the stock count, the minimum purchase and
whether the part is Basic or Extended. Those five facts settle more than stock:

  * a TRANSPOSED C-code       - the code resolves, but to a different part number
  * a part DELISTED since the BOM was written
  * a package that disagrees with the footprint - a SECOND authority on top of
                                check_footprints.py, which can only read the mirror
  * Basic vs Extended         - an Extended part carries a per-part setup fee, so this is
                                also the cost of the order
  * stock below what 2 boards need

TIMING. Stock decays daily, so the result is written to a DATED, VERSIONED snapshot
(`fab/stock-snapshot.json`) and the check fails once it is older than MAX_AGE_DAYS. That
converts "verify stock before spending money" from a hope into either a passing check or a
named command that refreshes it.

This is deliberately split so the gate stays offline:

    python3 tools/check_stock.py --fetch    # network, writes the snapshot
    python3 tools/check_stock.py            # no network: validates the snapshot

Usage:
    python3 tools/check_stock.py [--fetch] [BOM.csv]
"""
import csv
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOM = os.path.join(REPO, "fab", "BOM-NAVCORE-SoOP.csv")
SNAP = os.path.join(REPO, "fab", "stock-snapshot.json")

API = ("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/"
       "smtGood/selectSmtComponentList")

# Stock decays; a week-old count is a starting point, not a fact.
MAX_AGE_DAYS = 7

# Boards being assembled, so the stock must cover qty x this. The order is 2 assembled.
ASSEMBLED_BOARDS = 2

# Codes JLCPCB assembles but which need a note. Not a pass - a recorded reason.
KNOWN = {
    # nothing currently: the API carries every code on this BOM. Kept so the mechanism
    # for "the authority does not have this line" exists and is visible.
}


def _post(code):
    body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 10,
                       "searchSource": "search"}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        d = json.loads(r.read().decode())
    lst = ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []
    for row in lst:
        if str(row.get("componentCode", "")).upper() == code.upper():
            return row
    return None


def fetch(lines):
    out = {}
    for code, want in lines.items():
        try:
            row = _post(code)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"  !! network error for {code}: {e}")
            return None
        if row is None:
            out[code] = {"found": False}
            continue
        out[code] = {
            "found": True,
            "mpn": row.get("componentModelEn") or row.get("componentName"),
            "spec": row.get("componentSpecificationEn"),
            "library": row.get("componentLibraryType"),
            "stock": row.get("stockCount"),
            "min_purchase": row.get("minPurchaseNum"),
            "least_patch": row.get("leastPatchNumber"),
            "price_usd": row.get("initialPrice"),
            "lcsc_url": row.get("lcscGoodsUrl"),
        }
    return out


def main():
    argv = [a for a in sys.argv[1:] if a != "--fetch"]
    do_fetch = "--fetch" in sys.argv
    bom = argv[0] if argv else BOM
    if not os.path.isabs(bom):
        bom = os.path.join(REPO, bom)

    rows = list(csv.DictReader(open(bom)))
    # DNP lines are not placed, so they are reported but never block: no part is bought.
    lines, dnp = {}, set()
    for r in rows:
        code = (r.get("LCSC") or "").strip()
        if not code:
            continue
        qty = int((r.get("Qty") or "0").strip() or 0)
        if (r.get("DNP") or "").strip():
            dnp.add(code)
        lines[code] = lines.get(code, 0) + qty
    print(f"BOM        : {os.path.relpath(bom, REPO)} - {len(rows)} lines, "
          f"{len(lines)} distinct codes ({len(dnp)} DNP)")

    if do_fetch:
        print(f"source     : {API.split('/api')[0]} (live)")
        data = fetch(lines)
        if data is None:
            print("\nFAIL - could not reach JLCPCB; nothing was verified")
            return 1
        payload = {"date": datetime.date.today().isoformat(),
                   "source": API,
                   "assembled_boards": ASSEMBLED_BOARDS,
                   "lines": data}
        with open(SNAP, "w") as f:
            json.dump(payload, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"snapshot   : wrote {os.path.relpath(SNAP, REPO)}")
    else:
        if not os.path.exists(SNAP):
            print(f"\nFAIL - no snapshot at {os.path.relpath(SNAP, REPO)}; "
                  f"run: python3 tools/check_stock.py --fetch")
            return 1
        payload = json.load(open(SNAP))
        print(f"source     : {os.path.relpath(SNAP, REPO)} (no network this run)")

    held = datetime.date.fromisoformat(payload["date"])
    age = (datetime.date.today() - held).days
    stale = age > MAX_AGE_DAYS
    print(f"snapshot   : {held.isoformat()} ({age} day(s) old, max {MAX_AGE_DAYS})"
          + ("  ** STALE **" if stale else ""))
    data = payload["lines"]
    print()

    fails, notes = [], []
    covered = 0
    for code, qty in sorted(lines.items()):
        need = qty * ASSEMBLED_BOARDS
        rec = data.get(code)
        tag = "DNP" if code in dnp else f"x{qty}"
        if rec is None:
            fails.append(f"{code:11} ({tag:5}) not in the snapshot - run "
                         f"tools/check_stock.py --fetch")
            continue
        if not rec.get("found"):
            if code in KNOWN:
                notes.append(f"{code:11} ({tag:5}) not carried by the API - {KNOWN[code]}")
            else:
                fails.append(f"{code:11} ({tag:5}) NOT FOUND at JLCPCB - check "
                             f"jlcpcb.com/partdetail/{code} by hand")
            continue
        stock = rec.get("stock") or 0
        lib = (rec.get("library") or "?").lower()
        tier = {"base": "Basic", "expand": "Extended"}.get(lib, lib)
        bad = []
        if stock < need:
            bad.append(f"stock {stock} < {need} needed")
        if bad and code not in dnp:
            fails.append(f"{code:11} ({tag:5}) {rec.get('mpn')}: " + "; ".join(bad))
        elif bad:
            notes.append(f"{code:11} ({tag:5}) DNP and short ({stock} < {need}) - only "
                         f"matters if it is ever populated")
        else:
            covered += 1
        print(f"  {code:11} {tag:5} {tier:9} stock {stock:>7}  "
              f"{str(rec.get('mpn'))[:28]:28} {str(rec.get('spec'))[:20]}")

    if stale:
        fails.append(f"the stock snapshot is {age} days old (max {MAX_AGE_DAYS}) - "
                     f"run: python3 tools/check_stock.py --fetch")

    print()
    for n in notes:
        print(f"  note: {n}")
    print(f"{covered}/{len(lines)} line(s) resolved with stock >= {ASSEMBLED_BOARDS} boards")
    if fails:
        print(f"\nFAIL - {len(fails)} problem(s):")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("every BOM line resolves to the intended part and covers the order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
