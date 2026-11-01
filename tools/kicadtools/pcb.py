#small pcbnew helpers: units, design rules, zone filling and kicad-cli DRC
import collections, os, re, subprocess, tempfile
import pcbnew
from kicadtools.project import design

MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
TRACK_W = 0.1016            #4 mil, JLCPCB's free-tier minimum
CLEAR = 0.1016
VIA_D, VIA_DRILL = 0.60, 0.30

#parts whose two ends are interchangeable
NONPOLAR = getattr(design, "NONPOLAR_SYMBOLS", {
    "Device:R", "Device:R_Small", "Device:C", "Device:C_Small", "Device:L", "Device:L_Small",
    "Device:FerriteBead", "Device:FerriteBead_Small", "Device:D_TVS", "Switch:SW_Push"})


def nonpolar(ref):
    c = getattr(design, "COMPONENTS", {}).get(ref)
    return bool(c) and (c[0] in NONPOLAR or c[0].startswith("Device:R_Pack"))



#rebuild connectivity, then fill every zone
def fill(board):
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


#apply the board's design rules (JLCPCB, 4 mil)
def set_rules(board):
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = MM(TRACK_W)
    ds.m_ViasMinSize = MM(0.45)
    ds.m_MinThroughDrill = MM(0.20)
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_MinClearance = MM(CLEAR)
    ds.m_HoleClearance = MM(0.20)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(MM(CLEAR))
    nc.SetTrackWidth(MM(TRACK_W))
    nc.SetViaDiameter(MM(VIA_D))
    nc.SetViaDrill(MM(VIA_DRILL))
    ds.m_MinResolvedSpokes = 1
    ds.SetCopperLayerCount(getattr(design, "COPPER_LAYERS", board.GetCopperLayerCount()))

    net_classes = getattr(design, "NET_CLASSES", {})
    if net_classes:
        ns = ds.m_NetSettings
        for cname, cinfo in net_classes.items():
            if cname == "Default":
                nc.SetTrackWidth(MM(cinfo.get("width", TRACK_W)))
                nc.SetClearance(MM(cinfo.get("clearance", CLEAR)))
                nc.SetViaDiameter(MM(cinfo.get("via_dia", VIA_D)))
                nc.SetViaDrill(MM(cinfo.get("via_drill", VIA_DRILL)))
                continue
            c = pcbnew.NETCLASS(cname)
            c.SetTrackWidth(MM(cinfo.get("width", TRACK_W)))
            c.SetClearance(MM(cinfo.get("clearance", CLEAR)))
            c.SetViaDiameter(MM(cinfo.get("via_dia", VIA_D)))
            c.SetViaDrill(MM(cinfo.get("via_drill", VIA_DRILL)))
            if "diff_pair_width" in cinfo:
                c.SetDiffPairWidth(MM(cinfo["diff_pair_width"]))
            if "diff_pair_gap" in cinfo:
                c.SetDiffPairGap(MM(cinfo["diff_pair_gap"]))
            ns.SetNetclass(cname, c)
            for netname in cinfo.get("nets", []):
                ns.SetNetclassPatternAssignment(netname, cname)
        ns.RecomputeEffectiveNetclasses()

        fname = board.GetFileName()
        pro_path = (os.path.splitext(fname)[0] + ".kicad_pro") if fname else None
        if not pro_path or not os.path.isfile(pro_path):
            from kicadtools import project
            try:
                pro_path = os.path.splitext(project.board_path())[0] + ".kicad_pro"
            except Exception:
                pro_path = None
        if pro_path and os.path.isfile(pro_path):
            try:
                import json
                with open(pro_path) as f:
                    pro = json.load(f)
                classes = pro.setdefault("net_settings", {}).setdefault("classes", [])
                patterns = pro.setdefault("net_settings", {}).setdefault("netclass_patterns", [])
                for cname, cinfo in net_classes.items():
                    match = next((c for c in classes if c.get("name") == cname), None)
                    if match:
                        match["track_width"] = cinfo.get("width", 0.15)
                        match["clearance"] = cinfo.get("clearance", 0.1016)
                        match["via_diameter"] = cinfo.get("via_dia", 0.45)
                        match["via_drill"] = cinfo.get("via_drill", 0.20)
                        if "diff_pair_width" in cinfo:
                            match["diff_pair_width"] = cinfo["diff_pair_width"]
                        if "diff_pair_gap" in cinfo:
                            match["diff_pair_gap"] = cinfo["diff_pair_gap"]
                    else:
                        classes.append({
                            "bus_width": 12,
                            "clearance": cinfo.get("clearance", 0.1016),
                            "diff_pair_gap": cinfo.get("diff_pair_gap", 0.25),
                            "diff_pair_via_gap": 0.25,
                            "diff_pair_width": cinfo.get("diff_pair_width", 0.2),
                            "line_style": 0,
                            "microvia_diameter": 0.3,
                            "microvia_drill": 0.1,
                            "name": cname,
                            "pcb_color": "rgba(0, 0, 0, 0.000)",
                            "priority": len(classes),
                            "schematic_color": "rgba(0, 0, 0, 0.000)",
                            "track_width": cinfo.get("width", 0.15),
                            "via_diameter": cinfo.get("via_dia", 0.45),
                            "via_drill": cinfo.get("via_drill", 0.20),
                            "wire_width": 6
                        })
                existing_pat = {(p.get("pattern"), p.get("netclass")) for p in patterns}
                for cname, cinfo in net_classes.items():
                    for net in cinfo.get("nets", []):
                        if (net, cname) not in existing_pat:
                            patterns.append({"netclass": cname, "pattern": net})
                with open(pro_path, "w") as f:
                    json.dump(pro, f, indent=2)
            except Exception:
                pass


