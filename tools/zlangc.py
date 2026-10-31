#!/usr/bin/env python3
"""zlangc.py - Python implementation of the Zlang compiler (v0.2).

It mirrors the Go compiler in compiler/ and produces the same assembly, so the
Studio server and the tests work without a Go toolchain.

Usage: python3 zlangc.py program.zl [-o program.zasm]
"""
import os
import re
import sys
from collections import namedtuple


class CompileError(Exception):
    pass


def fail(line, msg):
    raise CompileError(f"line {line}: {msg}")


KEYWORDS = {"fn", "var", "const", "if", "else", "while", "return"}
ESCAPES = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, "'": 39, '"': 34}
# builtin name -> number of arguments
BUILTINS = {"print": 1, "putc": 1, "puts": 1, "peek": 1, "peekb": 1,
            "poke": 2, "pokeb": 2, "getc": 0, "sleep": 1, "halt": 0}

Token = namedtuple("Token", "kind text num line")  # kind: num ident kw str punct eof

TWO_CHAR = {"==", "!=", "<=", ">=", "&&", "||", "<<", ">>"}
ONE_CHAR = set("+-*/%&|^<>=!(){},;")


# ------------------------------------------------------------------ lexer
def lex(src):
    toks, line, i, n = [], 1, 0, len(src)
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "/" and src[i + 1:i + 2] == "/":
            while i < n and src[i] != "\n":
                i += 1
        elif c.isdigit():
            start = i
            is_hex = c == "0" and src[i + 1:i + 2] in ("x", "X")
            if is_hex:
                i += 2
                while i < n and src[i] in "0123456789abcdefABCDEF":
                    i += 1
            else:
                while i < n and src[i].isdigit():
                    i += 1
            text = src[start:i]
            try:
                v = int(text[2:], 16) if is_hex else int(text, 10)
            except ValueError:
                v = -1
            if v < 0 or v > 65535:
                fail(line, f'bad number "{text}" (must fit in 16 bits)')
            toks.append(Token("num", "", v, line))
        elif c == "_" or c.isalpha():
            start = i
            while i < n and (src[i] == "_" or src[i].isalnum()):
                i += 1
            word = src[start:i]
            toks.append(Token("kw" if word in KEYWORDS else "ident", word, 0, line))
        elif c == "'":
            i += 1
            if i >= n:
                fail(line, "unterminated character literal")
            ch = src[i]
            if ch == "\\":
                i += 1
                if i >= n or src[i] not in ESCAPES:
                    fail(line, "bad escape sequence")
                ch = chr(ESCAPES[src[i]])
            i += 1
            if i >= n or src[i] != "'":
                fail(line, "bad character literal")
            i += 1
            toks.append(Token("num", "", ord(ch), line))
        elif c == '"':
            i += 1
            out = bytearray()
            while True:
                if i >= n or src[i] == "\n":
                    fail(line, "unterminated string")
                ch = src[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\":
                    i += 1
                    if i >= n or src[i] not in ESCAPES:
                        fail(line, "bad escape sequence")
                    out.append(ESCAPES[src[i]])
                else:
                    out += ch.encode("utf-8")
                i += 1
            toks.append(Token("str", bytes(out), 0, line))
        else:
            if src[i:i + 2] in TWO_CHAR:
                toks.append(Token("punct", src[i:i + 2], 0, line))
                i += 2
            elif c in ONE_CHAR:
                toks.append(Token("punct", c, 0, line))
                i += 1
            else:
                fail(line, f"unexpected character '{c}'")
    toks.append(Token("eof", "", 0, line))
    return toks


# ----------------------------------------------------------------- parser
BIN_PREC = {"||": 1, "&&": 2, "|": 3, "^": 4, "&": 5, "==": 6, "!=": 6,
            "<": 7, "<=": 7, ">": 7, ">=": 7, "<<": 8, ">>": 8,
            "+": 9, "-": 9, "*": 10, "/": 10, "%": 10}


def describe(t):
    if t.kind == "eof":
        return "end of file"
    if t.kind == "num":
        return f"number {t.num}"
    if t.kind == "str":
        return f"string {t.text!r}"
    return f"'{t.text}'"


class Parser:
    def __init__(self, toks):
        self.toks, self.pos = toks, 0

    def peek(self):
        return self.toks[self.pos]

    def next(self):
        t = self.toks[self.pos]
        if t.kind != "eof":
            self.pos += 1
        return t

    def is_punct(self, s):
        t = self.peek()
        return t.kind == "punct" and t.text == s

    def is_kw(self, s):
        t = self.peek()
        return t.kind == "kw" and t.text == s

    def expect(self, s):
        t = self.peek()
        if t.kind in ("punct", "kw") and t.text == s:
            return self.next()
        fail(t.line, f"expected '{s}', found {describe(t)}")

    def parse_program(self):
        consts, funcs = [], []
        while self.peek().kind != "eof":
            if self.is_kw("const"):
                consts.append(self.parse_const())
            else:
                funcs.append(self.parse_func())
        return consts, funcs

    def parse_const(self):
        self.expect("const")
        name = self.next()
        if name.kind != "ident":
            fail(name.line, f"expected constant name, found {describe(name)}")
        self.expect("=")
        val = self.next()
        if val.kind != "num":
            fail(val.line, "a constant must be a number or a character")
        self.expect(";")
        return ("const", name.text, val.num, name.line)

    def parse_func(self):
        kw = self.expect("fn")
        name = self.next()
        if name.kind != "ident":
            fail(name.line, f"expected function name, found {describe(name)}")
        params = []
        self.expect("(")
        if not self.is_punct(")"):
            while True:
                t = self.next()
                if t.kind != "ident":
                    fail(t.line, f"expected parameter name, found {describe(t)}")
                params.append(t.text)
                if self.is_punct(","):
                    self.next()
                    continue
                break
        self.expect(")")
        return {"name": name.text, "params": params, "body": self.parse_block(), "line": kw.line}

    def parse_block(self):
        self.expect("{")
        stmts = []
        while not self.is_punct("}"):
            if self.peek().kind == "eof":
                fail(self.peek().line, "unexpected end of file, missing '}'")
            stmts.append(self.parse_stmt())
        self.expect("}")
        return stmts

    def parse_stmt(self):
        t = self.peek()
        if self.is_kw("var"):
            self.next()
            name = self.next()
            if name.kind != "ident":
                fail(name.line, f"expected variable name, found {describe(name)}")
            init = ("num", 0)
            if self.is_punct("="):
                self.next()
                init = self.parse_expr()
            self.expect(";")
            return ("var", name.text, init, name.line)
        if self.is_kw("if"):
            self.next()
            self.expect("(")
            cond = self.parse_expr()
            self.expect(")")
            then = self.parse_block()
            els = []
            if self.is_kw("else"):
                self.next()
                els = [self.parse_stmt()] if self.is_kw("if") else self.parse_block()
            return ("if", cond, then, els)
        if self.is_kw("while"):
            self.next()
            self.expect("(")
            cond = self.parse_expr()
            self.expect(")")
            return ("while", cond, self.parse_block())
        if self.is_kw("return"):
            self.next()
            val = ("num", 0)
            if not self.is_punct(";"):
                val = self.parse_expr()
            self.expect(";")
            return ("ret", val)
        nxt = self.toks[self.pos + 1]
        if t.kind == "ident" and nxt.kind == "punct" and nxt.text == "=":
            self.next()
            self.next()
            val = self.parse_expr()
            self.expect(";")
            return ("assign", t.text, val, t.line)
        x = self.parse_expr()
        self.expect(";")
        return ("expr", x)

    def parse_expr(self):
        return self.parse_binary(1)

    def parse_binary(self, min_prec):
        left = self.parse_unary()
        while True:
            t = self.peek()
            if t.kind != "punct" or t.text not in BIN_PREC or BIN_PREC[t.text] < min_prec:
                return left
            self.next()
            right = self.parse_binary(BIN_PREC[t.text] + 1)
            left = ("bin", t.text, left, right)

    def parse_unary(self):
        if self.is_punct("-") or self.is_punct("!"):
            op = self.next().text
            return ("un", op, self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        t = self.next()
        if t.kind == "num":
            return ("num", t.num)
        if t.kind == "str":
            return ("str", t.text, t.line)
        if t.kind == "ident":
            if self.is_punct("("):
                self.next()
                args = []
                if not self.is_punct(")"):
                    while True:
                        args.append(self.parse_expr())
                        if self.is_punct(","):
                            self.next()
                            continue
                        break
                self.expect(")")
                return ("call", t.text, args, t.line)
            return ("var", t.text, t.line)
        if t.kind == "punct" and t.text == "(":
            e = self.parse_expr()
            self.expect(")")
            return e
        fail(t.line, f"unexpected {describe(t)}")


# ---------------------------------------------------------------- codegen
def escape_asm(data):
    out = bytearray()
    for c in data:
        if c == 10:
            out += b"\\n"
        elif c == 9:
            out += b"\\t"
        elif c == 13:
            out += b"\\r"
        elif c == 0:
            out += b"\\0"
        elif c == 92:
            out += b"\\\\"
        elif c == 34:
            out += b'\\"'
        else:
            out.append(c)
    return out.decode("utf-8")


def count_locals(stmts):
    n = 0
    for s in stmts:
        if s[0] == "var":
            n += 1
        elif s[0] == "if":
            n += count_locals(s[2]) + count_locals(s[3])
        elif s[0] == "while":
            n += count_locals(s[2])
    return n


class Gen:
    def __init__(self, consts, funcs):
        self.lines = []
        self.label_n = 0
        self.strs = []
        self.consts = {}
        self.funcs = {}
        self.scopes = []
        self.nlocals = 0
        self.ret_label = ""
        for c in consts:
            if c[1] in self.consts:
                fail(c[3], f"constant '{c[1]}' is defined twice")
            self.consts[c[1]] = c[2]
        for f in funcs:
            if f["name"] in BUILTINS:
                fail(f["line"], f"'{f['name']}' is a built-in function and cannot be redefined")
            if f["name"] in self.funcs:
                fail(f["line"], f"function '{f['name']}' is defined twice")
            self.funcs[f["name"]] = f

    def emit(self, text):
        self.lines.append("    " + text)

    def label(self, name):
        self.lines.append(name + ":")

    def raw(self, text):
        self.lines.append(text)

    def new_label(self):
        self.label_n += 1
        return f"L{self.label_n}"

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def add_string(self, data):
        if data in self.strs:
            return self.strs.index(data)
        self.strs.append(data)
        return len(self.strs) - 1

    def generate(self, funcs):
        if "main" not in self.funcs:
            fail(1, "no 'main' function")
        if self.funcs["main"]["params"]:
            fail(self.funcs["main"]["line"], "'main' must not take parameters")
        self.raw("; generated by zlangc - do not edit")
        self.emit("call f_main")
        self.emit("halt")
        for f in funcs:
            self.gen_func(f)
        if self.strs:
            self.raw("")
        for i, s in enumerate(self.strs):
            self.label(f"str{i}")
            self.emit(f'.string "{escape_asm(s)}"')
        return "\n".join(self.lines) + "\n"

    def gen_func(self, f):
        self.ret_label = f"f_{f['name']}_ret"
        self.scopes = [{}]
        self.nlocals = 0
        n = len(f["params"])
        for i, name in enumerate(f["params"]):
            if name in self.scopes[0]:
                fail(f["line"], f"duplicate parameter '{name}' in function '{f['name']}'")
            self.scopes[0][name] = 4 + 2 * (n - 1 - i)
        total = count_locals(f["body"])
        self.raw("")
        self.label("f_" + f["name"])
        self.emit("push r6")
        self.emit("mov r6, r7")
        if total > 0:
            self.emit(f"addi r7, {-2 * total}")
        self.gen_stmts(f["body"])
        self.emit("ldi r0, 0")
        self.label(self.ret_label)
        self.emit("mov r7, r6")
        self.emit("pop r6")
        self.emit("ret")

    def gen_stmts(self, stmts):
        for s in stmts:
            self.gen_stmt(s)

    def gen_scoped(self, stmts):
        self.scopes.append({})
        self.gen_stmts(stmts)
        self.scopes.pop()

    def gen_stmt(self, s):
        kind = s[0]
        if kind == "var":
            top = self.scopes[-1]
            if s[1] in top:
                fail(s[3], f"'{s[1]}' is already declared in this scope")
            self.gen_expr(s[2])
            self.nlocals += 1
            off = -2 * self.nlocals
            top[s[1]] = off
            self.emit(f"st [r6{off:+d}], r0")
        elif kind == "assign":
            off = self.lookup(s[1])
            if off is None:
                if s[1] in self.consts:
                    fail(s[3], f"cannot assign to constant '{s[1]}'")
                fail(s[3], f"undefined variable '{s[1]}'")
            self.gen_expr(s[2])
            self.emit(f"st [r6{off:+d}], r0")
        elif kind == "if":
            else_l, end_l = self.new_label(), self.new_label()
            self.gen_expr(s[1])
            self.emit("cmpi r0, 0")
            self.emit(f"jz {else_l}")
            self.gen_scoped(s[2])
            if s[3]:
                self.emit(f"jmp {end_l}")
                self.label(else_l)
                self.gen_scoped(s[3])
                self.label(end_l)
            else:
                self.label(else_l)
        elif kind == "while":
            top_l, end_l = self.new_label(), self.new_label()
            self.label(top_l)
            self.gen_expr(s[1])
            self.emit("cmpi r0, 0")
            self.emit(f"jz {end_l}")
            self.gen_scoped(s[2])
            self.emit(f"jmp {top_l}")
            self.label(end_l)
        elif kind == "ret":
            self.gen_expr(s[1])
            self.emit(f"jmp {self.ret_label}")
        elif kind == "expr":
            self.gen_expr(s[1])
        else:
            raise AssertionError("unknown statement")

    def gen_expr(self, e):
        kind = e[0]
        if kind == "num":
            self.emit(f"ldi r0, {e[1]}")
        elif kind == "str":
            self.emit(f"ldi r0, str{self.add_string(e[1])}")
        elif kind == "var":
            off = self.lookup(e[1])
            if off is not None:
                self.emit(f"ld r0, [r6{off:+d}]")
            elif e[1] in self.consts:
                self.emit(f"ldi r0, {self.consts[e[1]]}")
            else:
                fail(e[2], f"undefined variable '{e[1]}'")
        elif kind == "un":
            self.gen_expr(e[2])
            if e[1] == "-":
                self.emit("ldi r1, 0")
                self.emit("sub r1, r0")
                self.emit("mov r0, r1")
            else:
                yes, end = self.new_label(), self.new_label()
                self.emit("cmpi r0, 0")
                self.emit(f"jz {yes}")
                self.emit("ldi r0, 0")
                self.emit(f"jmp {end}")
                self.label(yes)
                self.emit("ldi r0, 1")
                self.label(end)
        elif kind == "bin":
            self.gen_binary(e)
        elif kind == "call":
            self.gen_call(e)
        else:
            raise AssertionError("unknown expression")

    def gen_binary(self, e):
        op = e[1]
        if op in ("&&", "||"):
            short, end = self.new_label(), self.new_label()
            jump, short_val, other_val = ("jz", 0, 1) if op == "&&" else ("jnz", 1, 0)
            self.gen_expr(e[2])
            self.emit("cmpi r0, 0")
            self.emit(f"{jump} {short}")
            self.gen_expr(e[3])
            self.emit("cmpi r0, 0")
            self.emit(f"{jump} {short}")
            self.emit(f"ldi r0, {other_val}")
            self.emit(f"jmp {end}")
            self.label(short)
            self.emit(f"ldi r0, {short_val}")
            self.label(end)
            return
        self.gen_expr(e[2])
        self.emit("push r0")
        self.gen_expr(e[3])
        self.emit("mov r1, r0")
        self.emit("pop r0")
        simple = {"+": "add", "-": "sub", "*": "mul", "/": "div", "%": "mod",
                  "&": "and", "|": "or", "^": "xor", "<<": "shl", ">>": "shr"}
        compare = {"==": ("cmp r0, r1", "jz"), "!=": ("cmp r0, r1", "jnz"),
                   "<": ("cmp r0, r1", "jlt"), ">=": ("cmp r0, r1", "jge"),
                   ">": ("cmp r1, r0", "jlt"), "<=": ("cmp r1, r0", "jge")}
        if op in simple:
            self.emit(f"{simple[op]} r0, r1")
        else:
            cmp_ins, jump = compare[op]
            yes, end = self.new_label(), self.new_label()
            self.emit(cmp_ins)
            self.emit(f"{jump} {yes}")
            self.emit("ldi r0, 0")
            self.emit(f"jmp {end}")
            self.label(yes)
            self.emit("ldi r0, 1")
            self.label(end)

    def gen_call(self, c):
        name, args, line = c[1], c[2], c[3]
        if name in BUILTINS:
            if len(args) != BUILTINS[name]:
                fail(line, f"{name}() takes {BUILTINS[name]} argument(s), got {len(args)}")
            self.gen_builtin(name, args)
            return
        f = self.funcs.get(name)
        if f is None:
            fail(line, f"undefined function '{name}'")
        if len(args) != len(f["params"]):
            fail(line, f"function '{name}' takes {len(f['params'])} argument(s), got {len(args)}")
        for a in args:
            self.gen_expr(a)
            self.emit("push r0")
        self.emit(f"call f_{name}")
        if args:
            self.emit(f"addi r7, {2 * len(args)}")

    def gen_builtin(self, name, args):
        if name == "print":
            self.gen_expr(args[0])
            self.emit("outn r0")
        elif name == "putc":
            self.gen_expr(args[0])
            self.emit("out r0")
        elif name == "puts":
            loop, end = self.new_label(), self.new_label()
            self.gen_expr(args[0])
            self.emit("mov r1, r0")
            self.label(loop)
            self.emit("ldb r0, [r1]")
            self.emit("cmpi r0, 0")
            self.emit(f"jz {end}")
            self.emit("out r0")
            self.emit("addi r1, 1")
            self.emit(f"jmp {loop}")
            self.label(end)
        elif name in ("peek", "peekb"):
            self.gen_expr(args[0])
            self.emit("mov r1, r0")
            self.emit("ld r0, [r1]" if name == "peek" else "ldb r0, [r1]")
        elif name in ("poke", "pokeb"):
            self.gen_expr(args[0])
            self.emit("push r0")
            self.gen_expr(args[1])
            self.emit("pop r1")
            self.emit("st [r1], r0" if name == "poke" else "stb [r1], r0")
        elif name == "getc":
            self.emit("in r0")
        elif name == "sleep":
            self.gen_expr(args[0])
            self.emit("sleep r0")
        elif name == "halt":
            self.emit("halt")


def compile_source(src):
    """Compile Zlang source text to ZX-16 assembly text."""
    consts, funcs = Parser(lex(src)).parse_program()
    return Gen(consts, funcs).generate(funcs)


def main():
    args = sys.argv[1:]
    inp = out = None
    i = 0
    while i < len(args):
        if args[i] == "-o" and i + 1 < len(args):
            out = args[i + 1]
            i += 2
        elif args[i] in ("-h", "--help"):
            print("usage: zlangc.py <program.zl> [-o output.zasm]")
            return 0
        else:
            inp = args[i]
            i += 1
    if not inp:
        print("usage: zlangc.py <program.zl> [-o output.zasm]", file=sys.stderr)
        return 64
    try:
        with open(inp, encoding="utf-8") as f:
            asm = compile_source(f.read())
    except CompileError as e:
        print(f"error: {inp}: {e}", file=sys.stderr)
        return 1
    out = out or re.sub(r"\.[^./\\]+$", "", inp) + ".zasm"
    with open(out, "w", encoding="utf-8") as f:
        f.write(asm)
    print(f"{inp} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
