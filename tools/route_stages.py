#!/usr/bin/env python3
"""
Staged autorouter: route one functional group at a time, verify DRC after each,
and roll the stage back if it made things worse.

The single-pass router failed because it had no rip-up-and-retry - it committed copper
greedily and later nets had nowhere legal to go, leaving ~190 shorts. Staging fixes that
differently: each stage is checked in isolation against real DRC, and a stage that
introduces errors is discarded rather than left on the board. Progress is monotonic - the
board is never worse after a stage than before it.

Order matters: the nets where layout affects function go first, while there is still
free copper (crystal, IMU SPI, SDMMC, USB), and the tolerant ones go last.

Usage:
  python3 tools/route_stages.py              # run all stages
  python3 tools/route_stages.py crystal usb  # run named stages only
  python3 tools/route_stages.py --list
"""
import os, sys, shutil, subprocess, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route

BOARD = "NAVCORE-SoOP.kicad_pcb"
BAK   = "/tmp/navcore_stage_backup.kicad_pcb"

STAGES = [
 ("crystal",  "HSE crystal - shortest possible, guards the clock",
              ["OSC_IN", "OSC_OUT"]),
 ("buck",     "5V buck loop - BUCK_PH is the switch node, worst EMI offender on the board",
              ["BUCK_PH", "BUCK_BOOT", "BUCK_FB", "BUCK_COMP", "BUCK_COMP2",
               "BUCK_EN", "BUCK_SS"]),
 ("boot",     "boot/reset straps",
              ["BOOT0", "NRST"]),
 ("imu1",     "IMU1 on SPI1 - gyro data integrity",
              ["SPI1_SCK", "SPI1_MISO", "SPI1_MOSI", "IMU1_CS"]),
 ("imu2",     "IMU2 on SPI4",
              ["SPI4_SCK", "SPI4_MISO", "SPI4_MOSI", "IMU2_CS"]),
 ("spi3",     "SPI3: optical flow + TLE flash",
              ["SPI3_SCK", "SPI3_MISO", "SPI3_MOSI", "EXT_CS1", "EXT_CS2"]),
 ("sdmmc",    "microSD 4-bit - highest pin count, wants space early",
              ["SD_D0", "SD_D1", "SD_D2", "SD_D3", "SD_CK", "SD_CMD", "SD_CD"]),
 ("usb",      "USB 2.0 data pair",
              ["USB_DP", "USB_DM", "USB_DP_CON", "USB_DM_CON", "CC1", "CC2"]),
 ("motors",   "DShot outputs to the ESC",
              ["M1", "M2", "M3", "M4"]),
 ("i2c",      "I2C1 (ToF + external compass) and I2C2 (baro)",
              ["I2C1_SCL", "I2C1_SDA", "I2C2_SCL", "I2C2_SDA"]),
 ("uarts",    "GPS, companion, RC, rangefinder",
              ["USART2_TX", "USART2_RX", "UART7_TX", "UART7_RX", "PPS_SYNC",
               "UART7_RTS", "USART6_TX", "RC_IN", "UART4_TX", "UART4_RX"]),
 ("can",      "CAN1 + transceiver",
              ["CAN1_RX", "CAN1_TX", "CAN1_SILENT", "CANH", "CANL"]),
 ("analog",   "battery sense, ESC current, SoOP ADC breakout",
              ["BATT_V_DIV", "ESC_CUR", "SOOP_I_ADC", "SOOP_Q_ADC"]),
 ("misc",     "LEDs, buzzer, WS2812, ToF control, ESC telemetry, SWD",
              ["LED0", "LED0_K", "LED1", "LED1_K", "BUZZER", "WS2812",
               "TOF_XSHUT", "TOF_INT", "ESC_TEL", "FLOW_VREG", "FLOW_MOTION",
               "SWDIO", "SWCLK", "PWM5", "PWM6", "USART1_TX", "USART1_RX"]),
 ("rails",    "secondary supply rails not carried by a plane",
              ["+5V", "+3V3A", "VDDA", "VBAT", "VBUS", "VCAP1", "VCAP2"]),
]


def drc_errors():
    """Non-unconnected DRC errors, and unconnected count."""
    subprocess.run(["kicad-cli", "pcb", "drc", "--output", "/tmp/stage_drc.rpt",
                    "--severity-error", BOARD],
                   capture_output=True, text=True, timeout=300)
    rpt = open("/tmp/stage_drc.rpt").read()
    classes = re.findall(r'^\[([a-z_]+)\]', rpt, re.M)
    hard = [c for c in classes if c != "unconnected_items"]
    unconn = sum(1 for c in classes if c == "unconnected_items")
    return len(hard), unconn, hard


