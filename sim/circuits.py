"""Load `tools/design.py` as the single source of truth for the simulations.

Every deck here reads its component values, rail voltages and load currents from
the design module, so a sim cannot drift from the board it is meant to describe.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def design():
    if os.path.join(_ROOT, "tools") not in sys.path:
        sys.path.insert(0, os.path.join(_ROOT, "tools"))
    import design as d
    return d


_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "R": 1.0}


def value(s):
    """Parse a schematic value string to a number in base SI units.

    Handles both forms: '10k', '100n', and the infix style '4k7' = 4700.
    A trailing unit letter (H, F) is ignored.
    """
    s = s.strip().rstrip("HF")
    i = 0
    while i < len(s) and (s[i].isdigit() or s[i] == "."):
        i += 1
    num, rest = s[:i], s[i:]
    if not rest:
        return float(num)
    mult = _PREFIX[rest[0]]
    tail = rest[1:]
    return (float(num) + float(tail) / 10 ** len(tail)) * mult if tail else float(num) * mult


def val(ref, d=None):
    """The value string of a component by reference (e.g. '10u')."""
    d = d or design()
    return d.COMPONENTS[ref][2]
