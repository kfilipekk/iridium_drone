#!/usr/bin/env python3
"""
Add a component to a board that is already routed, without regenerating it.

`gen_pcb.py` places every part from scratch, which on this board means discarding the
472/472 routing that took a full session to reach. For a two-part addition that is a
wildly disproportionate price, so this places the footprint into space that has been
verified clear, wires its pads from design.NETS, and routes only the new connections.

Placement is screened the same way tools/nudge_part.py screens a move - courtyard
overlap, copper clearance on the layers the pad actually occupies, and the solder mask
web - because all three bit during the C71 work and all three are cheap to test for.
Routing reuses the multi-layer A* in tools/move_net_pin.py.

Nets that are poured (GND and the rails) need no routing: the pad sits in the pour and
the zone fill connects it. Everything else is routed to the nearest existing pad on the
same net, and whole-board DRC decides whether the result stands.

The part must already exist in design.py - that file stays the source of truth, and this
tool only makes the board agree with it. That includes pads whose net CHANGED when the
part was added: giving PE15 a job renames it from PE15_SPARE to VTX_EN in design.py, and
until the board is told, the new part's gate sits on a net with nothing else on it and
DRC reports an unconnected item. Such a pad is reassigned automatically, but only when
its old net is genuinely empty - no copper and no other pads - so this can never quietly
detach something that was wired.

Usage:
  python3 tools/add_part.py --ref Q3 --at 128.5,125.25 [--side F] [--rot 0] [--apply]
  python3 tools/add_part.py --ref Q3 --near U18.3 [--apply]      # search for a spot
"""
import os, sys, re, math, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, design, fplib, shove, symlib
from move_net_pin import route_pad_to_pad, drc

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/addpart_backup.kicad_pcb"
TOMM  = route.TOMM
MM    = pcbnew.FromMM
POURED = {"GND", "+3V3", "+3V3A", "+5V", "+9V", "VBAT", "VDDA", "VBUS"}
MASK_GAP = 0.28


def load_fp(board, ref):
    lib_id, fpid, val, lcsc, dnp = design.COMPONENTS[ref]
    path = fplib.find(fpid)
    fp = pcbnew.FootprintLoad(os.path.dirname(path),
                              os.path.basename(path)[:-len(".kicad_mod")])
    if fp is None:
        raise SystemExit(f"could not load footprint {fpid} for {ref}")
    fp.SetReference(ref)
    fp.SetValue(val)
    return fp


def courtyards(board, skip=None):
    """Occupied boxes PER SIDE. Courtyard overlap is a per-side rule - a part on the
    bottom does not stop one going on the top above it, and treating them as one set
    made most of the board look full when it is not."""
    out = {"F": [], "B": []}
    for fp in board.GetFootprints():
        if skip and fp.GetReference() == skip:
            continue
        side = "B" if fp.IsFlipped() else "F"
        poly = None
        for lay in (pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd,):
            try:
                poly = fp.GetCourtyard(lay)
            except Exception:
                poly = None
        box = None
        if poly is not None and poly.OutlineCount():
            bb = poly.BBox()
            box = (TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                   TOMM(bb.GetRight()), TOMM(bb.GetBottom()))
        pxs, pys = [], []
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            pxs += [TOMM(bb.GetLeft()), TOMM(bb.GetRight())]
            pys += [TOMM(bb.GetTop()), TOMM(bb.GetBottom())]
        if pxs:
            pb = (min(pxs)-0.25, min(pys)-0.25, max(pxs)+0.25, max(pys)+0.25)
            box = pb if box is None else (min(box[0], pb[0]), min(box[1], pb[1]),
                                          max(box[2], pb[2]), max(box[3], pb[3]))
        if box:
            out[side].append(box)
    return out


