import unittest
from prim_debug_uart import DebugUART, DebugTimeout, encode_number


def wire(s):
    return bytes(ord(c) | 128 for c in s)


class Transport:
    timeout = None

    def __init__(self, replies):
        self.replies = bytearray(replies)
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def read(self, size):
        data = self.replies[:size]
        del self.replies[:size]
        return data


class DebugUARTChecks(unittest.TestCase):
    def test_connect_requests_low_latency_before_starting_client(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        for mode in ('supported', 'unsupported', 'denied', 'absent'):
            with self.subTest(mode=mode):
                transport = Transport(b'')
                transport.close = Mock()
                if mode != 'absent':
                    transport.set_low_latency_mode = Mock(side_effect={
                        'unsupported': ValueError('not supported'),
                        'denied': OSError('permission denied'),
                    }.get(mode))
                class Client(DebugUART):
                    def __init__(self, transport, **kwargs):
                        if mode != 'absent':
                            transport.set_low_latency_mode.assert_called_once_with(True)
                        super().__init__(transport, **kwargs)

                serial = SimpleNamespace(Serial=Mock(return_value=transport))
                with patch.dict('sys.modules', {'serial': serial}):
                    client = Client.connect('/dev/test', timeout=1)
                self.assertEqual(client.low_latency, mode == 'supported')
                self.assertEqual(client.low_latency_error is None, mode == 'supported')
                self.assertIs(client.transport, transport)
                transport.close.assert_not_called()
                serial.Serial.assert_called_once_with('/dev/test', baudrate=115200,
                    bytesize=8, parity='N', stopbits=1, timeout=0.1, write_timeout=1)

    def test_numbers(self):
        self.assertEqual(encode_number(0xba21, 4), '12ab')
        for value in (-1, 65536):
            with self.assertRaises(ValueError):
                encode_number(value, 4)

    def test_channel_and_async_break(self):
        t = Transport(b'Hi' + wire('BT3B12ab'))
        events = []
        client = DebugUART(t, on_break=lambda: events.append('break'))
        self.assertTrue(client.status().break_reason)
        self.assertEqual(client.read16(0x100), 0xba21)
        self.assertEqual(client.output, b'Hi')
        self.assertEqual(len(events), 2)
        self.assertEqual(b''.join(t.writes), wire('?A0010R'))

    def test_persistent_writes_wait_for_each_ok(self):
        class CheckedTransport(Transport):
            def write(self, data):
                if len(data) in (2, 4):
                    assert not self.replies, 'next value arrived before OK consumed'
                self.writes.append(data)
                if len(data) in (2, 4) and data != wire('w'):
                    self.replies.extend(wire('BK'))
                return len(data)
        t = CheckedTransport(b'')
        DebugUART(t).write_bytes([0x21, 0x43, 0xba], 0xffff)
        self.assertEqual(t.writes, list(map(wire, ['Affff', 'w', '12', '34', 'ab'])))
        DebugUART(t).write_words([0x4321, 0xdcba])
        self.assertEqual(t.writes[-3:], list(map(wire, ['W', '1234', 'abcd'])))

    def test_read_words_sends_next_request_after_third_digit(self):
        class ReadTransport(Transport):
            requests = 0

            def write(self, data):
                super().write(data)
                if data == wire('Aefff'):
                    return len(data)
                assert data == wire('R'), 'only single requests allowed'
                if self.requests:
                    # Exactly the preceding fourth digit is still unread.
                    assert self.replies == wire('b'), 'next R must follow digit three'
                self.requests += 1
                self.replies.extend(b'Hi' + wire('B12ab'))
                return len(data)

        transport = ReadTransport(b'')
        client = DebugUART(transport)
        progress = []
        self.assertEqual(client.read_words(3, 0xfffe, on_progress=progress.append), [0xba21] * 3)
        self.assertEqual(transport.writes, list(map(wire, ['Aefff', 'R', 'R', 'R'])))
        self.assertEqual(progress, [1, 2, 3])
        self.assertEqual(client.output, b'HiHiHi')
        self.assertEqual(client.break_events, 3)
        self.assertFalse(transport.replies, 'last word must be fully drained')

    def test_single_word_and_byte_reads_have_no_prefix(self):
        transport = Transport(wire('12ab34T1'))
        client = DebugUART(transport)
        self.assertEqual(client.read16(0x100), 0xba21)
        self.assertEqual(client.read8(), 0x43)
        self.assertTrue(client.status().halted)
        self.assertEqual(transport.writes, list(map(wire, ['A0010', 'R', 'r', '?'])))

    def test_read_words_single_request_is_fully_drained(self):
        transport = Transport(wire('1234T1'))
        client = DebugUART(transport)
        self.assertEqual(client.read_words(1), [0x4321])
        self.assertTrue(client.status().halted)
        self.assertEqual(transport.writes, list(map(wire, ['R', '?'])))

    def test_read_words_empty_and_invalid_count_do_not_send(self):
        transport = Transport(b'')
        client = DebugUART(transport)
        self.assertEqual(client.read_words(0), [])
        for count in (-1, 1.5):
            with self.assertRaises(ValueError):
                client.read_words(count)
        self.assertEqual(transport.writes, [])

    def test_read_words_missing_or_invalid_reply_does_not_retry(self):
        for replies, error, requests in [('12', DebugTimeout, 1), ('12z', RuntimeError, 1),
                                          ('123', DebugTimeout, 2), ('123z', RuntimeError, 2),
                                          ('1234abc', DebugTimeout, 2)]:
            with self.subTest(replies=replies):
                transport = Transport(wire(replies))
                with self.assertRaises(error):
                    DebugUART(transport, timeout=0.01).read_words(2)
                self.assertEqual(transport.writes, [wire('R')] * requests)

    def test_controls_and_word_writes(self):
        t = Transport(wire('KKKKK0010KK'))
        c = DebugUART(t)
        c.halt(); c.run(); c.step(); c.reset_halt()
        self.assertEqual(c.read_pc(), 0x100)
        c.write_words([0x4321, 0xdcba])
        self.assertEqual(b''.join(t.writes), wire('HGSZPW1234abcd'))

    def test_timeout_and_unexpected_response(self):
        with self.assertRaisesRegex(DebugTimeout, 'FPGA'):
            DebugUART(Transport(b''), timeout=0.001).halt()
        with self.assertRaisesRegex(RuntimeError, 'Expected'):
            DebugUART(Transport(wire('T'))).halt()

    def test_stream_sends_all_words_without_waiting_and_counts_oks(self):
        class StreamTransport(Transport):
            def write(self, data):
                super().write(data)
                if data == wire('1234abcd'):
                    self.replies.extend(b'Hi' + wire('BKKB'))
                return len(data)
        transport = StreamTransport(b'')
        client = DebugUART(transport, timeout=0.1)
        progress = []
        client.write_words_stream([0x4321, 0xdcba], 0, on_progress=progress.append)
        self.assertEqual(transport.writes, list(map(wire, ['A0000', 'W', '1234abcd'])))
        self.assertEqual(progress, [1, 2])
        self.assertEqual(client.output, b'Hi')
        self.assertEqual(client.break_events, 1)

    def test_stream_missing_or_invalid_ok_fails_without_retry(self):
        for replies in ('K', 'KT'):
            with self.subTest(replies=replies):
                transport = Transport(wire(replies))
                client = DebugUART(transport, timeout=0.02)
                with self.assertRaisesRegex(RuntimeError, '1/2 word OKs'):
                    client.write_words_stream([1, 2], 0)
                self.assertEqual(transport.writes.count(wire('A0000')), 1)
                self.assertEqual(transport.writes.count(wire('W')), 1)

    def test_stream_delay_flushes_each_word(self):
        from unittest.mock import Mock
        transport = Transport(wire('KK'))
        transport.flush = Mock()
        DebugUART(transport).write_words_stream([0x4321, 0xdcba], write_delay=0.001)
        self.assertEqual(transport.writes, list(map(wire, ['W', '1234', 'abcd'])))
        self.assertEqual(transport.flush.call_count, 2)

    def test_stream_rejects_invalid_delay_before_sending(self):
        for delay in (-1, float('nan'), float('inf')):
            transport = Transport(b'')
            with self.assertRaises(ValueError):
                DebugUART(transport).write_words_stream([0], write_delay=delay)
            self.assertEqual(transport.writes, [])


if __name__ == '__main__':
    unittest.main()
