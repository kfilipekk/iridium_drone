#!/usr/bin/env python3
"""Does the tuner driver program the MAX2112 the way its datasheet says?

Usage:  python3 tools/check_soop_max2112.py [--self-test]
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOOP = os.path.join(ROOT, "firmware", "soop")
REF = 25.0e6                      #Y2, the TCXO
STEP = REF / 2 ** 20


def flight_lo():
    sig = open(os.path.join(SOOP, "soop_signal.h")).read()
    ring = float(re.search(r"#define SOOP_F_RING_ALERT\s+([\d.eE+]+)", sig).group(1))
    off = float(re.search(r"#define SOOP_LO_OFFSET_HZ\s+\(?([-\d.eE+]+)", sig).group(1))
    return ring + off


def build(src_dir, out):
    r = subprocess.run(["cc", "-O2", "-std=c99", "-Wall", "-Wextra", "-Wshadow", "-o", out,
                        os.path.join(SOOP, "max2112_host.c"),
                        os.path.join(src_dir, "soop_max2112.c"), "-I", SOOP, "-lm"],
                       capture_output=True, text=True)
    return r.returncode == 0, r.stderr


def query(host, lines):
    r = subprocess.run([host], input="\n".join(lines) + "\n", capture_output=True,
                       text=True, check=True)
    return r.stdout.split("\n")[:len(lines)]


def decode(regs):
    """The datasheet's fields, from the bytes alone."""
    r = regs
    return dict(
        FRAC=r[0] >> 7, N=((r[0] & 0x7F) << 8) | r[1],
        CPMP=r[2] >> 6, CPLIN=(r[2] >> 4) & 3, F=((r[2] & 0x0F) << 16) | (r[3] << 8) | r[4],
        XD=r[5] >> 5, R=r[5] & 0x1F,
        D24=r[6] >> 7, CPS=(r[6] >> 6) & 1, ICP=(r[6] >> 5) & 1,
        VCO=r[7] >> 3, VAS=(r[7] >> 2) & 1, ADL=(r[7] >> 1) & 1, ADE=r[7] & 1,
        LPF=r[8], STBY=r[9] >> 7, PWDN=(r[9] >> 5) & 1, BBG=r[9] & 0x0F,
        SHDN=r[10] & 0x7F, CPTST=r[11] >> 5, TURBO=(r[11] >> 3) & 1, LDMUX=r[11] & 7,
    )


def evaluate(host):
    fails = []
    lo_f = flight_lo()
    cases = [(lo, bbg) for lo in (1616.0e6, 1621.25e6, 1626.5e6, lo_f) for bbg in (0, 4, 15)]
    cases += [(1625.0e6 - 3.0, 4), (1600.0e6 - 1.0, 4), (1000.0e6, 4)]
    out = query(host, [f"regs {lo!r} {REF!r} {bbg}" for lo, bbg in cases])
    for (lo, bbg), line in zip(cases, out):
        p = line.split()
        if p[0] != "0":
            fails.append(f"LO {lo / 1e6:.6f} MHz refused")
            continue
        d = decode([int(x, 16) for x in p[1:13]])
        want = dict(FRAC=1, CPMP=0, CPLIN=1, XD=0, R=1, D24=int(lo < 1125e6), CPS=0, ICP=0,
                    VCO=0b11001, VAS=1, ADL=0, ADE=0, LPF=12, STBY=0, PWDN=0, BBG=bbg,
                    SHDN=0, CPTST=0, TURBO=1, LDMUX=0)
        for k, v in want.items():
            if d[k] != v:
                fails.append(f"LO {lo / 1e6:.6f} MHz bbg {bbg}: {k} = {d[k]}, datasheet wants {v}")
        prog = REF * (d["N"] + d["F"] / 2 ** 20)
        if abs(prog - lo) > STEP / 2 + 1e-6:
            fails.append(f"LO {lo / 1e6:.6f} MHz: the bytes program {prog / 1e6:.6f} MHz, "
                         f"{prog - lo:+.1f} Hz off (half a step is {STEP / 2:.1f} Hz)")
        if abs(prog - float(p[13])) > 1e-3:
            fails.append(f"LO {lo / 1e6:.6f} MHz: reports {float(p[13]) / 1e6:.6f} MHz but "
                         f"programs {prog / 1e6:.6f} MHz")
    #the datasheet example: F = 194,180 = 0x2F684
    lo_ex = REF * (65 + 194180 / 2 ** 20)
    p = query(host, [f"regs {lo_ex!r} {REF!r} 0"])[0].split()
    if [p[3][1], p[4], p[5]] != ["2", "f6", "84"]:
        fails.append(f"F = 194,180 packs as {p[3][1]} {p[4]} {p[5]}, the datasheet's default "
                     f"is 2 f6 84")
    #n limits
    for n, ok in ((18, False), (19, True), (251, True), (252, False)):
        rc = query(host, [f"regs {REF * n + 1000.0!r} {REF!r} 0"])[0].split()[0]
        if (rc == "0") != ok:
            fails.append(f"N = {n} {'refused' if ok else 'accepted'}; the datasheet allows 19-251")
    #every status pair
    pairs = [(s1, s2) for s1 in range(0, 256, 16) for s2 in range(256)]
    got = query(host, [f"lock {s1:x} {s2:x}" for s1, s2 in pairs])
    bad = 0
    for (s1, s2), line in zip(pairs, got):
        lk, vco, adc = (int(x) for x in line.split())
        want = (s1 & 0x60) == 0x60 and bool(s1 & 0x10) and (s2 & 7) not in (0, 7)
        if lk != int(want) or vco != s2 >> 3 or adc != s2 & 7:
            bad += 1
            if bad <= 3:
                fails.append(f"status {s1:02x} {s2:02x}: locked {lk} vco {vco} adc {adc}, "
                             f"Tables 14-15 say locked {int(want)} vco {s2 >> 3} adc {s2 & 7}")
    return fails, len(cases), len(pairs), lo_f