def fits(board, fp, x, y, yards, idx, pidx):
    """Courtyard, copper and mask checks for the footprint at this position."""
    fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    got = None
    for side in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        poly = fp.GetCourtyard(side)
        if poly.OutlineCount():
            bb = poly.BBox()
            got = (TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                   TOMM(bb.GetRight()), TOMM(bb.GetBottom()))
            break
    # Not every JLC footprint declares a courtyard - the 0402s do not - and some declare
    # one SMALLER than their own pads. gen_pcb.py handles both by taking the larger of
    # the courtyard and the pad extent, so do the same here rather than refusing.
    pxs, pys = [], []
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        pxs += [TOMM(bb.GetLeft()), TOMM(bb.GetRight())]
        pys += [TOMM(bb.GetTop()), TOMM(bb.GetBottom())]
    if pxs:
        pad_box = (min(pxs) - 0.25, min(pys) - 0.25, max(pxs) + 0.25, max(pys) + 0.25)
        got = pad_box if got is None else (
            min(got[0], pad_box[0]), min(got[1], pad_box[1]),
            max(got[2], pad_box[2]), max(got[3], pad_box[3]))
    if got is None:
        return False, "footprint has neither a courtyard nor pads"
    x1, y1, x2, y2 = got
    # Check the WHOLE extent against the outline, not two corners. route.inside_board
    # also excludes the rounded corners and the four M3 mounting holes, and a two-corner
    # test walked straight past that: the first candidate this tool produced sat on top
    # of the hole at (137.75, 138.25).
    steps = 6
    for i in range(steps + 1):
        for j in range(steps + 1):
            qx = x1 + (x2 - x1) * i / steps
            qy = y1 + (y2 - y1) * j / steps
            if not route.inside_board(qx, qy, 0.3):
                return False, "off the board, or over a corner radius or mounting hole"
    for a1, b1, a2, b2 in yards:
        if x1 < a2 and a1 < x2 and y1 < b2 and b1 < y2:
            return False, "courtyard overlap"
    for pad in fp.Pads():
        p = pad.GetPosition()
        px, py = TOMM(p.x), TOMM(p.y)
        bb = pad.GetBoundingBox()
        hw = TOMM(bb.GetRight() - bb.GetLeft()) / 2
        hh = TOMM(bb.GetBottom() - bb.GetTop()) / 2
        ls = frozenset(L for L in shove.COPPER if pad.IsOnLayer(board.GetLayerID(L)))
        nm = design.NETS and _net_for(fp.GetReference(), pad.GetNumber())
        need = route.CLEAR + 0.005
        for u in range(-4, 5):
            for v in (-1, 1):
                for qx, qy in ((px + hw*u/4.0, py + hh*v), (px + hw*v, py + hh*u/4.0)):
                    for sh in idx.near(qx, qy, need + 1.0):
                        if sh.net == nm or not (sh.lset & ls):
                            continue
                        if route.gap_to_shape(qx, qy, sh.geom) < need:
                            return False, f"pad {pad.GetNumber()} clears only "
        for sh in pidx.near(px, py, MASK_GAP + 1.0):
            if sh.net != nm and route.gap_to_shape(px, py, sh.geom) < MASK_GAP:
                return False, f"pad {pad.GetNumber()} bridges the solder mask"
    return True, "ok"


# design.py names MCU pins by their FUNCTION ("U1.PE15") while the footprint numbers its
# pads ("U1.45"). Every tool that touches both has to translate, so do it once here.
_PAD_OF_PIN = None
def _u1_pad(name):
    global _PAD_OF_PIN
    if _PAD_OF_PIN is None:
        _PAD_OF_PIN = {}
        for pn in symlib.load()["STM32H743VIT6_C114409"]:
            # keyed BOTH ways. design.py writes the oscillator pins in full
            # ("PH0-OSC_IN"); keying only on the part before the hyphen returned None
            # for them, and a caller that read None as "no net" cut the crystal tracks.
            _PAD_OF_PIN[pn["name"]] = pn["num"]
            _PAD_OF_PIN[pn["name"].split("-")[0]] = pn["num"]
    return _PAD_OF_PIN.get(name, name)


def board_pad(spec):
    """'U1.PE15' -> ('U1', '45'); anything else passes through unchanged."""
    ref, pad = spec.split(".", 1)
    return ref, (_u1_pad(pad) if ref == "U1" else pad)


_NET_OF = {}
def _net_for(ref, pad):
    if not _NET_OF:
        for n, specs in design.NETS.items():
            for sp in specs:
                r, p = board_pad(sp)
                _NET_OF[f"{r}.{p}"] = n
    return _NET_OF.get(f"{ref}.{pad}")


def commit(board, routes):
    for nm, (runs, vias), _note, _tgt in routes:
        n = board.FindNet(nm)
        for lay, pts in runs:
            for k in range(len(pts) - 1):
                route.add_track(board, pts[k], pts[k+1], lay, n, width=route.TRACK_W)
        for vx, vy in vias:
            v = route.add_via(board, vx, vy, n)
            v.SetWidth(MM(0.45)); v.SetDrill(MM(0.20))
    route.fill(board)


def _reassign_nets(board, fp, ref):
    """Re-apply the design.py net changes after a board reload."""
    my = {_net_for(ref, q.GetNumber()) for q in fp.Pads()} - {None}
    for want in sorted(my):
        for spec in design.NETS.get(want, []):
            oref, onum = board_pad(spec)
            if oref == ref:
                continue
            ofp = board.FindFootprintByReference(oref)
            if ofp is None:
                continue
            opad = next((q for q in ofp.Pads() if q.GetNumber() == onum), None)
            if opad is None or (opad.GetNet()
                                and opad.GetNet().GetNetname() == want):
                continue
            n = board.FindNet(want)
            if n is None:
                n = pcbnew.NETINFO_ITEM(board, want)
                board.Add(n)
            opad.SetNet(n)


