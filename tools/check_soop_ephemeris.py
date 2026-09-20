#!/usr/bin/env python3
"""Gate the real Iridium ephemeris: SGP4 + TLE, with the TEME->ECEF frame conversion."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soop_solver


def main():
    try:
        r = soop_solver.ephemeris_test()
    except RuntimeError as e:
        print(f"EPHEMERIS CHECK FAILED - {e}")
        return 1
    except Exception as e:                       # a malformed catalogue, a bad TLE
        print(f"EPHEMERIS CHECK FAILED - {type(e).__name__}: {e}")
        return 1

    passed, total = r["checks"]
    med = r["median_m"]
    if r["ok"]:
        print(f"EPHEMERIS OK - {passed}/{total} assertions on {r['n_sats']} real "
              f"satellites" + (f", {med:.0f} m median recovery at 5 Hz / 60 bursts"
                               if med is not None else ""))
        return 0
    print(f"EPHEMERIS CHECK FAILED - {passed}/{total} assertions hold")
    return 1


if __name__ == "__main__":
    sys.exit(main())
