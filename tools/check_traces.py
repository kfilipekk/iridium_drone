#!/usr/bin/env python3
"""Signal-integrity review of the routed copper: length, layer changes, and pair matching."""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heapq
import pcbnew, design, cables

BOARD = "NAVCORE-SoOP.kicad_pcb"
TOMM = lambda v: v / 1e6

#limits are derived, not invented
CRYSTAL_MM = design.Y1_STRAY_PF / 0.1        #~0.1 pF per mm of trace
#an SPI line is electrically short
SPI_TR_PS, TPD_PS_MM = 2800.0, 7.0
SPI_MM = SPI_TR_PS / (6 * TPD_PS_MM)          #~66.7 mm
#nets judged on that path rather than on total copper: summed over a tree
EDGE_LIMITED = {"SPI1_SCK", "SPI1_MISO", "SPI1_MOSI", "SPI4_SCK", "SPI3_SCK"}
CRITICAL = {
    "OSC_IN":       ("crystal - stray C shifts the load; see Y1_STRAY_PF", CRYSTAL_MM),
    "OSC_OUT":      ("crystal", CRYSTAL_MM),
    "USB_DP":       ("USB 2.0 FS - delay is irrelevant at 12 Mbps", 80.0),
    "USB_DM":       ("USB 2.0 FS", 80.0),
    "SPI1_SCK":     ("IMU1 clock - the primary IMU, 24 MHz", SPI_MM),
    "SPI1_MISO":    ("IMU1", SPI_MM),
    "SPI1_MOSI":    ("IMU1", SPI_MM),
    "SPI4_SCK":     ("IMU2 clock", SPI_MM),
    "SPI3_SCK":     ("flash 32 MHz + flow port J14", SPI_MM),
    "I2C1_SCL":     ("external I2C - capacitance-limited, not length-limited", 200.0),
    "I2C1_SDA":     ("external I2C", 200.0),
    "SWCLK":        ("SWD ~4 MHz", 125.0),
    "SWDIO":        ("SWD", 125.0),
}
#USB 2.0 full speed tolerates enormous skew
PAIRS = [("USB_DP", "USB_DM", 20.0)]


def net_stats(board):
    """Length, via count and layer spread per net."""
    out = {}
    for t in board.GetTracks():
        net = t.GetNet()
        if not net:
            continue
        n = net.GetNetname()
        d = out.setdefault(n, {"len": 0.0, "vias": 0, "layers": set()})
        if t.Type() == pcbnew.PCB_VIA_T:
            d["vias"] += 1
        else:
            s, e = t.GetStart(), t.GetEnd()
            d["len"] += math.hypot(TOMM(e.x - s.x), TOMM(e.y - s.y))
            d["layers"].add(board.GetLayerName(t.GetLayer()))
    return out