def try_routes(board, fp, ref, x, y):
    """Place at (x,y), wire the pads, and route everything that needs routing.

    Returns (routes, None) or (None, why). Poured nets need no route - the pad sits in
    the pour and the zone fill connects it.
    """
    fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    out, planned = [], []
    for pad in fp.Pads():
        nm = _net_for(ref, pad.GetNumber())
        if nm is None:
            continue
        n = board.FindNet(nm)
        if n is None:
            n = pcbnew.NETINFO_ITEM(board, nm)
            board.Add(n)
        pad.SetNet(n)
    for pad in fp.Pads():
        nm = _net_for(ref, pad.GetNumber())
        if nm is None or nm in POURED:
            continue
        mp = (TOMM(pad.GetPosition().x), TOMM(pad.GetPosition().y))
        best = None
        for f in board.GetFootprints():
            if f.GetReference() == ref:
                continue
            for q in f.Pads():
                if not q.GetNet() or q.GetNet().GetNetname() != nm:
                    continue
                dd = math.hypot(TOMM(q.GetPosition().x) - mp[0],
                                TOMM(q.GetPosition().y) - mp[1])
                if best is None or dd < best[0]:
                    best = (dd, f"{f.GetReference()}.{q.GetNumber()}", q)
        if best is None:
            continue
        res, note = route_pad_to_pad(board, pad, best[2], nm, 0.05, extra=planned)
        if res is None:
            return None, f"pad {pad.GetNumber()} ({nm}): {note}"
        # feed this route forward so the next one routes around it
        runs, vias = res
        for lay, pts in runs:
            for k in range(len(pts) - 1):
                planned.append(shove.Shape(
                    ("cap", pts[k][0], pts[k][1], pts[k+1][0], pts[k+1][1],
                     route.TRACK_W/2), "track", nm, layer=lay,
                    lset=frozenset([lay])))
        for vx, vy in vias:
            planned.append(shove.Shape(("cap", vx, vy, vx, vy, 0.225), "via", nm))
        out.append((nm, res, note, best[1]))
    return out, None


