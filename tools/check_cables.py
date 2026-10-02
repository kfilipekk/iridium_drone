#!/usr/bin/env python3
"""Every cable, routed through the airframe and measured: length, bend and clearance."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import design
import cables
import gen_scad_mounts
import gen_scad_plugs

F, TPM, P = design.FRAME, design.TOP_PLATE_MOUNT, design.PLATES
G = gen_scad_mounts.G
STEP = 0.5            #mm between clearance samples along a path
FILLETS = (0.0, 0.5, 1.0)   #polyline, half-size and full-size corner arcs


#geometry
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def add(a, b): return tuple(x + y for x, y in zip(a, b))
def mul(a, k): return tuple(x * k for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    n = norm(a)
    return mul(a, 1.0 / n) if n > 1e-12 else a


def angle(a, b):
    c = dot(unit(a), unit(b))
    return math.acos(max(-1.0, min(1.0, c)))


def box(x0, x1, y0, y1, z0, z1):
    return ("box", (min(x0, x1), min(y0, y1), min(z0, z1)), (max(x0, x1), max(y0, y1), max(z0, z1)))


def prism(a, b, r, z0, z1):
    """A capsule in plan, extruded from z0 to z1 - an arm, a post, a prop disc."""
    return ("prism", a, b, r, z0, z1)


def vcyl(x, y, r, z0, z1):
    return prism((x, y), (x, y), r, z0, z1)


def dist(p, s):
    """Distance from point p to shape s; negative inside."""
    if s[0] == "box":
        lo, hi = s[1], s[2]
        d = [max(lo[i] - p[i], 0.0, p[i] - hi[i]) for i in range(3)]
        out = math.sqrt(sum(x * x for x in d))
        if out > 0.0:
            return out
        return -min(min(p[i] - lo[i], hi[i] - p[i]) for i in range(3))
    _, a, b, r, z0, z1 = s
    ab = (b[0] - a[0], b[1] - a[1])
    L2 = ab[0] ** 2 + ab[1] ** 2
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / L2))
    dr = math.hypot(p[0] - a[0] - t * ab[0], p[1] - a[1] - t * ab[1]) - r
    dz = max(z0 - p[2], p[2] - z1)
    if dr <= 0.0 and dz <= 0.0:
        return max(dr, dz)
    return math.hypot(max(dr, 0.0), max(dz, 0.0))


#the airframe, as hazards: (name, shape, margin key)
def stack_z(board):
    """The FC board's underside, as drone.scad and check_cad_fit place it."""
    rs = design.required_standoff(board)
    fc_z = rs["below"] + design.ESC["pcb"] + design.ESC["parts"] + design.MOUNTING["gap"] + rs["bot"]
    return fc_z, rs


def plug_exits(board, fc_z):
    """Each port's mated plug."""
    out = {}
    for ref in design.MATING_FACE:
        dx, dy, ux, uy, w, _depth, flip = gen_scad_plugs.plug_of(board, ref)
        body = design.MATING_PLUG_BODY[ref]
        axis = cables.AXIS_OVERRIDE.get(ref, cables.PLUG_AXIS)
        z = fc_z - axis if flip else fc_z + design.BOARD_T + axis
        out[ref] = dict(mouth=(dx, dy), u=(ux, uy, 0.0), w=w, flip=flip, body=body,
                        exit=(dx + ux * body, dy + uy * body, z))
    return out


def floorplan_mouth(ref):
    """The mouth design.FLOORPLAN_REV_D intends, to compare with the board's."""
    fp, B = design.FLOORPLAN_REV_D[ref], design.BOARD
    cx, cy = B["X0"] + B["W"] / 2, B["Y0"] + B["H"] / 2
    n = dict(N=(0, 1), S=(0, -1), E=(1, 0), W=(-1, 0))[fp["edge"]]
    if fp["edge"] in "NS":
        return (fp["at"] - cx, n[1] * (B["H"] / 2 + fp["front"]))
    return (n[0] * (B["W"] / 2 + fp["front"]), cy - fp["at"])


