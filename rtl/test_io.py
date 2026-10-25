#!/usr/bin/env python3
"""UART framing plus CPU/SRAM/MMIO comparison with serial output decoding."""
import subprocess
import unittest

import test_sram
from compare import PrimAsm, Op


class IoChecks(test_sram.SramChecks):
    with_uart = True

    def test_serial_hello_world(self):
        message = b'Hello, World!\r\n'
        asm = ' '.join(f'{byte} 0xffff c!' for byte in message)
        for timing in test_sram.TIMINGS:
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
        for timing in test_sram.TIMINGS:
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
                binary = self.directory / f'uart-{divider}'
                subprocess.run([
                    test_sram.args.iverilog, '-g2012', '-s', 'tb_uart',
                    '-P', f'tb_uart.CLKS_PER_BIT={divider}', '-o', str(binary),
                    str(test_sram.RTL / 'tb_uart.sv'), str(test_sram.RTL / 'uart_tx.v'),
                ], capture_output=True, text=True, check=True, timeout=30)
                result = subprocess.run([test_sram.args.vvp, str(binary)],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS UART', result.stdout)


if __name__ == '__main__':
    unittest.main(argv=[__file__, *test_sram.remaining])
