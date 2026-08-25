#!/usr/bin/env python3
"""
Make the board's footprint metadata agree with design.py.

`gen_pcb.py` loads footprints with pcbnew.FootprintLoad(directory, name), which returns a
footprint whose FPID has no library nickname. design.py and the schematic both carry the
full id - "Capacitor_SMD:C_0402_1005Metric" - so KiCad's schematic-parity check reports
every one of them as a mismatch. 199 of the board's 218 parity issues were this and
nothing else, which buries the 19 that are real.

It also re-syncs the Value fields, which had drifted further and worse. design.py
applies a late `_VALUE_FIX` correcting the buck dividers - the 5 V rail's divider was
10k2/3k24, which is 3.32 V, a 3.3 V rail where 5 V was intended. The BOM and the
schematic carry the corrected values, but the BOARD's footprints still said 3k24, 10k2,
392k, 78k7 and 102k: the wrong ones, printed on the fab drawing next to parts the BOM
correctly orders as 5k1 and 27k. Nobody assembling from the BOM is misled; anyone
reading the board or repairing it would be.

Metadata only: nothing moves, no copper changes. Verified by DRC anyway.

Usage:  python3 tools/fix_fpid.py [--apply]
"""
import os, re, sys, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/fpid_backup.kicad_pcb"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/nav/fpid.rpt",
                    "--schematic-parity", "--severity-all", BOARD],
                   capture_output=True, timeout=900)
    t = open("/tmp/nav/fpid.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return (cls.count("unconnected_items"), cls.count("footprint_symbol_mismatch"),
            len([c for c in cls if c != "unconnected_items"]))


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    u0, m0, tot0 = drc()
    print(f"baseline: {u0} unconnected, {m0} footprint/symbol mismatches, {tot0} total")

    board = pcbnew.LoadBoard(BOARD)
    todo = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        want = design.COMPONENTS.get(ref, (None, None))[1]
        if not want or ":" not in want:
            continue
        nick = want.split(":")[0]
        if fp.GetFPID().GetLibNickname().wx_str() != nick:
            todo.append((ref, nick, want.split(":")[1]))
    vals = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        c = design.COMPONENTS.get(ref)
        if c and c[2] and fp.GetValue() != c[2]:
            vals.append((ref, fp.GetValue(), c[2]))
    print(f"{len(todo)} footprint(s) missing their library nickname")
    print(f"{len(vals)} footprint(s) with a stale Value field")
    for ref, was, now in vals[:6]:
        print(f"   {ref:5} board says {was!r}, design.py says {now!r}")
    if not apply:
        for ref, nick, name in todo[:4]:
            print(f"   {ref:5} -> {nick}:{name}")
        print("\ndry run - pass --apply to write the board")
        return 0

    shutil.copy(BOARD, BAK)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        want = design.COMPONENTS.get(ref, (None, None))[1]
        if not want or ":" not in want:
            continue
        # The SWIG bindings want a UTF8, not a str, on every setter - the two-argument
        # constructor is the one that takes plain strings.
        nick, name = want.split(":", 1)
        fp.SetFPID(pcbnew.LIB_ID(nick, name))
    for fp in board.GetFootprints():
        c = design.COMPONENTS.get(fp.GetReference())
        if c and c[2]:
            fp.SetValue(c[2])
    board.Save(BOARD)
    u, m, tot = drc()
    if u <= u0 and tot <= tot0:
        print(f"set {len(todo)} nickname(s) and {len(vals)} value(s) -> {u} unconnected, "
              f"{m} mismatches (was {m0}), {tot} parity/DRC items (was {tot0})")
        return 0
    shutil.copy(BAK, BOARD)
    print(f"rolled back: {u} unconnected, {tot} items")
    return 1


if __name__ == "__main__":
    sys.exit(main())
