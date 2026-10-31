#!/usr/bin/env python3
"""Tests for ZERO: assembler encoding + example programs on every available emulator."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "assembler"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import zasm   # noqa: E402
import pyemu  # noqa: E402

EXPECTED = {
    "hello": b"Hello, ZERO!\n",
    "fib": b"0 1 1 2 3 5 8 13 21 34 55 89 144 233 377 \n",
    "primes": b"2 3 5 7 11 13 17 19 23 29 31 37 41 43 47 53 59 \n",
}

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        failures += 1


# --- assembler unit tests ---
check("encode ldi", zasm.assemble("ldi r1, 0x1234") == bytes([0x02, 0x10, 0x34, 0x12]))
check("encode add", zasm.assemble("add r2, r3") == bytes([0x04, 0x23, 0, 0]))
check("encode ld", zasm.assemble("ld r1, [r2+6]") == bytes([0x0E, 0x12, 6, 0]))
check("encode st", zasm.assemble("st [r2-2], r1") == bytes([0x0F, 0x21, 0xFE, 0xFF]))
check("label forward", zasm.assemble("jmp end\nnop\nend: halt") == bytes([0x12, 0, 8, 0, 0, 0, 0, 0, 1, 0, 0, 0]))
check("string", zasm.assemble('.string "a;b"') == b"a;b\0")
check("char comma", zasm.assemble("ldi r0, ','") == bytes([0x02, 0, 44, 0]))
try:
    zasm.assemble("bogus r1")
    check("unknown instruction rejected", False)
except zasm.AsmError:
    check("unknown instruction rejected", True)

# --- example programs ---
rust_bin = os.path.join(ROOT, "emulator", "target", "release", "zx-emu")
if os.name == "nt":
    rust_bin += ".exe"

for name, expected in EXPECTED.items():
    with open(os.path.join(ROOT, "examples", name + ".zasm"), encoding="utf-8") as f:
        prog = zasm.assemble(f.read())
    out, code = pyemu.run(prog)
    check(f"{name} (python emulator)", out == expected and code == 0, repr(out))

    if os.path.exists(rust_bin):
        path = os.path.join(ROOT, f"_test_{name}.bin")
        with open(path, "wb") as f:
            f.write(prog)
        res = subprocess.run([rust_bin, path], capture_output=True)
        os.remove(path)
        check(f"{name} (rust emulator)", res.stdout == expected and res.returncode == 0, repr(res.stdout))

if not os.path.exists(rust_bin):
    print("note: Rust emulator not built, skipped (run `make build`)")

# --- Zlang compiler (needs the Go binary: `make compiler`) ---
EXPECTED_ZL = {
    "hello": b"Hello from Zlang!\n",
    "fib": EXPECTED["fib"],
    "primes": EXPECTED["primes"],
    "ops": b"14 20 4 4 19 1 0 1 3 5 1 0 0 1 0 \n",
}
zlangc = os.path.join(ROOT, "compiler", "zlangc")
if os.name == "nt":
    zlangc += ".exe"

if os.path.exists(zlangc):
    for name, expected in EXPECTED_ZL.items():
        src = os.path.join(ROOT, "examples", name + ".zl")
        asm_path = os.path.join(ROOT, f"_test_{name}.zasm")
        res = subprocess.run([zlangc, src, "-o", asm_path], capture_output=True, text=True)
        if res.returncode != 0:
            check(f"{name}.zl compiles", False, res.stderr)
            continue
        with open(asm_path, encoding="utf-8") as f:
            prog = zasm.assemble(f.read())
        os.remove(asm_path)
        out, code = pyemu.run(prog)
        check(f"{name}.zl (python emulator)", out == expected and code == 0, repr(out))
        if os.path.exists(rust_bin):
            path = os.path.join(ROOT, f"_test_{name}.bin")
            with open(path, "wb") as f:
                f.write(prog)
            res = subprocess.run([rust_bin, path], capture_output=True)
            os.remove(path)
            check(f"{name}.zl (rust emulator)", res.stdout == expected and res.returncode == 0, repr(res.stdout))
else:
    print("note: Zlang compiler not built, skipped (run `make compiler`)")


print("\nall tests passed" if failures == 0 else f"\n{failures} test(s) FAILED")
sys.exit(1 if failures else 0)
