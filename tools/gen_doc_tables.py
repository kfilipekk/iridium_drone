#!/usr/bin/env python3
"""Regenerate the buy list in docs/navcore-runbook.tex from docs/PARTS.csv."""
import argparse
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
TEX_ORDER_BEGIN = "% BEGIN GENERATED ORDER"
TEX_ORDER_END = "% END GENERATED ORDER"


STAGES = [
    ("A1", "The board, and its bench",
     "Power it, flash it, prove it - no aircraft. Runbook Parts 7-10 (T1-T3a)."),
    ("A2", "Iridium navigation, no aircraft",
     "The receive chain the board cannot supply, and the bench reference receiver "
     "for T3b step 1. The tuner (U13) is on the board; this is what feeds it."),
    ("B1", "The aircraft - minimum to fly on GPS",
     "Frame, propulsion, radio, GPS, fasteners, looms. Every optional sensor ships "
     "disabled, so nothing in B2 is needed for a GPS flight."),
    ("B2", "Aircraft sensors and payload - optional",
     "`RNGFNDn_TYPE` and `PRX1_TYPE` ship at 0; enable each one at the bench after it "
     "is fitted. The +5 V rail cannot carry all of these at once - "
     "`check_order.py modules` prints the budget."),
]


def _parts():
    import csv
    rows = list(csv.DictReader(open(REPO / "docs" / "PARTS.csv")))
    cost_key = next(k for k in rows[0] if "USD" in k or "Indicative" in k)

    def money(r):
        try:
            return float(r[cost_key] or 0)
        except ValueError:
            return 0.0
    return rows, money


def _tex(s):
    """Escape a CSV cell for LaTeX."""
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                 ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")):
        s = s.replace(a, b)
    return s


def runbook_order():
    """The same staged list as a LaTeX longtable."""
    rows, money = _parts()
    buy = [r for r in rows if r["Status"].strip() in ("TO BUY", "BUY", "PRINT")]
    have = [r for r in rows if r["Status"].strip() == "HAVE"]
    stage_of = lambda r: (r.get("Stage") or "-").strip()
    out = []
    total = 0.0
    for code, name, blurb in STAGES:
        grp = [r for r in buy if stage_of(r) == code]
        own = [r for r in have if stage_of(r) == code]
        if not grp and not own:
            continue
        sub = sum(money(r) for r in grp)
        total += sub
        out += [r"\subsubsection*{" + _tex(f"{code} --- {name}") + r"} " +
                _tex(f"{len(grp)} lines, about GBP {sub:.0f}."),
                _tex(blurb.replace("`", "")), "",
                r"\begin{longtable}{@{}P{0.50\textwidth}P{0.12\textwidth}rP{0.22\textwidth}@{}}",
                r"\toprule", r"\textbf{Item} & \textbf{Qty} & \textbf{GBP} & \textbf{Source} \\ \midrule", r"\endhead",
                r"\bottomrule", r"\endfoot"]
        for r in grp:
            out.append(f"{_tex(r['Item'])} & {_tex(r['Qty'])} & {money(r):.0f} & {_tex(r['Source'])} \\\\")
        out.append(r"\end{longtable}")
        if own:
            out.append(_tex("Already have: " + ", ".join(r["Item"] for r in own) + "."))
        out.append("")
    out.append(_tex(f"Total, everything to buy: about GBP {total:.0f}. ") +
               r"Generated from \file{docs/PARTS.csv} by \file{tools/gen\_doc\_tables.py}; " +
               r"every row's reasoning, link and provenance is in the CSV.")
    return "\n".join(out)


def _splice(path, begin, end, body, what, check):
    text = path.read_text()
    if begin not in text or end not in text:
        print(f"FAIL: {path} has no {begin} / {end} markers")
        return 1, text
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    new = f"{head}{begin}\n{body}\n{end}{tail}"
    if new == text:
        print(f"{what} is current")
        return 0, text
    if check:
        print(f"FAIL: {path.name} {what} is stale - run tools/gen_doc_tables.py")
        return 1, text
    path.write_text(new)
    print(f"rewrote the {what} in {path}")
    return 0, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    return _splice(REPO / "docs" / "navcore-runbook.tex", TEX_ORDER_BEGIN, TEX_ORDER_END,
                   runbook_order(), "runbook buy list", args.check)[0]


if __name__ == "__main__":
    raise SystemExit(main())
