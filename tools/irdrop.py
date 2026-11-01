#!/usr/bin/env python3
"""DC IR-drop and current density of a net: its copper from pcbnew, the resistor mesh with numpy.

Usage:  python3 irdrop.py check [NET ...] [--grid 0.05] [--self-test]
        python3 irdrop.py export NET out.json [board.kicad_pcb]
        python3 irdrop.py solve out.json [grid_mm=0.04] [--inner1oz]
"""
import json, math, sys
from types import SimpleNamespace
from kicadtools import project
from kicadtools.project import design

RHO = 1.72e-8                #copper, ohm m
PLATING = 20e-6              #via barrel, m
DROP_MAX_MV = getattr(design, "DROP_MAX_MV", 50.0)
#IPC-2221 at 10 C rise
DENSITY_MAX = getattr(design, "CURRENT_DENSITY_MAX", {"outer": 100.0, "inner": 50.0})
VIA_A_PER_MM_DRILL = getattr(design, "VIA_A_PER_MM_DRILL", 3.3)     #1 A for a 0.3 mm drill
SMOOTH_MM = 0.3


#one net's copper, pads, vias, source and loads
def export(net, board=None, thin=False):
    import pcbnew
    from kicadtools import pcb
    if board is None:
        board = pcbnew.LoadBoard(project.board_path()); pcb.fill(board)
    b, mm = board, pcbnew.ToMM
    ERR = pcbnew.FromMM(0.005)
    CU = [l for l in b.GetEnabledLayers().CuStack()]
    names = [b.GetLayerName(l) for l in CU]
    def rings(sps):
        res = []
        for i in range(sps.OutlineCount()):
            poly = [[[mm(p.x), mm(p.y)] for p in [sps.Outline(i).CPoint(k) for k in range(sps.Outline(i).PointCount())]]]
            for h in range(sps.HoleCount(i)):
                hole = sps.Hole(i, h); poly.append([[mm(hole.CPoint(k).x), mm(hole.CPoint(k).y)] for k in range(hole.PointCount())])
            res.append(poly)
        return res
    layers = {n: [] for n in names}
    code = b.FindNet(net).GetNetCode()
    for t in b.GetTracks():
        if t.GetNetCode() != code or t.GetClass() == 'PCB_VIA': continue
        sps = pcbnew.SHAPE_POLY_SET()
        if thin:                     #the self-test: every track at the fab minimum, no pours
            w = t.GetWidth(); t.SetWidth(pcbnew.FromMM(0.1016))
        t.TransformShapeToPolygon(sps, t.GetLayer(), 0, ERR, pcbnew.ERROR_INSIDE)
        if thin:
            t.SetWidth(w)
        layers[b.GetLayerName(t.GetLayer())] += rings(sps)
    for z in b.Zones():
        if thin or z.GetNetCode() != code or z.GetIsRuleArea(): continue
        for l in z.GetLayerSet().CuStack():
            layers[b.GetLayerName(l)] += rings(z.GetFilledPolysList(l))
    pads = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() != code: continue
            key = f"{f.GetReference()}.{p.GetNumber()}"; per = {}
            for l in CU:
                if not p.IsOnLayer(l): continue
                sps = pcbnew.SHAPE_POLY_SET(); p.TransformShapeToPolygon(sps, l, 0, ERR, pcbnew.ERROR_INSIDE)
                r = rings(sps); per[b.GetLayerName(l)] = r; layers[b.GetLayerName(l)] += r
            pads[key] = per
    vias = []
    for v in b.GetTracks():
        if v.GetClass() != 'PCB_VIA' or v.GetNetCode() != code: continue
        top, bot = v.TopLayer(), v.BottomLayer()
        span = [b.GetLayerName(l) for l in CU if CU.index(top) <= CU.index(l) <= CU.index(bot)]
        vias.append({'x': mm(v.GetPosition().x), 'y': mm(v.GetPosition().y), 'dia': mm(v.GetWidth(top)), 'drill': mm(v.GetDrillValue()), 'layers': span})
    #a part's name stands for all of its pads on the rail
    loads = {}
    for key, amps in getattr(design, 'LOAD_CURRENT', {}).get(net, {}).items():
        mine = [k for k in pads if k == key or ("." not in key and k.split(".")[0] == key)]
        for k in mine or [key]:
            loads[k] = loads.get(k, 0.0) + amps / max(len(mine), 1)
    profiles = {k: list(p['keys']) for k, p in getattr(design, 'PAYLOAD_PROFILES', {}).items()} if net == '+5V_PAYLOAD' else {}
    gaps = getattr(design, 'LAYER_GAPS_MM', None) or [pcbnew.ToMM(b.GetDesignSettings().GetBoardThickness()) / (len(names) - 1)] * (len(names) - 1)
    return {'net': net, 'layers': names, 'gaps': gaps, 'copper': layers, 'pads': pads, 'vias': vias,
            'source': getattr(design, 'NET_SOURCE', {}).get(net), 'loads': loads, 'profiles': profiles,
            'want': getattr(design, 'NET_CURRENT', {}).get(net)}


