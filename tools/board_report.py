#!/usr/bin/env python3
"""
One-line-per-board summary for comparing routing configurations.

Routing completion on its own is a misleading score. An earlier run hit 88% by
putting 995 mm of signal through the GND plane, which fragmented the pour, stranded
the power pads and removed the return path under the fastest nets on the board. So
plane integrity is reported alongside completion, and the critical nets are checked
by name: those are the ones where a broken reference costs real signal integrity
rather than just a DRC entry.

Usage:  python3 tools/board_report.py <board.kicad_pcb> [more.kicad_pcb ...]
"""
import os, sys, re, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

PLANE_LAYERS = ("In1.Cu", "In4.Cu")
# Nets that need a continuous reference under them, not merely a connection.
CRITICAL = ("USB_DM", "USB_DP", "USB_DM_CON", "USB_DP_CON",
            "SD_CK", "SD_D0", "SD_D1", "SD_D2", "SD_D3",
            "OSC_IN", "OSC_OUT", "SPI1_SCK", "SPI3_SCK", "SPI4_SCK",
            "M1", "M2", "M3", "M4", "SOOP_I_ADC", "SOOP_Q_ADC")


PROJECT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "NAVCORE-SoOP.kicad_pro")


def drc(path):
    # kicad-cli reads netclasses and custom rules from the .kicad_pro sitting next to
    # the board. Without it every clearance falls back to defaults and a snapshot in
    # /tmp reports hundreds of phantom errors - which makes cross-board comparison
    # worthless. Give each board a copy of the real project file first.
    sib = os.path.splitext(path)[0] + ".kicad_pro"
    borrowed = False
    if not os.path.exists(sib) and os.path.exists(PROJECT):
        shutil.copy(PROJECT, sib); borrowed = True
    try:
        subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/nav/rep.rpt",
                        "--severity-error", path], capture_output=True, timeout=600)
    finally:
        if borrowed:
            os.remove(sib)
    t = open("/tmp/nav/rep.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', t, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def report(path):
    b = pcbnew.LoadBoard(path)
    hard, un = drc(path)
    pads = sum(1 for f in b.GetFootprints() for p in f.Pads()
               if p.GetNet() and p.GetNet().GetNetname())
    tracks = [t for t in b.GetTracks() if t.Type() != pcbnew.PCB_VIA_T]
    vias = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]

    plane_seg, plane_mm, crit = 0, 0.0, {}
    for t in tracks:
        ln = b.GetLayerName(t.GetLayer())
        if ln in PLANE_LAYERS:
            plane_seg += 1
            plane_mm += t.GetLength() / 1e6
            nm = t.GetNet().GetNetname() if t.GetNet() else ""
            if nm in CRITICAL:
                crit[nm] = crit.get(nm, 0) + 1

    gnd_islands = 0
    for z in b.Zones():
        if z.GetNetname() != "GND":
            continue
        for li in z.GetLayerSet().CuStack():
            if b.GetLayerName(li) == "In1.Cu":
                gnd_islands += z.GetFilledPolysList(li).OutlineCount()

    print(f"\n=== {os.path.basename(path)} ===")
    print(f"  routed            {pads-un}/{pads} = {100*(pads-un)/pads:.0f}%   "
          f"({un} unconnected, {hard} DRC errors)")
    print(f"  copper            {len(tracks)} segments, {sum(t.GetLength() for t in tracks)/1e6:.0f} mm, "
          f"{len(vias)} vias")
    print(f"  ON PLANE LAYERS   {plane_seg} segments, {plane_mm:.0f} mm")
    print(f"  GND In1.Cu        {gnd_islands} island(s)   "
          f"{'SOLID' if gnd_islands <= 1 else 'FRAGMENTED'}")
    if crit:
        print(f"  critical nets crossing a plane layer ({len(crit)}):")
        for n, c in sorted(crit.items(), key=lambda kv: -kv[1]):
            print(f"      {n:14} {c} segments")
    else:
        print("  critical nets     none routed through a plane layer")


if __name__ == "__main__":
    os.makedirs("/tmp/nav", exist_ok=True)
    for p in sys.argv[1:]:
        report(p)
