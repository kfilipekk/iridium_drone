#!/usr/bin/env python3
"""
Apply a freerouting Specctra .ses session back onto the board, and verify it.

Round trip:
    pcbnew.ExportSpecctraDSN(board, "x.dsn")   ->  freerouting  ->  x.ses
    pcbnew.ImportSpecctraSES(board, "x.ses")

What happens to existing copper, which is the thing worth being sure about:
  * an UNLOCKED track exports as DSN "(type route)". Freerouting may shove or rip it
    up, and it comes back in the .ses. KiCad's importer clears unlocked tracks and
    lays down what the session says. Nothing is lost - it is replaced.
  * a LOCKED track exports as "(type fix)". Freerouting treats it as an immovable
    obstacle and omits it from the .ses; KiCad's importer sets locked tracks aside
    and re-adds them afterwards.
So locking is the knob for "do not touch this net". Locking everything reproduces the
dead end a shove-less router is already in, so lock only what genuinely must not move.

The board is restored automatically if the import makes DRC worse.

Usage: python3 tools/apply_ses.py <session.ses>
"""
import os, sys, shutil, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/navcore_pre_ses.kicad_pcb"


def drc(path=BOARD):
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/ses_drc.rpt",
                    "--severity-error", path], capture_output=True, timeout=600)
    rpt = open("/tmp/ses_drc.rpt").read()
    cls = re.findall(r'^\[([a-z_]+)\]', rpt, re.M)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items")


def stats(path):
    b = pcbnew.LoadBoard(path)
    tr = [t for t in b.GetTracks() if t.Type() != pcbnew.PCB_VIA_T]
    vi = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    return len(tr), len(vi), sum(t.GetLength() for t in tr) / 1e6


def main():
    ses = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fr/out.ses"
    if not os.path.exists(ses) or os.path.getsize(ses) == 0:
        print(f"no usable session file at {ses}"); return 1

    shutil.copy(BOARD, BAK)
    h0, u0 = drc()
    t0, v0, l0 = stats(BOARD)
    print(f"before: {h0} hard DRC errors, {u0} unconnected, "
          f"{t0} tracks ({l0:.0f} mm), {v0} vias")

    b = pcbnew.LoadBoard(BOARD)
    ok = pcbnew.ImportSpecctraSES(b, ses)
    if not ok:
        print("ImportSpecctraSES returned False - session not applied"); return 1
    pcbnew.SaveBoard(BOARD, b)

    # the pours must be refilled: the session moved copper around under them
    b = pcbnew.LoadBoard(BOARD)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(BOARD, b)

    h1, u1 = drc()
    t1, v1, l1 = stats(BOARD)
    print(f"after : {h1} hard DRC errors, {u1} unconnected, "
          f"{t1} tracks ({l1:.0f} mm), {v1} vias")
    print(f"delta : {u1-u0:+d} unconnected, {t1-t0:+d} tracks, {v1-v0:+d} vias")

    if h1 > h0:
        shutil.copy(BAK, BOARD)
        print(f"\nROLLED BACK: the session added {h1-h0} DRC errors.")
        print(f"The pre-import board is intact. Session kept at {ses} for inspection.")
        return 1
    print(f"\nkept. previous board saved at {BAK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
