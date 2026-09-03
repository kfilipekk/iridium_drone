#!/usr/bin/env bash
# Build a single self-contained bundle you can upload to JLCPCB from a phone.
set -euo pipefail
cd "$(dirname "$0")/.."
BOARD=NAVCORE-SoOP.kicad_pcb
OUT=fab/NAVCORE-SoOP-order-bundle.zip
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

echo "regenerating gerbers from $BOARD ..."
rm -rf fab/gerbers && mkdir -p fab/gerbers
kicad-cli pcb export gerbers --output fab/gerbers/ \
  --layers "F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" \
  --no-protel-ext "$BOARD" >/dev/null
kicad-cli pcb export drill --output fab/gerbers/ --format excellon \
  --drill-origin absolute --excellon-units mm --generate-map --map-format gerberx2 \
  "$BOARD" >/dev/null

n_cu=$(ls fab/gerbers/ | grep -c "_Cu.gbr")
if [ "$n_cu" -ne 6 ]; then
  echo "REFUSING: $n_cu copper layers exported, expected 6." >&2
  echo "A 6-layer board fabricated from 4 gerbers is a board with no planes." >&2
  exit 1
fi
echo "  $n_cu copper layers ok"

mkdir -p "$STAGE/gerbers"
cp fab/gerbers/* "$STAGE/gerbers/"
cp fab/BOM-NAVCORE-SoOP.csv fab/CPL-NAVCORE-SoOP.csv "$STAGE/"
cp fab/BOM-NAVCORE-SoOP-economic.csv fab/CPL-NAVCORE-SoOP-economic.csv "$STAGE/" 2>/dev/null || true
cp fab/BOM-NAVCORE-SoOP-nofpv.csv fab/CPL-NAVCORE-SoOP-nofpv.csv "$STAGE/" 2>/dev/null || true

# gerbers must be their own zip - that is what the uploader takes
( cd "$STAGE" && zip -qr gerbers.zip gerbers && rm -rf gerbers )

cat > "$STAGE/HOW-TO-ORDER.txt" <<'TXT'
NAVCORE-SoOP - JLCPCB order, from a phone
=========================================
Upload gerbers.zip as the PCB. Do NOT unzip it first.

FABRICATION
  Layers            6          <- if the preview shows 4, STOP. The power planes
                                  are missing and the board will not work.
  Dimensions        45.1 x 46.1 mm
  Thickness         1.6 mm
  Outer copper      1 oz       <- 0.5 oz halves every trace's current rating and
                                  invalidates tools/check_power_cut.py
  Surface finish    ENIG       <- 0402s and LGA parts want a flat finish
  Min track/space   4 mil (0.1016 mm)   should be free tier; an upcharge means
                                        the design rules drifted
  Min via / drill   0.45 / 0.20 mm
  Impedance control No

ASSEMBLY
  Quantity          5 bare PCBs, 2 assembled  (5 is the multilayer minimum,
                    2 the SMT minimum; the 3 spare bare boards are the practice
                    pieces and cost almost nothing)
  Side              BOTH sides are populated - 30 top, 65 bottom. Two stencils.
  BOM               BOM-NAVCORE-SoOP.csv
  CPL               CPL-NAVCORE-SoOP.csv

  Variants, if you want them instead of the default:
    *-economic.csv  Economic tier, U3/U6/U7 left off for hand-fitting
    *-nofpv.csv     9 V VTX buck omitted (it is DNP by default anyway)

BEFORE YOU PAY - the things no offline check can confirm
  - Accept JLCPCB's free DFM review. It is the only thing that checks pad LAND
    SIZE and paste apertures; tools/check_footprints.py verifies pad count,
    package family and pitch, but not those.
  - Confirm the quote says 1 oz outer copper.
  - U6, U7 and U18 are DNP by design. If the preview shows them placed, the
    wrong BOM went up.
  - STM32H743VIT6 (C5271084) and MS5611 (C15639) are sole-source and were thin
    at last check (314 and 1216 units). Confirm stock in the quote tool; buy
    spares if it looks tight.

WHAT THIS BOARD IS NOT, YET
  Ready to order is not ready to fly. tools/check_rf.py fails until the T3b
  bench measurements exist, and U8/U9 junction temperatures are computed, not
  measured. See docs/BUILD.md T1-T3a before powering anything.
TXT

rm -f "$OUT"
( cd "$STAGE" && zip -qr "$OLDPWD/$OUT" . )
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
unzip -l "$OUT" | tail -n +4 | head -12
