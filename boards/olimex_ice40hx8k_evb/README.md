# Olimex iCE40HX8K-EVB Rev.B

Board: iCE40HX8K-CT256, 100 MHz oscillator, K6R4016V1D-TC10 SRAM.
Programmer: UM-FT2232H, working command supplied by the user: `iceprog -b <file>`.
Debug link: separate FTDI USB-UART adapter, 115200/8N1, 3.3 V logic.

Sources of the fixed pin mapping:

- [Olimex Rev.B schematic](https://github.com/OLIMEX/iCE40HX8K-EVB/blob/master/HARDWARE/REV-B/iCE40HX8K-EVB_Rev_B.pdf)
- [Olimex Rev.B netlist](https://github.com/OLIMEX/iCE40HX8K-EVB/blob/master/HARDWARE/REV-B/iCE40HX8K-EVB_Rev_B.net)
- [SRAM manufacturer datasheet hosted by Olimex](https://www.olimex.com/Products/_resources/ds_k6r4016v1d_rev40.pdf)
- [User-specified UM-FT2232H module](https://github.com/mariusgreuel/um-ft2232h/blob/main/README.md)

The board wrapper and constraints are specifically for Rev.B, not Rev.B1.

The board now includes the [VGA text controller](../../vga/README.md).
The iCE40-IO Rev.A expansion board provides VGA through its onboard resistor
DACs: GPIO1.20/18 carry HSYNC/VSYNC and nine GPIOs carry RGB. UART uses the free
GPIO1.5/7 pass-through pins. The VGA guide contains the wiring, memory map,
Forth output driver and new resource/timing measurements. The timer-only
resource figures below describe the earlier build.

## System clock and timing

The board oscillator remains 100 MHz. With user approval on 29 October 2026,
`top.v` uses an `SB_PLL40_CORE` to generate a **25 MHz global system clock**.
CPU, UART and SRAM controller all use that one clock; no fabric clock divider
or gated clock is introduced. `PLLOUTGLOBAL` drives the global clock network.
See the [Lattice primitive reference](https://www.latticesemi.com/view_document?document_id=52206).

`icepll -i 100 -o 25` gives SIMPLE feedback, DIVR=0, DIVF=7, DIVQ=5,
FILTER_RANGE=5: PFD=100 MHz, VCO=800 MHz, output=25 MHz. nextpnr explicitly
constrains the oscillator to 100 MHz and derives the PLL output constraint as
25 MHz. The fixed seed-1 build passes after routing with a reported maximum
system clock of **40.87 MHz** with the timer integrated. This is an internal timing report, not a supported
operating-frequency claim above the selected 25 MHz.

The current UART pin assignment is GPIO1 pin 5 for FPGA RX (ball E4) and
GPIO1 pin 7 for FPGA TX (ball B2), compatible with iCE40-IO Rev.A. Artifacts are in
`build/olimex_ice40hx8k_evb/`, including the bitstream `prim.bin`. Utilization is
3414/7680 logic cells (44.5%), one PLL, and no block RAM. The user has confirmed
the running bitstream, working debug communication and successful
streaming loading on the board (29 October 2026).
The build stops before icepack if timing fails; there is no timing override.

For comparison, the original direct-100-MHz attempt failed at about 52–54 MHz;
its logs remain under `build/board-initial-100mhz/`.
Physical SRAM timing has not been measured. Place-and-route internal-clock
timing alone does not establish external SRAM setup/hold margins.

## UART wiring

GPIO1 pins 5/7 are free pass-through signals on the
[iCE40-IO Rev.A expansion board](https://github.com/OLIMEX/iCE40-IO/blob/master/ICE40-IO_Rev_A.net).
They are accessible at the expansion board's GPIO_Out1 connector with the same
pin numbers. The main board Rev.B netlist maps GPIO1.5 to FPGA ball E4 and
GPIO1.7 to B2. The former UART pins 33/34 are used by IrDA_Tx and VGA_RED3 on
the expansion board. Both current assignments are defined in `board.pcf`:

```tcl
set_io -pullup yes uart_rx E4
set_io uart_tx B2
```

| USB-UART adapter | GPIO1 / iCE40-IO GPIO_Out1 connection | FPGA ball |
|---|---|---|
| TX, 3.3 V logic | Pin 5, FPGA RX | E4 |
| RX | Pin 7, FPGA TX | B2 |
| GND | Pin 2, GND | — |

Move the adapter wires from pins 33/34 to pins 5/7 when installing this
bitstream. Baud rate and debug protocol remain 115200/8N1.

These UART signals are separate from the PGM1 SPI pins used by the UM-FT2232H.
The board uses its existing power supply; the UART adapter's power output is
not required. To change the wiring, edit `board.pcf`; the build never allows
unconstrained IOs.

## Wrapper behavior

`top.v` uses the PLL's 25 MHz global output. Power-up initialization,
synchronized PLL LOCK and synchronized BUT1 generate a synchronous system reset.
Reset stays asserted until LOCK has passed two synchronizer stages and the
four-cycle reset pipe has drained. Lock loss reasserts reset synchronously
while the system clock is running; it is released through the same sequence.
`START_HALTED=1` holds the CPU at PC 0000 from the first fetch; no SRAM boot
contents are assumed. UART/debug logic remain available after reset. BUT1 resets CPU, UART, debug controller and its
pointer. UART `Z` resets only the CPU and retains the debug pointer.

LED1 (M12) and LED2 (R16) are controlled by bits 0 and 1 of the CPU register
at `0xFFFD`: 1 turns the LED on. Both LEDs are off after system reset.
For example, `3 0xfffd c!` turns both on; `0 0xfffd c!` turns both off.
SRAM A17:A15 are held at zero: the CPU uses the first 64 KiB of the 512 KiB
physical device. Both byte enables are wired low on the board; the existing
whole-word controller preserves neighboring bytes. Read/write phases last
three system clocks (120 ns), with one 40 ns cycle per existing
turnaround/setup/hold/release phase. The UART divider is 217 clocks/bit.
The configuration RESET button reconfigures the FPGA; BUT1 is the logic reset.

## Build and programming

The [root Makefile](../../docs/BUILD.md) offers `make bitstream`, `make resources`
and explicit `make flash` shortcuts. `make load-run PORT=... SKIP_UART_MMIO=1`
builds/loads a TokenForth program and starts it; add `VERIFY=1` for readback;
`make uart-console PORT=...` opens the duplex console. Use `make help` for all
targets and `config.local.mk.example` for local UART/programmer settings.

Run these commands from the project root. All pin assignments come directly
from [board.pcf](board.pcf); no UART pin parameters are passed to CMake or the
Python build script. The board build uses `build/olimex_ice40hx8k_evb`;
`build/sim` is reserved for the simulator workflow. Artifacts are written directly
to the selected CMake build directory, without an additional board subfolder.

```sh
cmake -S . -B build/olimex_ice40hx8k_evb
cmake --build build/olimex_ice40hx8k_evb --target fpga_bitstream
# Explicit action; never invoked by the ordinary build or CTest:
cmake --build build/olimex_ice40hx8k_evb --target fpga_program
```

The board tools must be on PATH: yosys, nextpnr-ice40, icepack, iceprog.
The board targets do not participate in the default simulator build.
The standalone build script uses the same `board.pcf` and the same output
folder, `build/olimex_ice40hx8k_evb/`:

```sh
python boards/olimex_ice40hx8k_evb/build.py build
python boards/olimex_ice40hx8k_evb/build.py program build/olimex_ice40hx8k_evb/prim.bin
```

`iceprog -b` erases the entire SPI configuration flash, writes the image and
verifies it; it does not select volatile FPGA configuration SRAM programming.
This matches the user's existing workflow. Programming starts only through
`program` or `fpga_program`. With multiple FTDI devices, use
`-DOLIMEX_ICEPROG_DEVICE=s:0x0403:0x6010:<serial>` as appropriate; the interface
can be configured with `OLIMEX_ICEPROG_INTERFACE` (default A). The direct script
accepts `--device` and `--interface` on the `program` subcommand.
USB permissions/udev rules on Arch Linux remain those of the already working
iceprog setup. Use the separate UART adapter's stable `/dev/serial/by-id/` path.

Outputs include `synth.log`, `nextpnr.log`, `timing.json`, `prim.json`,
`prim.asc` and, only after passed timing, `prim.bin`. A failed rebuild removes a
stale binary. CTest registers 16 suites. The board test is included as
`olimex_board_checks` and checks PLL startup, reset
release, loss of LOCK, recovery and UART at 25 MHz. `pll_sim.v` is a test-only
ideal frequency/LOCK model and is never included in production synthesis;
analog PLL acquisition/jitter is outside the simulation. The additional
`olimex_host_checks` suite checks CLI controls, load boundaries, explicit MMIO
skipping, verification failures and transport cleanup without USB hardware.
The UART session/PTY suite additionally checks continuous output/BREAK,
RX-credit backpressure, uninterrupted debug write modes and terminal restoration. Logs: `build/olimex-validation/ctest.log`.

## First contact and loading

### Hello quick start

From the project root, build and open the console (`PORT` may be set in
`config.local.mk`):

```sh
make image PROGRAM=src/examples/hello.cf
make uart-console
```

Press **Ctrl+B**, then enter this local debug command:

```text
load build/software/hello.bin --skip-mmio --run
```

The loader halts/resets the CPU, streams the image into SRAM, counts write OKs
and starts the CPU after successful loading. The console stays connected to both
channels. Expect `Hello, World!` and a BREAK notification; `status` then shows
halted=true, break=true and PC 0005. Empty Enter leaves the debug prompt;
Ctrl+D exits the console. The user has reported this streaming workflow working
on the board. This is a functional check, not an external SRAM timing measurement.

| Load option | Default | Meaning |
|---|---|---|
| `--skip-mmio` | off | Explicitly omit included FFF0..FFFF system MMIO bytes; required for the full compiler image |
| `--run` | off | Start only after the complete load and any requested verification succeed |
| `--verify` | off | Read back words and an optional last byte, checking all loaded bytes |
| `--write-delay SECONDS` | `0` | Pause after each transmitted word; e.g. `0.001` for 1 ms |

For example, with both pacing and readback:

```text
load build/software/hello.bin --skip-mmio --write-delay 0.001 --verify --run
```

For one-shot use outside the console, the equivalent Make targets are
`make load-run PROGRAM=src/examples/hello.cf SKIP_UART_MMIO=1`, optionally with
`WRITE_DELAY=0.001 VERIFY=1`. `make upload IMAGE=...` loads an existing image and
leaves the CPU halted. Keep one owner of the UART port: issue commands inside
the console while it is open.

### Detailed loading behavior

Install the root Python package and pyserial in the active environment.
After successful build/programming and connecting the GPIO1 UART pins:

```sh
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> status
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> sram-check
python -m prim asm -i cpu/tests/test.asm -o build/example.bin
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> load build/example.bin
```

Expect halted=true, break=false, PC=0000 after configuration. `sram-check`
halts first, preserves/restores eight scratch bytes at 2000, and checks byte
and unaligned word transfers.

The host script also exposes the CPU controls as individual commands:

```sh
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> halt
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> pc
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> step
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> run
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> reset-halt
```

`halt` waits for confirmed halt, `step` waits for retirement and renewed halt,
and `reset-halt` resets only the CPU. `step` and `pc` first query status and
reject a running CPU with a clear message; they do not silently halt it.
The debug library continues to handle CPU output and asynchronous BREAK
notifications while waiting for replies. Each CLI invocation closes its port.

`load` performs RESET-HALT and loads a raw CPU binary at zero using the persistent
16-bit write mode. It streams SRAM words without waiting between values, while
a concurrent reader counts one OK per word. Words are little-endian; an odd
final byte uses a byte write without changing its neighbor. Readback is disabled
by default. `--verify` enables word reads plus an optional final byte read,
setting the read pointer once and then using its automatic increment.
`r` returns two hex digits and `R` four, without a `K` prefix. Verification sends
the next `R` after receiving digit three, overlapping its transmission with the
fourth reply digit. No FPGA read-request queue is used. The final reply is fully
consumed before an optional byte read or any subsequent command. Update the FPGA
bitstream along with the host: older bitstreams return prefixed memory reads
and are incompatible. Reply transmission alone takes about 11.4 seconds for
65520 bytes at 115200 baud, plus USB/host latency for each word.
`--run` resumes after successful loading and, when requested, verification.
A failed verification does not start the CPU. Token streams are not CPU binaries.

This SRAM loader intentionally sends ahead of the ordinary protocol's per-value
wait rule. Data may be lost if a bus operation takes too long. Missing/invalid
OKs cause an error, never an automatic retry or RUN. A failed streaming console
session closes to discard late replies: restart the console and load the full
image again manually. `--write-delay 0.001` inserts a 1-ms pause after each word
has drained to the UART; the default is zero. With Make use `WRITE_DELAY=0.001`.
Correct OK counts do not prove data integrity; `--verify` checks actual contents.

The loader reports Writing (and, with `--verify`, Verifying) byte counts at least once per second while
transfers advance, and at the start/end of each phase. Updates replace the same
terminal line without newlines; normal messages and CPU output remain available.
Full images require many
individual operations; optional readback still waits for each reply and may take
several minutes with USB-UART latency. The console prompt remains visible while its worker loads the
image. Wait for `Loaded ...` (or `Loaded and verified ...` with `--verify`)
and, with `--run`, `CPU running`;
the initial MMIO-skipping messages do not indicate completion.

Images of 1..65520 bytes load directly. Compiler memory exports contain 65536
bytes; those require the explicit `--skip-mmio` option:

```sh
python -m prim export -i build/src/base.tf.toml -s memory -o build/base.bin
python boards/olimex_ice40hx8k_evb/host.py --port /dev/serial/by-id/<uart-adapter> load build/base.bin --skip-mmio
# With an image that has executable entry code at PC 0000, optionally add --run.
```

With a full 64-KiB image, the script reports the omitted bytes at
`0xFFF0..0xFFFF`, writes only `0x0000..0xFFEF` (65520 bytes), optionally verifies
them, and preserves the physical SRAM bytes hidden behind MMIO. Timer registers,
reserved bytes, LEDs and UART are all excluded. Any image exceeding 65520 bytes
requires `--skip-mmio`.
Only included MMIO bytes are reported; no trimming occurs without this option.
Empty images and images larger than 65536 bytes remain errors. Invalid sizes
and a missing skip option are rejected before connecting to the board.
The base-library example demonstrates loading a compiler image; it does not
install a runnable application entry at PC 0000.

## CPU timer/LED/UART registers

| Address | Read | Write |
|---|---|---|
| FFF0..FFF1 | timer COUNT, 16 bits | set COUNT |
| FFF2..FFF3 | timer COMPARE, 16 bits | set COMPARE |
| FFF4..FFF5 | timer CSR: ENABLE/AUTO/INTEN in bits 0/1/2 | set control bits |
| FFF6..FFFC | reserved, zero | ignored |
| FFFD | LED1 in bit 0, LED2 in bit 1; other bits zero | set LEDs from bits 0/1; ignore bits 7:2 |
| FFFE | bit 0 received, bit 1 TX buffer free; other bits zero | ignored |
| FFFF | last received seven-bit byte; clear received on final bus ACK | enqueue seven-bit CPU TX byte; wait when full |

The [timer reference](../../system/docs/timer_mmio.md) describes counting and
word access behavior. The board uses `TIMER_DIVISOR=25000` at 25 MHz (1 ms per
counting interval). Timer IRQ is connected to the CPU, which does not yet
handle interrupts. CPU halt/debug reset leave the timer running.

Reading an empty RX register returns the last byte, initially zero. New reception
wins over simultaneous consumption. TX buffer free does not imply an idle UART
wire: the previous frame can still be active. Debug replies/BREAK have priority
at byte boundaries. RESET-HALT preserves both UART buffers; full system reset
clears them. Word operations combine the selected MMIO/SRAM lanes little-endian,
including wrapping to address zero. A full RX register never blocks debug RX.

## Interactive console (POSIX / Arch Linux)

Rebuild and flash the matching FPGA image before using the new q/status/input
protocol. Install the root Python package and pyserial in the active environment:

```sh
.venv/bin/python -m pip install -e . pyserial
.venv/bin/python boards/olimex_ice40hx8k_evb/host.py console --help
.venv/bin/python boards/olimex_ice40hx8k_evb/host.py --port "$PORT" console
```

Set PORT to the separate UART adapter's `/dev/serial/by-id/...` path. One process
owns the port. Do not open another serial terminal or CLI session alongside it.
CPU data are seven-bit; UTF-8 input is rejected instead of becoming debug bytes.

| Key | Action |
|---|---|
| Ctrl+B | Switch between CPU mode and local debug prompt (not sent to CPU) |
| Ctrl+D | Quit either mode without HALT/RESET |
| Ctrl+V, then a byte | Send that byte literally to CPU, including Ctrl+B/Ctrl+D |
| Empty Enter in debug prompt | Show a fresh debug prompt |
| Enter in CPU mode | Send Enter to CPU |

The console uses raw input so Enter (CR) and Ctrl+B (STX) are distinct. `help` or
`?` prints every command/keybinding; `console --help` works without opening USB.
The local prompt accepts these commands (no port argument is needed there):

```text
help
halt                     # stop is an alias
step
reset-halt
run
pc
status
uart-status
sram-check
load build/example.bin
load build/program.bin --skip-mmio --run
load build/program.bin --skip-mmio --verify --run
quit
```

CPU output and asynchronous BREAK continue while entering commands, displaying
help, loading/verifying an image, or awaiting replies. Loading and RUN use the
same open connection, preserving the program's first output. One reader routes
all incoming bytes; a separate input sender uses q status to send at most one
CPU byte per free RX register. Queued keyboard input waits when the CPU is halted
or its RX register is full, while debug controls remain available. Credit polls
cannot interrupt a persistent debug write sequence. Memory debug operations
still require confirmed CPU halt. CPU-only reset does not clear queued UART data.

Ctrl+D/quit closes the session, discards unsent local input/commands and restores
terminal settings; it does not abort an already-started FPGA bus operation.
A protocol timeout, invalid reply or disconnected adapter terminates the session
instead of misinterpreting late replies. Regular one-shot CLI commands still
close their port on completion; use console for continuous output monitoring.
The user has confirmed board operation and streaming loading; no physical
UART/flash operation was performed by the development agent.

## Resource comparison for the duplex extension

Historical measurements before iCE40-IO integration: same Rev.B board target,
25 MHz PLL and seed 1, previous GPIO1.33/34 UART:

| Resource | Before duplex | After duplex | Delta |
|---|---:|---:|---:|
| Placed logic cells | 3145 | 3216 | +71 |
| Synthesis LUT4 | 2712 | 2766 | +54 |
| Flip-flops | 779 | 795 | +16 |
| Carry cells | 203 | 224 | +21 |
| PLLs | 1 | 1 | 0 |
| Block RAM | 0 | 0 | 0 |

The extra 16 flip-flops implement the two seven-bit buffers and their flags.
Reported routed maximum changes from 54.72 to 50.12 MHz; timing passes at 25 MHz.
Baseline reports: `build/uart-duplex-before/`; current reports/bitstream:
`build/olimex_ice40hx8k_evb/`. No board hardware/timing measurement is implied.
