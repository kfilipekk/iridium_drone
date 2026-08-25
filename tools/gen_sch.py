#!/usr/bin/env python3
"""
Generate NAVCORE-SoOP.kicad_sch from tools/design.py.

Connectivity is expressed with global labels placed exactly on pin endpoints rather
than drawn wires. That is valid KiCad and keeps a 500-connection netlist readable and
diffable; the netlist itself lives in design.py, which is the actual source of truth.
"""
import os, sys, re, uuid, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symlib, design

JLC   = "../.libraries/symbols/jlc_parts.kicad_sym"
STOCK = "/usr/share/kicad/symbols"
U = lambda: str(uuid.uuid4())

def raw_symbol(libpath, name):
    """Return the verbatim (symbol "name" ...) block from a .kicad_sym file."""
    s = open(libpath).read()
    m = re.search(r'\(symbol "%s"' % re.escape(name), s)
    if not m: return None
    d, i = 0, m.start()
    while i < len(s):
        if s[i] == '(': d += 1
        elif s[i] == ')':
            d -= 1
            if d == 0: break
        i += 1
    return s[m.start():i+1]

def collect():
    """lib_id -> (raw block, pin list)"""
    out, syms_jlc = {}, symlib.load()
    for ref,(lib_id, fp, val, lcsc, dnp) in design.COMPONENTS.items():
        if lib_id in out: continue
        nick, name = lib_id.split(":", 1)
        path = JLC if nick == "jlc_parts" else f"{STOCK}/{nick}.kicad_sym"
        blk = raw_symbol(path, name)
        if blk is None:
            raise SystemExit(f"symbol {lib_id} not found in {path}")
        blk = blk.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)
        pins = (syms_jlc.get(name) if nick == "jlc_parts" else symlib.load(path).get(name)) or []
        out[lib_id] = (blk, pins)
    return out

GRID = 1.27
def snap(v): return round(v / GRID) * GRID

def pin_index(lib):
    """lib_id -> {pin number: (x, y, rot, unit)}"""
    return {lid: {p['num']: (p['x'], p['y'], p['rot'], p.get('unit', 1)) for p in pins}
            for lid, (blk, pins) in lib.items()}

def resolve_pin(lib_id, pins_by_num, spec, lib):
    if spec in pins_by_num: return spec
    _blk, plist = lib[lib_id]
    named = [p for p in plist if p['name'] == spec]
    if len(named) == 1: return named[0]['num']
    pre = [p for p in plist if p['name'].split('-')[0] == spec]
    if len(pre) == 1: return pre[0]['num']
    return None

