.PHONY: build compiler test run run-zl clean
PROG ?= hello

build:
	cargo build --release --manifest-path emulator/Cargo.toml

compiler:
	cd compiler && go build -o zlangc .

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
	rm -rf emulator/target compiler/zlangc *.bin
