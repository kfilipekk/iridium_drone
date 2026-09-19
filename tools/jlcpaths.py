#!/usr/bin/env python3
"""Where the JLC (LCSC/EasyEDA) part libraries live."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SYMBOLS = os.environ.get("JLC_SYM") or os.path.join(
    ROOT, "libraries", "symbols", "jlc_parts.kicad_sym")

FOOTPRINTS = os.environ.get("JLC_FP") or os.path.join(ROOT, "libraries", "jlc.pretty")

MODEL_ROOT = os.environ.get("JLC_LIB") or os.path.expanduser(
    "~/Code/Hardware/.libraries/jlc.pretty")
