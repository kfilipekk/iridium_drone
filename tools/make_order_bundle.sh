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

echo "regenerating BOM and CPL, all three variants ..."
python3 tools/gen_bom.py            >/dev/null
python3 tools/gen_bom.py --economic >/dev/null
python3 tools/gen_bom.py --no-fpv   >/dev/null

mkdir -p "$STAGE/gerbers"
cp fab/gerbers/* "$STAGE/gerbers/"
for f in BOM-NAVCORE-SoOP.csv CPL-NAVCORE-SoOP.csv \
         BOM-NAVCORE-SoOP-economic.csv CPL-NAVCORE-SoOP-economic.csv \
         BOM-NAVCORE-SoOP-nofpv.csv CPL-NAVCORE-SoOP-nofpv.csv; do
  if [ ! -f "fab/$f" ]; then
    echo "REFUSING: fab/$f is missing - the bundle would ship without it." >&2
    exit 1
  fi
  cp "fab/$f" "$STAGE/"
done

# The DNP list in the instructions is derived from the BOM that ships, like the placement counts.
DNPLIST=$(python3 - <<'PY'
import csv
refs = []
for r in csv.DictReader(open("fab/BOM-NAVCORE-SoOP.csv")):
    if r.get("DNP", "").strip():
        refs += [x for x in r["Designator"].split(",") if x.strip()]
print(", ".join(sorted(refs)))
PY
)
[ -n "$DNPLIST" ] || { echo "REFUSING: could not read the DNP list from the BOM" >&2; exit 1; }

STOCKLINE=$(python3 - <<'PY'
import json, os
p = "fab/stock-snapshot.json"
if not os.path.exists(p):
    print("(no snapshot on disk - run tools/check_stock.py --fetch)")
else:
    d = json.load(open(p))
    bits = []
    for code, name in (("C5271084", "STM32H743VIT6"), ("C15639", "MS5611"),
                       ("C596391", "MAX2112")):
        bits.append(f"{name} {d['lines'].get(code, {}).get('stock', '?')}")
    print(f"snapshot {d['date']}: " + ", ".join(bits))
PY
)

# gerbers must be their own zip - that is what the uploader takes
( cd "$STAGE" && zip -qr gerbers.zip gerbers && rm -rf gerbers )

cat > "$STAGE/HOW-TO-ORDER.txt" <<'TXT'
NAVCORE-SoOP - JLCPCB order, from a phone
=========================================
Upload gerbers.zip as the PCB. Do NOT unzip it first.

FABRICATION
  Layers            6          <- if the preview shows 4, STOP. The power planes
                                  are missing and the board will not work.
  Dimensions        45.0 x 47.2 mm
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
  Side              BOTH sides are populated - @@SIDES@@. Two stencils.
  BOM               BOM-NAVCORE-SoOP.csv
  CPL               CPL-NAVCORE-SoOP.csv

  Variants, if you want them instead of the default:
    *-economic.csv  U3 (second IMU) left off for hand-fitting. That is the ONLY
                    difference from the default pair.
    *-nofpv.csv     9 V VTX buck omitted. That block is DNP by default anyway, so
                    today this variant is byte-identical to the default one.

BEFORE YOU PAY - the things no offline check can confirm
  - Accept JLCPCB's free DFM review. It is the only thing that checks pad LAND
    SIZE and paste apertures; tools/check_footprints.py verifies pad count,
    package family and pitch, but not those.
  - Confirm the quote says 1 oz outer copper.
  - ABSENT BY DESIGN. The placement preview must agree - if any of these is
    placed, the wrong BOM went up:
@@DNP@@
    U11 is the CAN transceiver: pads provisioned, deliberately unfitted, so this
    board does NOT speak CAN as ordered. The rest is the 9 V VTX block, DNP
    because its switch node could not be routed on this placement.
  - SOLE SOURCE, from the dated stock snapshot in this repo. Confirm them in the
    quote tool and buy spares if the count looks tight:
      @@STOCK@@
    (MAX2112 is the tuner - nothing else in JLC's library covers 1616-1626.5 MHz
    with quadrature baseband output.)

WHAT THIS BOARD IS NOT, YET
  Ready to order is not ready to fly. tools/check_rf.py fails until the T3b
  bench measurements exist, and U8/U9 junction temperatures are computed, not
  measured. See docs/navcore-runbook.pdf, Parts 7-10 (T1-T3a), before powering anything.
TXT

# The placement counts are derived from the CPL that ships in this bundle, not typed.
TOPN=$(awk -F, 'NR>1 && tolower($4) ~ /top/' fab/CPL-NAVCORE-SoOP.csv | wc -l)
BOTN=$(awk -F, 'NR>1 && tolower($4) ~ /bottom/' fab/CPL-NAVCORE-SoOP.csv | wc -l)
if [ "$TOPN" -eq 0 ] || [ "$BOTN" -eq 0 ]; then
  echo "REFUSING: could not read placement counts from the CPL" >&2; exit 1
fi
sed -i "s/@@SIDES@@/$TOPN top, $BOTN bottom/" "$STAGE/HOW-TO-ORDER.txt"

DNP_WRAP=$(printf '%s' "$DNPLIST" | fold -s -w 62 | sed 's/^/      /')
export DNP_WRAP STOCKLINE
python3 - "$STAGE/HOW-TO-ORDER.txt" <<'PY'
import os, sys
p = sys.argv[1]
t = open(p).read()
t = t.replace("@@DNP@@", os.environ["DNP_WRAP"]).replace("@@STOCK@@", os.environ["STOCKLINE"])
open(p, "w").write(t)
PY

# A placeholder that never got substituted would ship as "@@DNP@@" to a phone at the
# checkout, so it is a refusal, not a warning.
if grep -q '@@' "$STAGE/HOW-TO-ORDER.txt"; then
  echo "REFUSING: unsubstituted placeholder left in HOW-TO-ORDER.txt:" >&2
  grep -n '@@' "$STAGE/HOW-TO-ORDER.txt" >&2
  exit 1
fi

rm -f "$OUT"
( cd "$STAGE" && zip -qr "$OLDPWD/$OUT" . )
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
unzip -l "$OUT" | tail -n +4 | head -12
