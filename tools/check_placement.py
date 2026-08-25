#!/usr/bin/env python3
"""Gate 1: is the placement electrically correct, before any routing time is spent?"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = "NAVCORE-SoOP.kicad_pcb"
TOMM = pcbnew.ToMM


def main():
    b = pcbnew.LoadBoard(BOARD)
    pads, fps = {}, {}
    for fp in b.GetFootprints():
        fps[fp.GetReference()] = fp
        for pad in fp.Pads():
            pads[(fp.GetReference(), pad.GetPadName())] = (
                TOMM(pad.GetPosition().x), TOMM(pad.GetPosition().y))

    # --- adjacency rules -----------------------------------------------------
    fails, worst = [], []
    for ref, (t_ref, t_pad, max_mm) in design.ADJACENCY.items():
        if ref not in fps or (t_ref, t_pad) not in pads: continue
        tx, ty = pads[(t_ref, t_pad)]
        best = min((math.hypot(px - tx, py - ty)
                    for (r, _p), (px, py) in pads.items() if r == ref), default=None)
        if best is None: continue
        worst.append((best, ref, t_ref, t_pad, max_mm))
        if best > max_mm: fails.append((best, ref, t_ref, t_pad, max_mm))

    # --- net spans -----------------------------------------------------------
    bynet = {}
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNet()
            # Power rails are inherently long - +5V feeds connectors on every edge.
            # Measuring them as "signal span" just measures the board diagonal.
            nm = n.GetNetname() if n else ""
            if nm and nm not in ("GND", "+3V3", "+3V3A", "+5V", "+9V",
                                 "VBAT", "VBUS", "VDDA", "VCC_RF"):
                p = pad.GetPosition()
                bynet.setdefault(n.GetNetname(), []).append((TOMM(p.x), TOMM(p.y)))
    spans = []
    for nn, ps in bynet.items():
        if len(ps) < 2: continue
        spans.append((max(math.hypot(a[0]-c[0], a[1]-c[1]) for a in ps for c in ps), nn))
    mean = sum(s for s, _ in spans) / len(spans)
    diag = math.hypot(design.BOARD["W"], design.BOARD["H"])
    frac = mean / diag

    print("=== Gate 1: placement ===\n")
    print(f"{'metric':<42} {'value':>10} {'target':>10}  ")
    print("-" * 68)
    print(f"{'adjacency rules checked':<42} {len(worst):>10} {'':>10}")
    print(f"{'  violations':<42} {len(fails):>10} {'0':>10}  {'PASS' if not fails else 'FAIL'}")
    # An MCU-to-edge-pad net cannot be short: the MCU is central and the pad must reach an edge.
    print(f"{'mean signal span, rails excluded (mm)':<42} {mean:>10.1f} {'':>10}")
    print(f"{'  as a fraction of the diagonal':<42} {frac:>10.2f} {'<0.30':>10}  "
          f"{'PASS' if frac < 0.30 else 'FAIL'}")
    for s, nn in sorted(spans, reverse=True)[:5]:
        print(f"{'    longest: ' + nn:<42} {s:>10.1f}")
    if fails:
        print(f"\nadjacency violations ({len(fails)}):")
        for d, ref, tr, tp, mx in sorted(fails, reverse=True):
            print(f"   {ref:<5} -> {tr}.{tp:<5} {d:6.2f} mm  (max {mx})")
    else:
        print("\nworst adjacency distances (all within limit):")
        for d, ref, tr, tp, mx in sorted(worst, reverse=True)[:6]:
            print(f"   {ref:<5} -> {tr}.{tp:<5} {d:6.2f} mm  (max {mx})")
    mount = check_mounting(b)
    return 1 if (fails or mount or frac >= 0.30) else 0


# The stack screws land on the board, not just through it.
HARDWARE = [("M3 cap head, 5.5 mm OD", 2.75, True),      # True = hard failure
            ("silicone grommet flange, 6 mm OD", 3.00, False),
            ("M3 washer, 7 mm OD", 3.50, False)]


def check_mounting(board):
    import math, pcbnew
    holes = [(d.GetCenter().x / 1e6, d.GetCenter().y / 1e6) for d in board.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts and d.ShowShape() == "Circle"]
    if not holes:
        print("\nno mounting holes found on Edge.Cuts"); return 0
    near = []
    for f in board.GetFootprints():
        best = 1e9
        for pad in f.Pads():
            bb = pad.GetBoundingBox()
            x0, y0, x1, y1 = [v / 1e6 for v in (bb.GetLeft(), bb.GetTop(),
                                                bb.GetRight(), bb.GetBottom())]
            for hx, hy in holes:
                best = min(best, math.hypot(max(x0 - hx, 0, hx - x1),
                                            max(y0 - hy, 0, hy - y1)))
        if best < 1e9:
            near.append((best, f.GetReference()))
    near.sort()
    bad = 0
    print(f"\nmounting hardware clearance ({len(holes)} holes):")
    for label, r, hard in HARDWARE:
        hits = [(d, ref) for d, ref in near if d < r]
        if hits and hard:
            bad += len(hits)
            print(f"   FAIL {label}: pad copper within {r} mm -> "
                  + ", ".join(f"{ref} ({d:.2f})" for d, ref in hits))
        elif hits:
            print(f"   note {label}: {len(hits)} parts within {r} mm "
                  f"(closest {hits[0][1]} at {hits[0][0]:.2f}) - do not fit washers")
        else:
            print(f"   ok   {label}: nothing within {r} mm")
    return bad


if __name__ == "__main__":
    sys.exit(main())
