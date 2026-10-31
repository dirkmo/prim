# PS/2 keyboard and two console transports

Planning baseline: 2026-10-31. This document proposes work packages; it does
not claim an implemented PS/2 controller or dual-console Forth.

AP1 is complete: see [the board and interface contract](PS2_AP1_CONTRACT.md)
and [the measured resource baseline](PS2_AP1_BASELINE.json). The AP1 contract
resolves the provisional register/dispatch choices below and governs AP2 onward.

## Required behavior

- One on-CPU Forth interpreter/compiler, one dictionary and one pair of user
  stacks. UART and local console share definitions and stack contents.
- PS/2 input uses VGA for echo, results, prompts and errors. UART input uses
  UART for all of these. Normal console output is never broadcast.
- Each transport has its own receive queue, line buffer, editing state and
  CR/LF state. Characters from different transports never form one command.
- The interpreter executes one command at a time. At an idle command boundary,
  complete lines are selected fairly, alternating when both are ready.
- The selected transport owns execution through the final response. Ownership
  continues across an open multiline definition and blocking KEY calls; KEY
  reads only that owner's input. A partial line alone does not acquire ownership.
- Errors and ABORT report to the owner, roll back unfinished compilation and
  release ownership after recovery. The other console can then proceed.
- While a program runs, the other console may buffer input, within documented
  limits. It cannot execute commands until the current program yields control.
  A nonterminating program can therefore block both consoles. No multitasking
  or interpreter reentry from an interrupt is planned.
- Idle editing echo is directed explicitly to its source. Input arriving on
  the inactive console during execution is queued and echoed when serviced.
  Boot initializes both endpoints and issues one readiness prompt per endpoint.
- Explicit device words such as VGA-EMIT remain explicit device operations;
  automatic routing applies to the ordinary Forth console words and diagnostics.

## Existing integration points

The CPU already accepts synchronous IRQ pulses and retains a coalesced pending
request while masked/halted. Timer and UART IRQs are already combined in
`system/rtl/prim_system.v`. The initial Forth kernel disables interrupts and
polls UART. Several output helpers in `forth/kernel/` write UART directly;
changing only EMIT would leave prompts and errors on the wrong endpoint.

VGA occupies FFF6..FFFA and banks VRAM over E000..EFFF. FFFB and FFFC are
available for PS/2 without moving timer, LEDs or UART. The existing
`vga/examples/console.fs` provides output behavior to reuse, but its bank helper
is not interrupt/reentrant safe and is not an integrated kernel backend.

## Resource constraints

Resource efficiency is an explicit implementation requirement. Reuse the
existing CPU, system clock, VGA controller, UART and single Forth kernel.
Do not duplicate the interpreter, dictionary, user stacks or VGA memory for
the second console. Keep scan-code decoding, key mapping, line editing and
console arbitration in software rather than adding hardware state machines
for those functions.

- Start with the proposed 16-byte PS/2 FIFO; make its depth a build-time
  parameter. Use compact inferred storage and compare synthesis results rather
  than forcing a dedicated block RAM for a tiny queue. Existing UART buffering
  remains unchanged unless measurements demonstrate a need to change it.
- Place software receive rings and the two bounded line buffers in external
  SRAM. Size them explicitly for the documented behavior; do not add large
  speculative queues. Share parser/compiler scratch and the execution input
  buffer where lifetimes permit, while retaining independent pending input
  and editing state for each endpoint. Define whether arbitration copies a
  ready line or selects its buffer, choosing the smaller safe implementation.
- Use one context-save/restore path in the generic ISR and short device
  handlers. For the small fixed source set, prefer a compact static sequence
  of pending-bit tests and direct calls over a dynamic registration framework.
  This sequence is the source-to-handler mapping; keep a defined handler ABI
  and make future sources easy to add. Add a runtime table only if needed.
- Add only the pending bits needed to identify shared interrupt sources.
  Reuse persistent receive status where it meets the pending/acknowledgment
  contract; latch transient events separately. Do not add per-source counters
  when coalescing is sufficient. Prefer existing register space for new flags
  if compatible; extend the MMIO map only when necessary.
- Share output formatting, parsing and editing routines between transports.
  Keep backend differences in small key/emit primitives. Use a compact
  scan-code lookup representation and support the documented initial key set.
- Keep CPU stack sizes unchanged. Include dispatcher and handler call depth
  in the interrupt headroom proof; avoid deep helper-call chains in the ISR.
  Resource savings must preserve correct routing, event handling and visible
  overflow reporting.

