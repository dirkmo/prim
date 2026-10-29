# Project knowledge

As of October 27, 2026. This document summarizes the architecture and development
workflows. [DECISIONS.md](DECISIONS.md) records the reasons behind the choices.
See [system/README.md](../system/README.md) for signal details, edge cases and simulations.

Detailed walkthroughs are in [Code and architecture](CODE.md) and
[Tests and verification](TESTS.md).

## Goal and components

Prim is a stack CPU designed to be as minimal as possible, with a 16-bit data
path, 16-bit addresses and 8-bit opcodes. Both the data stack and return stack
hold 16-bit values. Opcode bit 7 requests an additional return; exceptions and
the order of stack effects are described in the RTL documentation.

| Path | Responsibility |
|------|----------------|
| `cpu/rtl/prim.v` | Verilog CPU |
| `system/rtl/memory.v` | Adapt the byte-addressed CPU bus to SRAM supporting only whole-word transfers |
| `system/rtl/memory_io.v`, `debug_uart/rtl/uart_tx.v`, `debug_uart/rtl/uart_rx.v`, `debug_uart/rtl/debug_uart.v`, `system/rtl/prim_system.v` | Shared CPU/debug UART, MMIO and system integration |
| `src/prim/cpu.py`, `isa.py`, `assembler.py` | Python CPU, instruction set and assembler |
| `src/prim/tokenizer.py`, `tokens.py` | Read TokenForth source and generate tokens |
| `src/prim/compiler.py` | Compile tokens into a program image |
| `src/prim/artifacts.py` | Document models, validation and TOML/binary I/O |
| `src/base.cf`, `src/examples/` | Base library and example programs |
| `tests/support/` | Shared simulation and comparison helpers |

Python tools run through `python -m prim` or the installed `prim-*` commands;
library imports use `prim.*`. The old `src/*.py` compatibility wrappers have
been removed. The alternative Amaranth implementation under `hdl/` is currently
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

`bootstrap.cf` first defines `c,` and `,`. The ISA exporter generates
`opcodes.cf` with one comma-suffixed word per opcode, compiled against the
bootstrap image. `base.cf` imports this opcode library and adds composite
emitters and control words. Examples import the resulting `base.tf.toml`.
`boot!` installs `PUSH16 entry; CALL; BREAK` at zero while preserving HERE. The unfinished
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

Python and RTL CPU memory accesses wrap at 16 bits without overflow traps.
No program/dictionary collision checks are added to the compiler (D13).

The CPU bus is byte-addressed and little-endian. A request with `o_bs != 0`
remains stable until the acknowledging clock edge with `i_ack = 1`.
`READ_CYCLES` and `WRITE_CYCLES` configure SRAM controller latency; their
values must meet the requirements of the SRAM and board clock frequency.

CPU writes to FFFF enqueue a seven-bit TX byte and stall only when the pending
buffer is full. Reads return the last CPU RX byte and clear its received flag
at final ACK, retaining the byte. FFFE reads bit 0 received/bit 1 TX-buffer-free;
writes are ignored. Mixed word operations complete SRAM before MMIO ACK and
wrap from FFFF to zero. RX and TX each have one byte plus one flag. CPU-only
reset preserves them; full system reset clears them. UART uses 115200/8N1 with
synchronized bit-centre RX. Debug ASCII uses bit 7 and has TX priority. q reads
UART status while CPU runs, without taking the CPU bus. SRAM debug ownership
still requires confirmed CPU halt. Details are in [DRAFT.md](DRAFT.md).
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

`make -C src` writes artifacts under `build/src/` and rebuilds them when tool
modules change. `make -C src base.tf.toml` builds only the base library;
`make -C src clean` removes named outputs only. Override `OUT_DIR` or `PYTHON`
as needed. Legacy artifacts under `src/` are not cleaned automatically.

