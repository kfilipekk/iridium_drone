#!/usr/bin/env python3
"""Gate the burst DSP: detection and carrier-frequency estimation from I/Q."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soop_burst


def main():
    try:
        r = soop_burst.selftest()
    except Exception as e:                      # a numeric blow-up must read as a failure
        print(f"BURST DSP CHECK FAILED - {type(e).__name__}: {e}")
        return 1

    passed, total = r["checks"]
    if r["ok"]:
        cn0 = r["snr_db"] + 10 * math.log10(soop_burst.SAMPLE_RATE)
        print(f"BURST DSP OK - {passed}/{total} assertions, p90 {r['p90_hz']:.2f} Hz < 5 Hz "
              f"at C/N0 {cn0:.0f} dB-Hz ({r['n']} bursts)")
        return 0
    print(f"BURST DSP CHECK FAILED - {passed}/{total} assertions hold")
    return 1


if __name__ == "__main__":
    sys.exit(main())