#the net's copper as a resistor mesh on an H mm grid, ready to solve
def model(D, H=0.04, inner_um=None):
    import numpy as np
    inner_um = inner_um or getattr(design, "INNER_COPPER_UM", 17.5)
    T = {n: (35e-6 if n in ('F.Cu', 'B.Cu') else inner_um * 1e-6) for n in D['layers']}
    GAP = dict(zip(D['layers'][:-1], D['gaps']))                                       #mm between a layer and the next
    pts = [p for L in D['copper'].values() for poly in L for ring in poly for p in ring]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    X0, Y0 = min(xs) - 1, min(ys) - 1; NX = int((max(xs) + 1 - X0) / H) + 1; NY = int((max(ys) + 1 - Y0) / H) + 1
    def raster(polys):
        m = np.zeros((NY, NX), bool)
        for poly in polys:
            e = []
            for ring in poly:
                r = np.array(ring)
                e.append(np.column_stack([r, np.roll(r, -1, axis=0)]))
            e = np.vstack(e); ya, yb = e[:, 1], e[:, 3]
            j0 = max(0, int((min(ya.min(), yb.min()) - Y0) / H)); j1 = min(NY - 1, int((max(ya.max(), yb.max()) - Y0) / H) + 1)
            for j in range(j0, j1 + 1):
                yc = Y0 + (j + 0.5) * H
                c = (ya <= yc) != (yb <= yc)
                if not c.any(): continue
                ee = e[c]; xi = ee[:, 0] + (yc - ee[:, 1]) * (ee[:, 2] - ee[:, 0]) / (ee[:, 3] - ee[:, 1])
                xi = np.sort(xi)
                for a, bq in zip(xi[0::2], xi[1::2]):
                    i0 = max(0, int(math.ceil((a - X0) / H - 0.5))); i1 = min(NX - 1, int(math.floor((bq - X0) / H - 0.5)))
                    if i1 >= i0: m[j, i0:i1 + 1] = True
        return m
    def disk(x, y, r):
        jj, ii = np.ogrid[:NY, :NX]
        return (X0 + (ii + 0.5) * H - x) ** 2 + (Y0 + (jj + 0.5) * H - y) ** 2 <= r * r
    masks = {n: raster(D['copper'][n]) for n in D['layers']}
    for v in D['vias']:
        for n in v['layers']: masks[n] |= disk(v['x'], v['y'], v['dia'] / 2)
    #node numbering, and where each node is
    idx, nj, ni, nl = {}, [], [], []
    base = 0
    for li, n in enumerate(D['layers']):
        a = -np.ones((NY, NX), np.int64); k = int(masks[n].sum()); a[masks[n]] = np.arange(base, base + k); idx[n] = a; base += k
        jj, ii = np.nonzero(masks[n]); nj.append(jj); ni.append(ii); nl.append(np.full(k, li))
    N = base
    nj, ni, nl = np.concatenate(nj), np.concatenate(ni), np.concatenate(nl)
    ei, ej, eg = [], [], []
    for n in D['layers']:
        a = idx[n]; g = T[n] / RHO
        for sl1, sl2 in (((slice(None), slice(0, -1)), (slice(None), slice(1, None))), ((slice(0, -1), slice(None)), (slice(1, None), slice(None)))):
            p, q = a[sl1], a[sl2]; ok = (p >= 0) & (q >= 0)
            ei.append(p[ok]); ej.append(q[ok]); eg.append(np.full(ok.sum(), g))
    n_plane = sum(len(x) for x in ei)
    via_links = []                                       #per via, its links' indices
    for v in D['vias']:
        i, j = int((v['x'] - X0) / H), int((v['y'] - Y0) / H)
        L, mine = v['layers'], []
        for a, b_ in zip(L, L[1:]):
            p, q = idx[a][j, i], idx[b_][j, i]
            if p >= 0 and q >= 0:
                mine.append(n_plane + len(ei) - len(D['layers']) * 2)
                ei.append(np.array([p])); ej.append(np.array([q])); eg.append(np.array([math.pi * v['drill'] * 1e-3 * PLATING / (RHO * GAP[a] * 1e-3)]))
        via_links.append(mine)
    #the barrel meets each layer all round the hole wall, not at one point
    for v in D['vias']:
        i, j = int((v['x'] - X0) / H), int((v['y'] - Y0) / H)
        hole = disk(v['x'], v['y'], v['drill'] / 2 + H / 2)
        for n in v['layers']:
            c = idx[n][j, i]
            if c < 0: continue
            cells = idx[n][hole]; cells = cells[(cells >= 0) & (cells != c)]
            ei.append(np.full(len(cells), c)); ej.append(cells); eg.append(np.full(len(cells), 10 * T[n] / RHO))
    ei = np.concatenate(ei); ej = np.concatenate(ej); eg = np.concatenate(eg)
    def padnodes(key):
        out = []
        for n, polys in D['pads'].get(key, {}).items():
            m = raster(polys); out.append(idx[n][m & masks[n]])
        return np.concatenate(out) if out else np.array([], np.int64)
    src = padnodes(D['source'])
    #what the source reaches: labels spread along the links
    lab = np.arange(N)
    while True:
        m = np.minimum(lab[ei], lab[ej])
        new = lab.copy(); np.minimum.at(new, ei, m); np.minimum.at(new, ej, m)
        while True:
            jumped = new[new]
            if (jumped == new).all(): break
            new = jumped
        if (new == lab).all(): break
        lab = new
    live = np.isin(lab, np.unique(lab[src])) if len(src) else np.zeros(N, bool)
    diag = np.bincount(ei, eg, N) + np.bincount(ej, eg, N)
    def solve(currents):
        I = np.zeros(N)
        for key, amps in currents.items():
            nodes = padnodes(key); nodes = nodes[live[nodes]]
            if len(nodes) == 0: continue
            I[nodes] -= amps / len(nodes)
        fixed = np.zeros(N, bool); fixed[src] = True
        free = live & ~fixed
        def A(x):
            y = diag * x - np.bincount(ei, eg * x[ej], N) - np.bincount(ej, eg * x[ei], N)
            y[~free] = 0; return y
        x = np.zeros(N); r = I.copy(); r[~free] = 0
        M = np.where(free, 1 / np.maximum(diag, 1e-30), 0); z = M * r; p = z.copy(); rz = r @ z; n0 = math.sqrt(r @ r) + 1e-30
        it = 0
        for it in range(20000):
            if math.sqrt(r @ r) < 1e-9 * n0: break
            Ap = A(p); al = rz / (p @ Ap); x += al * p; r -= al * Ap
            z = M * r; rz2 = r @ z; p = z + (rz2 / rz) * p; rz = rz2
        cur = eg * (x[ei] - x[ej])
        return x, cur, it
    #{layer: (A/mm2 per cell averaged over SMOOTH_MM, (x, y) of its peak)}
    def density(cur):
        out = {}
        k = max(1, round(SMOOTH_MM / H))
        inplane = np.arange(len(ei)) < n_plane
        for li, n in enumerate(D['layers']):
            if not masks[n].any(): continue
            jx, jy = np.zeros((NY, NX)), np.zeros((NY, NX))
            sel = inplane & (nl[ei] == li)
            a, c, i_ = ei[sel], ej[sel], cur[sel]
            horiz = nj[a] == nj[c]
            for grid, h in ((jx, horiz), (jy, ~horiz)):
                np.add.at(grid, (nj[a[h]], ni[a[h]]), i_[h] / 2)
                np.add.at(grid, (nj[c[h]], ni[c[h]]), i_[h] / 2)
            d = np.hypot(jx, jy) / (H * T[n] * 1e3) * masks[n]
            cs = lambda g: np.pad(g, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
            S, C = cs(d), cs(masks[n].astype(float))
            box = lambda s: s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k]
            sm = box(S) / np.maximum(box(C), 1)
            sm *= masks[n][k // 2:k // 2 + sm.shape[0], k // 2:k // 2 + sm.shape[1]]
            j, i = np.unravel_index(np.argmax(sm), sm.shape)
            out[n] = (float(sm[j, i]), (X0 + (i + k / 2) * H, Y0 + (j + k / 2) * H))
        return out
    return SimpleNamespace(N=N, NX=NX, NY=NY, H=H, T=T, live=live, src=src, padnodes=padnodes,
                           solve=solve, density=density, via_links=via_links, X0=X0, Y0=Y0,
                           masks=masks, idx=idx, ei=ei, ej=ej)


def run_export():
    d = export(sys.argv[1], None if len(sys.argv) <= 3 else __import__("pcbnew").LoadBoard(sys.argv[3]))
    json.dump(d, open(sys.argv[2], 'w'))
    print(f"{d['net']}: {sum(len(v) for v in d['copper'].values())} polygons on "
          f"{len([k for k, v in d['copper'].items() if v])} layers, {len(d['vias'])} vias, "
          f"{len(d['pads'])} pads; source {d['source']}; loads {d['loads']}")
    return 0


def run_solve():
    D = json.load(open(sys.argv[1])); H = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 0.04
    m = model(D, H, 35.0 if '--inner1oz' in sys.argv else None)
    def report(title, currents):
        x, cur, it = m.solve(currents)
        print(f"--- {title}: {sum(currents.values()):.2f} A total (CG {it} it)")
        for key, amps in sorted(currents.items(), key=lambda kv: -kv[1]):
            nodes = m.padnodes(key)
            if len(nodes) == 0: print(f"   {key:8s} {amps:.2f} A  NO COPPER"); continue
            if not m.live[nodes].any(): print(f"   {key:8s} {amps:.2f} A  NOT CONNECTED to {D['source']}"); continue
            print(f"   {key:8s} {amps:.2f} A  drop {-x[nodes].mean()*1000:6.1f} mV")
        for n, (dens, (px, py)) in m.density(cur).items():
            print(f"   {n:7s} peak {dens:6.1f} A/mm2 at ({px:.2f},{py:.2f}), averaged over {SMOOTH_MM} mm")
    print(f"{D['net']}: grid {m.NX}x{m.NY} at {H} mm, {m.N} copper cells, {len(D['vias'])} vias; "
          f"{int(m.live.sum())} cells reach {D['source']}")
    loads = D['loads']
    if D['profiles']:
        for name, keys in D['profiles'].items(): report(f"mission {name}", {k: loads[k] for k in keys if k in loads})
    report('every load at once', loads)
    return 0


#(problems, summary line) for one rail, solved at its budget
def check_net(D, H):
    import numpy as np
    loads, want = dict(D['loads']), D['want'] or 0.0
    if not loads:
        return [f"{D['net']}: no loads declared in design.LOAD_CURRENT"], ""
    missing = [k for k in loads if k not in D['pads']]
    if missing:
        return [f"{D['net']}: loads {', '.join(missing)} are not pads on this net"], ""
    total = sum(loads.values())
    scale = want / total if total and total < want else 1.0
    m = model(D, H)
    x, cur, _it = m.solve({k: a * scale for k, a in loads.items()})
    bad, worst_drop = [], (0.0, None)
    for key in loads:
        nodes = m.padnodes(key)
        if not len(nodes) or not m.live[nodes].any():
            bad.append(f"{D['net']}: {key} is not reached from {D['source']}")
            continue
        drop = -x[nodes].mean() * 1000
        worst_drop = max(worst_drop, (drop, key))
        if drop > DROP_MAX_MV:
            bad.append(f"{D['net']}: {drop:.0f} mV drop at {key} (max {DROP_MAX_MV:.0f})")
    worst_d = (0.0, None, None)
    for n, (dens, (px, py)) in m.density(cur).items():
        lim = DENSITY_MAX["outer" if n in ("F.Cu", "B.Cu") else "inner"]
        if dens / lim > worst_d[0]:
            worst_d = (dens / lim, n, dens)
        if dens > lim:
            bad.append(f"{D['net']}: {dens:.0f} A/mm2 on {n} at ({px:.2f}, {py:.2f}) (max {lim:.0f})")
    worst_v = 0.0
    for v, links in zip(D['vias'], m.via_links):
        if not links:
            continue
        amps = float(np.abs(cur[links]).max())
        lim = VIA_A_PER_MM_DRILL * v['drill']
        worst_v = max(worst_v, amps / lim)
        if amps > lim:
            bad.append(f"{D['net']}: via at ({v['x']:.2f}, {v['y']:.2f}) carries {amps:.2f} A "
                       f"(a {v['drill']:.2f} mm drill takes {lim:.2f})")
    line = (f"{D['net']:13} {want:5.2f} A over {len(loads):2} load(s)"
            + (f" (declared {total:.2f}, scaled)" if scale > 1 else "")
            + f"; drop {worst_drop[0]:5.1f} mV at {worst_drop[1]}; density "
            + (f"{worst_d[2]:5.0f} A/mm2 on {worst_d[1]}" if worst_d[1] else "-")
            + f" ({100 * worst_d[0]:3.0f}% of limit); vias {100 * worst_v:3.0f}% of limit")
    return bad, line


def run_check():
    import pcbnew
    from kicadtools import pcb
    H = float(project.arg("--grid", 0.05))
    b = pcbnew.LoadBoard(project.board_path()); pcb.fill(b)
    rails = [a for i, a in enumerate(sys.argv[1:], 1)
             if not a.startswith("-") and sys.argv[i - 1] not in ("--grid", "--board")] or \
        [n for n in getattr(design, "NET_CURRENT", {}) if getattr(design, "NET_SOURCE", {}).get(n)]
    if "--self-test" in sys.argv:
        #the busiest rail that passes must fail as bare fab-minimum tracks
        for net in sorted(rails, key=lambda n: -design.NET_CURRENT[n]):
            if check_net(export(net, b), H)[0]:
                continue
            bad, _ = check_net(export(net, b, thin=True), H)
            print(f"  {'ok  ' if bad else 'MISS'} {net} as 0.1016 mm tracks without pours: "
                  + (bad[0] if bad else "passed"))
            return 0 if bad else 1
        print("  MISS no rail passes, so none can be shown to fail")
        return 1
    fails = []
    for net in rails:
        bad, line = check_net(export(net, b), H)
        print(("  ok   " if not bad else "  FAIL ") + (line or net))
        fails += bad
    print(f"\n{len(rails)} rail(s) solved at their budget on a {H} mm grid; limits {DROP_MAX_MV:.0f} mV, "
          f"{DENSITY_MAX['outer']:.0f}/{DENSITY_MAX['inner']:.0f} A/mm2 outer/inner, "
          f"{VIA_A_PER_MM_DRILL:.1f} A per mm of via drill")
    if fails:
        print(f"\nFAIL - {len(fails)} problem(s):")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("every rail reaches its loads within its drop, density and via limits")
    return 0


COMMANDS = {"check": run_check, "export": run_export, "solve": run_solve}

if __name__ == "__main__":
    sys.exit(project.main(COMMANDS, __doc__))
