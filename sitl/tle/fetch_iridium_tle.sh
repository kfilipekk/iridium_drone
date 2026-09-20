#!/usr/bin/env bash
# Refresh the vendored Iridium NEXT TLE catalogue used by tools/soop_solver.py.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$here/iridium-next.tle"
url="https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle"

body="$(curl -fsS "$url" | tr -d '\r')"
n="$(printf '%s\n' "$body" | grep -c '^1 ')"
if [ "$n" -lt 60 ]; then
    echo "REFUSED: CelesTrak returned $n satellites, expected the full ~80-satellite" >&2
    echo "constellation. Writing a short catalogue would silently narrow the geometry." >&2
    exit 1
fi

{
    printf '# iridium-NEXT TLE catalogue - fetched %s UTC from CelesTrak\n' "$(date -u +%Y-%m-%dT%H:%M)"
    printf '# %s objects. Source: %s\n' "$n" "$url"
    printf '%s\n' "$body"
} > "$out"

echo "wrote $n satellites to $out"