AP1 records a reproducible baseline for the current board target and kernel.
AP3/AP5/AP7 report incremental LUT/logic-cell, flip-flop, EBR, kernel-image and
reserved SRAM costs as applicable. AP8 compares the complete implementation
with that baseline using the same synthesis/routing settings and verifies
25 MHz timing. Record actual buffer capacities, remaining user-dictionary
space and maximum interrupt stack use. Do not invent unmeasured size targets;
justify material increases and remove unnecessary duplication before acceptance.

## Proposed minimal hardware contract

Receive-only Verilog: synchronized/filtered clock and data, falling-edge frame
sampling, start/stop and odd-parity validation, partial-frame timeout and a
16-byte raw scan-code FIFO. Use the existing system clock throughout; PS/2
clock is data, never an internal RTL clock. Emit only valid bytes. Full FIFO
drops the newest byte and records overflow; it must not overwrite older bytes.
No ASCII conversion, host transmit engine, LED commands or mouse support in
this version. Assume a keyboard sending scan-code set 2 after power-up; command
negotiation and devices requiring explicit initialization are later extensions.

| Address | Proposed contract |
| --- | --- |
| FFFB, CSR | Read: bit 0 RXAVAIL, bit 1 FULL, bit 2 RXIE, bit 3 FRAMEERR, bit 4 OVERFLOW; remaining bits zero. Write: replace RXIE from bit 2, clear sticky errors by writing ones to bits 3/4. |
| FFFC, DATA | Read oldest raw byte and pop exactly once for a completed selected bus lane; empty read returns zero without a pop. Writes ignored. |

Errors include parity, framing and timeout; a concurrent new error wins over
clearing. Concurrent FIFO pop/push, including full/empty boundaries, must have
an explicit tested ordering. Byte masks, unaligned words, adjacent VGA/LED
registers and debug-master reads must obey the existing byte-addressed bus.
DATA reads by the debug master also consume input.

RXIE generates a one-cycle source event for each accepted byte or receive error,
including enabling RXIE with data/errors already queued. Software drains the FIFO, rather
than counting interrupts. Pending data and errors remain readable by polling.
System reset clears FIFO, flags and RXIE; CPU-only reset preserves peripheral
state, so Forth boot disables/reinitializes sources before installing its ISR.

## Generic ISR and source dispatch

Multiple peripherals share the CPU's single IRQ input: timer, UART RX/TX and
PS/2, with room for future sources. Install one generic ISR entry using INTAD;
individual device handlers are called by this dispatcher, not installed as
competing CPU vectors. The shared IRQ pin and the CPU's single pending bit
cannot identify which source fired or how many events occurred.

Each source therefore needs independently readable pending state and an enable
mask. A transient pulse or a readiness bit alone is insufficient to identify
an event after delayed service, particularly for timer and UART TX. AP1 must
audit existing sources and define retained pending/acknowledgment semantics;
AP3 adds missing hardware state. AP1 selected FFF5, the previously unused
upper byte of timer CSR, as a four-bit shared IRQ_PENDING register with W1C
acknowledgment. Derive masks from existing source enables; no extra mask
register or MMIO-window extension is needed. See the contract for the explicit
change to timer word access behavior and source bit assignments.

The dispatcher follows this contract:

1. Disable nesting and preserve the interrupted execution context once.
2. Read all enabled pending sources without consuming their data.
3. For each pending source, acknowledge its snapshot bit before calling its
   registered handler in the documented order. This preserves events arriving
   during a handler.
   Check every source, not an exclusive if/else chain; simultaneous events must
   invoke all corresponding handlers.
4. Acknowledge only selected events according to the source's contract. A new
   event concurrent with acknowledgment wins and remains pending. Receive
   handlers drain available data into their separate software rings; event
   handlers use the dispatcher's prior event acknowledgment. Coalescing is explicit; use a
   counter if a future source requires exact event counts.
5. Rescan for events arriving during dispatch, then restore context and finish
   with INTEI.RET. A request arriving at the final check/return boundary must
   remain pending and trigger subsequent service. An entry with no enabled
   pending source returns safely without calling an unrelated handler.

Use a compact static source-to-handler mapping with a defined handler ABI,
as described under resource constraints. Adding a source extends this mapping and its
status/acknowledgment support, without replacing the generic ISR. Handlers
remain short, preserve their documented registers/stacks and private state,
and do not run the Forth interpreter or perform console output. Define safe
handling of an enabled source without a registered handler, so it cannot
produce an endless interrupt loop. Only sources with installed handlers are
enabled at boot; unused timer and UART TX sources remain disabled.

## Work packages

