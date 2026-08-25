#!/usr/bin/env python3
"""
Place explicitly specified routes, one net at a time, and let DRC judge each.

The grid router in route.py finished the easy part of the J1/J2 rotation but stalls on
the last few nets: it models neither the zones nor the six-layer routing freerouting
originally laid down, so the paths it finds for them short to copper it cannot see.
These last nets are short and their geometry is known exactly, so they are specified by
hand here instead of searched for.

Each route is a list of points. A point is (layer, x, y); the string "VIA" between two
points puts a through via at that position. Every route is committed on its own, the
zones are refilled, and whole-board DRC decides: a route that raises the hard-error
count or fails to reduce the unconnected count is reverted.

DRC MUST run on the board in its project directory. kicad-cli reads the design rules
from the .kicad_pro beside the board, so checking a copy in /tmp silently falls back to
KiCad's defaults - 0.2 mm clearance instead of this board's 0.1016 - and invents a
thousand violations that are purely an artifact of where the file was sitting.

Usage: python3 tools/hand_route.py
"""
import os, sys, re, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from route import add_via, add_track

BOARD = 'NAVCORE-SoOP.kicad_pcb'

# net -> list of (layer, x, y) with "VIA" markers between layer changes
ROUTES = {
 # The last +9V break: C70's stub to L5's output. Every straight line and every inner
 # layer was blocked, and both a via at C70's end and moving C70 were dead ends - its
 # pocket has no free space and no exit. A B.Cu DOGLEG does exist, threading between
 # C19, R11 and the UART7_RX via, with 0.079 mm of margin.
 #
 # Endpoints are the tracks' EXACT coordinates. Rounding them to 0.01 mm left the new
 # copper a few microns clear of what it was supposed to join, so it committed cleanly
 # and connected nothing.
 '+9V': [('B.Cu', 124.0167, 119.7253), ('B.Cu', 124.000, 118.800),
         ('B.Cu', 126.0938, 119.0312)],
}


def drc(path):
    subprocess.run(['kicad-cli','pcb','drc','--severity-error','--output','/tmp/nav/hand.rpt',path],
                   capture_output=True)
    txt = open('/tmp/nav/hand.rpt').read()
    errs = len(re.findall(r'^\[', txt, re.M))
    unc  = len(re.findall(r'^\[unconnected_items\]', txt, re.M))
    return errs, unc


def place(b, netname, pts):
    net = b.GetNetInfo().GetNetItem(netname)
    prev = None
    for p in pts:
        if p == 'VIA':
            add_via(b, prev[1], prev[2], net); continue
        if prev is not None and prev[0] == p[0]:
            add_track(b, (prev[1], prev[2]), (p[1], p[2]), p[0], net)
        prev = p


def main():
    os.makedirs('/tmp/nav', exist_ok=True)
    shutil.copy(BOARD, '/tmp/nav/hand_base.kicad_pcb')
    err, unc = drc(BOARD)
    print(f"baseline: {err} errors ({err-unc} hard), {unc} unconnected\n")
    for netname, pts in ROUTES.items():
        b = pcbnew.LoadBoard(BOARD)
        place(b, netname, pts)
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        b.Save(BOARD)
        e, u = drc(BOARD)
        if (e - u) > (err - unc) or u >= unc:
            shutil.copy('/tmp/nav/hand_base.kicad_pcb', BOARD)
            print(f"  {netname:12s} REVERTED   {e} errors ({e-u} hard), {u} unconnected")
        else:
            shutil.copy(BOARD, '/tmp/nav/hand_base.kicad_pcb')
            err, unc = e, u
            print(f"  {netname:12s} kept       {e} errors ({e-u} hard), {u} unconnected")
    print(f"\nfinal: {err} errors ({err-unc} hard), {unc} unconnected")
    sys.stdout.flush(); os._exit(0)

main()
