# System timer

`prim_system` connects the standalone [`timer`](../../timer/README.md) through
`timer_mmio.v` and `memory_io.v` to the shared CPU/debug bus. Timer IRQ is wired
directly to `Prim.i_irq`. The CPU does not yet implement interrupt handling;
the wiring does not change instruction execution.

## Register map

The system reserves **FFF0..FFFF** for MMIO; ordinary SRAM ends at FFEF.
All addresses below are CPU byte addresses. Register words are little-endian.

| Address | Register | Access |
|---|---|---|
| FFF0..FFF1 | COUNT, 16 bits | R/W |
| FFF2..FFF3 | COMPARE, 16 bits | R/W |
| FFF4..FFF5 | CSR: bit 0 ENABLE, bit 1 AUTO, bit 2 INTEN | R/W; bits 15:3 read zero |
| FFF6..FFFC | Reserved | Read zero, writes ignored |
| FFFD | LEDs | See [LED/UART reference](uart_mmio.md) |
| FFFE..FFFF | UART | See [LED/UART reference](uart_mmio.md) |

Aligned timer words access both bytes atomically in one system clock. Byte
accesses preserve the other register byte. All bus byte masks are supported.
An odd word crossing two timer registers (FFF1 or FFF3) uses two consecutive
phases, lower address first, with final ACK on the second phase. These accesses
are not atomic: the low-address read byte is retained from the first phase,
and a low-address write takes effect before the final ACK. Requests must remain
stable until ACK, as on the rest of the bus. Aligned words are recommended for
coherent COUNT reads.

A mixed SRAM/timer word at FFEF completes its SRAM byte first, then its timer
byte at final ACK. Timer/reserved crossings use the selected timer byte only.
Word wrapping from FFFF to SRAM address zero retains the existing UART behavior.

## Clock and reset

`prim_system.TIMER_DIVISOR` is passed through `memory_io.TIMER_DIVISOR` to
`timer.DIVISOR`. It defaults to 50000 system clocks per counting interval,
independent of `CLK_HZ`. The interval is `TIMER_DIVISOR / CLK_HZ` seconds.
The Olimex wrapper explicitly uses 25000 at 25 MHz, giving 1 ms.

Full system reset clears timer registers, divider and IRQ. CPU-only debug reset,
halt and step do not reset or pause the timer. An enabled timer continues to
run while the debug master owns the bus. Each interrupt pulse lasts one system
clock, without a pending latch. The [standalone documentation](../../timer/README.md)
defines counting, reload, write priority and interrupt conditions.

## Software example

```text
0 0xfff4 !       # disable
100 0xfff2 !     # compare value
0 0xfff0 !       # reset COUNT and divider phase
5 0xfff4 !       # ENABLE | INTEN, one-shot
0xfff0 @        # read COUNT
```

COUNT stops at 100 after 100 counting intervals; ENABLE stays set. Writing
COUNT=0 restarts it. AUTO adds a separate interval for the reload to zero, so
periodic operation has a period of `(COMPARE+1)` counting intervals.

## Image loading and verification

Board `host.py load` rejects images extending into FFF0..FFFF unless
`--skip-mmio` is supplied.
It reports and skips all included MMIO bytes, writing/verifying only SRAM.
A full image therefore loads 65520 bytes. The physical SRAM hidden behind MMIO
is left untouched. Makefile `SKIP_UART_MMIO=1` also skips this entire range.

`system/tests/test_io.py` checks CPU register accesses, and
`system/tests/test_debug_uart.py` checks all byte masks, unaligned/mixed words,
exactly-once writes, IRQ wiring, one-shot/auto operation and reset behavior
through the complete debug UART/system path.

The Olimex build with the timer passes place-and-route at 25 MHz: 3414/7680
logic cells, one PLL, no block RAM; reported routed maximum 40.87 MHz (seed 1).
