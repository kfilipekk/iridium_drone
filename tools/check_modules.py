#!/usr/bin/env python3
"""Assert design.MODULES against the real board."""
import re, sys, pathlib


def _money(v):
    """Whole pounds when the price is whole, 2 dp when it is not (LD06 = 13.99)."""
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.2f}"
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import design

REPO = pathlib.Path(__file__).parent.parent
PCB = REPO / "NAVCORE-SoOP.kicad_pcb"
t = PCB.read_text()

def footprint_blocks(src: str):
    """Yield each (footprint ...) block by scanning paren depth."""
    for start in (m.start() for m in re.finditer(r'\(footprint "', src)):
        depth, i, n = 0, start, len(src)
        while i < n:
            c = src[i]
            if c == '"':                       # skip string literals wholesale
                i += 1
                while i < n and src[i] != '"':
                    i += 2 if src[i] == '\\' else 1
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    yield src[start:i + 1]
                    break
            i += 1

# ref -> set of nets its pads connect to
nets: dict[str, set[str]] = {}
for blk in footprint_blocks(t):
    r = re.search(r'\(property "Reference" "([^"]+)"', blk)
    if r:
        nets[r.group(1)] = {n for n in re.findall(r'\(net \d+ "([^"]*)"\)', blk) if n}
if len(nets) < 100:
    sys.exit(f"parser sanity check failed: found only {len(nets)} footprints")

fail, warn = [], []
mods = {k: v for k, v in design.MODULES.items() if isinstance(v, dict)}

for name, m in mods.items():
    needs = m["needs_board_change"]
    status = m["status"]

    # 1. every landing pad must be a real footprint carrying real nets
    for ref in m["lands_on"]:
        if ref not in nets:
            fail.append(f"{name}: lands_on '{ref}' is not a footprint on the board")
        elif not nets[ref]:
            fail.append(f"{name}: '{ref}' exists but NO PAD CARRIES A NET - not an attachment point")

    # 2. a module claiming it needs no board change must actually have somewhere to land
    if needs is None and not m["lands_on"] and not m.get("bec"):
        fail.append(f"{name}: claims needs_board_change=None but lands_on is empty")

    # 3. status and needs_board_change must agree - this is the anti-drift assertion
    blocked = status in ("blocked", "dnp")
    if blocked and needs is None:
        fail.append(f"{name}: status={status} but no board change is recorded as needed")
    if not blocked and needs is not None:
        fail.append(f"{name}: needs a board change ({needs[:40]}...) but status={status} "
                    f"reads as available - a respin is not 'later', it is another fab run")

# ---------------------------------------------------------------------------
# Sweep the prose too.
# ---------------------------------------------------------------------------
NOT_FOOTPRINTS = {
    "PF1": "PWR_FLAG schematic symbol - the VBAT one. No footprint, correctly absent",
    "PF8": "PWR_FLAG schematic symbol. No footprint, correctly absent",
    "J7": "a solder-pad GROUP (P71-P74), not a socket - see VERIFICATION.md",
    # Rev B removals.
    "J4": "companion/TELEM1 JST-GH - cut 2026-09-09, no legal edge home; UART7 reaches no pad",
    "P42": "UART7 S1 spare pad - removed in the Rev B relayout along with J4; UART7 has no landing",
    "P43": "UART7 S2 spare pad - removed in the Rev B relayout along with J4; UART7 has no landing",
    "P45": "UART7 spare pad - removed in the Rev B relayout along with J4",
    "P51": "RC receiver solder pad - removed in the Rev B relayout; RC now lands on J5 (JST-SH 4P, USART6)",
    "P52": "RC receiver solder pad - removed in the Rev B relayout; RC now lands on J5 (JST-SH 4P, USART6)",
    "P53": "RC receiver solder pad - removed in the Rev B relayout; RC now lands on J5 (JST-SH 4P, USART6)",
    "P54": "RC receiver solder pad - removed in the Rev B relayout; RC now lands on J5 (JST-SH 4P, USART6)",
    "TP11": "Q-channel DC tap probe - removed 2026-09-18 with R30 in the baseband rework; "
            "SOOP_Q_ADC now comes from U14's difference-amplifier output, and PC5 is free",
}
docs = [q for q in (REPO / "docs").glob("*.md") if q.name != "HISTORY.md"]
docs.append(REPO / "README.md")
ghosts: dict[str, set[str]] = {}
for q in docs:
    if not q.exists():
        continue
    for mm in re.finditer(r"`(P\d{1,2}|TP\d{1,2}|PV\d|PF\d|J\d|PL\d|PZ\d)`", q.read_text()):
        ref = mm.group(1)
        if ref not in nets and ref not in NOT_FOOTPRINTS:
            ghosts.setdefault(ref, set()).add(q.name)
