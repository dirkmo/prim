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

    def test_cpu_timer_registers(self):
        # Keep ENABLE clear: compare the CPU's byte/word adapter with static MMIO.
        asm = ('0x1234 0xfff0 ! 0xabcd 0xfff2 ! 6 0xfff4 ! '
               '0xfff0 @ 0xfff2 @ 0xfff4 @ '
               '0x5678 0xfff1 ! 0xfff0 @ 0xfff2 @ 0xfff1 @ '
               '0xfe00 0xfff3 ! 0xfff2 @ 0xfff4 @ '
               '0xff 0xfff5 c! 0xfff5 c@ '
               '0x4142 0xffef ! 0xffef @ 0xffef c@ 0xfff0 c@ '
               '0xffff 0xfff6 ! 0xfff6 @ 0xfffc c@')
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), timing)

    def test_led_register_readback(self):
        # Upper bits are ignored; byte and word accesses read back bits 1:0.
        asm = ' '.join(f'{value} 0xfffd c! 0xfffd c@ 0xffff c!'
                       for value in (0, 1, 2, 3, 0xfc, 0xff))
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                actual = self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), timing)
                self.assertEqual(actual, bytes((0, 1, 2, 3, 0, 3)))

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

    def test_output_depends_on_tx_free_status(self):
        asm = '65 0xffff c! 66 0xffff c! 0xfffe c@ 48 + 0xffff c!'
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                actual = self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), timing)
                self.assertEqual(actual[:2], b'AB')
                self.assertIn(actual[2:], (b'0', b'2'))

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
