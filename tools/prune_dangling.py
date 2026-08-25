#!/usr/bin/env python3
"""
Remove copper that connects nothing: tracks with a free end, and vias plated on one side.

The router scripts in this directory commit a track, then re-plan around it, and the
leftovers accumulate. DRC classes them `track_dangling` / `via_dangling` at warning
severity, so nothing ever blocked on them and 31 pieces built up.

Most are litter. Some are not:

  * VBAT on In2.Cu, 8.84 mm with a free end - the largest orphan on the board, on the
    highest-voltage net.
  * two BUCK_PH stubs - the 5 V buck's switch node, the highest dV/dt net here and the
    worst place on the board to leave an unterminated radiator.
  * four +5V vias plated on ONE side only, and one on USB_DM whose F.Cu end floats.
    check_traces.py independently reports the USB pair as asymmetric ("via counts differ:
    2 vs 3"); that via is the reason.

WHY THIS DOES NOT TRUST THE DRC LABEL

The obvious implementation - parse `track_dangling`, delete everything it names - is
wrong, and it was tried first: it removed 29 items in one pass and broke 7 connections.
`track_dangling` means "one end touches nothing". It does NOT mean the piece is
load-bearing at neither end, and it says nothing about redundancy: two tracks can each be
individually removable while the pair is not, because the second carries what the first
was carrying.

So the DRC report is used only to propose candidates. Whether a piece is actually inert
is decided by KiCad's own connectivity engine, per candidate, with the zones refilled -
removing a track lets the surrounding pour expand into the gap, which changes
connectivity, so filling is part of the test rather than an afterthought.

Each candidate is tried on a freshly loaded board (accepted removals replayed), in a
SUBPROCESS. Two reasons, both learned the hard way: Remove() followed by Add()
invalidates the SWIG handle and segfaults later, so a trial must never be undone in
place; and several LoadBoard() calls in one interpreter segfault on their own once
tracks have been removed from any of them. One board per process is the only
arrangement that survives.

DRC must run on the board in its own directory: kicad-cli reads the design rules from the
.kicad_pro beside it, and a copy elsewhere silently falls back to KiCad's 0.2 mm defaults
and invents about 1100 violations.

Usage: python3 tools/prune_dangling.py [--apply]
"""
import os, re, sys, json, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

BOARD = 'NAVCORE-SoOP.kicad_pcb'
RPT   = '/tmp/nav/prune_drc.rpt'
TOL   = pcbnew.FromMM(0.005)      # DRC prints 4 decimal places

TRACK_RE = re.compile(
    r'@\((?P<x>-?[\d.]+) mm, (?P<y>-?[\d.]+) mm\): Track \[(?P<net>[^\]]*)\] on (?P<layer>[^,\s]+)')
VIA_RE = re.compile(
    r'@\((?P<x>-?[\d.]+) mm, (?P<y>-?[\d.]+) mm\): Via \[(?P<net>[^\]]*)\] on ')


def drc():
    os.makedirs(os.path.dirname(RPT), exist_ok=True)
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--output', RPT,
                    '--severity-all', BOARD], capture_output=True, timeout=900)
    return open(RPT).read() if os.path.exists(RPT) else ''


def dangling(rpt):
    """(kind, x, y, net, layer) for every dangling item DRC names.

    Parsed line by line, tracking the current violation class. Splitting the report on
    '[' does not work: every entry carries a '[NET]' of its own, so the split lands
    mid-entry and the class is lost.
    """
    out, kind = [], None
    for line in rpt.splitlines():
        m = re.match(r'^\[([a-z_]+)\]', line)
        if m:
            kind = m.group(1)
            continue
        if kind not in ('track_dangling', 'via_dangling'):
            continue
        m = TRACK_RE.search(line) if kind == 'track_dangling' else VIA_RE.search(line)
        if m:
            out.append((kind, float(m.group('x')), float(m.group('y')),
                        m.group('net'), m.groupdict().get('layer')))
    return out


def key(board, t):
    """Identity stable across reloads: type, net, layer, and both endpoints in nm."""
    s, e = t.GetStart(), t.GetEnd()
    return (t.Type() == pcbnew.PCB_VIA_T, t.GetNetname(),
            board.GetLayerName(t.GetLayer()), s.x, s.y, e.x, e.y)