def main():
    lib = collect()
    pidx = pin_index(lib)

    # --- lay out using each symbol's real pin extent so nothing overlaps ------
    def extent(lid):
        pins = lib[lid][1]
        if not pins: return 10.0, 10.0
        nu = max(p.get('unit', 1) for p in pins)
        xs = [p['x'] for p in pins]; ys = [p['y'] for p in pins]
        w = (max(xs) - min(xs)) + 30.48 * (nu - 1) + 25.4   # + label room
        h = (max(ys) - min(ys)) + 15.24
        return max(w, 20.0), max(h, 15.0)

    order = sorted(design.COMPONENTS, key=lambda r: (-len(pidx[design.COMPONENTS[r][0]]), r))
    place, x, y, rowh = {}, 40.0, 40.0, 0.0
    PAGE_W = 1400.0
    for ref in order:
        w, h = extent(design.COMPONENTS[ref][0])
        if x + w > PAGE_W:
            x = 40.0; y = snap(y + rowh + 20.0); rowh = 0.0
        place[ref] = (snap(x + w/2), snap(y + h/2))
        # Gutter scales with the symbol so tiny 1-pin parts (power flags, test
        # points) cannot end up with coincident labels as the design grows.
        x = snap(x + w + (25.4 if len(pidx[design.COMPONENTS[ref][0]]) <= 2 else 12.7))
        rowh = max(rowh, h)

    # --- net lookup: (ref, pinnum) -> netname ------------------------------
    single = {n for n, v in design.NETS.items() if len(v) == 1}
    pin_net = {}
    for netname, specs in design.NETS.items():
        if netname in single: continue      # single-pin net -> no_connect, not a label
        for sp in specs:
            ref, pin = sp.split(".", 1)
            if ref not in design.COMPONENTS: continue
            lid = design.COMPONENTS[ref][0]
            num = resolve_pin(lid, pidx[lid], pin, lib)
            if num: pin_net[(ref, num)] = netname

    out = ['(kicad_sch', '\t(version 20231120)', '\t(generator "navcore-gen")',
           '\t(generator_version "9.0")', f'\t(uuid "{U()}")', '\t(paper "User" 1100 850)',
           '\t(lib_symbols']
    for lid in sorted(lib):
        out.append("\t\t" + lib[lid][0].replace("\n", "\n\t\t"))
    out.append('\t)')

    nlabels = 0
    nnc = 0
    for ref in order:
        lid, fp, val, lcsc, dnp = design.COMPONENTS[ref]
        cx, cy = place[ref]
        units = sorted({u for (_x, _y, _r, u) in pidx[lid].values()})
        for ui in units:
            ox = cx + (ui - 1) * 30.48
            out += [f'\t(symbol (lib_id "{lid}") (at {ox:.2f} {cy:.2f} 0) (unit {ui})',
                    '\t\t(exclude_from_sim no) (in_bom yes) (on_board yes)'
                    f' (dnp {"yes" if dnp else "no"})',
                    f'\t\t(uuid "{U()}")',
                    f'\t\t(property "Reference" "{ref}" (at {ox:.2f} {cy-3.81:.2f} 0)'
                    ' (effects (font (size 1.27 1.27)) (justify left)))',
                    f'\t\t(property "Value" "{val}" (at {ox:.2f} {cy-2.54:.2f} 0)'
                    ' (effects (font (size 1.27 1.27)) (justify left)))',
                    f'\t\t(property "Footprint" "{fp}" (at {ox:.2f} {cy:.2f} 0)'
                    ' (effects (font (size 1.27 1.27)) hide))',
                    f'\t\t(property "LCSC" "{lcsc}" (at {ox:.2f} {cy:.2f} 0)'
                    ' (effects (font (size 1.27 1.27)) hide))']
            for num, (_px, _py, _pr, pu) in pidx[lid].items():
                if pu == ui:
                    out.append(f'\t\t(pin "{num}" (uuid "{U()}"))')
            out += ['\t\t(instances (project "NAVCORE-SoOP"'
                    f' (path "/" (reference "{ref}") (unit {ui}))))', '\t)']

            for num, (px, py, prot, pu) in pidx[lid].items():
                if pu != ui: continue
                ax, ay = snap(ox + px), snap(cy - py)
                netname = pin_net.get((ref, num))
                if netname:
                    lrot = 0 if abs(prot - 180) < 1 else 180
                    out += [f'\t(global_label "{netname}" (shape passive)'
                            f' (at {ax:.2f} {ay:.2f} {lrot})',
                            '\t\t(effects (font (size 1.0 1.0))'
                            f' (justify {"right" if lrot else "left"}))',
                            f'\t\t(uuid "{U()}")', '\t)']
                    nlabels += 1
                else:
                    out += [f'\t(no_connect (at {ax:.2f} {ay:.2f}) (uuid "{U()}"))']
                    nnc += 1

    out += ['\t(sheet_instances (path "/" (page "1")))', '\t(embedded_fonts no)', ')']
    open("NAVCORE-SoOP.kicad_sch", "w").write("\n".join(out) + "\n")
    print(f"schematic: {len(design.COMPONENTS)} symbols, {nlabels} net labels, "
          f"{nnc} no-connects, {len(lib)} unique symbols embedded")

if __name__ == "__main__":
    main()
