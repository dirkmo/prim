# Shared interpreter on UART and PS/2/VGA

Implementation follows [the PS/2 work packages](../docs/PS2_CONSOLE_PLAN.md).
Each package is committed separately. Hardware AP2/AP3 already provides the
receiver, FIFO, MMIO and shared IRQ_PENDING source bits.

## AP4: output routing and integrated VGA backend

The default FPGA build (`python3 forth/build.py`) now selects the dual-console
kernel. `--uart-only` retains the original small UART-polling image for systems
without VGA/PS2; `forth/run.py` uses that profile for a host terminal. Python
`build_image()` defaults to dual; existing component fixtures explicitly request
`dual_console=False`, while dual-console checks execute the default target.

All ordinary output, including errors, prompts, number signs/spaces, EMIT,
TYPE and input echo, uses one raw emitter. `console_owner=0` selects UART;
1 selects the integrated VGA backend. User dictionary and stacks are shared.
The backend handles CR, LF, BS/DEL, line wrapping, 32-row ring scrolling,
cursor updates and display clearing. It restores every prior VGA CONTROL bit
after each mapped VRAM write, and resides below E000. It uses no extra FPGA
video storage. Eight private cells at F000..F00F are reserved initially;
software buffers and dispatcher state are added in later packages.

AP4 supplies routing/backend routines; input selection, boot prompts on both
endpoints and automatic execution ownership are completed in AP7. Kernel
images and helpers never execute inside the temporarily banked E000..EFFF
window. User definitions may still use that SRAM region between video writes.

Validation: `python3 forth/tests/test_dual.py` runs real Prim instructions
against an independent VGA/MMIO model, checking output separation, scrolling,
numeric formatting, bank restoration and physical stack bounds. Existing
UART-profile regression suites retain their original behavior.

## AP5: generic ISR and receive rings

One INTAD vector enters `irq_entry`, which starts with INTDI, saves carry once,
calls the shared source dispatcher and restores carry before INTEI.RET.
The dispatcher snapshots enabled pending sources, acknowledges each selected
bit before calling its corresponding handler, checks all sources and rescans.
UART and PS/2 handlers drain into independent 64-byte rings (63 bytes usable).
Overflow discards newest bytes and sets a sticky loss flag. PS/2 hardware
errors also set that local loss flag. Decoding and output stay in foreground.
Timer/TX are disabled at boot; their default handlers mask unexpected enabled
events and record diagnostic bits rather than looping forever.

Cold boot disables sources, drains stale hardware input, clears errors/pending,
initializes the vector/rings, then enables RX sources. CPU-only reset therefore
cannot accidentally interpret bytes retained from the previous image/session.
IRQ-private cells occupy F020..F02F. Rings reserve F100..F17F and F180..F1FF;
each uses a six-byte head/tail/loss header followed by 64 bytes of storage.

The current CPU has **32 data and 32 return cells**. After initialization,
IRQs remain enabled during ordinary Forth execution, compilation, output and
KEY. `irq_wait` is now a simple collector return point, not an enable window.
Only the ISR calls `irq_service`; foreground polling no longer reenters its
scratch. The first ISR instruction is INTDI, and INTEI.RET reenables IRQs while
returning. Prim tests IRQ acceptance after the instruction's updated enable
state, so INTDI prevents nesting and INTEI.RET completes the return before a
pending IRQ can enter again. No ISA change or hardware automatic masking is
introduced.

Dispatcher/handler/enqueue code adds at most three data cells and four return
frames including CPU IRQ entry. IRQ-private scratch does not alias arithmetic,
parser or VGA state, and all ISR SRAM accesses stay outside the banked window.
Carry is restored before returning. These budgets leave at most 29 data and
28 return cells for foreground use when IRQs are enabled. No general stack
underflow/overflow guard or reserve enforcement is added; the former eight-cell
user limit and data-stack guards have also been removed
(see [unchecked stacks](../docs/FORTH_UNCHECKED.md)). Arbitrary deep calls can
still corrupt the circular hardware stacks.

