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
        # Fail the test if a write could reach the system MMIO address.
        if address is None or address + len(values) > 0xfff0:
            raise AssertionError('write touched system MMIO')
        self.calls.append(('write_bytes', address, values))
        self.memory[address:address + len(values)] = values

    def write_words(self, values, address=None):
        values = tuple(values)
        data = b''.join(value.to_bytes(2, 'little') for value in values)
        if address is None or address + len(data) > 0xfff0:
            raise AssertionError('word write touched system MMIO')
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
        if address >= 0xfff0:
            raise AssertionError('skipped image byte was verified')
        self.reads.append(address)
        return self.memory[address] ^ int(address == self.corrupt_address)


class HostChecks(unittest.TestCase):
    def test_memory_read_default_and_hex_ascii_rows(self):
        client = Client(halted=False)
        output, errors = self.invoke(client, 'read', '010')
        self.assertEqual(output, f'000a: {"5a":47}  |Z|\n')
        self.assertEqual(client.reads, [10])
        self.assertEqual(client.calls, [('set_address', 10)])
        self.assertFalse(errors)

        client = Client()
        client.memory[0x123:0x135] = b'A\x00\x1f ~\x7f\x80\xffBCDEFGHIJK'
        output, errors = self.invoke(client, 'read', '0x123', '0x12')
        self.assertEqual(output.splitlines(), [
            '0123: 41 00 1f 20 7e 7f 80 ff 42 43 44 45 46 47 48 49  |A.. ~...BCDEFGHI|',
            f'0133: {"4a 4b":47}  |JK|',
        ])
        self.assertEqual(client.reads, list(range(0x123, 0x135)))
        self.assertFalse(errors)

    def test_memory_write_mixed_numbers(self):
        client = Client(halted=False)
        output, errors = self.invoke(client, 'write', '0X2000', '65', '0x42', '0255', '0')
        self.assertEqual(client.calls, [('write_bytes', 0x2000, b'AB\xff\x00')])
        self.assertEqual(client.memory[0x2000:0x2004], b'AB\xff\x00')
        self.assertIn('Wrote 4 bytes at 0x2000', output)
        self.assertFalse(errors)

    def test_invalid_memory_commands_do_not_access_device(self):
        parser = host.ConsoleParser()
        host.add_commands(parser)
        cases = [
            ['read'], ['read', '0', '1', '2'], ['write', '0'],
            ['read', '0b10'], ['read', 'ff'], ['write', '0', '0xGG'],
            ['read', '-1'], ['read', '65536'], ['read', '0', '0'],
            ['read', '0', '-1'], ['read', '0xffff', '2'],
            ['write', '65536', '1'], ['write', '-1', '1'],
            ['write', '0xffff', '1', '2'],
            ['write', '0', '1', '256'], ['write', '0', '1', '-1'],
        ]
        for tokens in cases:
            with self.subTest(tokens=tokens):
                client = Mock()
                with self.assertRaises(ValueError):
                    host.dispatch(client, parser.parse_args(tokens))
                self.assertEqual(client.mock_calls, [])

    def test_memory_access_last_address_including_mmio(self):
        parser = host.ConsoleParser()
        host.add_commands(parser)
        client = Mock()
        client.read8.return_value = 0xff
        output = []
        host.dispatch(client, parser.parse_args(['read', '0xffff']), report=output.append)
        client.set_address.assert_called_once_with(0xffff)
        client.read8.assert_called_once_with()
        self.assertEqual(output, [f'ffff: {"ff":47}  |.|'])
        host.dispatch(client, parser.parse_args(['write', '0xffff', '255']), report=output.append)
        client.write_bytes.assert_called_once_with([255], address=0xffff)
        client.halt.assert_not_called()
        client.reset_halt.assert_not_called()

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
            self.assertIn('--skip-mmio', errors.getvalue())
            connect.assert_not_called()

    def test_full_image_omits_only_mmio_addresses_and_runs_after_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            data = bytes(range(256)) * 256
            image = Path(directory) / 'image.bin'
            image.write_bytes(data)
            client = Client()
            output, errors = self.invoke(client, 'load', str(image), '--skip-mmio', '--verify', '--run')
            self.assertEqual(client.memory[:0xfff0], data[:0xfff0])
            self.assertEqual(client.memory[0xfff0:], bytes([0x5a]) * 16)
            self.assertEqual(client.reads, list(range(0xfff0)))
            words = tuple(int.from_bytes(data[i:i+2], 'little') for i in range(0, 0xfff0, 2))
            self.assertEqual(client.calls, ['reset_halt', ('write_words', 0, words), ('set_address', 0), 'read_pc', 'run'])
            self.assertEqual(client.word_reads, list(range(0, 0xfff0, 2)))
            self.assertIn('65520 bytes', output)
            self.assertIn('Writing: 0/65520 bytes (0%)', output)
            self.assertIn('Writing: 65520/65520 bytes (100%)', output)
            self.assertIn('Verifying: 0/65520 bytes (0%)', output)
            self.assertIn('Verifying: 65520/65520 bytes (100%)', output)
            self.assertLess(output.index('Writing: 65520/65520'), output.index('Verifying: 0/65520'))
            self.assertLess(output.index('Verifying: 65520/65520'), output.index('CPU running'))
            self.assertIn('0xFFFF', errors)
            self.assertIn('0xff', errors)
            self.assertIn('not written or verified', errors)

    def test_short_images_and_maximum_without_skip_stay_halted(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            for size in (1, 5, 65520):
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

    def test_skip_mmio_option_at_first_timer_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            image.write_bytes(bytes(65521))
            client = Client()
            output, errors = self.invoke(client, 'load', str(image), '--skip-mmio', '--verify')
            self.assertEqual(client.memory[:0xfff0], bytes(65520))
            self.assertEqual(client.memory[0xfff0:], bytes([0x5a]) * 16)
            self.assertIn('0xFFF0', errors)
            self.assertNotIn('0xFFF1', errors)
            self.assertIn('65520 bytes', output)

    def test_partial_mmio_image_skips_timer_led_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            image.write_bytes(bytes(65535))
            client = Client()
            output, errors = self.invoke(client, 'load', str(image), '--skip-mmio')
            self.assertIn('0xFFF0', errors)
            self.assertIn('0xFFFD', errors)
            self.assertIn('0xFFFE', errors)
            self.assertNotIn('0xFFFF', errors)
            self.assertEqual(client.memory[0xfff0:], bytes([0x5a]) * 16)
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
        for text in ('Ctrl+B', 'Ctrl+D', 'Ctrl+V', 'uart-status', 'reset-halt', 'load', '--skip-mmio', '--verify',
                     'read <addr> [len]', 'write <addr> <bytes...>', '0x prefix'):
            self.assertIn(text, output.getvalue())

    def test_invalid_sizes_rejected_even_with_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image.bin'
            for size in (0, 65537):
                for extra in ([], ['--skip-mmio']):
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
