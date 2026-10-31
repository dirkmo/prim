# Current Forth status

The kernel has 90 words and runs its text interpreter and native-code compiler
on Prim. Python generates the initial kernel image. The default profile shares
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

| Profile | Usable dictionary after boot | Free bytes | Gain from previous cleanup |
| --- | --- | ---: | ---: |
| Dual | 30FA..EFFF | 48902 | 192 |
| UART-only | 23C8..EFFF | 52280 | 186 |

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
python3 forth/test.py --rtl --output build/forth-rest/tests
python3 vga/tests/test_forth.py
python3 audio/tests/test_forth.py
```

Validation: 99 tests passed across the RTL suites after updating/rerunning the
data-definition boundary test for compact headers; no skips. Separate VGA and
CPU/SRAM/audio-Forth regressions passed. The retained summary is
`build/forth-rest/validation.json`, including the initial report and rerun details.

[README.md](README.md) documents use, [WORDS.md](WORDS.md) the public words,
and [ARCHITECTURE.md](ARCHITECTURE.md) the current ABI. Earlier AP descriptions,
stack limits and measurements are retained in [HISTORY.md](HISTORY.md).
Simulation results do not imply physical board acceptance.
