#!/usr/bin/env python3
"""Every regex in the gate, tested against the text the tools ACTUALLY print.

THE DEFECT THIS HUNTS
---------------------
A gate regex exists to pull a number or a verdict out of a tool's output. When the tool's
format changes and the regex stops matching, **the check does not fail loudly** — it falls
through to a fallback string, so the gate can still print `ok` while the evidence printed
beside it is a lie.

That is exactly what the SITL check did: it grepped `green\\s*:\\s*\\d+/\\d+ scenario`, which
`check_sitl.py` has never emitted, so a **passing** suite of 5/5 asserting scenarios was
printed as *"no SITL result recorded, or it predates the current parameters"*. The verdict
was right and the evidence next to it said the opposite.

It cannot be found by reading `preflight.py` alone — you have to see what the tools print.
So this runs the real gate with `subprocess.run` patched, tees every subprocess's stdout
and stderr to disk (nothing in the repo is modified; this only observes), then AST-parses
`preflight.py` for every `re.search` / `re.findall` / `re.match` with a literal pattern and
reports which captured output each one matches.

WHAT A "DEAD" PATTERN MEANS
---------------------------
`NONE` is a *candidate* defect, not a verdict. Most are legitimate: a check whose failure
line only prints on the failure path (so on a green board it correctly matches nothing),
or a pattern that parses a **report file** written by `kicad-cli drc`/`erc` rather than a
subprocess's stdout. This classifies those automatically — it looks at whether the
enclosing function reads a report file — rather than pinning line numbers, which drift.

    python3 tools/audit_gate_patterns.py                 # capture + audit (runs the gate, ~15 min)
    python3 tools/audit_gate_patterns.py --capture-only  # just capture, for later audits
    python3 tools/audit_gate_patterns.py --audit-dir DIR # audit an existing capture

Exit code is always 0: this is an audit, not a gate. Read the NONE list and judge it.
"""
import argparse
import ast
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PREFLIGHT = os.path.join(HERE, "preflight.py")

# A function that reads a kicad-cli report file gets its evidence from disk, not stdout.
FILE_SOURCE_HINTS = ("cli(", "json.load", "loads(", "json.loads")


def capture(outdir):
    """Run the real gate with every subprocess teed to `outdir`."""
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        os.unlink(os.path.join(outdir, f))

    _real_run = subprocess.run
    seen = {}

    def patched(args, *a, **k):
        r = _real_run(args, *a, **k)
        try:
            argv = list(args) if not isinstance(args, str) else [args]
            stem = os.path.basename(argv[1]) if len(argv) > 1 and argv[1].endswith(".py") \
                else os.path.basename(argv[0])
            stem = stem.replace(".py", "")
            label = stem if len(argv) < 2 or not argv[1].endswith(".py") else " ".join(
                [stem] + [x for x in argv[2:] if x.startswith("--")])
            seen[label] = seen.get(label, 0) + 1
            with open(os.path.join(outdir, f"{label}.txt"), "a",
                      encoding="utf-8", errors="replace") as fh:
                fh.write(f"\n##### argv={' '.join(argv)} rc={r.returncode}\n")
                fh.write(r.stdout or "")
                if r.stderr:
                    fh.write("\n##### stderr\n")
                    fh.write(r.stderr)
        except Exception as e:                                  # never break the gate
            print(f"capture failed: {e}", file=sys.stderr)
        return r

    subprocess.run = patched
    sys.path.insert(0, HERE)
    os.chdir(REPO)
    import preflight                                          # noqa: E402
    rc = preflight.main()
    print(f"\ncaptured {sum(seen.values())} subprocess run(s) into {outdir}")
    for k in sorted(seen):
        print(f"   {k} x{seen[k]}")
    return rc


