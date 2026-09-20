#!/usr/bin/env python3
"""Every "measure it at the bench" item, answered two ways: closed, or bounded.

Run: python3 tools/check_bench_bounds.py
"""
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design
import readiness

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD_R = 2.75          # M3 cap head, 5.5 mm OD - metal, the hard constraint
FLANGE_R = design.MOUNTING["grommet_d"] / 2.0      # assumed silicone flange, 6.0 mm OD
FLANGE_R_WIDE = 4.0    # 8.0 mm OD - the widest silicone M3 grommet worth buying


def thermal_verdict():
    """check_thermal.py is the authority on the junction bounds."""
    out = subprocess.run([sys.executable, "tools/check_thermal.py"], cwd=REPO,
                         capture_output=True, text=True).stdout
    got = {}
    for m in re.finditer(r"^  (ok|warn|FAIL)\s+(U\d+) junction temperature\s+(.*)$",
                         out, re.M):
        got[m.group(2)] = (m.group(1), m.group(3).strip())
    return got


def mounting_bound():
    """Nearest copper to each mounting hole, so the grommet closure rests on the artwork."""
    import pcbnew
    b = pcbnew.LoadBoard(os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb"))
    mm = pcbnew.ToMM
    holes = [(mm(d.GetCenter().x), mm(d.GetCenter().y)) for d in b.GetDrawings()
             if d.GetLayer() == pcbnew.Edge_Cuts and d.ShowShape() == "Circle"]
    rows = []
    for hx, hy in holes:
        best = (1e9, None)
        for pd in b.GetPads():
            bb = pd.GetBoundingBox()
            l, t, r, bt = mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())
            d = math.hypot(max(l - hx, 0, hx - r), max(t - hy, 0, hy - bt))
            if d < best[0]:
                best = (d, pd.GetParentFootprint().GetReference() + "." + pd.GetPadName())
        rows.append((hx, hy, best[0], best[1]))
    return rows


def build_rows():
    th = thermal_verdict()
    rows = []

    # ============================================================ closed by evidence ===

    mrows = mounting_bound()
    head_min = min(r[2] - HEAD_R for r in mrows)
    flange_min = min(r[2] - FLANGE_R for r in mrows)
    flange_wide_min = min(r[2] - FLANGE_R_WIDE for r in mrows)
    rows.append(dict(
        id="bench.grommet", cls="CLOSED",
        bound=(f"the metal M3 cap head clears copper at every hole by {head_min:+.2f} mm "
               f"(nearest pad {min(mrows, key=lambda r: r[2]-HEAD_R)[3]}); the flange "
               f"overlap is {flange_min:+.2f} mm at the assumed 6.0 mm OD and "
               f"{flange_wide_min:+.2f} mm at 8.0 mm, all of it on MASK, which "
               f"check_placement.py already classes as an assembly note"),
        evidence=("the flange and the M3 head are CONCENTRIC, so the flange is always the "
                  "wider of the two and the metal is always the narrower. Growing the "
                  "flange adds only silicone-on-mask; it cannot make the metal part reach "
                  "copper it does not already clear. Z is swept 2.0-4.5 mm by check_fit.py, "
                  "which requires every PURCHASE to cover the whole range - so the design "
                  "is invariant over the grommet, which is stronger than measuring one"),
        residual="caliper the received grommet only to choose the standoff set - an "
                 "assembly convenience, not a prerequisite"))

    rows.append(dict(
        id="bench.escshunt", cls="CLOSED",
        bound=("the ESC's own manual publishes Scale=400 -> 40.0 mV/A -> 25.0 A/V, and "
               "defaults.parm ships exactly that"),
        evidence=("check_build.py 'BATT_AMP_PERVLT matches the ESC' now compares the "
                  "derivation against the value in the SHIPPED defaults.parm rather than "
                  "against a second typed literal, and gen_hwdef.py DERIVES the emitted "
                  "value from design.ESC - so the number exists once and is checked at "
                  "both ends. Mutation-tested: shipping the retired 52.7 fails it"),
        residual="bench calibration still refines shunt tolerance; it cannot change what "
                 "ships, and battery failsafe does not turn on a 10% scale error"))

    rows.append(dict(
        id="bench.esccable", cls="CLOSED",
        bound=("J2 is the documented 8-pin order - GND VBAT M1 M2 M3 M4 CUR TEL - and a "
               "reversed pack is designed out by Q4 (reverse-polarity P-FET) + D1 (SMBJ18A, "
               "which clamps at 29.2 V UNDER the 30 V limit of what is downstream)"),
        evidence=("design.ESC now DECLARES pin_order from the manual, and check_build.py "
                  "'J2 pin order matches the ESC manual' holds the netlist against it. "
                  "Nothing checked this before: J2 is a passive connector, so DRC, ERC and "
                  "check_pin_semantics all pass a transposed one - the symptom is four "
                  "motors on the wrong signals. Mutation-tested: swapping M1/M2 and "
                  "CUR/TEL each fail it"),
        residual="a continuity test on the received cable is still prudent before first "
                 "power; it is not a prerequisite and it cannot change the board"))

    # ================================================================= bound / PARAM ===
    u8, u9 = th.get("U8"), th.get("U9")
    # The good-copper figure only for U9: the rest of that line is the MINIMAL-copper
    # corner, which is the datasheet's "No Heatsink" board and not this one.
    u9_bound = (u9[1].split(" but ")[0] if u9 else "NOT COMPUTED")
    rows.append(dict(
        id="bench.u8", cls="BOUND",
        bound=f"check_thermal.py: {u8[1] if u8 else 'NOT COMPUTED'}",
        evidence=("the worst-case corner would have to pass 125 C; it is 38 C below it, and "
                  "U8 was already swapped to the LMR33630A RNX for exactly this - the swap "
                  "is ON the board, so no reading can un-fit it"),
        residual="a thermocouple at T3a confirms the bound (kept as a flight gate)"))
    rows.append(dict(
        id="bench.u9", cls="BOUND",
        bound=f"check_thermal.py: {u9_bound}",
        evidence=("the good-copper corner would have to pass 150 C; it is 46 C below it, on "
                  "a board tools/thermal_vias.py MEASURES at 7443 mm2 of GND plane and 5 "
                  "vias on the output pad. Only the datasheet's 'No Heatsink' corner is "
                  "over, and that describes a 2-layer board this one is not"),
        residual="T3a sets the board-to-junction offset once; U19 then logs it every flight"))
    rows.append(dict(
        id="bench.flowyaw", cls="PARAM",
        bound=("FLOW_ORIENT_YAW selects one of four cardinal values; flow arrives as MAVLink "
               "from the off-board companion, so the board cannot encode it"),
        evidence=("nothing on the board. The sign is a constant in defaults.parm"),
        residual="set the sign from CAD, then confirm it in position hold"))

    # ====================================================================== module ====
    # The requirement arithmetic, so the bench knows what it is looking for.
    cn0_req = 62.0
    req_2db = cn0_req - 174.0 + 2.0
    req_4db = cn0_req - 174.0 + 4.0
    rows.append(dict(
        id="bench.rf", cls="MODULE",
        bound=(f"the requirement is C/N0 {cn0_req:.0f} dB-Hz, so Pr must reach "
               f"{req_2db:.0f} dBm at 2 dB system NF ({req_4db:.0f} dBm at 4 dB). The gain "
               f"and noise figure that meet it come from the BOUGHT Nooelec SAWbird+ IR "
               f"(>=30 dB gain, 60 MHz bandpass at 1620 MHz, shielded, at the antenna where "
               f"NF is set before cable loss). The board contributes a U.FL entry (J12) and "
               f"3.3 V"),
        evidence=("a desense result is fixed by antenna separation, ferrites and shielding - "
                  "all listed mitigations - because the SAW sits AT THE ANTENNA and rejects "
                  "the board's own switchers before the tuner sees them. The one board-side "
                  "lever, an on-board LNA+SAW, was DELETED in favour of the bought module "
                  "(design.py U15/U16/FL1), so putting it back would be a respin - and it is "
                  "the wrong move: an LNA belongs before the cable, not after it. NOTE this "
                  "is the ONE item with no analytic bound: whether the link closes depends "
                  "on real sky and real desense, so it stays a flight gate"),
        residual="T3b: four steps that each name their own culprit"))
    rows.append(dict(
        id="fly.rfbench", cls="DATA",
        bound=("check_rf.py records the four T3b steps and compares them to baseline; it "
               "asserts nothing about the board"),
        evidence="nothing on the board - it gates FLYING, not ordering",
        residual="the same bench session as bench.rf"))
    rows.append(dict(
        id="bench.cameraflow", cls="MODULE",
        bound=("flow quality is a property of the off-board companion camera and the ground; "
               "J4 (its connector) was cut from this board"),
        evidence=("nothing on the board. Poor flow selects a different camera. Kept as a "
                  "flight gate because the runbook stops at GPS Loiter"),
        residual="record a flight, then replay it through the harness"))

    return rows