#area of a polygon given as [(x, y), ...]
def area(p):
    a = 0.0
    for i in range(len(p)):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % len(p)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


#the copper layers of the board file at `path`, top to bottom
def copper(path):
    if not path or not os.path.isfile(path):
        return ["F.Cu", "B.Cu"]
    names = set(re.findall(r'\(\d+ "((?:F|B|In\d+)\.Cu)"', open(path).read(50000)))
    return ["F.Cu"] + sorted((n for n in names if n.startswith("In")),
                             key=lambda n: int(n[2:-3])) + ["B.Cu"]


#the violation class of every item in a kicad-cli report
def classes(report):
    return re.findall(r"^\[([a-z_]+)\]", report, re.M)


#kicad-cli DRC of the board at `path`
def drc(path, everything=False):
    with tempfile.TemporaryDirectory() as d:
        rpt = os.path.join(d, "drc.rpt")
        subprocess.run(["kicad-cli", "pcb", "drc", "--output", rpt,
                        "--severity-all" if everything else "--severity-error", path],
                       capture_output=True, timeout=900)
        text = open(rpt).read()
    cls = classes(text)
    return len([c for c in cls if c != "unconnected_items"]), cls.count("unconnected_items"), text


#how many track and via ends kicad-cli calls dangling at `path`
def dangling(path):
    _e, _u, txt = drc(path, everything=True)
    return sum(1 for c in classes(txt) if c in ("track_dangling", "via_dangling"))


