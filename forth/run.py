#!/usr/bin/env python3
"""Run the actual Prim Forth kernel with terminal UART I/O in the Python CPU."""
import argparse
import os
from pathlib import Path
import select
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'src'))

from forth.build import build_image
from prim.cpu import Prim, MemoryIf


class ConsoleMemory(MemoryIf):
    """Flat RAM plus terminal-backed UART; no timer simulation."""
    def __init__(self, image, source, sink):
        self.data = bytearray(65536)
        self.data[:len(image)] = image
        self.source, self.sink = source, sink
        self.pending = None
        self.last = 0
        self.ie = 0
        self.eof = False

    def read8(self, address):
        address &= 65535
        if address == 0xFFFE:
            if self.pending is None:
                try:
                    fd = self.source.fileno()
                except (AttributeError, OSError):
                    byte = self.source.read(1)
                else:
                    if not select.select([fd], [], [], 0.01)[0]:
                        return 2 | self.ie
                    byte = os.read(fd, 1)
                if byte:
                    self.pending = byte[0] & 127
                else:
                    self.eof = True
            return 2 | self.ie | int(self.pending is not None)
        if address == 0xFFFF:
            if self.pending is not None:
                self.last, self.pending = self.pending, None
            return self.last
        return self.data[address]

    def read16(self, address):
        return self.read8(address) | self.read8(address + 1) << 8

    def write8(self, address, value):
        address &= 65535
        if address == 0xFFFF:
            self.sink.write(bytes([value & 127]))
            self.sink.flush()
        elif address == 0xFFFE:
            self.ie = value & 12
        else:
            self.data[address] = value & 255

    def write16(self, address, value):
        self.write8(address, value)
        self.write8(address + 1, value >> 8)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    image = build_image()
    memory = ConsoleMemory(image.memory, sys.stdin.buffer, sys.stdout.buffer)
    cpu = Prim(memory)
    saved = None
    try:
        if sys.stdin.isatty():
            import termios
            import tty
            fd = sys.stdin.fileno()
            saved = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            active = termios.tcgetattr(fd)
            active[0] &= ~termios.ICRNL
            active[1] &= ~termios.OPOST
            termios.tcsetattr(fd, termios.TCSANOW, active)
        while True:
            if memory.eof and cpu._pc == image.symbols['raw_key']:
                return 0
            cpu.step()
    except KeyboardInterrupt:
        return 0
    finally:
        if saved is not None:
            termios.tcsetattr(fd, termios.TCSANOW, saved)


if __name__ == '__main__':
    sys.exit(main())
