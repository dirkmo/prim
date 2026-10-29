#!/usr/bin/env python3
"""Board host CLI controls and MMIO-safe image loading without USB hardware."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from prim_debug_uart import Status, UARTStatus

BOARD = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('board_host', BOARD / 'host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class Client:
    def __init__(self, *, halted=True):
        self.halted = halted
        self.pc = 0x4321
        self.memory = bytearray([0x5a]) * 65536
        self.transport = SimpleNamespace(close=Mock())
        self.calls = []
        self.reads = []
        self.corrupt_address = None

    def status(self):
        self.calls.append('status')
        return Status(self.halted, False)

    def uart_status(self):
        self.calls.append('uart_status')
        return UARTStatus(True, False)

    def read_pc(self):
        self.calls.append('read_pc')
        return self.pc

    def halt(self):
        self.calls.append('halt')
        self.halted = True

    def run(self):
        self.calls.append('run')
        self.halted = False

    def step(self):
        self.calls.append('step')
        self.pc += 1

    def reset_halt(self):
        self.calls.append('reset_halt')
        self.halted = True
        self.pc = 0

    def write_bytes(self, values, address=None):
        values = bytes(values)
        # Fail the test if a write could reach the UART MMIO address.
        if address is None or address + len(values) > 0xfffe:
            raise AssertionError('write touched UART MMIO')
        self.calls.append(('write_bytes', address, values))
        self.memory[address:address + len(values)] = values

    def read8(self, address):
        if address >= 0xfffe:
            raise AssertionError('skipped image byte was verified')
        self.reads.append(address)
        return self.memory[address] ^ int(address == self.corrupt_address)


class HostChecks(unittest.TestCase):
    def invoke(self, client, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(host.DebugUART, 'connect', return_value=client) as connect, \
                redirect_stdout(output), redirect_stderr(errors):
            host.main(['--port', '/dev/test-uart', *arguments])
        connect.assert_called_once_with('/dev/test-uart', timeout=2.0)
        client.transport.close.assert_called_once()
        return output.getvalue(), errors.getvalue()

    def test_separate_control_commands(self):
        cases = {
            'uart-status': ['uart_status'], 'halt': ['halt'], 'run': ['run'], 'reset-halt': ['reset_halt'],
            'step': ['status', 'step', 'read_pc'], 'pc': ['status', 'read_pc'],
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                client = Client()
                output, errors = self.invoke(client, command)
                self.assertEqual(client.calls, expected)
                self.assertFalse(errors)
                if command == 'pc':
                    self.assertEqual(output, 'pc=0x4321\n')
                if command == 'step':
                    self.assertEqual(output, 'pc=0x4322\n')

    def test_step_and_pc_require_halt_and_close_on_error(self):
        for command in ('step', 'pc'):
            with self.subTest(command=command):
                client = Client(halted=False)
                with self.assertRaisesRegex(RuntimeError, 'requires a halted CPU'):
                    self.invoke(client, command)
                self.assertEqual(client.calls, ['status'])
                client.transport.close.assert_called_once()

    def test_full_image_requires_explicit_option_before_connect(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            image.write_bytes(bytes(65536))
            errors = io.StringIO()
            with patch.object(host.DebugUART, 'connect') as connect, redirect_stderr(errors):
                with self.assertRaises(SystemExit) as raised:
                    host.main(['--port', '/dev/test-uart', 'load', str(image)])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn('--skip-uart-mmio', errors.getvalue())
            connect.assert_not_called()

    def test_full_image_omits_only_uart_addresses_and_runs_after_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            data = bytes(range(256)) * 256
            image = Path(directory) / 'image.bin'
            image.write_bytes(data)
            client = Client()
            output, errors = self.invoke(client, 'load', str(image), '--skip-uart-mmio', '--run')
            self.assertEqual(client.memory[:0xfffe], data[:0xfffe])
            self.assertEqual(client.memory[0xfffe:], b'\x5a\x5a')
            self.assertEqual(client.reads, list(range(0xfffe)))
            self.assertEqual(client.calls, ['reset_halt', ('write_bytes', 0, data[:-2]), 'read_pc', 'run'])
            self.assertIn('65534 bytes', output)
            self.assertIn('0xFFFF', errors)
            self.assertIn('0xff', errors)
            self.assertIn('not written or verified', errors)

    def test_short_images_and_maximum_without_skip_stay_halted(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            for size in (1, 5, 65534):
                with self.subTest(size=size):
                    data = bytes([0x21]) * size
                    image.write_bytes(data)
                    client = Client()
                    output, errors = self.invoke(client, 'load', str(image))
                    self.assertTrue(client.halted)
                    self.assertNotIn('run', client.calls)
                    self.assertEqual(client.memory[:size], data)
                    self.assertEqual(client.memory[size:], bytes([0x5a]) * (65536 - size))
                    self.assertEqual(client.reads, list(range(size)))
                    self.assertFalse(errors)

    def test_partial_mmio_image_skips_only_fffe(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            image.write_bytes(bytes(65535))
            client = Client()
            output, errors = self.invoke(client, 'load', str(image), '--skip-uart-mmio')
            self.assertIn('0xFFFE', errors)
            self.assertNotIn('0xFFFF', errors)
            self.assertEqual(client.memory[0xfffe:], b'\x5a\x5a')
            self.assertEqual(len(client.reads), 65534)
            with patch.object(host.DebugUART, 'connect') as connect, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    host.main(['--port', '/dev/test-uart', 'load', str(image)])
                connect.assert_not_called()

    def test_console_help_lists_keys_and_commands_without_connecting(self):
        output = io.StringIO()
        with patch.object(host.DebugUART, 'connect') as connect, redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                host.main(['console', '--help'])
        self.assertEqual(raised.exception.code, 0)
        connect.assert_not_called()
        for text in ('Ctrl+J', 'Ctrl+D', 'Ctrl+V', 'uart-status', 'reset-halt', 'load', '--skip-uart-mmio'):
            self.assertIn(text, output.getvalue())

    def test_invalid_sizes_rejected_even_with_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            for size in (0, 65537):
                for extra in ([], ['--skip-uart-mmio']):
                    with self.subTest(size=size, extra=extra):
                        image.write_bytes(bytes(size))
                        with patch.object(host.DebugUART, 'connect') as connect, redirect_stderr(io.StringIO()):
                            with self.assertRaises(SystemExit):
                                host.main(['--port', '/dev/test-uart', 'load', str(image), *extra])
                        connect.assert_not_called()

    def test_failed_verification_does_not_run_and_closes_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            image.write_bytes(b'abc')
            client = Client()
            client.corrupt_address = 1
            with self.assertRaisesRegex(RuntimeError, 'Verify failed at 0x0001'):
                self.invoke(client, 'load', str(image), '--run')
            self.assertNotIn('run', client.calls)
            self.assertTrue(client.halted)
            client.transport.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
