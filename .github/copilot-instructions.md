# Prim Stack Machine AI Coding Agent Instructions

## Project Overview

**Prim** is a two-layer stack machine implementation:
1. **Stack Machine CPU** (`prim/cpu.py`, `hdl/prim.py`): 8-bit opcodes, 16-bit ALU, dual stacks (data & return), Forth-based instruction set
2. **TokenForth Language** (`prim/tokenizer.py`, `prim/compiler.py`): A ColorForth-like language with compile-time and immediate-mode execution

The project includes Python-based simulation, HDL implementation (Amaranth), and Verilog/C++ simulation infrastructure.

## Architecture

### Core Components

- **`src/prim/cpu.py`** (Interpreter): Pure Python CPU simulator with data/return stack management, memory interface, instruction execution
- **`hdl/prim.py`** (Hardware): Amaranth HDL describing the actual CPU state machine with opcode decoding
- **`src/prim/tokenizer.py`**: Lexical analyzer converting TokenForth source → TOML token representation
- **`src/prim/compiler.py`**: Compiler converting tokenized input → binary bytecode (with embedded interpreter calls)
- **`src/prim/assembler.py`**: Assembler/disassembler for CPU opcodes (mnemonics ↔ 8-bit opcodes)
- **`src/prim/tokens.py`**: Token type definitions (13 types: WORD_CALL, NUMBER, MNEMONIC, etc.)

### Data Flow

```
TokenForth Source (.cf)
  → Tokenizer (.py) → TOML tokens (.tok.toml)
  → TokenForth Compiler (.py) → Binary (.tf.toml)
  → BinExport (.py) → Binary file (.tok)
  ↓
Python Simulator (Prim class)
  ↓
Memory/Stacks Output
```

### Key Design Decisions

- **Dual Two-Stack Architecture**: Data stack (DSP) and return stack (RSP) both 8-entry, with top value in `T` register
- **Immediate Mode in TokenForth**: Words between `[` and `]` execute at compile time, enabling meta-programming
- **Opcode Format**: High byte is type flag (0=immediate/direct, 1=encoded). Low byte contains 4-bit ALU op + 2 bits each for stack pointers + 3 bits each for source/dest
- **Memory Layout**: Dictionary grows downward from `0xFEFE`, code/data grow upward from `HERE` (`0x000A`)
- **Build Dictionary**: `prim/isa.py` auto-generates Verilog opcodes from Python class

## Developer Workflows

### Setup

```bash
cd /Users/dirk/dev/prim
bash setup.sh              # Creates .venv and installs amaranth + amaranth-boards
source .venv/bin/activate
```

### Compilation Workflow (src/)

```bash
cd src
make                       # Builds: base.tf.toml → test.tf.toml → test.tok
make clean                 # Removes .toml artifacts
```

**Targets**:
- `base.tf.toml`: Core TokenForth library (from `base.cf`)
- `test.tf.toml`: User code with library (from `test.cf`, depends on base)
- `test.tok`: Binary export for simulation

### Simulation Workflow (rtl/)

```bash
cd rtl/build
make simulate             # Assemble + compile Verilog + run C++ simulator
make wave                 # Open GTKWave with signal trace
make yosys               # Syntax check via Yosys
```

**Key build targets**:
- `genopcodes`: Exports `PrimOpcodes` class to `opcodes.v` (Verilog localparam)
- `assemble`: Converts `test.asm` → `test.bin` via `prim/assembler.py`
- `simulator`: Runs Verilated circuit with binary input
- `wave`: Displays VCD trace in GTKWave

## Code Patterns & Conventions

### Memory Interface Pattern

All CPU interactions use **abstract memory interface** (`MemoryIf` class):

```python
class MemoryIf:
    def read8(self, addr): ...
    def read16(self, addr): ...
    def write8(self, addr, value): ...
    def write16(self, addr, value): ...
```

Implementations: `Mif` (dict-backed), `PrimDebug` (with logging).

### Token Generation Pattern

Each token type inherits from `Token` base class and implements `generate()` method:

