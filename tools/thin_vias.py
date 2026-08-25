#!/usr/bin/env python3
"""
Remove redundant vias that sit too close to another hole in the same net.

The board's hole-to-hole rule is 0.2495 mm - JLCPCB's stated minimum for holes on the
SAME net (0.254 mm / 10 mil). tools/route.py enforced HOLE_CLEAR = 0.20 when it placed
fanout and stitching vias, which is looser than the board's own rule, so 23 pairs ended
up between 0.2025 and 0.2464 mm apart. Every one is same-net - GND to GND, +5V to +5V,
+3V3 to +3V3 - so the risk is drill breakout and tear-out in fabrication rather than a
short, but it is still outside what the fab guarantees.

These are stitching and fanout vias, placed in numbers for low inductance rather than for
connectivity, so a pair that is too close can simply lose one member. Which one goes is
decided by redundancy: the via with more of its own net's copper nearby is kept.

Whole-board DRC after every removal, and the via goes back if the unconnected count moves.

ONE REMOVAL PER PROCESS. Loading the board repeatedly inside a single process is the
long-standing pcbnew SWIG instability this project has hit before - wrappers from an
earlier load go stale and GetPosition() starts returning a bare SwigPyObject with no .x.
So --apply removes exactly one via and exits; drive it from a shell loop.

Usage:
  python3 tools/thin_vias.py                      # report
  while python3 tools/thin_vias.py --apply; do :; done    # until it stops
"""
import os, re, sys, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/thinvia_backup.kicad_pcb"
RPT   = "/tmp/nav/thinvia.rpt"
TOMM  = route.TOMM


def drc(extra=()):
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT, *extra, BOARD],
                   capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return (len([c for c in cls if c != "unconnected_items"]),
            cls.count("unconnected_items"), cls.count("hole_to_hole"))


def too_close(board):
    """Same-net via pairs closer than the board's hole-to-hole rule."""
    ds = board.GetDesignSettings()
    try:
        need = TOMM(ds.m_HoleToHoleMin)
    except Exception:
        need = 0.2495
    vias = []
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        p = t.GetPosition()
        vias.append((TOMM(p.x), TOMM(p.y), TOMM(t.GetDrill()) / 2,
                     t.GetNetCode(), t.GetNet().GetNetname() if t.GetNet() else ""))
    pairs = []
    for i in range(len(vias)):
        for j in range(i + 1, len(vias)):
            a, b = vias[i], vias[j]
            gap = math.hypot(a[0]-b[0], a[1]-b[1]) - a[2] - b[2]
            if gap < need - 1e-6:
                pairs.append((gap, a, b, a[3] == b[3]))
    return sorted(pairs), need


def neighbours(board, x, y, code, r=2.0):
    """How much of this net's own copper is within r - a proxy for redundancy."""
    n = 0
    for t in board.GetTracks():
        if t.GetNetCode() != code:
            continue
        p = t.GetPosition()
        if math.hypot(TOMM(p.x) - x, TOMM(p.y) - y) < r:
            n += 1
    return n


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, h0 = drc(["--severity-all"])
    print(f"baseline: {un0} unconnected, {h0} hole-to-hole violations")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    pairs, need = too_close(board)
    diff = [p for p in pairs if not p[3]]
    print(f"rule: holes must be {need:.4f} mm apart (edge to edge)")
    print(f"{len(pairs)} pair(s) below it, {len(diff)} of them between DIFFERENT nets")
    for gap, a, b, same in pairs[:6]:
        print(f"   {gap:.4f} mm  {a[4]} ({a[0]:.2f},{a[1]:.2f}) <-> "
              f"{b[4]} ({b[0]:.2f},{b[1]:.2f}){'' if same else '  DIFFERENT NETS'}")
    if diff:
        print("   different-net pairs are NOT touched here - that is a routing problem, "
              "not a redundancy one")
    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0

    same = [p for p in pairs if p[3]]
    if not same:
        print("nothing left to thin")
        return 1
    removed = 0
    if True:
        gap, a, b, _ = same[0]
        # drop whichever has more of its own net around it
        ka = neighbours(board, a[0], a[1], a[3])
        kb = neighbours(board, b[0], b[1], b[3])
        drop = a if ka >= kb else b
        shutil.copy(BOARD, BAK)
        # Read every position BEFORE touching the board. pcbnew's SWIG wrappers go stale
        # as soon as anything is removed, and GetPosition() then returns a bare
        # SwigPyObject with no .x - a failure mode this project has hit before.
        found = None
        for t in board.GetTracks():
            if t.Type() != pcbnew.PCB_VIA_T:
                continue
            q = t.GetPosition()
            if abs(TOMM(q.x) - drop[0]) < 1e-4 and abs(TOMM(q.y) - drop[1]) < 1e-4:
                found = t
                break
        if found is None:
            print(f"   could not find the via at ({drop[0]:.2f},{drop[1]:.2f})")
            return 1
        board.Remove(found)
        route.fill(board)
        board.Save(BOARD)
        hard, un, h = drc(["--severity-all"])
        if un <= un0 and hard <= hard0:
            print(f"   removed {drop[4]} via at ({drop[0]:.2f},{drop[1]:.2f}) "
                  f"[gap was {gap:.4f}] -> {h} hole-to-hole left, {un} unconnected")
            return 0
        shutil.copy(BAK, BOARD)
        print(f"   keeping {drop[4]} via at ({drop[0]:.2f},{drop[1]:.2f}) - "
              f"removing it costs {un - un0} connection(s)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
