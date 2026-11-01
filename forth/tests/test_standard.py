"""Forth-defined memory, defining-word and cooperative delay behavior."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'src', ROOT / 'tests', ROOT / 'forth/tests'):
    sys.path.insert(0, str(path))

from dual_support import DualRunner, DualSession
from forth.tests.model import lookup


def invoke(r, name, values=()):
    word = next(w for w in r.image.words if w['name'] == name)
    r.set('depth', len(values))
    r.invoke(word['xt'], values)


class StandardChecks(unittest.TestCase):
    def test_fill_byte_counts_zero_and_caller_stack(self):
        for count, byte in ((0, 0xABCD), (1, 0), (17, 255), (128, 0xABCD)):
            with self.subTest(count=count, byte=byte):
                r = DualRunner()
                r.memory.data[0x8000:0x8102] = b'Z' * 258
                invoke(r, 'FILL', [1234, 0x8001, count, byte])
                self.assertEqual(r.memory.data[0x8000:0x8102],
                                 b'Z' + bytes([byte & 255]) * count + b'Z' * (257-count))
                self.assertEqual(r.get('depth'), 1)
                self.assertEqual(r.cpu._ds[r.cpu._dsp], 1234)
                self.assertTrue(r.cpu._int_enable)

    def test_move_matches_snapshot_copy_for_both_overlap_directions(self):
        cases = [(0x8000, *args) for args in ((0, 1, 63), (1, 0, 63), (7, 7, 33),
                                             (0, 128, 64), (128, 0, 64), (5, 9, 0), (1, 3, 1))]
        cases += [(0x7FC0, 63, 64, 64), (0x7FC0, 64, 63, 64)]
        for base, source, target, count in cases:
            with self.subTest(base=base, source=source, target=target, count=count):
                r = DualRunner()
                original = bytes(range(256))
                r.memory.data[base:base+256] = original
                expected = bytearray(original)
                expected[target:target+count] = original[source:source+count]
                invoke(r, 'MOVE', [5678, base+source, base+target, count])
                self.assertEqual(r.memory.data[base:base+256], expected)
                self.assertEqual(r.get('depth'), 1)
                self.assertEqual(r.cpu._ds[r.cpu._dsp], 5678)

    def test_zero_length_does_not_access_invalid_source_or_destination(self):
        for name, args in (('MOVE', [65535, 65535, 0]), ('FILL', [65535, 0, 17])):
            r = DualRunner()
            accesses = []
            read, write = r.memory.read8, r.memory.write8

            def read8(address):
                if address == 65535:
                    accesses.append(('read', address))
                return read(address)

            def write8(address, value):
                if address == 65535:
                    accesses.append(('write', address))
                write(address, value)

            r.memory.read8, r.memory.write8 = read8, write8
            invoke(r, name, args)
            self.assertEqual(accesses, [])

    def test_irq_during_move_preserves_copy_and_input(self):
        r = DualRunner()
        r.memory.data[0x8000:0x8040] = bytes(range(64))
        original = r.memory.read8
        sent = False

        def read(address):
            nonlocal sent
            if address == 0x8001 and not sent:
                sent = True
                r.memory.receive_ps2(0x1C)
            return original(address)

        r.memory.read8 = read
        invoke(r, 'MOVE', [0x8000, 0x8001, 63])
        self.assertTrue(sent)
        self.assertEqual(r.memory.data[0x8001:0x8040], bytes(range(63)))
        self.assertEqual(r.memory.read16(0xF182), 1)
        self.assertTrue(r.cpu._int_enable)

    def test_marker_restores_exact_unaligned_here_and_preserves_older_data(self):
        r = DualSession()
        r.uart('17 CREATE keep 3 ALLOT 65 keep C!\n')
        r.quiet()
        here, latest = r.get('here'), r.get('latest')
        self.assertEqual(here & 1, 1)
        r.uart('MARKER clean VARIABLE gone 99 gone ! 31 ALLOT 66 keep C!\n')
        r.quiet()
        self.assertGreater(r.get('here'), here)
        r.uart('clean\n')
        r.quiet()
        self.assertEqual((r.get('here'), r.get('latest')), (here, latest))
        self.assertEqual(r.stack(), [17])
        for name in ('clean', 'gone'):
            with self.assertRaisesRegex(AssertionError, 'missing dictionary entry'):
                lookup(r.memory, name)
        r.uart('keep C@\n')
        r.quiet()
        self.assertEqual(r.stack(), [17, 66])
        self.assertNotIn(b'error:', bytes(r.memory.tx))

    def test_nested_markers_and_subsequent_compilation(self):
        r = DualSession()
        before = r.get('here'), r.get('latest')
        for line in ('MARKER outer : one 1 ;\n', 'MARKER inner : two 2 ; inner\n',
                     'one\n', 'outer : fresh 3 ; fresh\n'):
            r.uart(line)
            r.quiet()
        self.assertEqual(r.stack(), [1, 3])
        self.assertEqual(r.memory.read16(lookup(r.memory, 'fresh')[0]), before[1])
        self.assertEqual(lookup(r.memory, 'fresh')[0], before[0])
        self.assertNotIn(b'error:', bytes(r.memory.tx))

    def test_marker_cancels_callback_before_reclaiming_its_code(self):
        r = DualSession()
        r.uart('MARKER clean : tick 1 62464 +! ; 100 \' tick TIMER-EVERY\n')
        r.quiet()
        self.assertNotEqual(r.get('timer_callback'), 0)
        r.memory.event(1)
        r.uart('clean\n')
        r.quiet()
        self.assertEqual((r.get('timer_callback'), r.get('timer_event')), (0, 0))
        self.assertEqual(r.memory.timer[4], 3)
        self.assertEqual((r.memory.uart_ie, r.memory.ps2_ie), (4, 4))

    def test_marker_rejects_open_definitions_and_kernel_words_stay_protected(self):
        for command in ('MARKER clean\n: bad [ clean ] ;\n',
                        ': bad MARKER nested ;\n', 'FORGET MARKER\n'):
            r = DualSession()
            r.uart(command)
            r.quiet()
            self.assertIn(b'error:', bytes(r.memory.tx))
            self.assertEqual(r.get('definition_open'), 0)
            self.assertEqual(r.stack(), [])
            for name in ('MARKER', 'MS', 'MOVE', 'FILL'):
                lookup(r.memory, name)

    def test_marker_creation_failure_rolls_back_dictionary_transaction(self):
        for command, here in (('MARKER\n', None), ('MARKER exceeds\n', 0xEFF0)):
            r = DualSession()
            if here is not None:
                r.set('here', here)
            before = r.get('here'), r.get('latest')
            r.uart(command)
            r.quiet()
            self.assertIn(b'error:', bytes(r.memory.tx))
            self.assertEqual((r.get('here'), r.get('latest')), before)
            self.assertEqual((r.get('definition_open'), r.get('state')), (0, 0))
            self.assertEqual(r.stack(), [])

    def test_ms_sampled_waits_wrap_short_period_and_unsigned_durations(self):
        for ticks, compare, samples in ((0, 0, []), (1, 65535, [10, 10, 11]),
                                        (10, 65535, [65530, 65534, 2, 4]),
                                        (15, 99, [90, 95, 2, 5]),
                                        (6, 1, [0, 1, 0, 1, 0, 1, 0]),
                                        (65535, 65535, [0, 30000, 60000, 1000])):
            with self.subTest(ticks=ticks, compare=compare):
                r = DualRunner()
                r.memory.timer[4] = 3 if ticks else 0
                r.memory.write16(0xFFF2, compare)
                values, reads = iter(samples), []
                original = r.memory.read16

                def read16(address):
                    if address == 0xFFF0:
                        value = next(values)
                        reads.append(value)
                        return value
                    return original(address)

                r.memory.read16 = read16
                invoke(r, 'MS', [1234, ticks])
                self.assertEqual(reads, samples)
                self.assertEqual(r.get('depth'), 1)
                self.assertEqual(r.cpu._ds[r.cpu._dsp], 1234)
                self.assertEqual(r.memory.timer[4], 3 if ticks else 0)

    def test_ms_dispatches_callback_with_irqs_enabled(self):
        r = DualSession()
        r.uart(': tick 1 62464 +! 0 MS ; 100 \' tick TIMER-EVERY\n')
        r.quiet()
        original = r.memory.read16
        samples = iter([90, 95, 2, 5])
        first = True

        def read16(address):
            nonlocal first
            if address == 0xFFF0:
                if first:
                    first = False
                    r.memory.event(1)
                return next(samples)
            return original(address)

        r.memory.read16 = read16
        invoke(r, 'MS', [15])
        self.assertEqual(r.memory.read16(0xF400), 1)
        self.assertEqual(r.memory.timer[4], 7)
        self.assertTrue(r.cpu._int_enable)

    def test_ms_invalid_timer_modes_abort_instead_of_spinning(self):
        for mode, compare in ((0, 0), (1, 100), (2, 100), (3, 0)):
            r = DualSession()
            r.memory.timer[4] = mode
            r.memory.write16(0xFFF2, compare)
            r.uart('1 MS\n')
            r.quiet()
            self.assertEqual(r.stack(), [])
            self.assertEqual(r.get('timer_callback'), 0)
            r.uart('123\n')
            r.quiet()
            self.assertEqual(r.stack(), [123])


if __name__ == '__main__':
    if '--rtl' in sys.argv:
        sys.argv.remove('--rtl')  # Integrated RTL coverage lives in dual_system.
    unittest.main()
