#!/usr/bin/env python3
"""Record sitl/sitl-results.json from a fresh scenario run."""
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT = os.path.join(REPO, "sitl", "sitl-results.json")
DEFAULTS = os.path.join(REPO, "firmware", "NAVCORE_SoOP", "defaults.parm")
AP = os.environ.get("AP_DIR", os.path.expanduser("~/.cache/navcore/ardupilot"))
SITL_BIN = os.path.join(AP, "build/sitl/bin/arducopter")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if len(sys.argv) != 2:
        print("usage: record_sitl_result.py <report.json>")
        return 2
    report = sys.argv[1]
    if not os.path.exists(report):
        print(f"FAILED - no report at {report}")
        return 1
    if not os.path.exists(SITL_BIN):
        print(f"FAILED - no SITL binary at {SITL_BIN}")
        return 1

    scenarios = {}
    for r in json.load(open(report)):
        name = r.get("scenario")
        scenarios[name] = r.get("verdict") or f"ERROR - {r.get('error')}"

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=AP,
                          capture_output=True, text=True).stdout.strip()

    out = {
        "ardupilot_head": head,
        "defaults_path": os.path.relpath(DEFAULTS, REPO),
        "defaults_sha256": sha256_file(DEFAULTS),
        "scenarios": scenarios,
        "sitl_binary_mtime": int(os.path.getmtime(SITL_BIN)),
        "sitl_binary_sha256": sha256_file(SITL_BIN),
        "source": report,
    }
    json.dump(out, open(RESULT, "w"), indent=2)
    print(f"recorded {len(scenarios)} scenario(s) to {os.path.relpath(RESULT, REPO)}")
    print(f"  binary sha256 {out['sitl_binary_sha256'][:12]}, "
          f"defaults sha256 {out['defaults_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