for ref, where in sorted(ghosts.items()):
    fail.append(f"docs reference `{ref}` as if it were on the board, but it is not a "
                f"footprint - in {', '.join(sorted(where))}. If that is deliberate, "
                f"add it to NOT_FOOTPRINTS with a reason")

# ---------------------------------------------------------------------------
# The rail budget.
# ---------------------------------------------------------------------------
rail = design.RAIL_5V
budget_ma = rail["headroom_a"] * 1000
on_bec = [(n, m["ma_5v"]) for n, m in mods.items() if m.get("bec")]
uncounted = [(n, m["ma_5v"]) for n, m in mods.items()
             if not m["counted"] and m["ma_5v"] and not m.get("bec")]
total = sum(ma for _, ma in uncounted)

print(f"\n+5 V rail: {rail['fitted_load_a']:.3f} A fitted (continuous, every FC-rail sensor "
      f"budgeted) against L2's {rail['irms_a']} A Irms -> {budget_ma:.0f} mA headroom")
if on_bec:
    bec_total = sum(ma for _, ma in on_bec)
    print(f"  on the PAYLOAD BEC, not this rail ({bec_total} mA running; LD06 surges to 300 mA):")
    for n, ma in sorted(on_bec, key=lambda x: -x[1]):
        print(f"    {n:20s} {ma:4d} mA")
    if bec_total > 2000:
        fail.append(f"payload BEC loads total {bec_total} mA - above a 3 A BEC's sensible continuous rating")
if uncounted:
    print(f"  modules on the FC rail but NOT in design.LOADS_5V, totalling {total} mA:")
    for n, ma in sorted(uncounted, key=lambda x: -x[1]):
        print(f"    {n:20s} {ma:4d} mA")
        fail.append(f"{n}: {ma} mA on the FC's +5 V rail but neither in design.LOADS_5V nor "
                    f"marked bec=True - U8's thermal bracket does not include it")
if total > budget_ma:
    print(f"  -> {total} mA exceeds {budget_ma:.0f} mA: these CANNOT all run together.")
    print(f"     Fit them one or two at a time, or give one its own BEC off the battery.")
    print(f"     This is a POWER limit, not an interface limit - every one still attaches.")
    # Not a fail.
    warn.append(f"+5 V rail cannot carry all optional modules at once "
                f"({total} mA offered, {budget_ma:.0f} mA available)")

avail = [n for n, m in mods.items() if m["needs_board_change"] is None]
blkd = [n for n, m in mods.items() if m["needs_board_change"] is not None]

print(f"{len(avail)}/{len(mods)} modules attach to the board AS FABRICATED:")
for n in avail:
    m = mods[n]
    print(f"  ok   {n:20s} {m['status']:7s} GBP{_money(m['gbp']):<7s} {m['conn']}")
if blkd:
    print(f"\n{len(blkd)} need a second fabrication run:")
    for n in blkd:
        print(f"  --   {n:20s} {mods[n]['status']:7s} {mods[n]['needs_board_change']}")
for f in fail:
    print(f"\nFAIL {f}")
for w in warn:
    print(f"\nwarn {w}")
print(f"\n{'FAIL' if fail else 'PASS'} - {len(fail)} problem(s), {len(warn)} warning(s)")
sys.exit(1 if fail else 0)
