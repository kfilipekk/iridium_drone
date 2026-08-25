#!/usr/bin/env python3
"""
Widen a power net's traces to whatever the surrounding clearance allows.

tools/route.py lays every track at TRACK_W (4 mil), because that is the design rule and
the router has no notion of current. A 4 mil 1 oz trace carries about 0.45 A. VBAT has to
carry ~1.7 A on 4S and +5V up to the 3 A its regulator can source, so the rails were
routed at roughly a quarter of the copper they need.

Widening is the safest possible fix: it changes no topology, adds no vias, moves nothing.
A segment either has room to grow or it does not, and nothing that was connected can
become disconnected. What it cannot do is fix a route that is hemmed in along its whole
length - for that the rail needs the In4.Cu pour extended to it, which is a separate job.

Each segment is grown independently to the widest value its own surroundings permit:

    half-width' <= (distance from centre line to nearest foreign copper) - CLEAR

sampled along the segment. The whole net is then committed at once and checked by
whole-board DRC, because widening changes where the zones can fill and that can strand a
pour island. Rolled back as a unit if anything regresses.

Usage:
  python3 tools/widen_net.py --net VBAT [--target 1.7] [--max 1.0] [--apply]
  python3 tools/widen_net.py --all [--apply]
"""
import os, re, sys, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, design, shove

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/widen_backup.kicad_pcb"
RPT   = "/tmp/nav/widen.rpt"
TOMM  = route.TOMM
STEPS = [0.1016, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.80, 1.00]


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def capacity(width_mm, internal, dT=10.0):
    """IPC-2221 current for 1 oz copper at a given trace width."""
    k = 0.024 if internal else 0.048
    area = (width_mm / 0.0254) * 1.37          # mil^2
    return k * (dT ** 0.44) * (area ** 0.725)


EDGE_CLEAR = 0.30          # board setup: copper to board edge


def widest_here(pts, idx, netname, layer, cap_mm, kos=()):
    """The widest step this segment can take and still clear everything.

    Evaluates the candidate widths directly rather than solving for a maximum, because
    the board-edge rule depends on the width itself: a wider trace needs its own half
    width PLUS the edge clearance, and checking the centre line at a fixed margin let
    five +5V segments grow into the board outline.
    """
    samples = list(shove._walk(pts, 0.05))
    best = route.TRACK_W
    for w in STEPS:
        if w > cap_mm:
            break
        ok = True
        for x, y in samples:
            if not route.inside_board(x, y, w/2 + EDGE_CLEAR):
                ok = False; break
            if any(x1 - w/2 < x < x2 + w/2 and y1 - w/2 < y < y2 + w/2
                   for x1, y1, x2, y2 in kos):
                ok = False; break
            need = w/2 + route.CLEAR
            for sh in idx.near(x, y, need + 1.0):
                if sh.net == netname or layer not in sh.lset:
                    continue
                if route.gap_to_shape(x, y, sh.geom) < need:
                    ok = False; break
            if not ok:
                break
        if not ok:
            break
        best = w
    return best


def main():
    def arg(name, default=None):
        return sys.argv[sys.argv.index(name)+1] if name in sys.argv else default
    apply = "--apply" in sys.argv
    cap_mm = float(arg("--max", "1.0"))
    nets = ([arg("--net")] if arg("--net")
            else sorted(design.NET_CURRENT) if "--all" in sys.argv else None)
    if not nets or nets == [None]:
        print(__doc__.strip().splitlines()[-2]); return 2
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, _ = drc()
    print(f"baseline {hard0} errors, {un0} unconnected\n")

    for netname in nets:
        # Try the generous cap first and fall back. Widening changes where the zones can
        # fill, and on the densest rails that strands a pour island - which is a real
        # regression, but not a reason to leave the rail at 4 mil when a smaller step
        # would have been fine.
        for cap in [c for c in (cap_mm, 0.60, 0.40, 0.30, 0.25, 0.20, 0.15)
                    if c <= cap_mm]:
            board = pcbnew.LoadBoard(BOARD)
            route.set_rules(board)
            n = board.FindNet(netname)
            if n is None:
                print(f"  {netname}: no such net"); break
            want = float(arg("--target", "0")) or design.NET_CURRENT.get(netname, 0.0)

            allsh = shove.shapes_of(board)
            idx = shove.ShapeIndex(allsh)
            kos = route.keepout_boxes(board)
            plan = []
            for t in board.GetTracks():
                if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != n.GetNetCode():
                    continue
                lay = board.GetLayerName(t.GetLayer())
                a = (TOMM(t.GetStart().x), TOMM(t.GetStart().y))
                b = (TOMM(t.GetEnd().x), TOMM(t.GetEnd().y))
                if math.hypot(b[0]-a[0], b[1]-a[1]) < 1e-9:
                    continue
                w = widest_here([a, b], idx, netname, lay, cap, kos)
                if w > TOMM(t.GetWidth()) + 1e-9:
                    plan.append((a, b, lay, w))
            if not plan:
                print(f"  {netname}: nothing more can be widened"); break

            widths = sorted(w for _a, _b, _l, w in plan)
            msg = (f"  {netname}: {len(plan)} segment(s) can grow to <= {cap:.2f} mm; "
                   f"narrowest result {widths[0]:.4f} mm "
                   f"(~{capacity(widths[0], False):.2f} A), needs {want:.1f} A")
            if not apply:
                print(msg); break
            shutil.copy(BOARD, BAK)
            want_keys = {(a, b, lay): w for a, b, lay, w in plan}
            done = 0
            for t in board.GetTracks():
                if t.Type() == pcbnew.PCB_VIA_T or t.GetNetCode() != n.GetNetCode():
                    continue
                lay = board.GetLayerName(t.GetLayer())
                a = (TOMM(t.GetStart().x), TOMM(t.GetStart().y))
                b = (TOMM(t.GetEnd().x), TOMM(t.GetEnd().y))
                w = want_keys.get((a, b, lay))
                if w:
                    t.SetWidth(pcbnew.FromMM(w)); done += 1
            route.fill(board)
            board.Save(BOARD)
            hard, un, txt = drc()
            if hard <= hard0 and un <= un0:
                print(msg)
                print(f"     widened {done} segment(s) -> {hard} errors, {un} unconnected")
                break
            bad = [z for z in re.split(r'^\[', txt, flags=re.M)
                   if z and not z.startswith("unconnected_items")
                   and not z.startswith("** ")]
            print(f"     cap {cap:.2f} mm: +{hard-hard0} err, {un} unconn"
                  + (f" - {bad[0].splitlines()[0]}" if bad else "") + "; trying narrower")
            shutil.copy(BAK, BOARD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
