# CPU UART register and handshake reference

This is the CPU/application interface of [`debug_uart_link`](../rtl/debug_uart_link.v).
It is independent of the debug ASCII parser and the selected CPU instruction set.
The top-level interface is described in the [module README](../README.md).

## Address-independent module interface

The UART RTL does **not** decode addresses. It exposes these synchronous signals:

| Function | Signals | Transfer at a rising `i_clk` edge |
|---|---|---|
| RX data | `o_input_data[6:0]` | Sample the current retained byte |
| RX consume | `i_input_read` | Clear received flag; do not erase data |
| TX enqueue | `i_output_data[6:0]`, `i_output_valid`, `o_output_ready` | Accept exactly one byte on valid AND ready |
| CSR read | `o_uart_csr[3:0]` | Status and interrupt enables; observation has no side effect |
| CSR write | `i_csr_data[7:0]`, `i_csr_write` | Update RXIE/TXIE on a write edge |
| Interrupt | `o_irq` | Registered synchronous event pulse |

A surrounding MMIO adapter chooses addresses, pads these values to the CPU's
register width, masks TX bit 7, generates the consume pulse, and turns ready
into a bus acknowledgment. Another SoC can choose different addresses without
modifying any UART RTL. For a ready/valid stream without MMIO, connect directly
to these same signals.

All these signals are in `i_clk`'s clock domain. They are not an asynchronous
processor interface. Do not derive `i_input_read` from address decode alone;
assert it only for a completed read. Keep TX valid and data stable until
accepted, then deassert valid or present the next transfer.

## Logical RX, TX and CSR interface

The logical functions are not assigned addresses by this module:

| Function | Value / side effect |
|---|---|
| RX read | Seven retained data bits; the adapter asserts consume at its read ACK |
| TX write | Seven data bits; acceptance requires valid AND ready |
| CSR read | Status and interrupt enables; observing them consumes nothing |
| CSR write | Update bits 2/3; ignore all other bits |

A consuming system can map RX and TX to the same address for read/write, or
choose separate addresses. Zero-extend the four-bit CSR output to a byte.
Assert `i_csr_write` only at the completed bus write, with the selected byte
on `i_csr_data`. For an integration without interrupts, tie `i_csr_write` and
`i_csr_data` low and leave `o_irq` unconnected.

The Prim system's address map and word accesses are documented separately in
[system/docs/uart_mmio.md](../../system/docs/uart_mmio.md). Its addresses, adjacency and word-lane rules are properties of that system,
not of the reusable UART module.

### CSR bits (zero-extended by a register adapter)

| Bit | Name | Meaning of 1 | Meaning of 0 |
|---|---|---|---|
| 0 | RXAVAIL (received) | A CPU-channel byte arrived since the last consume | No unread CPU byte |
| 1 | TXFREE (tx_free) | Pending CPU TX buffer is empty | Pending CPU TX buffer is occupied |
| 2 | RXIE | Interrupt on CPU-channel reception enabled | Disabled |
| 3 | TXIE | Interrupt on CPU TX slot becoming free enabled | Disabled |
| 7:4 | reserved | — | Always zero |

Bits 0/1 are read-only. Writes replace RXIE/TXIE and ignore bits 0/1 and 7:4.
After a synchronous module-reset edge CSR is **02**: RX empty, TX slot free,
both interrupt enables cleared.

`tx_free` is not physical transmitter idle. The current UART frame can be
active while the pending slot is free. Conversely, debug priority can leave a
CPU byte pending while the transmitter sends debug bytes. The public interface
does not offer a separate frame-complete or physical-idle flag.

`o_output_ready = !i_reset && tx_free`. During reset it is low even though the
reset status says the pending TX slot is empty. Do not initiate bus accesses
while the surrounding system is in reset.

## Interrupt semantics

`o_irq` is registered on the event edge and asserted for one clock per event:

- RXIE enables an event for each received CPU-channel byte (wire bit 7 = 0),
  including overwrites and simultaneous consumption/reception.
- TXIE enables an event when a pending CPU byte is accepted by the transmitter.
  The CPU TX slot becomes free at that edge, before the serial frame completes.
- Debug reception, debug responses and BREAK frames do not generate events.
  Debug priority can delay a pending CPU byte's acceptance and its TX interrupt.

Enables are sampled from before the event edge. A simultaneous CSR write takes
effect for subsequent edges. Enabling an interrupt does not replay an earlier
event or generate an event merely because RX is full or TX is free. An empty
TX slot does not continuously request interrupts. Simultaneous RX/TX events
share one pulse; consecutive events may assert IRQ on consecutive clocks.
There are no UART pending/acknowledge bits. Reading DATA consumes RX as before;
reading CSR has no side effects. System reset clears enables and IRQ; CPU-only
reset preserves the UART state. The surrounding interrupt receiver must latch
pulses as needed while masked or halted. Prim already does this, coalescing
multiple requests; its UART and timer IRQs are ORed together.

## RX semantics

- Only wire bytes with bit 7 = 0 update this register. Debug bytes do not modify
  CPU RX data or its received flag, even if their low bits spell the same text.
- Each CPU-channel reception replaces the seven-bit data and sets received.
- A consume edge clears received but retains data. Repeated DATA reads therefore
  return the same byte until another CPU byte arrives, even with received = 0.
- New reception wins over simultaneous consumption. The consumer samples the old
  data at that edge; after it, the new byte is present with received = 1.
- Another arrival while received = 1 overwrites the previous byte. There is no
  FIFO, overrun counter, overflow response, or automatic sender backpressure.
