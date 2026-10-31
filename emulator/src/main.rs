//! zx-emu: emulator for the ZX-16 CPU (part of the ZERO project, spec v0.2).
//!
//! Usage: zx-emu program.bin [--trace] [--max-steps N] [--screen] [--realtime]

use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::process;
use std::thread;
use std::time::Duration;

const MEM_SIZE: usize = 65536;
const STACK_TOP: u16 = 0xF000;
const SCREEN_BASE: usize = 0xF000;
const SCREEN_W: usize = 64;
const SCREEN_H: usize = 32;
const TIMER_ADDR: u16 = 0xFF02;

// PICO-8 palette
const PALETTE: [(u8, u8, u8); 16] = [
    (0x00, 0x00, 0x00), (0x1D, 0x2B, 0x53), (0x7E, 0x25, 0x53), (0x00, 0x87, 0x51),
    (0xAB, 0x52, 0x36), (0x5F, 0x57, 0x4F), (0xC2, 0xC3, 0xC7), (0xFF, 0xF1, 0xE8),
    (0xFF, 0x00, 0x4D), (0xFF, 0xA3, 0x00), (0xFF, 0xEC, 0x27), (0x00, 0xE4, 0x36),
    (0x29, 0xAD, 0xFF), (0x83, 0x76, 0x9C), (0xFF, 0x77, 0xA8), (0xFF, 0xCC, 0xAA),
];

struct Cpu {
    mem: Vec<u8>,
    r: [u16; 8],
    pc: u16,
    z: bool,
    n: bool,
    c: bool,
    v: bool,
    halted: bool,
    steps: u64,
    vtime: u64, // virtual milliseconds added by SLEEP
    realtime: bool,
}

impl Cpu {
    fn new(program: &[u8], realtime: bool) -> Cpu {
        let mut mem = vec![0u8; MEM_SIZE];
        mem[..program.len()].copy_from_slice(program);
        let mut r = [0u16; 8];
        r[7] = STACK_TOP;
        Cpu {
            mem,
            r,
            pc: 0,
            z: false,
            n: false,
            c: false,
            v: false,
            halted: false,
            steps: 0,
            vtime: 0,
            realtime,
        }
    }

    // ---- memory (16-bit little-endian words, addresses wrap around) ----
    fn rd8(&self, a: u16) -> u8 {
        self.mem[a as usize]
    }

    fn rd16(&self, a: u16) -> u16 {
        let lo = self.mem[a as usize] as u16;
        let hi = self.mem[a.wrapping_add(1) as usize] as u16;
        lo | (hi << 8)
    }

    fn wr8(&mut self, a: u16, v: u8) {
        self.mem[a as usize] = v;
    }

    fn wr16(&mut self, a: u16, v: u16) {
        self.mem[a as usize] = (v & 0xFF) as u8;
        self.mem[a.wrapping_add(1) as usize] = (v >> 8) as u8;
    }

    // ---- ALU helpers that also update the flags ----
    fn logic(&mut self, res: u16) -> u16 {
        self.z = res == 0;
        self.n = (res & 0x8000) != 0;
        self.c = false;
        self.v = false;
        res
    }

    fn add(&mut self, a: u16, b: u16) -> u16 {
        let full = a as u32 + b as u32;
        let r = (full & 0xFFFF) as u16;
        self.z = r == 0;
        self.n = (r & 0x8000) != 0;
        self.c = full > 0xFFFF;
        self.v = ((!(a ^ b)) & (a ^ r) & 0x8000) != 0;
        r
    }

    fn sub(&mut self, a: u16, b: u16) -> u16 {
        let r = a.wrapping_sub(b);
        self.z = r == 0;
        self.n = (r & 0x8000) != 0;
        self.c = a < b;
        self.v = ((a ^ b) & (a ^ r) & 0x8000) != 0;
        r
    }

    // ---- stack (r7 is the stack pointer, grows downwards) ----
    fn push(&mut self, v: u16) {
        let sp = self.r[7].wrapping_sub(2);
        self.r[7] = sp;
        self.wr16(sp, v);
    }

    fn pop(&mut self) -> u16 {
        let sp = self.r[7];
        let v = self.rd16(sp);
        self.r[7] = sp.wrapping_add(2);
        v
    }

