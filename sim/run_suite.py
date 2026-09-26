#!/usr/bin/env python3
"""Run every NAVCORE-SoOP simulation and tally its assertions."""
import importlib
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from checks import Checks          # noqa: E402

MODULES = ("power", "hotplug", "pyro", "pll", "baseband", "sense", "ldo")


def run(names=None):
    """Run the named modules into one shared collector."""
    chk = Checks()
    failed = []
    for name in (names or list(MODULES)):
        print("=" * 72)
        try:
            importlib.import_module(name).main(chk)
        except Exception:                       # noqa: BLE001 - report and continue
            failed.append(name)
            traceback.print_exc()
        print()
    return chk, failed


def report(chk, failed):
    """Print the tally and the one line the gate parses."""
    n, ok = chk.n(), chk.n_ok()
    if chk.failures():
        print(f"SIM FAIL - {n - ok} of {n} assertion(s) failed:")
        for label, detail in chk.failures():
            print(f"   x {label}: {detail}")
    if failed:
        print(f"SIM FAIL - module(s) did not run: {', '.join(failed)}")
    if chk.all_ok() and not failed:
        print(f"SIM OK - {ok}/{n} assertions across {len(MODULES)} decks")
        return 0
    return 1


def main(argv):
    chk, failed = run(argv or None)
    return report(chk, failed)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
