# AP1: PS/2 board, MMIO and shared interrupt contract

Completed design work: 2026-10-31. This is the implementation contract for
AP2 onward, not a description of new implemented registers. Current RTL is
unchanged. The parent plan is [PS2_CONSOLE_PLAN.md](PS2_CONSOLE_PLAN.md).

## Board wiring and electrical path

Source snapshots: [expansion Rev.A](../boards/netlists/ICE40-IO_Rev_A.net),
[FPGA board Rev.B](../boards/netlists/iCE40HX8K-EVB_Rev_B.net), with provenance
and checksums in [the netlist README](../boards/netlists/README.md).

| Top-level input | Expansion net | GPIO_In1 / GPIO_Out1 / main GPIO1 | FPGA U4 ball | PS2_KEYBOARD1 contact |
| --- | --- | --- | --- | --- |
| `ps2_clk` | `/PS2_CLK` | 14 | G1 (`PIO3_25/IOL_13B`) | 5, through R18 (200 ohm) |
| `ps2_data` | `/PS2_DATA` | 16 | J5 (`PIO3_24/IOL_13A`) | 1, through R14 (200 ohm) |

PS2_KEYBOARD1 contact 4 is +5V, supplied through GPIO1.1; contact 3 is GND.
Expansion GPIO1.2/4/8 are GND. Clock and data are on bank 3; its supply balls
E1/G6/J6/N1 connect to +3V3 in the main-board snapshot. Neither G1 nor J5 is
assigned in the current board constraints; they are distinct from all SRAM,
VGA and UART pins. UART remains E4/B2, GPIO1.5/7.

Each signal has a 5.6 kohm pull-up to +5V on the FPGA side of its 200 ohm
series resistor (clock R10, data R11), and a 10 kohm pull-down to GND
(clock R21, data R22). Thus the released-line nominal FPGA voltage is
`5 * 10 / (5.6 + 10) = 3.205 V`, before keyboard loading and tolerances.
This is a resistor divider, not a direct 5V connection or an active level
translator. With the connector contact held at zero, the calculated FPGA
voltage is approximately 0.169 V. These are circuit calculations, not readings.

