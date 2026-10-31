#!/usr/bin/env python3
"""Regenerate the 256-character 8x16 ROM from the supplied VGA atlas (Pillow)."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate(source):
    from PIL import Image
    with Image.open(source) as image:
        if image.size != (144, 272):
            raise ValueError('expected a 144x272 atlas (16x16 cells of 9x17 pixels)')
        image = image.convert('RGB')
        rows = []
        for char in range(256):
            for y in range(16):
                rows.append(sum((sum(image.getpixel(((char % 16)*9+x, (char//16)*17+y))) > 384)
                                << (7-x) for x in range(8)))
    lines = [
        '// Generated from VGA-8x16.png: 16 columns, 9x17 cells; crop to 8x16.',
        '// Byte order: character * 16 + scanline; bit 7 is the leftmost pixel.',
        'module vga_font(input i_clk, input i_en, input [11:0] i_addr, output reg [7:0] o_data);',
        'reg [7:0] rom [0:4095];',
        'initial begin',
    ]
    for char in range(256):
        lines.append('    ' + ' '.join(f"rom[{i}] = 8'h{rows[i]:02x};"
                                      for i in range(char*16, char*16+16)))
    lines += ['end', 'always @(posedge i_clk) if (i_en) o_data <= rom[i_addr];', 'endmodule', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'VGA-8x16.png')
    parser.add_argument('--output', type=Path, default=ROOT / 'vga/rtl/vga_font.v')
    args = parser.parse_args()
    args.output.write_text(generate(args.source), encoding='ascii')


if __name__ == '__main__':
    main()
