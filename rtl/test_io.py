#!/usr/bin/env python3
"""UART framing plus CPU/SRAM/MMIO comparison with serial output decoding."""
import unittest

from prim.assembler import PrimAsm
from prim.isa import PrimOpcodes as Op
from sim_support.config import run_tests
from sim_support.paths import TIMINGS
from sim_support.scenarios import SramScenarios
from sim_support.unittest_bridge import SramHarness


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
                self.assertEqual(actual, chunk)

    def test_serial_word_crossings(self):
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                # FFFE -> high byte to UART; FFFF -> low byte to UART, high to 0.
                asm = ('0x4142 0xfffe ! 0xfffe @ '
                       '0x4344 0xffff ! 0xffff @ 0 c@ '
                       '0x5556 0xffff c! 0xffff c@')
                actual = self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), timing)
                self.assertEqual(actual, b'ADV')

    def test_uart_unit(self):
        for divider in (1, 4, 7):
            with self.subTest(divider=divider):
                self.assertIn('PASS UART', self.simulation.run_uart(divider))


if __name__ == '__main__':
    run_tests(IoChecks)
