#!/usr/bin/env bash
#refresh the vendored Iridium NEXT TLE catalogue used by tools/soop_solver.py
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$here/iridium-next.tle"
sup="https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=iridium&FORMAT=tle"
pub="https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle"

count() { printf '%s\n' "$1" | grep -c '^1 ' || true; }

url="$sup"
body="$(curl -fsS "$url" | tr -d '\r' || true)"
n="$(count "$body")"
if [ "$n" -lt 60 ]; then
    echo "supplemental (Iridium-derived) sets unavailable ($n satellites); using public TLEs" >&2
    url="$pub"
    body="$(curl -fsS "$url" | tr -d '\r')"
    n="$(count "$body")"
fi
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

echo "wrote $n satellites to $out from $url"
