#!/usr/bin/env python3
"""Import a freerouting .ses, restore design rules, re-add plane fanout, verify."""
import os, sys, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

board, ses = sys.argv[1], sys.argv[2]
stripped = ses.replace(".ses", "").replace("out", "in") + "-stripped.kicad_pcb"
shutil.copy(board, board + ".bak")
shutil.copy(stripped, board)

b = pcbnew.LoadBoard(board)
if not pcbnew.ImportSpecctraSES(b, ses):
    shutil.copy(board + ".bak", board); sys.exit("SES import failed; board restored")
pcbnew.SaveBoard(board, b)

# freerouting necks traces down below our minimum in tight spots; widen them back
b = pcbnew.LoadBoard(board); route.set_rules(b)
MINW = pcbnew.FromMM(route.TRACK_W)
for t in b.GetTracks():
    if t.Type() != pcbnew.PCB_VIA_T and t.GetWidth() < MINW: t.SetWidth(MINW)
b.Save(board)

# freerouting does not stitch our GND pours to the L2 plane; that stays our job
route.BOARD = board
b = pcbnew.LoadBoard(board); route.set_rules(b)
nf, ns = route.fanout(b), route.stitch(b)
route.fill(b); b.Save(board)
print(f"imported, widened necks, fanout +{nf} vias, stitching +{ns} vias")
