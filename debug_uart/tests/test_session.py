"""Concurrent reader, RX-credit scheduling, terminal keys and PTY restoration."""
import io
import os
import pty
import queue
import termios
import threading
import time
import unittest
from unittest.mock import Mock

from prim_debug_uart import DebugTimeout
from prim_debug_uart.session import UARTSession
from prim_debug_uart.console import Console, HELP


def wire(text):
    return bytes(ord(c) | 128 for c in text)


def until(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError('Timed out waiting for concurrent test condition')
        threading.Event().wait(0.002)


class Transport:
    timeout = 0.005

    def __init__(self):
        self.incoming = queue.Queue()
        self.cpu = []
        self.commands = []
        self.rx_full = True
        self.closed = 0
        self.error = None
        self.hold = False
        self.writing = False

    def emit(self, data):
        for byte in data:
            self.incoming.put(byte)

    def read(self, size):
        if self.error:
            raise self.error
        try:
            return bytes([self.incoming.get(timeout=0.005)])
        except queue.Empty:
            return b''

    def write(self, data):
        if not data[0] & 128:
            if self.rx_full:
                raise AssertionError('CPU RX register overwritten')
            self.cpu.extend(data)
            self.rx_full = True
        else:
            text = ''.join(chr(b & 127) for b in data)
            self.commands.append(text)
            if text == 'q':
                self.writing = False
                self.emit(wire('K3' if self.rx_full else 'K2'))
            elif text == '?':
                self.emit(wire('T1'))
            elif text == 'P':
                self.emit(wire('K1234'))
            elif text in 'HGSZ':
                self.emit(wire('K'))
            elif text == 'w':
                self.writing = True
            elif self.writing:
                if not self.hold:
                    self.emit(wire('K'))
        return len(data)

    def close(self):
        self.closed += 1


class SessionChecks(unittest.TestCase):
    def test_stream_keeps_reader_live_and_blocks_credit_polls(self):
        transport = Transport()
        with UARTSession(transport) as session:
            errors = []
            def load():
                try:
                    session.write_words_stream([0x4321, 0xdcba], 0)
                except Exception as exc:
                    errors.append(exc)
            thread = threading.Thread(target=load)
            thread.start()
            until(lambda: '1234abcd' in transport.commands)
            session.queue_cpu(b'x')
            transport.emit(b'live' + wire('B'))
            until(lambda: session.output == b'live' and session.break_events == 1)
            self.assertNotIn('q', transport.commands)
            transport.emit(wire('KK'))
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            until(lambda: 'q' in transport.commands)

    def test_stream_failure_invalidates_session_without_retry(self):
        transport = Transport()
        with UARTSession(transport, timeout=0.02) as session:
            with self.assertRaisesRegex(RuntimeError, '0/2 word OKs'):
                session.write_words_stream([1, 2], 0)
            self.assertIsNotNone(session.error)
            self.assertEqual(transport.commands.count('W'), 1)
            with self.assertRaises(OSError):
                session.status()

    def test_idle_output_break_and_debug_with_full_rx(self):
        transport = Transport()
        output, events = bytearray(), []
        with UARTSession(transport, on_output=output.extend, on_break=lambda: events.append('B')) as session:
            session.queue_cpu(b'ab')
            until(lambda: 'q' in transport.commands)
            self.assertTrue(session.status().halted)
            session.halt()
            transport.emit(b'CPU text' + wire('B'))
            until(lambda: output == b'CPU text' and events == ['B'])
            self.assertEqual(transport.cpu, [])
            transport.rx_full = False
            until(lambda: transport.cpu == [ord('a')])
            session.run()  # Still usable with the next CPU byte blocked.
            transport.rx_full = False
            until(lambda: transport.cpu == list(b'ab'))
            self.assertEqual(session.read_pc(), 0x4321)
        self.assertEqual(transport.closed, 1)

    def test_credit_polls_do_not_interrupt_persistent_write(self):
        transport = Transport()
        transport.hold = True
        with UARTSession(transport) as session:
            thread = threading.Thread(target=lambda: session.write_bytes([0x21, 0x43]))
            thread.start()
            until(lambda: '12' in transport.commands)
            session.queue_cpu(b'x')
            transport.emit(b'concurrent output')
            until(lambda: session.output == b'concurrent output')
            self.assertNotIn('q', transport.commands)
            transport.hold = False
            transport.emit(wire('K'))
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(transport.commands[:3], ['w', '12', '34'])

    def test_reader_failure_and_timeout_close_transport(self):
        transport = Transport()
        session = UARTSession(transport)
        transport.error = OSError('USB disconnected')
        until(lambda: session.error is not None)
        with self.assertRaisesRegex(OSError, 'USB disconnected'):
            session.status()
        session.close(); session.close()
        self.assertEqual(transport.closed, 1)

        transport = Transport()
        transport.write = lambda data: len(data)  # Never replies.
        with UARTSession(transport, timeout=0.02) as session:
            with self.assertRaises(DebugTimeout):
                session.status()
            with self.assertRaises(OSError):
                session.run()

    def test_keys_help_and_literal_control_bytes(self):
        ui = Console(lambda text: None, output=io.StringIO())
        ui.session = Mock()
        ui.key(13)  # Enter in CPU mode.
        ui.session.queue_cpu.assert_called_once_with(b'\r')
        ui.session.reset_mock()
        ui.key(11)  # Ctrl+K is now an ordinary CPU byte.
        ui.session.queue_cpu.assert_called_once_with(b'\x0b')
        self.assertFalse(ui.debug_mode)
        ui.session.reset_mock()
        ui.key(2)
        self.assertTrue(ui.debug_mode)
        for byte in b'help\r':
            ui.key(byte)
        self.assertIn('uart-status', ui.output.getvalue())
        self.assertIn('Ctrl+D', ui.output.getvalue())
        self.assertIn('Ctrl+B', ui.output.getvalue())
        ui.key(22); ui.key(2)
        ui.session.queue_cpu.assert_called_once_with(b'\x02')
        ui.session.reset_mock()
        ui.key(22); ui.key(4)
        ui.session.queue_cpu.assert_called_once_with(b'\x04')
        self.assertTrue(ui.running)
        ui.key(13)
        self.assertTrue(ui.debug_mode)
        ui.key(2)
        self.assertFalse(ui.debug_mode)
        ui.key(2); ui.key(4)
        self.assertFalse(ui.running)
        for command in ('halt', 'stop', 'step', 'reset-halt', 'run', 'pc', 'status', 'load', 'quit'):
            self.assertIn(command, HELP)

    def test_history_navigation_restores_draft_and_stops_at_oldest(self):
        ui = Console(lambda text: None, output=io.StringIO())
        ui.session = Mock()

        def keys(data):
            for byte in data:
                ui.key(byte)

        keys(b'\x02\x1b[A\x1b[B')  # Empty history.
        self.assertEqual(ui.line, b'')
        keys(b'help\rstatus\rread 0x2000 16\rwrite 0x2000 ')
        keys(b'\x1b[B')  # Down at the draft is a no-op.
        self.assertEqual(ui.line, b'write 0x2000 ')
        keys(b'\x1b[A')
        self.assertEqual(ui.line, b'read 0x2000 16')
        keys(b'\x1b[A')
        self.assertEqual(ui.line, b'status')
        keys(b'\x1b[A\x1b[A')
        self.assertEqual(ui.line, b'help')
        keys(b'\x1b[B\x1b[B\x1b[B\x1b[B')
        self.assertEqual(ui.line, b'write 0x2000 ')
        self.assertTrue(ui.output.getvalue().endswith('\r\x1b[2Kdebug> write 0x2000 '))
        ui.session.queue_cpu.assert_not_called()

    def test_recalled_command_can_be_edited_submitted_and_recalled_after_cpu_mode(self):
        ui = Console(lambda text: None, output=io.StringIO())
        ui.session = Mock()
        for byte in b'\x02read 32 16\r\x1bOA\x7f\x7f1\r':
            ui.key(byte)
        self.assertEqual(ui._commands.get_nowait(), 'read 32 16')
        self.assertEqual(ui._commands.get_nowait(), 'read 32 1')
        self.assertTrue(ui._commands.empty())
        for byte in b'\x02\x1b[A':  # Arrow keys pass through in CPU mode.
            ui.key(byte)
        self.assertFalse(ui.debug_mode)
        self.assertEqual(ui.session.queue_cpu.call_args_list,
                         [unittest.mock.call(bytes([byte])) for byte in b'\x1b[A'])
        for byte in b'\x02\x1bOA':
            ui.key(byte)
        self.assertEqual(ui.line, b'read 32 1')
        ui.cpu_output(b'CPU output\n')
        self.assertTrue(ui.output.getvalue().endswith('debug> read 32 1'))
        for byte in b'\x1bOB':
            ui.key(byte)
        self.assertEqual(ui.line, b'')

    def test_empty_enter_keeps_debug_prompt_responsive(self):
        for ending in (b'\r', b'\n', b'\r\n', b'   \r'):
            with self.subTest(ending=ending):
                ui = Console(lambda text: None, output=io.StringIO())
                ui.session = Mock()
                for byte in b'\x02' + ending:
                    ui.key(byte)
                self.assertTrue(ui.debug_mode)
                self.assertTrue(ui.output.getvalue().endswith('debug> '))
                self.assertEqual(ui._history, [])
                self.assertTrue(ui._commands.empty())
                ui.session.queue_cpu.assert_not_called()
                for byte in b'status\r':
                    ui.key(byte)
                self.assertEqual(ui._commands.get_nowait(), 'status')
                ui.key(2)
                self.assertFalse(ui.debug_mode)
                ui.key(13)
                ui.session.queue_cpu.assert_called_once_with(b'\r')

    def test_debug_escape_sequences_do_not_pollute_command_or_swallow_controls(self):
        ui = Console(lambda text: None, output=io.StringIO())
        ui.session = Mock()
        for byte in b'\x02status\x1b[C\x1b[D\x1b[3~\x1b[1;5A':
            ui.key(byte)
        self.assertEqual(ui.line, b'status')
        for byte in b'\x1b\r':  # An unfinished escape must not swallow Enter.
            ui.key(byte)
        self.assertEqual(ui._commands.get_nowait(), 'status')
        for byte in b'\x1b[\x16\x02':
            ui.key(byte)
        ui.session.queue_cpu.assert_called_once_with(b'\x02')
        for byte in b'\x1b[A':
            ui.key(byte)
        self.assertEqual(ui.line, b'status')
        for byte in b'\x1b[\x04':
            ui.key(byte)
        self.assertFalse(ui.running)

    def test_progress_replaces_line_and_preserves_prompt_and_cpu_output(self):
        ui = Console(lambda text: None, output=io.StringIO())
        ui.session = Mock()
        ui.key(2)
        ui.line.extend(b'status')
        ui.output.seek(0); ui.output.truncate()
        ui.progress('Writing: 0/10')
        ui.progress('Writing: 2/10')
        self.assertEqual(ui.output.getvalue(), '\r\x1b[2KWriting: 0/10\r\x1b[2KWriting: 2/10')
        ui.cpu_output(b'hello\n')
        self.assertIn('hello\r\n', ui.output.getvalue())
        self.assertTrue(ui.output.getvalue().endswith('debug> status'))
        ui.progress('Verifying: 10/10')
        ui.message('Loaded')
        self.assertTrue(ui.output.getvalue().endswith('Loaded\r\ndebug> status'))
        ui.progress('Writing: 0/10')
        ui.key(ord('!'))
        self.assertTrue(ui.output.getvalue().endswith('debug> status!'))
        ui.progress('')
        self.assertTrue(ui.output.getvalue().endswith('debug> status!'))

    def test_pty_debug_prompt_keeps_rx_live_and_restores_terminal(self):
        master, slave = pty.openpty()
        previous = termios.tcgetattr(slave)
        transport = Transport()
        ui = Console(lambda command: 'PC=' + str(session.read_pc()), output=io.StringIO())
        session = UARTSession(transport, on_output=ui.cpu_output, on_break=lambda: ui.message('[BREAK]'))
        thread = threading.Thread(target=lambda: ui.run(session, input_fd=slave))
        try:
            thread.start()
            until(lambda: 'Prim UART console' in ui.output.getvalue())
            os.write(master, b'\x02')
            until(lambda: ui.debug_mode)
            transport.emit(b'live CPU\r\n' + wire('B'))
            until(lambda: '[BREAK]' in ui.output.getvalue())
            prompts = ui.output.getvalue().count('debug> ')
            os.write(master, b'\r')
            until(lambda: ui.output.getvalue().count('debug> ') > prompts)
            self.assertTrue(ui.debug_mode)
            os.write(master, b'pc\r')
            until(lambda: 'PC=17185' in ui.output.getvalue())
            self.assertIn('live CPU', ui.output.getvalue())
            os.write(master, b'\x1b[A')
            until(lambda: ui.line == b'pc')
            os.write(master, b'\r')
            until(lambda: ui.output.getvalue().count('PC=17185') == 2)
            os.write(master, b'\x04')
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(termios.tcgetattr(slave), previous)
            self.assertEqual(transport.closed, 1)
            self.assertNotIn('H', transport.commands)  # Exit never halts/resets the CPU.
        finally:
            ui.running = False
            thread.join(timeout=2)
            session.close()
            os.close(master); os.close(slave)


if __name__ == '__main__':
    unittest.main()
