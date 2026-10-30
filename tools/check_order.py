#!/usr/bin/env python3
"""Ordering and documentation checks: purchases, links, modules, payload, bench and docs.

Usage:  python3 tools/check_order.py CHECK [options]

Checks:
  purchase           Assert every interface between parts that are bought SEPARATELY.
  links              Buying links: recoverability offline, liveness online.
  modules            Assert design.MODULES against the real board.
  module_wiring      Can each module be plugged in without modifying another module's cable?
  payload            Assert that the payload provisions design.PAYLOAD claims are actually still spare.
  bench_bounds       Every "measure it at the bench" item, answered two ways: closed, or bounded.
  rf                 Gate ready-to-FLY on the T3b RF self-interference measurements.
  doc_figures        A retired figure may not appear in a live document unless the text says it is retired.

Stock, the BOM/CPL variants and the order bundle are kicad-tools' fab.py.
"""
import argparse, csv, glob, json, math, os, pathlib, re, subprocess, sys
import design, readiness

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BOARD = (sys.argv[sys.argv.index("--board") + 1] if "--board" in sys.argv
         else os.path.join(REPO, "NAVCORE-SoOP.kicad_pcb"))

EXEMPT = ('docs/HISTORY.md',)


#purchase

"""Assert every interface between parts that are bought SEPARATELY."""

fails, assumed = [], []


def purchase_check(ok, name, detail, src=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:38} {detail}")
    if src:
        print(f"        {src}")
        if src.lstrip().startswith("[A]"):
            assumed.append(name)
    if not ok:
        fails.append(name)


def run_purchase():
    M, P, F, S = design.MOTOR, design.PROP, design.FRAME, design.SKID
    B, PC, O = design.BATT, design.POWER_CONN, design.OFFBOARD

    print("=== the rotating parts ===")
    purchase_check(M["shaft_thread"] == P["mount"], "motor shaft <-> prop mount",
          f"motor is {M['shaft_thread']}, prop mount is {P['mount']}, bore "
          f"{P['bore_mm']:.1f} mm", P["src"])
    adj = F["wb"] / (2 ** 0.5)
    purchase_check(adj > P["dia_mm"], "prop <-> frame",
          f"adjacent motors {adj:.1f} mm, prop {P['dia_mm']:.1f} mm -> "
          f"{adj - P['dia_mm']:+.1f} mm gap", F["src"].split(";")[0])
    #numeric and referential, not substring and not a literal
    purchase_check(design.MOTOR_JOINT["pitch_mm"] in F["motor_patterns_mm"],
          "motor bolts <-> frame arm",
          f"motor needs {design.MOTOR_JOINT['pitch_mm']:.0f} x "
          f"{design.MOTOR_JOINT['pitch_mm']:.0f} mm; the arm offers "
          f"{design.fmt_pattern(F['motor_patterns_mm'])} mm",
          design.MOTOR_JOINT["src"])
    purchase_check(abs(S["hole_pitch"] - design.MOTOR_JOINT["pitch_mm"]) < 1e-6,
          "skid <-> MOTOR pattern",
          f"skid is built to {S['hole_pitch']:.0f} x {S['hole_pitch']:.0f} mm and the "
          f"motor IS {design.MOTOR_JOINT['pitch_mm']:.0f} x "
          f"{design.MOTOR_JOINT['pitch_mm']:.0f} mm - this compares them, where it used "
          f"to compare the skid to the literal 19.0", S["src"])

    print("\n=== power ===")
    purchase_check(PC["adapter_needed"], "battery plug <-> everything else",
          f"pack is {PC['pack']}, airframe is {PC['airframe']} -> ADAPTER REQUIRED. "
          f"Without it nothing connects on build day", PC["src"])
    purchase_check(3 <= B["cells"] <= 6, "battery <-> ESC chemistry",
          f"{B['cells']}S within the ESC's 3-6S input range", B["src"])

    print("\n=== connectors, traced to the netlist ===")
    gps = O["gps"]
    expect = ["5V", "USART2_TX", "USART2_RX", "I2C1_SCL", "I2C1_SDA", "GND"]
    purchase_check(gps["pinout"] == expect, "GPS cable <-> J3",
          f"{' / '.join(gps['pinout'])} - the standard ArduPilot order, so a stock cable "
          f"mates pin-for-pin", gps["src"])
    esc = O["esc"]
    purchase_check(True, "ESC cable <-> J2",
          f"{esc['conn']} - order matches SpeedyBee's documented one, but BUZZ THE CABLE "
          f"before VBAT. Not desk-verifiable", esc["src"])

    print("\n=== the sensors, and the variant traps ===")
    rd = O["rangefinder_down"]
    purchase_check(rd["variant"] == "I2C", "TFS20-L VARIANT",
          f"must be the {rd['variant']} part at 0x{rd['addr']:02X} on {rd['lands_on']}. "
          f"{rd['wrong_variant_note']}", rd["src"])
    purchase_check(rd["vcc"] == "3.3 V", "TFS20-L supply",
          f"module is {rd['vcc']} and {rd['lands_on']} pin 1 is 5 V -> inline LDO "
          f"unless the module "
          f"regulates on board", rd["src"])
    ru = O["rangefinder_up"]
    purchase_check(not design.POPULATE_BLIND_SENSORS, "upward VL53L1X address",
          f"0x{ru['addr']:02X} is free ONLY because {ru['free_because']}", ru["src"])
    rx = O["rx"]
    purchase_check(rx.get("mcu") == "ESP", "ELRS RX <-> laptop ground station",
          f"receiver MUST be {rx.get('mcu')}-based, firmware >= {rx.get('min_fw')}. "
          f"An STM32-based ELRS receiver CANNOT carry MAVLink, so there would be no "
          f"telemetry link to a laptop and no fix in software", rx["src"])
    purchase_check(True, "ELRS RX <-> J5", rx["note"], rx["src"])

    bz = O["buzzer"]
    purchase_check(bz["must_be"] == "passive", "buzzer TYPE",
          f"must be PASSIVE. {bz['drive']} is a timer channel - {bz['note']}", bz["src"])
    led = O["led"]
    purchase_check(led["volts"] == 5, "LED strip VOLTAGE",
          f"must be {led['volts']} V WS2812B - {led['note']}", led["src"])

    L = O["lidar"]
    ear = dict(design.PAYLOAD.get("serial_earmarked", []))
    purchase_check(2 in ear, "360 lidar <-> UART budget",
          f"{L['lands_on']} - {L['wires']}. SERIAL2 is earmarked for it in "
          f"design.PAYLOAD, so a payload cannot also claim it", L["src"])
    #light rating is conditional on where it flies, not an absolute floor
    lo, hi = L["indoor_lux"]
    margin = L["klux"] * 1000 / hi
    purchase_check(L["klux"] >= 60 or L.get("indoor_only"), "360 lidar <-> AMBIENT LIGHT",
          f"{L['klux']} klux, declared INDOOR ONLY. Room light is {lo}-{hi} lux, so that "
          f"is {margin:.0f}x margin. DO NOT FLY IT OUTSIDE: full sun is ~100 klux and a "
          f"lidar that hallucinates is worse than none - AC_Avoid brakes for nothing. "
          f"Outdoors, swap to {L['outdoor_swap']}"
          if L.get("indoor_only") else
          f"{L['klux']} klux, clears the 60 klux outdoor floor", L["src"])
    purchase_check(bool(L.get("buying_check")), "360 lidar <-> THE LISTING",
          L.get("buying_check", ""), L["src"])

    print()
    if assumed:
        print(f"{len(assumed)} interface(s) still rest on an ASSUMED source - confirm on "
              f"the listing before ordering:")
        for a in assumed:
            print(f"   - {a}")
        print()
    if fails:
        print(f"FAIL - {len(fails)} interface(s) do not mate: {', '.join(fails)}")
        return 1
    print("every buy-to-buy interface asserted")
    return 0


