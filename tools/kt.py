"""Puts kicad-tools, the shared KiCad scripts, on the path: $KICAD_TOOLS, else ~/Code/kicad-tools."""
import os, sys

ROOT = os.path.expanduser(os.environ.get("KICAD_TOOLS", "~/Code/kicad-tools"))
if not os.path.isdir(os.path.join(ROOT, "kicadtools")):
    raise SystemExit(f"no kicad-tools at {ROOT}: clone it there or set KICAD_TOOLS")
os.environ.setdefault("KICAD_PROJECT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.append(ROOT)