With the debug extra installed, run
`prim debug -i build/src/interpreter.tf.toml -u build/src/test.tok`.
Debugger inspection is side-effect-free; `uart <text>` queues UTF-8 bytes.
Reset replays the initial UART file, discards interactive additions and
temporary breakpoints, and retains user breakpoints. Without `-u`, RX starts
empty. Its CPU-visible RX status/data at `0xfffe`/`0xffff` are separate from
the FPGA debug receiver. The FPGA also has CPU UART input, but only seven-bit
data, retained last-byte semantics and TX-free in status bit 1; the software
debugger keeps its independent eight-bit FIFO model.
See the root README for a standalone example and debugger keys.

Run Python checks with `python -m unittest discover -s src -p 'test*.py'`.
Debugger tests run when `.[debug]` is installed and otherwise skip; Makefile
checks require `make`. Both are also included in the CTest Python regressions.

The complete RTL checks require CMake, Verilator, Icarus Verilog and a C++17
compiler:

```sh
cmake -S . -B build/sim
cmake --build build/sim
ctest --test-dir build/sim --output-on-failure
```

CTest does not rebuild the simulator. The Python/RTL comparison checks
architectural state after each completed instruction and compares memory
accesses. Unoccupied stack cells may remain undefined. Four-state SRAM tests
also check bus release, read-modify-write and timing. UART output is decoded
independently from the serial signal.

The end-to-end TokenForth test freshly builds bootstrap, opcode words and
`base.cf`, then compiles the `hello`,
`control`, `data` and `strings` examples, then runs each example with three SRAM
timing configurations. Results are stored under `build/tokenforth/`.
The Python regressions are included in this CTest suite.

CTest registers sixteen suites. The debug-host, board and board-host suites
passed after the board host CLI extension.
This establishes simulation behavior; SRAM can now be loaded through debug
writes. Rev.B board pins and build/program targets are prepared under
`boards/olimex_ice40hx8k_evb/`. The initial 100 MHz board timing failed (about
52–54 MHz achieved); the user-approved board PLL now supplies a 25 MHz global
system clock. The routed build passes at 25 MHz (50.12 MHz reported maximum);
The debug UART uses GPIO1.33 (FPGA RX/G3) and GPIO1.34 (FPGA TX/F3).
The user has confirmed functional board operation and streaming SRAM loading.
External SRAM timing margins remain unmeasured; the reusable system's default
clock/timing parameters are not the board's selected 25-MHz configuration.

Semicolon return folding is implemented for simple word endings, including
generated PUSH instructions. Immediate/control-flow/data cases retain NOP.RET.
Simple final word calls use JP instead of CALL NOP.RET. See D17/D18 in
[DECISIONS.md](DECISIONS.md) for scope and planned extensions.

## Possible next improvements

The following items have been proposed and are not yet implemented:

5. Split the compiler into token decoding, dictionary management and immediate execution.
6. Add type annotations at module interfaces.
7. Unify CLI argument processing and error handling.
8. Set up Ruff and automated quality checks.

These proposals do not authorize implementation.

The Olimex host.py provides halt/run/step/reset-halt/pc/uart-status and a POSIX
console. Ctrl+B opens local commands, Ctrl+D exits without changing CPU state,
Ctrl+V quotes the next CPU byte; help/? and console --help list all commands.
One continuous reader owns RX and dispatches CPU output, debug replies and BREAK.
The input sender uses q credits and never holds the debug lock while RX is full.
Full debug operations (including loads) exclude q polls. The loader requires
--skip-uart-mmio for any image covering FFFE/FFFF, reports/skips only included
MMIO addresses and writes 65534 SRAM bytes for a full image using persistent
word writes (an odd tail uses a byte write). SRAM words are sent ahead with
concurrent OK counting; --write-delay optionally paces them. Failure is reported
without automatic retry or RUN, and invalidates the connection. The user can
reconnect and reload manually. Readback is optional via --verify
and uses word reads with automatic pointer increment. --run follows successful
loading and any requested verification. The board rebuild passes 25 MHz timing and uses
3216/7680 logic cells, one PLL and no block RAM. On 29 October 2026 the user
confirmed the running board bitstream, LED2 heartbeat, debug communication and
successful streaming loading. This does not establish external SRAM timing
margins or exercise every loader option on hardware.
