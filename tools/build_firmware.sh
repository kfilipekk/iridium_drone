#!/usr/bin/env bash
# Build real ArduPilot firmware for this board.
#
# This is the only test that actually proves the hwdef works. tools/check_hwdef.py
# checks that the hwdef describes the netlist; it cannot tell you whether ChibiOS can
# assign a DMA stream to every peripheral you asked for, whether a pin really has the
# alternate function you claimed, or whether the flash layout is self-consistent. Those
# only surface when chibios_hwdef.py runs and the linker script gets written.
#
# The ArduPilot tree is cached outside this repo - a 1.5 GB source tree has no business
# being vendored into a hardware repository.
#
# The tree is PINNED to a release tag. Building against whatever master happens to be
# that day is not reproducible, and it is not even safe: parameter names move between
# releases. RNGFND1_MIN/MAX are metres in 4.7 and in master, but were RNGFND1_MIN_CM /
# MAX_CM in 4.5 - and ArduPilot silently ignores a default parameter whose name it does
# not recognise, so a board built against the wrong tree boots looking fine and is
# quietly unconfigured. tools/check_params.py checks defaults.parm against THIS tag.
#
# Board ID 9001 is registered LOCALLY in the clone so the build can resolve
# AP_HW_NAVCORE_SOOP. That is not upstream registration; it must still be requested from
# ArduPilot before this design is shared or sold.
#
# The bootloader is built FIRST and on purpose. ArduPilot embeds the bootloader binary
# into the main firmware when AP_BOOTLOADER_FLASHING_ENABLED is on, so `waf configure`
# fails outright until Tools/bootloaders/<board>_bl.bin exists. That is not an error in
# the hwdef - it is the required order.
#
# Full logs are kept per stage; the tails printed here are a summary, not the record.
#
# Usage:  bash tools/build_firmware.sh [--clean]
set -euo pipefail

# Cached OUTSIDE /tmp on purpose. This tree, the venv, the SITL logs and every
# board backup taken during the connector-rotation surgery were all lost when /tmp was
# cleared mid-session - the same trap route_freerouting.sh already warns about after
# losing a 48-pass run, its log, the JRE and the jar. AP_DIR still overrides.
AP=${AP_DIR:-$HOME/.cache/navcore/ardupilot}
LOGS=${LOG_DIR:-$HOME/.cache/navcore/fwlogs}
# ArduPilot's DroneCAN dsdl compiler needs empy 3.3.4 exactly, and this machine's system
# Python is externally managed. A venv with --system-site-packages keeps the distro
# packages visible while letting empy be pinned. Put it first on PATH so ./waf's
# `#!/usr/bin/env python3` picks it up.
VENV=${VENV_DIR:-$HOME/.cache/navcore/apvenv}
# Create the venv rather than assume it. Previously this line only PREPENDED the venv to
# PATH if it happened to exist, so once the old one was lost the build silently fell back
# to the system python, and the only sign was a ModuleNotFoundError for 'em' buried in
# the stage-2 banner - forty lines above the failure it actually caused. ArduPilot pins
# empy to 3.3.4; 4.x renamed the API and does not work.
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
# Judge this on the artefact, not the exit code. build_bootloaders.py prints
# "Build failed" and "Failed boards: [...]" and still exits 0, so the old `&& echo ok`
# reported success for a bootloader that was never built - and the real complaint only
# surfaced two stages later as a configure error that reads like an hwdef fault.
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

echo "=== 6. what the hwdef processing said ==="
grep -iE "warn|error|conflict|shared|no dma|not enough|unassign|no default" \
  "$LOGS/configure.log" | sed 's/^/  /' || echo "  (nothing flagged)"

echo "=== 7. artefacts ==="
find "$AP/build/$BOARD" -maxdepth 2 \( -name '*.apj' -o -name '*.bin' -o -name '*.abin' \) \
  -printf '  %-64p %10s bytes\n' 2>/dev/null | sort

echo "=== 8. DMA map ==="
sed -n '/DMA/,/^$/p' "$LOGS/configure.log" | head -40 | sed 's/^/  /'
