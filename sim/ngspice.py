"""Drive KiCad's bundled libngspice from Python, with no ngspice CLI installed.

`run(netlist)` returns (vectors, log). `vectors` maps a vector name to a list of
floats (a transient/DC plot) or complex numbers (an `.ac` plot). `log` is the
engine's captured stdout, so a deck that fails to parse is visible rather than a
key error.

The shared library is the one KiCad ships (`libngspice.so.0`); it is on the
default loader path on a KiCad install. If it ever moves, set
NAVCORE_NGSPICE_LIB.
"""
import ctypes
import os

_LIB = os.environ.get("NAVCORE_NGSPICE_LIB", "libngspice.so.0")
_out = []
_lib = ctypes.CDLL(_LIB)

_SendChar = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_SendStat = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_Exit = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool,
                         ctypes.c_int, ctypes.c_void_p)


@_SendChar
def _send_char(s, _i, _p):
    _out.append(s.decode(errors="replace"))
    return 0


@_SendStat
def _send_stat(_s, _i, _p):
    return 0


@_Exit
def _exit(_a, _b, _c, _i, _p):
    return 0


_lib.ngSpice_Init(_send_char, _send_stat, _exit, None, None, None, None)


class _VectorInfo(ctypes.Structure):
    _fields_ = [
        ("v_name", ctypes.c_char_p),
        ("v_type", ctypes.c_int),
        ("v_flags", ctypes.c_short),
        ("v_realdata", ctypes.POINTER(ctypes.c_double)),
        ("v_compdata", ctypes.c_void_p),
        ("v_length", ctypes.c_int),
    ]


class _Complex(ctypes.Structure):
    _fields_ = [("re", ctypes.c_double), ("im", ctypes.c_double)]


_lib.ngGet_Vec_Info.restype = ctypes.POINTER(_VectorInfo)
_lib.ngSpice_CurPlot.restype = ctypes.c_char_p
_lib.ngSpice_AllVecs.restype = ctypes.POINTER(ctypes.c_char_p)


def run(netlist):
    """Run a whole netlist (with its own `.end`) and return (vectors, log)."""
    _out.clear()
    _lib.ngSpice_Command(b"destroy all")
    _lib.ngSpice_Command(b"reset")
    lines = netlist.strip().splitlines()
    arr = (ctypes.c_char_p * (len(lines) + 1))(*[l.encode() for l in lines], None)
    _lib.ngSpice_Circ(arr)
    _lib.ngSpice_Command(b"run")
    plot = _lib.ngSpice_CurPlot()
    names = _lib.ngSpice_AllVecs(plot)
    res = {}
    i = 0
    while names[i]:
        name = names[i].decode()
        info = _lib.ngGet_Vec_Info(f"{plot.decode()}.{name}".encode()).contents
        if info.v_realdata:
            res[name] = [info.v_realdata[k] for k in range(info.v_length)]
        elif info.v_compdata:
            cp = ctypes.cast(info.v_compdata, ctypes.POINTER(_Complex))
            res[name] = [complex(cp[k].re, cp[k].im) for k in range(info.v_length)]
        i += 1
    return res, list(_out)


def errors(log):
    """The engine error lines from a captured log, so a bad deck is not silent."""
    return [l for l in log if "error" in l.lower()]
