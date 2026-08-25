#!/usr/bin/env python3
"""Strip routing, add keepouts, export a Specctra DSN for freerouting.

Each stage runs in its OWN PROCESS, re-invoking this file. That is not tidiness, it
is required: stripping every track, adding rule-area zones, and ExportSpecctraDSN
each work fine alone, but doing all three in one interpreter segfaults. Splitting
them was the only arrangement that survived.

Zone building is inline rather than in a helper too - called from inside a function,
z.Outline() returns a bare SwigPyObject with no NewOutline on it.

Usage:  fr_prepare.py <board.kicad_pcb> <out.dsn>
"""
import os, sys, math, shutil, subprocess

ME = os.path.abspath(__file__)
sys.path.insert(0, os.path.dirname(ME))

def _add_small_via(dsn):
    """Offer freerouting a 0.45 mm via as well as the default one.

    KiCad exports a single padstack from the board's default via size, so freerouting
    was given only the 0.60 mm one. That does not fit between 0.5 mm pitch LQFP pads,
    which is why its fanout stalled and SPI1/SPI4/VCAP2 never reached the SES at all.
    0.45/0.20 is JLCPCB's floor for 4+ layers at standard price.

    The padstack name encodes the layer span - Via[0-3] on a 4-layer board, Via[0-5]
    on six - so it is matched by pattern rather than by literal name. Hardcoding
    Via[0-3] silently did nothing the moment the board went to 6 layers.
    """
    import re as _re
    txt = open(dsn).read()
    m = _re.search(r'\(padstack "(Via\[[0-9]+-([0-9]+)\]_(\d+):(\d+)_um)"', txt)
    if not m:
        print("::WARNING no via padstack found - small via NOT added")
        return
    big, top = m.group(1), int(m.group(2))
    small = big.replace(f"_{m.group(3)}:{m.group(4)}_", "_450:200_")
    if small in txt:
        return
    layers = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, top)] + ["B.Cu"]
    shapes = "".join(f"      (shape (circle {ln} 450))\n" for ln in layers)
    pad = f'    (padstack "{small}"\n{shapes}      (attach off)\n    )\n'
    anchor = f'    (padstack "{big}"'
    txt = txt.replace(anchor, pad + anchor, 1)
    use = f'(use_via "{big}")'
    if use in txt:
        txt = txt.replace(use, f'(use_via "{big}" "{small}")', 1)
    else:
        print("::WARNING could not find use_via - small via declared but unused")
    open(dsn, "w").write(txt)
    print(f"::added {small} for tight escapes ({len(layers)} layers)")


stage = sys.argv[1] if sys.argv[1].startswith("--stage") else None

if stage is None:
    board, out = sys.argv[1], sys.argv[2]
    tmp = out.replace(".dsn", "-stripped.kicad_pcb")
    shutil.copy(board, tmp)
    for st in ("--stage1", "--stage2", "--stage3"):
        r = subprocess.run([sys.executable, ME, st, tmp, out],
                           capture_output=True, text=True)
        note = [l for l in r.stdout.splitlines() if l.startswith("::")]
        if r.returncode != 0:
            sys.stderr.write(r.stdout + r.stderr)
            sys.exit(f"{st} failed with {r.returncode}")
        for l in note:
            print(l[2:])

    # planes: done on the DSN text, because a board-wide rule area on an inner layer
    # segfaults on save. Left alone freerouting treats In1/In2 as ordinary signal
    # layers and routes hard on them - 325 segments and 995 mm, more than any other
    # layer, through what the plan specifies as a SOLID GND plane. That shreds the
    # pour into islands, which is what strands the power pads, and it removes the
    # return path under USB, SDMMC, SPI, DShot, the crystal and the analogue I
    # channel. Specctra type "power" marks the layer a plane: freerouting stops
    # routing through it but can still via down to it.
    # FR_PROTECT_LAYERS picks the trade. In1.Cu is the one that is not negotiable:
    # it sits directly under F.Cu and is the return path for USB, SDMMC, SPI, DShot
    # and the crystal. In2.Cu is already SPLIT into per-rail islands rather than a
    # solid reference, so routing there costs much less - and it hands freerouting a
    # third layer, which matters a lot on a board this dense (escape was 89% with
    # four layers, 70% with two).
    #   "In1.Cu,In2.Cu"  both protected - safest, fewest routing layers  (default)
    #   "In1.Cu"         reference plane kept solid, In2.Cu routable     (balanced)
    #   ""               nothing protected - what produced the shredded 88% board
    want = os.environ.get("FR_PROTECT_LAYERS", "In1.Cu,In4.Cu")
    if os.environ.get("FR_ALLOW_PLANE_ROUTING") == "1":
        want = ""
    _add_small_via(out)
    want = [w for w in (x.strip() for x in want.split(",")) if w]
    if not want:
        print("planes NOT protected - freerouting may route through them")
    else:
        txt = open(out).read(); hits = []
        for ln in want:
            needle = f"(layer {ln}\n      (type signal)"
            if needle in txt:
                txt = txt.replace(needle, f"(layer {ln}\n      (type power)", 1)
                hits.append(ln)
        open(out, "w").write(txt)
        if len(hits) != len(want):
            sys.exit(f"asked to protect {want}, matched {hits} - the DSN layer "
                     "format changed, check it before routing")
        print(f"planes protected: {', '.join(hits)} set to Specctra type power")
    sys.exit(0)

