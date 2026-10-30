# Compile and load programs

This is the central guide for compiling TokenForth programs and loading them
onto the Prim CPU. Run all shell commands from the repository root. The hardware
examples use the Olimex iCE40-HX8K Rev.B board with the Prim system bitstream
already programmed. See [FPGA configuration](#fpga-configuration) for that step.

## Quick start: compile and run Blink

Install the tools once (Python 3.11 or newer is required):

```sh
make setup
```

Choose the separate USB-UART adapter connected to the board's debug UART:

```sh
export PORT=/dev/serial/by-id/your-uart-adapter
```

Replace the example path with your adapter's actual device path. The UART runs
at 115200 baud; FPGA RX is GPIO1 pin 33 and FPGA TX is GPIO1 pin 34. See the
[board guide](../boards/olimex_ice40hx8k_evb/README.md) for wiring.

Compile the program, load it into CPU SRAM, and start execution:

```sh
.venv/bin/python tools/build_cf.py src/examples/blink.cf \
  -o build/software/blink.bin
make upload IMAGE=build/software/blink.bin PORT="$PORT" SKIP_UART_MMIO=1 VERIFY=1
make run PORT="$PORT"
```

`upload` resets and halts the CPU, writes SRAM, optionally verifies it, and leaves
the CPU halted. Run `make run` after a successful upload. `SKIP_UART_MMIO=1` is
required for compiler images: it skips addresses `FFF0..FFFF`, which belong to
peripherals. `VERIFY=1` checks the written SRAM by reading it back.

## Compile one or several source files

Pass `.cf` files in dependency order, with library files before their users:

```sh
.venv/bin/python tools/build_cf.py library.cf application.cf \
  -o build/software/application.bin \
  --toml build/software/application.tf.toml
```

`library.cf` and `application.cf` stand for your own source files. Each file
inherits the compiled dictionary and memory of the previous file. This produces
one combined image; no separate linker step or prior Make build is required.

The default compilation order is:

```text
src/bootstrap.cf → generated opcode words → src/base.cf → supplied .cf files
```

Do not list `base.cf` again when using this default. To omit all three base
stages, use `--no-base`:

```sh
.venv/bin/python tools/build_cf.py --no-base library.cf application.cf \
  -o build/software/application.bin
```

With `--no-base`, CPU mnemonics and compiler built-ins remain available, but
base words such as `1+`, `while`, `repeat`, and `boot!` must be supplied by your
sources if needed. The default base build uses repository sources and requires
the editable install created by `make setup`.

| Option | Effect |
|---|---|
| `-o PATH`, `--output PATH` | Write the binary memory image to this path |
| No `-o` | Write `build/software/<last source name>.bin` |
| `--toml PATH` | Also save memory, dictionary and literal information for the debugger |
| `--no-base` | Skip bootstrap, generated opcode words and `base.cf` |
| `--max-immediate-steps N` | Limit CPU steps per immediate execution; default: 100000 |

Output directories are created automatically. The `.bin` file is a complete
64-KiB CPU memory image starting at address zero. Load this binary onto the CPU;
`.cf`, `.tok.toml`, `.tf.toml`, and exported token streams are not loader inputs.

After activating the environment, the same builder is available as `prim build`:

```sh
source .venv/bin/activate
prim build library.cf application.cf -o build/software/application.bin
prim build --help
```

### Set the reset entry

The CPU starts at address zero. Define an entry word and install it in the last
source file, after its dependencies have been defined:

```forth
:main
    \ Application code goes here.
    ;

[ 'main boot! ]
```

`boot!` comes from `base.cf`. It writes `PUSH16 main; CALL; BREAK` at address zero
and preserves HERE. If `main` returns, the CPU halts at BREAK; programs such as
Blink normally remain in their main loop. With `--no-base`, your sources must
provide their own reset entry.

### Alternative: build a single program with Make

```sh
make image PROGRAM=src/examples/blink.cf
```

This builds the base library and produces `build/software/blink.tok.toml`,
`blink.tf.toml`, and `blink.bin`. `PROGRAM` defaults to `src/examples/hello.cf`.
`make base` builds just the base stages; `make software` builds all outputs of
`src/Makefile` under `build/src`.

For a single source, Make can also compile, load, and start in one command:

```sh
make load-run PROGRAM=src/examples/blink.cf PORT="$PORT" SKIP_UART_MMIO=1 VERIFY=1
```

For an image built from multiple files, use `make upload IMAGE=...` followed by
`make run`, or the console below. `load-run` rebuilds the single `PROGRAM` and
uses that result. `IMAGE` selects an existing file for `upload` and `disasm`;
it does not choose the output of `make image` or the input of `load-run`.

## Load and run from the UART console

The console keeps one connection open for CPU output and debug commands:

```sh
make uart-console PORT="$PORT"
```

Press **Ctrl+B** to open the local debug prompt, then enter:

```text
load build/software/blink.bin --skip-mmio --verify --run
```

`load` performs RESET-HALT before writing. `--run` starts execution only after
loading and any requested verification succeed. Omit `--run` to inspect or step
the loaded program while halted. Omit `--verify` to skip readback.

Use debug commands in this console while it is open, so a single process owns
the serial port. `help` lists commands, Ctrl+D exits, and Ctrl+V quotes the next
CPU byte. `make console-help` shows all controls without opening a port. CPU
output and BREAK events appear in the console.

### Loading details and retries

The system maps timer, reserved, LED and UART registers at `FFF0..FFFF`.
`--skip-mmio` (Make: `SKIP_UART_MMIO=1`) skips and reports those addresses,
writing only the 65520 bytes of SRAM at `0000..FFEF` for a full compiler image.
Without this option, the loader rejects images covering MMIO before opening the
connection. Binary images of at most 65520 bytes do not require this option.
See the [register map](../system/docs/registers.md).

Writes stream in 16-bit mode while a receiver counts acknowledgments. An odd
final byte is written separately. Readback is disabled by default; use `--verify`
or `VERIFY=1` to check contents. A verification failure prevents automatic RUN.
Progress updates replace the same line.

Missing or incorrect acknowledgments produce an error without automatic retries
or automatic RUN. After a streaming failure, reopen the console and reload the
complete image. If needed, add `--write-delay 0.001` to console `load`, or
`WRITE_DELAY=0.001` to Make, for a 1-ms pause between streamed word writes.
Acknowledgment counts alone do not verify memory contents.

### CPU control from the shell

When the console is closed, use:

```sh
make status PORT="$PORT"
make halt PORT="$PORT"
make pc PORT="$PORT"
make step PORT="$PORT"
make reset-halt PORT="$PORT"
make run PORT="$PORT"
make uart-status PORT="$PORT"
make sram-check PORT="$PORT"
```

`step` and `pc` require a confirmed halt. `stop` aliases `halt`.
CPU-only reset preserves timer, UART and LED state; an enabled timer continues
running while the CPU is halted. Programs should initialize the peripherals
they use. See the [timer reference](../system/docs/timer_mmio.md).

## Local settings

`make setup` creates `.venv`, installs the project in editable mode, and installs
`pyserial` for hardware access. Make uses `.venv/bin/python` by default; no
activation is required. Override it with `PYTHON=/path/to/python` if needed.
`SYSTEM_PYTHON` defaults to `python3` for project helper commands.

For persistent settings, copy `config.local.mk.example` to the untracked
`config.local.mk` and edit `PORT`, `PROGRAM`, `JOBS`, or `TIMEOUT`.
Command-line assignments take precedence. `TIMEOUT` is the host timeout in
seconds (default: 2). `PORT` identifies the separate USB-UART adapter;
`ICEPROG_DEVICE` and `ICEPROG_INTERFACE` (default: A) select the UM-FT2232H FPGA
programmer independently.

`make` or `make help` lists targets without building or accessing hardware.
`make check-tools` checks Python packages and the software/FPGA tools; install
system tools separately as described in the board guide.

## FPGA configuration

CPU program images are loaded into SRAM through the debug UART. The FPGA
bitstream configures the CPU and peripherals and is programmed separately:

```sh
make bitstream
make resources
make flash
```

The supported board is `BOARD=olimex_ice40hx8k_evb` (Rev.B).
`bitstream` configures and builds the CMake `fpga_bitstream` target with timing
checks. Its output is `build/olimex_ice40hx8k_evb/prim.bin`. This FPGA bitstream
is distinct from CPU images under `build/software`.

`flash` builds if necessary, then erases, programs and verifies the FPGA SPI
configuration flash using `iceprog -b`. `make all` builds software, the selected
program image, and the bitstream without programming hardware. `resources`
reports synthesis and routing results from `prim.json` and `timing.json`.
LUTs, flip-flops and carry cells are parts of logic cells and should not be
added together. See the [board guide](../boards/olimex_ice40hx8k_evb/README.md)
for programmer setup and pins.

## Debugging, assembly and tests

To inspect an optional TOML output in the Python terminal debugger:

```sh
.venv/bin/python -m pip install -e '.[debug]'
.venv/bin/python -m prim debug -i build/software/application.tf.toml
```

This debugger uses the Python CPU model. To inspect the FPGA CPU, use the UART
console. Additional build and test commands:

```sh
make asm ASM=cpu/tests/test.asm
make disasm IMAGE=build/software/test.asm.bin
make sim
make test
```

`asm` defaults to `build/software/<name>.asm.bin`; `ASM_IMAGE` selects another
output path. `sim` builds the standalone CPU simulator under `build/sim`.
`test-python` runs Python and Makefile checks; `test-rtl` builds the simulator
and runs CTest; `test` runs both. For example,
`make test-rtl TEST_ARGS='-R debug_uart --verbose'` filters CTest suites.
`test-makefile` runs workflow checks in temporary repository copies with mock
programmer and UART tools. See the [test guide](TESTS.md) for coverage.

## Output directories and cleanup

`BUILD_DIR` defaults to `build`. Its managed subdirectories can be overridden
with `SRC_BUILD_DIR`, `SOFTWARE_DIR`, `SIM_BUILD_DIR`, and `FPGA_BUILD_DIR`.
`JOBS` controls CMake build parallelism (default: 2). Avoid spaces in build paths.
The source builder's `-o` and `--toml` paths are independent of these Make settings.

`make clean` removes only the four selected managed build trees. It preserves
sources, `.venv`, local settings and unrelated files under `build`. Cleanup
accepts only subdirectories of the repository's `build/`; remove external
output directories manually. Cleanup does not access hardware.
