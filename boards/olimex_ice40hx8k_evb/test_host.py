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
        self.word_reads = []
        self.pointer = 0
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
        # Fail the test if a write could reach the LED/UART MMIO address.
        if address is None or address + len(values) > 0xfffd:
            raise AssertionError('write touched LED/UART MMIO')
        self.calls.append(('write_bytes', address, values))
        self.memory[address:address + len(values)] = values

    def write_words(self, values, address=None):
        values = tuple(values)
        data = b''.join(value.to_bytes(2, 'little') for value in values)
        if address is None or address + len(data) > 0xfffd:
            raise AssertionError('word write touched LED/UART MMIO')
        self.calls.append(('write_words', address, values))
        self.memory[address:address + len(data)] = data

    def write_words_stream(self, values, address=None, *, write_delay=0, on_progress=None):
        self.stream_delay = write_delay
        values = tuple(values)
        self.write_words(values, address)
        for done in range(1, len(values) + 1):
            if on_progress:
                on_progress(done)

    def set_address(self, address):
        self.calls.append(('set_address', address))
        self.pointer = address

    def read16(self):
        self.word_reads.append(self.pointer)
        return self.read8() | (self.read8() << 8)

    def read8(self, address=None):
        if address is None:
            address = self.pointer
        self.pointer = address + 1
        if address >= 0xfffd:
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

    def test_full_image_omits_only_mmio_addresses_and_runs_after_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            data = bytes(range(256)) * 256
            image = Path(directory) / 'image.bin'
            image.write_bytes(data)
            client = Client()
            output, errors = self.invoke(client, 'load', str(image), '--skip-uart-mmio', '--verify', '--run')
            self.assertEqual(client.memory[:0xfffd], data[:0xfffd])
            self.assertEqual(client.memory[0xfffd:], b'\x5a\x5a\x5a')
            self.assertEqual(client.reads, list(range(0xfffd)))
            words = tuple(int.from_bytes(data[i:i+2], 'little') for i in range(0, 0xfffc, 2))
            self.assertEqual(client.calls, ['reset_halt', ('write_words', 0, words), ('write_bytes', 0xfffc, data[0xfffc:0xfffd]), ('set_address', 0), 'read_pc', 'run'])
            self.assertEqual(client.word_reads, list(range(0, 0xfffc, 2)))
            self.assertIn('65533 bytes', output)
            self.assertIn('Writing: 0/65533 bytes (0%)', output)
            self.assertIn('Writing: 65533/65533 bytes (100%)', output)
            self.assertIn('Verifying: 0/65533 bytes (0%)', output)
            self.assertIn('Verifying: 65533/65533 bytes (100%)', output)
            self.assertLess(output.index('Writing: 65533/65533'), output.index('Verifying: 0/65533'))
            self.assertLess(output.index('Verifying: 65533/65533'), output.index('CPU running'))
            self.assertIn('0xFFFF', errors)
            self.assertIn('0xff', errors)
            self.assertIn('not written or verified', errors)

    def test_short_images_and_maximum_without_skip_stay_halted(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            for size in (1, 5, 65533):
                with self.subTest(size=size):
                    data = bytes([0x21]) * size
                    image.write_bytes(data)
                    client = Client()
                    output, errors = self.invoke(client, 'load', str(image))
                    self.assertTrue(client.halted)
                    self.assertNotIn('run', client.calls)
                    self.assertEqual(client.memory[:size], data)
                    self.assertEqual(client.memory[size:], bytes([0x5a]) * (65536 - size))
                    self.assertEqual(client.reads, [])
                    self.assertNotIn('Verifying:', output)
                    self.assertNotIn('Loaded and verified', output)
                    self.assertFalse(errors)

    def test_partial_mmio_image_skips_led_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            image.write_bytes(bytes(65535))
            client = Client()
            output, errors = self.invoke(client, 'load', str(image), '--skip-uart-mmio')
            self.assertIn('0xFFFD', errors)
            self.assertIn('0xFFFE', errors)
            self.assertNotIn('0xFFFF', errors)
            self.assertEqual(client.memory[0xfffd:], b'\x5a\x5a\x5a')
            self.assertEqual(client.reads, [])
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
        for text in ('Ctrl+B', 'Ctrl+D', 'Ctrl+V', 'uart-status', 'reset-halt', 'load', '--skip-uart-mmio', '--verify'):
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
                self.invoke(client, 'load', str(image), '--verify', '--run')
            self.assertNotIn('run', client.calls)
            self.assertTrue(client.halted)
            client.transport.close.assert_called_once()

    def test_word_order_odd_tail_and_optional_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'odd.bin'
            image.write_bytes(b'\x12\x34\xab\xcd\xef')
            for verify in (False, True):
                with self.subTest(verify=verify):
                    client = Client()
                    self.invoke(client, 'load', str(image), '--run', *(['--verify'] if verify else []))
                    self.assertEqual(client.calls[:3], ['reset_halt',
                        ('write_words', 0, (0x3412, 0xcdab)), ('write_bytes', 4, b'\xef')])
                    self.assertEqual(client.memory[:6], b'\x12\x34\xab\xcd\xef\x5a')
                    self.assertEqual(client.word_reads, [0, 2] if verify else [])
                    self.assertEqual(client.reads, list(range(5)) if verify else [])
                    self.assertEqual(client.calls[-1], 'run')

    def test_verification_detects_each_lane_and_odd_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'odd.bin'
            image.write_bytes(b'abc')
            for address in range(3):
                with self.subTest(address=address):
                    client = Client()
                    client.corrupt_address = address
                    with self.assertRaisesRegex(RuntimeError, f'Verify failed at 0x{address:04x}'):
                        self.invoke(client, 'load', str(image), '--verify', '--run')
                    self.assertNotIn('run', client.calls)

    def test_single_byte_verification_does_not_read_neighbor(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'one.bin'
            image.write_bytes(b'\xab')
            client = Client()
            self.invoke(client, 'load', str(image), '--verify')
            self.assertEqual(client.calls[:2], ['reset_halt', ('write_bytes', 0, b'\xab')])
            self.assertEqual(client.word_reads, [])
            self.assertEqual(client.reads, [0])
            self.assertEqual(client.memory[1], 0x5a)

    def test_progress_has_no_newlines_and_clears_on_error(self):
        parser = host.ConsoleParser()
        host.add_commands(parser)
        args = parser.parse_args(['load', 'unused.bin', '--verify'])
        for corrupt in (None, 0):
            with self.subTest(corrupt=corrupt):
                client = Client()
                client.corrupt_address = corrupt
                messages, progress = [], []
                if corrupt is None:
                    host.dispatch(client, args, image=b'ab', report=messages.append, progress_report=progress.append)
                    self.assertTrue(messages[-1].startswith('Loaded and verified'))
                else:
                    with self.assertRaises(RuntimeError):
                        host.dispatch(client, args, image=b'ab', report=messages.append, progress_report=progress.append)
                self.assertEqual(progress[0], 'Writing: 0/2 bytes (0%)')
                self.assertEqual(progress[-1], '')
                self.assertTrue(all('\n' not in line and '\r' not in line for line in progress))

    def test_stream_failure_reports_error_without_reset_retry_or_run(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            image.write_bytes(b'abcd')
            client = Client()
            client.write_words_stream = Mock(side_effect=RuntimeError('missing word OK'))
            with self.assertRaisesRegex(RuntimeError, 'missing word OK'):
                self.invoke(client, 'load', str(image), '--run')
            self.assertEqual(client.calls, ['reset_halt'])
            client.write_words_stream.assert_called_once()
            client.transport.close.assert_called_once()

    def test_write_delay_cli_validation_and_forwarding(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            image.write_bytes(b'ab')
            client = Client()
            self.invoke(client, 'load', str(image), '--write-delay', '0.001')
            self.assertEqual(client.stream_delay, 0.001)
            for value in ('-1', 'nan', 'inf'):
                with patch.object(host.DebugUART, 'connect') as connect, redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        host.main(['--port', 'unused', 'load', str(image), '--write-delay', value])
                    connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