#segment indices in a closed loop that reaches no pad and no pour of its net
def _loop_dead(board, net, segs, vias, pads, live_t, fills):
    def N(p):
        return (p.x // 1000, p.y // 1000)

    live = sorted(live_t)
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    point = {}
    for i in live:
        t = segs[i]
        for p in (t.GetStart(), t.GetEnd()):
            parent.setdefault(N(p), N(p))
            point.setdefault(N(p), p)
    for v in vias:
        p = v.GetPosition()
        vk = ("v", p.x // 1000, p.y // 1000)
        parent.setdefault(vk, vk)
        point.setdefault(vk, p)
        for i in live:
            t = segs[i]
            for e in (t.GetStart(), t.GetEnd()):
                if (e - p).EuclideanNorm() <= v.GetWidth(t.GetLayer()) // 2:
                    parent.setdefault(N(e), N(e))
                    point.setdefault(N(e), e)
                    union(N(e), vk)
    #edges between the merged vertices, each segment one edge
    edges = collections.defaultdict(list)
    deg = {}
    for i in live:
        t = segs[i]
        u, w = find(N(t.GetStart())), find(N(t.GetEnd()))
        edges[u].append((w, i))
        edges[w].append((u, i))
        deg[u] = deg.get(u, 0) + 1
        deg[w] = deg.get(w, 0) + 1
    for r in list(parent):
        parent[r] = find(r)
    #connected components of the edge graph
    comp, seen = [], set()
    for start in list(edges):
        if start in seen:
            continue
        stack, members = [start], set()
        while stack:
            u = stack.pop()
            if u in members:
                continue
            members.add(u)
            for w, _i in edges.get(u, ()):
                stack.append(w)
        seen |= members
        comp.append(members)

    def anchored(r, layers):
        pt = point[find(r)]
        for l in layers:
            if any(p.IsOnLayer(l) and p.HitTest(pt, 0) for p in pads):
                return True
            if any(f.Contains(pt) for f in fills.get((net, l), ())):
                return True
        return False

    dead = set()
    for members in comp:
        idxs = {i for r in members for w, i in edges.get(r, ())}
        lay = {}
        for i in idxs:
            t = segs[i]
            for p in (t.GetStart(), t.GetEnd()):
                lay.setdefault(find(N(p)), set()).add(t.GetLayer())
        if all(deg.get(r, 0) == 2 for r in members) \
                and not any(anchored(r, lay.get(r, ())) for r in members):
            dead |= idxs
    return dead


#(tracks, vias) that lead to no pad and no pour of their net
def dead_copper(board):
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    fills = {}
    for z in board.Zones():
        if not z.GetIsRuleArea():
            for l in z.GetLayerSet().CuStack():
                fills.setdefault((z.GetNetCode(), l), []).append(z.GetFilledPolysList(l))
    all_t = [t for t in board.GetTracks() if t.Type() != pcbnew.PCB_VIA_T]
    all_v = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    dead_t, dead_v = [], []
    for net in {t.GetNetCode() for t in all_t}:
        segs = [t for t in all_t if t.GetNetCode() == net]
        vias = [v for v in all_v if v.GetNetCode() == net]
        mine = [p for p in pads if p.GetNetCode() == net]
        live_t, live_v = set(range(len(segs))), set(range(len(vias)))

        #what copper other than segment `own` the round end of radius r at pt touches
        def touches(lay, pt, own, r):
            out = {("pad", k) for k, p in enumerate(mine) if p.IsOnLayer(lay) and p.HitTest(pt, r)}
            if any(f.Collide(pcbnew.SHAPE_CIRCLE(pt, max(r, 1))) for f in fills.get((net, lay), ())):
                out.add(("pour", lay))
            out |= {("via", k) for k in live_v if vias[k].IsOnLayer(lay)
                    and (vias[k].GetPosition() - pt).EuclideanNorm() <= vias[k].GetWidth(lay) // 2 + r}
            return out | {("seg", k) for k in live_t
                          if k != own and segs[k].GetLayer() == lay and segs[k].HitTest(pt, r)}
        changed = True
        while changed:
            changed = False
            for i in list(live_t):
                t = segs[i]
                r = t.GetWidth() // 2
                a, c = (touches(t.GetLayer(), p, i, r) for p in (t.GetStart(), t.GetEnd()))
                #an end on nothing
                if not a or not c or (a == c and len(a) == 1):
                    live_t.discard(i); changed = True
            for k in list(live_v):
                v = vias[k]
                layers = {segs[j].GetLayer() for j in live_t
                          if segs[j].HitTest(v.GetPosition(), v.GetWidth(segs[j].GetLayer()) // 2)}
                anchored = any(p.IsOnLayer(l) and p.HitTest(v.GetPosition(), v.GetWidth(l) // 2)
                               for p in mine for l in v.GetLayerSet().CuStack()) or any(
                    f.Contains(v.GetPosition()) for l in board.GetEnabledLayers().CuStack()
                    if v.IsOnLayer(l) for f in fills.get((net, l), ()))
                if len(layers) <= 1 and not anchored:
                    live_v.discard(k); changed = True
        for i in _loop_dead(board, net, segs, vias, mine, live_t, fills):
            live_t.discard(i)
        dead_t += [segs[i] for i in range(len(segs)) if i not in live_t]
        dead_v += [vias[k] for k in range(len(vias)) if k not in live_v]
    return dead_t, dead_v