def find(board, kind, x, y, net, layer):
    want_via = (kind == 'via_dangling')
    xn, yn = pcbnew.FromMM(x), pcbnew.FromMM(y)
    best, bestd = None, None
    for t in list(board.GetTracks()):
        if (t.Type() == pcbnew.PCB_VIA_T) != want_via:
            continue
        if t.GetNetname() != net:
            continue
        if not want_via and board.GetLayerName(t.GetLayer()) != layer:
            continue
        # DRC names a track by whichever end it likes, so test both.
        ends = [t.GetStart()] if want_via else [t.GetStart(), t.GetEnd()]
        for p in ends:
            d = max(abs(p.x - xn), abs(p.y - yn))
            if d <= TOL and (bestd is None or d < bestd):
                best, bestd = t, d
    return best


def _trial(remove_keys, save=False):
    """Drop every track whose key is in remove_keys, refill, count. Runs in-process;
    the caller is responsible for making that process disposable."""
    b = pcbnew.LoadBoard(BOARD)
    doomed = [t for t in list(b.GetTracks()) if key(b, t) in remove_keys]
    for t in doomed:
        b.Remove(t)
    if save:
        # Only on the real commit: ZONE_FILLER after a Remove segfaults often enough
        # that it cannot be in the trial path, which runs it dozens of times.
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.BuildConnectivity()
    n = b.GetConnectivity().GetUnconnectedCount(True)
    if save:
        b.Save(BOARD)
    return n, len(doomed)


def unconnected_after(remove_keys, save=False):
    """As _trial, but in a throwaway subprocess so SWIG lifetime bugs cannot reach us."""
    payload = json.dumps([list(k) for k in remove_keys])
    r = subprocess.run([sys.executable, os.path.abspath(__file__), '--trial',
                        '--save' if save else '--nosave'],
                       input=payload, capture_output=True, text=True, timeout=900)
    for line in r.stdout.splitlines():
        if line.startswith('RESULT '):
            _, n, removed = line.split()
            return int(n), int(removed)
    raise RuntimeError(f"trial failed:\n{r.stdout}\n{r.stderr}")


def main():
    if '--trial' in sys.argv:
        keys = {tuple(k) for k in json.loads(sys.stdin.read())}
        n, removed = _trial(keys, save='--save' in sys.argv)
        print(f"RESULT {n} {removed}")
        return 0

    apply = '--apply' in sys.argv
    rpt = drc()
    cands = dangling(rpt)
    print(f"DRC proposes {len(cands)} dangling item(s)")

    base = pcbnew.LoadBoard(BOARD)
    resolved = []
    for kind, x, y, net, layer in cands:
        t = find(base, kind, x, y, net, layer)
        if t is None:
            print(f"  no match: {kind} {net} @({x}, {y})")
            continue
        length = 0.0 if kind == 'via_dangling' else pcbnew.ToMM(t.GetLength())
        resolved.append((key(base, t), kind, net, layer, length))
    print(f"matched {len(resolved)} on the board")

    baseline, _ = unconnected_after(set())
    print(f"baseline unconnected: {baseline}\n")

    safe, unsafe = [], []
    for k, kind, net, layer, length in resolved:
        n, _ = unconnected_after({k})
        tag = "inert" if n == baseline else f"LOAD-BEARING (+{n - baseline})"
        if n == baseline:
            safe.append((k, kind, net, layer, length))
        else:
            unsafe.append((k, kind, net, layer, length, n - baseline))
        print(f"  {kind:14s} {net:10s} {(layer or ''):7s} {length:6.2f} mm  {tag}")

    print(f"\n{len(safe)} inert, {len(unsafe)} load-bearing despite the dangling label")

    if not apply:
        print("\ndry run - pass --apply to remove the inert ones")
        return 0

    # Individually inert is not jointly inert: two tracks can be redundant with each
    # other. Try the whole set, and if that regresses, fall back to one at a time.
    keys = {s[0] for s in safe}
    n, removed = unconnected_after(keys)
    if n != baseline:
        print(f"joint removal regressed ({n} vs {baseline}) - falling back to cumulative")
        keys = set()
        for k, kind, net, layer, length in safe:
            trial = keys | {k}
            m, _ = unconnected_after(trial)
            if m == baseline:
                keys = trial
            else:
                print(f"  keeping {kind} {net} {layer} - redundant pair")
    total = sum(s[4] for s in safe if s[0] in keys)
    n, removed = unconnected_after(keys, save=True)
    print(f"\nremoved {removed} item(s), {total:.2f} mm of track; unconnected {n}")
    return 0 if n == baseline else 1


if __name__ == '__main__':
    sys.exit(main())
