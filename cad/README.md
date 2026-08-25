# 3D models

Three files, three levels of effort. Start at the top.

| file | what it is | opens in |
|---|---|---|
| — | the **real board**, no export needed | **KiCad's own 3D viewer** — already installed |
| `NAVCORE-SoOP.glb` | the board as a mesh | `f3d`, Blender, any glTF viewer |
| `NAVCORE-SoOP.step` | the board as CAD solids | FreeCAD, Fusion 360, OnShape |
| `drone.scad` | the **whole aircraft** — frame, ESC, board, motors, props, battery | **OpenSCAD** |

## On Linux, the easiest path needs no install at all

**KiCad 9 is already on this machine and has a 3D viewer built in.**

```bash
pcbnew NAVCORE-SoOP.kicad_pcb
```

then **View → 3D Viewer**, or just press **Alt+3**. Left-drag rotates, scroll zooms,
right-drag pans. It renders the real board with real component models, and it is always in
sync with the design — no export step to forget.

Useful things in that viewer: **Preferences → Display Options** toggles silkscreen,
soldermask and individual copper layers, and the *Raytracing* button under Preferences
gives a photo-realistic render if you want a picture for documentation.

## The whole drone

```bash
sudo apt install openscad
./cad/view.sh                  # <- use this, not `openscad drone.scad`
```

### Why the wrapper: "GLEW Error: Unknown error"

On a **Wayland** session the packaged OpenSCAD 2021.01 fails to start its GL context.
The GPU is not the problem — Mesa 26 on AMD with direct rendering works fine, and
headless CLI rendering succeeds. It is Qt picking the native Wayland platform plugin.

Tested on this machine:

| invocation | result |
|---|---|
| `openscad drone.scad` | **GLEW Error: Unknown error** |
| `QT_QPA_PLATFORM=xcb openscad drone.scad` | **works** |
| `LIBGL_ALWAYS_SOFTWARE=1 openscad drone.scad` | still fails — it is not a driver issue |

`view.sh` just sets `QT_QPA_PLATFORM=xcb` and `cd`s to the right directory, which also
avoids the other easy mistake: the file is at `NAVCORE-SoOP/cad/drone.scad`, so
`openscad cad/drone.scad` from `~/Code/Hardware` finds nothing.

Press **F5** to preview, drag to rotate, **F6** to render properly, then
**File → Export → STL**.

If you also want a quick mesh viewer for the `.glb`:

```bash
sudo apt install f3d
f3d cad/NAVCORE-SoOP.glb
```

## The whole drone: OpenSCAD

Install OpenSCAD, open `drone.scad`, press **F5**. Drag to rotate, scroll to zoom.

It is **accurate in dimension and crude in detail** — the board is a slab with a component
blob rather than real parts, which is the point. Every number is commented with where it
came from:

- `[M]` measured from the KiCad file — board size, hole pitch, component heights
- `[D]` from SpeedyBee's manual or a datasheet — ESC size, grommets
- `[A]` **assumed, and you should check it** — frame dimensions, battery size

The knobs worth touching are at the top:

```
explode        = 0;      // set to 25 to pull the stack apart
show_props     = true;   // off makes the stack easier to see
bottom_plate_w = 50;     // *** the number to check against your real frame ***
wheelbase      = 300;
```

Press **F6** to render properly, then **File → Export → STL** for anything else.

OpenSCAD prints three sanity checks to its console every time it renders:

```
stack height mm = 19.1
bottom plate must be >= 46.1 mm; it is 50
prop-to-prop gap mm = 34.3
```

Change `wheelbase` or `bottom_plate_w` to your frame's real numbers and those lines tell
you immediately whether it still fits.

## Both together

FreeCAD is not in the Debian/Ubuntu repos on this machine (`apt-cache policy freecad`
returns no candidate). Get it as a Flatpak or AppImage if you want it:

```bash
flatpak install flathub org.freecadweb.FreeCAD
```

Then import both `NAVCORE-SoOP.step` and an STL exported from `drone.scad`. FreeCAD also
reads `.scad` directly when OpenSCAD is installed alongside it.

## Regenerating

```bash
kicad-cli pcb export glb  --output cad/NAVCORE-SoOP.glb  --no-dnp NAVCORE-SoOP.kicad_pcb
kicad-cli pcb export step --output cad/NAVCORE-SoOP.step --no-dnp --subst-models NAVCORE-SoOP.kicad_pcb
```

`--no-dnp` omits `U3`, `U6` and `U7`, so the model matches the **Economic** build you are
actually ordering rather than a fully populated board.

## Verified

Rendered on OpenSCAD 2021.01 — parses and renders clean, no warnings. Pre-rendered views
are in `renders/`.

Every render prints its own sanity checks to the console:

```
ECHO: "stack height mm = 19.1"
ECHO: "bottom plate must be >= 46.1 mm; it is 50"
ECHO: "prop-to-prop gap mm = 34.332"
ECHO: "clearance above FC to top plate mm = 10.9"
```

Change `wheelbase`, `bottom_plate_w` or `top_plate_z` to your real frame's numbers and
those four lines tell you immediately whether everything still fits.

## Useful views

The default view hides the battery, because at 140 x 45 x 38 mm it covers the entire
stack. Turn things off to see past them:

```bash
# assembled, isometric
./view.sh

# plan view of the stack - the one that shows the board against the plate
./view.sh -D show_props=false -D show_top_plate=false

# exploded, to see the FC clear of the ESC
./view.sh -D explode=28

# with the battery, to check it clears the props
./view.sh -D show_battery=true
```

Command line render, if you want a picture rather than the GUI:

```bash
openscad -o iso.png --imgsize=1000,780 --camera=0,0,14,58,0,35,430 \
         --colorscheme=Tomorrow drone.scad
```
