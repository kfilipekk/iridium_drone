"""The project a tool works on: its root, board, schematic, design data and scratch space."""
import glob, os, sys

ROOT = os.path.abspath(os.environ.get("KICAD_PROJECT") or os.getcwd())
_tools = os.path.join(ROOT, "tools")
if os.path.isdir(_tools) and _tools not in sys.path:
    sys.path.append(_tools)

try:
    import design
except ImportError:
    design = None


#the value given after `name` on the command line
def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv[:-1] else default


#every value given after `name`
def args(name):
    return [sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == name]


#the board to work on
def board_path():
    b = arg("--board") or os.environ.get("KICAD_BOARD")
    if b:
        if not os.path.isfile(b):
            if any(h in sys.argv for h in ("-h", "--help", "help")):
                return ""
            raise SystemExit(f"board file not found: {b}")
        return b
    boards = sorted(os.path.relpath(b) for b in glob.glob(os.path.join(ROOT, "*.kicad_pcb"))
                    if "backup" not in b and not os.path.basename(b).startswith("_autosave"))
    if len(boards) == 1:
        return boards[0]
    if len(sys.argv) < 2 or any(h in sys.argv for h in ("-h", "--help", "help")):
        return ""
    raise SystemExit("which board? pass --board PATH or set KICAD_BOARD "
                     f"(found: {', '.join(boards) or 'none'})")


def _name():
    pro = glob.glob(os.path.join(ROOT, "*.kicad_pro"))
    if len(pro) == 1:
        return os.path.basename(pro[0])[:-len(".kicad_pro")]
    pcb = glob.glob(os.path.join(ROOT, "*.kicad_pcb"))
    return os.path.basename(pcb[0])[:-len(".kicad_pcb")] if len(pcb) == 1 else "board"


NAME = _name()
SCH = os.path.join(ROOT, NAME + ".kicad_sch")
FAB = os.path.join(ROOT, "fab")

#the project's vendored JLC library
SYMBOLS = os.environ.get("JLC_SYM") or os.path.join(
    ROOT, "libraries", "symbols", "jlc_parts.kicad_sym")
FOOTPRINTS = os.environ.get("JLC_FP") or os.path.join(ROOT, "libraries", "jlc.pretty")
#the shared JLC library every project fetches into: .libraries/ here
SHARED = next((d for d in (os.path.join(ROOT, ".libraries"),
                           os.path.join(os.path.dirname(ROOT), ".libraries")) if os.path.isdir(d)),
              os.path.join(os.path.dirname(ROOT), ".libraries"))
MODELS = os.environ.get("JLC_LIB") or os.path.join(SHARED, "jlc.pretty")


#a path in the project's scratch directory
def scratch(name=""):
    d = os.environ.get("KICAD_TOOLS_TMP") or os.path.join(
        os.path.expanduser("~/.cache/kicad-tools"), NAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


#run the command named on the command line, or list them
def main(commands, doc):
    help_requested = any(h in sys.argv[1:] for h in ("-h", "--help", "help"))
    cmd_idx = next((i for i, a in enumerate(sys.argv[1:], 1) if a in commands), None)

    if cmd_idx is not None:
        cmd_name = sys.argv.pop(cmd_idx)
        cmd = commands[cmd_name]
        if help_requested:
            if cmd.__doc__:
                print(cmd.__doc__.strip())
            else:
                print(f"Usage: python3 {os.path.basename(sys.argv[0])} {cmd_name} [options]")
            return 0
        return cmd()

    if help_requested:
        print(doc.strip())
        return 0

    if len(sys.argv) < 2:
        print(doc.strip())
        return 2

    first_arg = next((a for a in sys.argv[1:] if not a.startswith("-")), sys.argv[1])
    print(f"Unknown command: '{first_arg}'")
    print(f"Available commands: {', '.join(sorted(commands.keys()))}\n")
    print(doc.strip())
    return 2
