# Contributing

## Checking the board

```bash
python3 tools/preflight.py     # ~15 min, needs KiCad's pcbnew Python module
```

It runs every check and ends with a summary:

- **READY TO ORDER** – everything that can be checked without hardware passes.
- **NOT READY TO FLY** – bench measurements that need a real board (T3a–T3d in the runbook).
- **NOT BUILT YET** – firmware still to be written.

Warnings are listed with their reasons in `tools/readiness.py`.

## Where things are

| | |
|---|---|
| Components, nets, board outline, pinout | `tools/design.py` |
| Open issues and accepted warnings | `docs/KNOWN-ISSUES.md` |
| What to buy | `docs/PARTS.csv` |
| Ordering, assembly and bring-up | `docs/navcore-runbook.pdf` (source: `.tex`) |
| What each script does | `tools/README.md` |

## Generated files

Edit the source and regenerate rather than editing these by hand:

- `NAVCORE-SoOP.kicad_sch` – `tools/gen_sch.py` from `design.py`.
- `NAVCORE-SoOP.kicad_pcb` – edited in KiCad. The pcbnew scripts used to place, route and
  tidy it live in a separate toolkit (`kicad-tools`); this repo keeps the checks.
- `firmware/NAVCORE_SoOP/hwdef.dat` and `defaults.parm` – `tools/gen_hwdef.py`.
- `fab/` – `tools/make_order_bundle.sh`.
- `docs/navcore-runbook.pdf` – `tectonic docs/navcore-runbook.tex`.

## Before committing

Run `tools/preflight.py` and make sure the tree is clean. If you add a check, make sure it
can fail: run it once against a board with the fault in it. `tools/fault_injection.py`
proves every gated check still can - add your check's fault (Tier B) and keep it at 53/53.
If you correct a number in the docs, add the old value to `tools/check_doc_figures.py` so it
can't come back.
