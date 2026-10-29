# CPU

`rtl/prim.v` implements the Prim stack CPU. `rtl/opcodes.v` is generated from
`prim.isa` with the root CMake target `genopcodes`.

The CPU has no UART, MMIO decoder or SRAM controller. Its byte-addressed
16-bit bus uses BS/WE/ACK; requests stay stable until ACK. Debug control uses
synchronous `i_halt`, `i_run`, `i_step`, `i_debug_reset` inputs and
`o_halted`, `o_pc`, `o_break_reason`, `o_break_event` outputs. Tie unused control
inputs low. HALT completes the current instruction, including memory waits;
STEP retires exactly one instruction. BREAK preserves stacks and ignores the
return bit, advancing PC to the following instruction. See
[the protocol and CPU semantics](../docs/DRAFT.md).

`tests/` owns the Verilator simulator, ISA comparisons, memory handshake tests,
and directed CPU debug-control tests. Shared simulation helpers live under
`tests/support/` in the project root.

From the project root:

```sh
cmake -S . -B build/sim
cmake --build build/sim
ctest --test-dir build/sim --output-on-failure
python cpu/tests/compare.py --asm '1 2 +'
python cpu/tests/test_debug_cpu.py
```

The standalone Verilator simulator links only the CPU. The top-level system
and all UART RTL are independent sources and are not part of that simulator.

The CPU UART-bus regression models status and retained RX data at FFFE/FFFF,
a full TX buffer with delayed ACK, HALT during that write, and STEP afterwards.
No peripheral logic belongs in the CPU: ordinary byte/word memory instructions
and the stable-until-ACK bus already support buffered UART MMIO.

## Interrupts

`i_irq` accepts synchronous, one-clock pulses. One pending bit captures pulses
in every phase, including HALT and while masked; multiple pending pulses coalesce.
CPU reset and debug reset clear pending, the interrupt enable and the ISR address
register (zero). Configure the ISR address before enabling or using software INT:

```text
<isr-address> INTAD
INTEI
```

| Instruction | Opcode | Data stack | Effect |
|-------------|--------|------------|--------|
| INTEI | 23 | ( -- ) | Enable hardware interrupts |
| INTDI | 24 | ( -- ) | Disable hardware interrupts; retain pending |
| INTAD | 25 | ( addr -- ) | Pop the 16-bit ISR byte address into the vector register |

All three support `.RET`: their normal effect completes before returning.
Software `INT` uses the same vector, ignores the return bit and works even while
hardware interrupts are disabled. Address 0004 has no special meaning.

A request is accepted after an instruction fully retires, using that instruction's
updated enable state. A fourth state in the existing two-bit phase register then
pushes the updated PC onto the existing return stack and jumps to the vector.
The entry takes one clock, performs no bus transaction and leaves the data stack,
carry and interrupt enable unchanged. This also preserves CALL/return stack effects
and completes memory accesses before entry. A directly accepted pulse is consumed;
a new pulse coinciding with acceptance of an older pending request remains pending.

The first ISR instruction executes before another request can be accepted. For
no nesting, start the ISR with `INTDI` and finish with `INTEI.RET`. Otherwise nested
interrupts use the same return stack. There is no hardware stack overflow check or
automatic context save beyond the PC; software must balance stack use and preserve
any needed carry state. Pending interrupts may cause immediate re-entry after
`INTEI.RET`.

HALT, BREAK and STEP take priority over interrupt acceptance. Requests remain
pending while halted; STEP retires one instruction without an interrupt entry.
RUN allows acceptance after the next instruction. Asynchronous sources require
synchronization/pulse transfer outside the CPU. In the Python instruction model,
`request_irq()` latches an event and `step()` includes any resulting entry after
the instruction; it does not model individual clock phases or debug stepping.

`test_debug_cpu.py` includes delayed-bus interrupt tests for masking, nesting,
simultaneous events, CALL/return collisions and debug controls. `src/test_interrupts.py`
checks the Python model; the ISA comparison suite covers the new opcodes and `.RET`.

A CPU-only Yosys `synth_ice40 -top Prim` comparison with default DSS/RSS=4
measured 2247 -> 2302 LUT4 and 604 -> 623 flip-flops (+55 LUT4, +19 FF).
Carry cells remain at 87. The new architectural state is 18 bits; synthesis
also adds one flip-flop when recoding the four-state phase machine. This is a
synthesis count, not a routed timing result. Reproduce the current count with
`yosys -p 'read_verilog -Icpu/rtl cpu/rtl/prim.v; synth_ice40 -top Prim; stat'`.
