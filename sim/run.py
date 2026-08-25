#!/usr/bin/env python3
"""Run an ngspice deck through KiCad's bundled libngspice, with no CLI installed."""
import ctypes
import sys

OUT = []
_lib = ctypes.CDLL("libngspice.so.0")


@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
def _send_char(msg, _id, _u):
    OUT.append(msg.decode(errors="replace"))
    return 0


@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
def _send_stat(msg, _id, _u):
    return 0


@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool,
                  ctypes.c_int, ctypes.c_void_p)
def _exit(status, immediate, quit_exit, _id, _u):
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    _lib.ngSpice_Init(_send_char, _send_stat, _exit, None, None, None, None)
    _lib.ngSpice_Command(f"source {sys.argv[1]}".encode())
    bad = [l for l in OUT if "Error" in l or "error" in l]
    for line in OUT:
        s = line.replace("stdout ", "").replace("stderr ", "")
        if "=" in s and not s.startswith("Note") or "Error" in s:
            print("  " + s)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