def main():
    def arg(name, default=None):
        return sys.argv[sys.argv.index(name)+1] if name in sys.argv else default
    ref = arg("--ref")
    apply = "--apply" in sys.argv
    side = arg("--side", "F")
    rot = float(arg("--rot", "0"))
    route_budget = int(arg("--tries", "25"))
    if not ref or ref not in design.COMPONENTS:
        print(f"--ref must name a part in design.py"); return 2
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, _ = drc()
    print(f"baseline {hard0} errors, {un0} unconnected")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    if board.FindFootprintByReference(ref):
        print(f"  {ref} is already on the board"); return 1

    allsh = shove.shapes_of(board)
    idx = shove.ShapeIndex(allsh)
    pidx = shove.ShapeIndex([s for s in allsh if s.kind == "pad"])
    yards_all = courtyards(board)

    fp = load_fp(board, ref)
    board.Add(fp)
    if side == "B":
        fp.Flip(pcbnew.VECTOR2I(0, 0), False)
    if rot:
        fp.SetOrientationDegrees(rot)

    # where to put it
    cands = []
    if arg("--at"):
        x, y = (float(v) for v in arg("--at").split(","))
        cands = [(0.0, x, y)]
    else:
        spec = arg("--near")
        if not spec:
            print("  need --at X,Y or --near REF.PAD"); return 2
        tref, tnum = spec.split(".", 1)
        tfp = board.FindFootprintByReference(tref)
        tp = next(q for q in tfp.Pads() if q.GetNumber() == tnum)
        tx, ty = TOMM(tp.GetPosition().x), TOMM(tp.GetPosition().y)
        BD = design.BOARD
        step = 0.25
        gx = BD["X0"] + 1.0
        while gx < BD["X0"] + BD["W"] - 1.0:
            gy = BD["Y0"] + 1.0
            while gy < BD["Y0"] + BD["H"] - 1.0:
                cands.append((math.hypot(gx - tx, gy - ty), gx, gy))
                gy += step
            gx += step
        cands.sort()

    # Bring any pad whose net changed in design.py into line first, before anything
    # else looks at nets.
    # part's nets have the members design.py says they have.
    reassigned = []
    my_nets = {_net_for(ref, q.GetNumber()) for q in fp.Pads()} - {None}
    for want in sorted(my_nets):
        for pad_spec in design.NETS.get(want, []):
            oref, onum = board_pad(pad_spec)
            if oref == ref:
                continue
            ofp = board.FindFootprintByReference(oref)
            if ofp is None:
                continue
            opad = next((q for q in ofp.Pads() if q.GetNumber() == onum), None)
            if opad is None:
                continue
            cur = opad.GetNet().GetNetname() if opad.GetNet() else ""
            if cur == want:
                continue
            code = opad.GetNetCode()
            tracks = [t for t in board.GetTracks() if t.GetNetCode() == code]
            siblings = [f"{f.GetReference()}.{q.GetNumber()}"
                        for f in board.GetFootprints() for q in f.Pads()
                        if q.GetNetCode() == code
                        and (f.GetReference(), q.GetNumber()) != (oref, onum)]
            if tracks or siblings:
                print(f"  refusing to move {pad_spec} from '{cur}' to '{want}': that "
                      f"net has {len(tracks)} track(s) and {len(siblings)} other pad(s)")
                return 1
            n = board.FindNet(want)
            if n is None:
                n = pcbnew.NETINFO_ITEM(board, want)
                board.Add(n)
            opad.SetNet(n)
            reassigned.append((pad_spec, cur, want))
    for spec, was, now in reassigned:
        print(f"     {spec}: net '{was}' -> '{now}' (design.py gave it a job)")


    # Placement and routing are ONE search, not two steps. The first position that fits
    # geometrically is not necessarily one the new pads can be routed from - the first
    # candidate for Q3 fitted fine and then could not reach the MCU pin 20 mm away. So
    # each candidate is placed AND routed, and only a position where everything routes
    # is accepted.
    # When applying, the DRC check belongs INSIDE this loop. A position can place and
    # route perfectly and still be wrong: Q3's first working position laid copper that
    # cut the ground pour into two orphan islands. Accepting the first routable spot and
    # then rolling back means giving up on a problem the next spot would not have had.
    placed, routes, reasons = None, None, {}
    tried = 0
    for d, x, y in cands:
        ok, why = fits(board, fp, x, y, yards_all[side], idx, pidx)
        if not ok:
            k = why.split(" clears only")[0]
            reasons[k] = reasons.get(k, 0) + 1
            continue
        if tried >= route_budget:
            break
        tried += 1
        got, fail = try_routes(board, fp, ref, x, y)
        if got is None:
            reasons[fail] = reasons.get(fail, 0) + 1
            continue
        if not apply:
            placed, routes = (x, y, d), got
            break
        shutil.copy(BOARD, BAK)
        commit(board, got)
        board.Save(BOARD)
        hard, un, txt = drc()
        if hard <= hard0 and un <= un0:
            placed, routes = (x, y, d), got
            print(f"  {ref} at ({x:.2f},{y:.2f}) on {side}.Cu"
                  + (f", {d:.2f} mm from {arg('--near')}" if arg("--near") else ""))
            for spec, was, now in reassigned:
                print(f"     {spec}: net '{was}' -> '{now}' (design.py gave it a job)")
            for nm, note, tgt in [(r[0], r[2], r[3]) for r in got]:
                print(f"     -> {tgt} ({nm}): {note}")
            print(f"  added {ref} -> {hard} errors, {un} unconnected")
            return 0
        bad = [z for z in re.split(r'^\[', txt, flags=re.M)
               if z and not z.startswith("unconnected_items")
               and not z.startswith("** ")]
        why = (bad[0].splitlines()[0] if bad
               else f"{un - un0} new unconnected item(s)")
        reasons[why] = reasons.get(why, 0) + 1
        print(f"     ({x:.2f},{y:.2f}): +{hard-hard0} err, {un} unconn - {why}")
        shutil.copy(BAK, BOARD)
        board = pcbnew.LoadBoard(BOARD)
        route.set_rules(board)
        fp = load_fp(board, ref)
        board.Add(fp)
        if side == "B":
            fp.Flip(pcbnew.VECTOR2I(0, 0), False)
        if rot:
            fp.SetOrientationDegrees(rot)
        _reassign_nets(board, fp, ref)
    if placed is None:
        print(f"  nowhere to put {ref} on {side}.Cu that also routes and verifies "
              f"({tried} position(s) routed):")
        for w, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:5]:
            print(f"     {n:5} positions: {w}")
        return 1
    x, y, d = placed
    print(f"  {ref} at ({x:.2f},{y:.2f}) on {side}.Cu"
          + (f", {d:.2f} mm from {arg('--near')}" if arg("--near") else ""))
    for spec, was, now in reassigned:
        print(f"     {spec}: net '{was}' -> '{now}' (design.py gave it a job)")
    for nm, note, tgt in [(r[0], r[2], r[3]) for r in routes]:
        print(f"     -> {tgt} ({nm}): {note}")

    if not apply:
        print("\ndry run - pass --apply to write the board")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
