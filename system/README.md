# System integration and simulation

The [complete register overview](docs/registers.md) collects the MMIO map,
bit fields, reset values, access side effects and CPU registers.

`rtl/prim_system.v` composes the standalone CPU from `cpu/rtl/`, the serial
subsystem from `debug_uart/rtl/`, and this component's bus mux and memory/MMIO
controllers. `rtl/bus_mux.v` grants the debug bus only on confirmed CPU halt.
`rtl/memory_io.v` owns the FFF0..FFFF timer/reserved/LED/UART address mapping and produces a seven-bit
valid/ready output stream; it does not instantiate or configure a UART.
`rtl/memory.v` implements the physical SRAM interface. The system wrapper adds
no CPU instruction behavior.

Optional `VGA_ENABLE=1` adds the [VGA text controller](../vga/README.md),
registers at FFF6..FFFA and a switchable 4-KiB video-RAM window at E000..EFFF.
The Olimex board enables it using the existing 25 MHz clock. Generic system
instances default to VGA disabled.

Complete SRAM/MMIO/CPU/debug and TokenForth integration tests live in `tests/`.
See [CPU](../cpu/README.md), [debug UART](../debug_uart/README.md), and
[the implemented protocol](../docs/DRAFT.md) for the component boundaries.

## RTL simulation

Requirements: CMake, Verilator, Icarus Verilog (`iverilog` and `vvp`),
a C++17 compiler, and Python 3.11 or newer. The TokenForth compiler also needs
the installed local `prim-tokenforth` package (dependencies in pyproject.toml). On macOS,
install the Xcode Command Line Tools. CMake falls back to the active SDK's
libc++ headers if the compiler cannot find them automatically.

First run `bash setup.sh` and `source .venv/bin/activate` from the repository
root. The commands below assume this environment is active. CMake prefers
`.venv/bin/python` when available; override with `-DPython3_EXECUTABLE=...` if
needed, using an interpreter where `pip install -e .` has been run.

From the repository root, build the simulator and run the existing regressions:

```sh
python3 cpu/tests/control_flow_regressions.py
```

This configures and builds in `build/sim` on every invocation, so changes to the
RTL and C++ sources are picked up. It does not use the old `rtl/build` cache.
The simulator writes `trace.vcd` into its build directory.

The equivalent explicit workflow is:

```sh
cmake -S . -B build/sim
cmake --build build/sim
ctest --test-dir build/sim --output-on-failure
```

CTest uses the simulator from that build without rebuilding it. To run the
regressions against another existing build:

```sh
python3 cpu/tests/control_flow_regressions.py --simulator /path/to/simulator
```

## Python/RTL comparison

Build and compare the 45 existing programs after every completed instruction:

```sh
python3 cpu/tests/compare.py
```

Run an individual assembly program or a raw binary (assembly gets an appended
BREAK; binaries must reach a BREAK or SIMEND marker):

```sh
python3 cpu/tests/compare.py --asm '0xffff 1 + carry'
python3 cpu/tests/compare.py --binary build/sim/test.bin --max-steps 10000
```

Use `--simulator build/sim/simulator` to skip building. Differences produce a
nonzero exit code and identify the first instruction, address, field, and both
values. For example, `--asm '1 2 over 3'` checks a previously broken combination
of OVER followed by PUSH; it now matches Python.

The simulator's `-j retirement.jsonl` option emits PC, opcode, stack pointers,
carry, stacks (top first), and byte reads/writes after each EXECUTE edge. Python
advances its PC during fetch; the comparison uses its state after `step()`,
when both PCs address the next instruction. BREAK/SIMEND are debugger markers
and are checked before fetching/executing them in comparison mode.

The comparison uses the default 16-cell stacks. It compares the occupied stack
cells, excluding unused cells that Python clears on pop but hardware retains.
Depth is tracked from instruction effects, capped at 16; stack underflow and
reset contents of unused cells are outside this check.

To keep the CPU minimal, neither stack array has a reset. Unused cells are
undefined after reset; programs must write stack entries before reading them.
PC, stack pointers, cached T/N registers, carry, and execution control still
reset. Python's zero-filled stack arrays are not part of the RTL contract.

