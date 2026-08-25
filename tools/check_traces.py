#!/usr/bin/env python3
"""
Signal-integrity review of the routed copper: length, layer changes, and pair matching.

Three questions this answers that DRC does not:

  * Is any timing-critical net absurdly long? SPI to an IMU, the crystal, the USB pair.
  * Do the USB D+/D- lengths match? A mismatch skews the differential pair. USB 2.0 full
    speed is forgiving, but the number should be known rather than assumed.
  * How many vias does a fast net pass through? Each is an impedance discontinuity and a
    stub.

Nothing here is a hard pass/fail - a 6-layer board at 45 mm cannot have a genuinely long
trace. The point is to SEE the numbers before committing money, and to catch the one net
that got routed the long way round.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, design

BOARD = "NAVCORE-SoOP.kicad_pcb"
TOMM = lambda v: v / 1e6

# LIMITS ARE DERIVED, NOT INVENTED.
#
# A first version of this file used round numbers and flagged six nets. Every one
# dissolved under analysis, which is the worst thing a checker can do - it teaches you to
# ignore it. Signals in FR4 travel at about 150 mm/ns, and a trace only matters when its
# delay approaches a sixth of the signal's rise time, or when its capacitance approaches
# the bus limit. The numbers below come from that, per net class:
#
#   USB 2.0 FS (12 Mbps, 83,300 ps/bit) - 40 mm of skew is still under 0.3% of a bit.
#   I2C 400 kHz - capacitance-limited at 400 pF; a trace is ~0.1 pF/mm, so ~1000 mm.
#   SWD ~4 MHz, rise ~5 ns - 125 mm before delay reaches a sixth of the edge.
#   SPI 24 MHz, edge ~2 ns - 50 mm on the same basis.
#   CRYSTAL - the real one. The oscillator loop is high impedance, so stray capacitance
#             shifts the load the crystal sees. Budget is design.Y1_STRAY_PF.
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
    """True if every pad on `net` belongs to a do-not-populate part.

    Same predicate preflight.py uses to split unrouted nets: a net whose every pad is
    on a DNP part has no component touching it, so no copper is not a fault.
    """
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
            # This used to `continue` WITHOUT incrementing warn, so a critical net that
            # had vanished from the board entirely read as "within limits" - the most
            # alarming result this file can produce was its quietest. A net with no
            # copper is a failure unless every pad on it belongs to a DNP part, in
            # which case no component touches it and it cannot stop the board working.
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

    # This block used to COMPUTE the stray capacitance, PRINT it beside the budget, and
    # never compare the two - while preflight.py reported the result as "lengths, skew
    # and crystal stray capacitance within limits". No comparison existed anywhere in
    # the repo. It matters: Y1_STRAY_PF feeds the C15/C16 value derivation in design.py,
    # and a crystal whose load capacitance is wrong is a board that does not boot.
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
    # This was `return 0`, unconditionally, so the file could not fail and the gate lived
    # in preflight.py as a scrape of the line above. The count is the answer.
    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
