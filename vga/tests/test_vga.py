#!/usr/bin/env python3
"""Run independent VGA bus and complete-raster scoreboards."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import sys
import hashlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from vga.font import generate, read_rows


def check_font():
    source = ROOT / 'vga/fonts/cp437-8x16.hex'
    rows = read_rows(source)
    # Independent reference: complete glyph data from kbd v2.8.0 default8x16.
    assert hashlib.sha256(rows).hexdigest() == '602906c22a6d9e1dcf04cffe4fcfa4c9f5239762d670390b9d069bca5588d593'
    assert (ROOT / 'vga/rtl/vga_font.v').read_text() == generate(source)
    for char, tail in {'g': '0ccc7800', 'j': '66663c00',
                       'p': '6060f000', 'q': '0c0c1e00', 'y': '060cf800'}.items():
        assert rows[ord(char)*16+12:ord(char)*16+16] == bytes.fromhex(tail)
    assert rows[ord('_')*16+13] == 0xff
    assert rows[0xdb*16:0xdc*16] == bytes([0xff])*16


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iverilog', default='iverilog')
    parser.add_argument('--vvp', default='vvp')
    args = parser.parse_args()
    check_font()
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
