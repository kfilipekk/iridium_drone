#!/usr/bin/env python3
"""The vendored JLC library is present, complete, and identical to the board it rebuilds.

Usage: python3 tools/check_libraries.py
"""
import os
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew, design, fplib, symlib, jlcpaths

BOARD = sys.argv[1] if len(sys.argv) > 1 else "NAVCORE-SoOP.kicad_pcb"


def main():
    print(f"symbols    : {jlcpaths.SYMBOLS}")
    print(f"footprints : {jlcpaths.FOOTPRINTS}")
    print(f"3d models  : {jlcpaths.MODEL_ROOT}  (NOT vendored - reported only)")
    print()

    fp_refs = collections.defaultdict(list)      # footprint id -> [refs]
    sym_refs = collections.defaultdict(list)     # symbol id    -> [refs]
    for ref, v in design.COMPONENTS.items():
        sym, fp = v[0], v[1]
        if fp.startswith("jlc:"):
            fp_refs[fp].append(ref)
        if sym.startswith("jlc_parts:"):
            sym_refs[sym].append(ref)

    fails = []

    # ---- 1. complete ----------------------------------------------------------
    resolved = {}
    for fpid, refs in sorted(fp_refs.items()):
        path = fplib.find(fpid)
        if path is None:
            fails.append(f"{fpid}: referenced by {','.join(sorted(refs))} but not in "
                         f"{os.path.relpath(jlcpaths.FOOTPRINTS)}")
            continue
        resolved[fpid] = path

    syms = symlib.load()
    for sid, refs in sorted(sym_refs.items()):
        name = sid.split(":", 1)[1]
        if name not in syms:
            fails.append(f"{sid}: referenced by {','.join(sorted(refs))} but not in "
                         f"{os.path.basename(jlcpaths.SYMBOLS)}")

    print(f"referenced : {len(fp_refs)} footprint(s), {len(sym_refs)} symbol(s)")
    print(f"resolved   : {len(resolved)} footprint(s), "
          f"{len([s for s in sym_refs if s.split(':', 1)[1] in syms])} symbol(s)")

    # ---- 2. identical ---------------------------------------------------------
    board_pads = {}
    if os.path.exists(BOARD):
        bd = pcbnew.LoadBoard(BOARD)
        for f in bd.GetFootprints():
            board_pads[f.GetReference()] = sorted(p.GetNumber() for p in f.Pads())
    else:
        fails.append(f"{BOARD} not found - cannot compare the library to the board")

    checked = 0
    for fpid, refs in sorted(fp_refs.items()):
        if fpid not in resolved:
            continue
        info = fplib.load(fpid)
        lib_pads = sorted(p["num"] for p in info["pads"])
        for ref in refs:
            if ref not in board_pads:
                fails.append(f"{ref} ({fpid}): in design.py but has no footprint on "
                             f"{BOARD}")
                continue
            checked += 1
            if board_pads[ref] != lib_pads:
                only_lib = sorted(set(lib_pads) - set(board_pads[ref]))
                only_brd = sorted(set(board_pads[ref]) - set(lib_pads))
                detail = []
                if only_lib:
                    detail.append(f"in library only: {only_lib}")
                if only_brd:
                    detail.append(f"on board only: {only_brd}")
                fails.append(f"{ref} ({fpid}): pads differ - "
                             + "; ".join(detail or
                                         [f"same numbers, different order? lib={lib_pads} "
                                          f"board={board_pads[ref]}"]))
    print(f"compared   : {checked} ref(s) library pad-set vs board pad-set")

    # ---- 3. wired -------------------------------------------------------------
    wired = 0
    for netname, specs in design.NETS.items():
        for sp in specs:
            if "." not in sp:
                continue
            ref, pin = sp.split(".", 1)
            v = design.COMPONENTS.get(ref)
            if not v or not v[0].startswith("jlc_parts:"):
                continue
            pins = syms.get(v[0].split(":", 1)[1])
            if pins is None:
                continue          # already reported under complete
            wired += 1
            if symlib.resolve(pins, pin) is None:
                fails.append(f"{netname}: {sp} is wired, but {v[0]} has no pin {pin!r}")
    print(f"wired pins : {wired} spec(s) resolved against the vendored symbols")

    # ---- 4. tidy --------------------------------------------------------------
    vendored = {f[:-len(".kicad_mod")] for f in os.listdir(jlcpaths.FOOTPRINTS)
                if f.endswith(".kicad_mod")}
    used = {fpid.split(":", 1)[1] for fpid in fp_refs}
    orphans = sorted(vendored - used)
    print(f"vendored   : {len(vendored)} file(s), {len(orphans)} unreferenced")
    for o in orphans:
        fails.append(f"{o}.kicad_mod is vendored but no design.py part uses it")

    # ---- 3D models: report only ----------------------------------------------
    have_models = sum(1 for u in used
                      if os.path.exists(os.path.join(jlcpaths.MODEL_ROOT, "packages3d",
                                                     u + ".step")))
    print(f"3d bodies  : {have_models}/{len(used)} present under MODEL_ROOT "
          f"(not required here)")

    print()
    if fails:
        print(f"FAIL - {len(fails)} problem(s) with the vendored library:")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("vendored library is complete, agrees with the board, and nothing is orphaned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
