#!/usr/bin/env python3
"""Read .kicad_mod footprints: body text, pad list, and courtyard extent."""
import re, os, glob, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jlcpaths

DIRS = [jlcpaths.FOOTPRINTS, "/usr/share/kicad/footprints"]

def find(fpid):
    nick, name = fpid.split(":", 1)
    cands = ([f"{DIRS[0]}/{name}.kicad_mod"] if nick == "jlc" else []) + \
            [f"{DIRS[1]}/{nick}.pretty/{name}.kicad_mod"]
    for c in cands:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), c) \
            if c.startswith("..") else c
        if os.path.exists(p): return p
    return None

def load(fpid):
    p = find(fpid)
    if not p: raise FileNotFoundError(fpid)
    s = open(p).read()
    pads = []
    # jlc footprints write (pad 100 smd oval ...); stock ones (pad "1" smd roundrect ...)
    # and split across lines - accept both.
    for m in re.finditer(r'\(pad\s+(?:"([^"]*)"|(\S+))\s+(\w+)\s+(\w+)\s*\(at\s+(-?[\d.]+)\s+(-?[\d.]+)'
                         r'(?:\s+(-?[\d.]+))?\)\s*\(size\s+(-?[\d.]+)\s+(-?[\d.]+)\)',
                         re.sub(r'\s+', ' ', s)):
        nq, nb, ptype, shape, x, y, rot, sx, sy = m.groups()
        num = nq if nq is not None else nb
        pads.append({'num': num, 'type': ptype, 'shape': shape,
                     'x': float(x), 'y': float(y), 'rot': float(rot or 0),
                     'sx': float(sx), 'sy': float(sy)})
    xs, ys = [], []
    for m in re.finditer(r'\(fp_(?:line|rect)\s*\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)'
                         r'\s*\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)((?:.|\n)*?)\)', s):
        x1, y1, x2, y2, rest = m.groups()
        if 'CrtYd' in rest:
            xs += [float(x1), float(x2)]; ys += [float(y1), float(y2)]
    if not xs:
        for pd in pads:
            xs += [pd['x'] - pd['sx']/2 - 0.25, pd['x'] + pd['sx']/2 + 0.25]
            ys += [pd['y'] - pd['sy']/2 - 0.25, pd['y'] + pd['sy']/2 + 0.25]
    if not xs: xs, ys = [-0.5, 0.5], [-0.5, 0.5]
    return {'path': p, 'text': s, 'pads': pads,
            'w': max(xs) - min(xs), 'h': max(ys) - min(ys),
            'cx': (max(xs) + min(xs)) / 2, 'cy': (max(ys) + min(ys)) / 2}

