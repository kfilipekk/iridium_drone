#!/usr/bin/env python3
"""Parse the tbs Source One V6 7in DC flat pattern into cad/frame-dxf.json.

Run:  ~/.cache/navcore/dxfvenv/bin/python3 tools/parse_frame_dxf.py [path/to.dxf]
      (system python has no ezdxf; the venv is created by the same one-liner the
       docstring in docs/VERIFICATION.md records)
"""
import collections, hashlib, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DXF = os.path.expanduser("~/.cache/navcore/frame/So1-V6-7inDC-2025-JUL-07.dxf")
OUT = os.path.join(os.path.dirname(HERE), "cad", "frame-dxf.json")

# The plates, identified by the layer tbs drew them on and their outline size.
PLATE_LAYERS = {"Draw3": "fc_plate", "Draw13": "top_plate", "Draw14": "bottom_plate"}


def main():
    try:
        import ezdxf
    except ImportError:
        print("ezdxf not importable - run with ~/.cache/navcore/dxfvenv/bin/python3")
        return 2
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DXF
    if not os.path.exists(path):
        print(f"DXF not found: {path}\n  fetch: curl -sL -o {path} "
              "https://raw.githubusercontent.com/tbs-trappy/source_one/HEAD/"
              "So1-V6-7inDC-2025-JUL-07.dxf")
        return 2
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    polys = []
    for e in msp.query("LWPOLYLINE"):
        pts = [(p[0], p[1], p[4]) for p in e.get_points()]
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        polys.append(dict(layer=e.dxf.layer, pts=pts, x0=min(xs), y0=min(ys),
                          x1=max(xs), y1=max(ys), w=max(xs) - min(xs), h=max(ys) - min(ys)))
    circles = [dict(layer=c.dxf.layer, x=c.dxf.center.x, y=c.dxf.center.y,
                    dia=2 * c.dxf.radius) for c in msp.query("CIRCLE")]
    texts = [dict(layer=t.dxf.layer, x=t.dxf.insert.x, y=t.dxf.insert.y, text=t.dxf.text)
             for t in msp.query("TEXT")]

    out = dict(source=os.path.basename(path), sha256=sha,
               units="mm" if doc.header.get("$INSUNITS") == 4 else str(doc.header.get("$INSUNITS")),
               plates={}, arms=[], labels=[], hardware=[])

    # ---- plates: first instance of each outline, holes relative to its centre ----
    seen = set()
    for p in polys:
        name = PLATE_LAYERS.get(p["layer"])
        if not name or max(p["w"], p["h"]) < 40 or name in seen:
            continue
        seen.add(name)
        cx = (p["x0"] + p["x1"]) / 2; cy = (p["y0"] + p["y1"]) / 2
        holes = [dict(dia=round(c["dia"], 2), x=round(c["x"] - cx, 2), y=round(c["y"] - cy, 2),
                      layer=c["layer"])
                 for c in circles if p["x0"] <= c["x"] <= p["x1"] and p["y0"] <= c["y"] <= p["y1"]]
        out["plates"][name] = dict(layer=p["layer"], w=round(p["w"], 2), l=round(p["h"], 2),
                                   holes=sorted(holes, key=lambda h: (h["dia"], h["x"], h["y"])))

    # ---- arms: motor centre = the O7 circle; slots = small 2-arc polylines around it --
    sevens = [c for c in circles if c["layer"] == "Frame-Arms" and abs(c["dia"] - 7.0) < 0.01]
    small = [p for p in polys if p["layer"] == "Frame-Arms" and max(p["w"], p["h"]) < 8]
    for s in sevens:
        slots = []
        for p in small:
            pcx = (p["x0"] + p["x1"]) / 2; pcy = (p["y0"] + p["y1"]) / 2
            r = math.hypot(pcx - s["x"], pcy - s["y"])
            if 4 < r < 16:
                # slot = 2 straight + 2 semicircle segments; radial extent from the
                # midpoints of the two arc chords
                pts = p["pts"]
                arcs = [i for i, q in enumerate(pts) if abs(q[2]) > 1e-9]
                ends = []
                for i in arcs:
                    a = pts[i]; b = pts[(i + 1) % len(pts)]
                    ends.append(math.hypot((a[0] + b[0]) / 2 - s["x"], (a[1] + b[1]) / 2 - s["y"]))
                width = math.hypot(pts[arcs[0]][0] - pts[(arcs[0] + 1) % len(pts)][0],
                                   pts[arcs[0]][1] - pts[(arcs[0] + 1) % len(pts)][1]) if arcs else None
                slots.append(dict(r_centre=round(r, 2),
                                  r_min=round(min(ends), 2) if ends else None,
                                  r_max=round(max(ends), 2) if ends else None,
                                  width=round(width, 2) if width else None))
        if slots:
            rs = sorted(set(sl["r_centre"] for sl in slots))
            out["arms"].append(dict(motor_centre=[round(s["x"], 2), round(s["y"], 2)],
                                    slots=slots,
                                    # a square pattern of side S has holes at S/sqrt2
                                    square_side_min=round(min(sl["r_min"] for sl in slots) * math.sqrt(2), 2),
                                    square_side_max=round(max(sl["r_max"] for sl in slots) * math.sqrt(2), 2)))

    # ---- thickness labels -> nearest big outline by x --------------------------
    outs = [p for p in polys if 25 <= max(p["w"], p["h"]) <= 200]
    for t in texts:
        if t["text"].endswith("mm") and t["layer"] == "Draw" and outs:
            near = min(outs, key=lambda o: abs((o["x0"] + o["x1"]) / 2 - t["x"]))
            out["labels"].append(dict(text=t["text"], layer=near["layer"],
                                      outline=[round(near["w"], 2), round(near["h"], 2)]))

    # ---- the frame's own hardware BOM, as drawn ----------------------------------
    out["hardware"] = [t["text"] for t in texts if t["layer"] in ("2", "9")
                       and ("M3" in t["text"] or "M2" in t["text"] or "nut" in t["text"].lower())]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {os.path.relpath(OUT)}  (dxf sha256 {sha[:16]})")
    for n, pl in out["plates"].items():
        print(f"  {n:13} {pl['w']} x {pl['l']}  {len(pl['holes'])} holes")
    for a in out["arms"][:1]:
        print(f"  arm motor slots: r {a['slots'][0]['r_min']}-{a['slots'][0]['r_max']} mm "
              f"-> square pattern {a['square_side_min']}-{a['square_side_max']} mm "
              f"({len(out['arms'])} motor ends)")
    print(f"  labels: {[l['text'] + '@' + l['layer'] for l in out['labels']]}")
    print(f"  hardware: {out['hardware']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
