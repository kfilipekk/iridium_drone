#!/usr/bin/env python3
"""Signal-integrity review of the routed copper: length, layer changes, and pair matching."""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = "NAVCORE-SoOP.kicad_pcb"
TOMM = lambda v: v / 1e6

# Limits are derived, not INVENTED.
CRITICAL = {
    "OSC_IN":       ("crystal - stray C shifts the load; see Y1_STRAY_PF", 15.0),
    "OSC_OUT":      ("crystal", 15.0),
    "USB_DP":       ("USB 2.0 FS - delay is irrelevant at 12 Mbps", 80.0),
    "USB_DM":       ("USB 2.0 FS", 80.0),
    "SPI1_SCK":     ("IMU1 clock - the primary IMU, 24 MHz", 50.0),
    "SPI1_MISO":    ("IMU1", 50.0),
    "SPI1_MOSI":    ("IMU1", 50.0),
    "SPI4_SCK":     ("IMU2 clock", 50.0),
    "SPI3_SCK":     ("flash + flow sensor clock", 50.0),
    "I2C1_SCL":     ("external I2C - capacitance-limited, not length-limited", 200.0),
    "I2C1_SDA":     ("external I2C", 200.0),
    "SWCLK":        ("SWD ~4 MHz", 125.0),
    "SWDIO":        ("SWD", 125.0),
}
# USB 2.0 full speed tolerates enormous skew. This is recorded so the number is known,
# not because 4 mm would ever matter at 12 Mbps.
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


def _all_dnp(net):
    """True if every pad on `net` belongs to a do-not-populate part."""
    pins = design.NETS.get(net) or []
    if not pins:
        return False
    return all((design.COMPONENTS.get(q.split(".")[0]) or (0, 0, 0, 0, False))[4]
               for q in pins)


def main():
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
        flag = "  <-- OVER" if d["len"] > limit else ""
        if d["len"] > limit:
            warn += 1
        print(f"{n:14}{d['len']:8.1f}{d['vias']:6}  {','.join(sorted(d['layers']))[:22]:22} {why}{flag}")

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
