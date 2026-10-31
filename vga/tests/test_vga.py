#!/usr/bin/env python3
"""Run independent VGA bus and complete-raster scoreboards."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iverilog', default='iverilog')
    parser.add_argument('--vvp', default='vvp')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='prim-vga-') as directory:
        binary = Path(directory) / 'vga'
        sources = ['vga/tests/tb_vga.sv', 'vga/rtl/vga_text.v', 'vga/rtl/vga_font.v',
                   'system/rtl/memory_io.v', 'system/rtl/memory.v',
                   'system/rtl/timer_mmio.v', 'timer/rtl/timer.v']
        subprocess.run([args.iverilog, '-g2012', '-s', 'tb_vga', '-o', str(binary),
                        *sources], cwd=ROOT, check=True)
        subprocess.run([args.vvp, str(binary)], cwd=ROOT, check=True, timeout=90)


if __name__ == '__main__':
    main()
