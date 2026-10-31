#!/usr/bin/env python3
"""Build the standalone Forth kernel: python forth/build.py [--output DIR]."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# Support direct invocation from any working directory without installation.
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'src'))

from forth.image import Image, KERNEL_START, RAM_END, USER_LIMIT
from forth.kernel.boot import VARIABLES, emit_kernel


def build_image():
    image = Image()
    emit_kernel(image)
    image.resolve()
    return image


def memory_map(image):
    return {
        'format': 'prim-forth-map-v1',
        'stage': 'AP8 interpreter/compiler, control, data definitions and strings',
        'image': {'file': 'kernel.bin', 'start': 0, 'size': RAM_END,
                  'endianness': 'little', 'entry': 0},
        'symbols': dict(sorted(image.symbols.items())),
        'variables': VARIABLES,
        'words': [{**word, 'header': image.symbols[word['header']],
                   'xt': image.symbols[word['xt']]} for word in image.words],
        'regions': [
            {'name': name, 'start': start, 'end_exclusive': end}
            for name, start, end in (
                ('boot', 0, 0x0100), ('variables', 0x0100, 0x0200),
                ('input', 0x0200, 0x0280), ('string', 0x0280, 0x0300),
                ('control', 0x0300, 0x0380), ('scratch', 0x0380, KERNEL_START),
                ('kernel', KERNEL_START, image.symbols['kernel_end']),
                ('alignment', image.symbols['kernel_end'], image.symbols['user_start']),
                ('user', image.symbols['user_start'], USER_LIMIT),
                ('reserved', USER_LIMIT, RAM_END), ('mmio', RAM_END, 0x10000),
            )
        ],
    }


def write_artifacts(directory):
    image = build_image()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'kernel.bin').write_bytes(image.memory)
    (directory / 'kernel.map.json').write_text(
        json.dumps(memory_map(image), indent=2, sort_keys=True) + '\n', encoding='utf-8')
    (directory / 'kernel.disasm').write_text(image.disassembly(), encoding='utf-8')
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build' / 'forth')
    args = parser.parse_args()
    image = write_artifacts(args.output)
    print(f'Built {args.output / "kernel.bin"}: {len(image.memory)} RAM bytes; '
          f'USER_START=0x{image.symbols["user_start"]:04x}; '
          f'{len(image.words)} kernel words (interactive interpreter)')


if __name__ == '__main__':
    main()