Receive rings have one ISR producer (tail) and one foreground consumer (head).
Ordinary consumption needs no masking: the ISR publishes tail after storing
the byte and the foreground publishes head after reading it; CPU memory
instructions finish before IRQ entry. Loss recovery masks IRQs across clearing
the loss flag and setting head=tail, then reenables with INTEI.RET. Initialization
also masks IRQs until the vector, buffers and source enables are ready.

Asynchronous reception continues during long-running Forth words. The rings
remain finite (63 raw bytes per source); echo and interpretation resume in
foreground. This does not introduce Forth multitasking or command preemption.

`python3 forth/tests/test_irq.py` covers simultaneous sources, ring wrap/loss,
non-nesting and ISR-return handoff, carry/scratch/stack preservation at every
instruction boundary of division and banked VGA output, and IRQs with more than
16 occupied stack cells. The full wire test receives more than 16 PS/2 bytes
while a Forth word loops without KEY or collector polling. Current results:
[32/32 validation](../docs/STACK32_IRQ.md).

## AP6: keyboard decoding

Set-2 decoding runs entirely on Prim in foreground, using three compact
128-byte normal/Shift/AltGr tables. State uses twelve cells at F040..F057.
The chosen layout is German ISO QWERTZ with ASCII output: letters/digits,
Enter, keypad Enter, BS, Tab, Escape and punctuation. AltGr-Q is @, AltGr-7/8/9/0
is `{[]}`, AltGr-ß is backslash, AltGr-plus is tilde and AltGr-ISO-< is bar.
Shift-2 supplies quotes, Shift-comma semicolon and Shift-period colon.
Unrepresentable umlauts/ß/§ and unsupported function/navigation keys emit
nothing. No dead-key composition or keyboard LED commands.

Both Shift and both Ctrl keys retain independent pressed bits. Caps toggles
once per press, not per typematic repetition, and affects letters only.
Ctrl maps ASCII letters and @.._ to control codes, with Ctrl-space producing
NUL; availability is separate from the byte value. AltGr selects its own
table before Ctrl processing. Ordinary make repeats generate repeated text;
breaks update state without text. E0 fake shifts used by Print Screen never
change Shift; the eight-byte Pause sequence is consumed completely.
BAT resets modifiers, ACK/resend replies clear prefixes, and protocol error
bytes mark local input loss for foreground recovery. A ring/frame error resets
modifiers/prefixes and discards damaged input in AP7.

