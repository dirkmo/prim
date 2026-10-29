# Prim system LED/UART memory map

This map belongs to [`memory_io.v`](../rtl/memory_io.v) in the Prim system.
The reusable [`debug_uart_link`](../../debug_uart/rtl/debug_uart_link.v) exposes
RX, TX and status signals without address decoding. Their buffer/handshake
semantics are described in the
[UART register-interface reference](../../debug_uart/docs/register_interface.md).
The full system reserves FFF0..FFFF for MMIO, including the
[timer at FFF0..FFF5](timer_mmio.md). FFF6..FFFC is reserved and reads zero.

## Byte addresses

| CPU byte address | Read | Write |
|---|---|---|
| `0xFFFD` — LEDs | Bits 0/1: LED1/LED2; bits 7:2 zero | Set LED1/LED2 from bits 0/1; ignore bits 7:2 |
| `0xFFFE` — STATUS | Bit 0: received; bit 1: pending TX buffer free; bits 7:2 zero | Acknowledge and ignore |
| `0xFFFF` — RX/TX DATA | Last received seven-bit byte, bit 7 zero; clear received at final ACK | Enqueue bits 6:0 into CPU TX; ignore bit 7; wait if the buffer is full |

LED1 (M12) and LED2 (R16) turn on when their respective bit is 1. Full system
reset clears the LED register; CPU-only reset preserves it. 0000 remains SRAM.
SRAM cells behind FFF0..FFFF are not accessible through this map.
CPU and debug master see the same register side effects. A debug read of FFFF
also consumes RX; debug command q instead reads UART status without consuming
input or acquiring the CPU bus. STATUS is not write-one-to-clear.

## Word accesses

The CPU bus is **byte-addressed**. A 16-bit word starting at byte address A
accesses bytes A and `(A+1) mod 65536`. In little-endian order, A is the low
byte and A+1 the high byte. These accesses do not create new register addresses.
For example, a word read starting at FFFE reads STATUS at FFFE into bits 7:0
and RX DATA at FFFF into bits 15:8.

BS selects lanes relative to A: 01 accesses A in bits 7:0, 10 accesses A+1
in bits 15:8, and 11 selects both. Unselected lanes cause no register effects.
The table below applies to BS=11:

| Starting byte address of 16-bit access | Low byte, bits 7:0 | High byte, bits 15:8 | Write effect |
|---|---|---|---|
| `FFFC` | Reserved (zero) | LEDs at FFFD | Ignore low byte; set LEDs from high bits 1:0 |
| `FFFD` | LEDs at FFFD | STATUS at FFFE | Set LEDs from low bits 1:0; ignore high status byte |
| `FFFE` | STATUS at FFFE | RX DATA at FFFF | Ignore low status byte; enqueue high byte's low seven bits |
| `FFFF` | RX DATA at FFFF | SRAM[0000], due to wraparound | Enqueue low byte's low seven bits; write all eight high-byte bits to SRAM[0000] |

A read consumes RX once at final ACK if the RX lane is selected. For mixed
MMIO/SRAM transfers, the SRAM lane completes first and the UART effect occurs
at the final ACK. Requests remain stable through all phases; a TX wait after
the SRAM phase must not repeat that SRAM write. A word read at FFFE returns
the pre-consumption STATUS value. A simultaneous new reception can leave the
received flag set after ACK.

Transfers below FFF0 use the existing SRAM word operations, including
unaligned accesses and address wrapping. The table describes this system's
adapter behavior, not an inherent feature of the UART module.

## CPU software

Use byte accesses for independent STATUS and DATA operations:

```text
3 0xfffd c!          # turn both LEDs on (0: off, 1: LED1, 2: LED2)
0xfffd c@             # read current LED bits
0xfffe c@ 1 and       # test received
0xffff c@             # read RX; clear received, retain byte
0xfffe c@ 2 and       # test pending TX buffer free (not physical TX idle)
65 0xffff c!          # enqueue ASCII A, waiting for room if necessary
```

Reading a 16-bit word at FFFE also reads/consumes RX at FFFF. Reading DATA
without checking received can return an already-consumed byte; NUL is valid
input and must be distinguished using the received flag, not its data value.
Writes to STATUS do not clear flags. CPU-only reset preserves UART buffers;
full system reset clears them.

## Image loading

This system reserves FFF0..FFFF. A full 64-KiB SRAM image therefore
requires `load --skip-mmio` in the board host tool.
It reports each included MMIO address, writes/verifies only 0000..FFEF
(65520 bytes for a full image),
and leaves the physical SRAM bytes behind the registers unchanged. Readback
through the mapped registers does not verify those hidden SRAM cells.

Other integrations can choose a different map and must define their own word
access behavior and loader exclusions.