import pcbnew, design, route
tmp, out = sys.argv[2], sys.argv[3]

if stage == "--stage1":
    b = pcbnew.LoadBoard(tmp)
    # Force the design rules onto the board before anything else. The .kicad_pro
    # holding them is NOT copied alongside this temp board, so without this the
    # export silently falls back to defaults - a 0.15 -> 0.10 mm rule change simply
    # never reached the DSN, and the router kept solving the old, tighter problem.
    route.set_rules(b)
    n = 0
    for t in list(b.GetTracks()):
        b.Remove(t); n += 1
    pcbnew.SaveBoard(tmp, b)
    print(f"::stripped {n} tracks and vias")

elif stage == "--stage2":
    b = pcbnew.LoadBoard(tmp)
    B = design.BOARD
    CX, CY = B["X0"] + B["W"]/2, B["Y0"] + B["H"]/2
    R = B["HOLE_D"]/2 + 0.35
    for dx in (-B["MOUNT"]/2, B["MOUNT"]/2):
        for dy in (-B["MOUNT"]/2, B["MOUNT"]/2):
            hx, hy = CX + dx, CY + dy
            z = pcbnew.ZONE(b); z.SetIsRuleArea(True)
            z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True)
            z.SetDoNotAllowPads(True)
            ls = pcbnew.LSET()
            for ln in ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"):
                ls.addLayer(b.GetLayerID(ln))
            z.SetLayerSet(ls)
            o = z.Outline(); o.NewOutline()
            for k in range(16):
                a = 2*math.pi*k/16
                o.Append(pcbnew.FromMM(hx + R*math.cos(a)),
                         pcbnew.FromMM(hy + R*math.sin(a)))
            b.Add(z)
    # NPTH pads need keepouts too. freerouting knows only about copper clearance, so
    # it happily drops a via 0.48 mm from an NPTH pad's annulus - which is only
    # 0.18 mm from its DRILL, because the hole is wider than the copper around it.
    # That is a hole_clearance failure KiCad catches and freerouting never sees. Two
    # VBUS vias landed against J1's USB-C mounting holes exactly this way.
    npth = 0
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                continue
            q = pad.GetPosition()
            hx, hy = q.x / 1e6, q.y / 1e6
            # drill radius + via drill radius + the 0.2 mm hole-to-hole rule, plus
            # margin, so a via centre can never land inside the ring.
            rr = pad.GetDrillSizeX() / 2e6 + 0.15 + 0.20 + 0.15
            z = pcbnew.ZONE(b); z.SetIsRuleArea(True)
            z.SetDoNotAllowTracks(False); z.SetDoNotAllowVias(True)
            z.SetDoNotAllowPads(False)
            ls = pcbnew.LSET()
            for ln in ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"):
                ls.addLayer(b.GetLayerID(ln))
            z.SetLayerSet(ls)
            o = z.Outline(); o.NewOutline()
            for k in range(16):
                a = 2*math.pi*k/16
                o.Append(pcbnew.FromMM(hx + rr*math.cos(a)),
                         pcbnew.FromMM(hy + rr*math.sin(a)))
            b.Add(z)
            npth += 1

    pcbnew.SaveBoard(tmp, b)
    print(f"::added 4 mounting-hole keepouts and {npth} NPTH via-keepouts")

elif stage == "--stage3":
    b = pcbnew.LoadBoard(tmp)
    route.set_rules(b)
    ok = pcbnew.ExportSpecctraDSN(b, out)
    if not ok:
        sys.exit("ExportSpecctraDSN returned False")
    print("::DSN exported")
