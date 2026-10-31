#!/usr/bin/env python3
"""Reference ZX-16 emulator in Python (spec v0.2).

Slow, but handy for testing and for running ZERO without a Rust toolchain.
Usage: python3 pyemu.py program.bin [--trace] [--max-steps N] [--screen] [--realtime]
"""
import argparse
import sys
import time

STACK_TOP = 0xF000
SCREEN_BASE, SCREEN_W, SCREEN_H = 0xF000, 64, 32
KEY_ADDR, TIMER_ADDR = 0xFF00, 0xFF02

PALETTE = [
    (0x00, 0x00, 0x00), (0x1D, 0x2B, 0x53), (0x7E, 0x25, 0x53), (0x00, 0x87, 0x51),
    (0xAB, 0x52, 0x36), (0x5F, 0x57, 0x4F), (0xC2, 0xC3, 0xC7), (0xFF, 0xF1, 0xE8),
    (0xFF, 0x00, 0x4D), (0xFF, 0xA3, 0x00), (0xFF, 0xEC, 0x27), (0x00, 0xE4, 0x36),
    (0x29, 0xAD, 0xFF), (0x83, 0x76, 0x9C), (0xFF, 0x77, 0xA8), (0xFF, 0xCC, 0xAA),
]


class CpuError(Exception):
    pass