#links

"""Buying links: recoverability offline, liveness online."""

DOCS = ("docs/BUYING.md", "docs/SENSORS.md", "README.md",
        "docs/HARDWARE.md", "docs/BENCHMARK.md")
PARTS = "docs/PARTS.csv"

GEO_GATED = ("aliexpress.us", "de.aliexpress.")
LEGACY_FORM = re.compile(r"aliexpress\.com/i/\d+")
URL_RE = re.compile(r"https?://[^\s\)\]\"'>,|]+")

#sites that serve a 403 to anything without a browser fingerprint
BOT_BLOCKED = ("arducam.com", "ebay.com", "mdpi.com")


def urls_in(path):
    try:
        s = open(path).read()
    except FileNotFoundError:
        return []
    return [(m.group(0).rstrip(".,;>"), s[:m.start()].count("\n") + 1)
            for m in URL_RE.finditer(s)]


def run_links():
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", action="store_true", help="also test liveness over HTTP")
    a = ap.parse_args()
    fails, warns = [], []

    #1. fallback terms
    rows = list(csv.DictReader(open(PARTS)))
    fragile = 0
    print("=== fragile links have a fallback search term ===")
    for r in rows:
        link = (r.get("Link") or "").strip()
        fb = (r.get("Search term if the link dies") or "").strip()
        if "aliexpress" in link and ("/item/" in link or "/i/" in link):
            fragile += 1
            if not fb:
                fails.append(f"{r['Item'][:50]}: AliExpress item link with NO fallback "
                             f"search term - when it dies the part is unfindable")
    print(f"  {fragile} AliExpress item link(s); "
          f"{fragile - len([f for f in fails])} with a fallback term")
    if not fails:
        print("  ok   every fragile link is recoverable from its search term")

    #2. geo gating
    print("\n=== no geo-gated or legacy link forms in the live docs ===")
    geo = []
    for path in (PARTS,) + DOCS:
        for u, line in urls_in(path):
            if any(g in u for g in GEO_GATED):
                geo.append(f"{path}:{line} {u}")
            if LEGACY_FORM.search(u):
                geo.append(f"{path}:{line} legacy /i/ form: {u}")
    for g in geo:
        fails.append(f"geo-gated or legacy link: {g}")
    print(f"  ok   none found" if not geo else f"  {len(geo)} found")
    print(f"  note {', '.join(EXEMPT)} exempt - superseded research, not a buying list")

    #3. liveness
    if a.net:
        print("\n=== liveness (--net) ===")
        seen = {}
        for path in (PARTS,) + DOCS:
            for u, line in urls_in(path):
                seen.setdefault(u, f"{path}:{line}")
        ali = [u for u in seen if "aliexpress" in u]
        other = [u for u in seen if "aliexpress" not in u]
        ua = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        for u in sorted(other):
            try:
                out = subprocess.run(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                     "-A", ua, "-L", "--max-time", "25", u],
                    capture_output=True, text=True, timeout=40).stdout.strip()
            except Exception:
                out = "ERR"
            if out.startswith("2"):
                continue
            if any(b in u for b in BOT_BLOCKED) and out == "403":
                print(f"  note 403 (bot-blocked, verified by hand): {u}")
            else:
                fails.append(f"dead link {out}: {u}  ({seen[u]})")
                print(f"  FAIL {out}  {u}")
        print(f"  {len(other)} non-AliExpress link(s) tested")
        print(f"  note {len(ali)} AliExpress link(s) NOT liveness-tested - their pages "
              f"render client-side, so a 200 proves nothing. Recoverability is asserted "
              f"offline instead.")

    print()
    for f in fails:
        print(f"  FAIL {f}")
    for w in warns:
        print(f"  warn {w}")
    print(f"\n{'FAIL' if fails else 'PASS'} - {len(fails)} problem(s), {len(warns)} warning(s)")
    return 1 if fails else 0


#modules

"""Assert design.MODULES against the real board."""

def _money(v):
    """Whole pounds when the price is whole, 2 dp when it is not (LD06 = 13.99)."""
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.2f}"


def footprint_blocks(src: str):
    """Yield each (footprint ...) block by scanning paren depth."""
    for start in (m.start() for m in re.finditer(r'\(footprint "', src)):
        depth, i, n = 0, start, len(src)
        while i < n:
            c = src[i]
            if c == '"':                       #skip string literals wholesale
                i += 1
                while i < n and src[i] != '"':
                    i += 2 if src[i] == '\\' else 1
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    yield src[start:i + 1]
                    break
            i += 1


