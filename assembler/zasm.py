#!/usr/bin/env python3
"""zasm - assembler for the ZX-16 CPU (part of the ZERO project).

Usage:  python3 zasm.py program.zasm -o program.bin
"""
import argparse
import re
import sys

MEM_SIZE = 65536


class AsmError(Exception):
    pass


# mnemonic -> (opcode, operand form)
OPS = {
    "nop": (0x00, "none"), "halt": (0x01, "none"),
    "ldi": (0x02, "ri"), "mov": (0x03, "rr"),
    "add": (0x04, "rr"), "sub": (0x05, "rr"),
    "and": (0x06, "rr"), "or": (0x07, "rr"), "xor": (0x08, "rr"),
    "shl": (0x09, "rr"), "shr": (0x0A, "rr"),
    "addi": (0x0B, "ri"), "cmp": (0x0C, "rr"), "cmpi": (0x0D, "ri"),
    "ld": (0x0E, "load"), "st": (0x0F, "store"),
    "ldb": (0x10, "load"), "stb": (0x11, "store"),
    "jmp": (0x12, "i"), "jz": (0x13, "i"), "jnz": (0x14, "i"),
    "jlt": (0x15, "i"), "jge": (0x16, "i"),
    "call": (0x17, "i"), "ret": (0x18, "none"),
    "push": (0x19, "r"), "pop": (0x1A, "r"),
    "out": (0x1B, "r"),
    "mul": (0x1C, "rr"), "div": (0x1D, "rr"), "mod": (0x1E, "rr"),
    "outn": (0x1F, "r"),
}
ALIASES = {"je": "jz", "jne": "jnz"}
OPERAND_COUNT = {"none": 0, "r": 1, "i": 1, "rr": 2, "ri": 2, "load": 2, "store": 2}

REGS = {f"r{i}": i for i in range(8)}
REGS["sp"] = 7

ESCAPES = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, "'": 39, '"': 34}

TOKEN = re.compile(
    r"\s*([+-]?)\s*('(?:\\.|[^'\\])'|0[xX][0-9a-fA-F]+|0[bB][01]+|\d+|[A-Za-z_]\w*)"
)
MEM = re.compile(r"^\[\s*([A-Za-z]\w*)\s*(?:([+-])\s*(.+?))?\s*\]$")
LABEL = re.compile(r"^([A-Za-z_]\w*)\s*:\s*(.*)$")


def strip_comment(line):
    out, quote, i = [], None, 0
    while i < len(line):
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        else:
            if ch == ";":
                break
            if ch in "\"'":
                quote = ch
            out.append(ch)
        i += 1
    return "".join(out).strip()


