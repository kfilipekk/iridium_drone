#!/usr/bin/env bash
# Route the board with freerouting (rip-up + push-and-shove), headless.
#
# My own grid router converged at 64% because it can only ADD copper - it can never
# move an existing trace aside. Freerouting can, and takes the same board to 83%.
#
# Two findings that matter, both learned the hard way:
#
#  1. ROUTE FROM A CLEAN BOARD. Handing freerouting existing routing makes it far
#     WORSE, not better: with 13745 of my segments in the DSN, fanout escaped 46% of
#     pins, pass 1 took 53 min and produced 334 violations, and pass 2 hung for 7
#     hours. From a stripped board the same job escaped 89%, ran passes in 4 s and
#     finished in 17 min with zero violations. Strip first.
#
#  2. MOUNTING HOLES ARE NOT KEEPOUTS. KiCad exports them as circles on Edge.Cuts and
#     freerouting only reads the outermost outline as the board edge, so it happily
#     routes through them. Add explicit rule-area keepouts before exporting.
#
#  4. THE PLANES MUST BE PROTECTED, or freerouting eats them. Given all four layers
#     it put 995 mm through In1.Cu - more than any other layer - shredding the GND
#     plane it is supposed to be. fr_prepare.py marks the plane layers Specctra
#     "power" so it routes only where it should. Choose the trade with
#     FR_PROTECT_LAYERS:
#         In1.Cu,In2.Cu   both protected, 2 routing layers      (default, safest)
#         In1.Cu          reference plane solid, In2.Cu routable (balanced)
#         (empty)         nothing protected                      (the shredded board)
#
# Java 25 is a hard requirement (class file version 69). Java 21 throws
# UnsupportedClassVersionError.
set -euo pipefail
BOARD="${1:-NAVCORE-SoOP.kicad_pcb}"
WORK="${WORK:-/tmp/fr}"
JAVA="${JAVA:-/tmp/jre25/bin/java}"
JAR="${JAR:-$WORK/freerouting.jar}"
PASSES="${PASSES:-24}"

#  3. KEEP THE TOOLCHAIN OUT OF /tmp IF YOU CARE ABOUT IT. A 48-pass run and its
#     log were lost when /tmp was cleared between sessions, taking the JRE and the
#     jar with them. Both are fetched below if missing; set WORK to somewhere
#     durable to keep the intermediate DSN/SES around.

mkdir -p "$WORK"

if [ ! -x "$JAVA" ]; then
    echo "fetching a JRE 25 into ${JAVA%/bin/java} ..."
    mkdir -p "${JAVA%/bin/java}"
    curl -fsSL "https://api.adoptium.net/v3/binary/latest/25/ga/linux/x64/jre/hotspot/normal/eclipse" \
        | tar xz -C "${JAVA%/bin/java}" --strip-components=1
fi
if [ ! -f "$JAR" ]; then
    echo "fetching freerouting into $JAR ..."
    curl -fsSL -o "$JAR" \
        "https://github.com/freerouting/freerouting/releases/download/v2.3.0/freerouting-2.3.0.jar"
fi
"$JAVA" -version 2>&1 | head -1

python3 tools/fr_prepare.py "$BOARD" "$WORK/in.dsn"
"$JAVA" -Xss64m -Xmx6g -jar "$JAR" --gui.enabled=false \
        -de "$WORK/in.dsn" -do "$WORK/out.ses" -mp "$PASSES" -mt 3 -oit 2
python3 tools/fr_apply.py "$BOARD" "$WORK/out.ses"
