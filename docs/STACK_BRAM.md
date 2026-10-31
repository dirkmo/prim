# CPU stacks in block RAM

The CPU retains 32 data cells and 32 return cells, the existing ISA, circular
pointer behavior, cached T/N, and instruction-boundary HALT/STEP/IRQ semantics.
Each stack is split into even and odd addresses, using four iCE40 EBRs in total.
Adjacent cells can then be read together through synchronous memory ports.
Neither stack storage nor its read registers need a reset.

FETCH and MEMWAIT prefetch data cells three/four and return cells one/two.
The read outputs are held through execution, so the design does not depend
on the EBR's behavior when a read collides with a write. The data stack's
additional writes are serialized: CLEAN clears consumed cells or updates the
third cell for ROT/-ROT; EXECUTE writes the new T/N cells and retires the
instruction. This preserves clearing and wraparound behavior without a
multi-write register array. Return-stack pushes retain the existing single
write; combined R>.RET/RDROP.RET use both prefetched return cells. >R.RET
returns through T without writing return-stack storage.

Data-stack pops (including arithmetic, CALL/JP/JZ and stores) and ROT/-ROT
take one additional system clock. Other instructions retain their previous
latency. CLEAN has no bus transaction; IRQ pulses remain pending until
retirement, and HALT/STEP finish the instruction. IRQ entry still takes one
clock. The Forth ISR still begins with INTDI and ends with INTEI.RET, preventing
nested handlers. No Forth sources or external SRAM layout were changed.

## Measured board results

Olimex iCE40HX8K-EVB, HX8K/CT256, 25 MHz, nextpnr seed 1, with VGA, PS/2,
UART/debug and audio enabled. The baseline is `build/audio-bram`; its cell
types, parameters and connections matched a fresh synthesis of the previous
RTL during review. The new complete build is `build/stack-bram/board`.

| Resource | Before | After | Change |
| --- | ---: | ---: | ---: |
| Routed logic cells / 7680 | 6733 | 3458 | -3275 |
| Synthesized LUT4 / 7680 | 5573 | 2816 | -2757 |
| Synthesized flip-flops / 7680 | 1923 | 896 | -1027 |
| Block RAM, 4 Kibit / 32 | 18 | 22 | +4 |
| PLLs / 2 | 1 | 1 | 0 |
| Internal routed maximum | 28.67 MHz | 27.87 MHz | Both pass 25 MHz |

4222 logic cells (55.0%) and ten EBRs remain free. LUT/FF/carry are components
of logic cells and must not be added to the routed count. These are measured
synthesis/place-and-route results, not estimates. The reported Fmax is from
one routed build and does not measure program throughput; affected instructions
take the extra CLEAN clock at the unchanged 25 MHz operating frequency.
The bitstream was built but was not programmed or tested on a physical board.

## Verification and reproduction

All 24 CTest suites passed: the 23 existing suites and the added mapped-cell
test. The full Forth run passed 99 tests with no skips; the separate Python
test-helper run passed 16 tests. Source/build hashes and exact utilization
are recorded in [STACK_BRAM_RESOURCES.json](STACK_BRAM_RESOURCES.json).

The existing CPU comparison suite covers every occupied stack depth, repeated
pointer wraparound, combined return operations, nested calls and randomized
instruction sequences. Debug/IRQ tests cover delayed bus ACK, masking,
simultaneous requests, CALL/return collisions, HALT and STEP.

The added `stack_bram_checks` independently synthesizes the CPU, requires four
SB_RAM40_4K cells and fewer than 256 flip-flops, then simulates the mapped
iCE40 cells. Its black-box bus trace must match the Python ISA exactly while
both pointers wrap repeatedly, data are drained to SRAM, combined returns
cross bank boundaries, and ACK delays vary. Simulation-only hierarchical
stack views are excluded from that netlist. A pulse during a store and another
inside the masked ISR check pending IRQ delivery at INTEI.RET, using the actual
mapped BRAM cells for the return-stack pop/push sequence.

```sh
cmake -S . -B build/sim
cmake --build build/sim --target simulator -j2
ctest --test-dir build/sim --output-on-failure -j2
python3 boards/olimex_ice40hx8k_evb/build.py build --output build/stack-bram/board
python3 tools/project.py resources --build-dir build/stack-bram/board
```

The mapped-cell CTest requires Yosys and yosys-config. The board directory
contains the matching `prim.json`, `synth.log`, `nextpnr.log`, `timing.json`,
`prim.asc` and `prim.bin`.
