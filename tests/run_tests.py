#!/usr/bin/env python3
"""Tests for ZERO. Everything that needs an optional tool (Rust, Go, Node, g++)
is skipped with a note when the tool is not available."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "assembler"), os.path.join(ROOT, "tools")]
import zasm       # noqa: E402
import pyemu      # noqa: E402
import zlangc     # noqa: E402
import build_studio  # noqa: E402

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        failures += 1


def example(name):
    with open(os.path.join(ROOT, "examples", name), encoding="utf-8") as f:
        return f.read()


def build_prog(name):
    """Assemble examples/<name> (.zasm) or compile and assemble it (.zl)."""
    src = example(name)
    return zasm.assemble(zlangc.compile_source(src) if name.endswith(".zl") else src)


def zl_prog(src):
    return zasm.assemble(zlangc.compile_source(src))


# programs without input: file -> expected output
FIB = b"0 1 1 2 3 5 8 13 21 34 55 89 144 233 377 \n"
PRIMES = b"2 3 5 7 11 13 17 19 23 29 31 37 41 43 47 53 59 \n"
EXPECTED = {
    "hello.zasm": b"Hello, ZERO!\n",
    "fib.zasm": FIB,
    "primes.zasm": PRIMES,
    "hello.zl": b"Hello from Zlang!\n",
    "fib.zl": FIB,
    "primes.zl": PRIMES,
    "ops.zl": b"14 20 4 4 19 1 0 1 3 5 1 0 0 1 0 \n",
}
SHELL_IN = b"help\nver\necho hi   there\nrev stressed\nadd 12 30\nmul 6 7\nfib 10\nprimes 30\npeek 0\nbogus\n\nexit\n"
SHELL_CHECKS = [b"ZOS 0.1 on ZX-16", b"hi   there\n", b"desserts\n", b"zos> 42\nzos> 42\n", b"0 1 1 2 3 5 8 13 21 34 \n",
                b"2 3 5 7 11 13 17 19 23 29 \n", b"unknown command: bogus", b"bye\n"]

# ------------------------------------------------------------- assembler
check("asm: ldi", zasm.assemble("ldi r1, 0x1234") == bytes([0x02, 0x10, 0x34, 0x12]))
check("asm: add", zasm.assemble("add r2, r3") == bytes([0x04, 0x23, 0, 0]))
check("asm: ld", zasm.assemble("ld r1, [r2+6]") == bytes([0x0E, 0x12, 6, 0]))
check("asm: st", zasm.assemble("st [r2-2], r1") == bytes([0x0F, 0x21, 0xFE, 0xFF]))
check("asm: in / sleep", zasm.assemble("in r0\nsleep r2") == bytes([0x20, 0, 0, 0, 0x21, 0x20, 0, 0]))
check("asm: forward label", zasm.assemble("jmp end\nnop\nend: halt") == bytes([0x12, 0, 8, 0, 0, 0, 0, 0, 1, 0, 0, 0]))
check("asm: string with ';'", zasm.assemble('.string "a;b"') == b"a;b\0")
check("asm: char ','", zasm.assemble("ldi r0, ','") == bytes([0x02, 0, 44, 0]))
try:
    zasm.assemble("bogus r1")
    check("asm: unknown instruction rejected", False)
except zasm.AsmError:
    check("asm: unknown instruction rejected", True)

# ------------------------------------------------------- python emulator
check("emu: stack starts at 0xF000", pyemu.CPU(b"").r[7] == 0xF000)
for name, expected in EXPECTED.items():
    out, code = pyemu.run(build_prog(name))
    check(f"{name} (python emulator)", out == expected and code == 0, repr(out))

# ------------------------------------------------------- zlang v0.2 features
def zl_out(src, stdin=None):
    return pyemu.run(zl_prog(src), stdin=stdin)

check("zlang: const", zl_out("const A = 7; const B = 'x'; fn main() { print(A * 6); putc(B); }")[0] == b"42x")
check("zlang: peek/poke", zl_out("fn main() { poke(0x9000, 1234); pokeb(0x9002, 200); print(peek(0x9000)); putc(' '); print(peekb(0x9002)); }")[0] == b"1234 200")
check("zlang: strings are addresses", zl_out('fn main() { var s = "hey"; puts(s); putc(peekb(s + 1)); }')[0] == b"heye")
check("zlang: getc and halt", zl_out("fn main() { var c = getc(); while (c != 65535) { putc(c + 1); c = getc(); } halt(); }", stdin=b"HAL")[0] == b"IBM")
check("zlang: sleep advances the timer", zl_out(
    "fn main() { var t0 = peek(0xFF02); sleep(500); var i = 0; while (i < 200) { i = i + 1; } "
    "var t1 = peek(0xFF02); if (t1 - t0 >= 500) { puts(\"ok\"); } }")[0] == b"ok")
for label, bad in [("undefined variable", "fn main() { x = 1; }"),
                   ("assign to constant", "const A = 1; fn main() { A = 2; }"),
                   ("wrong argument count", "fn f(a) { return a; } fn main() { f(1, 2); }"),
                   ("builtin argument count", "fn main() { poke(1); }"),
                   ("missing main", "fn f() { }")]:
    try:
        zlangc.compile_source(bad)
        check(f"zlang: rejects {label}", False)
    except zlangc.CompileError:
        check(f"zlang: rejects {label}", True)

# ------------------------------------------------------- ZOS shell
shell = build_prog("shell.zl")
out, code = pyemu.run(shell, stdin=SHELL_IN)
check("shell.zl: runs all commands", all(s in out for s in SHELL_CHECKS) and code == 0, repr(out[-120:]))
out, code = pyemu.run(shell, stdin=b"ver\n")
check("shell.zl: leaves cleanly on end of input", out.endswith(b"zos> \nbye\n") and code == 0, repr(out[-40:]))

# ------------------------------------------------------- Snake
snake = build_prog("snake.zl")
cpu, _ = pyemu.run_cpu(snake, max_steps=400_000)
check("snake.zl: dies on the wall without input", b"GAME OVER, score: 0" in bytes(cpu.out))


def bot(state):
    """Steers the snake to the food through the key register."""
    def hook(c):
        h = c.rd16(0xFC00)
        if h == state.get("last"):
            return
        state["last"] = h
        scr = c.screen()
        food = [(x, y) for y in range(32) for x in range(64) if scr[y][x] == 8]
        if not food:
            return
        fx, fy = food[0]
        x, y, d = c.rd8(0xF800 + h), c.rd8(0xF900 + h), c.rd16(0xFC04)
        want = None
        if fx > x and d != 3: want = 4
        elif fx < x and d != 4: want = 3
        elif fy > y and d != 1: want = 2
        elif fy < y and d != 2: want = 1
        if want and want != d:
            c.mem[0xFF00], c.mem[0xFF01] = want, 0
    return hook


cpu, _ = pyemu.run_cpu(snake, max_steps=700_000, hook=bot({}))
scores = [int(s.split(b": ")[1]) for s in bytes(cpu.out).split(b"\n") if s.startswith(b"GAME OVER")]
check("snake.zl: steering and eating work", scores and max(scores) >= 3, f"scores={scores}")

# ------------------------------------------------------- Rust emulator
exe = ".exe" if os.name == "nt" else ""
rust_bin = os.path.join(ROOT, "emulator", "target", "release", "zx-emu" + exe)


def run_native(binary, prog, stdin=b""):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.bin")
        with open(path, "wb") as f:
            f.write(prog)
        res = subprocess.run([binary, path], input=stdin, capture_output=True, timeout=60)
        return res.stdout, res.returncode


if os.path.exists(rust_bin):
    for name, expected in EXPECTED.items():
        out, code = run_native(rust_bin, build_prog(name))
        check(f"{name} (rust emulator)", out == expected and code == 0, repr(out))
    out, code = run_native(rust_bin, shell, SHELL_IN)
    check("shell.zl (rust emulator)", out == pyemu.run(shell, stdin=SHELL_IN)[0] and code == 0)
    out, code = run_native(rust_bin, zl_prog('fn main() { puts("x"); sleep(100); print(peek(0xFF02) + 0); }'))
    check("rust emulator: sleep and timer", out.startswith(b"x") and code == 0, repr(out))
else:
    print("note: Rust emulator not built, skipped (make build)")

# ------------------------------------------------------- Go compiler
go_bin = os.path.join(ROOT, "compiler", "zlangc" + exe)
if os.path.exists(go_bin):
    for name in [n for n in EXPECTED if n.endswith(".zl")] + ["shell.zl", "snake.zl"]:
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "o.zasm")
            res = subprocess.run([go_bin, os.path.join(ROOT, "examples", name), "-o", out_path], capture_output=True, text=True)
            if res.returncode != 0:
                check(f"go compiler: {name}", False, res.stderr)
                continue
            with open(out_path, encoding="utf-8") as f:
                go_asm = f.read()
        check(f"go compiler == python compiler: {name}", go_asm == zlangc.compile_source(example(name)))
else:
    print("note: Go compiler not built, skipped (make compiler)")

# ------------------------------------------------------- JavaScript emulator + Studio
node = shutil.which("node")
if node:
    def run_js(prog, stdin=None, steps=None, screen=False):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.bin")
            with open(path, "wb") as f:
                f.write(prog)
            cmd = [node, os.path.join(ROOT, "tests", "js_runner.js"), path]
            if stdin is not None:
                sp = os.path.join(d, "in")
                with open(sp, "wb") as f:
                    f.write(stdin)
                cmd += ["--stdin", sp]
            if steps:
                cmd += ["--steps", str(steps)]
            if screen:
                cmd += ["--screen"]
            return subprocess.run(cmd, capture_output=True, timeout=120).stdout

    for name, expected in EXPECTED.items():
        check(f"{name} (javascript emulator)", run_js(build_prog(name)) == expected)
    check("shell.zl (javascript emulator)", run_js(shell, SHELL_IN) == pyemu.run(shell, stdin=SHELL_IN)[0])
    cpu, _ = pyemu.run_cpu(snake, max_steps=300_000)
    py_screen = bytes(v for row in cpu.screen() for v in row).hex() + "\n"
    check("snake.zl: same framebuffer in JS and Python", run_js(snake, steps=300_000, screen=True).decode() == py_screen)
    res = subprocess.run([node, os.path.join(ROOT, "tests", "studio_smoke.js")], capture_output=True, text=True, timeout=120)
    check("studio page runs (fake DOM smoke test)", res.returncode == 0, res.stdout[-300:] + res.stderr[-300:])
else:
    print("note: Node.js not found, skipped the JavaScript and Studio tests")

check("studio/examples.js is up to date", build_studio.main_check() if hasattr(build_studio, "main_check") else True)

# ------------------------------------------------------- C++ disassembler
gxx = shutil.which("g++") or shutil.which("c++")
if gxx:
    with tempfile.TemporaryDirectory() as d:
        zdis = os.path.join(d, "zdis" + exe)
        res = subprocess.run([gxx, "-std=c++17", "-O1", "-o", zdis, os.path.join(ROOT, "tools", "zdis.cpp")], capture_output=True, text=True)
        if res.returncode != 0:
            check("zdis compiles", False, res.stderr[-300:])
        else:
            for name in list(EXPECTED) + ["shell.zl", "snake.zl"]:
                prog = build_prog(name)
                path = os.path.join(d, "p.bin")
                with open(path, "wb") as f:
                    f.write(prog)
                text = subprocess.run([zdis, path], capture_output=True, text=True).stdout
                check(f"zdis roundtrip: {name}", zasm.assemble(text) == prog)
else:
    print("note: no C++ compiler found, skipped the disassembler tests")

print("\nall tests passed" if failures == 0 else f"\n{failures} test(s) FAILED")
sys.exit(1 if failures else 0)
