# VGA text controller

`rtl/vga_text.v` implements monochrome 640x480 output with 80x30 cells of
8x16 pixels. It uses FPGA block RAM only: 4096 bytes of video RAM plus a
4096-byte, 256-character font ROM. CPU program/data memory remains in the
existing board SRAM; no external SDRAM is required for video.

## Implementation and integration

The implemented steps are:

1. Generate the font ROM from the supplied `VGA-8x16.png` atlas.
2. Generate the raster, fetch characters and font rows, and align pixels and sync.
3. Add the 32-line ring buffer, cursor overlay and frame-based blink.
4. Add MMIO and the banked CPU/debug memory window with byte-lane handling.
5. Connect the board pins, verify synthesis/routing and provide a Forth driver.

The board enables `VGA_ENABLE=1` in `prim_system`; standalone system simulations
retain the default `VGA_ENABLE=0` and the previous reserved-register behavior.
The VGA-enabled design requires a **25 MHz input clock**, shared with the CPU.
No additional PLL or clock domain is introduced.

The raster has 800 pixels per line and 525 lines per frame. Active video is
x=0..639, y=0..479; negative HSYNC is x=656..751, negative VSYNC y=490..491.
At 25 MHz this gives 31.25 kHz horizontal and **59.524 Hz vertical**. This uses
the existing approved board clock rather than the nominal 25.175 MHz VGA
pixel clock; monitor acceptance still needs checking on hardware.

Character RAM and font ROM each add one synchronous read stage. Both sync
signals, active-video gating, pixel bit index and cursor follow the same
two-stage pipeline. Bit 7 of a font byte is the leftmost pixel. The monochrome
output drives all three board RGB outputs together.

