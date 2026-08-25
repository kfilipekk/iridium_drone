#!/usr/bin/env bash
# Export the board to STEP and GLB, WITH the component 3D models.
#
# THE -D IS THE WHOLE POINT. Footprints from this repo's JLC library reference their
# models as ${JLC_LIB}/packages3d/*.step, and kicad-cli does NOT inherit that path
# variable from the environment or the project. Without -D the export still succeeds,
# still prints no warning, and is still tens of megabytes - because copper, soldermask
# and silkscreen dominate the file size - but every component model is missing and the
# STEP is a bare board. File size is not the tell; count component PRODUCT() entries.
#
#   without -D :  9 products (board, copper, pads, vias, silk, mask), 44 MB
#   with    -D : 36 products (+ LQFP-100, LGA-14, JST-GH, crystal, inductors...), 68 MB
set -euo pipefail
cd "$(dirname "$0")/.."
JLC=${JLC_LIB:-$(cd .. && pwd)/.libraries/jlc.pretty}
[ -d "$JLC/packages3d" ] || { echo "no packages3d under $JLC"; exit 1; }
COMMON=(--force --subst-models --no-dnp -D "JLC_LIB=$JLC"
        --include-tracks --include-pads --include-zones
        --include-silkscreen --include-soldermask)
for fmt in step glb; do
  echo "=== $fmt"
  kicad-cli pcb export "$fmt" "${COMMON[@]}" -o "cad/NAVCORE-SoOP.$fmt" NAVCORE-SoOP.kicad_pcb
done
n=$(grep -c "PRODUCT(" cad/NAVCORE-SoOP.step)
echo "components in the STEP: $n products"
[ "$n" -gt 20 ] || { echo "FAIL: component models missing - check JLC_LIB"; exit 1; }
ls -la cad/NAVCORE-SoOP.step cad/NAVCORE-SoOP.glb