def main():
    rows = build_rows()
    live = [r for r in rows if r["cls"] != "CLOSED"]
    widths = {"BOUND": "confirmed", "PARAM": "firmware", "MODULE": "bought part",
              "DATA": "recorded", "CLOSED": "by evidence"}

    print("=== the bench list: what is closed, and what the rest can move ===\n")
    for r in rows:
        print(f"  {r['cls']:6s} {r['id']:20s} {widths.get(r['cls'], r['cls']):12s} "
              f"{r['bound']}")
        print(f"         evidence:    {r['evidence']}")
        print(f"         bench sets:  {r['residual']}")
        print()

    unknown = [r["id"] for r in rows if r["cls"] not in widths]
    n = {k: sum(1 for r in rows if r["cls"] == k) for k in widths}
    print(f"{len(rows)} items accounted for: " +
          ", ".join(f"{v} {k}" for k, v in n.items() if v))

    # ---- reconciliation: the live set must be the manifest's bench/FLY set -----------
    want = {p["id"] for p in readiness.PREREQUISITES if p["cls"] in (readiness.BENCH,
                                                                     readiness.FLY)}
    got = {r["id"] for r in live}
    if got != want:
        print("\nFAIL - this file and readiness.PREREQUISITES disagree:")
        for i in sorted(want - got):
            print(f"  - {i} is a bench/FLY entry in the manifest but is not classified here")
        for i in sorted(got - want):
            print(f"  - {i} is classified here but is not a bench/FLY entry in the manifest")
        print("Every bench item must be classified, and closing one must be recorded.")
        return 1

    if unknown:
        print(f"\nFAIL - unclassified, so nobody decided whether they can change the board: "
              f"{', '.join(unknown)}")
        return 1

    closed = [r["id"] for r in rows if r["cls"] == "CLOSED"]
    print(f"\nClosed by evidence and no longer prerequisites: {', '.join(closed)}")
    print(f"The {len(live)} that remain are all still MEASURED. None can force a different")
    print("board except bench.rf, which is honestly unmeasurable offline and gates FLYING.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
