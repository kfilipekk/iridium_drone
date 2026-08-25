#!/usr/bin/env bash
# Export the board to STEP and GLB, with the component 3D models.
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
