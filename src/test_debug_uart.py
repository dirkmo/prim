import unittest
from prim.debug_uart import DebugUART, DebugTimeout, encode_number


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
    def test_numbers(self):
        self.assertEqual(encode_number(0xba21, 4), '12ab')
        for value in (-1, 65536):
            with self.assertRaises(ValueError):
                encode_number(value, 4)

    def test_channel_and_async_break(self):
        t = Transport(b'Hi' + wire('BT3BK12ab'))
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


if __name__ == '__main__':
    unittest.main()
