# 32/32 stacks and asynchronous Forth reception

Historical baseline saved in commit `bb0eb19`; the subsequent removal of Forth
data-stack guards is documented in [FORTH_UNCHECKED.md](FORTH_UNCHECKED.md).

Date: 2026-10-31. This change supersedes the 16/16 stack and interrupt-window
policy documented in the historical AP8 results. The existing ISA and public
Forth word set are preserved. No general stack overflow protection is added;
the checked Forth user data limit remains eight cells.

The CPU RTL and Python model default to 32 cells per hardware stack. Simulator
traces and comparison scoreboards now cover all 32 cells, including wraparound,
combined return operations and nested calls through depth 32.

After console initialization, Forth keeps IRQs enabled during normal execution,
compilation, output and KEY. Only the ISR calls the source dispatcher. Its first
instruction disables IRQs and its final INTEI.RET restores them with the return;
pending requests can enter again after that return without nesting. The handler
preserves carry and user data and uses private SRAM outside the VGA bank window.
Initialization and receive-ring loss recovery use masked sections to avoid
concurrent resets of producer state. Ordinary ring consumption needs no masking.

Reception continues during a running user word; echo and interpretation remain
in foreground. Each receive ring still holds 63 raw bytes. Input can therefore
still be lost if a program does not return or consume input for long enough.
The ISR needs up to three extra data and four extra return cells. Foreground
code must leave that space; there is no automatic enforcement.

## Measured resources

Same HX8K board, 25 MHz target and routing seed 1 as the AP8 baseline:

| Resource | AP8, 16/16 | This build, 32/32 | Change |
| --- | ---: | ---: | ---: |
| Routed logic cells | 4225 / 7680 (55.0%) | 5872 / 7680 (76.5%) | +1647 |
| Synthesized LUT4 | 3518 | 4934 | +1416 |
| Flip-flops | 1054 | 1569 | +515 |
| Block RAM, 4 Kibit | 17 / 32 | 17 / 32 | 0 |
| PLLs | 1 / 2 | 1 / 2 | 0 |
| Internal routed maximum | 28.98 MHz | 30.34 MHz | Both pass 25 MHz |
| Free dual-console dictionary after boot | 44140 bytes | 44150 bytes | +10 bytes |
| Free UART-only dictionary after boot | 47534 bytes | 47534 bytes | 0 |

1808 logic cells (23.5%) remain free. LUT/FF/carry counts are components of
logic-cell usage and must not be added to it. The internal timing result is
one routed build, not evidence of a general speed improvement or of external
SRAM timing margins.

The default kernel code/table span is 16265 bytes, ending at 4389 exclusive.
Its user dictionary is 438A..EFFF (hex), leaving 44150 usable bytes immediately
after boot. The UART-only dictionary starts at 3652 and leaves 47534 bytes.
Reserved SRAM and MMIO are excluded. Hardware stack storage does not consume
external SRAM.

## Verification and reproduction

All **21 CTest suites passed**, including **93 Forth tests with no skips**.
The complete wire session measured 248 IRQ entries and peak occupancy of seven
data and nine return cells over 6063685 cycles. The deeper model fixture also
checks IRQ entry above sixteen occupied cells on both stacks. The exported
kernel matches the wire fixture byte-for-byte. Exact results, source hashes and
artifact hashes are recorded in [STACK32_RESOURCES.json](STACK32_RESOURCES.json).

The IRQ model tests inject simultaneous UART/PS2 input separately at all 845
instruction boundaries of a full-stack signed division and 117 boundaries of
banked VGA output. They compare results, data-stack storage, carry, arithmetic
scratch, video state and SRAM preservation against uninterrupted execution.
Other cases cover ISR-return handoff, non-nesting, deep stacks and reception
during each masked loss-recovery instruction. The full serial/PS2/VGA RTL case
receives more than 16 physical PS/2 bytes while a Forth word loops without KEY
or collector polling, then resumes interpretation of the buffered input.

```sh
cmake -S . -B build/sim
cmake --build build/sim -j2
ctest --test-dir build/sim --output-on-failure -j2
python3 forth/build.py --output build/stack32/forth
python3 forth/build.py --uart-only --output build/stack32/uart-only
python3 boards/olimex_ice40hx8k_evb/build.py build --output build/stack32/board
python3 tools/project.py resources --build-dir build/stack32/board
```

Artifacts: `build/stack32/board/prim.bin`, matching synthesis/routing reports,
both kernel images/maps under `build/stack32/`, and CTest/Forth logs under
`build/stack32/ctest.log` and `build/sim/forth-tests/`.
No physical FPGA programming or board acceptance is included.