def route_stage(names):
    """Route only the given nets on the current board. Returns (routed, failed)."""
    board = pcbnew.LoadBoard(BOARD)
    board.BuildConnectivity()
    route.set_rules(board)
    r = route.Router(board)
    pads = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNet()
            if not net: continue
            nn = net.GetNetname()
            if nn not in names: continue
            p = pad.GetPosition()
            pads.setdefault(nn, []).append((route.TOMM(p.x), route.TOMM(p.y), net, pad))
    # Skip pad pairs that are ALREADY electrically connected - otherwise a second pass
    # happily lays a duplicate track over copper that is already there.
    # Cache each pad's connected set once per stage. Calling GetConnectedPads() per
    # MST edge turned a 30-second stage into a 15-minute one.
    # Which pads are ALREADY connected? Without this, a repeat pass re-routes pairs
    # that already have copper, laying redundant track while the unconnected count
    # sits still - which is exactly what an earlier pass did for 12 straight stages.
    #
    # GetConnectedPads() returns nothing in this build, and pcbnew hands back a fresh
    # Python wrapper per call so id() is not a stable key. GetConnectedTracks() does
    # work, so: union-find over pads that share a track, keyed by UUID.
    # Which pads already have copper joining them?
    #
    # pcbnew's own connectivity was no help: GetConnectedPads() returns nothing in this
    # build, GetConnectedTracks() does not give a shared cluster, and pcbnew hands back
    # a fresh Python wrapper per call so id() is never a stable key. So compute it
    # geometrically - union track endpoints, then attach pads whose copper covers one.
    # Without this a repeat pass re-routes already-joined pairs, laying redundant track
    # while the unconnected count sits still.
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb

    Q = lambda v: round(v / 1000.0)          # quantise nm -> um
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            union(("V", Q(p.x), Q(p.y)), ("N", Q(p.x), Q(p.y)))
        else:
            a, c = t.GetStart(), t.GetEnd()
            lay = t.GetLayer()
            union(("N", Q(a.x), Q(a.y)), ("N", Q(c.x), Q(c.y)))

    # attach pads: any track/via endpoint inside the pad's bounding box joins it
    # Bucket the track endpoints spatially. Testing every pad against every node was
    # ~10 million comparisons per stage once the board carried 11k track segments -
    # which is why a second routing pass appeared to hang while the first took 70 s.
    BK = 2000          # bucket size, same micron units as Q()
    grid = {}
    for k in list(parent):
        if k[0] not in ("N", "V"): continue
        grid.setdefault((k[1] // BK, k[2] // BK), []).append(k)

    padkey = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if not (pad.GetNet() and pad.GetNet().GetNetCode()): continue
            k = ("P", pad.m_Uuid.AsString()); find(k)
            padkey[pad.m_Uuid.AsString()] = k
            bb = pad.GetBoundingBox()
            x0, y0 = Q(bb.GetLeft()), Q(bb.GetTop())
            x1, y1 = Q(bb.GetRight()), Q(bb.GetBottom())
            for bi in range(x0 // BK, x1 // BK + 1):
                for bj in range(y0 // BK, y1 // BK + 1):
                    for n in grid.get((bi, bj), ()):
                        if x0 <= n[1] <= x1 and y0 <= n[2] <= y1:
                            union(k, n)

    def connected(pa, pb):
        ka = padkey.get(pa.m_Uuid.AsString()); kb = padkey.get(pb.m_Uuid.AsString())
        if not ka or not kb: return False
        return find(ka) == find(kb)

    done = fail = 0
    for nn in sorted(pads, key=lambda n: route._span(pads[n]) if len(pads[n]) > 1 else 0):
        pts = pads[nn]
        if len(pts) < 2: continue
        net = pts[0][2]; code = net.GetNetCode()
        for a, b in route._mst(pts):
            if len(a) > 3 and len(b) > 3 and connected(a[3], b[3]):
                continue
            path = r.route(code, (a[0], a[1]), (b[0], b[1]))
            if path:
                r.commit(code, net, path); done += 1
            else:
                fail += 1
    route.fill(board)
    board.Save(BOARD)
    return done, fail


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--list" in sys.argv:
        for n, d, nets in STAGES:
            print(f"  {n:<9} {len(nets):>2} nets   {d}")
        return
    todo = [s for s in STAGES if not args or s[0] in args]

    base_hard, base_unconn, _ = drc_errors()
    print(f"baseline: {base_hard} hard DRC errors, {base_unconn} unconnected\n")
    print(f"{'stage':<9} {'nets':>4} {'routed':>7} {'failed':>7} {'errors':>7} "
          f"{'unconn':>10}  verdict")
    print("-" * 78)

    kept = dropped = 0
    for name, desc, nets in todo:
        shutil.copy(BOARD, BAK)
        t0 = time.time()
        try:
            done, fail = route_stage(set(nets))
        except Exception as e:
            shutil.copy(BAK, BOARD)
            print(f"{name:<9} {len(nets):>4} {'-':>7} {'-':>7} {'-':>7} {'-':>7}  ERROR {e}")
            continue
        hard, unconn, classes = drc_errors()
        # Accept on "no NEW DRC errors" alone. Requiring unconnected to fall was wrong:
        # a track crossing the GND pour can orphan a couple of pour-connected pads, so
        # a stage that routed 4/4 cleanly could still show unconnected unchanged and be
        # thrown away. Errors are the invariant; unconnected is reported, not gated.
        ok = hard <= base_hard and done > 0
        d_un = unconn - base_unconn
        if ok:
            base_hard, base_unconn = hard, unconn; kept += 1
            verdict = f"kept ({time.time()-t0:.0f}s)"
        else:
            shutil.copy(BAK, BOARD); dropped += 1
            verdict = (f"ROLLED BACK - +{hard-base_hard} errors" if hard > base_hard
                       else "ROLLED BACK - nothing routed")
        print(f"{name:<9} {len(nets):>4} {done:>7} {fail:>7} {hard:>7} "
              f"{unconn:>6}{d_un:+4d}  {verdict}")

    print("-" * 78)
    hard, unconn, classes = drc_errors()
    print(f"final: {hard} hard DRC errors, {unconn} unconnected  "
          f"({kept} stages kept, {dropped} rolled back)")


if __name__ == "__main__":
    main()
