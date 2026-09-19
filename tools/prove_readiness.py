#!/usr/bin/env python3
"""Prove the readiness manifest BLOCKS, instead of trusting its docstring.

`readiness.py` claims: an unrun check, a failed tool, an ORDER_CHECK with no recorded
source, and an unclassified entry are each a blocking failure — "Proved by breaking all
four". This reproduces that proof **from outside, on synthetic inputs**, so it cannot pass
by accident of the real board being green.

Each case supplies PASSING verdicts for every gated check and rc=0 for every tool, then
breaks EXACTLY ONE thing, and asserts that exactly one prerequisite blocks and that it is
the right one. The non-blocking classes are asserted NOT to block, because a gate that
blocks on everything is as useless as one that blocks on nothing. Case 0 is the positive
control: full evidence must yield zero blockers.

WHY THIS EXISTS, and it is the whole point
------------------------------------------
The gate's job is to make "ready to order" mean something. A gate that silently stops
checking is indistinguishable from a green one by looking at its output — that is the
defect class this project keeps finding. So the gate's own blocking behaviour is tested
rather than asserted in a comment.

Run:  python3 tools/prove_readiness.py     ->  exit 0 if every claim reproduced

This does NOT touch the board, the fab outputs, or any file: it mutates an in-memory copy
of readiness.PREREQUISITES and restores it between cases.

NOTE on the counts: nothing below asserts a literal number of prerequisites. The manifest
owns that number and it grows; asserting "43" would make this harness fail every time
something is added, which trains people to edit the test instead of reading it. The
property asserted is always "exactly the right one blocked".
"""
import copy
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import readiness  # noqa: E402

ORIG = copy.deepcopy(readiness.PREREQUISITES)
GATED, ORDER_CHECK = readiness.GATED, readiness.ORDER_CHECK

ok = True


def check(label, cond, detail=""):
    global ok
    ok = ok and cond
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")


def fresh():
    readiness.PREREQUISITES[:] = copy.deepcopy(ORIG)


def gated_tools():
    return [p["tool"] for p in ORIG if p["cls"] == GATED and "tool" in p]


def passing_checks():
    """A verdict per gated check, as a real run would supply."""
    return [("x", p["check"], "PASS", "") for p in ORIG
            if p["cls"] == GATED and "check" in p]


def all_tools_pass():
    return {t: 0 for t in gated_tools()}


def blockers(rep):
    return sorted(p["id"] for p, _ in rep["blocking"])


def reasons(rep, pid):
    return [w for p, w in rep["blocking"] if p["id"] == pid]


print("=== 0. absence of EVIDENCE is not a pass ===")
fresh()
none = readiness.evaluate([], {})
all_gated = sorted(p["id"] for p in ORIG if p["cls"] == GATED)
check("no evidence at all -> EVERY gated prerequisite blocks, tool-backed included",
      blockers(none) == all_gated and len(all_gated) > 0,
      f"{len(blockers(none))} blocking, {len(all_gated)} gated")
clean = readiness.evaluate(passing_checks(), all_tools_pass())
check("every check PASS + every tool rc=0 -> NOTHING blocks (positive control)",
      clean["blocking"] == [], f"blocking={blockers(clean)}")

print("\n=== 1. an UNRUN tool is a failure, not a skip ===")
fresh()
partial = {t: 0 for t in gated_tools() if t != "check_topology.py"}
rep = readiness.evaluate(passing_checks(), partial)
check("omitting one tool blocks exactly one prerequisite", len(blockers(rep)) == 1,
      f"blocking={blockers(rep)}")
check("and it is that tool's", reasons(rep, "topology.externals") ==
      ["check_topology.py was never run"], str(reasons(rep, "topology.externals")))
check("a tool that RAN and passed is credited, not blocked",
      not reasons(rep, "design.netlist") and not reasons(rep, "fab.bundle"))

print("\n=== 2. a tool that EXITED NONZERO is a failure ===")
fresh()
bad = all_tools_pass()
bad["check_power_cut.py"] = 3
rep = readiness.evaluate(passing_checks(), bad)
check("a nonzero exit blocks exactly one prerequisite", len(blockers(rep)) == 1,
      f"blocking={blockers(rep)}")
check("and reports the exit code", reasons(rep, "elec.current") ==
      ["check_power_cut.py exited 3"], str(reasons(rep, "elec.current")))