Both sides start with identical 64 KiB RAM filled with `0xff` outside the image.
In comparison mode the simulator treats **all** addresses as flat RAM, including
`0xfffe`/`0xffff`, with little-endian words and address wrapping. Ordered byte
writes are compared after every instruction; equal initial memory plus equal
writes ensures equal memory contents. This mode does not emulate UART/MMIO.
The normal simulator mode keeps its existing memory map.

CTest runs the original final-state regressions, the instruction comparisons,
and integration checks. The stack checks cover every depth from 3 to 16,
repeated data stack pointer wraparound, memory/branch interactions, and 20
reproducible sequences of 200 mixed instructions followed by stack draining.
The RTL array uses Python's circular indexing (T at DSP, N at DSP-1) and is
updated together with the cached T/N registers at instruction retirement.

Return-bit checks cover regular operations, immediates, memory operations, and
the CALL/JP/JZ/INT exceptions (these ignore the return bit). The instruction's
return stack effect precedes the return: `>R.RET` jumps through the consumed
data stack value without changing RSP; `R>.RET` and `RDROP.RET` remove two
return stack entries and jump through the second one. The implementation does
this within the normal EXECUTE cycle, without resetting or clearing return
stack cells. Tests include ring boundary cases, up to 16 nested calls, and a
CALL at address `0xffff` whose return address wraps to zero.

## ALU and carry

Results are 16 bits. Signed and unsigned comparisons return `0xffff` for true
and zero for false. ADD sets carry on unsigned overflow; SUB sets it on borrow
(`N < T`). Shifts are logical and replace carry with the last bit shifted out:

| Instruction | Result | Carry from original T |
|-------------|--------|-----------------------|
| SR | T >> 1 | Bit 0 |
| SRW | T >> 8 | Bit 7 |
| SL | (T << 1) & 0xffff | Bit 15 |
| SLW | (T << 8) & 0xffff | Bit 8 |

All other instructions preserve carry; CARRY pushes its value as 0 or 1.
Python and RTL implement the same rules. This changes the previous SRW carry
tap (bit 0) and the previous SL/SLW carry behavior (always zero).

Tests check arithmetic boundary pairs, signed/unsigned comparisons, preservation
of carry, and every single-bit shift operand against independent expected
results as well as comparing Python with RTL after each instruction.

## Memory handshake

`o_bs != 0` requests a transfer. It completes on a rising clock edge with
`i_ack == 1`; read data must be valid on that edge. Until then, the CPU holds
the address, byte selection, write enable, write data, and execution state.
The memory accepts a write exactly once on its acknowledging edge.

`o_bs = 01` accesses the byte at `o_addr` using the low data lane; `11` accesses
that byte and the next byte as a little-endian word, including odd addresses.
Address arithmetic wraps at 16 bits. The unused lane of a byte read is ignored.

Instruction fetches happen in FETCH. Immediates, data reads, and data writes
complete in MEMWAIT. EXECUTE changes the architectural state with the bus idle.
There is no extra read before a store and no repeated access in EXECUTE.
FETCH and MEMWAIT transfers can be back-to-back: the memory must support a new
request immediately after an acknowledged one, without requiring a low-BS gap.
Reset deasserts BS and WE and returns control to FETCH.

Test fixed or reproducible random memory latency from the repository root:

```sh
python3 cpu/tests/compare.py --wait-cycles 3
python3 cpu/tests/compare.py --wait-cycles 9 --wait-seed 42
```

The first waits three cycles on each transfer. The second chooses 0..9 wait
cycles per transfer from the seeded generator. These options also work with
`--asm` and `--binary`. The simulator equivalents are `-w 3` and `-w 9 -s 42`.

The simulator checks that requests and CPU state remain stable until ACK and
poisons invalid read data and unused byte lanes. The comparison checks ordered
byte reads as well as writes, detecting extra accesses and duplicate stores.
CTest includes all 45 baseline programs at five latency settings, odd/wrapped
word accesses, repeated accesses, self-modifying code, memory instructions with
the return bit, and 257-cycle stalls.

These handshake tests use the C++ memory model. The physical controller has
separate tests described below. Timer IRQ wiring is tested in the system suite;
CPU interrupt semantics and tests are described in [cpu/README.md](../cpu/README.md).