```python
class TokenWordCall(Token):
    def __init__(self, name, fragment):
        super().__init__(self.WORD_CALL, fragment)
        self.name = name
    def generate(self):
        return [self.tag, Token.D[self.name]]  # Index into definition dictionary
```

### Opcode Constants

Update `src/prim/isa.py` `PrimOpcodes` class → run `make genopcodes` to regenerate `opcodes.v`.

```python
class PrimOpcodes:
    NOP = 0x00
    CALL = 0x01
    ADD = 0x0c
    ...
```

### Compiler Dictionary Structure

Definitions stored at `DICT` (0xFEFE) growing downward:
- Index 0: `HERE` pointer (code allocation point, grows up)
- Index 1: `LATEST` pointer (most recent definition)
- Indices 2+: User word addresses

## Critical Integration Points

### Tokenizer → Compiler Handoff

1. `prim/tokenizer.py` reads `.cf` (ColorForth), emits `.tok.toml` (TOML-serialized tokens)
2. `prim/compiler.py` consumes `.tok.toml`, executes immediate words via `Prim` interpreter, emits binary
3. **Key**: `Token.D` dictionary (Python dict) bridges both phases; must persist across invocations

### Immediate Mode Execution

During compilation:
- `[` switches mode to immediate; `]` switches back to compile
- Immediate words execute against active `Prim` instance (shares `Mif`)
- Side effects (stack, memory) carried forward to compiled output

**Example**: `:array [ 10 ]` → allocates 10 bytes at compile time by executing `10` on stack, then stores address in compiled word.

### Verilog ↔ Python Synchronization

- `prim/isa.py` Python class → auto-export to `opcodes.v` (localparam)
- `hdl/prim.py` Amaranth design reads `PrimOpcodes.py` to decode instruction bits
- Keep instruction set synchronized: adding opcodes requires updates to both files

## Testing & Validation

### Python Unit Tests

```bash
cd src
python3 test.py          # Runs Prim interpreter against TokenForth code
python3 -m prim debug     # Interactive CPU debugger with stack/memory trace
```

### Simulation Tests

```bash
cd rtl/build
cmake ..
make simulate            # Runs C++ Verilator simulation
make wave                # View VCD trace
```

### VCD Waveforms

- Generated by Verilator in `rtl/build/trace.vcd`
- Signal definitions in `rtl/sim.gtkw` or custom `addsignals.tcl`
- Compare Python simulator behavior against hardware via waveforms

## Common Debugging Patterns

1. **TokenForth compile failure**: Check `prim/tokenizer.py` output (TOML), verify token types match `prim/tokens.py` classes
2. **Stack underflow/overflow**: Use `Prim.setLogLevel(Prim.LOG_LEVEL_DBG)` to trace execution
3. **Opcode mismatch**: Regenerate `opcodes.v` after modifying `prim/isa.py`, verify `hdl/prim.py` decoding matches
4. **Dictionary overflow**: Check `LATEST` pointer in memory dump; grows toward `HERE` → collision risk
5. **Immediate mode side effects**: Trace `Prim` state after `[` blocks; inspect stack via `T()`, `N()` accessors

## Repository Structure Map

```
src/
  prim/cpu.py             # CPU interpreter (execute, stack, memory)
  prim/assembler.py       # Assembler/disassembler mnemonics
  prim/isa.py             # Opcode constants + Verilog export
  prim/tokenizer.py       # TokenForth lexer
  prim/compiler.py        # TokenForth compiler + executor
  prim/tokens.py          # Token type classes
  test.cf                 # TokenForth source for testing

hdl/
  prim.py                 # Amaranth HDL of CPU (state machine, ALU)
  prim.vcd                # Simulation output

rtl/
  prim.v                  # Verilog (generated from Amaranth or hand-written)
  sim.cpp                 # C++ Verilator testbench
  CMakeLists.txt          # Verilator + simulation build

.github/
  copilot-instructions.md # This file
```

## Branch Context

**Current branch**: `feature/amaranth` — Migrating HDL from Verilog to Amaranth (Python HDL) for easier hardware-software co-design. Main implementation in `hdl/prim.py`; legacy Verilog in `rtl/prim.v` for reference.
