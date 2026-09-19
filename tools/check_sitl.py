#!/usr/bin/env python3
"""The SITL suite is green, and it is green against the firmware that actually ships.

Usage:
    python3 tools/check_sitl.py                  # validate (no network, no SITL)
    python3 tools/check_sitl.py --record         # fold the newest run into the result
"""
import ast
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RESULT = os.path.join(REPO, "sitl", "sitl-results.json")
LOGS = os.path.join(REPO, "sitl", "logs")


def defaults_sha():
    """The parameter set the firmware ships, identified by content."""
    for p in (os.path.join(REPO, "firmware", "NAVCORE_SoOP", "defaults.parm"),
              os.path.join(REPO, "firmware", "defaults.parm")):
        if os.path.exists(p):
            return hashlib.sha256(open(p, "rb").read()).hexdigest(), p
    return None, None


AP_DIR = os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot"))
API_BIN = os.path.join(AP_DIR, "build", "sitl", "bin", "arducopter")


def sitl_binary():
    """(sha256, mtime) of the SITL binary, or (None, None) if it is not built."""
    if not os.path.exists(API_BIN):
        return None, None
    with open(API_BIN, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest(), int(os.path.getmtime(API_BIN))


def ap_head():
    """The ArduPilot revision the SITL binary was built from, or None."""
    try:
        return subprocess.run(["git", "-C", AP_DIR, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=20
                              ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def declared():
    """Scenario names declared in sitl/scenarios.py's scenarios dict."""
    src = open(os.path.join(REPO, "sitl", "scenarios.py")).read()
    body = src.split("SCENARIOS = {", 1)[1] if "SCENARIOS = {" in src else ""
    return set(re.findall(r'^\s{4}"([a-z0-9_]+)":\s*dict\(', body, re.M))


# Not every scenario is A gate, and pretending otherwise breaks the gate both WAYS.
ASSERT_KEYS = ("expect_arm_failure", "max_p95", "expect_ceiling")


def expectations():
    """{scenario: 'asserting'|'measuring'} read from scenarios.py, or {} on parse failure."""
    try:
        tree = ast.parse(open(os.path.join(REPO, "sitl", "scenarios.py")).read())
    except (OSError, SyntaxError):
        return {}
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "SCENARIOS" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for k, v in zip(node.value.keys, node.value.values):
            if not isinstance(k, ast.Constant):
                continue
            if isinstance(v, ast.Call):
                keys = {kw.arg for kw in v.keywords if kw.arg}
            elif isinstance(v, ast.Dict):
                keys = {kk.value for kk in v.keys
                        if isinstance(kk, ast.Constant) and isinstance(kk.value, str)}
            else:
                continue
            if "informational" in keys:
                out[k.value] = "measuring"
            elif keys & set(ASSERT_KEYS):
                out[k.value] = "asserting"
            else:
                out[k.value] = "undeclared"
        break
    return out


SITL_OUT = os.environ.get("OUT", "/tmp/nav/sitl")


def newest_report():
    cands = glob.glob(os.path.join(SITL_OUT, "report.json"))
    cands += glob.glob(os.path.join(LOGS, "**", "report.json"), recursive=True)
    cands = [c for c in cands if os.path.exists(c)]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def record():
    rep = newest_report()
    if not rep:
        print(f"no report.json in {SITL_OUT} or under "
              f"{os.path.relpath(LOGS, REPO)} - nothing to record. Run "
              f"sitl/run_scenarios.sh first (or set OUT to its output directory).")
        return 1
    merged = json.load(open(rep))
    sha, path = defaults_sha()
    bsha, bmtime = sitl_binary()
    rel = os.path.relpath(rep, REPO)
    out = {"source": rel if not rel.startswith("..") else rep,
           "defaults_sha256": sha,
           "defaults_path": os.path.relpath(path, REPO) if path else None,
           "sitl_binary_sha256": bsha,
           "sitl_binary_mtime": bmtime,
           "ardupilot_head": ap_head(),
           "scenarios": {}}
    for r in merged:
        name = r.get("scenario") or "?"
        out["scenarios"][name] = r.get("verdict") or r.get("error") or "NO VERDICT"
    with open(RESULT, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"recorded {len(out['scenarios'])} scenario(s) -> "
          f"{os.path.relpath(RESULT, REPO)}")
    return 0


def main():
    if "--record" in sys.argv:
        return record()

    want = declared()
    print(f"declared   : {len(want)} scenario(s) in sitl/scenarios.py")
    if not os.path.exists(RESULT):
        print(f"\nFAIL - no result at {os.path.relpath(RESULT, REPO)}. The suite has not "
              f"been run; run sitl/run_scenarios.sh, then "
              f"python3 tools/check_sitl.py --record")
        return 1

    res = json.load(open(RESULT))
    have = set(res.get("scenarios") or {})
    cur, path = defaults_sha()

    problems = []
    if want - have:
        problems.append(f"scenarios declared but absent from the result: "
                        f"{', '.join(sorted(want - have))}")
    if have - want:
        problems.append(f"scenarios in the result that no longer exist: "
                        f"{', '.join(sorted(have - want))}")

    bsha, _ = sitl_binary()
    recorded_b = res.get("sitl_binary_sha256")
    if bsha is None:
        problems.append("the SITL binary is not built, so no result can be trusted "
                        "until it is")
    elif recorded_b is None:
        problems.append("the result does not record which SITL binary produced it - "
                        "re-record with `python3 tools/check_sitl.py --record`")
    elif recorded_b != bsha:
        problems.append(
            "the result was produced by a DIFFERENT SITL binary "
            f"(recorded {str(recorded_b)[:12]}, now {bsha[:12]}). The flight logic has "
            "been rebuilt since these scenarios ran, so a green result says nothing "
            "about the binary that exists now. Re-run sitl/run_scenarios.sh")

    recorded_head = res.get("ardupilot_head")
    cur_head = ap_head()
    if recorded_head and cur_head and recorded_head != cur_head:
        problems.append(f"the ArduPilot source moved since these scenarios ran "
                        f"(recorded {recorded_head[:12]}, now {cur_head[:12]})")

    recorded_sha = res.get("defaults_sha256")
    if cur is None:
        problems.append("cannot find defaults.parm to compare against")
    elif recorded_sha != cur:
        problems.append(
            "the result was produced against a DIFFERENT defaults.parm "
            f"(recorded {str(recorded_sha)[:12]}, now {cur[:12]}) - the parameters have "
            "changed since these scenarios ran, so a green result says nothing about "
            "what ships. Re-run sitl/run_scenarios.sh")

    kind = expectations()
    if not kind:
        problems.append("cannot read scenario expectations from sitl/scenarios.py")

    # A verdict is a failure when it contradicts what the scenario declared it would do.
    bad, measuring = {}, {}
    for n, v in (res.get("scenarios") or {}).items():
        up = str(v).upper()
        k = kind.get(n)
        failed = up.startswith("FAIL") or up.startswith("UNEXPECTED")
        if k == "measuring":
            (bad if failed else measuring)[n] = v
        elif k == "asserting":
            if not up.startswith("PASS"):
                bad[n] = v
        elif k == "undeclared":
            bad[n] = (f"declares neither {'/'.join(ASSERT_KEYS)} nor informational=True, "
                      f"so this result asserts nothing: {v}")
        else:
            bad[n] = f"no expectation found in sitl/scenarios.py: {v}"
    for n, v in sorted(bad.items()):
        problems.append(f"{n}: {v}")

    print(f"result     : {os.path.relpath(RESULT, REPO)} "
          f"({len(have)} scenario(s), from {res.get('source')})")
    print(f"parameters : {'matches' if recorded_sha == cur else 'DIFFERS from'} "
          f"{os.path.relpath(path, REPO) if path else 'defaults.parm'}")
    print(f"binary     : {'matches' if recorded_b == bsha else 'DIFFERS from'} "
          f"build/sitl/bin/arducopter ({str(bsha)[:12]})")
    print(f"source     : ArduPilot {str(recorded_head or 'unrecorded')[:12]}")
    n_assert = sum(1 for n in have if kind.get(n) == "asserting")
    print(f"mechanisms : {n_assert - len([n for n in bad if kind.get(n) == 'asserting'])}"
          f"/{n_assert} asserting scenario(s) PASS (arming refusals, RTL, failsafe, "
          f"measurement canary)")
    print(f"measurement: {len(measuring)} informational scenario(s) - reported, not "
          f"gated, because they declare no pass criterion")
    for n, v in sorted(measuring.items()):
        print(f"     ~ {n:20} {str(v)[:74]}")

    if problems:
        print(f"\nFAIL - {len(problems)} problem(s):")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("\nSITL is green against the parameters that ship")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