| Package | Scope and deliverable | Acceptance / dependencies |
| --- | --- | --- |
| AP1: Board and interface contract | Trace PS2_CLK/DATA through local Rev.A/Rev.B netlists, document FPGA balls, connector pins, resistor network, pull-ups and voltage levels; finalize CSR and reset/IRQ semantics. Audit pending, enable and acknowledgment support for every shared IRQ source; assign any additional MMIO addresses. | GPIO1.14 is clock and GPIO1.16 is data in the expansion snapshot. Confirm complete electrical path before hardware use; no UART/VGA pin collision. Every source remains identifiable after masked/HALT service delays. |
| AP2: PS/2 receiver | Add `ps2/rtl/ps2_rx.v`, synchronizers, glitch filter, frame validation and timeout, with standalone simulation. | Valid frames, all byte values, asynchronous phase variation, glitches, parity/stop/start errors, interrupted frames and recovery. Depends on AP1. |
| AP3: FIFO, MMIO and interrupts | Add FIFO/CSR wrapper, PS2_ENABLE parameter, system IRQ connection, top-level pins, constraints and build sources. Implement missing per-source retained pending/acknowledgment state for generic dispatch. Preserve disabled-feature behavior. | Burst ordering, overflow, simultaneous push/pop, IRQ enabling/coalescing, masked/HALT behavior, reset, byte/word lanes, ACK exactly-once consumption and VGA/LED crossings. Check simultaneous source events and event/acknowledgment races. Depends on AP2. |
| AP4: Kernel console routing and VGA backend | Introduce private transport-aware key/emit helpers; route public KEY/EMIT/TYPE, numeric output, echo, prompts, compiler messages and errors through them. Integrate VGA initialization, cursor, backspace, wrapping and scrolling into the kernel. | UART-only regression stays valid; every ordinary output path reaches its selected backend. Bank access restores the previous control value and cannot expose mapped VRAM to interrupted code. Depends on AP1; can precede AP3. |
| AP5: Generic ISR dispatcher and device handlers | Install one non-nesting ISR with common context save/restore, source-to-handler mapping, pending-source checks and rescan. Add separate UART and PS/2 receive handlers and SRAM rings; keep decoding/output in foreground code. Define handler ABI, ring limits and loss reporting. | Demonstrate carry, data/return-stack and scratch preservation including dispatcher/handler call depth within the existing 16-cell hardware stacks. Test each source, simultaneous sources, events during handlers and return, empty entries and unregistered-source handling. Do not enable unused timer/TX IRQs. Depends on AP3/AP4. |
| AP6: Keyboard decoding | Decode set-2 make/break, E0/F0, both Shift keys, Ctrl, Caps Lock and typematic; use an explicit German QWERTZ mapping with ASCII output initially. Support Enter, backspace, space and punctuation required for Forth. Handle startup/status bytes and consume unsupported sequences such as Pause/Print Screen without emitting stray characters. | Table-driven key sequences, independent modifier release, punctuation, repeated keys and recovery after malformed/lost input. On overflow discard the damaged line and reset decoder modifiers/prefix state, reporting locally. Depends on AP5. |
| AP7: Single-interpreter arbitration | Add independent line/edit buffers, per-source CR/LF handling, complete-line selection, execution owner and owner-aware KEY. Retain ownership during multiline compilation and release correctly after completion/error/ABORT. Update RAM layout and image-size checks. | Simultaneous lines never mix; other-source partial input cannot steal execution; multiline definitions and KEY stay with the owner. Shared dictionary/stack behavior is explicit and tested. Depends on AP4/AP5/AP6. |
| AP8: End-to-end and board validation | Add serial/PS2/VGA system tests and documentation, run regressions and synthesize/route the 25 MHz board target. Then perform physical keyboard/monitor/UART checks. | UART commands produce no VGA console output; PS/2 commands produce no UART console output, including echo/errors/prompts. Definitions created on either endpoint work on the other. Verify concurrent input, HALT/RUN, boot/reset, overflow, long output, scrolling and resource/timing deltas. Depends on AP7. |

AP5 must settle interrupt stack/carry safety before interrupts are enabled in
the kernel. If the existing stack budget cannot accommodate the ISR, revise
the service routine or reserve verified kernel headroom explicitly; do not
silently reduce the public stack guarantee or grow the CPU stacks.

VGA mapping helpers and ISR code/data must reside outside E000..EFFF. The ISR
must not touch VGA banking or shared arithmetic/parser scratch. Reserve the
additional rings, line buffers and decoder state explicitly rather than
assuming spare space in the existing 0100..03FF layout. Every queue has a finite
capacity; prolonged HALT or long-running programs may lose keyboard input.
Transport-specific overflow must be visible, never silently execute a truncated
command. UART host credit behavior must remain compatible with its one-byte
hardware receive slot.

Suggested order: AP1 -> AP2 -> AP3; AP4 can proceed after AP1. Then AP5 -> AP6
-> AP7 -> AP8. Physical acceptance is a separate, recorded result after the
simulation and routed build checks.
