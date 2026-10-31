// zlangc: compiler for Zlang, a tiny C-like language for the ZX-16 CPU.
//
// Usage: zlangc program.zl [-o program.zasm]
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func usage() {
	fmt.Fprintln(os.Stderr, "usage: zlangc <program.zl> [-o output.zasm]")
}

func die(msg string) {
	fmt.Fprintln(os.Stderr, "error: "+msg)
	os.Exit(1)
}

func main() {
	args := os.Args[1:]
	var in, out string
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "-o":
			i++
			if i >= len(args) {
				die("-o needs a file name")
			}
			out = args[i]
		case "-h", "--help":
			usage()
			return
		default:
			if in != "" {
				die("only one input file is supported")
			}
			in = args[i]
		}
	}
	if in == "" {
		usage()
		os.Exit(64)
	}

	src, err := os.ReadFile(in)
	if err != nil {
		die(err.Error())
	}
	toks, err := Lex(string(src))
	if err != nil {
		die(in + ": " + err.Error())
	}
	funcs, err := Parse(toks)
	if err != nil {
		die(in + ": " + err.Error())
	}
	asm, err := Generate(funcs)
	if err != nil {
		die(in + ": " + err.Error())
	}

	if out == "" {
		out = strings.TrimSuffix(in, filepath.Ext(in)) + ".zasm"
	}
	if err := os.WriteFile(out, []byte(asm), 0o644); err != nil {
		die(err.Error())
	}
	fmt.Printf("%s -> %s\n", in, out)
}