print("\n=== 3. a FAILED check blocks, a WARN does not ===")
fresh()
rows = passing_checks() + [("fabrication", "DRC errors", "FAIL", "3 errors"),
                           ("fabrication", "ERC clean", "WARN", "2 warnings")]
rep = readiness.evaluate(rows, all_tools_pass())
check("FAIL on 'DRC errors' blocks fab.drc", len(blockers(rep)) == 1 and
      reasons(rep, "fab.drc") == ["check 'DRC errors' failed"], f"blocking={blockers(rep)}")
check("WARN on a gated check does NOT block", not reasons(rep, "fab.erc"))

print("\n=== 4. an ORDER_CHECK with no recorded source blocks ===")
fresh()
readiness.PREREQUISITES.append(dict(id="order.synthetic", cls=ORDER_CHECK,
                                    claim="a fact that must be confirmed before paying",
                                    why="synthetic"))
rep = readiness.evaluate(passing_checks(), all_tools_pass())
check("an unconfirmed ORDER_CHECK blocks", len(blockers(rep)) == 1 and
      reasons(rep, "order.synthetic") == ["not confirmed yet"], f"blocking={blockers(rep)}")
readiness.PREREQUISITES[-1]["state"] = {"date": "2026-09-19", "source": "synthetic"}
rep = readiness.evaluate(passing_checks(), all_tools_pass())
check("...and stops blocking once a dated source is recorded", rep["blocking"] == [])

print("\n=== 5. an UNCLASSIFIED entry blocks - the manifest cannot silently shrink ===")
fresh()
readiness.PREREQUISITES.append(dict(id="mystery.thing", cls="TOTALLY_NEW",
                                    claim="something nobody classified"))
rep = readiness.evaluate(passing_checks(), all_tools_pass())
check("an unknown class blocks", len(blockers(rep)) == 1 and
      "unclassified class" in " ".join(reasons(rep, "mystery.thing")),
      str(reasons(rep, "mystery.thing"))[:80])

print("\n=== 6. staleness blocks once it expires ===")
fresh()
prereq = dict(id="order.stale", cls=GATED, tool="check_stock.py", claim="synthetic",
              max_age_days=7, state={"date": "2026-08-01", "source": "synthetic"})
readiness.PREREQUISITES.append(prereq)
today = datetime.date(2026, 9, 19)
rep = readiness.evaluate(passing_checks(), all_tools_pass(), today=today)
check("a stale dated result blocks", len(blockers(rep)) == 1 and
      reasons(rep, "order.stale") == ["recorded 2026-08-01, 49 days old (max 7)"],
      str(reasons(rep, "order.stale")))
prereq["state"]["date"] = "2026-09-18"
rep = readiness.evaluate(passing_checks(), all_tools_pass(), today=today)
check("a 1-day-old result does not block", rep["blocking"] == [])

print("\n=== 7. the non-blocking classes must NOT block ===")
fresh()
rep = readiness.evaluate([], {})
soft = {p["id"] for p in ORIG if p["cls"] != GATED}
check("no ADVISORY/BENCH/ORDER_ACTION/FLY entry ever blocks",
      not (set(blockers(rep)) & soft), f"intersection={sorted(set(blockers(rep)) & soft)}")
check("every gated entry has a tool= or check=",
      all(("tool" in p) or ("check" in p) for p in ORIG if p["cls"] == GATED))

print("\n=== 8. the verdict string is DERIVED from the walk ===")
fresh()
blocked = readiness.evaluate([], {})
clear = readiness.evaluate(passing_checks(), all_tools_pass())
check("blocking -> 'NOT READY TO ORDER'", "NOT READY TO ORDER" in readiness.render(blocked))
check("clear -> 'READY TO ORDER'", "READY TO ORDER - all" in readiness.render(clear))
check("the blocked verdict names the count it is short by",
      f"{len(blocked['blocking'])} of {len(ORIG)}" in readiness.render(blocked))
check("the clear verdict counts the gated entries it proved",
      f"all {len([p for p in ORIG if p['cls'] == GATED])} gated" in readiness.render(clear))

fresh()
print(f"\n{'ALL CLAIMS REPRODUCED' if ok else 'SOME CLAIMS DID NOT REPRODUCE'}")
print("(This proves the manifest blocks. It says nothing about whether the BOARD is good -")
print(" that is preflight's job, and the two are independent on purpose.)")
sys.exit(0 if ok else 1)
