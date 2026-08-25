#!/usr/bin/env python3
"""
Which spare MCU pins can actually be used?

"Spare" in a netlist means "nothing is connected to it". On a finished board that is not
the same as "available": an inner pin of a 100-pin LQFP whose neighbours have already
escaped can be walled into a pocket a couple of square millimetres across, with nowhere
to put the via it would need to get out. PE15 and PB2 on this board are exactly that -
both look free in design.py and neither can be routed anywhere. That is not a detail you
want to discover after committing a circuit to one of them.

So this measures the real thing: from each spare pin's pad, how much of its own layer a
trace can reach, and how many of those cells could take a via.

It also matters WHICH spare you take. This board's premise is pin-identity with
MatekH743, so a pin MatekH743 DRIVES will be driven by a stock binary too. For something
that must fail safe - a VTX enable, say - the right choice is a pin MatekH743 only ever
reads: PA7 is an ADC input there, so no stock firmware can assert it.

Usage:  python3 tools/scan_spare_pins.py
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew, route, shove, island_route as ir, move_net_pin as mv, design, symlib

BOARD = "NAVCORE-SoOP.kicad_pcb"
VIA_D, DRILL = 0.45, 0.20


def main():
    b = pcbnew.LoadBoard(BOARD)
    route.set_rules(b)
    h7 = {p['name'].split('-')[0]: p['num']
          for p in symlib.load()["STM32H743VIT6_C114409"]}
    u1 = b.FindFootprintByReference("U1")
    pads = {q.GetNumber(): q for q in u1.Pads()}

    spares = []
    for n, specs in design.NETS.items():
        if len(specs) == 1 and specs[0].startswith("U1."):
            pin = specs[0].split(".", 1)[1]
            num = h7.get(pin, pin)
            if num in pads:
                spares.append((n, pin, num))

    allsh_base = shove.shapes_of(b)
    holes = route.hole_shapes(b)
    kos = route.keepout_boxes(b)
    print(f"{len(spares)} spare MCU pins to test\n")
    print(f"  {'PIN':6} {'LAYER':7} {'REACHABLE':>12}  {'VIA-LEGAL':>9}  VERDICT")

    for netname, pin, num in sorted(spares, key=lambda t: t[1]):
        pad = pads[num]
        p = pad.GetPosition()
        x, y = route.TOMM(p.x), route.TOMM(p.y)
        allsh = [s for s in allsh_base if s.net != netname]
        kidx = shove.ShapeIndex(allsh)
        lay = mv.pad_layers(b, pad)
        if not lay:
            print(f"  {pin:6} no signal layer")
            continue
        L = lay[0]
        g = ir.Grid(b, L, (x-7, y-7, x+7, y+7), 0.05, allsh, 1.0)
        c = g.cell(x, y)
        if not g.ok(*c):
            print(f"  {pin:6} {L:7} pad cell itself is blocked")
            continue
        d, _ = shove.spread(g, [c])
        need = VIA_D/2 + route.VIA_CLEAR + 0.005
        vias = 0
        for cell in d:
            vx, vy = g.pos(*cell)
            if not route.inside_board(vx, vy, VIA_D/2 + 0.35):
                continue
            if not route.hole_ok(vx, vy, holes, DRILL):
                continue
            if any(x1 - VIA_D/2 < vx < x2 + VIA_D/2 and y1 - VIA_D/2 < vy < y2 + VIA_D/2
                   for x1, y1, x2, y2 in kos):
                continue
            if any(route.gap_to_shape(vx, vy, s.geom) < need
                   for s in kidx.near(vx, vy, need + 1.0)):
                continue
            vias += 1
        print(f"  {pin:6} {L:7} {len(d)*0.0025:9.1f} mm2  {vias:9}  "
              f"{'usable' if vias else 'BOXED IN - unusable'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