- A received NUL is valid data: DATA = 00 with received = 1. DATA = 00 alone
  cannot distinguish NUL from an empty/reset register. Check CSR bit 0.
- Reset initializes data to 00 and clears received. Neither CPU HALT nor
  CPU-only RESET-HALT clears this register.

DATA is a live output, not a latched bus-response snapshot. The adapter must
sample it at the acknowledging edge and consume once at that edge. Polling
CSR and subsequently reading DATA is not a reservation against an independent
sender; reliable delivery also needs the host pacing below.

### Host RX flow control

The debug command `q` replies `K` plus one low-first hex digit containing the
same low two CSR status bits (RXIE/TXIE are excluded). It is available at run
or halt without a memory access.
The host must serialize debug operations, query status, wait until received is
zero, and send **one** CPU byte. Before sending the next byte it must obtain
another free indication. Wire ordering places that query after the previous
CPU byte. Do not reuse one free indication for a burst.

`q` is a debug command: like every new command it terminates an address or
persistent write mode. A host must not insert these polls inside a debug
transaction/write burst. The supplied `UARTSession` handles this locking and
pacing. Its reader continues dispatching CPU output/BREAK even when CPU input
is waiting. A halted CPU may keep RX full indefinitely; RUN/debug control must
remain usable in that state.

## TX semantics

The pending CPU TX buffer holds one seven-bit byte in addition to a possibly
active UART frame. A valid/ready edge accepts the byte and makes tx_free zero.
This means **queued**, not transmitted. The adapter may acknowledge a CPU write
only when that transfer is accepted. If full, it must keep request/data stable
and wait; it must not overwrite the buffered byte.

The arbiter offers pending CPU data to the existing transmitter only when no
debug response/BREAK is valid. When the transmitter accepts the byte, the pending
slot becomes free; the frame then runs independently to completion. A slot
which is full before an edge is not replaced on that same dequeue edge:
`o_output_ready` becomes high after the edge, permitting enqueue on the next one.
There is no combinational fall-through path from CPU input to UART TX.

CPU output is always wire-encoded with bit 7 = 0. Debug output bypasses the CPU
slot and uses bit 7 = 1. Priority changes only between frames, never mid-frame.
Debug can delay CPU transmission indefinitely under sustained debug traffic.
Reset discards pending CPU output and aborts an active frame; CPU-only reset
preserves both. Debug-MMIO writes to DATA enqueue normal CPU output too, with
exactly the same capacity and backpressure.

## Bus adapter and word accesses

A bus adapter can complete reads without waiting for serial input. It forwards
CSR writes at the final acknowledgment. An empty DATA read returns retained data
immediately; it does not wait for another character. Only a full CPU TX buffer delays a DATA write.

The UART has no bus byte lanes, word size or address-wrap rules. A system
adapter defines which byte/word accesses select these logical functions and
which other targets participate. It must consume RX exactly once at the final
read acknowledgment and must acknowledge a TX write only on buffer acceptance.
If an operation also touches memory, its completion/side-effect ordering must
be defined by that system; a stalled TX transfer must not repeat memory writes.

The following fragment illustrates a **byte-only** adapter with address constants
supplied by its surrounding system. It needs a lane adapter before it can be
used on a word-capable bus. RX/TX share a logical DATA address in this example;
that is an adapter choice, not a UART requirement. This example forwards writes
to CSR:

```verilog
// bus_valid/write/address/wdata remain stable through the uart_ack edge.
// uart_* nets connect to debug_uart_link's CPU buffer ports.
wire data_select = (bus_address == UART_DATA_ADDRESS);
wire csr_select = (bus_address == UART_CSR_ADDRESS);
wire selected = !system_reset && bus_valid && (data_select || csr_select);
assign uart_tx_data = bus_wdata[6:0];
assign uart_tx_valid = selected && bus_write && data_select;
assign uart_ack = selected && (!bus_write || csr_select || uart_tx_ready);
assign uart_rx_consume = uart_ack && !bus_write && data_select;
assign uart_csr_write = uart_ack && bus_write && csr_select;
assign uart_csr_data = bus_wdata[7:0];
assign uart_rdata = data_select ? {1'b0, uart_rx_data} : {4'b0, uart_csr};
```

Mux `uart_ack`/`uart_rdata` with other target responses in the surrounding bus.
Do not clear received at request start: a stalled access must not consume data
before the CPU accepts it. Do not report a write ACK without enqueuing its byte.

## CPU-side use

Typical byte-register pseudocode:

```text
receive_nonblocking():
    if (read8(CSR) & 1) == 0:
        return NO_BYTE
    return read8(DATA)              # NUL is a valid result

send(byte):
    while (read8(CSR) & 2) == 0:
        wait_or_do_other_work()
    write8(DATA, byte & 0x7f)
```

Polling TX is optional on a bus that supports wait states: writing DATA directly
will stall until the slot is free. Software and other bus masters must coordinate
access if multiple producers/consumers exist; a status read reserves nothing.
Use access widths supported by your adapter. Whether a word access selects
multiple registers is a property of its address map, not of this UART.

For the Prim-specific addresses, word lanes, assembly examples and image-loader
exclusions, see the [system MMIO reference](../../system/docs/uart_mmio.md).
A consuming project's loader must exclude whatever addresses its own adapter
reserves for MMIO from ordinary RAM initialization and verification.

To enable RX and TX interrupts, write `0x0c` to CSR after installing the ISR.
For an interrupt-driven transmitter, enqueue the first byte explicitly to start
the stream; enabling TXIE on an already-empty slot does not create an interrupt.
