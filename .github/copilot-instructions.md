# Prim coding instructions

Read [project knowledge](../docs/PROJECT_KNOWLEDGE.md) and
[decisions](../docs/DECISIONS.md) for architecture, requirements and rationale.
[RTL documentation](../rtl/README.md) describes signal and simulation details.

Detailed code flow: [Code documentation](../docs/CODE.md). Test entry points
and coverage: [Test documentation](../docs/TESTS.md).

## Scope and architecture

Active implementations are `rtl/` (Verilog) and `src/prim/` (Python).
The alternative Amaranth implementation under `hdl/` is outside the current
scope; its dependencies remain optional.

- `src/prim/cpu.py`: reference CPU and `MemoryIf` interface.
- `src/prim/isa.py`: opcode constants, Verilog and TokenForth exports.
- `src/prim/assembler.py`: assembler and binary disassembly.
- `src/prim/tokenizer.py`, `tokens.py`: source scanning and token encoding.
- `src/prim/compiler.py`: compilation, per-compilation dictionary and immediate execution.
- `src/prim/artifacts.py`: owned token/program models, validation and TOML/binary I/O.
- `src/prim/debugger.py`: optional terminal debugger and UART RX extension.
- `rtl/sim_support/`: shared simulation, reference and test helpers.

The CPU has 8-bit opcodes, a 16-bit ALU, 16-bit addresses and two stacks of
16 entries. Opcode bit 7 is the return bit. Do not add RTL stack-array resets;
unused stack cells are undefined. Carry semantics are specified in D02.
Python and RTL CPU accesses wrap at 16 bits without memory-overflow traps.
No compiler program/dictionary collision checks are introduced (D13).

The dictionary grows downward from `0xfefe`; code/data grow upward from HERE.
Token/program documents carry symbols between tool invocations. Compiler
symbol and literal state belongs to each compilation, not a global dictionary.
Immediate execution is bounded by `--max-immediate-steps` (default 100000).
Strings use UTF-8 with a one-byte byte-count prefix (maximum 255).

SRAM supports physical whole-word transfers only. Byte and unaligned writes
require read-modify-write. Requests remain stable through ACK. RTL UART TX
is at byte address `0xffff`; reads access SRAM. The debugger separately models
RX status at `0xfffe` and RX data at `0xffff`. Its views and `r` command must
use `peek8`/`peek16` so inspection never consumes input. `uart <text>` queues
UTF-8 bytes. Reset restores initial memory/UART input and removes temporary
step-over breakpoints, retaining user breakpoints.

## Setup and Python tools

From the repository root:

```sh
bash setup.sh
source .venv/bin/activate
pip install -e '.[debug]'  # optional terminal debugger
make -C src
prim debug -i build/src/interpreter.tf.toml -u build/src/test.tok
```

Python 3.11+ is required. Runtime dependencies are declared in `pyproject.toml`;
`requirements.txt` installs the local package. HDL dependencies use `.[hdl]`.
Use `prim` subcommands, `prim-*` commands or `python -m prim`; legacy script
wrappers have been removed. Library imports use `prim.*`.

The Makefile writes twelve named outputs under `build/src/` (`OUT_DIR` override).
Targets such as `make -C src base.tf.toml` remain available.
Build order: `bootstrap.cf` (`c,` and `,`) -> generated `opcodes.cf` -> `base.cf`.
`prim opcodes --format tokenforth` exports one opcode emitter per assembler
mnemonic, lowercased with a trailing comma and no prefix. Default export remains
Verilog. Do not duplicate opcode-byte constants in `base.cf`; composite emitters
use the generated words. PUSH emitters write only the opcode, not operands.
Use `[ 'main boot! ]` for reset entries; it preserves HERE. Python module,
project configuration and Makefile changes trigger rebuilds. Clean removes only
named outputs; unrelated files and old artifacts under `src/` are preserved.
IDE tool launch entries use `build/src/`; run make once to create that directory.

## Verification

```sh
python -m unittest discover -s src -p 'test*.py'
python src/test.py
cmake -S rtl -B build/rtl
cmake --build build/rtl
ctest --test-dir build/rtl --output-on-failure
```

Debugger regressions require `.[debug]`, otherwise they skip. Makefile checks
require `make`. RTL tests require CMake, Verilator, Icarus Verilog and C++17.
CTest does not rebuild the simulator; build before running it. Compare Python
and RTL state after instruction completion, ignoring unused stack cells.
`rtl/test_tokenforth.py` freshly compiles examples, checks serial output and
runs the Python regressions including debugger, Makefile and generated opcode-word checks.

For opcode changes, update `src/prim/isa.py` and the active RTL implementation;
`cmake --build build/rtl --target genopcodes` exports `rtl/opcodes.v`.
Keep helper modules free of argument parsing, builds and other import effects.