def longest_path(board, net, driver="U1"):
    """mm from the driver's pad, through the net's copper."""
    T = TOMM
    segs = [t for t in board.GetTracks() if t.GetNetname() == net and t.Type() != pcbnew.PCB_VIA_T]
    vias = [t for t in board.GetTracks() if t.GetNetname() == net and t.Type() == pcbnew.PCB_VIA_T]
    pads = [(fp.GetReference(), p) for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == net]
    nodes = []                                   #(layer, x, y)
    adj = {}

    def node(lay, q):
        nodes.append((lay, T(q.x), T(q.y)))
        adj[len(nodes) - 1] = []
        return len(nodes) - 1

    def link(a, b, w):
        adj[a].append((b, w)); adj[b].append((a, w))

    ends = []
    for t in segs:
        a, b = node(t.GetLayer(), t.GetStart()), node(t.GetLayer(), t.GetEnd())
        link(a, b, T(t.GetLength()))
        ends += [(a, t), (b, t)]
    for i, (a, ta) in enumerate(ends):
        la, xa, ya = nodes[a]
        for b, tb in ends[i + 1:]:
            lb, xb, yb = nodes[b]
            if la == lb and tb is not ta and math.hypot(xa - xb, ya - yb) <= T(ta.GetWidth() + tb.GetWidth()) / 2:
                link(a, b, math.hypot(xa - xb, ya - yb))
        for t in segs:                           #a tee onto another track's body
            if t is ta or t.GetLayer() != la:
                continue
            if t.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(xa), pcbnew.FromMM(ya)), ta.GetWidth() // 2):
                s0, s1 = t.GetStart(), t.GetEnd()
                for q in (s0, s1):
                    j = next(n for n, tt in ends if tt is t and nodes[n][1:] == (T(q.x), T(q.y)))
                    link(a, j, math.hypot(xa - T(q.x), ya - T(q.y)))
    for v in vias:
        c, r = v.GetPosition(), T(v.GetWidth(pcbnew.F_Cu)) / 2
        hub = node(None, c)
        for n, t in ends:
            if math.hypot(nodes[n][1] - T(c.x), nodes[n][2] - T(c.y)) <= r + T(t.GetWidth()) / 2:
                link(hub, n, 0.0)
    padnode = {}
    for ref, p in pads:
        hub = node(None, p.GetPosition())
        padnode[(ref, p.GetNumber())] = hub
        for n, t in ends:
            q = pcbnew.VECTOR2I(pcbnew.FromMM(nodes[n][1]), pcbnew.FromMM(nodes[n][2]))
            if p.IsOnLayer(t.GetLayer()) and p.HitTest(q, t.GetWidth() // 2):
                link(hub, n, 0.0)
    src = [h for (ref, _num), h in padnode.items() if ref == driver]
    if not src:
        return None
    dist = {s0: 0.0 for s0 in src}
    pq = [(0.0, s0) for s0 in src]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        for v2, w in adj[u]:
            if d + w < dist.get(v2, 1e18):
                dist[v2] = d + w
                heapq.heappush(pq, (d + w, v2))
    if any(h not in dist for h in padnode.values()):
        return None
    return max(dist.values())


def offboard_mm(net):
    """The longest lead fitted to a connector on the net."""
    refs = {q.split(".")[0] for q in design.NETS.get(net, [])}
    return max([cables.CABLES[r].get("buy") or 0.0 for r in refs if r in cables.CABLES] or [0.0])


def self_test():
    """Each fault must put SPI3_SCK over its limit, or make a pad unreachable."""
    def over(board):
        path = longest_path(board, "SPI3_SCK")
        return path is None or path + offboard_mm("SPI3_SCK") > SPI_MM

    def stub(board):                       #a spur as long as the limit: over wherever it hangs
        segs = [t for t in board.GetTracks() if t.GetNetname() == "SPI3_SCK"
                and t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() == board.GetLayerID("In2.Cu")]
        t0 = max(segs, key=lambda t: t.GetEnd().x)
        t = pcbnew.PCB_TRACK(board)
        t.SetLayer(t0.GetLayer()); t.SetNet(t0.GetNet()); t.SetWidth(t0.GetWidth())
        t.SetStart(t0.GetEnd()); t.SetEnd(t0.GetEnd() + pcbnew.VECTOR2I(0, pcbnew.FromMM(SPI_MM)))
        board.Add(t)

    def cut(board):                        #the via that takes U1's escape down to In2
        v = min((t for t in board.GetTracks() if t.GetNetname() == "SPI3_SCK"
                 and t.Type() == pcbnew.PCB_VIA_T),
                key=lambda t: abs(TOMM(t.GetPosition().x) - 121.73) + abs(TOMM(t.GetPosition().y) - 123.4))
        board.Remove(v)

    def lead(board):                       #a flow sensor fitted on a 200 mm lead
        cables.CABLES["J14"]["buy"] = 200

    bad = 0
    if over(pcbnew.LoadBoard(BOARD)):
        print("  the unfaulted board is already over - the faults below would prove nothing")
        return 1
    for name, fault in (("spur of the limit's length", stub), ("escape via removed", cut), ("200 mm J14 lead", lead)):
        b = pcbnew.LoadBoard(BOARD)
        keep = cables.CABLES["J14"].get("buy")
        fault(b)
        caught = over(b)
        cables.CABLES["J14"]["buy"] = keep
        print(f"  {'ok  ' if caught else 'MISS'} {name}")
        bad += not caught
    print("self-test " + ("FAILED" if bad else "passed"))
    return 1 if bad else 0


def _all_dnp(net):
    """True if every pad on `net` belongs to a do-not-populate part."""
    pins = design.NETS.get(net) or []
    if not pins:
        return False
    return all((design.COMPONENTS.get(q.split(".")[0]) or (0, 0, 0, 0, False))[4]
               for q in pins)


def main():
    if "--self-test" in sys.argv:
        return self_test()
    board = pcbnew.LoadBoard(BOARD)
    st = net_stats(board)

    print("=== critical nets ===")
    print(f"{'net':14}{'len mm':>8}{'vias':>6}  {'layers':22} note")
    warn = 0
    for n, (why, limit) in CRITICAL.items():
        d = st.get(n)
        if not d:
            print(f"{n:14}{'--':>8}{'--':>6}  {'(not routed)':22} {why}")
            if not _all_dnp(n):
                print(f"{'':14}{'':>8}{'':>6}  {'':22} "
                      f"<-- NOT ROUTED and it is not a DNP-only net")
                warn += 1
            continue
        measure = d["len"]
        if n in EDGE_LIMITED:
            path = longest_path(board, n)
            if path is None:
                print(f"{n:14}{'--':>8}{d['vias']:6}  {'':22} {why}  <-- a pad is unreachable "
                      f"through the copper from U1")
                warn += 1
                continue
            lead = offboard_mm(n)
            measure = path + lead
            why = (f"{why}; longest path {path:.1f} mm" + (f" + {lead:.0f} mm lead" if lead else "")
                   + f" of {limit:.1f} (total copper {d['len']:.1f})")
        flag = "  <-- OVER" if measure > limit else ""
        if measure > limit:
            warn += 1
        print(f"{n:14}{measure:8.1f}{d['vias']:6}  {','.join(sorted(d['layers']))[:22]:22} {why}{flag}")

    print("\n=== differential pair matching ===")
    for a, bnet, tol in PAIRS:
        da, db = st.get(a), st.get(bnet)
        if not (da and db):
            print(f"  {a}/{bnet}: one or both not routed")
            continue
        skew = abs(da["len"] - db["len"])
        ok = skew <= tol
        print(f"  {a} {da['len']:.1f} mm vs {bnet} {db['len']:.1f} mm"
              f"  -> skew {skew:.2f} mm (tolerance {tol})  {'OK' if ok else 'MISMATCHED'}")
        if da["vias"] != db["vias"]:
            print(f"     via counts differ: {da['vias']} vs {db['vias']} - "
                  f"asymmetric pairs radiate and reflect")
        if not ok:
            warn += 1

    print("\n=== longest nets on the board ===")
    for n, d in sorted(st.items(), key=lambda kv: -kv[1]["len"])[:8]:
        print(f"  {n:18}{d['len']:8.1f} mm{d['vias']:4} vias")

    print("\nEstimated stray capacitance on the crystal nets "
          "(~0.1 pF/mm of trace, ~0.5 pF per via):")
    for n in ("OSC_IN", "OSC_OUT"):
        d = st.get(n)
        if d:
            c = d["len"] * 0.1 + d["vias"] * 0.5
            over = c > design.Y1_STRAY_PF
            if over:
                warn += 1
            print(f"  {n:8} ~{c:.1f} pF   (budget: design.Y1_STRAY_PF = "
                  f"{design.Y1_STRAY_PF} pF)" + ("  <-- OVER BUDGET" if over else ""))
        else:
            print(f"  {n:8} (not routed)")

    print(f"\n{warn} item(s) over their stated limit")
    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
