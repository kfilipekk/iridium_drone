#!/usr/bin/env python3
"""Dissolve the C8.2 ground island by nudging C3 0.06 mm west.

The island
----------
The 2.10 mm2 B.Cu ground pocket under U1's pad row (bbox 124.21..127.41 x
111.58..113.53) that carries C8.2 - the VCAP1 bypass cap's ground pad. It holds no
via and DRC reports it as "Missing connection between items: Zone [GND] on In3.Cu /
Zone [GND] on B.Cu", which is what tools/preflight.py's "all nets routed" failure is
actually complaining about.

Why nothing else worked
-----------------------
The pocket is a RING, and the ring is five B.Cu traces that are all load-bearing.
Measured by removing one at a time and refilling (islands 2.101 -> 0 for each, and a
new unconnected item naming that net for each):

    +3V3      (125.344,113.246) -> (124.339,112.240)
    +3V3      (126.180,113.768) -> (125.658,113.246)     C3.1's fanout
    BUCK_BOOT (126.793,114.495) -> (126.793,113.376)
    BUCK_BOOT (126.793,113.376) -> (127.619,112.550)
    VCAP1     (125.256,111.426) -> (123.977,111.426)

So there is no "rip the one trace that seals it" fix, and every search tool agrees:
island_route.py (3934 island cells, no route and nowhere a via fits), island_via.py,
open_pocket.py and bridge_visible.py (258 boundary points, 774 rays, none provable)
all report no legal escape. The reason is arithmetic, not search resolution: this
pour's fill rule is min_thickness = clearance = 0.1016 mm, so the pour needs a 0.3048 mm
gap to flow through, and a bridge TRACK needs the same. Every gap between two ring
members is a shade under it:

    C3.1's pad -> BUCK_BOOT's B.Cu run       0.2822   (short 0.0226)  <-- used here
    island -> poly 11 across BUCK_BOOT       0.3058   but with BUCK_BOOT dead centre
    island -> the main pour across +3V3      0.3058   with the +3V3 junction dead centre
    island -> poly 14 across the VCAP1 via   0.2349

The two 0.3058 gaps are exactly 2 x clearance + track, i.e. the cutting trace fills
them edge to edge with zero slack, so no track fits and no pour reaches.

The fix
-------
Shoving the traces is not available either: BUCK_BOOT's run has 0.0018 mm of eastward
room (the SOOP_I_ADC via) and that via has 0.0017 mm east (an In3 SPI4_MISO track) and
0.0011 mm north-west (BUCK_BOOT's own diagonal) - all three are already at the minimum
clearance, so a coordinated 0.03 mm re-route of three nets would be needed.

C3 is the one thing in the passage with room. Moving it 0.06 mm WEST widens the
C3.1-pad -> BUCK_BOOT gap from 0.2822 to 0.3422, the pour flows in, and the island
dissolves - islands 1 -> 0, no bridge track required, DRC 0 errors and 0 unconnected.

C3 is a 100 nF decoupling cap on the BOTTOM side directly under U1.50, and U1 is on the
top side, so the move has no courtyard interaction at all. C3.1's +3V3 fanout track
ends at (126.180,113.768), which is still inside the moved pad (125.840..126.400), so
the fanout stays connected.

Usage:  python3 tools/free_island_b.py [--apply]

"""
import os, sys, re, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, island_route as ir

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK = "/tmp/nav/islandb_backup.kicad_pcb"
RPT = "/tmp/nav/islandb.rpt"
REF = "C3"
DX = 0.06           # west


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
        cls.count("unconnected_items"), t


def islands():
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    return [round(a, 3) for _l, _p, _poly, a in ir.orphans(b, ir.gnd_polys(b))]


def main():
    apply_ = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, _ = drc()
    isl0 = islands()
    print(f"baseline: {hard0} errors, {un0} unconnected, islands {isl0}")
    if not isl0:
        print("no islands - nothing to do")
        return 0
    if not apply_:
        print(f"dry run: would move {REF} west {DX} mm "
              f"({len(isl0)} island(s) to dissolve)")
        return 0

    shutil.copy(BOARD, BAK)
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    hit = 0
    for fp in b.GetFootprints():
        if fp.GetReference() != REF:
            continue
        p = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(route.TOMM(p.x) - DX),
                                       pcbnew.FromMM(route.TOMM(p.y))))
        hit += 1
        print(f"moved {REF} west {DX} mm -> "
              f"({route.TOMM(fp.GetPosition().x):.3f},{route.TOMM(fp.GetPosition().y):.3f})")
    if not hit:
        print(f"{REF} not on the board")
        return 1
    route.fill(b)
    b.Save(BOARD)

    hard, un, txt = drc()
    isl = islands()
    print(f"  -> islands {isl}, DRC {hard} errors, {un} unconnected")
    if not isl and hard <= hard0 and un <= un0:
        print("KEPT")
        return 0
    for blk in re.split(r'^\[', txt, flags=re.M)[1:][:6]:
        print("     " + blk.splitlines()[0])
    print("reverting")
    shutil.copy(BAK, BOARD)
    return 1


if __name__ == "__main__":
    sys.exit(main())
