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
system clock of **54.72 MHz**. This is an internal timing report, not a supported
operating-frequency claim above the selected 25 MHz.

The UART pin assignment requested by the user is GPIO1 pin 33 for FPGA RX
(ball G3) and GPIO1 pin 34 for FPGA TX (ball F3). Artifacts are in
`build/olimex_ice40hx8k_evb/`, including the bitstream `prim.bin`. Utilization is
3145/7680 logic cells, one PLL, and no block RAM. No image has been programmed.
The build stops before icepack if timing fails; there is no timing override.

For comparison, the original direct-100-MHz attempt failed at about 52–54 MHz;
its logs remain under `build/board-initial-100mhz/`.
Physical SRAM timing has not been measured. Place-and-route internal-clock
timing alone does not establish external SRAM setup/hold margins.

## UART wiring

GPIO1 pins 33/34 are the selected UART connection. The Rev.B netlist maps
GPIO1.33 to PIO3_14/IOL_8A (FPGA ball G3) and GPIO1.34 to PIO3_15/IOL_8B
(FPGA ball F3). Both assignments are defined directly in `board.pcf`, the
single pin-constraint source used by CMake and the standalone build script:

```tcl
set_io -pullup yes uart_rx G3
set_io uart_tx F3
```

| USB-UART adapter | Rev.B board connection | FPGA ball |
|---|---|---|
| TX, 3.3 V logic | GPIO1 pin 33, FPGA RX | G3 |
| RX | GPIO1 pin 34, FPGA TX | F3 |
| GND | GPIO1 pin 2, GND | — |

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

LED1 shows confirmed CPU halt, LED2 is a heartbeat (about 1.49 Hz at 25 MHz).
SRAM A17:A15 are held at zero: the CPU uses the first 64 KiB of the 512 KiB
physical device. Both byte enables are wired low on the board; the existing
whole-word controller preserves neighboring bytes. Read/write phases last
three system clocks (120 ns), with one 40 ns cycle per existing
turnaround/setup/hold/release phase. The UART divider is 217 clocks/bit.
The configuration RESET button reconfigures the FPGA; BUT1 is the logic reset.

## Build and programming

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
stale binary. The board test is included in CTest as `olimex_board_checks`. All 13 CTest
suites passed; the board-specific tests additionally check PLL startup, reset
release, loss of LOCK, recovery and UART at 25 MHz. `pll_sim.v` is a test-only
ideal frequency/LOCK model and is never included in production synthesis;
analog PLL acquisition/jitter is outside the simulation. Logs: `build/olimex-validation/ctest.log`.

## First contact and loading

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
and unaligned word transfers. `load` performs RESET-HALT, loads a raw CPU binary
at zero, verifies every byte and leaves the CPU halted; add `--run` to execute.
Token streams are not CPU binaries. The current simple loader rejects 65536-byte
images because address FFFF has a UART write side effect and cannot be loaded
as SRAM through this memory map. A raw program of at most 65535 bytes is accepted.

UART and flash operations require the user's actual hardware and have not been
performed from this workspace. The host helper runs synchronously; output from
a running program is handled by the underlying library during later commands.
