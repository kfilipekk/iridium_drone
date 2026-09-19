# AGENTS.md — picking this repo up

For any agent or human continuing this work. One command tells you everything:

```bash
python3 tools/preflight.py     # ~15 min. Needs the pcbnew python module (KiCad); no env vars.
```

## Reading the verdict

The verdict is **derived, not printed**: `preflight.py` runs the checks, and
`tools/readiness.py` classifies every prerequisite and renders the summary. Nothing in the
output is hand-typed, so if a fresh run disagrees with the last recorded one, something
actually changed — investigate, never edit output around it.

- **`READY TO ORDER — all N gated prerequisites proven`** — every claim that can be
  checked offline is true *right now*. This is the strongest statement the repo can make
  without hardware.
- **`NOT READY TO FLY — N item(s) need hardware`** — bench measurements that cannot exist
  before a physical board does. Expected until hardware arrives; deliberately not an
  order blocker. Never "fix" these — they close at the bench (T3a–T3d, see the runbook).
- **`NOT BUILT YET — N item(s) are code, not measurements`** — the on-board Iridium DSP
  components that have to be *written* (ephemeris, burst detection, H743 firmware, EKF
  backend). They gate the project, not ordering. See `docs/KNOWN-ISSUES.md`.
- **Warnings are never hidden** — currently six, each with its reason inline in
  `tools/readiness.py`. If a warning is on that register, it is already understood.

## Where the truth lives

| Question | Ask |
|---|---|
| Is the board orderable? What is left? | the gate verdict |
| What is accepted/deferred/not built? | `docs/KNOWN-ISSUES.md` — the register |
| What do I buy? | `docs/BUYING.md`, generated from `docs/PARTS.csv` (the decision record) |
| How do I order→fly? | `docs/navcore-runbook.tex` / `.pdf` (the compiled runbook) |
| Board outline, pinout, BOM, airframe | `tools/design.py` — the single source of truth |

Numbers that matter (stock levels, dates, counts) live in `fab/stock-snapshot.json` (aged
7 days max, enforced by `tools/check_stock.py`) or are computed by the gate — not in prose.
Prose quoting a number is the defect class this repo keeps paying for; see
`tools/check_doc_figures.py`, which enforces that retired figures never read as current.

## Do not hand-edit — generated

Edit the source, regenerate, and let the gate prove it:

- `NAVCORE-SoOP.kicad_pcb` / `.kicad_sch` — from `tools/design.py` via
  `gen_sch.py` / `gen_pcb.py`. Full rebuild:
  `python3 tools/check_design.py && python3 tools/gen_sch.py && python3 tools/gen_pcb.py && python3 tools/route.py`.
  **Read `tools/revb_transplant.py`'s header first**: regenerated placement loses the
  hand-tuned adjacency that satisfies 70 rules; the board file is ahead of the packer.
- `docs/PINMAP.md`, `docs/LAYOUT.md`, `docs/ROUTING-TODO.md` and the tables in
  `docs/BUYING.md` — `gen_doc_tables.py` / `gen_pinmap.py`.
- `firmware/NAVCORE_SoOP/hwdef.dat` — `gen_hwdef.py`.
- `fab/` gerbers, BOM, CPL, order bundle — `tools/make_order_bundle.sh`.
- Prose docs (`docs/*.md`) are gitignored held-back drafts; the tracked documentation is
  `README.md`, `docs/navcore-runbook.tex`/`.pdf` and `docs/PARTS.csv`.

## Verification culture

Every check is broken on purpose before it is trusted, then restored byte-identically.
A check that cannot fail is worse than no check — the README's "Verification" section
lists the defects that passed six checks each. If you add a check, add its negative test
to that discipline. If you correct a figure in the docs, add the old value to
`tools/check_doc_figures.py`'s retired list with the reason.

Firmware is proved by `tools/build_firmware.sh` (bootloader + arducopter, ~10 min warm);
it records the hwdef sha256 it compiled from and `preflight.py` compares **content**, not
timestamps. Zero DMA conflicts in its step 6 is the strongest evidence the hwdef is real.

## Conventions

- Commit messages: imperative, lead with the why; end every session with the tree clean
  and the gate re-run on the final tree.
- SITL scenarios: `sitl/run_scenarios.sh` (logs are gitignored; regenerate freely).
- `SPONSORSHIP.md`, `docs/datasheets/` are local-only by design.