## Whole-word SRAM controller

`memory.v` adapts the CPU bus to asynchronous SRAM with no FPGA-controlled byte
enables, as required for the iCE40HX8K-EVB connection. Board references:
[Olimex board documentation](https://www.olimex.com/Products/FPGA/iCE40/iCE40HX8K-EVB/)
and [Rev B1 schematic](https://github.com/OLIMEX/iCE40HX8K-EVB/blob/master/HARDWARE/REV-B1/iCE40HX8K-EVB_Rev_B1.pdf).

| CPU operation | Physical SRAM operations |
|---------------|--------------------------|
| Byte read | One word read, select the byte |
| Aligned word read | One word read |
| Odd-address word read | Two word reads, combine bytes |
| Byte write | One word read and one full-word write |
| Aligned word write | One full-word write, no read |
| Odd-address word write | Two word reads and two full-word writes |

Read-modify-write preserves the unselected neighbouring bytes. CPU BS=01
selects the byte at `i_addr` in bits 7:0; BS=10 selects only `i_addr+1` in bits
15:8; BS=11 selects both. All address arithmetic wraps within the CPU's 64 KiB.
The controller uses one shared 16-bit data buffer and relies on stable CPU
inputs until ACK, avoiding request registers. SRAM contents and the data buffer
have no reset; only controller state resets.

The interface now includes `i_reset` and active-low `ram_cs_n`, alongside OE
and WE. Connect the CPU reset to both CPU and controller. `ram_addr` is a
**word** address: its low 15 bits address the first 64 KiB of SRAM, and bit 15
is zero. Connect it to the SRAM address lines and tie any remaining upper
address lines low; bank switching is not implemented. Both physical byte
enables remain asserted as on the board. Instantiate the bidirectional
`ram_data` connection at FPGA I/O, not as an internal tri-state bus.

`READ_CYCLES` and `WRITE_CYCLES` are positive integer parameters, both defaulting
to 2. A read holds OE active for READ_CYCLES clocks; a write holds WE active for
WRITE_CYCLES clocks. One clock each is reserved for read-to-write bus release,
write setup, write hold, and FPGA bus release. ACK follows the last operation
with the SRAM controls inactive. The controller accepts consecutive CPU
requests without requiring BS to go low between them.

These cycle counts must meet SRAM access, output-disable, pulse, setup, and
hold times at the chosen clock frequency, including FPGA I/O/routing delays.
They have not been verified by board place-and-route or a hardware test.
Reset disables SRAM controls and releases the bus; resetting during an active
write does not guarantee atomic preservation of that SRAM word.

Run the physical controller tests directly:

```sh
python3 system/tests/test_sram.py
```

CTest also includes them as `sram_controller_checks`. The four-state Icarus
model supports only full 16-bit SRAM writes, delays SRAM data and bus release,
and checks write setup/pulse/hold times and bus contention. Three configurations
exercise read/write cycles of 1/1, 2/2, and 3/4, with model delays of 3, 12, and
19 ns at a 20 ns clock period. Controller tests cover all masks, neighbouring
bytes, wrapping, 512 random requests per configuration, reset, and idle bus
release. CPU + controller + SRAM tests run all 45 baseline programs and extra
memory/return/self-modifying cases against Python after every instruction.
Unused stack cells stay undefined in this simulation; unknown occupied cells
are reported as mismatches rather than silently treated as zero.

## Shared CPU/debug UART

`prim_system.v` instantiates `Prim`, `bus_mux`, `memory_io` and `debug_uart_link`.
It has serial RX/TX and uses fixed 115200 baud, 8N1, with a constant divider
rounded from CLK_HZ. RX uses two synchronizer flops and bit-centre samples.
A one-byte CPU TX buffer feeds the existing UART transmitter; debug wins
at byte boundaries. A retained CPU RX register operates independently.
CPU output has seven useful bits (bit 7 is cleared); debug ASCII has bit 7 set.
UTF-8 output is therefore not preserved on this FPGA UART.

The [system UART MMIO reference](docs/uart_mmio.md) defines the byte addresses,
word accesses and loader exclusions.
The [timer MMIO reference](docs/timer_mmio.md) describes COUNT at FFF0, COMPARE
at FFF2, CSR at FFF4 and the `TIMER_DIVISOR` system parameter. FFF6..FFFC is
reserved (read zero, writes ignored). The timer and UART one-clock IRQs are
ORed into the CPU; configure its ISR with INTAD before enabling interrupts with INTEI.
CPU halt/debug reset preserve the running timer; system reset clears it.

FFFD controls LED1/LED2 in bits 0/1 (1 = on); reads return these bits with
bits 7:2 zero. System reset turns both off; CPU-only reset preserves them.
FFFE is the UART CSR: bit 0 received, bit 1 pending TX buffer free, bit 2
RXIE, bit 3 TXIE. Writes update only bits 2/3. RXIE enables interrupts for CPU
receptions; TXIE enables interrupts when the CPU TX slot becomes free, before
frame completion. Debug traffic generates no UART IRQ. FFFF reads the most
recently received CPU byte and clears its received flag on ACK, retaining the byte; writes enqueue seven-bit TX data
and wait only when the buffer is full. New RX wins over simultaneous ACK. CPU
reset preserves both UART buffers and interrupt enables. The debug command q
returns status without taking the CPU bus, allowing input credit checks while the CPU runs.

Word accesses combine MMIO and SRAM as little-endian lanes. Mixed operations
finish their SRAM lane before the final MMIO phase. FFFE is CSR low/RX high
on reads, CSR low/TX high on writes. FFFF combines RX or TX low with SRAM
address zero high. FFFC combines reserved low/LEDs high; FFFD combines LEDs
low/CSR high. Normal RAM word operations remain whole-word requests. All UART
register effects occur once at the final bus ACK. Tests cover all byte masks,
unaligned/wrapped words, TX stalls, CPU echo with concurrent debug traffic,
RESET-HALT preservation and MMIO/OK deadlock freedom.

The complete command table, low-nibble-first numbers, persistent write modes,
CPU HALT/STEP/RESET-HALT/BREAK semantics, host API, intentionally omitted error
checks and synthesis comparison are in [docs/DRAFT.md](../docs/DRAFT.md).
The standalone Prim inputs i_halt/i_run/i_step/i_debug_reset must be connected
(tie low when unused). Standalone memory_io users connect its output stream to a valid/ready sink. CPU reset is distinct from system reset.

```sh
python system/tests/test_io.py
python system/tests/test_debug_uart.py
python debug_uart/tests/test_host.py
```

CTest includes the existing mapped-I/O tests and both new debug suites.
The full system simulation covers RX through physical SRAM bus and TX;
additional CPU tests check halt and step during delayed memory operations.
Board pin assignments, physical UART and timing after place-and-route still
need verification on hardware.

## TokenForth end-to-end test

Run the complete source-to-serial pipeline from the repository root:

```sh
python3 system/tests/test_tokenforth.py
```

The runner uses a Python with `prim-tokenforth` installed, checking its own interpreter
first, then `.venv/bin/python`. To select one explicitly:

```sh
.venv/bin/python -m pip install -e .
python3 system/tests/test_tokenforth.py --compiler-python .venv/bin/python
```

Every invocation freshly compiles `src/bootstrap.cf`, exports and compiles
the opcode words from `prim.isa`, then compiles `src/base.cf` and the examples
in `src/examples`. It exports the **memory** section of the resulting `.tf.toml`
using `python -m prim export`; token bytes are never treated as CPU code. Existing TOML
files in `src/` are not used or overwritten. The four examples cover:

| Source | Features | Expected UART output |
|--------|----------|----------------------|
| hello.cf | Compiled string, calls, while/repeat | `Hello, World!\r\n` |
| control.cf | if/else/then, do/loop, for/next, i | `BACCC012` |
| data.cf | Raw numeric/address literals, variable writes, indirect CALL | `ABCZ` |
| strings.cf | UTF-8, raw/empty strings, comment markers inside strings | `Grüße 🙂 Raw ä \ ( )\r\n` |

Each source uses an immediate block to install `PUSH16 main; CALL; BREAK` at
address zero. The test verifies this entry against the compiled dictionary;
it does not patch the binary. The comparison harness stops before BREAK; the integrated hardware now
executes BREAK as a real halt and advances PC to the following instruction. The compiler must produce no UART output itself.

All four 64-KiB binaries execute on CPU + physical SRAM controller + SRAM
model + UART at the three timing configurations. Each retired instruction,
including stack values, carry and logical memory reads/writes, is compared
with Python. The decoded serial output must match the seven-bit projection of both Python
and the explicit expected byte string. The UTF-8 strings example checks this
intentional loss of bit 7; it does not claim UTF-8 compatibility. The final frame is drained after the simulation marker.

`build/tokenforth/` keeps fresh base/example `.tok.toml`, `.tf.toml`, `.bin`,
compiler logs, and a `.jsonl` retirement trace and `.uart.bin` serial capture
for each example/timing combination. CTest runs this as `tokenforth_end_to_end`.
This tests the host compiler toolchain; `src/interpreter.cf` (the unfinished
on-CPU token interpreter) is a separate component and is not required here.

The same CTest entry runs the focused Python toolchain regressions, the original
Python CPU tests, and installed-package/CLI checks from a foreign working
directory. Run the focused checks separately with:

```sh
.venv/bin/python src/test_toolchain.py
```

TokenForth counted strings store a UTF-8 **byte** count, limited to 255 bytes.
The tokenizer rejects oversized text rather than wrapping the length field;
errors include source filename and line. Both ordinary strings and raw string
literals, including empty strings, are covered by Python and RTL tests.

An explicitly supplied tokenizer library (`-it`) must be a valid compiled
TokenForth file. Missing files, malformed TOML, wrong types, and invalid
library data are reported with the library filename, without silently starting
a new dictionary. Omitting `-it` still creates the initial H/LATEST symbols.

Each immediate execution has a default limit of 100000 CPU steps, including
the terminating BREAK step. Change it with the compiler option
`--max-immediate-steps N` (N must be positive). Exhausting the limit reports
the input TOML filename, step limit and current PC instead of hanging.
Python callers can pass `max_steps` to `execute` or `max_immediate_steps` to
`interpret`. Opcode inputs are copied and remain reusable across executions.

## Tokenizer/compiler API and diagnostics

The tokenizer scans source once, distinguishing words, strings, line comments
and parenthesized comments. Comment markers inside strings and quotes inside
comments are literal text. Multiple comments on a line and multiline
parenthesized comments are supported. Words and delimiters are separated by
whitespace; strings remain single-line with literal backslashes (no escape
syntax). Parenthesized comments are not nested. Immediate brackets must be
balanced and cannot be nested.

Input errors use `tferrors.CompileError` (a ValueError), with source locations
such as `example.cf:3:5`. Compiler token errors include the input filename and
byte offset, e.g. `example.tok.toml:token[12]`. Truncated payloads, invalid UTF-8,
unknown tags, modes, builtins and symbol indices are rejected. Validation also
runs under `python -O`; it no longer depends on assertions. The CLI reports
these errors without a traceback and does not write a compiled result.

There is no per-compilation class-global symbol or literal state. Each
tokenization owns a SymbolTable, tokens retain resolved indices, and each
compiler Mif owns a Dictionary. Input library lists and memory are copied.
Repeated, failed, and interleaved compilations are tested in one Python process.

From Python with the package installed:

```python
from prim.tokenizer import tokenize_text
from prim.compiler import compile_document

result = tokenize_text(':answer 42 ;', filename='example.cf')
image = compile_document({
    'type': 'tokenizer', 'tokens': result.tokens, 'symbols': result.symbols,
    'memory': [], 'string-literals': [], 'num-literals': [],
}, filename='example.tok.toml')
```

`tokenize_file(path, symbols=...)` returns the same TokenizedSource structure.
The existing `convert(path, symbols)` helper still returns token bytes, without
leaving shared state behind. `compile_document` returns a compiled document
with independent `symbols`, literal lists and `memory`. To extend a library,
pass its symbols to tokenization and its memory/literal lists into the next
tokenizer document, as the CLI does. The former Token.D and Dictionary.D/S/N
class attributes are replaced by these explicit per-compilation objects.

## RTL test infrastructure

`tests/support/` contains ordinary helper modules, separate from the test
cases and command-line entry points:

| Module | Responsibility |
|--------|----------------|
| build.py | Configure/build Verilator and compile Icarus testbenches |
| process.py | Run external tools with timeouts, logs and failure diagnostics |
| reference.py | Python memory model and instruction-retirement comparison |
| traces.py | Read retirement JSON and final-state output |
| verilator.py | Execute an image on the Verilator simulator |
| sram.py | Execute SRAM/UART testbenches and collect simulation results |
| tokenforth.py | Select compiler Python and freshly build TokenForth examples |
| config.py, unittest_bridge.py | Explicit tool options and unittest lifecycle |
| cases.py, scenarios.py | Shared instruction vectors and SRAM scenarios |

Test modules no longer import other test modules, mutate their parsers, or
parse command-line arguments on import. Importing them never launches a tool
or creates a build directory. Script tool options are parsed only at the entry
point and passed as an immutable Tools configuration. Direct test-script
commands and CMake tool-path overrides keep the same syntax.

SimulationResult supplies instruction counts, serial bytes and retirement
records; its `save` method writes the existing `.jsonl`/`.uart.bin` artifacts.
External-tool failures retain stdout/stderr and the exit code; timeouts and
invalid traces report the command or filename/line. The dedicated
`test_harness_checks` CTest suite covers these infrastructure guarantees.

Unittest can also discover the RTL tests normally, without tool argument
parsing. Build the Verilator simulator first, then run:

```sh
python -m unittest discover -s system/tests -p 'test_*.py'
```

These helpers belong to the repository's tests and are not included in the
installed runtime package.

## Shared artifact models

`prim.artifacts` is the common boundary for tokenizer/compiler documents,
binary export, annotated disassembly and debugger image loading:

- `TokenDocument`: token bytes, symbols, optional imported 64-KiB memory and
  literal metadata (`type = "tokenizer"`).
- `ProgramImage`: compiled 64-KiB memory, symbols and literal metadata
  (`type = "tokenforth"`).

Both dataclasses own their data: byte buffers become `bytes`, symbol/address
lists become tuples, and metadata is copied. Constructors and `from_mapping`
validate the schema; `to_mapping` returns independent lists/dictionaries for
compatibility. Token instruction/payload semantics remain the compiler's job,
including its token-offset diagnostics.

```python
from prim.tokenizer import tokenize_document
from prim.compiler import compile_tokens
from prim.artifacts import load_program, load_tokens, save, export_section

tokens = tokenize_document(':answer 42 ;', filename='answer.cf')
save(tokens, 'answer.tok.toml')
image = compile_tokens(load_tokens('answer.tok.toml'))
save(image, 'answer.tf.toml')
export_section(load_program('answer.tf.toml'), 'memory', 'answer.bin')
```

`load(path)` detects the document kind; `load_tokens` and `load_program` enforce
it. `save`, `section_bytes` and `export_section` centralize serialization and
byte-section export. Paths appear in parse, schema and I/O errors. Unknown
non-reserved metadata fields survive a load/save roundtrip. The existing field
names and TOML document kinds remain unchanged. Reading uses Python 3.11's
standard-library `tomllib`; writing uses `tomli-w`. The old `toml` dependency
and its comma-symbol workaround have been removed. Existing TOML artifacts
remain readable; newly written files can have different whitespace.

Existing `compile_document`, `snapshot` and `load_library` mapping APIs and
command-line flags remain available. For new code, `tokenize_document` and
`compile_tokens` provide typed input/output. Run the artifact regressions with
`python src/test_artifacts.py`; the TokenForth CTest entry includes them too.

## Board wrapper

The optional `START_HALTED` parameter (default 0) starts the CPU halted on
system reset, before its first fetch. `o_halted` exposes confirmed CPU halt to
board-level indicators. The [Olimex Rev.B wrapper](../boards/olimex_ice40hx8k_evb/README.md)
sets START_HALTED=1 and supplies power-up/button reset; default pin-independent
system behavior remains unchanged.

Mapped-UART instruction comparison feeds timing-dependent TX-free samples from
the simulated peripheral into the ISA reference (other UART status bits still
have fixed expected values when no CPU input is injected). Serial output is
checked against that same reference run, including programs branching on status.
Independent RTL tests verify the actual status/buffer and ACK semantics.