def flags_of(node):
    """Reconstruct the `re` flags argument, so a pattern is tested as the gate uses it.

    The first version of this audit compiled every pattern with NO flags, so all 19
    `^`-anchored patterns "matched nothing" and were reported dead. That was an audit bug,
    not a gate bug: the gate passes `re.M`, and under `re.M` those anchors mean line-start.
    Extracted from the AST rather than assumed.
    """
    f = 0
    names = {"M": re.M, "MULTILINE": re.M, "I": re.I, "IGNORECASE": re.I,
             "S": re.S, "DOTALL": re.S}

    def walk(n):
        nonlocal f
        if isinstance(n, ast.Attribute) and n.attr in names:
            f |= names[n.attr]
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
            walk(n.left)
            walk(n.right)
    for arg in node.args[2:]:
        walk(arg)
    for kw in node.keywords:
        if kw.arg == "flags":
            walk(kw.value)
    return f


def audit(outdir):
    src = open(PREFLIGHT).read()
    lines = src.splitlines()
    tree = ast.parse(src)

    funcs = [(n.lineno, n.end_lineno, n.name)
             for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    func_src = {name: ast.get_source_segment(src, n) or ""
                for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

    def enclosing(lineno):
        """The INNERMOST function containing this line, by real AST span."""
        best = ("?", 10 ** 9)
        for lo, hi, name in funcs:
            if lo <= lineno <= hi and (hi - lo) < best[1]:
                best = (name, hi - lo)
        return best[0]

    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("search", "findall", "match") \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "re":
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                calls.append((node.lineno, node.args[0].value, node.func.attr,
                              flags_of(node)))

    outputs = {}
    if os.path.isdir(outdir):
        for f in sorted(os.listdir(outdir)):
            outputs[f[:-4]] = open(os.path.join(outdir, f), encoding="utf-8",
                                   errors="replace").read()

    print(f"{len(calls)} regex(es) in preflight.py, tested against {len(outputs)} captured "
          f"tool output(s)\n")

    dead, thin = [], []
    for lineno, pat, attr, flags in sorted(calls):
        fn = enclosing(lineno)
        body = func_src.get(fn, "")
        parses_file = any(h in body for h in FILE_SOURCE_HINTS)
        try:
            rx = re.compile(pat, flags)
        except re.error as e:
            print(f"  !! line {lineno}: will not compile: {e}")
            continue
        hits = [k for k, txt in outputs.items() if rx.search(txt)]
        tag = "NONE" if not hits else ",".join(hits)
        note = "  [enclosing fn reads a report FILE, not stdout]" if parses_file else ""
        print(f"  line {lineno:3} re.{attr:7} {fn:14} flags={flags} -> {tag}{note}")
        print(f"        {lines[lineno-1].strip()[:96]}")
        if not hits and not parses_file:
            dead.append((lineno, pat))
        elif len(hits) == 1 and attr == "search":
            thin.append((lineno, hits[0]))

    print(f"\n=== {len(dead)} pattern(s) match NO captured tool output ===")
    print("    A candidate defect only. The common legitimate reason is a failure line that")
    print("    prints on the failure path and correctly matches nothing on a green board -")
    print("    check the tool's own f-string before concluding the pattern is stale.")
    for lineno, pat in dead:
        print(f"  line {lineno}: {pat!r}")
        print(f"     {lines[lineno-1].strip()[:100]}")

    print(f"\n=== {len(thin)} search pattern(s) match exactly one tool ===")
    for lineno, tool in thin:
        print(f"  line {lineno:3} parses {tool}")

    print("\nAudit only - always exit 0. Judge the NONE list above by hand; the test of a")
    print("stale pattern is whether the tool can still produce that string at all.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-only", action="store_true",
                    help="run the gate and tee tool output, do not audit")
    ap.add_argument("--audit-dir", help="audit an existing capture instead of running the gate")
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "nav_gate_toolout"),
                    help="where to write captured tool output")
    a = ap.parse_args()

    if a.audit_dir:
        return audit(a.audit_dir)
    if a.capture_only:
        return capture(a.out)
    capture(a.out)
    print()
    return audit(a.out)


if __name__ == "__main__":
    sys.exit(main())
