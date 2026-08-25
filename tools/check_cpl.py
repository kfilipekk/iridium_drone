#!/usr/bin/env python3
"""
Verify the pick-and-place rotations from board geometry, independently of what wrote them.

tools/gen_bom.py computes CPL rotations by applying two corrections. If this file checked
them by applying the same corrections it would only prove the code agrees with itself, so
it does not look at gen_bom at all. It reads the finished CPL and the board, and asks a
question that needs no correction table:

  For every part, take pin 1's real position relative to the footprint centre. Put it in
  the view the assembler uses - mirrored in X for bottom-side parts, because they see the
  board from below. Then rotate it back by the rotation the CPL claims. What is left is
  where pin 1 sits in that footprint's own zero-degree orientation.

  Every part sharing a footprint must produce the SAME answer.

That is what caught the original bug: Q1 (top) and Q3 (bottom) are the same AO3400A and
the CPL called them 0 and 180, but their geometry said otherwise - un-rotating gave two
different pin-1 directions for one footprint, which is impossible.

The check is relative, so it proves consistency rather than absolute correctness against
JLCPCB's library. The pin-1 overlay (--svg) and JLCPCB's own upload preview cover that.

Usage:  python3 tools/check_cpl.py [-v] [--svg DIR]
"""
import os, sys, csv, math, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
CPL   = "fab/CPL-NAVCORE-SoOP.csv"
TOMM  = route.TOMM
TOL   = 12.0        # degrees; footprints place pin 1 on a coarse grid of directions


def pin1(fp):
    """The pad that defines orientation - pin 1, or the first pad if unnumbered."""
    pads = list(fp.Pads())
    for want in ("1", "A1", "A4B9"):
        for p in pads:
            if p.GetNumber() == want:
                return p
    return pads[0] if pads else None


def main():
    verbose = "-v" in sys.argv
    svgdir = None
    if "--svg" in sys.argv:
        svgdir = sys.argv[sys.argv.index("--svg") + 1]

    b = pcbnew.LoadBoard(BOARD)
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
    rows = list(csv.DictReader(open(CPL)))

    by_fp = collections.defaultdict(list)
    errs, notes = [], []
    drawn = []

    for r in rows:
        ref = r["Designator"]
        fp = fps.get(ref)
        if fp is None:
            errs.append(f"{ref} is in the CPL but not on the board")
            continue
        p1 = pin1(fp)
        if p1 is None:
            continue
        c, pp = fp.GetPosition(), p1.GetPosition()
        dx, dy = TOMM(pp.x) - TOMM(c.x), TOMM(pp.y) - TOMM(c.y)
        if math.hypot(dx, dy) < 0.05:
            continue                       # centred pin 1 carries no direction
        bottom = r["Layer"].strip().lower() == "bottom"
        if bottom:
            dx = -dx                       # the assembler sees the back mirrored
        rot = float(r["Rotation"])
        # KiCad's y axis points DOWN, so a stored angle turns the opposite way from the
        # usual maths convention. Un-rotating with -rot looked right and put R17 180 deg
        # from its identical twin R16; +rot makes every 0402 on the board agree.
        a = math.radians(rot)
        cx = dx * math.cos(a) - dy * math.sin(a)
        cy = dx * math.sin(a) + dy * math.cos(a)
        name = fp.GetFPID().GetLibItemName().wx_str()
        by_fp[name].append((ref, math.degrees(math.atan2(cy, cx)) % 360.0,
                            r["Layer"].strip(), rot))
        drawn.append((ref, name, r["Layer"].strip(), rot,
                      TOMM(c.x), TOMM(c.y), TOMM(pp.x), TOMM(pp.y)))

    checked = 0
    for name, items in sorted(by_fp.items()):
        if len(items) < 2:
            continue
        checked += len(items)
        base = items[0][1]
        spread = [(ref, ((ang - base + 180) % 360) - 180, lay, rot)
                  for ref, ang, lay, rot in items]
        bad = [x for x in spread if abs(x[1]) > TOL]
        if bad:
            errs.append(
                f"{name}: parts disagree on where pin 1 is once their CPL rotation is "
                f"undone - " + ", ".join(
                    f"{ref} ({lay}, {rot:.0f} deg) off by {d:+.0f} deg"
                    for ref, d, lay, rot in bad[:4]))
        elif verbose:
            print(f"  ok  {name:48} {len(items)} parts agree")

    sides = collections.Counter(r["Layer"].strip() for r in rows)
    rots = collections.Counter(float(r["Rotation"]) for r in rows)
    print(f"CPL placements     : {len(rows)}  ({sides['top']} top, {sides['bottom']} bottom)")
    print(f"rotations used     : " + ", ".join(f"{k:.0f} deg x{v}"
                                               for k, v in sorted(rots.items())))
    print(f"cross-checked      : {checked} parts across "
          f"{sum(1 for v in by_fp.values() if len(v) > 1)} shared footprints")

    if svgdir:
        os.makedirs(svgdir, exist_ok=True)
        for side in ("top", "bottom"):
            write_svg(os.path.join(svgdir, f"pin1-{side}.svg"),
                      [d for d in drawn if d[2] == side], side, b)
            print(f"wrote {svgdir}/pin1-{side}.svg")

    for it in notes:
        print(f"   {it}")
    if errs:
        print(f"\nERRORS ({len(errs)}):")
        for e in errs:
            print(f"   {e}")
        return 1
    print("\nevery shared footprint agrees on pin 1 - rotations are self-consistent.")
    return 0


def write_svg(path, items, side, board):
    """Pin-1 overlay: part outline, a dot at pin 1, and the CPL rotation."""
    import design
    BD = design.BOARD
    W, H = BD["W"], BD["H"]
    X0, Y0 = BD["X0"], BD["Y0"]
    sc = 16
    flip = (side == "bottom")

    def X(x):
        return ((X0 + W - x) if flip else (x - X0)) * sc

    def Y(y):
        return (y - Y0) * sc

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*sc}" height="{H*sc+30}" '
           f'viewBox="0 0 {W*sc} {H*sc+30}">',
           f'<rect width="100%" height="100%" fill="#14181c"/>',
           f'<text x="8" y="{H*sc+20}" fill="#8aa" font-family="monospace" '
           f'font-size="13">{side} side, viewed as the assembler sees it - '
           f'dot = pin 1, number = CPL rotation</text>']
    for ref, name, lay, rot, cx, cy, px, py in items:
        out.append(f'<line x1="{X(cx):.1f}" y1="{Y(cy):.1f}" x2="{X(px):.1f}" '
                   f'y2="{Y(py):.1f}" stroke="#3d5a6c" stroke-width="1"/>')
        out.append(f'<circle cx="{X(px):.1f}" cy="{Y(py):.1f}" r="2.6" fill="#ffb347"/>')
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy):.1f}" fill="#dfe7ea" '
                   f'font-family="monospace" font-size="8" text-anchor="middle">'
                   f'{ref}</text>')
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy)+8:.1f}" fill="#6fd0c0" '
                   f'font-family="monospace" font-size="7" text-anchor="middle">'
                   f'{rot:.0f}</text>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
