# Small Forth for Prim

An independent on-CPU text interpreter and native-code compiler, with 90 kernel
words. It uses the existing Prim ISA: **32-cell hardware data and return stacks,
without runtime data-stack bounds checks**. TokenForth remains a separate language/toolchain.

The default FPGA image runs one shared interpreter on **UART and PS/2/VGA**.
UART commands receive their echo/results/errors on UART; PS/2 commands receive
them on VGA. Each endpoint has a separate editor; dictionary and user stack
are shared. Open multiline definitions and KEY retain their command's source.
See [dual-console architecture, limits and verification](DUAL_CONSOLE.md).
The local Python terminal uses the UART-only profile; it does not emulate a
keyboard or display. `forth/build.py --uart-only` builds that smaller profile.

## Start here

From the project root, with Python 3.11 or newer:

```sh
python3 forth/run.py
```

Or use `make forth-console` with the project's Python environment. The kernel
runs in the Prim CPU model; the host only transports UART bytes. For example:

```text
ok
: quadrat DUP * ;
ok
7 quadrat .
49 ok
```

At a POSIX terminal the kernel handles echo and backspace. Ctrl+C exits the
simulator and restores the terminal settings. Files work through standard input:

```sh
python3 forth/run.py < forth/examples/loops.fs
```

The five [examples](examples/README.md) have independently specified expected
responses and are tested in the CPU model, through this pipe workflow and in RTL.
Finish every input line with a newline. EOF discards an unterminated last line;
an already-open definition instead receives a kernel rollback/error and exit
status 1. On hardware there is no UART EOF: the kernel waits for more input.
The simulator models RAM/UART, not timer behavior or FPGA clock timing.

## Build the kernel

```sh
python3 forth/build.py
# alternatively:
make forth-image
# or, in a configured CMake build:
cmake --build build/sim --target forth_kernel
```

Direct Python scripts need no package installation: they find the local Prim
modules. `--output DIR` selects a different destination; default `build/forth/`.
CMake's destination is its own build directory. No host TokenForth compiler or
source tokenizer is used. Each initial image is deterministic.

| File | Meaning |
| --- | --- |
| `kernel.bin` | Raw CPU RAM image, 65504 bytes, addresses 0000..FFDF, entry at 0 |
| `kernel.map.json` | Memory regions, symbol addresses, word headers/XT/flags/effects |
| `kernel.disasm` | Generated executable instructions; data and reserved RAM omitted |

Runtime definitions are written to SRAM by the CPU; they do not modify these
initial build artifacts. A fresh build/run starts with kernel words only.

## Use the existing FPGA console

These instructions assume the board already runs the matching Prim FPGA design.
The CPU RAM image is separate from the FPGA bitstream; this workflow does not
program SPI flash. No physical board validation was performed for this Forth.

```sh
make forth-image
make upload IMAGE=build/forth/kernel.bin PORT=/dev/serial/by-id/YOUR-UART VERIFY=1
make uart-console PORT=/dev/serial/by-id/YOUR-UART
```

`upload` resets/halts the CPU, loads/verifies RAM and leaves it halted. In the
console press Ctrl+B for the local debug prompt, enter `run`, then Ctrl+B to
return to CPU input. The kernel prints `ok` on UART and VGA. Ctrl+D closes this host console
without changing CPU state. For a fresh Forth session, use `reset-halt` and
`run` at the debug prompt; this forgets user definitions. The host console uses
RX-credit polling for queued CPU input. A plain terminal or uploader must pace
input: the CPU UART has a single retained RX byte, not a line FIFO.

This image ends before FFE0, so no `SKIP_UART_MMIO` option is needed. Re-uploading
it overwrites user RAM. The existing `make image`/`make load-run` targets build
TokenForth `.cf` programs; use `forth-image` followed by `upload` for this kernel.
Hardware transport needs the project's serial dependencies (`make setup`).

## Language and input