#refs the docs may name that are not footprints, and why
NOT_FOOTPRINTS = {
    "PF1": "PWR_FLAG schematic symbol - the VBAT one. No footprint, correctly absent",
    "PF8": "PWR_FLAG schematic symbol. No footprint, correctly absent",
    "J7": "a solder-pad GROUP (P71-P74), not a socket - see VERIFICATION.md",
    #Rev B removals
    "J4": "companion/TELEM1 JST-GH - cut 2026-09-09, no legal edge home; UART7 reaches no pad",
    "P42": "UART7 S1 spare pad - removed in the Rev B relayout along with J4; UART7 has no landing",
    "P43": "UART7 S2 spare pad - removed in the Rev B relayout along with J4; UART7 has no landing",
    "P45": "UART7 spare pad - removed in the Rev B relayout along with J4",
    "P51": "RC receiver solder pad - removed in the Rev B relayout; RC now lands on J5 (JST-SH 4P, USART6)",
    "P52": "RC receiver solder pad - removed in the Rev B relayout; RC now lands on J5 (JST-SH 4P, USART6)",
    "P53": "RC receiver solder pad - removed in the Rev B relayout; RC now lands on J5 (JST-SH 4P, USART6)",
    "P54": "RC receiver solder pad - removed in the Rev B relayout; RC now lands on J5 (JST-SH 4P, USART6)",
    "TP11": "Q-channel DC tap probe - removed 2026-09-18 with R30 in the baseband rework; "
            "SOOP_Q_ADC now comes from U14's difference-amplifier output, and PC5 is free",
    "P61": "UART7 spare pad - removed in Rev B relayout",
    "P62": "UART7 spare pad - removed in Rev B relayout",
    "P63": "UART7 spare pad - removed in Rev B relayout",
    "P64": "UART7 spare pad - removed in Rev B relayout",
    #Rev C removals
    "TP1": "SWDIO probe pad - removed in Rev C; J19 carries SWD directly",
    "TP2": "SWCLK probe pad - removed in Rev C; J19 carries SWD directly",
    "TP5": "USART1_TX probe pad - removed in Rev C",
    "TP6": "USART1_RX probe pad - removed in Rev C",
    "TP7": "WS2812 probe pad - removed in Rev C",
    "TP8": "BUZZER probe pad - removed in Rev C",
    "TP20": "SWD GND probe pad - removed in Rev C; J19 carries GND",
    "TP21": "SWD 3V3 probe pad - removed in Rev C; J19 carries +3V3",
    "TP22": "VSERVO probe pad - removed in Rev C",
    "J18": "pyro channel connector - removed in Rev C; recovery is the lander's hardware",
    "J20": "touchdown switch connector - removed in Rev C",
    "Q5": "pyro gate FET - removed in Rev C with J18",
    "D5": "pyro flyback diode - removed in Rev C with J18",
    "F1": "pyro PPTC fuse - removed in Rev C with J18",
    "R54": "pyro gate series resistor - removed in Rev C with J18",
    "R55": "pyro gate pull-down - removed in Rev C with J18",
    "R56": "touchdown pull-up - removed in Rev C with J20",
    "C87": "pyro gate hold-down - removed in Rev C with J18",
    #Rev D: the wire-pad looms became latching ports
    "P41": "companion 5 V pad - Rev D, the companion is on J21 (GH-6P, UART7)",
    "P44": "companion PPS pad - Rev D, dropped with the pads; nothing in the firmware used it",
    "P46": "companion GND pad - Rev D, now J21.6",
    "P71": "SERIAL6 5 V pad - Rev D, removed; UART4 has no landing",
    "P72": "SERIAL6 TX pad - Rev D, removed; UART4 has no landing",
    "P73": "SERIAL6 RX pad - Rev D, removed; UART4 has no landing",
    "P74": "SERIAL6 GND pad - Rev D, removed",
    "PV1": "payload +5 V pad - Rev D, now J22 (GH-3P)",
    "PV2": "payload GND pad - Rev D, now J22",
}


def run_modules():
    root = pathlib.Path(REPO)
    t = (root / "NAVCORE-SoOP.kicad_pcb").read_text()


    #ref -> set of nets its pads connect to
    nets: dict[str, set[str]] = {}
    for blk in footprint_blocks(t):
        r = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if r:
            nets[r.group(1)] = {n for n in re.findall(r'\(net \d+ "([^"]*)"\)', blk) if n}
    if len(nets) < 100:
        print(f"parser sanity check failed: found only {len(nets)} footprints")
        return 1

    fail, warn = [], []
    mods = {k: v for k, v in design.MODULES.items() if isinstance(v, dict)}

    for name, m in mods.items():
        needs = m["needs_board_change"]
        status = m["status"]

        #1. every landing pad must be a real footprint carrying real nets
        for ref in m["lands_on"]:
            if ref not in nets:
                fail.append(f"{name}: lands_on '{ref}' is not a footprint on the board")
            elif not nets[ref]:
                fail.append(f"{name}: '{ref}' exists but NO PAD CARRIES A NET - not an attachment point")

        #2. a module claiming it needs no board change must actually have somewhere to land
        if needs is None and not m["lands_on"] and not m.get("bec"):
            fail.append(f"{name}: claims needs_board_change=None but lands_on is empty")

        #3. status and needs_board_change must agree
        blocked = status in ("blocked", "dnp")
        if blocked and needs is None:
            fail.append(f"{name}: status={status} but no board change is recorded as needed")
        if not blocked and needs is not None:
            fail.append(f"{name}: needs a board change ({needs[:40]}...) but status={status} "
                        f"reads as available - a respin is not 'later', it is another fab run")

    docs = [q for q in (root / "docs").glob("*.md") if q.name != "HISTORY.md"]
    docs.append(root / "README.md")
    ghosts: dict[str, set[str]] = {}
    for q in docs:
        if not q.exists():
            continue
        for mm in re.finditer(r"`(P\d{1,2}|TP\d{1,2}|PV\d|PF\d|J\d|PL\d|PZ\d)`", q.read_text()):
            ref = mm.group(1)
            if ref not in nets and ref not in NOT_FOOTPRINTS:
                ghosts.setdefault(ref, set()).add(q.name)
    for ref, where in sorted(ghosts.items()):
        fail.append(f"docs reference `{ref}` as if it were on the board, but it is not a "
                    f"footprint - in {', '.join(sorted(where))}. If that is deliberate, "
                    f"add it to NOT_FOOTPRINTS with a reason")

    #the rail budget
    rail = design.RAIL_5V
    budget_ma = rail["headroom_a"] * 1000
    on_bec = [(n, m["ma_5v"]) for n, m in mods.items() if m.get("bec")]
    uncounted = [(n, m["ma_5v"]) for n, m in mods.items()
                 if not m["counted"] and m["ma_5v"] and not m.get("bec")]
    total = sum(ma for _, ma in uncounted)

    print(f"\n+5 V rail (U8): {rail['fitted_load_a']:.3f} A fitted (continuous, every FC-rail "
          f"sensor budgeted) against L2's {rail['irms_a']} A Irms -> {budget_ma:.0f} mA headroom")
    if on_bec:
        print(f"  payload modules on +5V_PAYLOAD (U20), not this rail: "
              + ", ".join(f"{n} {ma} mA" for n, ma in sorted(on_bec, key=lambda x: -x[1])))

    #the payload rail, by MISSION
    prail = design.RAIL_5V_PAYLOAD
    th = design.BUCK_THERMAL[next(v for r, _rail, _v, *_x in design.BUCK_RAILS if r == "U20"
                                  for v in [design.COMPONENTS["U20"][2]])]
    vout = next(v for r, _rail, v, *_x in design.BUCK_RAILS if r == "U20")


    def u20_tj(amps, eff=0.85, t_amb=40.0):
        """Worst corner: 85 % efficiency on the datasheet's JEDEC theta_JA."""
        return t_amb + vout * amps * (1 / eff - 1) * th["theta_jedec"]


    print(f"\n+5V_PAYLOAD rail (U20): L5 {prail['irms_a']} A Irms, U20 limit {th['tj_max']:.0f} C")
    for name, prof in design.PAYLOAD_PROFILES.items():
        a = design.PAYLOAD_MISSION_A[name]
        tj = u20_tj(a)
        ok = a <= prail["irms_a"] and tj <= th["tj_max"]
        print(f"  {'ok  ' if ok else 'FAIL'} mission {name:7s} {a:5.2f} A  U20 {tj:4.0f} C worst  "
              f"({', '.join(prof['keys'])})")
        if not ok:
            fail.append(f"payload mission '{name}' draws {a:.2f} A: over L5's {prail['irms_a']} A "
                        f"Irms or U20's {th['tj_max']:.0f} C ({tj:.0f} C)")
    aw = design.PAYLOAD_ALL_WIRED_A
    if aw > prail["irms_a"] or u20_tj(aw) > th["tj_max"]:
        print(f"  warn everything wired at once {aw:.2f} A, U20 {u20_tj(aw):.0f} C - a harness "
              f"rule: fly one mission's payload, not all of them")
        warn.append(f"+5V_PAYLOAD cannot carry every payload connector at once ({aw:.2f} A, "
                    f"U20 {u20_tj(aw):.0f} C); each declared mission fits")
    if uncounted:
        print(f"  modules on the FC rail but NOT in design.LOADS_5V, totalling {total} mA:")
        for n, ma in sorted(uncounted, key=lambda x: -x[1]):
            print(f"    {n:20s} {ma:4d} mA")
            fail.append(f"{n}: {ma} mA on the FC's +5 V rail but neither in design.LOADS_5V nor "
                        f"on +5V_PAYLOAD (bec=True) - U8's thermal bracket does not include it")
    if total > budget_ma:
        print(f"  -> {total} mA exceeds {budget_ma:.0f} mA: these CANNOT all run together.")
        print(f"     Fit them one or two at a time, or give one its own BEC off the battery.")
        print(f"     This is a POWER limit, not an interface limit - every one still attaches.")
        #not a fail
        warn.append(f"+5 V rail cannot carry all optional modules at once "
                    f"({total} mA offered, {budget_ma:.0f} mA available)")

    avail = [n for n, m in mods.items() if m["needs_board_change"] is None]
    blkd = [n for n, m in mods.items() if m["needs_board_change"] is not None]

    print(f"{len(avail)}/{len(mods)} modules attach to the board AS FABRICATED:")
    for n in avail:
        m = mods[n]
        print(f"  ok   {n:20s} {m['status']:7s} GBP{_money(m['gbp']):<7s} {m['conn']}")
    if blkd:
        print(f"\n{len(blkd)} need a second fabrication run:")
        for n in blkd:
            print(f"  --   {n:20s} {mods[n]['status']:7s} {mods[n]['needs_board_change']}")
    for f in fail:
        print(f"\nFAIL {f}")
    for w in warn:
        print(f"\nwarn {w}")
    print(f"\n{'FAIL' if fail else 'PASS'} - {len(fail)} problem(s), {len(warn)} warning(s)")
    return 1 if fail else 0


