#!/usr/bin/env python3
"""
Rebuild the secondary-rail power plane on In4.Cu.

WHY THIS EXISTS
---------------
route.power_islands() builds the In4.Cu rails as bounding boxes around each rail's
pad CLUSTERS, capped at ISLAND_MAX_AREA = 50 mm2. On the Rev B placement that cap
drops almost everything that matters: the +5V clusters are 294.6 and 119.9 mm2, VBAT's
is 123.1, +9V's is 63.7, and +3V3A's analog cluster is 55.4. So Rev B came back with
+3V3 pouring 1594 mm2 of In4 and every secondary rail as a handful of small rectangles,
and check_power_cut.py found the whole aircraft's current entering the board through
one 0.102 mm track: VBAT at 0.2 A against the 1.7 A it needs, +5V at 0.2 A against
0.95, +3V3A at 0.2 A against 0.35.

That is a regression, not a design limit. The committed board's rail rectangles are a
known-good partition - with the CURRENT design.py and the CURRENT check_power_cut it
passes with room to spare (VBAT ~2.9 A, +5V ~2.9 A, +3V3A ~0.6 A). Rev B transplanted
134 hand-tuned part positions but not the zones.

So RECTS below is that partition, transcribed. The pour fills around whatever Rev B
put on top of it; nothing here assumes the placement is unchanged.

WHAT REV A DID NOT NEED
-----------------------
Rev B added three things the committed rectangles do not cover:

  VBAT entry      Rev A's VBAT arrived at J2.2 on the left edge at y~120. Rev B put the
                  reverse-polarity P-FET at the power entry, so VBAT now starts at
                  Q4's source at (103.45, 105.00) and J2.2 is on VBAT_IN. Without a
                  pour reaching Q4, the battery current crosses a line at y=105.5 on a
                  0.102 mm track.
  +3V3A corridor  The analog rail's regulator (U10) is at (121.2, 143.75) and its loads
                  are at y 110-124. The whole band between them is VBAT, +9V and VDDA
                  rectangles, so the rail was carried by one 0.102 mm In3 track from
                  (102.98, 137.59) to (108.87, 143.47) and back up. Hence the three
                  +3V3A rectangles below, one of which outranks the VBAT rectangles so
                  the corridor survives - VBAT keeps 2.0 A afterwards against 1.7.
  +9V             Dropped. Its only load, U18, is DNP, so the rail is not populated, and
                  its rectangle (prio 3) was sitting exactly where VBAT and +3V3 need to
                  cross. Removing it took VBAT from 1.5 A to 3.8 A.

RESIDUAL, AND IT IS REAL
------------------------
This leaves five +3V3 items unconnected. The rail rectangles carve the +3V3 pour, and
five +3V3 track stubs were only ever joined through it. They are listed by
check_design/DRC as Track<->Track and Pad<->Pad pairs around x 111-138, y 112-128.
They must be bridged before ordering. See the handoff notes.

Usage:
  python3 tools/repour_power.py [--apply] [--grid]

board.Remove() leaves pcbnew's ZONES list stale - the next Add() segfaults - so the
strip and the rebuild run in separate processes.
"""
import os, sys, subprocess

BOARD = "NAVCORE-SoOP.kicad_pcb"
HERE = os.path.abspath(__file__)

