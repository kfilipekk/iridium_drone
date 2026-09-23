# libraries/ — vendored JLC part data

These files used to live in `../.libraries/`, an unversioned directory outside the repo.
That made the design depend on state git did not hold, and the failure was silent and
total rather than cosmetic: **30 references load their footprint only from here**,
including `U1`, both IMUs, all four JST connectors and both oscillators. `J5`, `J9` and
`J11` share a single connector footprint that existed nowhere else. If that directory is
lost, touched or fetched into, the board cannot be regenerated or DRC'd at all — no
warning, no diff, just a project that no longer builds.

## What is versioned here

| path | what | why it is critical |
|---|---|---|
| `symbols/jlc_parts.kicad_sym` | the symbols | `design.py` wires parts by pin **number**. A wrong pin number here produces a schematic that passes ERC, a board that passes DRC, a netlist that passes `check_design`, and a scrapped fabrication run. `tools/check_symbol_pinout.py` compares every active part against KiCad's own library or the maker's datasheet. |
| `jlc.pretty/*.kicad_mod` | the 22 footprints this board uses | Pad geometry, courtyards and 3D references all come from these. Nothing else in the repo can reconstruct them. |

Total: ~296 KB. Only footprints the design references are vendored, so the directory
stays a description of this board rather than a mirror of a fetch cache.

## What is deliberately NOT here

`packages3d/*.step` — ~56 MB of 3D bodies. No correctness check reads them; they are used
only by `tools/export_3d.sh` and `tools/render_boards.sh` (visualisation). This repo
already keeps its own 66 MB `cad/*.step` exports out of git for the same reason. They stay
in the fetch directory and are located through the `JLC_LIB` environment variable, i.e.
`MODEL_ROOT` in `tools/jlcpaths.py`.

Note the consequence: a 3D export needs `JLC_LIB` pointed at a directory that has
`packages3d/`, which is **not** this one. That is intentional and `export_3d.sh` fails
loudly if the models are absent, rather than producing a bare board that still looks
plausible at 44 MB.

## Provenance and refreshing

Both were fetched from LCSC/EasyEDA via `JLC2KiCadLib` and are unmodified except by
`tools/fix_pintypes.py`, which corrects electrical pin types that EasyEDA does not carry
(ER C otherwise cannot tell a driver from a load and warns on nearly every connection).

To refresh from a new fetch: copy the files in, then run the full gate —
`python3 tools/preflight.py`. A symbol or footprint that no longer matches will fail
`check_symbol_pinout.py`, `check_footprints.py` or `check_design.py` rather than passing
quietly.

`tools/jlcpaths.py` is the single place these paths are defined; `JLC_SYM` and `JLC_FP`
override them for a one-off comparison against a fresh fetch.
