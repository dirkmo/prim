# DebugUart – initial design

As of October 28, 2026. Design proposal; not yet implemented.

## Purpose and architecture

`DebugUart` provides a resource-efficient UART for an FPGA with very limited
programmable logic. Two virtual channels share the serial connection:
normal CPU output and bidirectional debug communication.

The proposed architecture consists of a small UART core, a debug state machine,
and a bus multiplexer. Debug bus accesses are allowed only while the CPU is
halted. This avoids complex bus arbitration during program execution.

The existing RTL already provides a 16-bit system bus with BS/WE/ACK and an
unbuffered UART transmitter. CPU halt, single-step, and a functional hardware
BREAK must be added.

## UART and virtual channels

- Fixed baud rate: 115200, 8 data bits, no parity, one stop bit (8N1), LSB first.
- The FPGA clock frequency is a parameter used to derive a constant baud divider.
- RX: two-stage input synchronization and sampling at the middle of each bit,
  without 16x oversampling.
- TX: the existing valid/ready interface without a FIFO.

| UART byte | Purpose |
|---|---|
| `0xxxxxxx` | Channel 1: Prim CPU → host PC |
| `1xxxxxxx` | Channel 2: bidirectional debug communication |

Channel 1 therefore carries seven payload bits per byte. ASCII works directly;
existing UTF-8 output such as `Grüße` does not work unchanged.
Arbitrary 8-bit data would require additional encoding. This minimal design
defines channel 1 as 7-bit output.

Received channel-1 bytes are initially ignored, since only CPU → host is required.

## Debug protocol

Within channel 2, bit 6 distinguishes data bytes from control bytes:

| Byte range | Meaning |
|---|---|
| `80`–`BF` | Six payload bits in bits 5:0 |
| `C0`–`FF` | Command, response, or event |

All byte codes and addresses in this document are hexadecimal.

16-bit values are transmitted as three data bytes, least significant bits first:

```text
Byte 1: 10vvvvvv    Value[5:0]
Byte 2: 10vvvvvv    Value[11:6]
Byte 3: 1000vvvv    Value[15:12]
```

8-bit values require two data bytes; only two payload bits are valid in the
second byte. Unused bits must be zero.

Decoding uses fixed wiring and a small position counter. Variable packet lengths,
escape sequences, checksums, and packet buffers are omitted.

### Commands

| Code | Host command | Following data |
|---|---|---|
| `C0` | SYNC / STATUS | none |
| `C1` | HALT | none |
| `C2` | RUN | none |
| `C3` | STEP | none |
| `C4` | RESET-HALT | none |
| `C5` | READ8 | Address: 3 bytes |
| `C6` | READ16 | Address: 3 bytes |
| `C7` | WRITE8 | Address: 3 bytes, value: 2 bytes |
| `C8` | WRITE16 | Address: 3 bytes, value: 3 bytes |
| `C9` | READ-PC | none |

Each memory command includes its address. This avoids a persistent address
register with a separate control protocol and an automatic address incrementer.

### Responses and events

| Code | Meaning |
|---|---|
| `D0` | OK, followed by requested data where applicable |
| `D1` | STATUS, followed by one data byte |
| `D2` | ERROR, followed by an error code |
| `E0` | BREAK event |

The status byte initially contains only `halted` and `break_pending`.
READ-PC returns the address of the next instruction to execute.
The exact bit assignments and error codes must be defined before implementation.

## Command flow and synchronization

The host keeps at most one command outstanding and waits for its response.
Memory accesses start only after all parameters have been received.

A new command byte discards an incomplete command reception. SYNC can therefore
realign the receive decoder without a timeout. A bus access that has already
started runs to completion at ACK and is not aborted by SYNC.

- READ/WRITE and READ-PC are allowed only while halted.
- STEP while the CPU is running returns an error.
- HALT while already halted confirms the current state.
- RUN and RESET-HALT clear the previous break reason.
- UART framing errors discard the incomplete command.
- A bus access without ACK remains pending; a hardware bus timeout is initially
  outside the minimal design.

Channel-1 bytes may appear between debug bytes. The host separates the two
channels using bit 7.

## CPU control

The CPU gains a small debug interface with a halt request, halt acknowledgment,
step request, and break indication.

Halting occurs at an instruction boundary, before the next fetch starts.
An in-progress memory access and its instruction complete first.
While halted, the CPU bus is inactive (BS=00).

- HALT: respond only once the CPU has actually halted.
- RUN: resume execution at the current PC.
- STEP: execute exactly one complete instruction, including all memory wait
  cycles, then halt again and respond.
- RESET-HALT: reset only the CPU and leave it halted at the reset PC.
  The UART and debug controller remain accessible; SRAM contents are preserved.

Use synchronous clock enables or state-update enables, without generating or
gating a clock.

### BREAK semantics

- The CPU halts when executing the break instruction.
- No stack changes and no return-bit effect.
- The PC subsequently points to the instruction after the break instruction.
- RUN resumes there.
- A latched event bit preserves the host notification even while TX is busy.

BREAK does not yet halt the CPU in the existing RTL. These semantics require
a targeted CPU extension.

## Bus and transmitter

A multiplexer connects either the CPU or the debug master to the existing
memory_io module:

```text
CPU ───────────┐
               ├── Bus multiplexer ── memory_io ── SRAM / UART output
Debug master ──┘
```

The debug master follows the same bus contract: address, data, BS, and WE
remain stable until ACK. Byte, word, unaligned, and wrapping accesses retain
the existing bus semantics. Debug accesses to MMIO have its normal side effects.

The TX arbiter selects at byte boundaries with the following priority:

1. Pending debug response or break notification.
2. CPU output.

A UART byte already being transmitted completes first. CPU output waits through
the existing bus handshake when necessary; no additional transmit buffers are
required for this.

## Implementation steps

1. Document the protocol and CPU debug semantics.
2. Add a minimal UART RX and channel separation.
3. Verify halt, run, step, and break independently of the UART first.
4. Integrate the debug parser, bus multiplexer, and TX arbiter.
5. Create a small Python host library for commands and channel separation.
6. Simulate bus wait states, break during TX, reset, incomplete commands, and
   single-step execution of memory instructions.
7. Compare resource usage against the current implementation using synth_ice40.

Block transfers, FIFOs, hardware address breakpoints, and stack access are
initially outside the first version. Actual resource usage must be determined
by synthesis; CPU enable logic and the bus multiplexer may require more
resources than the small protocol decoder.
