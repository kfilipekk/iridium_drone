#!/usr/bin/env python3
"""
Clear residual DRC violations by ripping the copper that causes them.

freerouting reports zero violations against its own model and KiCad still finds a
handful - clearances of 0.0827 mm against a 0.1016 mm rule, for instance. The
difference is rounding through the DSN/SES round trip and a slightly different idea
of where a pad ends. They are always a fraction of a micron short, never gross.

Rather than nudge geometry, the offending track is deleted. route_remaining.py can
then re-route that connection under KiCad's own rules, which is the only model that
matters. A ripped-and-not-replaced connection costs one unconnected item; a shipped
clearance violation costs a board.

Vias and pads are never ripped - a via is usually the only thing tying a net to its
plane, and a pad cannot move. Those need placement work instead.

Usage:  python3 tools/fix_drc.py [--apply]
"""
import os, sys, re, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/nav/fixdrc_backup.kicad_pcb"
RPT   = "/tmp/nav/fixdrc.rpt"
RIPPABLE = ("clearance", "shorting_items", "tracks_crossing",
            "track_dangling", "copper_edge_clearance")
# hole_clearance is the one case where the VIA itself is the defect - it is drilled
# too close to another hole and no amount of re-routing around it helps. fanout()
# and stitch() now understand hole-to-hole clearance, so a ripped via gets replaced
# somewhere legal on the next pass.
VIA_RIPPABLE = ("hole_clearance",)


def drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", RPT,
                    "--severity-error", BOARD], capture_output=True, timeout=900)
    t = open(RPT).read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), \
           cls.count("unconnected_items"), t


def offenders(text):
    """Tracks and vias named in violations we are willing to rip."""
    tracks, vias = [], []
    parts = re.split(r'^\[([a-z_]+)\]', text, flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        kind, body = parts[i], parts[i + 1]
        if kind in RIPPABLE:
            for m in re.finditer(r'@\(([\d.]+) mm, ([\d.]+) mm\): Track \[([^\]]+)\]'
                                 r' on \S+, length ([\d.]+) mm', body):
                tracks.append((float(m.group(1)), float(m.group(2)),
                               m.group(3), float(m.group(4))))
        if kind in VIA_RIPPABLE:
            for m in re.finditer(r'@\(([\d.]+) mm, ([\d.]+) mm\): Via \[([^\]]+)\]',
                                 body):
                vias.append((float(m.group(1)), float(m.group(2)), m.group(3)))
    return tracks, vias


def main():
    apply = "--apply" in sys.argv
    os.makedirs("/tmp/nav", exist_ok=True)
    hard0, un0, text = drc()
    bad, badvias = offenders(text)
    print(f"{hard0} DRC errors, {un0} unconnected; "
          f"{len(bad)} track endpoints and {len(badvias)} vias named in "
          f"rippable violations")
    if not bad and not badvias:
        print("nothing to rip")
        return 0

    board = pcbnew.LoadBoard(BOARD)
    route.set_rules(board)
    # Match by start point and length - the report gives the track's own origin.
    want = {(round(x, 3), round(y, 3), round(L, 3)) for x, y, _, L in bad}
    wantv = {(round(x, 3), round(y, 3)) for x, y, _ in badvias}
    doomed, seen = [], {}
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            if (round(p.x / 1e6, 3), round(p.y / 1e6, 3)) in wantv:
                doomed.append(t)
                nm = t.GetNet().GetNetname() if t.GetNet() else "?"
                seen[f"{nm} via"] = seen.get(f"{nm} via", 0) + 1
            continue
        p = t.GetStart()
        key = (round(p.x / 1e6, 3), round(p.y / 1e6, 3), round(t.GetLength() / 1e6, 3))
        if key in want:
            doomed.append(t)
            nm = t.GetNet().GetNetname() if t.GetNet() else "?"
            seen[nm] = seen.get(nm, 0) + 1
    print(f"matched {len(doomed)} segments: "
          + ", ".join(f"{k}({v})" for k, v in sorted(seen.items())))
    if not apply:
        print("dry run - pass --apply to write the board")
        return 0

    shutil.copy(BOARD, BAK)
    for t in doomed:
        board.Remove(t)
    route.fill(board)
    board.Save(BOARD)
    hard, un, _ = drc()
    print(f"DRC: {hard0} -> {hard} errors, {un0} -> {un} unconnected")
    if hard > hard0:
        shutil.copy(BAK, BOARD)
        print("worse - rolled back")
        return 1
    print("kept - re-run route_remaining.py to close the gaps this opened")
    return 0


if __name__ == "__main__":
    sys.exit(main())
