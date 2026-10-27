# Project knowledge

As of October 27, 2026. This document summarizes the architecture and development
workflows. [DECISIONS.md](DECISIONS.md) records the reasons behind the choices.
See [rtl/README.md](../rtl/README.md) for signal details, edge cases and simulations.

## Goal and components

Prim is a stack CPU designed to be as minimal as possible, with a 16-bit data
path, 16-bit addresses and 8-bit opcodes. Both the data stack and return stack
hold 16-bit values. Opcode bit 7 requests an additional return; exceptions and
the order of stack effects are described in the RTL documentation.

| Path | Responsibility |
|------|----------------|
| `rtl/prim.v` | Verilog CPU |
| `rtl/memory.v` | Adapt the byte-addressed CPU bus to SRAM supporting only whole-word transfers |
| `rtl/memory_io.v`, `rtl/uart_tx.v`, `rtl/prim_system.v` | UART MMIO and system integration |
| `src/prim/cpu.py`, `isa.py`, `assembler.py` | Python CPU, instruction set and assembler |
| `src/prim/tokenizer.py`, `tokens.py` | Read TokenForth source and generate tokens |
| `src/prim/compiler.py` | Compile tokens into a program image |
| `src/prim/artifacts.py` | Document models, validation and TOML/binary I/O |
| `src/base.cf`, `src/examples/` | Base library and example programs |
| `rtl/sim_support/` | Shared simulation and comparison helpers |

The old tools under `src/*.py` are compatibility wrappers. New Python imports
use `prim.*`. The alternative Amaranth implementation under `hdl/` is currently
outside the scope of this work.

## TokenForth from source to CPU

1. The tokenizer reads `.cf`, recognizes words, definitions, numbers, strings,
   comments and mode changes, and resolves symbol indices.
2. A `TokenDocument` contains token bytes, symbols and optionally an imported
   library's memory image and literal addresses. It is saved as `.tok.toml`
   with `type = "tokenizer"`.
3. The compiler processes the tokens. In compile mode it generates code;
   immediate words execute on the Python CPU during compilation.
4. A `ProgramImage` contains 65536 memory bytes, symbols and literal addresses.
   It is saved as `.tf.toml` with `type = "tokenforth"`.
5. The exporter writes the `memory` section as a binary image, which the Python
   CPU or RTL simulation can execute.

`base.cf` is compiled first. Examples import its program image. The unfinished
on-CPU token interpreter in `src/interpreter.cf` is a separate component;
the host compiler and end-to-end test do not require it.

Strings use UTF-8. Their one-byte length prefix counts bytes, up to 255.
Compiler errors include source locations or token byte offsets. Each compilation
owns its symbol and dictionary state. Immediate execution defaults to a limit
of 100000 CPU steps per execution, including BREAK (`--max-immediate-steps`).

## Memory and board

The target board is the iCE40HX8K-EVB. According to the user's hardware
requirements, SRAM is connected through a 16-bit data bus and its byte-select
pins cannot be controlled by the FPGA. Physical transfers always access entire
16-bit words. Byte writes therefore require read-modify-write. Unaligned
16-bit accesses touch two SRAM words. The controller preserves neighboring
bytes and supports address wraparound within 64 KiB.

The CPU bus is byte-addressed and little-endian. A request with `o_bs != 0`
remains stable until the acknowledging clock edge with `i_ack = 1`.
`READ_CYCLES` and `WRITE_CYCLES` configure SRAM controller latency; their
values must meet the requirements of the SRAM and board clock frequency.

Writes to byte address `0xffff` go to UART TX. Reads there access SRAM. Word
accesses crossing this boundary are split by byte between SRAM and UART,
including wraparound to `0x0000`. UART uses 8N1 and currently has no FIFO,
receiver or status register. CPU writes wait while the transmitter is busy.
External interrupts are tied inactive in the integrated system.

## Development and verification

Python 3.11 or newer is required. Install from the repository root:

```sh
bash setup.sh
source .venv/bin/activate
prim --help
```

`pyproject.toml` defines the package and dependencies. `tomllib` reads TOML;
`tomli-w` writes it. The terminal debugger (`.[debug]`) and Amaranth (`.[hdl]`)
are optional extras.

The complete RTL checks require CMake, Verilator, Icarus Verilog and a C++17
compiler:

```sh
cmake -S rtl -B build/rtl
cmake --build build/rtl
ctest --test-dir build/rtl --output-on-failure
```

CTest does not rebuild the simulator. The Python/RTL comparison checks
architectural state after each completed instruction and compares memory
accesses. Unoccupied stack cells may remain undefined. Four-state SRAM tests
also check bus release, read-modify-write and timing. UART output is decoded
independently from the serial signal.

The end-to-end TokenForth test freshly compiles `base.cf` and the `hello`,
`control`, `data` and `strings` examples, then runs each example with three SRAM
timing configurations. Results are stored under `build/tokenforth/`.
The Python regressions are included in this CTest suite.

Last verified: all eight CTest suites passed, as did 14 artifact-format checks
under `python -O`. This establishes simulation behavior. Board pin assignments,
a program loader, timing after place-and-route and physical UART output remain
open. Default clock and timing parameters are not a verified board configuration.

## Possible next improvements

The following items have been proposed and are not yet implemented:

5. Split the compiler into token decoding, dictionary management and immediate execution.
6. Add type annotations at module interfaces.
7. Unify CLI argument processing and error handling.
8. Set up Ruff and automated quality checks.
9. Review the need for compatibility wrappers and their long-term maintenance.

These proposals do not authorize implementation.
