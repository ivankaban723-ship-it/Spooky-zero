#!/usr/bin/env python3
"""ZERO Studio server: serves the web UI and builds programs for it.

  python3 studio/server.py [--port 8000] [--open]

It only listens on 127.0.0.1. Standard library only.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "assembler"), os.path.join(ROOT, "tools")]
import zasm      # noqa: E402
import zlangc    # noqa: E402

GO_COMPILER = os.path.join(ROOT, "compiler", "zlangc")
MAX_BODY = 256 * 1024


def compile_zlang(source):
    """Returns (asm_text, compiler_name). Uses the Go compiler when it is built."""
    if os.path.isfile(GO_COMPILER) and os.access(GO_COMPILER, os.X_OK):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "p.zl"), os.path.join(d, "p.zasm")
            with open(src, "w", encoding="utf-8") as f:
                f.write(source)
            res = subprocess.run([GO_COMPILER, src, "-o", out], capture_output=True, text=True, timeout=20)
            if res.returncode != 0:
                msg = res.stderr.strip().replace("error: ", "", 1).replace(src + ": ", "")
                raise zlangc.CompileError(msg)
            with open(out, encoding="utf-8") as f:
                return f.read(), "Go (zlangc)"
    return zlangc.compile_source(source), "Python (zlangc.py)"


def build(lang, source):
    if lang == "zl":
        asm, compiler = compile_zlang(source)
    elif lang == "zasm":
        asm, compiler = source, "zasm"
    else:
        raise ValueError("unknown language")
    binary = zasm.assemble(asm)
    return {"ok": True, "bin": base64.b64encode(binary).decode("ascii"), "size": len(binary),
            "asm": asm if lang == "zl" else "", "compiler": compiler}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, obj, status=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/api/build":
            self.send_json({"ok": False, "error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY:
                self.send_json({"ok": False, "error": "source is too large"}, 413)
                return
            req = json.loads(self.rfile.read(length).decode("utf-8"))
            self.send_json(build(req.get("lang", ""), req.get("source", "")))
        except (zlangc.CompileError, zasm.AsmError) as e:
            self.send_json({"ok": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001 - report any build problem to the page
            self.send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 400)


def main():
    ap = argparse.ArgumentParser(description="ZERO Studio server")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"ZERO Studio is running at {url}  (Ctrl+C to stop)")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
