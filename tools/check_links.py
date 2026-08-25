#!/usr/bin/env python3
"""
Buying links: recoverability offline, liveness online.

WHY THIS IS NOT A LINK CHECKER. "Does this URL return 200 today" is the property next to
the one that matters, and for this project's biggest supplier it is not even measurable:
AliExpress item pages render client-side, so curl and any HTML-to-text fetch get a ~76 KB
JavaScript shell with no title and no product data. A dead listing and a live one are
byte-similar. Worse, a listing can return 200 and sell something else entirely - the
seller relisted, the variant went away - and no status code says so.

So the offline half asserts what actually survives:

  1. Every FRAGILE link (an AliExpress /item/ URL) has a fallback SEARCH TERM, because
     those listings die routinely and a search term is what lets a reader re-find the
     part in two years. This is the property that makes the order sheet durable.
  2. No GEO-GATED domains. aliexpress.us 302s to a login/cookie gate and de.aliexpress
     is a German gateway; this project prices in GBP and buys from hobbyrc.co.uk, so
     both are wrong for its reader. Verified: aliexpress.com/item/<us-id> redirects to
     the global id, and global = us_id - 2**51 reproduces it exactly.
  3. No legacy /i/ URL form in the live docs (docs/HISTORY.md is exempt - it records
     superseded research and the README says nothing there is current).

The online half (--net) is a genuine liveness test for everything that CAN be tested,
and it reports AliExpress separately rather than pretending a 200 means anything.

    python3 tools/check_links.py           # offline, gateable
    python3 tools/check_links.py --net     # also hit the network
"""
import argparse, csv, os, re, sys, subprocess

DOCS = ("docs/BUYING.md", "docs/BUILD.md", "docs/SENSORS.md", "README.md",
        "docs/HARDWARE.md", "docs/BENCHMARK.md")
PARTS = "docs/PARTS.csv"
# Records superseded research; the README says nothing in it is current, so its dead
# Mark4 links are evidence of what was rejected, not instructions to a buyer.
EXEMPT = ("docs/HISTORY.md",)

GEO_GATED = ("aliexpress.us", "de.aliexpress.")
LEGACY_FORM = re.compile(r"aliexpress\.com/i/\d+")
URL_RE = re.compile(r"https?://[^\s\)\]\"'>,|]+")

# Sites that serve a 403 to anything without a browser fingerprint. Not dead - checked
# by hand. Listing them keeps --net honest instead of noisy.
BOT_BLOCKED = ("arducam.com", "ebay.com", "mdpi.com")


def urls_in(path):
    try:
        s = open(path).read()
    except FileNotFoundError:
        return []
    return [(m.group(0).rstrip(".,;>"), s[:m.start()].count("\n") + 1)
            for m in URL_RE.finditer(s)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", action="store_true", help="also test liveness over HTTP")
    a = ap.parse_args()
    fails, warns = [], []

    # ---------------------------------------------------------- 1. fallback terms ---
    rows = list(csv.DictReader(open(PARTS)))
    fragile = 0
    print("=== fragile links have a fallback search term ===")
    for r in rows:
        link = (r.get("Link") or "").strip()
        fb = (r.get("Search term if the link dies") or "").strip()
        if "aliexpress" in link and ("/item/" in link or "/i/" in link):
            fragile += 1
            if not fb:
                fails.append(f"{r['Item'][:50]}: AliExpress item link with NO fallback "
                             f"search term - when it dies the part is unfindable")
    print(f"  {fragile} AliExpress item link(s); "
          f"{fragile - len([f for f in fails])} with a fallback term")
    if not fails:
        print("  ok   every fragile link is recoverable from its search term")

    # ------------------------------------------------------------- 2. geo gating ---
    print("\n=== no geo-gated or legacy link forms in the live docs ===")
    geo = []
    for path in (PARTS,) + DOCS:
        for u, line in urls_in(path):
            if any(g in u for g in GEO_GATED):
                geo.append(f"{path}:{line} {u}")
            if LEGACY_FORM.search(u):
                geo.append(f"{path}:{line} legacy /i/ form: {u}")
    for g in geo:
        fails.append(f"geo-gated or legacy link: {g}")
    print(f"  ok   none found" if not geo else f"  {len(geo)} found")
    print(f"  note {', '.join(EXEMPT)} exempt - superseded research, not a buying list")

    # ------------------------------------------------------------- 3. liveness ---
    if a.net:
        print("\n=== liveness (--net) ===")
        seen = {}
        for path in (PARTS,) + DOCS:
            for u, line in urls_in(path):
                seen.setdefault(u, f"{path}:{line}")
        ali = [u for u in seen if "aliexpress" in u]
        other = [u for u in seen if "aliexpress" not in u]
        ua = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        for u in sorted(other):
            try:
                out = subprocess.run(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                     "-A", ua, "-L", "--max-time", "25", u],
                    capture_output=True, text=True, timeout=40).stdout.strip()
            except Exception:
                out = "ERR"
            if out.startswith("2"):
                continue
            if any(b in u for b in BOT_BLOCKED) and out == "403":
                print(f"  note 403 (bot-blocked, verified by hand): {u}")
            else:
                fails.append(f"dead link {out}: {u}  ({seen[u]})")
                print(f"  FAIL {out}  {u}")
        print(f"  {len(other)} non-AliExpress link(s) tested")
        print(f"  note {len(ali)} AliExpress link(s) NOT liveness-tested - their pages "
              f"render client-side, so a 200 proves nothing. Recoverability is asserted "
              f"offline instead.")

    print()
    for f in fails:
        print(f"  FAIL {f}")
    for w in warns:
        print(f"  warn {w}")
    print(f"\n{'FAIL' if fails else 'PASS'} - {len(fails)} problem(s), {len(warns)} warning(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
