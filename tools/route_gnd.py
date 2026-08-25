#!/usr/bin/env python3
"""
Connect stranded GND pads by routing a short trace to the nearest GND copper.

Some GND pads - notably U1's VSS pins and the decoupling packed within 2 mm of every
VDD pin - are enclosed by neighbouring copper. No via fits beside them (tested down to
0.4 mm), and the pour cannot reach in. What a person does here is run a short trace out
to the nearest bit of the same net, so that is what this does, using the multi-target
router (goal = ANY cell already owned by GND).

DRC is checked per pad and the trace is rolled back if it introduces an error.
"""
import os, sys, math, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK = "/tmp/navcore_gnd_bak.kicad_pcb"


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/gnd_drc.rpt",
                    "--severity-error", BOARD], capture_output=True, timeout=600)
    t = open("/tmp/gnd_drc.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def stranded(rpt):
    """(ref, pad) pairs the DRC report calls unconnected, for one net."""
    out = set()
    for m in re.finditer(r'Pad (\S+) \[([^\]]+)\] of (\w+)', open(rpt).read()):
        pad, net, ref = m.groups()
        out.add((ref, pad, net))
    return out


def main():
    net_filter = sys.argv[1] if len(sys.argv) > 1 else "GND"
    h0, u0 = drc()
    print(f"baseline: {h0} hard DRC errors, {u0} unconnected")
    todo = [(r, p) for r, p, n in stranded("/tmp/gnd_drc.rpt") if n == net_filter]
    print(f"{len(todo)} stranded {net_filter} pads\n")

    kept = failed = 0
    for ref, padname in sorted(todo):
        shutil.copy(BOARD, BAK)
        b = pcbnew.LoadBoard(BOARD); route.set_rules(b)
        net = b.FindNet(net_filter)
        if net is None: break
        code = net.GetNetCode()
        pad = None
        for fp in b.GetFootprints():
            if fp.GetReference() != ref: continue
            for pd in fp.Pads():
                if pd.GetPadName() == padname: pad = pd
        if pad is None: failed += 1; continue

        r = route.Router(b)
        # goal: any cell already owned by this net (its other pads, tracks, vias)
        pts = []
        for fp in b.GetFootprints():
            for pd in fp.Pads():
                if pd.GetNet() and pd.GetNet().GetNetCode() == code and pd is not pad:
                    p = pd.GetPosition(); pts.append((route.TOMM(p.x), route.TOMM(p.y)))
        for t in b.GetTracks():
            if t.GetNet() and t.GetNet().GetNetCode() == code:
                p = t.GetPosition(); pts.append((route.TOMM(p.x), route.TOMM(p.y)))
        goals = r.cells_of_net(code, pts)
        if not goals: failed += 1; continue

        p = pad.GetPosition()
        A = (route.TOMM(p.x), route.TOMM(p.y))
        path = None
        for vc in (8, 3, 20):
            path = r.route_to_any(code, A, goals, via_cost=vc)
            if path: break
        if not path:
            failed += 1; print(f"  {ref}.{padname:<4} no path"); continue

        r.commit(code, net, path)
        route.fill(b); b.Save(BOARD)
        h, u = drc()
        if h > h0:
            shutil.copy(BAK, BOARD); failed += 1
            print(f"  {ref}.{padname:<4} rolled back (+{h-h0} err)")
        else:
            kept += 1
            print(f"  {ref}.{padname:<4} routed        unconnected now {u}")

    h, u = drc()
    print(f"\nkept {kept}, failed {failed} -> {h} hard DRC errors, {u} unconnected")


if __name__ == "__main__":
    main()
