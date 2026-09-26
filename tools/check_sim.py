#!/usr/bin/env python3
"""Gate wrapper around the SPICE suite in sim/ (see sim/run_suite.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "sim"))

import run_suite                                   # noqa: E402


def main():
    chk, failed = run_suite.run()
    return run_suite.report(chk, failed)


if __name__ == "__main__":
    sys.exit(main())
