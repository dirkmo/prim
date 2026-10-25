# RTL simulation

Requirements: CMake, Verilator, a C++17 compiler, and Python 3. On macOS,
install the Xcode Command Line Tools. CMake falls back to the active SDK's
libc++ headers if the compiler cannot find them automatically.

From the repository root, build the simulator and run the existing regressions:

```sh
python3 rtl/control_flow_regressions.py
```

This configures and builds in `build/rtl` on every invocation, so changes to the
RTL and C++ sources are picked up. It does not use the old `rtl/build` cache.
The simulator writes `trace.vcd` into its build directory.

The equivalent explicit workflow is:

```sh
cmake -S rtl -B build/rtl
cmake --build build/rtl
ctest --test-dir build/rtl --output-on-failure
```

CTest uses the simulator from that build without rebuilding it. To run the
regressions against another existing build:

```sh
python3 rtl/control_flow_regressions.py --simulator /path/to/simulator
```

## Python/RTL comparison

Build and compare the 45 existing programs after every completed instruction:

```sh
python3 rtl/compare.py
```

Run an individual assembly program or a raw binary (assembly gets an appended
BREAK; binaries must reach a BREAK or SIMEND marker):

```sh
python3 rtl/compare.py --asm '0xffff 1 + carry'
python3 rtl/compare.py --binary build/rtl/test.bin --max-steps 10000
```

Use `--simulator build/rtl/simulator` to skip building. Differences produce a
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
python3 rtl/compare.py --wait-cycles 3
python3 rtl/compare.py --wait-cycles 9 --wait-seed 42
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

External interrupts and the physical RAM controller in `memory.v` are not yet
validated. These handshake tests use the C++ memory model.