def hazards(fc_z, rs, plugs):
    H = []
    bt, at, mt, ut = F["bottom_t"], F["arm_t"], F["medium_t"], F["upper_t"]
    z_arm, z_mid, z_stack = bt, bt + at, bt + at + mt
    top_z = rs["top_plate_z"]
    pc = TPM["plate_centre_y"]
    #[D] plates from the manufacturer DXF (design.PLATES)
    for name, (w, l), cy, z0, z1 in (
            ("bottom plate", P["bottom"], pc["bottom"], 0.0, bt),
            ("mid plate", P["fc"], pc["fc"], z_mid, z_stack),
            ("top plate", P["top"], pc["top"], top_z, top_z + ut)):
        H.append((name, box(-w / 2, w / 2, cy - l / 2, cy + l / 2, z0, z1), "carbon"))
    mo = F["wb"] / 2 / math.sqrt(2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            tag = ("fore" if sy < 0 else "aft") + "-" + ("port" if sx < 0 else "starboard")
            m = (sx * mo, sy * mo)
            H.append((f"{tag} arm", prism((0.0, 0.0), m, P["arm"][0] / 2, z_arm, z_mid), "carbon"))
            H.append((f"{tag} motor", vcyl(m[0], m[1], design.MOTOR["dia_mm"] / 2, z_mid,
                                           z_mid + design.MOTOR["h_mm"] + 4.0), "carbon"))
            pz = z_mid + design.MOTOR["h_mm"] + 4.0      #as drone.scad's props()
            H.append((f"{tag} prop", vcyl(m[0], m[1], design.PROP["dia_mm"] / 2, pz, pz + 1.2),
                      "prop"))
            sk = design.SKID["hole_pitch"] / 2 + 2.0
            H.append((f"{tag} skid", box(m[0] - sk, m[0] + sk, m[1] - sk, m[1] + sk,
                                         -(design.SKID["drop"] + design.SKID["t"]), z_arm),
                      "carbon"))
    r_post = TPM["post_od"] / 2
    for x, y in TPM["front_posts"]:
        H.append((f"front post ({x:+.1f},{y:+.1f})", vcyl(x, y, r_post, z_stack, top_z), "carbon"))
    for x, y in TPM["rear_posts"]:
        H.append((f"rear post ({x:+.1f},{y:+.1f})", vcyl(x, y, r_post, z_arm, top_z), "carbon"))
    h = design.MOUNTING["pitch"] / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            H.append(("stack bolt", vcyl(sx * h, sy * h, design.MOUNTING["screw_dia"] / 2, z_mid,
                                         fc_z + design.BOARD_T + 2.4), "board"))
    #the stack
    E = design.ESC
    H.append(("esc", box(-E["L"] / 2, E["L"] / 2, -E["W"] / 2, E["W"] / 2, z_stack,
                         z_stack + E["pcb"] + E["parts"]), "board"))
    B = design.BOARD
    H.append(("fc", box(-B["W"] / 2, B["W"] / 2, -B["H"] / 2, B["H"] / 2, fc_z - rs["bot"],
                        fc_z + design.BOARD_T + rs["top"]), "board"))
    #the mated plugs of the cables this airframe fits
    for ref, pl in plugs.items():
        if ref == "J8":
            depth = 2.0                     #[A] a seated card stands ~2 mm proud
        elif cables.CABLES.get(ref, {}).get("end") is None:
            continue                        #nothing plugged in on this airframe
        else:
            depth = pl["body"]
        (mx, my), (ux, uy, _), w = pl["mouth"], pl["u"], pl["w"]
        px, py = -uy, ux
        xs = [mx + px * w / 2, mx - px * w / 2, mx + ux * depth + px * w / 2,
              mx + ux * depth - px * w / 2]
        ys = [my + py * w / 2, my - py * w / 2, my + uy * depth + py * w / 2,
              my + uy * depth - py * w / 2]
        z0 = fc_z - gen_scad_plugs.PLUG_H if pl["flip"] else fc_z + design.BOARD_T
        H.append((f"plug {ref}", box(min(xs), max(xs), min(ys), max(ys), z0,
                                     z0 + gen_scad_plugs.PLUG_H), "board"))
    #the battery on the top plate
    bp, ba = design.BATT_POS, design.BATT
    H.append(("battery", box(-ba["W"] / 2, ba["W"] / 2, bp["y"] - ba["L"] / 2,
                             bp["y"] + ba["L"] / 2, bp["z"], bp["z"] + ba["H"]), "battery"))
    #the antenna tower and what it carries (gen_scad_mounts.G, = cad/mounts.scad)
    T = G["tower"]
    st, sz = T["seat_t"], T["seat_z"]
    H += [("tower foot", box(-T["foot_x"] / 2, T["foot_x"] / 2, T["y_post"] - T["foot_y"] / 2,
                             T["y_post"] + T["foot_y"] / 2, T["foot_z"], T["foot_z"] + T["foot_t"]),
           "printed"),
          ("tower column", box(-T["col_x"] / 2, T["col_x"] / 2, T["col_y0"] - T["col_y"] / 2,
                               T["col_y0"] + T["col_y"] / 2, T["foot_z"], sz - st), "printed"),
          ("tower seat", box(-T["seat_x"] / 2, T["seat_x"] / 2, T["seat_y0"], T["seat_y1"],
                             sz - st, sz), "printed"),
          ("tower arm", box(-T["arm_x"] / 2, T["arm_x"] / 2, T["seat_y1"] - 1, T["arm_y1"],
                            sz - T["arm_t"], sz), "printed"),
          ("tower web", box(-T["web"] / 2, T["web"] / 2, T["helix_holes"][1][1] + 3, T["arm_y1"],
                            sz - T["arm_t"] - T["web_h"], sz - T["arm_t"]), "printed"),
          ("gps pod", box(-T["pod_x"] / 2, T["pod_x"] / 2, T["gps_y"] - T["pod_y"] / 2,
                          T["gps_y"] + T["pod_y"] / 2, sz, T["pod_top"]), "printed"),
          ("gps lid", box(-T["pod_x"] / 2, T["pod_x"] / 2, T["gps_y"] - T["pod_y"] / 2,
                          T["gps_y"] + T["pod_y"] / 2, T["pod_top"],
                          T["pod_top"] + T["proud"] + T["lid_t"]), "printed")]
    g = design.MOUNTED["gps"]
    H.append(("gps", box(-g["L"] / 2, g["L"] / 2, T["gps_y"] - g["W"] / 2, T["gps_y"] + g["W"] / 2,
                         T["gps_bot"], T["gps_top"]), "printed"))
    ant = design.MOUNTED["iridium_antenna"]
    H.append(("helix", vcyl(0.0, T["helix_y"], ant["dia"] / 2, sz, sz + ant["H"]), "antenna"))
    H.append(("helix SMA", vcyl(0.0, T["helix_y"], 4.0, sz - 10.0, sz), "printed"))
    #the nose mount, the receiver and the ELRS antennas
    N = G["nose"]
    pz = N["z"] - N["t"]
    cam_x = N["cam_x"] / 2 + 0.3 + N["cw"]
    cam_d = N["cam_d"] / 2 + 0.3 + N["cw"]
    cam_bot = N["z"] - N["t"] - N["cam_h"] - 0.3 - N["cw"]
    boss_r = (design.INSERTS["M2"]["od"] + 2 * design.INSERT_WALL) / 2
    cam_boss = cam_x + boss_r - 1
    rx_w = N["rx_x"] / 2 + 0.2 + N["rx_wall"]
    rx_l = N["rx_l"] / 2 + 0.2 + N["rx_wall"]
    rx_bot = N["z"] - N["t"] - (N["rx_h"] + 0.4)
    rx_boss = rx_w + boss_r - 1
    H += [("nose plate", box(-N["x"] / 2, N["x"] / 2, N["y1"], N["y0"], pz, N["z"]), "printed"),
          ("cam cradle", box(-cam_x, cam_x, N["cam_y"] - cam_d, N["cam_y"] + cam_d, cam_bot, pz),
           "printed"),
          ("cam bosses", box(-cam_boss - boss_r, cam_boss + boss_r, N["cam_y"] - boss_r,
                             N["cam_y"] + boss_r, cam_bot, pz), "printed"),
          ("xiao lid", box(-cam_boss - boss_r, cam_boss + boss_r, N["cam_y"] - cam_d,
                           N["cam_y"] + cam_d, cam_bot - N["cam_lid"], cam_bot), "printed"),
          ("rx pocket", box(-rx_w, rx_w, N["rx_y"] - rx_l, N["rx_y"] + rx_l, rx_bot, pz), "printed"),
          ("rx bosses", box(-rx_boss - boss_r, rx_boss + boss_r, N["rx_y"] - boss_r,
                            N["rx_y"] + boss_r, rx_bot, pz), "printed"),
          ("rx cover", box(-rx_boss - boss_r, rx_boss + boss_r, N["rx_y"] - rx_l, N["rx_y"] + rx_l,
                           rx_bot - N["rx_cover"], rx_bot), "printed"),
          ("rx", box(-N["rx_x"] / 2, N["rx_x"] / 2, N["rx_y"] - N["rx_l"] / 2,
                     N["rx_y"] + N["rx_l"] / 2, rx_bot + 0.2, rx_bot + 0.2 + N["rx_h"]), "printed"),
          ("elrs whip, vertical", vcyl(N["av"][0], N["av"][1], N["ant_d"] / 2, pz - 10,
                                       pz - 10 + N["ant_l"]), "antenna"),
          ("elrs holder, vertical", vcyl(N["av"][0], N["av"][1], 4.0, pz - 12, pz), "printed"),
          ("elrs whip, forward", box(N["ah"][0] - N["ant_d"] / 2, N["ah"][0] + N["ant_d"] / 2,
                                     N["ah"][1] + 4 - N["ant_l"], N["ah"][1] + 4,
                                     N["ah"][2] - N["ant_d"] / 2, N["ah"][2] + N["ant_d"] / 2),
           "antenna"),
          ("elrs holder, forward", box(N["ah"][0] - 5, N["ah"][0] + 5, N["ah"][1], N["ah"][1] + 5,
                                       N["ah"][2] - 4, pz), "printed")]
    #the lidar bracket and the LD06, the range cradle and the TFS20-L
    L, ld = G["lidar"], design.OFFBOARD["lidar"]
    H += [("lidar bracket", box(-L["x"] / 2, L["x"] / 2, L["y0"], L["y1"], -L["t"], 0.0), "printed"),
          ("ld06", box(-ld["L_mm"] / 2, ld["L_mm"] / 2, L["y"] - ld["W_mm"] / 2,
                       L["y"] + ld["W_mm"] / 2, -L["t"] - ld["H_mm"], -L["t"]), "printed")]
    R = G["range"]
    H += [("range cradle", box(-R["x"] / 2, R["x"] / 2, R["y"] - R["yl"] / 2, R["y"] + R["yl"] / 2,
                               -R["body_h"], 0.0), "printed"),
          ("range lid", box(-R["x"] / 2, R["x"] / 2, R["y"] - R["yl"] / 2, R["y"] + R["yl"] / 2,
                            -R["body_h"] - R["lid_t"], -R["body_h"]), "printed")]
    #the ground under the skids
    gz = -(design.SKID["drop"] + design.SKID["t"])
    H.append(("ground", box(-1e4, 1e4, -1e4, 1e4, gz - 1e3, gz), "ground"))
    return H


#a route: its corners, their radii, and the paths a real cable can take
def corners(V, d_in, d_out):
    """Turn angle at every vertex, the plug exit and the far socket included."""
    n = len(V)
    th = []
    for i in range(n):
        a = d_in if i == 0 else sub(V[i], V[i - 1])
        b = d_out if i == n - 1 else sub(V[i + 1], V[i])
        th.append(angle(a, b))
    return th


def radii(V, th):
    """Largest arc at each corner that fits."""
    tau = [math.tan(t / 2) if t > math.radians(0.5) else 0.0 for t in th]
    n = len(V)
    S = []
    for k in range(n - 1):
        tt = tau[k] + tau[k + 1]
        S.append(math.inf if tt == 0 else norm(sub(V[k + 1], V[k])) / tt)
    R = []
    for i in range(n):
        if tau[i] == 0.0:
            R.append(math.inf)
        elif i == 0 or i == n - 1:
            R.append(0.0)
        else:
            R.append(min(S[i - 1], S[i]))
    return R


def fillet(V, th, R, f):
    """The route with every corner replaced by an arc of f x its largest radius."""
    if f == 0.0:
        return list(V)
    out = [V[0]]
    for i in range(1, len(V) - 1):
        r = f * R[i]
        if not math.isfinite(r) or r <= 0.0:
            out.append(V[i]); continue
        a, b = unit(sub(V[i], V[i - 1])), unit(sub(V[i + 1], V[i]))
        t = r * math.tan(th[i] / 2)
        A, Bp = sub(V[i], mul(a, t)), add(V[i], mul(b, t))
        nrm = unit(sub(b, mul(a, dot(a, b))))
        C = add(A, mul(nrm, r))
        k = max(2, int(r * th[i] / STEP) + 1)
        for j in range(k + 1):
            phi = th[i] * j / k
            #from C, the arc starts at -nrm*r and turns toward a
            out.append(add(C, add(mul(nrm, -r * math.cos(phi)), mul(a, r * math.sin(phi)))))
        out[-1] = Bp
    out.append(V[-1])
    return out


def samples(path):
    for p, q in zip(path, path[1:]):
        L = norm(sub(q, p))
        k = max(1, int(L / STEP))
        for j in range(k + 1):
            yield add(p, mul(sub(q, p), j / k))


def length(V):
    return sum(norm(sub(q, p)) for p, q in zip(V, V[1:]))


#the gate
def check(ref, c, plug, H):
    lead = cables.LEADS[c["type"]]
    r_c = lead["od"] * cables.BUNDLE_X[c["wires"]] / 2
    rmin = lead["rmin_x"] * lead["od"]
    V = [plug["exit"]] + [tuple(map(float, p)) for p in c["via"]]
    d_in = plug["u"]
    if c["end"] is not None:
        V.append(tuple(map(float, c["end"])))
        d_out = c["end_dir"]
    else:
        d_out = sub(V[-1], V[-2])           #an open end: the lead runs on as it goes
    th = corners(V, d_in, d_out)
    R = radii(V, th)
    bends = [(R[i], i) for i in range(len(V)) if th[i] > math.radians(0.5)]
    tight, at = min(bends) if bends else (math.inf, None)

    #clearance, along the polyline and the filleted paths
    skip = set(c["touches"]) | {f"plug {ref}"}
    worst = None                            #(clearance - margin, clearance, name, margin)
    prop = None                             #the nearest prop disc, reported on its own
    for f in FILLETS:
        for p in samples(fillet(V, th, R, f)):
            for name, shape, mk in H:
                if name in skip:
                    continue
                clr = dist(p, shape) - r_c
                m = cables.MARGIN[mk]
                if worst is None or clr - m < worst[0]:
                    worst = (clr - m, clr, name, m, p)
                if mk == "prop" and (prop is None or clr < prop):
                    prop = clr

    run = length(V)
    bodies = plug["body"] + cables.FAR_BODY[c["far"]]
    slack = max(cables.SLACK["min"], cables.SLACK["frac"] * run)
    need = run + bodies + slack
    if c["end"] is None:
        need = run + bodies                 #a lower bound: no slack on a run not yet known
    fails = []
    if tight < rmin:
        fails.append(f"bend R {tight:.1f} mm at {'the plug' if at == 0 else 'the far end' if at == len(V) - 1 else 'waypoint ' + str(at)} "
                     f"< {rmin:.1f}")
    if worst[0] < 0.0:
        fails.append(f"{worst[2]} {worst[1]:.1f} mm < {worst[3]:.1f} at "
                     f"({worst[4][0]:.1f}, {worst[4][1]:.1f}, {worst[4][2]:.1f})")
    if c["end"] is not None and (c["buy"] is None or need > c["buy"]):
        fails.append(f"needs {need:.0f} mm, buying {c['buy']}")
    return dict(run=run, need=need, tight=tight, rmin=rmin, worst=worst, fails=fails,
                r_c=r_c, V=V, th=th, R=R, prop=prop)


SCAD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cad", "cables.scad")


def write_scad(results):
    """cad/cables.scad: each lead as the filleted path the gate checked."""
    out = ["// GENERATED by tools/check_cables.py --scad - DO NOT EDIT.",
           "// Each lead along the full-radius filleted path tools/check_cables.py checks,",
           "// at its bundle's diameter. A lead whose far end is undefined stops where its",
           "// known run does.", "",
           "module lead(pts, r) {",
           "    for (i = [0 : len(pts) - 2]) hull() {",
           "        translate(pts[i]) sphere(r = r, $fn = 8);",
           "        translate(pts[i + 1]) sphere(r = r, $fn = 8);",
           "    }",
           "}", "", "module cables() {"]
    for ref, r in results:
        pts = samples(fillet(r["V"], r["th"], r["R"], 1.0))
        body = ", ".join(f"[{x:.2f}, {y:.2f}, {z:.2f}]" for x, y, z in pts)
        out.append(f"    color(\"#222222\") lead([{body}], {max(r['r_c'], 0.5):.2f});   // {ref}")
    out.append("}")
    open(SCAD, "w").write("\n".join(out) + "\n")
    print(f"wrote {os.path.relpath(SCAD)}")


FAULTS = {
    "short": ("J3 bought at 150 mm", lambda C: C["J3"].update(buy=150)),
    "prop":  ("J12's climb past the top plate moved down to prop height, beside the "
              "aft-starboard prop",
              lambda C: C["J12"]["via"].__setitem__(2, (34.0, 66.0, 30.0))),
    "bend":  ("J2's loop pulled in to 2 mm outside its plug",
              lambda C: C["J2"].update(via=[(-29.7, 5.4, 29.5), (-29.7, 5.4, 13.55)])),
    "plate": ("J9 run straight through the bottom plate",
              lambda C: C["J9"]["via"].__setitem__(3, (-4.0, 80.0, 0.0))),
}


def main(argv):
    fault = None
    verbose = "-v" in argv
    if "--fault" in argv:
        i = argv.index("--fault")
        fault = argv[i + 1] if i + 1 < len(argv) else ""
        if fault not in FAULTS:
            print(f"--fault takes one of {', '.join(FAULTS)}")
            return 2
        FAULTS[fault][1](cables.CABLES)
        print(f"FAULT INJECTED: {FAULTS[fault][0]}\n")

    try:
        board = pcbnew.LoadBoard(gen_scad_plugs.BOARD)
        fc_z, rs = stack_z(board)
        plugs = plug_exits(board, fc_z)
    except Exception as e:                          #a gate fails, it does not vanish
        print(f"FAIL - could not read the board: {e}")
        return 1
    H = hazards(fc_z, rs, plugs)
    print(f"cables through the airframe (FC underside z {fc_z:.2f} mm, top plate "
          f"underside z {rs['top_plate_z']:.2f}; margins: prop {cables.MARGIN['prop']:.0f}, "
          f"carbon {cables.MARGIN['carbon']:.0f}, printed {cables.MARGIN['printed']:.1f} mm)")
    warns = []
    for ref in sorted(plugs):
        fm, bm = floorplan_mouth(ref), plugs[ref]["mouth"]
        if math.hypot(fm[0] - bm[0], fm[1] - bm[1]) > 0.1:
            warns.append(f"{ref}: the board's plug mouth ({bm[0]:.2f}, {bm[1]:.2f}) is not "
                         f"FLOORPLAN_REV_D's ({fm[0]:.2f}, {fm[1]:.2f}); routed from the board")

    fails, results = [], []
    for ref, c in sorted(cables.CABLES.items(), key=lambda kv: (len(kv[0]), kv[0])):
        if ref not in plugs:
            fails.append(f"{ref}: not a mated port in design.MATING_FACE")
            continue
        r = check(ref, c, plugs[ref], H)
        results.append((ref, r))
        w = r["worst"]
        near = f"prop {r['prop']:5.1f}  nearest {w[2]} {w[1]:.1f} mm (>= {w[3]:.1f})"
        bend = (f"bend R {r['tight']:5.1f} >= {r['rmin']:4.1f}" if math.isfinite(r["tight"])
                else f"bend none     >= {r['rmin']:4.1f}")
        if c["end"] is None:
            line = (f"  {ref:4s} run {r['run']:5.1f}  need >={r['need']:3.0f}  buy   -     "
                    f"{bend}  {near}  END UNDEFINED")
        else:
            line = (f"  {ref:4s} run {r['run']:5.1f}  need {r['need']:4.0f}  buy {c['buy']:4d} mm  "
                    f"{bend}  {near}")
        print(line + ("  ok" if not r["fails"] else "  FAIL"))
        if verbose:
            for v, t, rr in zip(r["V"], r["th"], r["R"]):
                print(f"        ({v[0]:7.2f}, {v[1]:7.2f}, {v[2]:6.2f})  turn "
                      f"{math.degrees(t):5.1f} deg  R {rr:6.1f}")
        for f_ in r["fails"]:
            fails.append(f"{ref}: {f_}")
        if c["end"] is not None and not r["fails"]:
            shorter = [s for s in cables.STOCK[c["type"]] if r["need"] <= s < c["buy"]]
            if shorter:
                warns.append(f"{ref}: a {shorter[0]} mm lead would do; buying {c['buy']}")
    if "--scad" in argv:
        write_scad(results)
    print()
    for ref, c in sorted(cables.CABLES.items()):
        if c["end"] is None:
            print(f"  {ref}: far end undefined - {c['undefined']}")
    for w_ in warns:
        print("  WARN " + w_)
    if fails:
        print(f"FAIL - {len(fails)} cable problem(s)")
        for f_ in fails:
            print("  - " + f_)
        return 1
    print(f"PASS - {sum(1 for c in cables.CABLES.values() if c['end'] is not None)} cables "
          f"routed, length, bend and clearance met")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
