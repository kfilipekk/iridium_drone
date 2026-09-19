#!/usr/bin/env bash
# Regenerate cad/renders/*.png from drone.scad, headless and reproducibly.
set -euo pipefail
cd "$(dirname "$0")"
export QT_QPA_PLATFORM=offscreen            # no display needed; see README for the Wayland note
R() { # name  camera(eye_x,eye_y,eye_z,center_x,center_y,center_z | rot form)  size  extra -D overrides
  local name=$1 cam=$2 size=$3; shift 3
  openscad -o "renders/$name.png" --imgsize="$size" --camera="$cam" --projection=p \
           --colorscheme=Tomorrow "$@" drone.scad >/dev/null 2>&1
  echo "  wrote renders/$name.png"
}
mkdir -p renders
R iso      0,0,0,55,0,35,900    1200,900
R top      0,0,0,0,0,0,800      1200,900
R front    0,0,0,90,0,0,800     1200,900
R bottom   0,0,0,180,0,0,800    1200,900
R assembly 0,0,40,60,0,30,420   1200,900   -D show_props=false -D show_top_plate=false
R exploded 0,0,60,60,0,30,520   1200,1000  -D show_props=false -D explode=28
