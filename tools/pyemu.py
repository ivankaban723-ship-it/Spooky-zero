#!/usr/bin/env python3
"""Reference ZX-16 emulator in Python (same behaviour as the Rust one).

Slow, but handy for testing and for running ZERO without a Rust toolchain.
Usage: python3 pyemu.py program.bin [--trace] [--max-steps N]
"""
import argparse
import sys


class CpuError(Exception):
    pass


class CPU:
    def __init__(self, program):
        if len(program) > 65536:
            raise CpuError("program is larger than 64 KiB")
        self.mem = bytearray(65536)
        self.mem[: len(program)] = program
        self.r = [0] * 8
        self.pc = 0
        self.z = self.n = self.c = self.v = False
        self.halted = False
        self.steps = 0
        self.out = bytearray()

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

    def step(self):
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
            self.out.append(r[a] & 0xFF)
        elif op == 0x1C:
            r[a] = self.logic((r[a] * r[b]) & 0xFFFF)
        elif op in (0x1D, 0x1E):
            if r[b] == 0:
                raise CpuError(f"division by zero at 0x{pc:04x}")
            r[a] = self.logic(r[a] // r[b] if op == 0x1D else r[a] % r[b])
        elif op == 0x1F:
            self.out += str(r[a]).encode()
        else:
            raise CpuError(f"illegal opcode 0x{op:02x} at 0x{pc:04x}")
        self.pc = nxt
        self.steps += 1

    def trace_line(self):
        regs = " ".join(f"r{i}={v:04x}" for i, v in enumerate(self.r))
        fl = "".join(c if f else "-" for c, f in zip("ZNCV", (self.z, self.n, self.c, self.v)))
        return f"{self.pc:04x}: op={self.rd8(self.pc):02x} {regs} [{fl}]"


def run(program, max_steps=10_000_000, trace=False):
    """Run a program. Returns (output_bytes, exit_code)."""
    cpu = CPU(program)
    code = 0
    while not cpu.halted:
        if cpu.steps >= max_steps:
            print(f"error: step limit ({max_steps}) reached", file=sys.stderr)
            code = 3
            break
        if trace:
            print(cpu.trace_line(), file=sys.stderr)
        try:
            cpu.step()
        except CpuError as e:
            print(f"error: {e}", file=sys.stderr)
            code = 1
            break
    return bytes(cpu.out), code


def main():
    ap = argparse.ArgumentParser(description="ZX-16 reference emulator (Python)")
    ap.add_argument("program")
    ap.add_argument("-t", "--trace", action="store_true")
    ap.add_argument("--max-steps", type=int, default=10_000_000)
    args = ap.parse_args()
    with open(args.program, "rb") as f:
        prog = f.read()
    out, code = run(prog, args.max_steps, args.trace)
    sys.stdout.buffer.write(out)
    sys.stdout.buffer.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
