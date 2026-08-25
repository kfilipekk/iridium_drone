#!/usr/bin/env python3
"""
Take out the trace that seals the last ground island, so the pour can simply flow in.

Every earlier attempt asked the same question - "where can a via go inside this
island?" - and the answer stayed no. It was the wrong question. The island is sealed on
B.Cu by ordinary traces, and the one via position that would free it is exactly the
corridor BUCK_EN needs to reach R5.1, so via-hunting can never win here.

The right question is which trace to remove so the pour reaches the island by itself.
Measured at C71.2's pad, the nearest foreign copper is a BUCK9_COMP2 trace 0.1164 mm
away and another at 0.2120 mm - the compensation net runs between C71 and C72 straight
past the ground pad it is stranding. Take that away and the corridor opens.

So: rip a candidate trace, re-flood the island, and if the pour can now reach the main
body, put the trace back somewhere it does not seal anything. Two ways, gentlest first:

  shove  - bow the trace aside by a couple of tenths of a millimetre, keeping its shape
           and both endpoints. The escape corridor here is only 0.24 mm long, so the
           trace only has to step out of a very small gap.
  reroute - throw the route away and find another across all four signal layers.

Shoving is tried first because it disturbs almost nothing; rerouting is the fallback.
Either way both endpoints stay exactly where they were, so whatever the trace connected
to stays connected.

Victims are tried least-sensitive first, which is a judgement worth stating rather than
burying. BUCK_EN is a static enable - lengthening it costs nothing. BUCK9_COMP2 is the
regulator's compensation node: high impedance and noise sensitive, so a longer route is
a real if modest trade, and it is only taken if nothing else works. Feedback nets
(BUCK9_FB) are never ripped - that one node is worth more than a tidy DRC report.

Usage:  python3 tools/open_pocket.py [--apply] [--grid MM] [--reach MM]
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove, island_route as ir, island_via as iv, rip_route as rr

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/open_backup.kicad_pcb"
RPT   = "/tmp/nav/open.rpt"
TOMM  = route.TOMM
NET   = "GND"
NEVER = ("_FB", "VREF", "VCAP")          # nets whose routing is not worth disturbing


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def sensitivity(net):
    """Lower is safer to reroute. Stated plainly so the ordering is reviewable."""
    if any(k in net for k in NEVER):
        return 99
    if "_EN" in net or "BOOT" in net or "RESET" in net:
        return 0          # static levels; length is irrelevant
    if "COMP" in net:
        return 5          # compensation node: high impedance, keep short if possible
    return 2


def main():
    apply = "--apply" in sys.argv
    step = float(sys.argv[sys.argv.index("--grid")+1]) if "--grid" in sys.argv else 0.02
    reach = float(sys.argv[sys.argv.index("--reach")+1]) if "--reach" in sys.argv else 1.5
    os.makedirs("/tmp/nav", exist_ok=True)

    hard0, un0, _ = drc()
    print(f"baseline {hard0} errors, {un0} unconnected\n")

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    route.fill(board)
    polys = ir.gnd_polys(board)
    isls = ir.orphans(board, polys)
    if not isls:
        print("no orphaned ground islands left")
        return 0
    allsh = shove.shapes_of(board, exclude_net=NET)      # for the ground escape
    allsh_full = shove.shapes_of(board)                  # for rerouting a signal
    chains, cindex = shove.build_chains(board)

    for lname, _pi, isl, a in isls:
        xs = [p[0] for p in isl]; ys = [p[1] for p in isl]
        box = (min(xs), min(ys), max(xs), max(ys))
        cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
        print(f"=== {lname} {a:.2f} mm2 at ({box[0]:.2f},{box[1]:.2f})")

        # traces on this layer running close enough to be part of the seal
        vict = []
        for ci, ch in enumerate(chains):
            if ch["layer"] != lname or ch["net"] == NET:
                continue
            d = min(math.hypot(px-cx, py-cy) for px, py in ch["pts"])
            if d > max(box[2]-box[0], box[3]-box[1])/2 + reach:
                continue
            s = sensitivity(ch["net"])
            if s >= 99:
                continue
            vict.append((s, d, ci))
        vict.sort()
        print(f"    {len(vict)} trace(s) on {lname} near enough to be the seal: "
              + ", ".join(f"{chains[c]['net']}({s})" for s, _d, c in vict[:8]))

        main_cells = [q for q in polys.get(lname, []) if ir.area(q) > 50.0]
        for s, d, ci in vict:
            ch = chains[ci]
            mine = {(x.p1, x.p2) for x in rr.chain_shapes(ch)}
            keep = [x for x in allsh
                    if not (x.layer == lname and x.p1 is not None
                            and (x.p1, x.p2) in mine)]
            g = ir.Grid(board, lname, box, step, keep, 4.0)
            src, cells = iv.pocket(g, isl)
            tgt = [c for c in cells
                   if any(ir.inside(q, *g.pos(*c)) for q in main_cells)]
            if not tgt:
                print(f"    ripping {ch['net']} does not open it "
                      f"({len(cells)} cells still sealed)")
                continue
            # shortest ground escape through the freed corridor
            dist, prev = shove.spread(g, src)
            best = min((dist[c], c) for c in tgt if c in dist)
            esc = shove.straighten(shove.walk_back(g, prev, best[1]))
            print(f"    ripping {ch['net']}/{lname} opens it: ground escapes in "
                  f"{best[0]*step:.2f} mm ({len(esc)-1} segments)")

            extra = [shove.Shape(("cap", esc[k][0], esc[k][1], esc[k+1][0], esc[k+1][1],
                                  route.TRACK_W/2), "track", NET, layer=lname,
                                 lset=frozenset([lname]))
                     for k in range(len(esc)-1)]

            # Gentlest first: can the trace simply step out of the corridor?
            mid = ((esc[0][0] + esc[-1][0]) / 2, (esc[0][1] + esc[-1][1]) / 2)
            runs, rvias, how = None, [], None
            others = [x for x in allsh_full
                      if not (x.layer == lname and x.p1 is not None
                              and (x.p1, x.p2) in mine) and x.net != ch["net"]]
            oidx = shove.ShapeIndex(others)
            eg = [x.geom for x in extra]
            for flat in shove.FLATS:
                off = 0.10
                while off <= shove.MAX_OFFSET:
                    for flip in (False, True):
                        got = shove.shove_chain(ch["pts"], mid, off, flip=flip,
                                                flat=flat)
                        if got is None:
                            continue
                        newpts, detour = got
                        hit = shove.polyline_hits(detour, others, ch["width"], eg,
                                                  layer=lname, index=oidx,
                                                  skip_net=ch["net"])
                        if hit:
                            continue
                        # does the pocket actually open with the trace in its new place?
                        moved = [shove.Shape(("cap", newpts[k][0], newpts[k][1],
                                              newpts[k+1][0], newpts[k+1][1],
                                              ch["width"]/2), "track", ch["net"],
                                             layer=lname, lset=frozenset([lname]))
                                 for k in range(len(newpts)-1)]
                        g2 = ir.Grid(board, lname, box, step, keep + moved, 4.0)
                        s2, c2 = iv.pocket(g2, isl)
                        t2 = [c for c in c2
                              if any(ir.inside(q, *g2.pos(*c)) for q in main_cells)]
                        if not t2:
                            continue
                        d2, p2 = shove.spread(g2, s2)
                        b2 = min((d2[c], c) for c in t2 if c in d2)
                        esc = shove.straighten(shove.walk_back(g2, p2, b2[1]))
                        runs = [(lname, newpts)]
                        how = f"shoved {off:.2f} mm aside"
                        break
                    if runs:
                        break
                    off += 0.05
                if runs:
                    break
            if runs is None:
                res, note = rr.reroute(board, ch, allsh_full, extra, max(step, 0.05))
                if res is None:
                    print(f"       but {ch['net']} can neither be shoved out of the "
                          f"corridor nor rerouted: {note}")
                    continue
                runs, rvias = res
                how = f"rerouted as {note}"
            print(f"       {ch['net']} {how}")
            if not apply:
                break

            shutil.copy(BOARD, BAK)
            bd = pcbnew.LoadBoard(BOARD)
            route.set_rules(bd)
            doomed_keys = set()
            for k in range(len(ch["pts"]) - 1):
                p, q = ch["pts"][k], ch["pts"][k+1]
                doomed_keys.add((ch["net"], ch["layer"], tuple(sorted(
                    [(shove.Q(p[0]*1e6), shove.Q(p[1]*1e6)),
                     (shove.Q(q[0]*1e6), shove.Q(q[1]*1e6))]))))
            doomed = []
            for t in bd.GetTracks():
                if t.Type() == pcbnew.PCB_VIA_T:
                    continue
                nx = t.GetNet()
                aa, bb = t.GetStart(), t.GetEnd()
                k = (nx.GetNetname() if nx else "", bd.GetLayerName(t.GetLayer()),
                     tuple(sorted([(shove.Q(aa.x), shove.Q(aa.y)),
                                   (shove.Q(bb.x), shove.Q(bb.y))])))
                if k in doomed_keys:
                    doomed.append(t)
            for t in doomed:
                bd.Remove(t)
            cnet = bd.FindNet(ch["net"])
            for lay, pts in runs:
                for k in range(len(pts) - 1):
                    route.add_track(bd, pts[k], pts[k+1], lay, cnet, width=ch["width"])
            for vx, vy in rvias:
                rv = route.add_via(bd, vx, vy, cnet)
                rv.SetWidth(pcbnew.FromMM(0.45)); rv.SetDrill(pcbnew.FromMM(0.20))
            gnet = bd.FindNet(NET)
            for k in range(len(esc) - 1):
                route.add_track(bd, esc[k], esc[k+1], lname, gnet, width=route.TRACK_W)
            route.fill(bd)
            bd.Save(BOARD)
            hard, un, txt = drc()
            if hard <= hard0 and un < un0:
                print(f"       -> {un} unconnected, {hard} errors "
                      f"({len(doomed)} segments rerouted)")
                un0 = un
                break
            bad = [z for z in re.split(r'^\[', txt, flags=re.M)
                   if z and not z.startswith("unconnected_items")
                   and not z.startswith("** ")]
            print(f"       -> +{hard-hard0} err, {un} unconn"
                  + (f": {bad[0].splitlines()[0]}" if bad else ""))
            shutil.copy(BAK, BOARD)

    hard, un, _ = drc()
    print(f"\n{hard} errors, {un} unconnected")
    if not apply:
        print("dry run - pass --apply to write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