[WORDS.md](WORDS.md) documents every initial word, stack effect and context flag.
Names are ASCII case-insensitive, at most 31 bytes. A newer definition shadows
an older one. The dictionary is searched before number conversion. Words,
including `:` and `;`, need whitespace separation:

```forth
: betrag DUP 0< IF NEGATE THEN ;
-9 betrag . CR
```

Definitions may span lines: an open definition receives `compiled`/CRLF after
each successful line; otherwise the response is `ok`/CRLF. Hidden incomplete
headers are not found, so a redefinition can still reference its old meaning.
`;` publishes the word only with a balanced compiler-control stack. Nested
colon definitions are rejected.

Input lines hold at most 127 bytes plus a terminator. CR or LF ends a line;
CRLF counts once. BS/DEL deletes one byte. TAB/VT/FF are whitespace; other
control characters invalidate the whole line, except the editing/EOL controls.
An invalid or overlong line is drained through EOL before reporting its error.
KEY still returns NUL as valid data. The FPGA UART is seven-bit ASCII.

`\` ignores the remainder of a line. `(` skips through `)` on the same line,
without nesting. Comment words need their own word boundaries. Strings use
`S" text"` and `." text"`: exactly one separator after the opening word belongs
to the syntax, further spaces belong to the text. No escapes or multiline
strings; comment markers inside strings are literal data.

Cells/addresses are 16-bit, byte-addressed, little-endian. Arithmetic wraps
modulo 65536. True is FFFF and false is zero; branches accept any nonzero flag.
Signed numbers range -32768..32767; positive literals may also be 32768..65535.
BASE supports 2..36, optional signs, and `$`/`#` prefixes after the sign.
`/MOD` truncates the quotient toward zero, with remainder sign matching the
dividend; division by zero and -32768/-1 are errors. `2/` is arithmetic right
shift (rounds negative odd values down), RSHIFT is logical. See WORDS.md for
all arithmetic/stack contracts.

## Compile-time behavior and data

`[` temporarily interprets within a definition, `]` resumes compilation.
LITERAL consumes a compile-time value and emits a runtime push with DEPTH bookkeeping:

```forth
: answer [ 20 22 + ] LITERAL ;
```

IMMEDIATE marks the latest completed user word. Such words run while compiling:

```forth
: forty-two 42 ; IMMEDIATE
: answer forty-two LITERAL ;
```

`' name` parses at execution time and returns an XT. `['] name` compiles that
XT as a literal. EXECUTE consumes the XT and invokes its word. STATE is a readable
mode variable (0 interpret, 1 compile); change modes through the compiler words.
Directly writing STATE or private kernel variables is unsupported.

IF/ELSE/THEN and BEGIN/UNTIL, BEGIN/AGAIN, BEGIN/WHILE/REPEAT use a separate
32-entry typed control stack. IF/UNTIL/WHILE consume one runtime flag. One
unmatched WHILE is allowed per BEGIN; nested loops/conditionals are supported.
DO/LOOP and public return-stack words are deliberately absent.

HERE is the next free byte. UNUSED returns the remaining dictionary/data bytes
(`F000` minus HERE); `UNUSED U.` prints the count as an unsigned number.
ALLOT accepts 0..32767 bytes and does not clear them.
`,`/`C,` store a cell/low byte and advance HERE. CREATE defines a body-address
word; VARIABLE adds one zeroed cell; CONSTANT defines a stored value. These
execute only outside open definitions, and may be used by simple defining
words. No DOES> behavior is implemented.

Interpreted S" returns a temporary address/length valid until the next
interpreted S" or reset. ." does not overwrite that buffer. Compiled S" refers
to persistent embedded bytes; compiled ." uses private temporaries and works
even with eight occupied user cells. TYPE consumes address/length and writes
bytes; length zero performs no read. Ordinary output follows the selected
command endpoint: seven-bit UART or the integrated VGA text backend.

## Errors, reset and limits

