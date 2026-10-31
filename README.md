# ZERO - a computer from scratch

ZERO is a "build the whole stack" project: we invent our own CPU (**ZX-16**, a 16-bit RISC)
and then write every layer on top of it, each in the language that fits it best.

```
 .zasm source ──► assembler (Python) ──► program.bin ──► emulator (Rust) ──► output
                                                  ▲
        Zlang source ──► compiler (Go, planned) ──┘
```

## Status

| Component | Language | Status |
|---|---|---|
| ISA specification (`spec/ZX16.md`) | Markdown | done (v0.1) |
| Emulator (`emulator/`) | Rust | done (console I/O) |
| Reference emulator (`tools/pyemu.py`) | Python | done, used by tests |
| Assembler (`assembler/zasm.py`) | Python | done |
| Examples (`examples/`) | ZX-16 assembly | hello, fib, primes |
| Compiler for Zlang | Go | planned |
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

With `make`: `make build`, `make test`, `make run PROG=fib`.

## Write your own program

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
spec/        CPU specification
assembler/   zasm.py - assembler
emulator/    Rust emulator (cargo project)
tools/       Python reference emulator
examples/    programs for ZX-16
tests/       test runner
```

## License

MIT
