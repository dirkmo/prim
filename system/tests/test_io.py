#!/usr/bin/env python3
"""UART framing plus CPU/SRAM/MMIO comparison with serial output decoding."""
import unittest

from prim.assembler import PrimAsm
from prim.isa import PrimOpcodes as Op
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

from support.config import run_tests
from support.paths import TIMINGS
from support.scenarios import SramScenarios
from support.unittest_bridge import SramHarness


class IoChecks(SramScenarios, SramHarness, unittest.TestCase):
    with_uart = True

    def test_serial_hello_world(self):
        message = b'Hello, World!\r\n'
        asm = ' '.join(f'{byte} 0xffff c!' for byte in message)
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                actual = self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), timing)
                self.assertEqual(actual, message)

    def test_serial_all_bytes(self):
        # Includes 00/FF and transitions with frequent backpressure.
        message = bytes(range(256))
        # Keep reference traces below their default 1000-instruction limit.
        for offset in range(0, 256, 64):
            chunk = message[offset:offset+64]
            asm = ' '.join(f'{byte} 0xffff c!' for byte in chunk)
            with self.subTest(offset=offset):
                actual = self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), (3, 4, 19))
                self.assertEqual(actual, bytes(b & 0x7f for b in chunk))

    def test_serial_word_crossings(self):
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                # FFFE -> high byte to UART; FFFF -> low byte to UART, high to 0.
                asm = ('0x4142 0xfffe ! 0xfffe @ '
                       '0x4344 0xffff ! 0xffff @ 0 c@ '
                       '0x5556 0xffff c! 0xffff c@')
                actual = self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), timing)
                self.assertEqual(actual, b'ADV')

if __name__ == '__main__':
    run_tests(IoChecks)
