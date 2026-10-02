#!/usr/bin/env python3
"""Where is the centre of gravity, and how far can the aircraft lean on its skids?

Usage:  python3 tools/check_balance.py [--self-test]
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design             # noqa: E402
import gen_scad_mounts    # noqa: E402

MIN_TIP_DEG = 45.0      #a landing on a 30 deg slope with 15 deg of bounce still stands
MAX_OFFSET_MM = 10.0    #CG this near the thrust centre keeps the four motors near equal

G = gen_scad_mounts.G
T, N, L, R = G["tower"], G["nose"], G["lidar"], G["range"]
MP = design.MOUNTED
SG = design.skid_geometry()
Z_MID = design.FRAME["bottom_t"] + design.FRAME["arm_t"]          #arm top, motor base
MOTOR_H = design.MOTOR["h_mm"]


def positions():
    """MASS_ITEMS name -> (x, y, z, source)."""
    batt = design.BATT_POS
    return {
        "frame": (0.0, 0.0, 6.0, "[A] arms and plates about the stack centre"),
        "4x motors": (0.0, 0.0, Z_MID + MOTOR_H / 2, "[M] on the arm tops, symmetric"),
        "ESC": (0.0, 0.0, 14.0, "[A] in the stack under the board"),
        "this board": (0.0, 0.0, 28.0, "[A] in the stack"),
        "4x props": (0.0, 0.0, Z_MID + MOTOR_H + 4.0, "[M] on the motor bells, as drone.scad"),
        "battery": (0.0, batt["y"], batt["z"] + design.BATT["H"] / 2,
                    "[M] design.BATT_POS on the top plate"),
        "GPS": (0.0, T["gps_y"], (T["gps_bot"] + T["gps_top"]) / 2,
                "[M] gen_scad_mounts tower arm"),
        "RX": (0.0, N["rx_y"], N["z"] - N["rx_h"] / 2, "[M] gen_scad_mounts nose mount"),
        "Iridium antenna (HC610)": (0.0, T["helix_y"], T["seat_z"] + MP["iridium_antenna"]["H"] / 2,
                                    "[M] gen_scad_mounts tower seat"),
        "XIAO nose camera": (0.0, N["cam_y"], N["z"] - N["cam_h"] / 2,
                             "[M] gen_scad_mounts nose mount"),
        "printed mounts, inserts, screws": (0.0, 40.0, 40.0,
                                            "[A] mostly the tower, aft and up"),
        design.PI["name"]: (0.0, 0.0, 30.0, "[A] deferred companion, budgeted at the stack"),
        "camera+cable (deferred, budgeted)": (0.0, R["y"], -8.0,
                                              "[A] the belly slot the rangefinder uses"),
        "TFS20-L": (0.0, R["y"], -R["body_h"] / 2, "[M] gen_scad_mounts range cradle"),
        "LD06 360 lidar (deferred, budgeted)": (0.0, L["y"], -(5.0 + design.OFFBOARD["lidar"]["H_mm"] / 2),
                                                 "[M] gen_scad_mounts lidar bracket"),
        "Remote ID (Holybro, rear-port arm)": (G["rid"]["cx"], G["rid"]["cy"],
                                               G["rid"]["z0"] + G["rid"]["base_t"] + MP["remote_id"]["H"] / 2,
                                               "[M] gen_scad_mounts rid_tray"),
        "skids": (0.0, 0.0, (SG["z0"] + SG["contact"]) / 2, "[M] at the four motors, symmetric"),
        "wiring/straps": (0.0, 0.0, 15.0, "[A] about the stack"),
    }


def feet(reach=None):
    """The eight foot centres: two per motor, along its arm."""
    mo = design.FRAME["wb"] / 2 / math.sqrt(2)
    r = SG["reach"] if reach is None else reach
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            u = (sx / math.sqrt(2), sy / math.sqrt(2))
            for s in (-1, 1):
                out.append((sx * mo + s * r * u[0], sy * mo + s * r * u[1]))
    return out


def hull(pts):
    pts = sorted(set(pts))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def evaluate(items, pos, foot_pts, verbose=False):
    fails = []
    missing = [n for n, _g, _s in items if n not in pos]
    for n in missing:
        fails.append(f"'{n}' has a mass and no position")
    known = [(n, g) for n, g, _s in items if n in pos]
    m = sum(g for _n, g in known)
    cg = [sum(g * pos[n][i] for n, g in known) / m for i in range(3)]
    if verbose:
        print(f"  {'item':38} {'g':>7} {'x':>7} {'y':>7} {'z':>7}  moment y (g.mm)")
        for n, g in known:
            x, y, z, src = pos[n]
            print(f"  {n:38} {g:7.1f} {x:7.1f} {y:7.1f} {z:7.1f}  {g * y:9.0f}  {src}")
    poly = hull(foot_pts)
    h = cg[2] - SG["contact"]
    tips = []
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        ln = math.hypot(x2 - x1, y2 - y1)
        d = ((x2 - x1) * (cg[1] - y1) - (y2 - y1) * (cg[0] - x1)) / ln   #>0 inside (CCW)
        tips.append(math.degrees(math.atan2(d, h)))
    tip = min(tips)
    off = math.hypot(cg[0], cg[1])
    if tip < MIN_TIP_DEG:
        fails.append(f"static tip angle {tip:.1f} deg is under {MIN_TIP_DEG:.0f} deg")
    if off > MAX_OFFSET_MM:
        fails.append(f"CG is {off:.1f} mm from the thrust centre (limit {MAX_OFFSET_MM:.0f})")
    return fails, dict(mass=m, cg=cg, tip=tip, off=off, h=h)


def self_test():
    items, pos = design.MASS_ITEMS, positions()
    ok = not evaluate(items, pos, feet())[0]
    print(f"  {'clean' if ok else 'NOT CLEAN'}  the aircraft as designed")
    moved = dict(pos)
    x, y, z, s = moved["battery"]
    moved["battery"] = (x, 150.0, z, s)
    gone = {k: v for k, v in pos.items() if k != "skids"}
    for name, args in (("battery moved to y = +150", (items, moved, feet())),
                       ("feet drawn in to a tenth of their span",
                        (items, pos, [(x * 0.1, y * 0.1) for x, y in feet()])),
                       ("a mass with no position", (items, gone, feet()))):
        caught = bool(evaluate(*args)[0])
        ok &= caught
        print(f"  {'caught' if caught else 'MISSED'}  {name}")
    print("self-test passed: every break is caught" if ok else "SELF-TEST FAILED")
    return 0 if ok else 1


def main():
    if "--self-test" in sys.argv:
        return self_test()
    fails, r = evaluate(design.MASS_ITEMS, positions(), feet(), verbose=True)
    print(f"\n  all-up {r['mass']:.1f} g; CG at x {r['cg'][0]:+.1f}, y {r['cg'][1]:+.1f}, "
          f"z {r['cg'][2]:.1f} mm ({r['h']:.1f} mm above the skid contact plane)")
    print(f"  CG {r['off']:.1f} mm from the thrust centre (limit {MAX_OFFSET_MM:.0f}); "
          f"static tip angle {r['tip']:.1f} deg (need {MIN_TIP_DEG:.0f})")
    for f in fails:
        print(f"  FAIL {f}")
    if fails:
        print(f"\nFAIL - {len(fails)} balance problem(s)")
        return 1
    print("\nbalanced: CG over the thrust centre, and it takes a "
          f"{r['tip']:.0f} deg lean to tip it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
