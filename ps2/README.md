# PS/2 keyboard receiver (AP2/AP3)

Receive-only Verilog keyboard interface, using the existing system clock.
The Olimex iCE40-IO Rev.A connector feeds clock/data to GPIO1.14/16, FPGA
G1/J5, through the board's resistor network. See the verified wiring and
nominal voltage calculations in [the AP1 contract](../docs/PS2_AP1_CONTRACT.md).
Physical keyboard/voltage measurements remain an AP8 hardware check.

`rtl/ps2_rx.v` synchronizes both inputs with two flops, qualifies clock
transitions after eight stable samples by default, and samples data on a
qualified falling edge. It validates low start, eight LSB-first data bits,
odd parity and high stop. A 2 ms inter-edge timeout discards an incomplete
frame. Frame errors produce a pulse, never a received byte. The next valid
start recovers reception. Filter and timeout are synthesis parameters.

`rtl/ps2_fifo.v` buffers raw bytes, default depth 16. The depth must be a
positive power of two (depth 1 is supported). Only pointers/count/flags reset;
storage is inferred without a reset. ASCII mapping, set-2 prefixes, modifiers
and keyboard startup/status-byte interpretation belong to later software APs.
No host transmit, keyboard LED commands, mouse support or scan-set negotiation.

## System integration

`prim_system.PS2_ENABLE` defaults to zero, preserving reserved FFFB/FFFC reads
of zero and ignored writes. The Olimex board enables it, using the existing
25 MHz clock and plain inputs without internal pulls. The `memory_io` wrapper
passes CLK_HZ and exposes FIFO-depth/filter/timeout parameters for integration.
The board design reuses its existing VGA and UART; no CPU instruction changes.

| Byte address | Read | Write |
| --- | --- | --- |
| FFFB PS2_CSR | Bit 0 RXAVAIL, 1 FULL, 2 RXIE, 3 FRAMEERR, 4 OVERFLOW; 7:5 zero | Replace RXIE from bit 2; W1C errors in bits 3/4; ignore other bits |
| FFFC PS2_DATA | Oldest raw byte, consuming once; zero if empty | Ignored |

Reset CSR is zero. Full system reset empties FIFO and flags and disables RXIE.
CPU-only debug reset/HALT/STEP preserve FIFO, flags and RXIE. NUL is a valid
raw byte: check RXAVAIL before reading. CPU and debug master share consuming
DATA semantics. CSR and shared pending reads do not consume data.

Full FIFO drops the newest incoming byte and sets OVERFLOW, except that a
same-edge successful pop frees space for the incoming byte. An empty read
concurrent with an arrival returns zero and leaves the new byte queued.
New frame/overflow errors win concurrent W1C. FRAMEERR covers bad parity,
bad stop and partial-frame timeout. Reading DATA does not clear errors.
When acknowledging errors, preserve bit 2 if interrupts should remain enabled:
writing `0x1c` clears both errors and enables RXIE.

RXIE qualifies receive/error source events. The shared interrupt block also
replays queued input/errors when RXIE is enabled. New events use the pre-edge
enable, including on the edge disabling RXIE. The [shared IRQ register](../system/docs/interrupts_mmio.md)
retains source identity in FFF5 bit 3. Acknowledge that bit before draining
the FIFO/capturing errors; rescan afterward. No event count is guaranteed.

Accesses touching PS/2, VGA or IRQ_PENDING are serialized by selected byte,
lower address first. A side effect happens once at its byte completion,
possibly before the outer word ACK. BS=01 selects A, BS=10 selects A+1 in
the upper data byte, BS=11 selects both, with 16-bit wrapping. A word at FFFB
returns pre-pop CSR in bits 7:0 and the consumed byte in bits 15:8. A word at
FFFC combines DATA and LEDs. Unselected lanes never cause side effects.

## Verification and resources

```sh
python3 ps2/tests/test_ps2.py
python3 system/tests/test_debug_uart.py
cmake -S . -B build/sim
cmake --build build/sim
ctest --test-dir build/sim --output-on-failure
python3 boards/olimex_ice40hx8k_evb/build.py build --output build/ps2-ap3/board
```

The receiver scoreboard tests all 256 bytes and asynchronous frame phases,
filter lengths 1/2/8, invalid start/parity/stop, clock glitches, timeout and
reset recovery. The FIFO uses an independent ordered-list reference through
3000 random cycles at depths 1/2/16, plus directed empty/full collisions and
error/clear races. The MMIO/IRQ scoreboard runs with VGA both off and on,
checking byte masks, register crossings, backlog enables, source coalescing,
W1C/event races, FIFO ordering/errors and hidden SRAM isolation.
The serial system suite additionally checks PS/2 input while the real CPU is
halted/globally masked, interrupt entry on RUN, consuming debug-bus reads and
CPU-only reset retention. It also retains the UART and timer regressions.

For the 16-byte FIFO alone, current Yosys inference uses 54 LUT4, 25 flip-flops,
10 carry cells and one EBR. A forced logic implementation uses 163 LUT4,
148 flip-flops, 10 carry cells and no EBR. Keep inferred storage: one EBR saves
109 LUT4 and 123 flip-flops, while the complete board still has free EBRs.
These are alternative standalone synthesis counts, not routed board costs.
The [AP3 resource report](../docs/PS2_AP3_RESOURCES.json) compares the complete
routed target with the AP1 baseline and records reproducible source hashes.
The seed-1 25 MHz board build uses **4225/7680 logic cells** and **17/32 EBRs**:
an increase of 205 routed cells, 188 synthesized LUT4, 81 flip-flops and one
EBR. The existing PLL is reused. Routed internal Fmax is **28.98 MHz** and
passes 25 MHz. AP2/AP3 add no CPU software or external SRAM allocations.

The Forth console is still UART-only after AP3. Routing, software ISR dispatch,
keyboard decoding and the second console are AP4–AP7; this implementation
provides the hardware and source identification those packages need.
