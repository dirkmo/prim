# Forth without data-stack bounds checks

The previous, validated 32/32 + asynchronous IRQ state was committed as
`bb0eb19` before this change, as requested.

The kernel no longer checks data-stack underflow or overflow at public word
boundaries, literals or runtime conditions. The fixed eight-cell user limit is
removed. Unreachable data-stack error handlers/messages are removed; error
numbers 1 and 2 are retired and the remaining error numbers stay unchanged.
Arithmetic, input, dictionary and compiler-control checks are preserved.

`Code.adjust_depth` only updates the logical depth when a word changes it.
This bookkeeping remains necessary for `DEPTH` and `.S`; it is not a bounds
check and does not protect the hardware stacks. Compiled literals and branch
conditions call renamed `literal_depth` and `branch_depth` bookkeeping helpers.
The `.S` scratch region now reserves 32 cells at 03A0..03DF. Tests exercise
display/restoration through depth 24, primitive and string results beyond eight
cells, dynamic EXECUTE, different branch effects and growing loops.

The 32/32 hardware, ISA and ISR masking policy are unchanged. Kernel temporaries
and the ISR share the physical data stack; IRQ work needs up to three data and
four return cells. There is no guaranteed maximum user depth independent of the
executed code, and stack misuse is no longer a recoverable Forth error.

## Size and instruction counts

Counts below execute the generated code on the Prim model, excluding the
caller's PUSH/CALL but including the word's return, on valid input:

| Word | Before | After | Fewer instructions |
| --- | ---: | ---: | ---: |
| SWAP | 8 | 2 | 75% |
| + | 14 | 8 | 43% |
| DUP | 20 | 8 | 60% |

Words with no net stack effect no longer need any stack bookkeeping. Words
whose depth changes retain six bookkeeping instructions. These are instruction
counts, not a cycle-level benchmark; SRAM latency and IRQs affect elapsed time.

| Profile | Previous free dictionary | Current free dictionary | Gain |
| --- | ---: | ---: | ---: |
| Dual console | 44150 bytes | 45554 bytes | 1404 bytes |
| UART-only | 47534 bytes | 48938 bytes | 1404 bytes |

The default kernel code/table span is 14861 bytes, ending at 3E0D exclusive;
the free dictionary is 3E0E..EFFF (hex) immediately after boot. UART-only user
space begins at 30D6. Reserved SRAM and MMIO are excluded from the free counts.
The FPGA bitstream is unchanged; this is a Forth image change only.

## Reproduction

Validation passed: **95 Forth tests, no skips**, including the complete
CPU/SRAM/UART/PS2/VGA wire test, plus the separate VGA-Forth regression suite.
The exported `build/forth/kernel.bin` matches the wire-test fixture byte-for-byte.
The 24-cell `.S` test also injects an IRQ during restoration/formatting and
checks that values and the adjacent scratch sentinel remain intact.

```sh
python3 forth/build.py
python3 forth/build.py --uart-only --output build/unchecked/uart-only
ctest --test-dir build/sim --output-on-failure \
  -R '^(forth_checks|vga_forth_checks)$' -j2
```

The default image, map and disassembly are refreshed in `build/forth/`, including
the `kernel.disasm` file used in the IDE. Regression logs are retained under
`build/unchecked-ctest.log` and `build/sim/forth-tests/`.