#module_wiring

"""Can each module be plugged in without modifying another module's cable?"""

SHARED_BY_DESIGN = {
    #J3 carries I2C by standard, not by accident
    ("gps_compass", "J3"): "DS-009 defines the GPS port as carrying I2C; this is standard",
    #the dedicated I2C port J9 is a bus - sharing it is what the port
    ("rangefinder_down", "J9"): "I2C bus - 0x10; the other rangefinder (0x29) is a "
                                  "different-address alternative, never fitted together",
    ("rangefinder_up", "J9"): "I2C bus - 0x29; the other rangefinder (0x10) is a "
                                "different-address alternative, never fitted together",
    #J21 is one UART: the radar or a companion, never both
    ("radar_velocity", "J21"): "one UART - the radar replaces the deferred companion",
    ("flow_globalshutter", "J21"): "one UART - the radar replaces the deferred companion",
}

RAIL_BY_NATURE = {
    "payload_5v_rail": "the rail itself, not a plug - it lands on J17.5 and J11.1, where "
                       "the servo header and the lidar take power FROM it",
}

PAD_BY_NATURE = {
    "soop_tuner": "an analogue I/Q pair, RSSI and PPS - coax and short leads, not a plug",
    "fpv":        "+5V/GND tap for a VTX; it has its own harness",
    "rec_camera": "two wires, +5V and GND",
}

#rails every module is entitled to tap
POWER_NETS = {"+5V", "+3V3", "+3V3A", "GND", "VBAT", "+9V", "VSERVO"}


def is_connector(ref):
    return ref.startswith("J")


def nets_on(ref):
    """Every net that reaches this reference, from design.NETS."""
    out = set()
    for net, pins in design.NETS.items():
        if any(p.split(".")[0] == ref for p in pins):
            out.add(net)
    return out


def carries_signal(ref):
    """Does this landing point carry anything."""
    n = nets_on(ref)
    return bool(n - POWER_NETS)


def run_module_wiring():
    mods = {k: v for k, v in design.MODULES.items() if isinstance(v, dict)}
    #who else lands on each ref
    owners = {}
    for name, m in mods.items():
        if name in RAIL_BY_NATURE:
            continue              #a supply does not contend for a socket
        for ref in m.get("lands_on") or []:
            if not carries_signal(ref):
                continue          #a power tap is shared by definition
            owners.setdefault(ref, []).append(name)

    shared, soldered, ok = [], [], []
    print("=== module wiring ===")
    print(f"{'module':22} {'lands on':22} {'dedicated':10} {'pluggable':10}")
    for name in sorted(mods):
        m = mods[name]
        refs = m.get("lands_on") or []
        if not refs:
            continue
        if name in RAIL_BY_NATURE:
            print(f"  {name:20} {','.join(refs)[:20]:22} {'supply':10} {'n/a':10}")
            continue
        co = sorted({o for r in refs for o in owners.get(r, []) if o != name})
        dedicated = not co or all((name, r) in SHARED_BY_DESIGN for r in refs)
        pluggable = all(is_connector(r) for r in refs)
        exempt = name in PAD_BY_NATURE

        if not dedicated:
            shared.append((name, refs, co))
        if not pluggable and not exempt:
            soldered.append((name, refs))
        if dedicated and (pluggable or exempt):
            ok.append(name)

        print(f"  {name:20} {','.join(refs)[:20]:22} "
              f"{'yes' if dedicated else 'SHARED':10} "
              f"{('yes' if pluggable else ('n/a' if exempt else 'SOLDER')):10}"
              + (f"  <-- shares with {', '.join(co)}" if not dedicated else ""))

    print()
    if shared:
        print("SHARED LANDING POINTS - not a fault where SHARED_BY_DESIGN says otherwise,")
        print("but each one needs a splitter or a Y-lead rather than a plug:")
        for name, refs, co in shared:
            why = next((SHARED_BY_DESIGN[(name, r)] for r in refs
                        if (name, r) in SHARED_BY_DESIGN), None)
            print(f"  {name}: lands on {','.join(refs)}, shared with {', '.join(co)}")
            if why:
                print(f"      {why}")
    if soldered:
        print("\nSOLDER-ONLY LANDING POINTS - real and reachable, but not a plug:")
        for name, refs in soldered:
            print(f"  {name}: {','.join(refs)}")
    for name, why in sorted(RAIL_BY_NATURE.items()):
        if name in mods:
            print(f"  note {name} is a supply, not a landing point - {why}")
    for name, why in sorted(PAD_BY_NATURE.items()):
        if name in mods:
            print(f"  note {name} exempt from the plug test - {why}")

    print(f"\n{len(ok)} module(s) wire cleanly, {len(shared)} need a cable splice, "
          f"{len(soldered)} need soldering")
    return 1 if shared else 0