    fn timer(&self) -> u16 {
        (((self.steps / 1000) + self.vtime) & 0xFFFF) as u16
    }

    fn trace(&self) {
        let mut regs = String::new();
        for (i, v) in self.r.iter().enumerate() {
            regs.push_str(&format!("r{}={:04x} ", i, v));
        }
        let flag = |on: bool, ch: char| if on { ch } else { '-' };
        eprintln!(
            "{:04x}: op={:02x} {}[{}{}{}{}]",
            self.pc,
            self.rd8(self.pc),
            regs,
            flag(self.z, 'Z'),
            flag(self.n, 'N'),
            flag(self.c, 'C'),
            flag(self.v, 'V')
        );
    }

    /// Execute one instruction.
    fn step(&mut self, out: &mut dyn Write, inp: &mut dyn Read) -> Result<(), String> {
        if (self.steps & 63) == 0 {
            let t = self.timer();
            self.wr16(TIMER_ADDR, t);
        }
        let pc = self.pc;
        let op = self.rd8(pc);
        let ab = self.rd8(pc.wrapping_add(1));
        let imm = self.rd16(pc.wrapping_add(2));
        let a = ((ab >> 4) & 7) as usize;
        let b = (ab & 7) as usize;
        let mut next = pc.wrapping_add(4);

        match op {
            0x00 => {} // NOP
            0x01 => self.halted = true, // HALT
            0x02 => self.r[a] = imm, // LDI
            0x03 => self.r[a] = self.r[b], // MOV
            0x04 => {
                let (x, y) = (self.r[a], self.r[b]);
                let res = self.add(x, y);
                self.r[a] = res;
            }
            0x05 => {
                let (x, y) = (self.r[a], self.r[b]);
                let res = self.sub(x, y);
                self.r[a] = res;
            }
            0x06 => {
                let res = self.r[a] & self.r[b];
                self.r[a] = self.logic(res);
            }
            0x07 => {
                let res = self.r[a] | self.r[b];
                self.r[a] = self.logic(res);
            }
            0x08 => {
                let res = self.r[a] ^ self.r[b];
                self.r[a] = self.logic(res);
            }
            0x09 => {
                let sh = (self.r[b] & 15) as u32;
                let res = self.r[a].wrapping_shl(sh);
                self.r[a] = self.logic(res);
            }
            0x0A => {
                let sh = (self.r[b] & 15) as u32;
                let res = self.r[a].wrapping_shr(sh);
                self.r[a] = self.logic(res);
            }
            0x0B => {
                let x = self.r[a];
                let res = self.add(x, imm);
                self.r[a] = res;
            }
            0x0C => {
                let (x, y) = (self.r[a], self.r[b]);
                self.sub(x, y); // CMP: flags only
            }
            0x0D => {
                let x = self.r[a];
                self.sub(x, imm); // CMPI: flags only
            }
            0x0E => {
                let addr = self.r[b].wrapping_add(imm);
                self.r[a] = self.rd16(addr); // LD
            }
            0x0F => {
                let addr = self.r[a].wrapping_add(imm);
                let val = self.r[b];
                self.wr16(addr, val); // ST
            }
            0x10 => {
                let addr = self.r[b].wrapping_add(imm);
                self.r[a] = self.rd8(addr) as u16; // LDB
            }
            0x11 => {
                let addr = self.r[a].wrapping_add(imm);
                let val = (self.r[b] & 0xFF) as u8;
                self.wr8(addr, val); // STB
            }
            0x12 => next = imm, // JMP
            0x13 => {
                if self.z {
                    next = imm; // JZ
                }
            }
            0x14 => {
                if !self.z {
                    next = imm; // JNZ
                }
            }
            0x15 => {
                if self.n != self.v {
                    next = imm; // JLT (signed)
                }
            }
            0x16 => {
                if self.n == self.v {
                    next = imm; // JGE (signed)
                }
            }
            0x17 => {
                self.push(next); // CALL
                next = imm;
            }
            0x18 => next = self.pop(), // RET
            0x19 => {
                let val = self.r[a];
                self.push(val); // PUSH
            }
            0x1A => {
                let val = self.pop();
                self.r[a] = val; // POP
            }
            0x1B => {
                let byte = (self.r[a] & 0xFF) as u8;
                out.write_all(&[byte]).map_err(|e| e.to_string())?; // OUT
            }
            0x1C => {
                let res = self.r[a].wrapping_mul(self.r[b]);
                self.r[a] = self.logic(res); // MUL
            }
            0x1D | 0x1E => {
                let (x, y) = (self.r[a], self.r[b]);
                if y == 0 {
                    return Err(format!("division by zero at 0x{:04x}", pc));
                }
                let res = if op == 0x1D { x / y } else { x % y };
                self.r[a] = self.logic(res); // DIV / MOD
            }
            0x1F => {
                let text = self.r[a].to_string();
                out.write_all(text.as_bytes()).map_err(|e| e.to_string())?; // OUTN
            }
            0x20 => {
                // IN: blocking read of one byte, 0xFFFF when the input is closed
                out.flush().map_err(|e| e.to_string())?;
                let mut byte = [0u8; 1];
                self.r[a] = match inp.read(&mut byte) {
                    Ok(1) => byte[0] as u16,
                    _ => 0xFFFF,
                };
            }
            0x21 => {
                // SLEEP: advances the timer, really sleeps only with --realtime
                let ms = self.r[a];
                self.vtime += ms as u64;
                if self.realtime {
                    out.flush().map_err(|e| e.to_string())?;
                    thread::sleep(Duration::from_millis(ms as u64));
                }
            }
            _ => return Err(format!("illegal opcode 0x{:02x} at 0x{:04x}", op, pc)),
        }

        self.pc = next;
        self.steps += 1;
        Ok(())
    }

