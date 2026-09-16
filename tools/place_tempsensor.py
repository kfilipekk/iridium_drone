#!/usr/bin/env python3
"""
Place U19 (TMP119) hard against U9, and C74 against U19.

WHY A DEDICATED TOOL. U19's whole value is WHERE it sits. It exists to measure the
temperature of U9, the one part on this board whose junction temperature nobody can
compute, and a TMP119 placed somewhere convenient measures the room instead. So the
placement is a requirement, not a preference: design.ADJACENCY binds U19 to within
4.0 mm of U9.1 and check_placement enforces it.

THE OBSTACLE MODEL IS THE WHOLE JOB, and it was learned by getting it wrong three times
on an earlier placement:

  * footprints alone      -> 28 DRC errors. The cells were free of PARTS and full of
                             TRACES.
  * plus copper           -> 6 errors. A solder-mask opening is WIDER than its pad, so
                             copper spacing is not mask spacing.
  * plus a zone refill    -> 1 error. A pad dropped into already-filled copper is a
                             clearance violation until the pour is recomputed round it.
  * plus footprint-level  -> clean. Rule areas live inside FOOTPRINTS too, not only on
    keepouts                 the board: J12's U.FL carries its own.

DRC is the authority, not the geometry above, and it is run IN PLACE with the .kicad_pro
beside the board - route.fill() documents that judging a copy in /tmp invents eight
ground islands that do not exist.

    python3 tools/place_tempsensor.py
"""
import math
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import design
import add_part

BOARD = "NAVCORE-SoOP.kicad_pcb"
SCREW_R, HOLE_MARGIN, EDGE, CLR, STEP = 2.75, 0.25, 0.45, 0.35, 0.25


def cbbox(fp):
    xs, ys = [], []
    for d in fp.GraphicalItems():
        if d.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            bb = d.GetBoundingBox()
            xs += [bb.GetLeft() / 1e6, bb.GetRight() / 1e6]
            ys += [bb.GetTop() / 1e6, bb.GetBottom() / 1e6]
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        xs += [bb.GetLeft() / 1e6, bb.GetRight() / 1e6]
        ys += [bb.GetTop() / 1e6, bb.GetBottom() / 1e6]
    if not xs:
        bb = fp.GetBoundingBox()
        return (bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
    return min(xs), min(ys), max(xs), max(ys)


def obstacles(b, ref, flipped, lay, placed):
    out = []
    for o in b.GetFootprints():
        if o.GetReference() == ref:
            continue
        if o.IsFlipped() == flipped:
            out.append(cbbox(o))
        for pad in o.Pads():
            if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                bb = pad.GetBoundingBox()
                out.append((bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                            bb.GetRight() / 1e6, bb.GetBottom() / 1e6))
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            v = t.GetPosition()
            try:
                r = t.GetWidth(pcbnew.F_Cu) / 2e6
            except TypeError:
                r = 0.30
            out.append((v.x / 1e6 - r, v.y / 1e6 - r, v.x / 1e6 + r, v.y / 1e6 + r))
        elif t.GetLayer() == lay:
            a, e = t.GetStart(), t.GetEnd()
            w = t.GetWidth() / 2e6
            out.append((min(a.x, e.x) / 1e6 - w, min(a.y, e.y) / 1e6 - w,
                        max(a.x, e.x) / 1e6 + w, max(a.y, e.y) / 1e6 + w))
    for z in list(b.Zones()) + [z for f2 in b.GetFootprints() for z in f2.Zones()]:
        if z.GetIsRuleArea():
            bb = z.GetBoundingBox()
            out.append((bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                        bb.GetRight() / 1e6, bb.GetBottom() / 1e6))
    for r2 in placed:
        o = b.FindFootprintByReference(r2)
        if o is not None and o.IsFlipped() == flipped:
            out.append(cbbox(o))
    return out


def drc_classes(path):
    rpt = "/tmp/nav/place_temp_drc.rpt"
    os.makedirs("/tmp/nav", exist_ok=True)
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", rpt,
                    "--severity-error", path], capture_output=True, timeout=900)
    out = {}
    for c in re.findall(r'^\[([a-z_]+)\]', open(rpt).read(), re.M):
        out[c] = out.get(c, 0) + 1
    return out


