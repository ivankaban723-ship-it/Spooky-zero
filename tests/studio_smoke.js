#!/usr/bin/env node
// Smoke test for studio/index.html: runs the page script in Node with a fake DOM,
// loads the ZOS shell, types a command and checks what the console shows.
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..', 'studio');

const elements = {};
const listeners = {};
function fakeEl(id) {
  const store = { value: '', textContent: '', innerHTML: '', style: {}, dataset: {}, children: [], scrollTop: 0, scrollHeight: 0 };
  const classes = new Set();
  const handler = {
    get(t, p) {
      if (p in store) return store[p];
      if (p === 'classList') return { add: (c) => classes.add(c), remove: (c) => classes.delete(c), toggle: (c, on) => (on === undefined ? (classes.has(c) ? classes.delete(c) : classes.add(c)) : on ? classes.add(c) : classes.delete(c)), contains: (c) => classes.has(c) };
      if (p === 'addEventListener') return (ev, fn) => { (listeners[id + ':' + ev] = listeners[id + ':' + ev] || []).push(fn); };
      if (p === 'querySelector') return () => fakeEl('sub');
      if (p === 'getContext') return () => ({ createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }), putImageData: () => { store.frames = (store.frames || 0) + 1; } });
      if (p === 'frames') return store.frames || 0;
      if (p === 'tagName') return 'DIV';
      return () => {};
    },
    set(t, p, v) { store[p] = v; return true; },
  };
  return new Proxy({}, handler);
}
globalThis.document = {
  getElementById: (id) => (elements[id] = elements[id] || fakeEl(id)),
  createElement: () => fakeEl('opt'),
  querySelectorAll: () => [],
  activeElement: null,
};
globalThis.window = globalThis;
globalThis.addEventListener = () => {};
let frameCb = null;
globalThis.requestAnimationFrame = (cb) => { frameCb = cb; };
globalThis.ZX = require(path.join(root, 'zx.js'));
eval(fs.readFileSync(path.join(root, 'examples.js'), 'utf8'));

const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const m = html.match(/<script>\s*'use strict';([\s\S]*?)<\/script>/);
if (!m) { console.error('FAIL: page script not found'); process.exit(1); }
new Function("'use strict';" + m[1])();

elements.speed = elements.speed || document.getElementById('speed');
elements.speed.value = '100';   // maximum speed
let failures = 0;
function check(name, ok) { console.log((ok ? 'PASS ' : 'FAIL ') + name); if (!ok) failures++; }
const frames = (n) => { for (let i = 0; i < n; i++) frameCb(); };

check('examples are listed', window.EXAMPLES.length >= 9);
// pick the ZOS shell and run it
elements.examples.onchange({ target: { value: String(window.EXAMPLES.findIndex((e) => e.id === 'shell.zl')) } });
elements.btnRun.onclick();
setTimeout(() => {
  frames(30);
  check('shell prints its prompt', elements.console.textContent.includes('zos> '));
  elements.conin.value = 'ver';
  (listeners['conform:submit'] || []).forEach((fn) => fn({ preventDefault() {} }));
  frames(30);
  check('shell answers "ver"', elements.console.textContent.includes('ZOS 0.1 on ZX-16'));
  elements.conin.value = 'add 40 2';
  (listeners['conform:submit'] || []).forEach((fn) => fn({ preventDefault() {} }));
  frames(30);
  check('shell computes "add 40 2"', /\n42\n/.test(elements.console.textContent));
  check('status shows waiting for input', elements.status.textContent === 'WAITING FOR INPUT');

  // snake: run a while, the canvas must have been drawn
  elements.examples.onchange({ target: { value: '0' } });
  elements.btnRun.onclick();
  setTimeout(() => {
    frames(60);
    check('snake prints its banner', elements.console.textContent.includes('SNAKE'));
    check('status is RUNNING', elements.status.textContent === 'RUNNING');
    console.log(failures ? failures + ' check(s) FAILED' : 'studio smoke test passed');
    process.exit(failures ? 1 : 0);
  }, 20);
}, 20);
