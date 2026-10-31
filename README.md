<div align="center">

# ZERO

### a computer from scratch: our own CPU, and every layer on top of it

[![CI](https://github.com/ivankaban723-ship-it/Spooky-zero/actions/workflows/ci.yml/badge.svg)](https://github.com/ivankaban723-ship-it/Spooky-zero/actions/workflows/ci.yml)
![languages](https://img.shields.io/badge/Rust%20%C2%B7%20Go%20%C2%B7%20Python%20%C2%B7%20C%2B%2B%20%C2%B7%20JavaScript%20%C2%B7%20NASM-7c5cff)
![license](https://img.shields.io/badge/license-MIT-00e5ff)

</div>

ZERO invents a tiny 16-bit CPU, **ZX-16**, and then builds everything above it:
an assembler, a C-like programming language, a game, an operating system shell,
a disassembler, emulators in three languages and a browser IDE with a live debugger.
Each part is written in the language that fits it best.

<!-- Add a screenshot: save the Studio as docs/studio.png and uncomment the next line
![ZERO Studio](docs/studio.png)
-->

```
                        ┌─────────────────────────────────────────────┐
   Zlang  (.zl) ───────►│ compiler  Go · Python                       │──┐
                        └─────────────────────────────────────────────┘  │ .zasm
   ZX-16 asm (.zasm) ───────────────────────────────────────────────────►│
                        ┌─────────────────────────────────────────────┐  ▼
                        │ assembler  Python                           │ .bin
                        └─────────────────────────────────────────────┘  │
        ┌────────────────────────┬─────────────────────┬─────────────────┴──┐
        ▼                        ▼                     ▼                    ▼
  emulator Rust           emulator Python      emulator JavaScript   disassembler C++
  (terminal, fast)        (reference/tests)    (ZERO Studio: screen,  (zdis, round-trips
                                                keys, live debugger)   back to .zasm)

   bonus: boot/boot.asm - a real x86 boot sector in NASM (runs in QEMU)
```

## What is inside

| Part | Language | What it does |
|---|---|---|
| **ZX-16 CPU** ([spec](spec/ZX16.md)) | - | 8 registers, 34 instructions, 64 KiB, screen 64x32 in 16 colours, keys, timer |
| **Assembler** `assembler/zasm.py` | Python | labels, expressions, `.string`, `.byte`, `.word`, `.equ`, `.org` |
| **Zlang compiler** `compiler/` ([spec](spec/Zlang.md)) | Go | functions, recursion, loops, constants, `peek`/`poke`, strings |
| Same compiler `tools/zlangc.py` | Python | identical output, used by the Studio and the tests |
| **Emulator** `emulator/` | Rust | fast terminal emulator with `--trace`, `--screen`, `--realtime` |
| Reference emulator `tools/pyemu.py` | Python | the executable specification |
| **ZERO Studio** `studio/` | JavaScript + Python | browser IDE: editor, 64x32 screen, console, registers, memory, disassembly, stepping |
| **Disassembler** `tools/zdis.cpp` | C++ | binary -> assembly that assembles back to the same bytes |
| **Boot sector** `boot/boot.asm` | NASM (x86) | a real-mode boot sector, bootable in QEMU |
| **Snake** `examples/snake.zl` | Zlang | a game for the 64x32 screen (arrows or WASD) |
| **ZOS** `examples/shell.zl` | Zlang | a tiny OS shell: `help`, `echo`, `rev`, `add`, `mul`, `fib`, `primes`, `peek`, `exit` |

## Quick start

### 1. The Studio (easiest, only needs Python 3)

```bash
python3 studio/server.py --open
```

Pick **Snake** or **ZOS shell** in the drop-down and press **Run** (Ctrl+Enter).
Play with the arrow keys, type commands into the console, press **Step** to execute one
instruction at a time and watch the registers, flags, stack and disassembly change.
Edit the code and press Run again: the server compiles it. The bundled examples also
work without the server if you just open `studio/index.html` in a browser.

### 2. Command line

```bash
make build compiler disasm        # needs Rust, Go and a C++ compiler (all optional)

python3 assembler/zasm.py examples/hello.zasm -o hello.bin
./emulator/target/release/zx-emu hello.bin          # or: python3 tools/pyemu.py hello.bin

make run-zl PROG=fib              # Zlang -> assembly -> binary -> run
make run-zl PROG=shell            # the ZOS shell, type 'help'
```

Disassemble anything: `./tools/zdis -l hello.bin`.
Boot sector: `make boot-run` (needs `nasm` and `qemu-system-i386`).

## Zlang

```
const SCREEN = 0xF000;

fn fib(n) {
    if (n < 2) { return n; }
    return fib(n - 1) + fib(n - 2);
}

fn main() {
    var i = 0;
    while (i < 10) {
        print(fib(i));
        putc(' ');
        pokeb(SCREEN + i, 8 + i);    // a pixel of a different colour for each number
        i = i + 1;
    }
    putc('\n');
}
```

## ZOS

```
ZOS 0.1 - a tiny operating system for the ZX-16
Type 'help'.
zos> add 12 30
42
zos> rev stressed
desserts
zos> primes 30
2 3 5 7 11 13 17 19 23 29
zos> exit
bye
```

## Tests

```bash
python3 tests/run_tests.py       # or: make test
```

The suite checks the assembler, all emulators against each other (even the exact Snake
framebuffer), the Go compiler against the Python one, the Studio page with a fake DOM
and the disassembler round trip. Tests that need Rust, Go, Node.js or g++ are skipped
when the tool is missing. CI runs everything on every push.

## Repository layout

```
spec/         ZX-16 and Zlang specifications
assembler/    zasm.py
compiler/     zlangc (Go)
emulator/     zx-emu (Rust)
studio/       ZERO Studio: index.html, zx.js (emulator), server.py
tools/        pyemu.py, zlangc.py, zdis.cpp, build_studio.py
boot/         x86 boot sector (NASM)
examples/     .zasm and .zl programs
tests/        test runner, Node helpers
```

## Roadmap

- [x] CPU, assembler, emulators, compiler
- [x] screen, keyboard, timer, Snake
- [x] Studio, disassembler, ZOS shell, boot sector
- [ ] interrupts and a multitasking ZOS
- [ ] sound
- [ ] globals, arrays and `for` in Zlang
- [ ] publish the Studio on GitHub Pages

## License

MIT
