#!/usr/bin/env python3
"""
Relocate the crystal cluster to sit under the MCU's oscillator pins.

The load caps C15/C16 were pinned to Y1 by an adjacency rule, but Y1 itself was
pinned to nothing, so the packer parked the whole cluster in a corner 24.5 mm from
the pins it drives. At 8 MHz that is several pF of stray on a high-impedance node:
it pulls the frequency, can stop the oscillator starting, and leaves a sensitive
node running past the bucks and the DShot outputs.

There is no top-side answer - every position within 7 mm of the OSC pins overlaps U1
itself, because those pins are on the package perimeter and the body fills the
inside. So the cluster moves to the BOTTOM side directly beneath them, which is the
textbook arrangement anyway: two short vias instead of a long surface trace.

Placement here is copper-aware. Checking footprint overlap alone is not enough - a
first attempt did exactly that and dropped the parts straight onto existing bottom
side tracks and vias, for 31 DRC violations.

Usage:  python3 tools/move_xtal.py [--apply]
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/xtal_backup.kicad_pcb"
MM    = pcbnew.FromMM
B     = design.BOARD
XTAL  = ("Y1", "C15", "C16")
OSC   = (118.13, 125.13)          # U1.12 / U1.13
CLEAR = 0.15                      # design rule copper-to-copper


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/nav/xt.rpt",
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open("/tmp/nav/xt.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def via_r(v, layer):
    """Via radius in mm. PCB_VIA::GetWidth() needs a layer in this KiCad build -
    calling it bare trips an assert and floods stderr."""
    try:
        return v.GetWidth(layer) / 2e6
    except TypeError:
        return route.VIA_D / 2


def bbox(fp):
    r = fp.GetBoundingBox(False, False)
    return (r.GetLeft()/1e6, r.GetTop()/1e6, r.GetRight()/1e6, r.GetBottom()/1e6)


def hits_rect(seg, rect, clear=0.15):
    """Does a capsule come within `clear` of a rectangle?

    Sampling the RECTANGLE on a 5x5 grid and measuring to the segment - the obvious
    thing - misses thin traces that pass between the sample points. It let 11 shorts
    through. Sampling along the SEGMENT instead is reliable at this scale, because
    the step is far smaller than any feature.
    """
    _, x1, y1, x2, y2, rad = seg
    L = math.hypot(x2 - x1, y2 - y1)
    n = max(2, int(L / 0.05) + 1)
    for i in range(n + 1):
        t = i / n
        sx, sy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        if route.gap_to_rect(sx, sy, rect) < rad + clear:
            return True
    return False


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    bid = board.GetLayerID("B.Cu")

    # Bottom-layer copper and every through via, minus the crystal's own nets.
    copper = []
    for t in board.GetTracks():
        n = t.GetNet()
        if n and n.GetNetname() in ("OSC_IN", "OSC_OUT"):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            copper.append(("cap", p.x/1e6, p.y/1e6, p.x/1e6, p.y/1e6, via_r(t, bid)))
        elif t.GetLayer() == bid:
            a, c = t.GetStart(), t.GetEnd()
            copper.append(("cap", a.x/1e6, a.y/1e6, c.x/1e6, c.y/1e6, t.GetWidth()/2e6))

    others = [bbox(fp) for fp in board.GetFootprints()
              if fp.GetReference() not in XTAL and fp.IsFlipped()]

    def fits(cx, cy, w, h, extra, copper_aware=True):
        x0, y0, x1, y1 = cx - w/2, cy - h/2, cx + w/2, cy + h/2
        if (x0 < B["X0"] + 0.5 or y0 < B["Y0"] + 0.5
                or x1 > B["X0"] + B["W"] - 0.5 or y1 > B["Y0"] + B["H"] - 0.5):
            return False
        for a, bb, c, d in others + extra:
            if x0 < c and a < x1 and y0 < d and bb < y1:
                return False
        if not copper_aware:
            return True
        rect = (x0, y0, x1, y1)
        for s in copper:
            if hits_rect(s, rect, CLEAR):
                return False
        return True

    y1 = board.FindFootprintByReference("Y1")
    if not y1.IsFlipped():
        y1.Flip(y1.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    r = y1.GetBoundingBox(False, False)
    W = (r.GetRight() - r.GetLeft())/1e6 + 0.3
    H = (r.GetBottom() - r.GetTop())/1e6 + 0.3

    # Two tiers. A copper-clear slot is free, but on this board the nearest is
    # 11.96 mm - still poor for an 8 MHz oscillator. Allowing the move to rip the
    # bottom-side traces in the way gets it to 6.17 mm, and those nets simply go back
    # on the hand-routing worklist. A correct crystal is worth a few more connections
    # to finish by hand; a 12 mm oscillator node is not something you fix later.
    def scan(copper_aware):
        found = None
        x = B["X0"] + 1.0
        while x < B["X0"] + B["W"] - 1.0:
            y = B["Y0"] + 1.0
            while y < B["Y0"] + B["H"] - 1.0:
                d = math.dist((x, y), OSC)
                if d <= 14.0 and (found is None or d < found[0]) \
                        and fits(x, y, W, H, [], copper_aware):
                    found = (d, x, y)
                y += 0.25
            x += 0.25
        return found

    best = scan(True)
    if best is None or best[0] > 8.0:
        loose = scan(False)
        if loose and (best is None or loose[0] < best[0] - 1.0):
            was = f"{best[0]:.2f} mm" if best else "nothing within 14 mm"
            print(f"copper-clear scan found {was}; taking {loose[0]:.2f} mm "
                  f"and ripping the traces in the way")
            best = loose
    if not best:
        print("no slot for Y1 within 14 mm of the OSC pins")
        return 1

    d, cx, cy = best
    y1.SetPosition(pcbnew.VECTOR2I(MM(cx), MM(cy)))
    print(f"Y1  -> ({cx:.2f}, {cy:.2f}) bottom, {d:.2f} mm from the OSC pins "
          f"(was 24.54 mm)")

    placed = [bbox(y1)]
    for ref in ("C15", "C16"):
        fp = board.FindFootprintByReference(ref)
        if not fp.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        q = fp.GetBoundingBox(False, False)
        w = (q.GetRight() - q.GetLeft())/1e6 + 0.25
        h = (q.GetBottom() - q.GetTop())/1e6 + 0.25
        spot = None
        for aware in (True, False):
            for rad in [t * 0.1 for t in range(11, 45)]:
                for k in range(360):
                    a = k * math.pi / 180
                    px, py = cx + rad*math.cos(a), cy + rad*math.sin(a)
                    if fits(px, py, w, h, placed, aware):
                        spot = (px, py, rad); break
                if spot:
                    break
            if spot:
                break
        if not spot:
            print(f"  {ref}: no copper-clear room beside Y1")
            continue
        px, py, rad = spot
        fp.SetPosition(pcbnew.VECTOR2I(MM(px), MM(py)))
        placed.append(bbox(fp))
        print(f"  {ref} -> ({px:.2f}, {py:.2f}) bottom, {rad:.2f} mm from Y1")

    # Decide every removal in ONE pass and delete afterwards. Iterating GetTracks()
    # again after a Remove() invalidates the board wrapper in this SWIG build -
    # "'SwigPyObject' object is not iterable" on a board that worked a line earlier.
    doomed, hit = [], {}
    for t in board.GetTracks():
        n = t.GetNet()
        nm = n.GetNetname() if n else ""
        if nm in ("OSC_IN", "OSC_OUT"):
            doomed.append(t); hit[nm] = hit.get(nm, 0) + 1
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            seg = ("cap", p.x/1e6, p.y/1e6, p.x/1e6, p.y/1e6, via_r(t, bid))
        elif t.GetLayer() == bid:
            a, c = t.GetStart(), t.GetEnd()
            seg = ("cap", a.x/1e6, a.y/1e6, c.x/1e6, c.y/1e6, t.GetWidth()/2e6)
        else:
            continue
        clash = any(hits_rect(seg, r, CLEAR) for r in placed)
        if clash:
            doomed.append(t); hit[nm] = hit.get(nm, 0) + 1
    for t in doomed:
        board.Remove(t)
    print(f"ripped {len(doomed)} segments: "
          + ", ".join(f"{k}({v})" for k, v in sorted(hit.items())))
    print("  those nets go back on the hand-routing worklist")

    if not apply:
        print("dry run - pass --apply to write the board")
        return 0

    shutil.copy(BOARD, BAK)
    hard0, un0 = drc()
    route.fill(board)
    board.Save(BOARD)
    hard, un = drc()
    print(f"DRC: {hard0} -> {hard} errors, {un0} -> {un} unconnected")
    if hard > hard0:
        shutil.copy(BAK, BOARD)
        print("new DRC errors - rolled back")
        return 1
    print("kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