MUTANTS = [
    ("no carry from F into N",
     r"const double steps = floor\(lo_hz / ref_hz \* 1048576.0 \+ 0.5\);\n"
     r"    const uint32_t N = \(uint32_t\)\(steps / 1048576.0\);\n"
     r"    const uint32_t F = \(uint32_t\)\(steps - \(double\)N \* 1048576.0\);",
     "const uint32_t N = (uint32_t)(lo_hz / ref_hz);\n"
     "    const uint32_t F = (uint32_t)floor((lo_hz / ref_hz - N) * 1048576.0 + 0.5) & 0xFFFFF;"),
    ("TURBO off", r"regs\[0x0B\] = 0x08;", "regs[0x0B] = 0x00;"),
    ("CPLIN 10", r"0x10 \| \(\(F >> 16\)", "0x20 | ((F >> 16)"),
    ("ADC 111 read as locked", r" && a != 7;", ";"),
    ("D24 inverted", r"lo_hz < 1125.0e6 \? 0x80 : 0x00", "lo_hz < 1125.0e6 ? 0x00 : 0x80"),
]


def self_test():
    src = open(os.path.join(SOOP, "soop_max2112.c")).read()
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for name, pat, rep in MUTANTS:
            mut, n = re.subn(pat, lambda _m: rep, src)
            if n != 1:
                print(f"  STALE  {name}: the pattern no longer matches soop_max2112.c")
                ok = False
                continue
            open(os.path.join(tmp, "soop_max2112.c"), "w").write(mut)
            host = os.path.join(tmp, "mutant")
            built, err = build(tmp, host)
            caught = not built or bool(evaluate(host)[0])
            ok &= caught
            print(f"  {'caught' if caught else 'MISSED'}  {name}")
    return ok


def main():
    host = os.path.join(SOOP, "max2112_host")
    r = subprocess.run(["make", "-s", "max2112_host"], cwd=SOOP, capture_output=True, text=True)
    if r.returncode:
        print(f"MAX2112 CHECK FAILED - max2112_host did not build:\n{r.stderr}")
        return 1
    fails, n_lo, n_st, lo_f = evaluate(host)
    if shutil.which("arm-none-eabi-gcc"):
        r = subprocess.run(["make", "-s", "arm"], cwd=SOOP, capture_output=True, text=True)
        if r.returncode or not os.path.exists(os.path.join(SOOP, "soop_max2112.o")):
            fails.append(f"soop_max2112.c does not compile for the H743: {r.stderr.strip()[:200]}")
    else:
        fails.append("arm-none-eabi-gcc not found, so the H743 build is unproven")
    if "--self-test" in sys.argv:
        print(f"  {'clean' if not fails else 'NOT CLEAN'}  the driver as written")
        ok = not fails and self_test()
        print("self-test passed: every mutant is caught" if ok else "SELF-TEST FAILED")
        return 0 if ok else 1
    for f in fails:
        print(f"  FAIL  {f}")
    print(f"MAX2112 CHECK {'FAILED' if fails else 'PASSED'}: {len(fails)} failure(s); "
          f"{n_lo} register images and {n_st} status pairs against the datasheet; "
          f"flight LO {lo_f / 1e6:.6f} MHz")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