Scan positions were checked against the Linux
[atkbd set-2 table](https://github.com/torvalds/linux/blob/master/drivers/input/keyboard/atkbd.c),
and German symbol positions against kbd's
[de-latin1 layout](https://github.com/legionus/kbd/blob/master/data/keymaps/i386/qwertz/de-latin1.map).
The ASCII/dead-key restrictions above are this kernel's explicit choices.
`python3 forth/tests/test_keyboard.py` executes literal scan sequences on Prim
and compares independent expected ASCII strings, modifier release, typematic,
Caps, AltGr, Ctrl/NUL, startup, unsupported sequences and recovery.

## AP7: two editors, one interpreter

Default FPGA images now boot both endpoints: initialize/clear VGA, discard
pre-prompt input and issue one `ok` prompt on each endpoint. UART stays UART;
PS/2 echo, results, prompts and errors go only to VGA. There is one shared
parser/compiler, dictionary, BASE, STATE and user stack. Switching endpoints
does not reset them or create a second session/interpreter.

Each endpoint has its own 127-byte line editor, ready/error state and CR/LF
suppression. BS/DEL edits only that endpoint; an invalid/overlong line is drained
and rejected. Partial lines cannot acquire interpreter ownership. The collector
services both endpoints in foreground and alternates complete ready lines when
both are available. It saves/restores the active owner around editing echo.
An open definition retains its owner across lines, including `[ ... ]` mode;
the other endpoint can edit/queue a line but cannot execute it until `;`, error
or ABORT releases the definition. Source buffers never mix characters.

During execution, KEY reads only its command's receive ring with IRQs enabled. Other-source input is buffered; echo is
deferred until the collector resumes. CRLF suppression belongs to the endpoint
and is also applied before KEY, so the LF of the command's CRLF is not mistaken
for the requested key. KEY does not echo a key. Arbitrary programs run to
completion and cannot be preempted by console commands; debug UART remains
available independently of the interpreter.

Input loss conservatively discards that source's queued bytes and pending
line, resets keyboard modifiers/prefixes if local, and resynchronizes at the
next Enter. It never executes a shortened command. The damaged line reports
`error: input too long` on its own endpoint. Loss during KEY aborts the current
command immediately and silently drains the resynchronizing Enter afterward,
avoiding a duplicate error. This message covers both buffer overflow and
PS/2 frame/protocol loss; it is deliberately a small shared error path.

Reserved SRAM allocation (user dictionary still ends at F000):

| Region | Use |
| --- | --- |
| F000..F07F | Output, IRQ, keyboard and collector cells; 82 initialized bytes |
| F080..F0FF | Reserved padding for console globals |
| F100..F17F | UART raw ring: six-byte header + 64-byte storage |
| F180..F1FF | PS/2 raw ring: six-byte header + 64-byte storage |
| F200..F2FF | UART editor: ten bytes of state, buffer at +16, 128 bytes |
| F300..F3FF | Local editor: same layout |
| F400..FFEF | Remaining reserved SRAM |

The total reservation is 1024 bytes from existing reserved SRAM, with 498
bytes of actual state/buffer storage. The existing 0200..027F buffer remains
the single parser input: a selected completed line is copied there. Sharing
it avoids duplicating parser/compiler state. Generated maps report the profile,
console variable addresses and console-runtime region. Kernel build rejects
any dual-console image whose kernel could execute in the banked VRAM window.

`python3 forth/tests/test_frontend.py` checks strict routing, shared definitions
and stack, concurrent/partial input, alternating ready lines, multiline locks,
KEY isolation, edit/error/ABORT behavior, overflows and decoder recovery using
the real Prim interpreter/compiler. Hardware-serial/VGA integration follows in
AP8; a Python peripheral model alone is not a board validation.

## AP8: full integration and acceptance

The integrated `forth/test.py --rtl` runner includes both profiles, all dual
model suites and a complete wire-level system case. The default dual image
runs on the real CPU/SRAM/MMIO/UART/PS2/VGA RTL, with 25 MHz clock, 115200-baud
serial traffic and 20 kHz keyboard clock. UART expectations are fixed literal
bytes; VGA checks inspect actual controller RAM, cursor/scroll and output
activity. No host-side interpreter or keyboard decoder replaces kernel code.

The wire case defines a word locally and executes it over UART, checks a local
error produces no UART output, blocks UART KEY while local input queues,
resumes KEY from UART, accepts concurrent input, scrolls through 35 CRs,
preserves SRAM behind banked VRAM, and verifies display/peripheral retention
during HALT and CPU-only reset. It also counts occupied physical stack cells
and includes IRQ PC pushes, independently of the Python model.

Model checks additionally cover foreground boundaries for both carry values,
an event at ISR return, eight user cells during formatting/WORDS, input loss
during KEY with Enter resynchronization, and cold restart with stale input.
All default and UART-only profiles retain the same public word set.

Current builds and measurements are in [STACK32_IRQ.md](../docs/STACK32_IRQ.md).
The historical AP8 results and physical acceptance checklist are in
[PS2_AP8_VALIDATION.md](../docs/PS2_AP8_VALIDATION.md). No physical FPGA
programming, keyboard-level measurement or monitor acceptance is claimed by
the automated tests. The board CMake dependency list now includes PS/2 RTL,
so receiver changes correctly invalidate an existing bitstream target.
