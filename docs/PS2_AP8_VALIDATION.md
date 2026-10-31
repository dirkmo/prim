# AP8: dual-console verification and physical acceptance

Date: 2026-10-31. AP4–AP7 are implemented and separately committed:

| Package | Commit | Deliverable |
| --- | --- | --- |
| AP4 | e7344e9 | Common output routing and integrated VGA backend |
| AP5 | 3209b51 | Generic ISR dispatcher, safe wait window, raw receive rings |
| AP6 | eedef90 | German set-2 ASCII keyboard decoder |
| AP7 | a78cab5 | Independent editors, fair arbitration, single-interpreter ownership |
| AP8 | This change | Full-system tests, resource report and physical procedure |

The [resource/verification manifest](PS2_AP8_RESOURCES.json) records source and
artifact hashes. Large logs and images stay under `build/`; no physical FPGA
programming or external keyboard/monitor access was performed. Automated
acceptance is separate from the outstanding physical checks below.
All **21 CTest suites passed**, including **90 Forth tests with no skips**.
The exported default kernel was checked byte-for-byte against the image used
by the complete RTL wire test.

## Reproduction

```sh
cmake -S . -B build/sim
cmake --build build/sim -j2
ctest --test-dir build/sim --output-on-failure -j2
python3 forth/build.py --output build/ps2-ap8/forth
python3 forth/build.py --uart-only --output build/ps2-ap8/uart-only
python3 boards/olimex_ice40hx8k_evb/build.py build --output build/ps2-ap8/board
```

For just the added model cases, run `forth/tests/test_dual.py`, `test_irq.py`,
`test_keyboard.py` and `test_frontend.py` with Python. For just the wire case:
`python3 forth/tests/test_dual_system.py --rtl`. The integrated runner
`python3 forth/test.py --rtl` also includes them and preserves per-suite logs
and fixtures. Tests use the same default dual image built for FPGA SRAM;
the original UART-only image remains independently covered.

The complete wire test uses an actual 25 MHz simulation clock, real UART
RX/TX frames at 115200 baud and 20 kHz PS/2 clock/data frames with make/break
bytes. It executes the kernel on Prim with SRAM wait states and real shared
IRQ/MMIO/VGA RTL. Checks cover exact UART bytes, local-only VGA echo/errors,
cross-console definitions, blocked KEY, simultaneous input, 35-line scrolling,
bank restoration/SRAM preservation and HALT/CPU-reset retention. An independent
counter includes ISR PC pushes when measuring physical data/return occupancy.
Existing VGA frame/pixel scoreboards and peripheral collision tests remain
part of the full CTest run.

## Resource results

| Metric | Result |
| --- | --- |
| Board routed logic cells | 4225 / 7680 |
| EBR / PLL | 17 / 32; one existing PLL |
| Internal routed Fmax | 28.98 MHz, passes 25 MHz (seed 1) |
| AP4–AP8 FPGA resource increase over AP3 | Zero; rebuilt bitstream is byte-identical |
| Default kernel code/table span | 16275 bytes from 0400 |
| Default USER_START / remaining dictionary | 4394 / 44140 bytes through EFFF |
| UART-only kernel span / remaining dictionary | 12881 bytes / 47534 bytes |
| Added kernel bytes versus current UART-only profile | 3394 bytes |
| Console SRAM reservation | 1024 bytes in existing F000..F3FF reserve; 498 used for state/storage |
| User / hardware stacks | Eight checked user cells; 16 data + 16 return cells, unchanged |

The FPGA bitstream does not contain the Forth image; the kernel runs from
external SRAM. Software tables and buffers therefore add no FPGA EBR or LUTs.
The one PS/2 EBR was already added in AP3. The default and UART-only kernel
measurements above use the same current source/word set, avoiding attribution
of unrelated intervening changes to this extension.

The complete wire session measured DS=5/16 and RS=6/16; the targeted model
session with all eight user values, .S and WORDS measured DS=12/16 and RS=6/16.
IRQ entry is restricted to the collector's INTEI/NOP/INTDI window. Both carry
values and each window boundary, masked requests and ISR return handoff are
tested. Arbitrary Forth execution stays globally masked; KEY services input
synchronously. A long-running program can overflow the 16-byte PS/2 hardware
FIFO before returning. This is an explicit stack-safety and scheduling limit,
not a claim of asynchronous execution or unlimited buffering.

## Physical acceptance — pending

Start from a freshly configured board (BANK clear), with the matching iCE40-IO
Rev.A expansion, a set-2 PS/2-compatible keyboard and a VGA monitor attached.
Use the [AP1 wiring/electrical contract](PS2_AP1_CONTRACT.md) and the existing
[board programming procedure](../boards/olimex_ice40hx8k_evb/README.md).
The commands below are instructions for the physical session, not actions
performed by the automated validation:

```sh
python3 boards/olimex_ice40hx8k_evb/build.py program build/ps2-ap8/board/prim.bin
make upload IMAGE=build/ps2-ap8/forth/kernel.bin VERIFY=1
make uart-console
```

Use the configured PORT or pass it to the Make commands. In the host console,
Ctrl+B opens the debug prompt; `run` starts the loaded CPU. A later reload
requires BANK clear; a full board reset provides that state. CPU-only HALT
may stop during a transient VRAM mapping, so do not assume it clears BANK.

- [ ] Measure idle/low clock and data levels at GPIO1.14/16 with the actual
  keyboard and supplies; record voltage margins, transitions, keyboard model
  and board revisions. Nominal resistor calculations alone do not establish
  electrical acceptance for every keyboard's internal pull-ups.
- [ ] Record monitor model and acceptance of the existing 25 MHz, approximately
  59.52 Hz raster; verify readable glyphs, stable sync and cursor.
- [ ] Confirm one readiness prompt on each endpoint. Enter `: twice DUP + ;`
  locally, then `7 twice .` over UART: definition/echo only on VGA, `14` only
  on UART. Enter `123` over UART, then `.S DROP` locally to demonstrate shared
  stack contents without leaving the test value behind.
- [ ] Start `: PART` locally. Enter `2 .` on UART; its result must wait. Finish
  locally with `7 ;`; UART can then execute. Repeat with a compile error and
  ABORT to verify owner release and rollback.
- [ ] On UART define `: take KEY . ;`, then run `take`. Type a local command;
  it must wait. Send `A` on UART without Enter: UART prints `65`, then the
  queued local command resumes on VGA. Check the reverse ownership direction.
- [ ] Check Shift keys independently, Caps repeat/release, Ctrl/AltGr and
  Forth punctuation (`: ; [ ] ( ) " \\ + - * /`). Umlauts and keyboard LED
  synchronization are outside the initial ASCII/receive-only scope.
- [ ] Exercise simultaneous typing, per-endpoint backspace and CRLF, unknown
  words, line overflow, long output and scrolling. Verify no ordinary output
  appears on the other endpoint.
- [ ] HALT using UART debug, type enough local keys to exceed the hardware
  FIFO, then RUN and press Enter to resynchronize. Expect a local input-loss
  error and no shortened command execution. Verify the next complete command.
- [ ] Verify VGA continues during HALT, CPU-only reset preserves peripherals
  until boot reinitializes them, stale input is discarded, and user definitions
  are forgotten on a fresh cold start. Check external SRAM operation on board.

Record observations and any failures separately; do not mark these boxes from
simulation results. Automated pass status does not substitute for this physical
acceptance.
