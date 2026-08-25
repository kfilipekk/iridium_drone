#!/usr/bin/env bash
# Open the assembly model, working around OpenSCAD 2021.01 on Wayland.
cd "$(dirname "$0")"
exec env QT_QPA_PLATFORM=xcb openscad "$@" drone.scad
