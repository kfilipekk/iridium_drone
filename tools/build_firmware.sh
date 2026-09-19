#!/usr/bin/env bash
# Build real ArduPilot firmware for this board.
set -euo pipefail

AP=${AP_DIR:-$HOME/.cache/navcore/ardupilot}
LOGS=${LOG_DIR:-$HOME/.cache/navcore/fwlogs}
VENV=${VENV_DIR:-$HOME/.cache/navcore/apvenv}
if [ ! -x "$VENV/bin/python" ]; then
    echo "=== creating the build venv at $VENV ==="
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet "empy==3.3.4" pexpect future intelhex pyserial
fi
export PATH="$VENV/bin:$PATH"
HERE=$(cd "$(dirname "$0")/.." && pwd)
BOARD=NAVCORE_SoOP
ID=9001
AP_TAG=${AP_TAG:-Copter-4.7.0}
mkdir -p "$LOGS"

[ -d "$AP" ] || { echo "no ArduPilot tree at $AP - clone it first:"; \
  echo "  git clone --depth 1 --recurse-submodules --shallow-submodules \\"; \
  echo "    https://github.com/ArduPilot/ardupilot.git $AP"; exit 1; }

echo "=== 0. pin the tree to $AP_TAG ==="
if [ "$(cd "$AP" && git describe --tags --exact-match 2>/dev/null)" != "$AP_TAG" ]; then
  ( cd "$AP" \
    && git checkout -- Tools/AP_Bootloader/board_types.txt 2>/dev/null || true
    cd "$AP" && git checkout -q "$AP_TAG" \
    && git submodule update --init --recursive --depth 1 >/dev/null 2>&1 ) \
    || { echo "  could not check out $AP_TAG"; exit 1; }
fi
echo "  $(cd "$AP" && git describe --tags --exact-match 2>/dev/null || echo detached)" \
     "-> $(cd "$AP" && grep -h THISFIRMWARE ArduCopter/version.h | cut -d'"' -f2)"

echo "=== 1. install the hwdef ==="
rm -rf "$AP/libraries/AP_HAL_ChibiOS/hwdef/$BOARD"
cp -r "$HERE/firmware/NAVCORE_SoOP" "$AP/libraries/AP_HAL_ChibiOS/hwdef/$BOARD"
echo "  $(ls "$AP/libraries/AP_HAL_ChibiOS/hwdef/$BOARD" | tr '\n' ' ')"

echo "=== 2. register the board ID (local only) ==="
BT="$AP/Tools/AP_Bootloader/board_types.txt"
grep -qE "^AP_HW_NAVCORE_SOOP\s" "$BT" \
  || printf 'AP_HW_NAVCORE_SOOP                  %s\n' "$ID" >> "$BT"
grep -E "^AP_HW_NAVCORE_SOOP\s" "$BT" | sed 's/^/  /'

cd "$AP"
echo "  python: $(command -v python3)  empy: $(python3 -c 'import em;print(em.__version__)' 2>&1)"
[ "${1:-}" = "--clean" ] && ./waf clean >/dev/null 2>&1 || true

echo "=== 3. bootloader (must come first) ==="
# Judge this on the artefact, not the exit code.
python3 Tools/scripts/build_bootloaders.py "$BOARD" > "$LOGS/bootloader.log" 2>&1 || true
if [ -f "Tools/bootloaders/${BOARD}_bl.bin" ]; then
  ls -la "Tools/bootloaders/${BOARD}_bl.bin" | sed 's/^/  ok  /'
else
  echo "  FAILED - no Tools/bootloaders/${BOARD}_bl.bin was produced"
  tail -15 "$LOGS/bootloader.log" | sed 's/^/    /'
  exit 1
fi

echo "=== 4. configure ==="
./waf configure --board "$BOARD" > "$LOGS/configure.log" 2>&1 \
  && echo "  ok" || { echo "  FAILED"; tail -25 "$LOGS/configure.log"; exit 1; }

echo "=== 5. copter ==="
./waf copter > "$LOGS/copter.log" 2>&1 \
  && echo "  ok" || { echo "  FAILED"; tail -40 "$LOGS/copter.log"; exit 1; }

sha256sum "$HERE/firmware/NAVCORE_SoOP/hwdef.dat" \
  | awk '{print $1}' > "$AP/build/$BOARD/bin/arducopter.apj.hwdef.sha256"
echo "=== 5b. hwdef digest recorded, for preflight to compare against ==="
sed 's/^/  /' "$AP/build/$BOARD/bin/arducopter.apj.hwdef.sha256"

echo "=== 6. what the hwdef processing said ==="
grep -iE "warn|error|conflict|shared|no dma|not enough|unassign|no default" \
  "$LOGS/configure.log" | sed 's/^/  /' || echo "  (nothing flagged)"

echo "=== 7. artefacts ==="
find "$AP/build/$BOARD" -maxdepth 2 \( -name '*.apj' -o -name '*.bin' -o -name '*.abin' \) \
  -printf '  %-64p %10s bytes\n' 2>/dev/null | sort

echo "=== 8. DMA map ==="
sed -n '/DMA/,/^$/p' "$LOGS/configure.log" | head -40 | sed 's/^/  /'
