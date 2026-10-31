# Shared interrupt pending register

Timer, UART RX, UART TX and optional PS/2 share the CPU's single IRQ input.
The CPU retains one coalesced request while masked/halted; its pending bit
does not identify the source. `memory_io` therefore retains four source bits.

| Address | Read | Write | Reset |
| --- | --- | --- | --- |
| FFF5 IRQ_PENDING | Bits 0 timer compare, 1 UART RX, 2 UART TX slot release, 3 PS/2 input/error; 7:4 zero | W1C bits 3:0; ignore 7:4 | 0 |

Read is nondestructive; writing zeros preserves pending. Source enables remain
in their device CSRs: timer FFF4 bit 2, UART FFFE bits 2/3, PS/2 FFFB bit 2.
There is no duplicate mask register. Disabling a source preserves its pending
bit. Software dispatches `IRQ_PENDING & enabled_mask` and handles every selected
source, since simultaneous pulses and multiple events can coalesce.

Source events use the enable before their event edge. The UART exposes
separate qualified RX/TX pulses in addition to its existing combined pulse.
Timer compare and PS/2 accepted-byte/receive-error events have their own bits.
A same-edge event wins W1C: `next = (pending & ~ack_mask) | events`.
Reading peripheral DATA does not acknowledge source pending; acknowledge the
snapshot bit **before** calling/draining its handler. Rescan after handling.
This preserves an event that occurs during handler execution. Events do not
count occurrences; exact timer counts need a different software/hardware policy.

The CPU gets synchronous event pulses, plus replay when a source is re-enabled
with retained pending. Enabling UART RX with unread RXAVAIL also seeds a pending
event; enabling PS/2 RX with FIFO data or sticky errors does likewise. Initial
UART TXFREE and timer COUNT=COMPARE are readiness/state, not old events, and do
not seed pending. These replay rules belong to the system; the standalone UART
component's existing combined IRQ still reports only actual RX/TX events.
Consecutive source events can keep the sampled IRQ asserted on adjacent clocks.
An already retained CPU request can lead to a later empty ISR entry; safely
return without calling unrelated handlers.

The CPU entry is still configured by INTAD and enabled by INTEI. Install one
generic dispatcher, begin it with INTDI, save/restore interrupted state, and
finish with INTEI.RET. Software ISR implementation and stack/carry proof are
AP5, not part of this hardware addition. Only enable sources with handlers.

## Word access and compatibility

FFF5 was previously the unused high byte of timer CSR. Timer COUNT/COMPARE
stay 16-bit registers; timer control remains FFF4 bits 2:0. A word read at FFF4
now includes pending in its high byte. A word write there sets control from
the low byte and acknowledges pending from high-byte ones, in two byte phases.
Existing writes such as `5 FFF4 !` have zero high byte and preserve pending.
Avoid whole-word read/modify/write of timer CSR: it could acknowledge read
pending bits. Prefer byte writes for control and acknowledgment independently.
High-only access to FFF5 does not write timer control or restart its divider.

Words touching IRQ_PENDING, VGA or PS/2 are serialized lower address first;
each selected byte completes exactly once and can take effect before the final
word ACK. Selected bytes at FFF4/FFF5 and FFF5/FFF6 are independent operations.
All other timer/SRAM/UART lanes retain their previous path. Unselected bytes
have no effects. Debug-master reads/writes obey the same contract.

System reset clears pending and device enables. CPU-only reset clears the
CPU's pending/global-enable/vector state but preserves this register and all
peripheral state. Forth boot must disable sources, install vector/handlers,
discard stale input, clear errors/pending, then enable receive sources and
global IRQs. Loader exclusion remains FFF0..FFFF; no extra SRAM is hidden.
