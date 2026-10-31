#!/usr/bin/env node
// Runs a ZX-16 binary with studio/zx.js.
// usage: js_runner.js prog.bin [--stdin FILE] [--steps N] [--screen]
const fs = require('fs');
const path = require('path');
const { CPU } = require(path.join(__dirname, '..', 'studio', 'zx.js'));

const args = process.argv.slice(2);
let file = null, stdinFile = null, maxSteps = 10000000, dumpScreen = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--stdin') stdinFile = args[++i];
  else if (args[i] === '--steps') maxSteps = parseInt(args[++i], 10);
  else if (args[i] === '--screen') dumpScreen = true;
  else file = args[i];
}
const cpu = new CPU(fs.readFileSync(file));
cpu.eof = true;
if (stdinFile) cpu.inq = Array.from(fs.readFileSync(stdinFile));
while (!cpu.halted && cpu.steps < maxSteps) cpu.step();
if (dumpScreen) process.stdout.write(Buffer.from(cpu.screen()).toString('hex') + '\n');
else process.stdout.write(Buffer.from(cpu.out));
if (cpu.error) { process.stderr.write('error: ' + cpu.error + '\n'); process.exit(1); }