def place(b, ref, anchor_xy, limit, geom, placed):
    """Nearest legal cell to anchor_xy, refusing beyond `limit` mm."""
    X0, Y0, W, H, holes = geom
    fp = b.FindFootprintByReference(ref)
    if fp is None:
        fp = add_part.load_fp(b, ref)
        b.Add(fp)
        for pad in fp.Pads():
            nm = add_part._net_for(ref, pad.GetNumber())
            if nm is None:
                continue
            net = b.FindNet(nm)
            if net is None:
                net = pcbnew.NETINFO_ITEM(b, nm)
                b.Add(net)
            pad.SetNet(net)
    ax, ay = anchor_xy
    for want_flip in (False, True):
        if fp.IsFlipped() != want_flip:
            fp.Flip(fp.GetPosition(), False)
        lay = pcbnew.B_Cu if want_flip else pcbnew.F_Cu
        obst = obstacles(b, ref, want_flip, lay, placed)
        for r in range(1, int(limit / STEP) + 1):
            cands = [(ax + ix * STEP, ay + iy * STEP)
                     for iy in range(-r, r + 1) for ix in range(-r, r + 1)
                     if max(abs(ix), abs(iy)) == r]
            cands.sort(key=lambda c: (c[0] - ax) ** 2 + (c[1] - ay) ** 2)
            for x, y in cands:
                if math.hypot(x - ax, y - ay) > limit:
                    continue
                fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
                x0, y0, x1, y1 = cbbox(fp)
                if (x0 < X0 + EDGE or y0 < Y0 + EDGE
                        or x1 > X0 + W - EDGE or y1 > Y0 + H - EDGE):
                    continue
                bad = False
                for p in fp.Pads():
                    v = p.GetPosition()
                    bb = p.GetBoundingBox()
                    rad = max(bb.GetWidth(), bb.GetHeight()) / 2e6
                    for hx, hy in holes:
                        if math.hypot(v.x / 1e6 - hx, v.y / 1e6 - hy) < \
                                SCREW_R + rad + HOLE_MARGIN:
                            bad = True
                if bad:
                    continue
                if any(not (x1 + CLR <= a or x0 - CLR >= c
                            or y1 + CLR <= b_ or y0 - CLR >= d)
                       for (a, b_, c, d) in obst):
                    continue
                return (x, y), math.hypot(x - ax, y - ay), want_flip
    return None, None, None


def main():
    b = pcbnew.LoadBoard(BOARD)
    out = b.GetBoardEdgesBoundingBox()
    X0, Y0 = out.GetLeft() / 1e6, out.GetTop() / 1e6
    W, H = out.GetWidth() / 1e6, out.GetHeight() / 1e6
    pitch = design.BOARD["MOUNT"]
    cx, cy = X0 + W / 2, Y0 + H / 2
    holes = [(cx + dx, cy + dy) for dx in (-pitch / 2, pitch / 2)
             for dy in (-pitch / 2, pitch / 2)]
    geom = (X0, Y0, W, H, holes)
    before = drc_classes(BOARD)

    u9 = b.FindFootprintByReference("U9")
    anchor = next(((p.GetPosition().x / 1e6, p.GetPosition().y / 1e6)
                   for p in u9.Pads() if p.GetNumber() == "1"), None)
    placed = []
    for ref, a, lim in (("U19", anchor, design.ADJACENCY["U19"][2]),
                        ("C74", None, design.ADJACENCY["C74"][2])):
        if a is None:
            u19 = b.FindFootprintByReference("U19")
            a = (u19.GetPosition().x / 1e6, u19.GetPosition().y / 1e6)
        xy, d, flip = place(b, ref, a, lim, geom, placed)
        if xy is None:
            print(f"{ref}: NO legal position within {lim} mm of its anchor.")
            print("REFUSING - a temperature sensor that is not against U9 measures the "
                  "room. Widen the bound deliberately or move something.")
            return 1
        print(f"{ref} -> ({xy[0]:.2f}, {xy[1]:.2f}) "
              f"{'B.Cu' if flip else 'F.Cu'}, {d:.2f} mm from its anchor "
              f"(bound {lim} mm)")
        placed.append(ref)

    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    bak = BOARD + ".tempbak"
    shutil.copy(BOARD, bak)
    b.Save(BOARD)
    after = drc_classes(BOARD)
    hb = {k: v for k, v in before.items() if k != "unconnected_items"}
    ha = {k: v for k, v in after.items() if k != "unconnected_items"}
    if ha != hb:
        shutil.copy(bak, BOARD)
        os.remove(bak)
        print(f"\nREFUSING TO SAVE - DRC hard errors moved {hb or 'none'} -> "
              f"{ha or 'none'}; board restored")
        return 1
    os.remove(bak)
    print(f"\nsaved - DRC hard errors unchanged ({ha or 'none'}), "
          f"{after.get('unconnected_items', 0)} unconnected (they are UNROUTED)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