#payload

"""Assert that the payload provisions design.PAYLOAD claims are actually still spare."""

PARM = os.path.join(REPO, "firmware/NAVCORE_SoOP/defaults.parm")
HWDEF = os.path.join(REPO, "firmware/NAVCORE_SoOP/hwdef.dat")

fails = []


def payload_check(ok, name, detail):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:34} {detail}")
    if not ok:
        fails.append(name)


def run_payload():
    parm = open(PARM).read()
    hwdef = open(HWDEF).read()
    P = design.PAYLOAD

    print("=== free actuator channels ===")
    for name, pin, pad, param in P["pwm"]:
        claimed = re.search(rf'^{param}\s', parm, re.M)
        payload_check(claimed is None, f"{name} ({pin}) at {pad}",
              f"{param} not set - free for a payload" if claimed is None
              else f"CONSUMED: {param} is set in defaults.parm")
        n = re.search(rf'^{re.escape(pin)}\s+\S+\s+\S+\s+PWM\((\d+)\)', hwdef, re.M)
        payload_check(n is not None, f"{name} exists in hwdef",
              f"{pin} is PWM({n.group(1)})" if n else f"{pin} is NOT a PWM output in hwdef")

    print("\n=== free serial links ===")
    for idx, periph, pads, note in P["serial"]:
        claimed = re.search(rf'^SERIAL{idx}_PROTOCOL\s', parm, re.M)
        payload_check(claimed is None, f"SERIAL{idx} ({periph}) at {pads}",
              f"unclaimed - {note}" if claimed is None
              else f"CONSUMED: SERIAL{idx}_PROTOCOL is set")

    for idx, who in P.get("serial_earmarked", []):
        print(f"  note  SERIAL{idx} is EARMARKED{'':16} for the {who}. Unclaimed in "
              f"defaults.parm today, so it passes above - but a payload and that cannot "
              f"both have it")

    print("\n=== declared but NOT reachable - stated so nobody plans around them ===")
    #derived, not trusted
    order = []
    for line in open(HWDEF):
        if line.startswith("SERIAL_ORDER"):
            order = line.split()[1:]
            break
    derived = {}
    for idx, periph in enumerate(order):
        if periph.startswith("OTG"):
            continue                      #USB, no pads by nature
        landed = False
        for suffix in ("_TX", "_RX"):
            for spec in design.NETS.get(periph + suffix, []):
                if not spec.startswith("U1."):
                    landed = True         #something other than the MCU is on it
        if not landed:
            derived[idx] = periph
    declared = dict(P["serial_unrouted"])
    missed = {i: p for i, p in derived.items() if i not in declared}
    phantom = {i: p for i, p in declared.items() if i not in derived}
    payload_check(not missed and not phantom,
          "unrouted serials match the netlist",
          "design.PAYLOAD agrees with the wiring" if not missed and not phantom
          else (f"PAYLOAD['serial_unrouted'] is stale - netlist says also "
                f"{sorted(missed.items())}" if missed else "")
               + (f" declares {sorted(phantom.items())} which IS routed" if phantom else ""))
    for idx, periph in sorted(derived.items()):
        print(f"  note  SERIAL{idx} ({periph}){'':18} in hwdef but routed to NO pad - "
              f"real to the firmware, unreachable with a soldering iron")

    print("\n=== power for a payload ===")
    print(f"  note  5 V pads{'':26} {', '.join(P['power_5v'])}")
    print(f"  note  GND pads{'':26} {', '.join(P['gnd'])}")
    print(f"  note  current{'':27} {P['power_note']}")
    print(f"  note  mass budget{'':23} {P['mass_budget_g']:.0f} g at 40% hover throttle")

    print()
    if fails:
        print(f"FAIL - {len(fails)} payload provision(s) no longer available: "
              f"{', '.join(fails)}")
        return 1
    print(f"payload provisions intact: {len(P['pwm'])} free PWM channel(s), "
          f"{len(P['serial'])} free routed UART, {P['mass_budget_g']:.0f} g budget")
    return 0


#bench_bounds

"""Every "measure it at the bench" item, answered two ways: closed, or bounded.

Run: python3 tools/check_order.py bench_bounds
"""

HEAD_R = 2.75          #M3 cap head, 5.5 mm OD - metal, the hard constraint
FLANGE_R = design.MOUNTING["grommet_d"] / 2.0      #assumed silicone flange, 6.0 mm OD
FLANGE_R_WIDE = 4.0    #8.0 mm OD - the widest silicone M3 grommet worth buying


def thermal_verdict():
    """check_circuit.py thermal is the authority on the junction bounds."""
    out = subprocess.run([sys.executable, "tools/check_circuit.py", "thermal"], cwd=REPO,
                         capture_output=True, text=True).stdout
    got = {}
    for m in re.finditer(r"^  (ok|warn|FAIL)\s+(U\d+) junction temperature\s+(.*)$",
                         out, re.M):
        got[m.group(2)] = (m.group(1), m.group(3).strip())
    return got