The [Lattice iCE40 LP/HX data sheet, table 4.13](https://www.latticesemi.com/-/media/LatticeSemi/Documents/DataSheets/iCE/FPGA-DS-02029-4-3-iCE40-LP-HX-Family-Data-Sheet.ashx?document_id=49312)
specifies LVCMOS3.3 VIL max 0.8 V, VIH min 2.0 V and VIH max VCCIO+0.2 V.
The nominal divider calculations fit these limits at 3.3 V VCCIO. The netlist
does not specify resistor tolerances, keyboard internal pull-ups or measured
supply extremes: nominal agreement does not prove every keyboard's electrical
margin. AP8 records idle/low voltages and transitions for the actual assembly
and keyboard, especially any rise caused by keyboard-side pull-ups. No physical
electrical test has been performed in AP1.

AP3 adds G1/J5 as plain inputs, with no internal pull-up/pull-down and no output
driver. The board's existing resistor network supplies bias. Receive-only
operation needs no open-drain output buffers; future host-transmit support
must use low-or-high-impedance drive, never actively drive a released line high.

## Receiver contract for AP2

One 25 MHz clock domain. Synchronize each asynchronous input through at least
two flops, then filter clock transitions before detecting falling edges.
Default filter: eight consecutive equal synchronized samples; parameterize
the filter length. Sample synchronized data on the qualified clock edge.
Validate an 11-bit frame: low start, eight data bits LSB first, odd parity,
high stop. A non-start edge while idle does not produce a byte.

Use a parameterized 2 ms inactivity timeout while a frame is in progress,
restarted by each qualified falling edge. Derive its cycles from CLK_HZ;
at 25 MHz the threshold is 50000 clocks. Reset returns the receiver to idle
and initializes input history to released/high. Bad parity/stop or timeout
reports a frame-error event and discards the frame. The next valid start can
begin recovery. AP2 verifies filter/data alignment over asynchronous phases
and back-to-back frames. No derived clock, transmit engine or scan decoder.

## PS/2 register contract for AP3

PS2_ENABLE defaults to zero for existing system integrations; the board opts
in when AP3 is implemented. When disabled, FFFB/FFFC retain zero reads and
ignored writes, with no PS/2 IRQ. Default FIFO depth is 16 raw bytes, a
power-of-two build parameter. Store raw 8-bit scan codes, not ASCII.

| Address | Read | Write |
| --- | --- | --- |
| FFFB PS2_CSR | Bit 0 RXAVAIL; bit 1 FULL; bit 2 RXIE; bit 3 FRAMEERR; bit 4 OVERFLOW; bits 7:5 zero | Replace RXIE from bit 2. Bits 3/4 are write-one-to-clear errors; other bits ignored. |
| FFFC PS2_DATA | Oldest byte; selected completed lane pops once. Empty read returns zero. | Ignored |

System reset: FIFO empty, flags and RXIE zero; reset FIFO pointers/count,
not the storage array. CPU-only debug reset/HALT preserve all peripheral
state. Software must check RXAVAIL; zero is a valid received byte.

Simultaneous pop/push: return the old head and enqueue the new byte. A full
FIFO accepts a new byte when a successful pop occurs on the same edge;
otherwise discard the newest byte and set OVERFLOW. An empty read concurrent
with reception returns zero without consuming the new byte. A new error wins
over a same-edge W1C. FRAMEERR includes receiver parity, stop and timeout
errors. Foreground decoding recovers from either error class by discarding
the damaged line and resetting modifier/prefix state, with a local diagnostic.

RXIE gates byte/error event notifications. Each accepted byte or new receive
error occurrence produces a source event; repeated errors still count as
events even if a sticky error flag was already set. Enabling RXIE with queued
data or sticky errors also produces an event. Use pre-edge enables for events
concurrent with a CSR write, including an event on the edge disabling RXIE.
Such an event remains pending but is masked from dispatch after disabling;
a CPU request already generated can cause an empty ISR entry. Unread data and
sticky errors remain available to polling. Exact event/enable collisions must
be tested against this specified priority rather than inferred from coding order.

All selected byte lanes use the existing byte-addressed, little-endian bus.
Transfers touching PS/2 are serialized lower address first, like VGA accesses.
Each side effect occurs once at completion of its selected byte transfer;
an outer word ACK may occur later. CSR+DATA words return CSR before consumption.
An unselected DATA lane never pops; stalled/repeated requests never pop twice.
Test FFFA/FFFB, FFFB/FFFC and FFFC/FFFD crossings as well as all byte masks.
Debug-master DATA reads have the same consumption side effects as CPU reads.

## Shared interrupt source audit and decision

Current behavior, before AP3:

| Source | Existing enable | Existing readable state | Missing for reliable dispatch |
| --- | --- | --- | --- |
| Timer compare | FFF4 bit 2 INTEN; timer runs when bit 0 ENABLE | COUNT/COMPARE; neither proves a past event | Retained source event |
| UART RX | FFFE bit 2 RXIE | Bit 0 RXAVAIL; DATA read consumes it | Separate event identity after other reads/consumption |
| UART TX slot becomes free | FFFE bit 3 TXIE | Bit 1 TXFREE is readiness, including initial idle | Retained event distinct from initial readiness |
| PS/2 RX/errors (new) | FFFB bit 2 RXIE | FIFO nonempty and sticky errors | Shared-dispatch source identity |

The CPU has one coalesced pending bit, not a source vector. Existing
`uart_buffers.o_irq` merges RX/TX events and `timer.o_irq` is transient.
AP3 exposes separate RX/TX event pulses to the system while preserving the
reusable UART's existing combined output. Add a small system-level pending
block with four bits; keep the standalone timer independent of this block.

Use **FFF5 IRQ_PENDING**, the previously unused upper byte of timer CSR.
No MMIO window or SRAM/loader exclusion is extended. Timer controls remain
at FFF4 bits 2:0; aligned words at FFF4 now include pending in their high byte.
Existing control writes with a zero high byte do not clear pending. Software
must avoid read/modify/write of the entire timer CSR word because read ones
in the high byte become acknowledgments. Use byte writes for independent
control/acknowledgment. This is an explicit future change from today's
documented zero high byte and ignored writes; update register references and
timer/debug regressions in AP3. Also intercept FFF5 in mixed/unaligned words;
do not forward its acknowledgment writes as timer control writes.

| IRQ_PENDING bit | Source | Handler |
| --- | --- | --- |
| 0 | Timer compare event | Timer handler, installed before enabling INTEN |
| 1 | UART CPU RX event | UART receive-ring handler |
| 2 | UART CPU TX-slot-free event | Optional TX handler; TXIE remains off for initial console |
| 3 | PS/2 accepted byte or receive-error event | PS/2 receive-ring/error handler |
| 7:4 | Reserved, read zero, ignore writes | None |

Read is nondestructive. Writing ones acknowledges selected pending bits;
zeros preserve them. Every qualified source event sets its bit, even if
already set. A same-edge event wins over acknowledgment:
`pending_next = (pending & ~ack_mask) | qualified_events`.
Events coalesce; no event counters. Capture uses the source enable before
the event edge. Disabling a source preserves its pending bit; dispatch uses
`pending & enabled_mask`. The mask is derived from the existing device enable
bits; do not add duplicate programmable mask registers. Timer mask includes
INTEN, independently of whether counting has subsequently stopped.

The CPU receives a synchronous one-clock pulse for qualified enabled source
events, and when a previously disabled source is enabled with retained
pending state. On UART RX enable, unread RXAVAIL also seeds pending and a
pulse; this explicitly extends current UART behavior, which does not replay
backlog on enable. PS/2 enable similarly seeds data/error backlog. UART TXFREE
at initial idle and timer COUNT=COMPARE alone do not seed pending.
If multiple sources fire together their bits all latch, while the CPU may see
one pulse. A pulse already latched by the CPU can result in a later empty ISR
entry; this is valid. A pending bit is never cleared merely by CPU IRQ entry.

System reset clears the shared pending bits. CPU-only reset preserves them
like the peripherals; cold Forth boot disables device IRQs, installs INTAD and
handlers, drains/discards stale input according to boot policy, clears stale
errors/pending, and enables the selected receive sources before INTEI.
Boot policy is to discard pre-boot input from both transports and start with
empty software queues; arrivals after receive enable are normal input.

## Generic dispatcher contract for AP5

One common context save/restore and one INTAD vector. First instruction INTDI;
finish with INTEI.RET. No nesting, interpreter calls or VGA access. Read
IRQ_PENDING and derive the enabled source mask from nondestructive CSR reads.
Use direct tests/calls in order timer, UART RX, UART TX, PS/2. Service every
bit in the snapshot, then rescan. Handler work is short and finite for a
finite input burst; timer/TX sources remain disabled until needed.

**Acknowledge each selected snapshot bit before calling its handler.** This
prevents a later acknowledgment from erasing an event received during the
handler. Same-edge set wins in hardware. RX handlers drain available bytes;
PS/2 handler also captures and clears error flags while retaining RXIE.
An event during drain can leave a pending bit although no data remains;
the next pass safely handles that case. A final-check/return race is covered
by the CPU's retained IRQ request. Never use an if/else chain that skips
simultaneous sources. A no-pending entry returns without calling a handler.

The static mapping is the registration mechanism; no runtime table needed.
Unexpected enabled sources without handlers are disabled and their pending
bit acknowledged, with a private diagnostic flag for later foreground
reporting. This does not silently enable or run an unrelated handler.
All handlers share the preservation ABI: balanced hardware stacks, no change
to interrupted carry, user DEPTH or shared parser/arithmetic scratch. Common
save/restore owns saved context; handlers use explicitly allocated ISR-private
SRAM. Prove the complete call-depth/headroom budget in AP5 before INTEI.

## Reproducible resource baseline

Fresh builds completed with unchanged RTL and Forth sources. Exact source
hashes, tool versions, commands and artifact hashes are recorded in
[PS2_AP1_BASELINE.json](PS2_AP1_BASELINE.json); large artifacts remain in
`build/ps2-ap1-baseline/`. Board configuration: HX8K CT256, 25 MHz, seed 1,
VGA enabled, 16-cell data and return stacks. No FPGA programming performed.

| Metric | Before PS/2 / dual console |
| --- | --- |
| Routed logic cells | 4020 / 7680 |
| Synthesized LUT4 / flip-flops / carry cells | 3330 / 973 / 361 |
| EBRs / PLLs | 16 / 32; 1 PLL |
| Routed internal Fmax | 30.53 MHz; passes 25 MHz |
| Kernel code/dictionary span | 0400..3622 inclusive, 12835 bytes |
| First user dictionary byte / exclusive limit | 3624 / F000 |
| Available user dictionary | 47580 bytes |
| Exported load image | 65520 bytes; padded SRAM image, not kernel code size |
| Kernel words / private variable cells | 89 / 58 |
| Existing reserved software buffers | Input 128 B, strings 128 B, compiler control 128 B, scratch 128 B; variable area 256 B |
| ISR stack headroom | Not measured: current Forth runs with interrupts disabled; AP5 must prove it |

AP1 acceptance: pin tracing and conflict check complete; nominal electrical
path documented with physical measurements reserved for AP8; source audit,
pending/acknowledgment map, FIFO/reset/IRQ priorities and baseline fixed.
AP2 can start with this contract. No receiver, pending-register or dispatcher
implementation is claimed by AP1.
