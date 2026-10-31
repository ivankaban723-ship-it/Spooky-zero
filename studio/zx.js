/* zx.js - ZX-16 emulator and disassembler in JavaScript (spec v0.2).
 * Works in the browser (global `ZX`) and in Node.js (`require('./zx.js')`). */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ZX = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const SCREEN_BASE = 0xF000, SCREEN_W = 64, SCREEN_H = 32;
  const KEY_ADDR = 0xFF00, TIMER_ADDR = 0xFF02, STACK_TOP = 0xF000;

  // PICO-8 palette
  const PALETTE = [
    '#000000', '#1D2B53', '#7E2553', '#008751', '#AB5236', '#5F574F', '#C2C3C7', '#FFF1E8',
    '#FF004D', '#FFA300', '#FFEC27', '#00E436', '#29ADFF', '#83769C', '#FF77A8', '#FFCCAA',
  ];

  // opcode -> [mnemonic, operand form]
  const OPS = [
    ['nop', 'none'], ['halt', 'none'], ['ldi', 'ri'], ['mov', 'rr'], ['add', 'rr'], ['sub', 'rr'],
    ['and', 'rr'], ['or', 'rr'], ['xor', 'rr'], ['shl', 'rr'], ['shr', 'rr'], ['addi', 'ri'],
    ['cmp', 'rr'], ['cmpi', 'ri'], ['ld', 'load'], ['st', 'store'],
    ['ldb', 'load'], ['stb', 'store'], ['jmp', 'i'], ['jz', 'i'], ['jnz', 'i'], ['jlt', 'i'],
    ['jge', 'i'], ['call', 'i'], ['ret', 'none'], ['push', 'r'], ['pop', 'r'], ['out', 'r'],
    ['mul', 'rr'], ['div', 'rr'], ['mod', 'rr'], ['outn', 'r'], ['in', 'r'], ['sleep', 'r'],
  ];

  const hex4 = (v) => '0x' + v.toString(16).padStart(4, '0');
  const hex2 = (v) => '0x' + v.toString(16).padStart(2, '0');
  const signed = (v) => (v >= 0x8000 ? v - 0x10000 : v);

  /** Disassemble the instruction at `addr`. Returns { text, bytes: [b0..b3] }. */
  function disasm(mem, addr) {
    const b = [0, 1, 2, 3].map((i) => mem[(addr + i) & 0xFFFF]);
    const op = b[0], ab = b[1], imm = b[2] | (b[3] << 8);
    const a = ab >> 4, bb = ab & 15;
    const raw = '.byte ' + b.map(hex2).join(', ');
    if (op >= OPS.length) return { text: raw, bytes: b };
    const [mn, form] = OPS[op];
    const usesA = form !== 'none' && form !== 'i';
    const usesB = form === 'rr' || form === 'load' || form === 'store';
    const usesImm = form === 'ri' || form === 'i' || form === 'load' || form === 'store';
    if (a > 7 || bb > 7 || (!usesA && a) || (!usesB && bb) || (!usesImm && imm)) return { text: raw, bytes: b };
    const mem_ = (reg, off) => '[r' + reg + (off === 0 ? '' : (signed(off) < 0 ? '-' : '+') + Math.abs(signed(off))) + ']';
    let text;
    switch (form) {
      case 'none': text = mn; break;
      case 'r': text = mn + ' r' + a; break;
      case 'rr': text = mn + ' r' + a + ', r' + bb; break;
      case 'ri': text = mn + ' r' + a + ', ' + (mn === 'ldi' ? (imm >= 256 ? hex4(imm) : imm) : signed(imm)); break;
      case 'i': text = mn + ' ' + hex4(imm); break;
      case 'load': text = mn + ' r' + a + ', ' + mem_(bb, imm); break;
      default: text = mn + ' ' + mem_(a, imm) + ', r' + bb; break;
    }
    return { text, bytes: b };
  }

  class CPU {
    constructor(program) {
      this.mem = new Uint8Array(65536);
      this.load(program);
    }

    load(program) {
      this.mem.fill(0);
      this.mem.set(program.subarray ? program : Uint8Array.from(program));
      this.r = new Uint16Array(8);
      this.r[7] = STACK_TOP;
      this.pc = 0;
      this.z = this.n = this.c = this.v = false;
      this.halted = false;
      this.waiting = false;    // blocked in IN, waiting for a key
      this.error = null;
      this.steps = 0;
      this.vtime = 0;          // virtual ms added by SLEEP
      this.sleepRequest = 0;   // ms requested by the last SLEEP (host consumes it)
      this.hostTimer = null;   // when not null the host supplies the timer value
      this.eof = false;        // when true IN returns 0xFFFF instead of waiting
      this.inq = [];
      this.out = [];
      this.onOut = null;
    }

    rd8(a) { return this.mem[a & 0xFFFF]; }
    rd16(a) { return this.mem[a & 0xFFFF] | (this.mem[(a + 1) & 0xFFFF] << 8); }
    wr8(a, v) { this.mem[a & 0xFFFF] = v & 0xFF; }
    wr16(a, v) { this.mem[a & 0xFFFF] = v & 0xFF; this.mem[(a + 1) & 0xFFFF] = (v >> 8) & 0xFF; }

    logic(res) { this.z = res === 0; this.n = (res & 0x8000) !== 0; this.c = false; this.v = false; return res; }
    add(a, b) {
      const full = a + b, r = full & 0xFFFF;
      this.z = r === 0; this.n = (r & 0x8000) !== 0; this.c = full > 0xFFFF;
      this.v = ((~(a ^ b)) & (a ^ r) & 0x8000) !== 0;
      return r;
    }
    sub(a, b) {
      const r = (a - b) & 0xFFFF;
      this.z = r === 0; this.n = (r & 0x8000) !== 0; this.c = a < b;
      this.v = ((a ^ b) & (a ^ r) & 0x8000) !== 0;
      return r;
    }
    push(v) { this.r[7] = (this.r[7] - 2) & 0xFFFF; this.wr16(this.r[7], v); }
    pop() { const v = this.rd16(this.r[7]); this.r[7] = (this.r[7] + 2) & 0xFFFF; return v; }
    emit(byte) { this.out.push(byte); if (this.onOut) this.onOut(byte); }
    timer() {
      if (this.hostTimer !== null) return this.hostTimer & 0xFFFF;
      return (Math.floor(this.steps / 1000) + this.vtime) & 0xFFFF;
    }
    fail(msg) { this.error = msg; this.halted = true; }

    /** Execute one instruction. */
    step() {
      if ((this.steps & 63) === 0) this.wr16(TIMER_ADDR, this.timer());
      const mem = this.mem, r = this.r, pc = this.pc;
      const op = mem[pc], ab = mem[(pc + 1) & 0xFFFF];
      const imm = mem[(pc + 2) & 0xFFFF] | (mem[(pc + 3) & 0xFFFF] << 8);
      const a = (ab >> 4) & 7, b = ab & 7;
      let next = (pc + 4) & 0xFFFF;

      switch (op) {
        case 0x00: break;
        case 0x01: this.halted = true; break;
        case 0x02: r[a] = imm; break;
        case 0x03: r[a] = r[b]; break;
        case 0x04: r[a] = this.add(r[a], r[b]); break;
        case 0x05: r[a] = this.sub(r[a], r[b]); break;
        case 0x06: r[a] = this.logic(r[a] & r[b]); break;
        case 0x07: r[a] = this.logic(r[a] | r[b]); break;
        case 0x08: r[a] = this.logic(r[a] ^ r[b]); break;
        case 0x09: r[a] = this.logic((r[a] << (r[b] & 15)) & 0xFFFF); break;
        case 0x0A: r[a] = this.logic(r[a] >> (r[b] & 15)); break;
        case 0x0B: r[a] = this.add(r[a], imm); break;
        case 0x0C: this.sub(r[a], r[b]); break;
        case 0x0D: this.sub(r[a], imm); break;
        case 0x0E: r[a] = this.rd16(r[b] + imm); break;
        case 0x0F: this.wr16(r[a] + imm, r[b]); break;
        case 0x10: r[a] = this.rd8(r[b] + imm); break;
        case 0x11: this.wr8(r[a] + imm, r[b]); break;
        case 0x12: next = imm; break;
        case 0x13: if (this.z) next = imm; break;
        case 0x14: if (!this.z) next = imm; break;
        case 0x15: if (this.n !== this.v) next = imm; break;
        case 0x16: if (this.n === this.v) next = imm; break;
        case 0x17: this.push(next); next = imm; break;
        case 0x18: next = this.pop(); break;
        case 0x19: this.push(r[a]); break;
        case 0x1A: r[a] = this.pop(); break;
        case 0x1B: this.emit(r[a] & 0xFF); break;
        case 0x1C: r[a] = this.logic(Math.imul(r[a], r[b]) & 0xFFFF); break;
        case 0x1D:
        case 0x1E:
          if (r[b] === 0) { this.fail('division by zero at ' + hex4(pc)); return; }
          r[a] = this.logic(op === 0x1D ? Math.floor(r[a] / r[b]) : r[a] % r[b]);
          break;
        case 0x1F: for (const ch of String(r[a])) this.emit(ch.charCodeAt(0)); break;
        case 0x20:
          if (this.inq.length > 0) { r[a] = this.inq.shift(); this.waiting = false; }
          else if (this.eof) { r[a] = 0xFFFF; }
          else { this.waiting = true; return; }   // stay on this instruction
          break;
        case 0x21: this.vtime += r[a]; this.sleepRequest = r[a]; break;
        default: this.fail('illegal opcode ' + hex2(op) + ' at ' + hex4(pc)); return;
      }
      this.pc = next;
      this.steps++;
    }

    /** Run up to `max` instructions; stops early on halt, input wait or a SLEEP. */
    run(max) {
      const start = this.steps;
      this.sleepRequest = 0;
      while (!this.halted && this.steps - start < max) {
        this.step();
        if (this.waiting || this.sleepRequest) break;
      }
      return this.steps - start;
    }

    /** The framebuffer as an array of 64*32 colour indexes. */
    screen() {
      const out = new Uint8Array(SCREEN_W * SCREEN_H);
      for (let i = 0; i < out.length; i++) out[i] = this.mem[SCREEN_BASE + i] & 15;
      return out;
    }
  }

  return { CPU, disasm, OPS, PALETTE, SCREEN_BASE, SCREEN_W, SCREEN_H, KEY_ADDR, TIMER_ADDR, STACK_TOP };
});
