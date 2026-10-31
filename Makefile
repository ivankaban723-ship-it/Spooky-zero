.PHONY: build test run clean
PROG ?= hello

build:
	cargo build --release --manifest-path emulator/Cargo.toml

test:
	python3 tests/run_tests.py

run: build
	python3 assembler/zasm.py examples/$(PROG).zasm -o $(PROG).bin
	./emulator/target/release/zx-emu $(PROG).bin

clean:
	rm -rf emulator/target *.bin