class CPU:
    def __init__(self, program, stdin=None, sink=None, realtime=False):
        if len(program) > 65536:
            raise CpuError("program is larger than 64 KiB")
        self.mem = bytearray(65536)
        self.mem[: len(program)] = program
        self.r = [0] * 8
        self.r[7] = STACK_TOP
        self.pc = 0
        self.z = self.n = self.c = self.v = False
        self.halted = False
        self.steps = 0
        self.vtime = 0          # virtual milliseconds added by SLEEP
        self.realtime = realtime
        self.out = bytearray()
        self.sink = sink
        if callable(stdin):
            self.read_byte = stdin
        else:
            it = iter(stdin or b"")
            self.read_byte = lambda: next(it, None)

    def emit(self, data):
        self.out += data
        if self.sink:
            self.sink(data)

    # memory
    def rd8(self, a):
        return self.mem[a & 0xFFFF]

    def rd16(self, a):
        return self.mem[a & 0xFFFF] | (self.mem[(a + 1) & 0xFFFF] << 8)

    def wr8(self, a, v):
        self.mem[a & 0xFFFF] = v & 0xFF

    def wr16(self, a, v):
        self.mem[a & 0xFFFF] = v & 0xFF
        self.mem[(a + 1) & 0xFFFF] = (v >> 8) & 0xFF

    # flags / ALU
    def logic(self, res):
        self.z, self.n, self.c, self.v = res == 0, bool(res & 0x8000), False, False
        return res

    def add(self, a, b):
        full = a + b
        r = full & 0xFFFF
        self.z, self.n, self.c = r == 0, bool(r & 0x8000), full > 0xFFFF
        self.v = bool((~(a ^ b)) & (a ^ r) & 0x8000)
        return r

    def sub(self, a, b):
        r = (a - b) & 0xFFFF
        self.z, self.n, self.c = r == 0, bool(r & 0x8000), a < b
        self.v = bool((a ^ b) & (a ^ r) & 0x8000)
        return r

    def push(self, v):
        self.r[7] = (self.r[7] - 2) & 0xFFFF
        self.wr16(self.r[7], v)

    def pop(self):
        v = self.rd16(self.r[7])
        self.r[7] = (self.r[7] + 2) & 0xFFFF
        return v

    def timer(self):
        return ((self.steps // 1000) + self.vtime) & 0xFFFF

    def step(self):
        if (self.steps & 63) == 0:
            self.wr16(TIMER_ADDR, self.timer())
        pc = self.pc
        op = self.rd8(pc)
        ab = self.rd8(pc + 1)
        imm = self.rd16(pc + 2)
        a, b = (ab >> 4) & 7, ab & 7
        r = self.r
        nxt = (pc + 4) & 0xFFFF

        if op == 0x00:
            pass
        elif op == 0x01:
            self.halted = True
        elif op == 0x02:
            r[a] = imm
        elif op == 0x03:
            r[a] = r[b]
        elif op == 0x04:
            r[a] = self.add(r[a], r[b])
        elif op == 0x05:
            r[a] = self.sub(r[a], r[b])
        elif op == 0x06:
            r[a] = self.logic(r[a] & r[b])
        elif op == 0x07:
            r[a] = self.logic(r[a] | r[b])
        elif op == 0x08:
            r[a] = self.logic(r[a] ^ r[b])
        elif op == 0x09:
            r[a] = self.logic((r[a] << (r[b] & 15)) & 0xFFFF)
        elif op == 0x0A:
            r[a] = self.logic(r[a] >> (r[b] & 15))
        elif op == 0x0B:
            r[a] = self.add(r[a], imm)
        elif op == 0x0C:
            self.sub(r[a], r[b])
        elif op == 0x0D:
            self.sub(r[a], imm)
        elif op == 0x0E:
            r[a] = self.rd16((r[b] + imm) & 0xFFFF)
        elif op == 0x0F:
            self.wr16((r[a] + imm) & 0xFFFF, r[b])
        elif op == 0x10:
            r[a] = self.rd8((r[b] + imm) & 0xFFFF)
        elif op == 0x11:
            self.wr8((r[a] + imm) & 0xFFFF, r[b])
        elif op == 0x12:
            nxt = imm
        elif op == 0x13:
            if self.z:
                nxt = imm
        elif op == 0x14:
            if not self.z:
                nxt = imm
        elif op == 0x15:
            if self.n != self.v:
                nxt = imm
        elif op == 0x16:
            if self.n == self.v:
                nxt = imm
        elif op == 0x17:
            self.push(nxt)
            nxt = imm
        elif op == 0x18:
            nxt = self.pop()
        elif op == 0x19:
            self.push(r[a])
        elif op == 0x1A:
            r[a] = self.pop()
        elif op == 0x1B:
            self.emit(bytes([r[a] & 0xFF]))
        elif op == 0x1C:
            r[a] = self.logic((r[a] * r[b]) & 0xFFFF)
        elif op in (0x1D, 0x1E):
            if r[b] == 0:
                raise CpuError(f"division by zero at 0x{pc:04x}")
            r[a] = self.logic(r[a] // r[b] if op == 0x1D else r[a] % r[b])
        elif op == 0x1F:
            self.emit(str(r[a]).encode())
        elif op == 0x20:
            byte = self.read_byte()
            r[a] = 0xFFFF if byte is None else byte
        elif op == 0x21:
            self.vtime += r[a]
            if self.realtime:
                time.sleep(r[a] / 1000.0)
        else:
            raise CpuError(f"illegal opcode 0x{op:02x} at 0x{pc:04x}")
        self.pc = nxt
        self.steps += 1

    def trace_line(self):
        regs = " ".join(f"r{i}={v:04x}" for i, v in enumerate(self.r))
        fl = "".join(c if f else "-" for c, f in zip("ZNCV", (self.z, self.n, self.c, self.v)))
        return f"{self.pc:04x}: op={self.rd8(self.pc):02x} {regs} [{fl}]"

    def screen(self):
        """The 64x32 framebuffer as a list of rows of colour indexes."""
        return [[self.mem[SCREEN_BASE + y * SCREEN_W + x] & 15 for x in range(SCREEN_W)]
                for y in range(SCREEN_H)]


def render_screen(cpu):
    """Draw the framebuffer with ANSI 24-bit colours (two pixel rows per text row)."""
    rows = cpu.screen()
    lines = []
    for y in range(0, SCREEN_H, 2):
        parts = []
        for x in range(SCREEN_W):
            t, b = PALETTE[rows[y][x]], PALETTE[rows[y + 1][x]]
            parts.append("\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm\u2580" % (t + b))
        lines.append("".join(parts) + "\x1b[0m")
    return "\n".join(lines)


def run_cpu(program, max_steps=10_000_000, trace=False, stdin=None, hook=None, sink=None, realtime=False):
    """Run a program. Returns (cpu, exit_code). `hook(cpu)` is called before every step."""
    cpu = CPU(program, stdin=stdin, sink=sink, realtime=realtime)
    code = 0
    while not cpu.halted:
        if cpu.steps >= max_steps:
            print(f"error: step limit ({max_steps}) reached", file=sys.stderr)
            code = 3
            break
        if hook:
            hook(cpu)
        if trace:
            print(cpu.trace_line(), file=sys.stderr)
        try:
            cpu.step()
        except CpuError as e:
            print(f"error: {e}", file=sys.stderr)
            code = 1
            break
    return cpu, code


def run(program, max_steps=10_000_000, trace=False, stdin=None):
    """Run a program. Returns (output_bytes, exit_code)."""
    cpu, code = run_cpu(program, max_steps, trace, stdin)
    return bytes(cpu.out), code


def main():
    ap = argparse.ArgumentParser(description="ZX-16 reference emulator (Python)")
    ap.add_argument("program")
    ap.add_argument("-t", "--trace", action="store_true")
    ap.add_argument("--max-steps", type=int, default=10_000_000)
    ap.add_argument("--screen", action="store_true", help="draw the framebuffer at exit")
    ap.add_argument("--realtime", action="store_true", help="really sleep on SLEEP")
    args = ap.parse_args()
    with open(args.program, "rb") as f:
        prog = f.read()

    def read_byte():
        sys.stdout.buffer.flush()
        b = sys.stdin.buffer.read(1)
        return b[0] if b else None

    cpu, code = run_cpu(prog, args.max_steps, args.trace, stdin=read_byte,
                        sink=sys.stdout.buffer.write, realtime=args.realtime)
    sys.stdout.buffer.flush()
    if args.screen:
        print(render_screen(cpu))
    return code


if __name__ == "__main__":
    sys.exit(main())