# net, priority, x1, y1, x2, y2 - the committed In4.Cu partition, plus Rev B corridors.
# Priority decides overlap: +3V3 is the base pour at 0 and loses to everything above it.
RECTS = [
    # --- committed partition -------------------------------------------------
    ('+3V3A',  5, 115.23, 109.25, 126.15, 115.66),
    ('+3V3A',  8, 117.44, 141.79, 122.10, 145.15),
    ('+5V',    1, 108.17, 135.70, 126.62, 144.65),
    ('+5V',    4, 123.51, 105.22, 136.44, 112.66),
    ('+5V',    9, 138.55, 123.37, 140.83, 127.07),
    ('+5V',   10, 128.70, 136.64, 133.34, 138.44),
    ('+5V',   12, 106.50, 132.50, 112.00, 135.40),
    ('+5V',   13, 110.00, 134.00, 115.00, 138.00),
    ('+5V',   16, 136.00, 105.50, 143.50, 113.00),
    ('+5V',   17, 138.00, 112.50, 143.50, 124.00),
    ('+5V',   18, 138.00, 123.00, 143.50, 128.50),
    ('+5V',   19, 136.50, 127.50, 143.50, 137.50),
    ('+5V',   20, 126.00, 135.50, 141.00, 142.00),
    ('VBAT',   2, 117.19, 113.20, 131.24, 122.91),
    ('VBAT',   6, 128.96, 123.03, 136.24, 130.06),
    ('VBAT',  11, 101.00, 117.50, 118.00, 123.50),
    ('VBAT',  14, 131.00, 113.50, 136.50, 118.00),
    ('VBAT',  15, 133.50, 117.50, 136.50, 124.50),
    ('VDDA',   7, 119.54, 124.23, 126.16, 131.23),
    # --- Rev B only ----------------------------------------------------------
    # VBAT reaches Q4's source (103.45, 105.00) through a LEFT-EDGE strip plus a
    # separate 3.5 mm band along the top, NOT through the full 16.5 x 15 mm box this
    # used to be. The full box covered the +3V3 pour that fed four +3V3 stubs at
    # x~111, y 112-124, and they came back unconnected. Narrowing it to the strip
    # fixes all four and costs VBAT nothing: the rail still crosses x=115.5 in the
    # band above the +3V3A corridor. Priority 3, not 1, because the band TOUCHES the
    # strip at x=106.5 and KiCad rejects two touching zones of one net at one priority.
    ('VBAT',   1, 101.00, 104.00, 106.50, 119.00),   # entry strip, reaches Q4
    ('VBAT',   3, 106.50, 104.00, 117.50, 108.00),   # entry band across the corridor
    ('+3V3A', 21, 115.50, 109.00, 118.00, 126.00),   # corridor, outranks VBAT
    ('+3V3A',  2, 101.00, 126.00, 106.40, 136.00),
    ('+3V3A',  3, 101.00, 135.50, 108.20, 145.00),
    # +3V3 LOCAL RESTORATION, priority 22 so it beats every rail rectangle it crosses.
    # These are NOT a plane-wide promotion - that was tried (a full-height +3V3 corridor)
    # and it starves whichever rail it runs through. They are four small patches exactly
    # where the VBAT rectangles had taken the +3V3 pour out from under shipped +3V3
    # copper: two around the R11/C3 stubs, one along the L1/via run at y~127.6, and one
    # under U5 whose pads 3/7/8 are all +3V3. VBAT keeps 2.0 A against the 1.7 A it
    # needs with all four in place; without the two R11/C3 patches it is 0.7 A and fails.
    ('+3V3',  22, 123.50, 112.10, 127.20, 115.20),   # C3/R12 stub (covers the +3V3 via at 123.85,112.69)
    ('+3V3',  22, 123.60, 118.00, 126.20, 121.20),   # R11 stub
    ('+3V3',  22, 125.50, 126.60, 136.00, 128.60),   # L1 / via run
    ('+3V3',  22, 134.80, 113.20, 138.50, 126.00),   # under U5 (covers the +3V3 via at 135.135,114.57)
]
DROP = {"+9V"}          # DNP rail; its rectangle blocked VBAT and +3V3


def strip():
    import pcbnew, route
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    n = 0
    for z in list(b.Zones()):
        net = z.GetNet()
        nm = net.GetNetname() if net else ""
        if not nm or nm in ("", "GND"):
            continue
        # The base +3V3 pour is priority 0 and is NOT ours to remove - it is the plane
        # these rectangles sit on. The +3V3 RESTORATION patches above are also +3V3 but
        # carry priority 22, and they must go, or a second run duplicates them.
        if nm == "+3V3" and z.GetAssignedPriority() == 0:
            continue
        b.Remove(z); n += 1
    b.Save(BOARD)
    print(f"stripped {n} secondary-rail zone(s)")


def main():
    apply = "--apply" in sys.argv
    if "strip" in sys.argv:
        strip()
        return 0
    if "dry" in sys.argv:
        print(__doc__.strip())
        print(f"\n{len(RECTS)} rectangle(s), {sum(1 for r in RECTS if r[0] not in DROP)} kept")
        return 0
    if not apply:
        print(__doc__.strip())
        print("\ndry run - pass --apply to write the board")
        return 0

    subprocess.run([sys.executable, "-u", HERE, "strip"])

    sys.path.insert(0, os.path.dirname(HERE))
    import pcbnew, route
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    made = 0
    for nm, prio, x1, y1, x2, y2 in RECTS:
        if nm in DROP:
            continue
        net = b.FindNet(nm)
        if net is None:
            continue
        z = pcbnew.ZONE(b)
        z.SetLayer(b.GetLayerID("In4.Cu"))
        z.SetNet(net)
        z.SetAssignedPriority(prio)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetLocalClearance(pcbnew.FromMM(0.25))
        z.SetMinThickness(pcbnew.FromMM(0.2))
        o = z.Outline(); o.NewOutline()
        for px, py in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
            o.Append(pcbnew.FromMM(px), pcbnew.FromMM(py))
        b.Add(z); made += 1
    route.fill(b)
    b.Save(BOARD)
    print(f"added {made} rail rectangle(s); {len(b.Zones())} zones total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