The [Lattice memory guide](https://www.latticesemi.com/view_document?document_id=47775)
describes separate read and write ports, rather than two independent read/write
ports. Accordingly, the controller reserves one RAM read every eight active
pixels for video; CPU reads use the other slots, with at most one clock of
arbitration delay. CPU writes use the independent write port and never stall
video. CPU reads are captured separately so later video fetches cannot change
an acknowledged read result. Word accesses use two byte transfers. This avoids
replicating the video RAM to obtain a second read port.

The video RAM is initialized to spaces at FPGA configuration. System reset
resets registers, timing and blink, while retaining RAM. A CPU-only debug reset
also retains all VGA registers and timing. Display continues during CPU HALT.
A simultaneous write and video read of the same address may display either
value for that character fetch; software must not depend on collision data.
There is no frame buffer swap or tear-free register latch. Update during blanking
when a visible mid-frame change is undesirable.

## CPU register and memory contract

These byte registers exist when `VGA_ENABLE=1`. All reset values are zero.
Unused writable bits read zero and are ignored on writes.

| Address | Name | Access | Bits / meaning |
|---|---|---|---|
| `FFF6` | CONTROL | R/W | 0 BANK, 1 DISPLAY, 2 CURSOR, 3 BLINK, 4 UNDERLINE |
| `FFF7` | ROW_OFFSET | R/W | Low 5 bits, modulo 32 |
| `FFF8` | CURSOR_X | R/W | Low 7 bits; screen column 0..79 |
| `FFF9` | CURSOR_Y | R/W | Low 5 bits; screen row 0..29 |
| `FFFA` | STATUS | R | Bit 0 raster blank, bit 1 vertical blank; writes ignored |
| `FFFB..FFFC` | Reserved | R/ignored W | Zero |

BANK maps all **4096 bytes** of VRAM at `E000..EFFF`, hiding and preserving
the underlying SRAM. With BANK clear, accesses go to the original SRAM;
the renderer continues to read VRAM independently. CPU and debug master share
this mapping. Keep executing code outside this window while it is mapped;
also clear BANK before loading a CPU SRAM image over the debug link.

VRAM bytes 0..2559 contain **32 physical rows of 80 bytes**. Bytes 2560..4095
are readable/writable storage unused by the renderer. The address formula is:

```
physical_row = (screen_row + ROW_OFFSET) & 31
CPU_address  = 0xE000 + physical_row * 80 + column
```

CURSOR_X/Y are screen coordinates, independent of ROW_OFFSET. Out-of-screen
coordinates hide the cursor. CURSOR overlays white; UNDERLINE selects only
scanline 15, otherwise all 16 scanlines are covered. With BLINK set, the cursor
is on for 16 frames and off for 16 frames, beginning on after system reset.
DISPLAY gates pixels only; sync/timing continue regardless of CONTROL.

To scroll upward one line, increment ROW_OFFSET modulo 32 and clear the new
bottom physical row `(ROW_OFFSET + 29) & 31` to ASCII space (80 writes).
No other text is copied. The two non-visible physical rows permit preparing
the next bottom row before changing the offset.

Byte selects remain relative to the original CPU byte address: BS=01 selects
A, BS=10 selects A+1, BS=11 selects both, with 16-bit address wrapping. Ordinary
SRAM/timer/UART transactions retain their existing path. A transfer touching
VGA is serialized by byte address, lower lane first; the first effect can occur
before the final ACK, including a word spanning timer/VGA or SRAM/VRAM.
A word at FFF8 changes both cursor coordinates through two byte writes.

## Forth output

Load [examples/console.fs](examples/console.fs) line by line into the standalone
Prim Forth over UART, then execute:

```forth
VGA-INIT
S" Prim VGA console" VGA-TYPE
VGA-CR
```

The driver provides VGA-EMIT, VGA-TYPE, VGA-CR, VGA-PAGE and cursor updates.
It handles CR, LF, backspace/DEL, line wrapping and scrolling. All driver
words must reside below E000; VGA-INIT checks HERE before enabling output.
VGA-C! temporarily maps VRAM only during a write and immediately restores
SRAM, allowing later user definitions in the E000..EFFF SRAM region. This
helper assumes BANK clear on entry and is not interrupt/reentrant safe.
KEY, ordinary EMIT/TYPE and interpreter echo still use UART. This is an
explicit VGA output driver; automatic redirection of the kernel console is
a separate software extension.

The font contains 256 glyphs, including the supplied extended character set;
printable ASCII uses its usual byte values. No attribute/color bytes or
escape-sequence parser are implemented in hardware.

## Board wiring

The board wrapper targets the **Olimex iCE40-IO Rev.A expansion board**,
connected pin-for-pin to GPIO1 of the iCE40HX8K-EVB Rev.B. The assignments
combine the official [expansion-board netlist](../boards/netlists/ICE40-IO_Rev_A.net)
with the [FPGA-board Rev.B netlist](../boards/netlists/iCE40HX8K-EVB_Rev_B.net).
Both are saved locally; [provenance and checksums](../boards/netlists/README.md)
identify the upstream snapshots.

| FPGA signal | iCE40-IO signal | GPIO1 / GPIO_In1 pin | FPGA ball |
|---|---|---|---|
| vga_hsync | VGA_HSYNC | 20 | J4 |
| vga_vsync | VGA_VSYNC | 18 | H2 |
| vga_red[2] | VGA_RED1 | 27 | E3 |
| vga_red[1] | VGA_RED2 | 29 | H5 |
| vga_red[0] | VGA_RED3 | 34 | F3 |
| vga_green[2] | VGA_GREEN1 | 32 | H3 |
| vga_green[1] | VGA_GREEN2 | 30 | F2 |
| vga_green[0] | VGA_GREEN3 | 28 | H6 |
| vga_blue[2] | VGA_BLUE1 | 26 | F1 |
| vga_blue[1] | VGA_BLUE2 | 24 | H4 |
| vga_blue[0] | VGA_BLUE3 | 22 | G2 |

Each RGB channel uses the expansion board's existing 470 ohm / 1 kohm /
1.8 kohm resistor network. Bus bit 2 drives COLOR1 (470 ohm), bit 1 COLOR2
(1 kohm), and bit 0 COLOR3 (1.8 kohm). All nine outputs carry the monochrome
pixel: `000` for black, `111` for white on each channel. No extra VGA resistors
or discrete breakout wiring are required; plug the monitor into VGA1.

The debug UART moves to the free pass-through pins **GPIO1.5 (FPGA RX, E4)**
and **GPIO1.7 (FPGA TX, B2)**, accessible on iCE40-IO's GPIO_Out1 connector.
Connect adapter TX to pin 5, adapter RX to pin 7, and adapter GND to pin 2.
Use a 3.3 V USB-UART adapter; 115200/8N1 and the debug protocol are unchanged.
The previous pins 33/34 connect to IrDA_Tx / VGA_RED3 and must no longer be
used for the UART adapter. PS/2 and IrDA are not driven by this VGA controller.

Physical wiring and monitor output have not been tested; no bitstream has
been programmed by this change.

## Verification and resources

From the repository root:

```sh
python3 vga/tests/test_vga.py
.venv/bin/python vga/tests/test_forth.py
cmake -S . -B build/sim
cmake --build build/sim
ctest --test-dir build/sim --output-on-failure
python3 boards/olimex_ice40hx8k_evb/build.py build --output build/vga-ice40-io
```

The RTL scoreboard checks complete 800x525 frames against an independent raster
and address calculation: glyph bit order, blanking, sync widths, scroll wrap,
block/underline/blinking cursor, concurrent CPU traffic, byte masks, bank/window
crossings, register masks, SRAM isolation and reset retention. The Forth check
executes the driver on the real Python Prim CPU against an independent bank
model, checking 64 newlines, 35 physical scrolls, cleared rows, output and
backspace, SRAM preservation and hardware stack bounds. It does not replace
an end-to-end Forth/serial/VGA hardware test.

The 2026-10-31 seed-1 board build with iCE40-IO Rev.A uses **4020/7680 logic
cells**, **16/32 EBRs**
(8 VRAM + 8 font) and the existing PLL. Routed timing passes at 25 MHz;
nextpnr reports a 30.53 MHz maximum internal clock. Logs and bitstream are in
`build/vga-ice40-io/`. These are implementation results, not physical monitor
or external SRAM timing measurements.

The generated font RTL is checked in; normal builds have no image dependency.
To regenerate it, use a Python environment with Pillow:

```sh
python3 vga/font.py --source VGA-8x16.png
```

The atlas contains 16x16 cells of 9x17 pixels. The generator crops each cell to
8x16, discarding the separator column and row, and emits one byte per scanline.
