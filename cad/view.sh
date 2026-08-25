#!/usr/bin/env bash
# Open the assembly model, working around OpenSCAD 2021.01 on Wayland.
#
# Plain `openscad drone.scad` dies with "GLEW Error: Unknown error" under a native
# Wayland session - the packaged 2021.01 predates the Wayland/Mesa combination on this
# machine. Forcing Qt onto XWayland fixes it; the GPU itself is fine (AMD, Mesa 26,
# direct rendering yes), so no software fallback is needed.
cd "$(dirname "$0")"
exec env QT_QPA_PLATFORM=xcb openscad "$@" drone.scad