    /// The framebuffer drawn with ANSI 24-bit colours (two pixel rows per text row).
    fn render_screen(&self) -> String {
        let mut s = String::new();
        let mut y = 0;
        while y < SCREEN_H {
            for x in 0..SCREEN_W {
                let top = PALETTE[(self.mem[SCREEN_BASE + y * SCREEN_W + x] & 15) as usize];
                let bot = PALETTE[(self.mem[SCREEN_BASE + (y + 1) * SCREEN_W + x] & 15) as usize];
                s.push_str(&format!(
                    "\x1b[38;2;{};{};{}m\x1b[48;2;{};{};{}m\u{2580}",
                    top.0, top.1, top.2, bot.0, bot.1, bot.2
                ));
            }
            s.push_str("\x1b[0m\n");
            y += 2;
        }
        s
    }
}

fn usage() {
    eprintln!("usage: zx-emu <program.bin> [--trace] [--max-steps N] [--screen] [--realtime]");
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let mut path: Option<String> = None;
    let mut trace = false;
    let mut screen = false;
    let mut realtime = false;
    let mut max_steps: u64 = 100_000_000;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "-t" | "--trace" => trace = true,
            "--screen" => screen = true,
            "--realtime" => realtime = true,
            "--max-steps" => {
                i += 1;
                max_steps = match args.get(i).and_then(|s| s.parse::<u64>().ok()) {
                    Some(n) => n,
                    None => {
                        eprintln!("--max-steps needs a number");
                        process::exit(64);
                    }
                };
            }
            "-h" | "--help" => {
                usage();
                return;
            }
            other => path = Some(other.to_string()),
        }
        i += 1;
    }

    let path = match path {
        Some(p) => p,
        None => {
            usage();
            process::exit(64);
        }
    };

    let program = match fs::read(&path) {
        Ok(data) => data,
        Err(e) => {
            eprintln!("cannot read {}: {}", path, e);
            process::exit(66);
        }
    };
    if program.len() > MEM_SIZE {
        eprintln!("program is larger than 64 KiB");
        process::exit(65);
    }

    let mut cpu = Cpu::new(&program, realtime);
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    let mut stdin = io::stdin();
    let mut code = 0;

    while !cpu.halted {
        if cpu.steps >= max_steps {
            let _ = out.flush();
            eprintln!("error: step limit ({}) reached", max_steps);
            code = 3;
            break;
        }
        if trace {
            cpu.trace();
        }
        if let Err(e) = cpu.step(&mut out, &mut stdin) {
            let _ = out.flush();
            eprintln!("error: {}", e);
            code = 1;
            break;
        }
    }

    let _ = out.flush();
    drop(out);
    if screen {
        print!("{}", cpu.render_screen());
    }
    process::exit(code);
}
