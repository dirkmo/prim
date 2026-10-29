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
