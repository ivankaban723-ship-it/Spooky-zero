# ZERO - a computer from scratch

ZERO is a "build the whole stack" project: we invent our own CPU (**ZX-16**, a 16-bit RISC)
and then write every layer on top of it, each in the language that fits it best.

```
 .zasm source ──► assembler (Python) ──► program.bin ──► emulator (Rust) ──► output
                                                  ▲
        Zlang source ──► compiler (Go) ───────────┘
```

## Status

| Component | Language | Status |
|---|---|---|
| ISA specification (`spec/ZX16.md`) | Markdown | done (v0.1) |
| Emulator (`emulator/`) | Rust | done (console I/O) |
| Reference emulator (`tools/pyemu.py`) | Python | done, used by tests |
| Assembler (`assembler/zasm.py`) | Python | done |
| Examples (`examples/`) | ZX-16 assembly | hello, fib, primes |
| Compiler for Zlang (`compiler/`, [`spec/Zlang.md`](spec/Zlang.md)) | Go | done (v0.1) |
| Tiny OS / firmware | assembly + C | planned |
| x86 bootloader demo | NASM | planned |
| Web debugger | Python + JS | planned |

## Quick start

You need Python 3.8+ and, optionally, Rust (https://rustup.rs).

```bash
# 1. assemble an example
python3 assembler/zasm.py examples/hello.zasm -o hello.bin

# 2a. run it with the Rust emulator
cargo run --release --manifest-path emulator/Cargo.toml -- hello.bin

# 2b. ...or without Rust, with the Python emulator
python3 tools/pyemu.py hello.bin
```

Expected output: `Hello, ZERO!`

Handy flags: `--trace` prints every executed instruction to stderr,
`--max-steps N` stops runaway programs.

Run the tests: `python3 tests/run_tests.py` (also tests the Rust emulator if it is built).

With `make`: `make build`, `make compiler`, `make test`, `make run PROG=fib`, `make run-zl PROG=fib`.

## Zlang: write programs in a C-like language

Needs Go (https://go.dev/dl/ or `sudo dnf install golang`).

```bash
cd compiler && go build -o zlangc . && cd ..
./compiler/zlangc examples/fib.zl -o fib.zasm
python3 assembler/zasm.py fib.zasm -o fib.bin
./emulator/target/release/zx-emu fib.bin
```

Or just: `make run-zl PROG=fib`. Language reference: [`spec/Zlang.md`](spec/Zlang.md).

## Write your own program in assembly

```asm
    ldi  r0, 'A'
    out  r0
    ldi  r0, '\n'
    out  r0
    halt
```

Save it as `my.zasm`, then `python3 assembler/zasm.py my.zasm` and run `my.bin`.
Full instruction list and syntax: [`spec/ZX16.md`](spec/ZX16.md).

## Repository layout

```
spec/        CPU and language specifications
assembler/   zasm.py - assembler
compiler/    zlangc - Zlang compiler (Go)
emulator/    Rust emulator (cargo project)
tools/       Python reference emulator
examples/    programs: .zasm (assembly) and .zl (Zlang)
tests/       test runner
```

## License

MIT
