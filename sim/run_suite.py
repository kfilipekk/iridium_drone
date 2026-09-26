#!/usr/bin/env python3
#run every NAVCORE-SoOP simulation and print its report
import importlib
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

MODULES = ("power", "hotplug", "pyro", "pll", "baseband")


def main(argv):
    names = argv or list(MODULES)
    failed = []
    for name in names:
        print("=" * 72)
        try:
            mod = importlib.import_module(name)
            mod.main()
        except Exception:                       # noqa: BLE001 - report and continue
            failed.append(name)
            traceback.print_exc()
        print()
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print("all simulations ran")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
