#!/usr/bin/env python3
"""Gate ready-to-FLY on the T3b RF self-interference measurements."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import design

SPEC = design.RF_BENCH
REPO = pathlib.Path(__file__).parent.parent
RESULTS = REPO / SPEC["results"]


def template() -> str:
    return json.dumps(
        {"_note": "T3b per the runbook (docs/navcore-runbook.tex). Record steps IN ORDER - the ordering is the "
                  "experiment: each degradation names its own culprit.",
         "_band_mhz": list(SPEC["band_mhz"]),
         **{name: {f: None for f in SPEC["fields"]} | {"_what": what, "_isolates": why}
            for name, what, why in SPEC["steps"]}},
        indent=2)


def main() -> int:
    if "--template" in sys.argv:
        print(template())
        return 0

    if not RESULTS.exists():
        print(f"NOT READY TO FLY - {SPEC['results']} does not exist.\n")
        print("The four T3b measurements have not been made. This is expected before the")
        print("hardware arrives, and is NOT an order blocker - preflight.py governs that.\n")
        for i, (name, what, why) in enumerate(SPEC["steps"], 1):
            print(f"  {i}. {name:16s} {what}")
            print(f"     {'':16s} -> {why}")
        print(f"\nStart with:  python3 {pathlib.Path(__file__).name} --template "
              f"> {SPEC['results']}")
        print("Step 1 needs no aircraft - do it the week the SDR parts arrive.")
        return 1

    data = json.loads(RESULTS.read_text())
    problems, baseline, prev = [], None, None

    for name, _what, _why in SPEC["steps"]:
        step = data.get(name)
        if not isinstance(step, dict):
            problems.append(f"{name}: missing from {SPEC['results']}")
            continue
        missing = [f for f in SPEC["fields"] if step.get(f) is None]
        if missing:
            problems.append(f"{name}: not measured - {', '.join(missing)}")
            continue

        bursts = step["bursts_per_min"]
        if name == "baseline":
            baseline = prev = bursts
            prev = (name, bursts)
            if not baseline:
                problems.append("baseline: 0 bursts/min - the receive chain does not work "
                                "at all, and nothing downstream of this is meaningful")
            continue
        if baseline:
            frac = bursts / baseline
            floor = SPEC["min_fraction_of_baseline"]
            verdict = "ok  " if frac >= floor else "FAIL"
            print(f"  {verdict} {name:16s} {bursts:6.1f}/min = {frac:5.1%} of baseline "
                  f"(floor {floor:.0%})")
            if frac < floor:
                problems.append(
                    f"{name}: {frac:.0%} of baseline, below the {floor:.0%} floor. "
                    f"Culprit: {dict((s[0], s[2]) for s in SPEC['steps'])[name]}")

            if prev is not None and bursts > prev[1] * 1.1:
                problems.append(
                    f"{name}: {bursts:.1f}/min is HIGHER than {prev[0]} at {prev[1]:.1f} - "
                    f"impossible if the run was cumulative. Re-measure both in one "
                    f"session, same position, same sky; do not attribute a culprit "
                    f"from this data")
            prev = (name, bursts)

    if problems:
        print("\nNOT READY TO FLY:")
        for p in problems:
            print(f"  - {p}")
        if any("below the" in p for p in problems):
            print("\nMitigations, cheapest first:")
            for m in SPEC["mitigations"]:
                print(f"  - {m}")
        return 1

    print(f"\nRF bench PASS - all {len(SPEC['steps'])} T3b steps measured, each within "
          f"{SPEC['min_fraction_of_baseline']:.0%} of baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