def mounting_bound():
    """Nearest copper to each mounting hole."""
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

    #closed by evidence

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
               f"check_board.py placement already classes as an assembly note"),
        evidence=("the flange and the M3 head are CONCENTRIC, so the flange is always the "
                  "wider of the two and the metal is always the narrower. Growing the "
                  "flange adds only silicone-on-mask; it cannot make the metal part reach "
                  "copper it does not already clear. Z is swept 2.0-4.5 mm by check_mech.py fit, "
                  "which requires every PURCHASE to cover the whole range - so the design "
                  "is invariant over the grommet, which is stronger than measuring one"),
        residual="caliper the received grommet only to choose the standoff set - an "
                 "assembly convenience, not a prerequisite"))

    rows.append(dict(
        id="bench.escshunt", cls="CLOSED",
        bound=("the ESC's own manual publishes Scale=400 -> 40.0 mV/A -> 25.0 A/V, and "
               "defaults.parm ships exactly that"),
        evidence=("check_mech.py build 'BATT_AMP_PERVLT matches the ESC' now compares the "
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
        evidence=("design.ESC now DECLARES pin_order from the manual, and check_mech.py build "
                  "'J2 pin order matches the ESC manual' holds the netlist against it. "
                  "Nothing checked this before: J2 is a passive connector, so DRC, ERC and "
                  "check_circuit.py pin_semantics all pass a transposed one - the symptom is four "
                  "motors on the wrong signals. Mutation-tested: swapping M1/M2 and "
                  "CUR/TEL each fail it"),
        residual="a continuity test on the received cable is still prudent before first "
                 "power; it is not a prerequisite and it cannot change the board"))

    #bound / PARAM
    u8, u9 = th.get("U8"), th.get("U9")
    #the good-copper figure only for U9
    u9_bound = (u9[1].split(" but ")[0] if u9 else "NOT COMPUTED")
    rows.append(dict(
        id="bench.u8", cls="BOUND",
        bound=f"check_circuit.py thermal: {u8[1] if u8 else 'NOT COMPUTED'}",
        evidence=("the worst-case corner would have to pass 125 C; it is 38 C below it, and "
                  "U8 was already swapped to the LMR33630A RNX for exactly this - the swap "
                  "is ON the board, so no reading can un-fit it"),
        residual="a thermocouple at T3a confirms the bound (kept as a flight gate)"))
    rows.append(dict(
        id="bench.u9", cls="BOUND",
        bound=f"check_circuit.py thermal: {u9_bound}",
        evidence=("the good-copper corner would have to pass 125 C; it is 43 C below it, on "
                  "a board measured at 7443 mm2 of GND plane and 5 "
                  "vias on the output pad. Even the minimal-copper corner stays at 104 C"),
        residual="T3a sets the board-to-junction offset once; U19 then logs it every flight"))
    u20 = th.get("U20")
    rows.append(dict(
        id="bench.u20", cls="BOUND",
        bound=f"check_circuit.py thermal: {u20[1] if u20 else 'NOT COMPUTED'}",
        evidence=("the worst payload mission at 40 C ambient on the part's single theta_JA "
                  "stays under 125 C; U20 is the same LMR33630A RNX swapped in for U8, and "
                  "the payload profiles that load it are budgeted per mission"),
        residual="a thermocouple at T3a under the worst mission's load confirms it"))
    rows.append(dict(
        id="bench.flowyaw", cls="PARAM",
        bound=("FLOW_ORIENT_YAW selects one of four cardinal values; flow arrives as MAVLink "
               "from the off-board companion, so the board cannot encode it"),
        evidence=("nothing on the board. The sign is a constant in defaults.parm"),
        residual="set the sign from CAD, then confirm it in position hold"))

    #module
    #the requirement arithmetic, so the bench knows what it is looking for
    cn0_req = 62.0
    req_2db = cn0_req - 174.0 + 2.0
    req_4db = cn0_req - 174.0 + 4.0
    rows.append(dict(
        id="bench.rf", cls="MODULE",
        bound=(f"the requirement is C/N0 {cn0_req:.0f} dB-Hz, so Pr must reach "
               f"{req_2db:.0f} dBm at 2 dB system NF ({req_4db:.0f} dBm at 4 dB). The gain "
               f"and noise figure that meet it come from the BOUGHT Tallysman HC610 "
               f"(a pre-filter then a 28 dB LNA, NF 2.0 dB, inside the antenna, where NF is "
               f"set before cable loss). The board contributes an MMCX entry (J12); the "
               f"antenna's 15 mA comes from the on-board feed (U24, monitored by U25)"),
        evidence=("a desense result is fixed by antenna separation, ferrites and shielding - "
                  "all listed mitigations - because the filter sits AT THE ANTENNA and rejects "
                  "the board's own switchers before the tuner sees them. The one board-side "
                  "lever, an on-board LNA+SAW, was DELETED in favour of the bought module "
                  "(design.py U15/U16/FL1), so putting it back would be a respin - and it is "
                  "the wrong move: an LNA belongs before the cable, not after it. NOTE this "
                  "is the ONE item with no analytic bound: whether the link closes depends "
                  "on real sky and real desense, so it stays a flight gate"),
        residual="T3b: four steps that each name their own culprit"))
    rows.append(dict(
        id="fly.rfbench", cls="DATA",
        bound=("check_order.py rf records the four T3b steps and compares them to baseline; it "
               "asserts nothing about the board"),
        evidence="nothing on the board - it gates FLYING, not ordering",
        residual="the same bench session as bench.rf"))
    rows.append(dict(
        id="build.firmware", cls="PARAM",
        bound=("AP_SoOP builds and links into the NAVCORE_SoOP firmware; the pins it uses "
               "(PC4/PA4 capture, I2C2 tuner, PC0/PC1 moved to ADC3) are gated against the "
               "netlist by the hwdef check"),
        evidence=("tuner lock, the 1 MSPS capture rate and the CPU share are properties of "
                  "the code on this silicon. ST's pin data confirms every ADC channel used, "
                  "so what the bench finds is fixed in firmware, not copper"),
        residual="runbook T3b step 2"))
    rows.append(dict(
        id="bench.cameraflow", cls="MODULE",
        bound=("flow quality is a property of the off-board companion camera and the ground; "
               "J4 (its connector) was cut from this board"),
        evidence=("nothing on the board. Poor flow selects a different camera. Kept as a "
                  "flight gate because the runbook stops at GPS Loiter"),
        residual="record a flight, then replay it through the harness"))

    return rows


def run_bench_bounds():
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

    #reconciliation: the live set must be the manifest's bench/FLY set
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


#rf

"""Gate ready-to-FLY on the T3b RF self-interference measurements."""

SPEC = design.RF_BENCH
REPO = pathlib.Path(__file__).parent.parent
RESULTS = REPO / SPEC["results"]


def template() -> str:
    return json.dumps(
        {"_note": "T3b per the runbook (docs/navcore-runbook.tex). Record steps IN ORDER - the ordering is the "
                  "experiment: each degradation names its own culprit.",
         "_band_mhz": list(SPEC["band_mhz"]),
         **{name: {f: None for f in SPEC["fields"]} | {"_what": what, "_isolates": why}
            for name, what, why in SPEC["steps"]}},
        indent=2)


def run_rf() -> int:
    if "--template" in sys.argv:
        print(template())
        return 0

    if not RESULTS.exists():
        print(f"NOT READY TO FLY - {SPEC['results']} does not exist.\n")
        print("The four T3b measurements have not been made. This is expected before the")
        print("hardware arrives, and is NOT an order blocker - preflight.py governs that.\n")
        for i, (name, what, why) in enumerate(SPEC["steps"], 1):
            print(f"  {i}. {name:16s} {what}")
            print(f"     {'':16s} -> {why}")
        print(f"\nStart with:  python3 tools/check_order.py rf --template "
              f"> {SPEC['results']}")
        print("Step 1 needs no aircraft - do it the week the SDR parts arrive.")
        return 1

    data = json.loads(RESULTS.read_text())
    problems, baseline, prev = [], None, None

    for name, _what, _why in SPEC["steps"]:
        step = data.get(name)
        if not isinstance(step, dict):
            problems.append(f"{name}: missing from {SPEC['results']}")
            continue
        missing = [f for f in SPEC["fields"] if step.get(f) is None]
        if missing:
            problems.append(f"{name}: not measured - {', '.join(missing)}")
            continue

        bursts = step["bursts_per_min"]
        if name == "baseline":
            baseline = prev = bursts
            prev = (name, bursts)
            if not baseline:
                problems.append("baseline: 0 bursts/min - the receive chain does not work "
                                "at all, and nothing downstream of this is meaningful")
            continue
        if baseline:
            frac = bursts / baseline
            floor = SPEC["min_fraction_of_baseline"]
            verdict = "ok  " if frac >= floor else "FAIL"
            print(f"  {verdict} {name:16s} {bursts:6.1f}/min = {frac:5.1%} of baseline "
                  f"(floor {floor:.0%})")
            if frac < floor:
                problems.append(
                    f"{name}: {frac:.0%} of baseline, below the {floor:.0%} floor. "
                    f"Culprit: {dict((s[0], s[2]) for s in SPEC['steps'])[name]}")

            if prev is not None and bursts > prev[1] * 1.1:
                problems.append(
                    f"{name}: {bursts:.1f}/min is HIGHER than {prev[0]} at {prev[1]:.1f} - "
                    f"impossible if the run was cumulative. Re-measure both in one "
                    f"session, same position, same sky; do not attribute a culprit "
                    f"from this data")
            prev = (name, bursts)

    if problems:
        print("\nNOT READY TO FLY:")
        for p in problems:
            print(f"  - {p}")
        if any("below the" in p for p in problems):
            print("\nMitigations, cheapest first:")
            for m in SPEC["mitigations"]:
                print(f"  - {m}")
        return 1

    print(f"\nRF bench PASS - all {len(SPEC['steps'])} T3b steps measured, each within "
          f"{SPEC['min_fraction_of_baseline']:.0%} of baseline")
    return 0


#doc_figures

"""A retired figure may not appear in a live document unless the text says it is retired.

Usage:  python3 tools/check_order.py doc_figures [--explain]
"""

SCAN = ["README.md", "docs/*.md", "docs/*.tex", "fab/*.md", "tools/README.md", "docs/PARTS.csv",
        "firmware/NAVCORE_SoOP/Readme.md"]

RETIRED = [
    (r"2\\?,m/s drag in 5 to 19", "the 2 m/s drag time before check_soop.py nav was rerun",
     "19 to 24 minutes without an independent velocity, about two with one (check_soop.py nav)"),
    (r"1\.3--2\.4\\?,km", "how far a caught drag had moved the GPS, before the rerun",
     "1.4-2.9 km (check_soop.py nav)"),
    (r"\b52\.7\b", "the BATT_AMP_PERVLT value from a different SpeedyBee stack",
     "the firmware ships 25.0 - 1000 / the ESC's 40 mV/A, and check_mech.py build verifies it"),
    (r"\b89\.2\b", "a theta_JA that is NOT in SLVSD26",
     "SLVSD26 5.4 gives 118.6 C/W (JEDEC) and 57.2 C/W (EVM); publish them as a bracket"),
    (r"\b48/48\b", "the LCSC code count when the community mirror still worked",
     "56/56 codes resolve, via JLCPCB's live API (fab.py stock)"),
    (r"\bnofpv\b|\bno-fpv\b", "the -nofpv variant, dropped as a byte-identical copy of the default",
     "there is one build and an -economic variant"),
    (r"NAVCORE-SoOP-fpv\b", "a BOM/CPL variant name retired two revisions ago",
     "there is one build and an -economic variant; the -nofpv variant was dropped as a "
     "byte-identical copy of the default"),
    (r"\b64% routed\b", "the stale routing figure from before the board was finished",
     "the board is fully routed; check_board.py traces and DRC both pass"),
    (r"6\.0\s?mm\s?\"?\s?nominal|nominal\s?6\.0\s?mm|allowance (is|of) 6\.0\s?mm",
     "J3's retired JST-GH class clearance",
     "the derived requirement is 3.6 mm (design.MATING_CLEARANCE['J3']); 5.30 mm clears it"),
    (r"\beighteen\b.*\bpart", "a part count from before the Rev B re-layout", "count it"),
    (r"22\.3\s?mm against 25\s?mm|2\.7\s?mm spare", "the Mark4-era stack clearance",
     "check_mech.py mechanical: the stack against the top plate on 25 mm front standoffs"),
    (r"30\s?mm standoffs for the top plate", "a top-plate standoff the frame does not use over the stack",
     "the top plate rides on 25 mm FRONT standoffs over the stack (33 mm at the rear)"),
    (r"27k\s?/\s?5k1|47k\s?/\s?4k7", "the TPS54331-era feedback dividers (0.8 V reference)",
     "the TPS54202 references 0.596 V: +5V is 37k4/5k1 -> 4.97 V, +9V is 100k/6k8 -> 9.36 V (DNP)"),
    (r"\b9\.03\s?V\b", "the +9V setpoint before the divider was re-derived", "9.36 V, and the rail is DNP"),
    (r"10\.2\s?mm needed", "the FC-to-ESC joint before the stack bolt was derived end to end",
     "fasteners.py: the 30.5 mm stack bolt needs 31.0 mm -> M3x35, with a 15 mm F-F spacer"),
    (r"kit'?s (own )?22 mm|22 mm front standoff|use the kit'?s (own )?standoffs",
     "the kit's top-plate standoffs, before the GH connectors under the board raised the stack",
     "25 mm front and 33 mm rear standoffs, bought (design.TOP_PLATE_MOUNT)"),
    (r"\b12 mm (F-F|female-female|nylon)|\b12\.1 mm\b|\bM3\s?x\s?30\b",
     "the ESC-to-FC spacer and stack bolt before the GH connectors under the board",
     "a 15 mm nylon F-F spacer and M3x35 stack bolts (tools/fasteners.py)"),
    (r"\b43 (of 43 )?gated\b|all 43 gated", "a gate count from one commit ago", "read it off preflight.py; do not type it"),
    (r"\bJ10\b", "a servo connector that was dropped in the Rev B re-layout",
     "the servo lands on TP3/TP4 (PWM5/6) with VSERVO on TP22"),
    (r"70\s?[-–]{1,2}\s?139|\b139\s?(°\s?C|C\b|\\degC)|\b0\.947\s?A|\b947\s?mA|\b653\s?mA",
     "U8's junction bracket and the +5 V budget it was computed from (0.947 A, 653 mA headroom)",
     "design.LOADS_5V derives 0.737 A; check_circuit.py thermal gives 63-117 C; headroom 863 mA - "
     "the old figures counted 281 mA of deleted parts and missed U10"),
    #revision C: figures the Rev C work left behind or introduced
    (r"46\.1\s?(mm|\$|x|×)|x\s?46\.1|\\times\s?46\.1|45\.1\s?[x×]\s?46", "the Rev B board outline",
     "Revision C is 45.1 x 47.3 mm (Edge.Cuts bounding box; check_circuit.py design prints it)"),
    (r"\b14 (DNP|designators|refs)\b", "the Rev B DNP count", "Revision C fits everything but R15, the CAN terminator"),
    (r"3S\s?[–-]{1,2}\s?6S|\b26\.1\s?V", "a 6S input rating the input TVS cannot protect",
     "the board is 5S max: the SMBJ22A stands off 22 V and clamps at 35.5 V under the bucks' 38 V"),
    (r"TPS54332", "a buck part this board never used", "both bucks are LMR33630 (design.BUCK_THERMAL)"),
    (r"USB cannot power", "a claim the board contradicts - D_USB feeds VBUS into +5 V",
     "USB runs the logic through D_USB; the payload rail still needs VBAT"),
    (r"JST-SH 8P Gimbal|8-pin Actuator|J17\.6[`)]* \(`?\+5V", "the 8-pin J17 pinout with +5 V on pin 6",
     "J17 is a 6-pin JST-SH: pin 5 +5V_PAYLOAD, pin 6 GND"),
    (r"5V\s?/\s?(2\.5|3)A payload|3A continuous|5V / 3A Payload", "the payload buck's IC rating quoted as the rail's",
     "L5 limits +5V_PAYLOAD to 1.6 A continuous"),
    (r"bootloader over SWD|no bootloader will not enumerate", "a first-flash procedure that is wrong for an H743",
     "hold BOOT (SW1) through RESET and the ROM DFU enumerates as 0483:df11 with no bootloader; SWD is the fallback"),
    (r"ROTATION\\?_ROLL\\?_180(?!\\?_YAW)|AHRS\\?_ORIENTATION`?\*{0,2} to `?Pitch180",
     "an IMU rotation that reads the board upside down",
     "both IMUs are ROTATION_YAW_270 (gen_hwdef.imu_rotation, forward = the top edge)"),
]

#a retirement marker is a word that says the reader should not act on this value
MARKERS = (
    "retired", "no longer", "used to", "previously", "superseded", "corrected", "stale",
    "deprecated", "obsolete", "instead of", "until", "came from", "was wrong", "wrong",
    "earlier", "old ", "history", "not in ", "does not contain", "no longer exists",
    "not stocked", "two revisions", "originally",
    "this said", "dropped",
)
WINDOW = 3

CLAUSE_BREAK = re.compile(r"(?<=[.;!?])\s|\u2014|\u2013|--")


def retirement_marker(text, rx, anchor):
    """The retirement marker that excuses the first match of `rx` at or after `anchor`."""
    m = next((q for q in re.finditer(rx, text, re.I) if q.start() >= anchor), None)
    if not m:
        return None
    breaks = list(CLAUSE_BREAK.finditer(text))
    before = [q for q in breaks if q.end() <= m.start()]
    after = [q for q in breaks if q.start() >= m.end()]
    start = before[-1].end() if before else 0
    end = after[0].start() if after else len(text)
    candidates = [text[start:end]]
    if len(before) >= 2:
        candidates.append(text[before[-2].end():start].lstrip(" *_>#:-\t"))
    elif start == 0:
        candidates.append(text[:start])
    else:
        candidates.append("")
    if len(after) >= 2:
        candidates.append(text[end:after[1].start()].lstrip(" *_>#:-\t"))
    else:
        candidates.append(text[end:].lstrip(" *_>#:-\t"))
    #the figure's own clause: any marker
    for mk in MARKERS:
        if mk in candidates[0]:
            return mk
    for mk in MARKERS:
        if candidates[1].startswith(mk) or candidates[2].startswith(mk):
            return mk
    return None


def run_doc_figures():
    os.chdir(REPO)
    explain = "--explain" in sys.argv

    files = []
    for pat in SCAN:
        files.extend(sorted(glob.glob(pat)))
    files = [f for f in files if os.path.isfile(f)]
    files = [f for f in files if f not in EXEMPT]

    problems, excused, hits = [], [], 0
    for path in files:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        for i, line in enumerate(lines):
            for rx, what, instead in RETIRED:
                if not re.search(rx, line, re.I):
                    continue
                hits += 1
                lo, hi = max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)
                near = " ".join(lines[lo:hi]).lower()
                anchor = len(" ".join(lines[lo:i])) + (1 if i > lo else 0)
                mark = retirement_marker(near, rx, anchor)
                if mark:
                    excused.append((path, i + 1, what, mark))
                    continue
                problems.append((path, i + 1, line.strip()[:110], what, instead))

    print("=== retired figures in live prose ===")
    print(f"      scanned {len(files)} file(s), {hits} mention(s) of {len(RETIRED)} retired value(s)")

    if explain:
        for path, ln, what, mark in excused:
            print(f"      excused {path}:{ln}  ({what}) because it says \"{mark}\"")

    for path, ln, text, what, instead in problems:
        print(f"  FAIL  {path}:{ln}")
        print(f"        {text}")
        print(f"        {what} is retired: {instead}")

    if problems:
        print(f"\nFAIL - {len(problems)} retired figure(s) presented as current")
        print("     Either write the current value, or say the old one is retired - this check")
        print("     only asks that a reader can tell which they are looking at.")
        return 1

    print(f"      {len(excused)} mention(s) are marked as retired and pass")
    print("\nno retired figure is presented as current")
    return 0


CHECKS = {
    "purchase": run_purchase,
    "links": run_links,
    "modules": run_modules,
    "module_wiring": run_module_wiring,
    "payload": run_payload,
    "bench_bounds": run_bench_bounds,
    "rf": run_rf,
    "doc_figures": run_doc_figures,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CHECKS:
        print(__doc__)
        return 2
    return CHECKS[sys.argv.pop(1)]()


if __name__ == "__main__":
    sys.exit(main())
