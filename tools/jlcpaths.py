#!/usr/bin/env python3
"""Where the JLC (LCSC/EasyEDA) part libraries live.

These are VENDORED IN THIS REPO under libraries/. They used to live in an unversioned
directory outside it, `../.libraries/`, which meant the design depended on state that
git did not hold: 30 refs - including U1, both IMUs and every JST connector - load their
footprint only from there, and J5/J9/J11 shared the one connector footprint that had no
copy anywhere else. Losing or touching that directory does not produce a warning, it
produces a board that cannot be regenerated or DRC'd at all.

Why these files and not the whole fetched library:

  libraries/symbols/jlc_parts.kicad_sym   the symbols. design.py wires parts by pin
                                          NUMBER, so a wrong pin number here is
                                          invisible to every other check.
  libraries/jlc.pretty/*.kicad_mod        the 22 footprints this board actually uses.

The 3D models under packages3d/ are deliberately NOT vendored. They are ~56 MB of STEP
data used only by export_3d.sh (visualisation) and fill_missing_models.py - no
correctness check reads them - and this repo already keeps its own 66 MB cad/*.step
exports out of git for the same reason. They stay in the external fetch directory and are
located through JLC_LIB, i.e. MODEL_ROOT below.

Overrides exist so a maintainer can still point at a fresh fetch:
    JLC_SYM  symbols file
    JLC_FP   footprint directory
    JLC_LIB  3D model root (only the two 3D tools read this)
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SYMBOLS = os.environ.get("JLC_SYM") or os.path.join(
    ROOT, "libraries", "symbols", "jlc_parts.kicad_sym")

FOOTPRINTS = os.environ.get("JLC_FP") or os.path.join(ROOT, "libraries", "jlc.pretty")

# Not in this repo - see the module docstring.
MODEL_ROOT = os.environ.get("JLC_LIB") or os.path.expanduser(
    "~/Code/Hardware/.libraries/jlc.pretty")