def split_operands(s):
    parts, cur, quote, depth, i = [], [], None, 0, 0
    while i < len(s):
        ch = s[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and i + 1 < len(s):
                cur.append(s[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch == "[":
            depth += 1
            cur.append(ch)
        elif ch == "]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    last = "".join(cur).strip()
    if last or parts:
        parts.append(last)
    return parts


def decode_chars(body, lineno):
    out, i = [], 0
    while i < len(body):
        ch = body[i]
        if ch == "\\":
            i += 1
            if i >= len(body) or body[i] not in ESCAPES:
                raise AsmError(f"line {lineno}: bad escape sequence")
            out.append(ESCAPES[body[i]])
        else:
            out.extend(ch.encode("utf-8"))
        i += 1
    return bytes(out)


def parse_string(text, lineno):
    text = text.strip()
    if len(text) < 2 or text[0] != '"' or text[-1] != '"':
        raise AsmError(f"line {lineno}: expected a string in double quotes")
    return decode_chars(text[1:-1], lineno)


def eval_expr(text, symbols, lineno):
    text = text.strip()
    pos, total, first = 0, 0, True
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or (not first and not m.group(1)):
            raise AsmError(f"line {lineno}: bad expression '{text}'")
        sign = -1 if m.group(1) == "-" else 1
        tok = m.group(2)
        if tok[0] == "'":
            data = decode_chars(tok[1:-1], lineno)
            if len(data) != 1:
                raise AsmError(f"line {lineno}: bad character literal {tok}")
            val = data[0]
        elif tok[0].isdigit():
            val = int(tok, 0) if tok[:2].lower() in ("0x", "0b") else int(tok, 10)
        else:
            if tok not in symbols:
                raise AsmError(f"line {lineno}: unknown symbol '{tok}'")
            val = symbols[tok]
        total += sign * val
        pos = m.end()
        first = False
    if first:
        raise AsmError(f"line {lineno}: empty expression")
    return total


def check16(value, lineno):
    if not -32768 <= value <= 65535:
        raise AsmError(f"line {lineno}: value {value} does not fit in 16 bits")
    return value & 0xFFFF


def reg(tok, lineno):
    t = tok.strip().lower()
    if t not in REGS:
        raise AsmError(f"line {lineno}: expected register (r0-r7), got '{tok}'")
    return REGS[t]


def parse_mem(tok, symbols, lineno):
    m = MEM.match(tok.strip())
    if not m:
        raise AsmError(f"line {lineno}: expected memory operand like [r1+4], got '{tok}'")
    base = reg(m.group(1), lineno)
    imm = 0
    if m.group(2):
        imm = eval_expr(m.group(3), symbols, lineno)
        if m.group(2) == "-":
            imm = -imm
    return base, imm


def encode(mn, ops, symbols, lineno):
    opcode, form = OPS[mn]
    if len(ops) != OPERAND_COUNT[form]:
        raise AsmError(f"line {lineno}: '{mn}' expects {OPERAND_COUNT[form]} operand(s), got {len(ops)}")
    a = b = imm = 0
    if form == "r":
        a = reg(ops[0], lineno)
    elif form == "i":
        imm = eval_expr(ops[0], symbols, lineno)
    elif form == "rr":
        a, b = reg(ops[0], lineno), reg(ops[1], lineno)
    elif form == "ri":
        a, imm = reg(ops[0], lineno), eval_expr(ops[1], symbols, lineno)
    elif form == "load":
        a = reg(ops[0], lineno)
        b, imm = parse_mem(ops[1], symbols, lineno)
    elif form == "store":
        a, imm = parse_mem(ops[0], symbols, lineno)
        b = reg(ops[1], lineno)
    imm = check16(imm, lineno)
    return bytes([opcode, (a << 4) | b, imm & 0xFF, imm >> 8])


def assemble(source):
    """Assemble source text into a bytes object (flat memory image, origin 0)."""
    symbols, items, pc = {}, [], 0

    # ---- pass 1: sizes and labels ----
    for lineno, raw in enumerate(source.splitlines(), 1):
        line = strip_comment(raw)
        while True:
            m = LABEL.match(line)
            if not m:
                break
            name, line = m.group(1), m.group(2).strip()
            if name in symbols:
                raise AsmError(f"line {lineno}: duplicate symbol '{name}'")
            symbols[name] = pc
        if not line:
            continue
        parts = line.split(None, 1)
        mn = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if mn.startswith("."):
            if mn == ".equ":
                ops = split_operands(rest)
                if len(ops) != 2:
                    raise AsmError(f"line {lineno}: .equ NAME, value")
                if ops[0] in symbols:
                    raise AsmError(f"line {lineno}: duplicate symbol '{ops[0]}'")
                symbols[ops[0]] = eval_expr(ops[1], symbols, lineno)
            elif mn == ".org":
                target = eval_expr(rest, symbols, lineno)
                if target < pc:
                    raise AsmError(f"line {lineno}: .org moves backwards")
                items.append((lineno, "raw", bytes(target - pc)))
                pc = target
            elif mn == ".space":
                n = eval_expr(rest, symbols, lineno)
                if n < 0:
                    raise AsmError(f"line {lineno}: negative .space")
                items.append((lineno, "raw", bytes(n)))
                pc += n
            elif mn in (".byte", ".word"):
                ops = split_operands(rest)
                items.append((lineno, mn, ops))
                pc += len(ops) * (1 if mn == ".byte" else 2)
            elif mn in (".string", ".ascii"):
                data = parse_string(rest, lineno)
                if mn == ".string":
                    data += b"\0"
                items.append((lineno, "raw", data))
                pc += len(data)
            else:
                raise AsmError(f"line {lineno}: unknown directive '{mn}'")
        else:
            mn = ALIASES.get(mn, mn)
            if mn not in OPS:
                raise AsmError(f"line {lineno}: unknown instruction '{mn}'")
            items.append((lineno, "ins", (mn, split_operands(rest))))
            pc += 4
        if pc > MEM_SIZE:
            raise AsmError(f"line {lineno}: program is larger than 64 KiB")

    # ---- pass 2: emit ----
    out = bytearray()
    for lineno, kind, payload in items:
        if kind == "raw":
            out += payload
        elif kind == "ins":
            out += encode(payload[0], payload[1], symbols, lineno)
        elif kind == ".byte":
            for op in payload:
                v = eval_expr(op, symbols, lineno)
                if not -128 <= v <= 255:
                    raise AsmError(f"line {lineno}: value {v} does not fit in a byte")
                out.append(v & 0xFF)
        elif kind == ".word":
            for op in payload:
                v = check16(eval_expr(op, symbols, lineno), lineno)
                out += bytes([v & 0xFF, v >> 8])
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description="ZX-16 assembler")
    ap.add_argument("input", help="source file (.zasm)")
    ap.add_argument("-o", "--output", help="output binary (default: input with .bin)")
    args = ap.parse_args()
    try:
        with open(args.input, encoding="utf-8") as f:
            data = assemble(f.read())
    except AsmError as e:
        print(f"{args.input}: error: {e}", file=sys.stderr)
        return 1
    out = args.output or re.sub(r"\.[^./\\]+$", "", args.input) + ".bin"
    with open(out, "wb") as f:
        f.write(data)
    print(f"{args.input} -> {out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
