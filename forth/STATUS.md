# Current Forth status

The standard kernel has 166 words (UART-only: 92) and runs its text interpreter
and native-code compiler on Prim. Python emits primitives, then the Prim compiler
builds higher words from `kernel/core.fs` and the standard hardware sources into
the initial image. Timer, `TIMER-EVERY`, explicit VGA output and audio are ready
without uploads; demos remain separate. `MS`, `MOVE`, `FILL` and `MARKER` are
Forth definitions in the sealed standard dictionary. Small native DP/LATEST,
context-check and COMPILE, interfaces support the Forth defining word.
The default profile shares
one dictionary and data stack between UART and PS/2/VGA; `--uart-only` selects
the polling console used by the local CPU model.

Both hardware stacks have 32 cells. There are no runtime data-stack bounds
checks or fixed eight-cell user limit. Kernel temporaries and interrupts also
use the hardware stacks. DEPTH/.S retain logical depth bookkeeping; .S scratch
is 03A0..03DF. IRQs remain masked throughout the ISR, ending in INTEI.RET.

## Dictionary and image

Headers contain link16, flags8, name-length8 and XT16, followed by the name at
+6 and optional alignment padding. Unused compilation-class/inline-opcode bytes
have been removed from both kernel and runtime headers. Words compile as calls;
literals, branch targets and return/tail-call optimizations use native Prim
instructions. The generated map format is `prim-forth-map-v2` and includes the
name and XT offsets. Older images, maps and raw dictionary layouts must be
rebuilt together; runtime definitions are not persistent.

| Profile | Usable dictionary after boot | Free bytes |
| --- | --- | ---: |
| Dual | 46BC..EFFF | 43332 |
| UART-only | 2B20..EFFF | 50400 |

Reserved SRAM and MMIO are excluded. RAM images end before FFE0; FFE0..FFFF
is MMIO, including the optional audio registers. Dual console state occupies
F000..F3FF. Generated maps are authoritative for addresses and memory regions.

`skip_lf` is emitted only for the UART-only profile; dual editors retain their
own CR/LF state. The shared variable address layout stays stable. The unused
`type_xt` alias is removed. The collector selects/recovers its source once,
then reads through the shared prepared-source entry; KEY still prepares its
source itself. Ready-line checks and loss recovery are preserved.

Error reporting uses one rollback/output/reset path and message byte spans,
with unchanged codes, messages and token suffixes. Generator helpers live in
`Code`: set_cell, advance, compile_byte, compile_cell and output.

## Build and verification

```sh
python3 forth/build.py
python3 forth/build.py --uart-only --output build/forth-uart
python3 forth/test.py --rtl --output build/forth-source/tests
python3 vga/tests/test_forth.py
python3 audio/tests/test_forth.py
```

The new bootstrap and SEE checks cover source-driven code generation,
reproducibility, source diagnostics, reset/forgotten-word protection, native
branches/strings, memory bounds, BASE/stack preservation and console IRQs.
Current validation is recorded under `build/forth-utilities-tests/validation.json`:
143 distinct Forth checks passed with RTL enabled and no skips. The expanded
real-wire system session passed on rerun with test-local retirement printing
disabled and a larger time allowance; the initial timeout report and rerun log
are retained. The session executes MOVE/FILL and MARKER over UART, checks exact
dictionary restoration, and exercises MS with actual timer IRQ callbacks.

SEE is immediate and accepts completed user words only. It prints CALL/TAIL,
unsigned literals, hexadecimal branch targets and embedded string bytes without
executing the target. It preserves BASE and the user stack; code 23 rejects a
kernel target. The original source's control syntax is not reconstructed.

Kernel-source entries in the map include their source file and definition line.
The build copies only sealed dictionary bytes, patches cold HERE/LATEST/bounds,
and adds native instructions to the disassembly. Compiler scratch and hardware
stacks from build execution are discarded. Source changes require a fresh build.
`CORE_EFFECTS` in `forth/bootstrap.py` and the ordered manifest in
`forth/libraries.py` declare stack contracts for source words. The generated
`forth_sources` map field lists compiled sources. Adding/migrating a word requires
updating this metadata and its tests. Build-time library execution that writes
peripheral registers is rejected. VGA helpers share the integrated console state.

[TODO.md](TODO.md) tracks remaining work; AGENTS.md requests a short reminder
about open items at the end of relevant Forth work.

[README.md](README.md) documents use, [WORDS.md](WORDS.md) the public words,
and [ARCHITECTURE.md](ARCHITECTURE.md) the current ABI. Earlier AP descriptions,
stack limits and measurements are retained in [HISTORY.md](HISTORY.md).
Simulation results do not imply physical board acceptance.
