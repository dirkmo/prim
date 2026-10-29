#!/usr/bin/env python3
"""Build or explicitly program the Olimex iCE40HX8K-EVB Rev.B."""
import argparse
from pathlib import Path
import subprocess
import sys

BOARD = Path(__file__).resolve().parent
ROOT = BOARD.parents[1]
SOURCES = [
    ROOT / 'cpu/rtl/prim.v',
    *(ROOT / 'system/rtl' / name for name in ('memory.v', 'memory_io.v', 'bus_mux.v', 'prim_system.v')),
    *(ROOT / 'debug_uart/rtl' / name for name in
      ('uart_rx.v', 'uart_tx.v', 'uart_arbiter.v', 'debug_uart.v', 'debug_uart_link.v')),
    BOARD / 'top.v',
]


def run(command, *, log=None):
    if log:
        with log.open('w') as output:
            result = subprocess.run([str(c) for c in command], cwd=ROOT,
                                    stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{command[0]} failed; see {log}\n{log.read_text()[-6000:]}')
    else:
        subprocess.run([str(c) for c in command], cwd=ROOT, check=True)


def build(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    binary = output / 'prim.bin'
    # A failed rebuild must never leave an old image that appears current.
    binary.unlink(missing_ok=True)
    # Source filenames are fixed; output paths may contain spaces.
    def quote(path):
        return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"') + '"'
    script = 'read_verilog -I' + quote(ROOT / 'cpu/rtl') + ' ' + ' '.join(quote(p) for p in SOURCES)
    script += '\nsynth_ice40 -top olimex_ice40hx8k_evb -json ' + quote(output / 'prim.json') + '\n'
    (output / 'synth.ys').write_text(script)
    (output / 'clocks.py').write_text("ctx.addClock('clk_100mhz', 100)\n")
    run([args.yosys, '-s', output / 'synth.ys'], log=output / 'synth.log')
    run([args.nextpnr, '--hx8k', '--package', 'ct256', '--json', output / 'prim.json',
         '--pcf', BOARD / 'board.pcf', '--asc', output / 'prim.asc', '--freq', '25',
         '--pre-pack', output / 'clocks.py', '--seed', '1', '--report', output / 'timing.json'], log=output / 'nextpnr.log')
    run([args.icepack, output / 'prim.asc', binary], log=output / 'icepack.log')
    print(f'Bitstream: {binary}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    p = commands.add_parser('build', help='Synthesize, route with timing checks, and pack')
    p.add_argument('--output', type=Path, default=ROOT / 'build/olimex_ice40hx8k_evb')
    p.add_argument('--yosys', default='yosys')
    p.add_argument('--nextpnr', default='nextpnr-ice40')
    p.add_argument('--icepack', default='icepack')
    p.set_defaults(function=build)
    p = commands.add_parser('program', help='Explicitly erase/program/verify SPI flash with iceprog -b')
    p.add_argument('bitstream', type=Path)
    p.add_argument('--iceprog', default='iceprog')
    p.add_argument('--device', help='iceprog device selector; useful with multiple FTDI devices')
    p.add_argument('--interface', choices=list('ABCD'), default='A')
    p.set_defaults(function=program)
    args = parser.parse_args(argv)
    try:
        args.function(args)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'{exc}\n')


def program(args):
    binary = args.bitstream.resolve()
    if not binary.is_file():
        raise ValueError(f'Bitstream not found: {binary}; build successfully first')
    command = [args.iceprog, '-I', args.interface]
    if args.device:
        command += ['-d', args.device]
    # User's working programming mode. -b bulk-erases SPI flash, NOT FPGA SRAM.
    run([*command, '-b', binary])


if __name__ == '__main__':
    main()