Errors print a reason (and the unknown/compile-only token when relevant),
discard the current line and user data, and resume with `ok`. An open definition
rolls HERE/LATEST back to their saved values before the state is cleared.
ABORT takes the same non-returning path without an error message. Completed
words survive both. Arbitrary immediate-word side effects are not rolled back.
A CPU reset rebuilds the dictionary pointers to kernel-only state; SRAM bytes
may remain, but user words are forgotten. No persistence or image-save facility.

The hardware stacks have 32 cells each. There is no fixed eight-cell user limit
and no runtime underflow/overflow check for either hardware stack. `DEPTH` and
`.S` retain software depth bookkeeping; internal temporaries are not counted.
Programmers must leave room for kernel temporaries and ISR work (up to three
data and four return cells), so 32 physical cells are not 32 freely usable user
cells. `.S` has a 32-cell scratch buffer at 03A0..03DF; it does not validate depth.
The dual-console interrupt policy is described in [DUAL_CONSOLE.md](DUAL_CONSOLE.md).
Current size and performance results: [unchecked stacks](../docs/FORTH_UNCHECKED.md).
Tail calls reduce return depth but cannot remove every live caller frame.

Code/data allocation is confined to USER_START..EFFF, with USER_START from the
generated kernel map. F000..FFDF is reserved; FFE0..FFFF is MMIO. Stack display,
string and arithmetic scratch have separate regions. There is no memory
isolation: arbitrary !/C!/EXECUTE operands can corrupt the kernel. Nontermination,
invalid XT and hardware-stack overflow are not recoverable Forth exceptions.
The dual kernel reserves F000..F3FF for console state and buffers. Interrupts
remain enabled during ordinary Forth execution and KEY. The ISR masks IRQs
until its INTEI.RET; initialization and receive-loss recovery also use short
masked sections. Input is buffered asynchronously, while interpretation and
echo remain in foreground. Finite receive rings can overflow during long-running
code; input loss requires Enter to resynchronize. See
[32/32 validation](../docs/STACK32_IRQ.md) for current measurements.
No floating point, files, user interrupt API, CATCH/THROW or standards compliance claim.

Private `last_error` at 0126 retains the last code (zero after reset):

| Codes | Meaning |
| --- | --- |
| 3–5 | Shift range, zero divisor, quotient overflow (codes 1–2 retired) |
| 6–10 | Line too long, open comment, invalid BASE, invalid text control, numeric overflow |
| 11–15 | Unknown word, compile-only word, compiler context, invalid name, dictionary full |
| 16–21 | No user word for IMMEDIATE, unresolved control, simulator EOF in definition, control stack full, invalid ALLOT, open string |

## Verification and implementation reference

```sh
python3 forth/test.py --rtl
# alternatively:
make test-forth
ctest --test-dir build/sim -R '^forth_checks$' --output-on-failure
```

The runner accepts `--output`, `--iverilog` and `--vvp`. Without `--rtl`, software
checks run and the report explicitly records the intentional RTL skips. Full
runs require Icarus/vvp. CTest's overall setup also needs the installed project
package, CMake, Verilator and a C++17 compiler; see [repository tests](../docs/TESTS.md).

The retained report includes commands, exit codes, timings, tools and test/skip
counts. Logs and initial kernel artifacts live under build/forth-tests/ (CTest:
build/sim/forth-tests/). Serial-system source, expected bytes and captured TX
are retained under artifacts/system/. Tests cover independently expected math,
compiler rollback/limits, return-bit/tail-call behavior, instruction retirement
through three SRAM timings, UART-buffer sessions and actual RTL serial RX/TX
with debug-q credit and debug HALT. Examples are executable documentation.
The Forth-specific SRAM bench copy raises only its watchdog; SRAM timings and
RTL are unchanged. Simulation results are not a physical board validation.

- [Word reference](WORDS.md)
- [Examples and golden responses](examples/README.md)
- [Architecture and private ABI](ARCHITECTURE.md)
- [Compact handoff and completed work packages](STATUS.md)
