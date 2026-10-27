"""Debugger regressions without an interactive terminal (requires .[debug])."""
import contextlib
import io
import unittest
from unittest.mock import patch

try:
    from blessed import Terminal
except ModuleNotFoundError:
    Terminal = None

from prim.cpu import Prim

if Terminal is not None:
    from prim.debugger import Mif, PrimDebug, debug


@unittest.skipIf(Terminal is None, 'Install .[debug] to test the debugger')
class DebuggerChecks(unittest.TestCase):
    def setUp(self):
        self.memory = Mif(bytes(65536), uart_rx_init=b'AB')
        self.cpu = Prim(self.memory)
        self.debugger = PrimDebug(self.cpu, Terminal(), symbols=[])

    def test_inspection_does_not_consume_uart(self):
        self.memory._mem[0] = 0x12
        self.assertEqual(self.memory.peek16(0xffff), 0x1241)
        self.assertEqual(self.memory.peek8(0x1ffff), ord('A'))
        self.debugger.memViewAddr = 0xfff8
        self.cpu._pc = 0xffff
        self.debugger.numlits = [0xfffe]
        with contextlib.redirect_stdout(io.StringIO()):
            self.debugger.showMemory(0, 0, 80, 0)
            self.debugger.showCode(0, 0, 80, 4)
            self.debugger.showCurrent(0, 80, 0)
            self.debugger.userReadMemoryCmd(['r', 'fffe', '2'])
        self.assertEqual(list(self.memory.uart_fifo_rx), list(b'AB'))
        self.assertEqual(self.memory.read16(0xfffe), 1 | ord('A') << 8)
        self.assertEqual(self.memory.read8(0xffff), ord('B'))
        self.assertEqual(self.memory.peek8(0xfffe), 0)
        self.assertEqual(self.memory.peek8(0xffff), 0)

    def test_uart_text_is_utf8_and_cpu_can_read_it(self):
        self.memory.read16(0xffff)
        self.memory.read8(0xffff)
        self.debugger.input = 'uart Grüße 🙂'
        self.debugger.userCommand()
        for expected in 'Grüße 🙂'.encode('utf-8'):
            self.assertEqual(self.cpu.read8(0xfffe), 1)
            self.assertEqual(self.cpu.read8(0xffff), expected)
        self.assertEqual(self.cpu.read8(0xfffe), 0)

    def test_missing_uart_text_does_not_queue_command(self):
        self.debugger.uartSendCmd('uart')
        self.assertEqual(list(self.memory.uart_fifo_rx), list(b'AB'))
        self.assertIn('Missing UART text', self.debugger.messages)

    def test_reset_restores_memory_and_initial_uart(self):
        self.memory.read8(0xffff)
        self.memory.uart_rx(0xff)
        self.memory.write8(100, 42)
        self.cpu._pc = 100
        self.debugger.silentBreakpoints.add(200)
        self.debugger.breakpoints.add(300)
        self.debugger.input = 'reset'
        self.debugger.userCommand()
        self.assertEqual(self.cpu._pc, 0)
        self.assertEqual(self.memory.peek8(100), 0)
        self.assertEqual(list(self.memory.uart_fifo_rx), list(b'AB'))
        self.assertFalse(self.debugger.silentBreakpoints)
        self.assertEqual(self.debugger.breakpoints, {300})

    def test_uart_bytes_are_validated(self):
        for invalid in ('A', -1, 256, True):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                self.memory.uart_rx(invalid)
        self.assertEqual(list(self.memory.uart_fifo_rx), list(b'AB'))

    def test_reset_without_initial_image_restores_zero_memory(self):
        memory = Mif()
        memory.write8(100, 42)
        memory.uart_rx(65)
        memory.reset()
        self.assertEqual(memory.peek8(100), 0)
        self.assertEqual(memory.peek8(0xfffe), 0)

    def test_explicit_uart_file_errors_are_reported(self):
        with patch('prim.debugger.load_program'), \
                patch('builtins.open', side_effect=FileNotFoundError('missing UART file')):
            with self.assertRaisesRegex(FileNotFoundError, 'missing UART file'):
                debug('program.tf.toml', 'missing.uart')


if __name__ == '__main__':
    unittest.main()
