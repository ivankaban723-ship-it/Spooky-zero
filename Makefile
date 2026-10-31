.PHONY: all build compiler disasm studio boot boot-run test run run-zl clean
PROG ?= hello

all: build compiler disasm

build:
	cargo build --release --manifest-path emulator/Cargo.toml

compiler:
	cd compiler && go build -o zlangc .

disasm:
	g++ -std=c++17 -O2 -o tools/zdis tools/zdis.cpp

studio:
	python3 tools/build_studio.py
	python3 studio/server.py --open

boot:
	nasm -f bin boot/boot.asm -o boot.img

boot-run: boot
	qemu-system-i386 -drive format=raw,file=boot.img

test:
	python3 tests/run_tests.py

run: build
	python3 assembler/zasm.py examples/$(PROG).zasm -o $(PROG).bin
	./emulator/target/release/zx-emu $(PROG).bin

run-zl: build compiler
	./compiler/zlangc examples/$(PROG).zl -o $(PROG).zasm
	python3 assembler/zasm.py $(PROG).zasm -o $(PROG).bin
	./emulator/target/release/zx-emu $(PROG).bin

clean:
	rm -rf emulator/target compiler/zlangc tools/zdis *.bin *.zasm boot.img
