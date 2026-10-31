"""Execute the timer Forth driver, checking bus accesses and sampled COUNT waits.

COUNT samples are supplied explicitly; this is not a timer RTL/timing model.
"""
import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / 'src', ROOT / 'tests', ROOT / 'forth/tests'):
    sys.path.insert(0, str(directory))

from forth.build import build_image
from forth.image import USER_LIMIT
from forth.kernel.boot import VARIABLES
from forth.tests.model import Runner, cell, lookup, session
from dual_support import DualSession

SOURCE = (ROOT / 'timer/forth/timer.fs').read_bytes()
DEMO = (ROOT / 'timer/forth/demo.fs').read_bytes()


class TimerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = build_image(dual_console=False)
        cls.output, cls.stack, cls.loaded, _ = session(cls.image, SOURCE)

    def runner(self, *values):
        r = Runner(self.image, values)
        start = self.image.symbols['user_start']
        end = cell(self.loaded, VARIABLES['here'])
        r.memory.data[start:end] = self.loaded.data[start:end]
        for variable in ('here', 'latest'):
            r.memory.write16(VARIABLES[variable], cell(self.loaded, VARIABLES[variable]))
        r.words.update({name: lookup(self.loaded, name)[1] for name in (
            'TIMER-INIT', 'TIMER-ONCE', 'TIMER-PERIOD', 'TIMER-START',
            'TIMER-STOP', 'TIMER-RESET', 'TIMER-COUNT@', 'TIMER-COUNT!',
            'TIMER-COMPARE@', 'TIMER-COMPARE!', 'TIMER-DONE?', 'TIMER-WAIT')})
        r.memory.writes.clear()
        return r

    def timer_writes(self, r):
        return [(a, v) for a, v in r.memory.writes if 0xFFF0 <= a <= 0xFFF5]

    def test_load_has_no_peripheral_side_effects(self):
        self.assertNotIn(b'error:', self.output)
        self.assertEqual(self.stack, [])
        self.assertEqual(cell(self.loaded, VARIABLES['base']), 10)
        self.assertFalse([(a, v) for a, v in self.loaded.writes if 0xFFF0 <= a <= 0xFFF5])
        for source in (SOURCE, DEMO):
            source.decode('ascii')
            self.assertTrue(all(len(line) <= 127 for line in source.splitlines()))

    def test_dual_console_load_and_demo(self):
        r = DualSession()
        for line in (SOURCE + DEMO).splitlines(keepends=True):
            r.uart(line)
            r.quiet()
        self.assertNotIn(b'error:', bytes(r.memory.tx))
        self.assertEqual(r.stack(), [])
        self.assertEqual(r.get('base'), 10)
        r.uart('TIMER-INIT TIMER-STOP TIMER-START TIMER-STOP\n')
        r.quiet()
        self.assertNotIn(b'error:', bytes(r.memory.tx))
        self.assertTrue(r.cpu._int_enable)
        self.assertEqual((r.memory.timer[4], r.memory.pending), (2, 0))
        self.assertEqual((r.memory.uart_ie, r.memory.ps2_ie), (4, 4))
        lookup(r.memory, 'TIMER-DEMO')
        self.assertLess(r.get('here'), USER_LIMIT)

    def test_setup_order_and_byte_control_writes(self):
        for word, args, compare, mode in (
                ('TIMER-INIT', (), 65535, 3),
                ('TIMER-ONCE', (0,), 0, 1),
                ('TIMER-ONCE', (250,), 250, 1),
                ('TIMER-ONCE', (65535,), 65535, 1),
                ('TIMER-PERIOD', (2,), 1, 3),
                ('TIMER-PERIOD', (1000,), 999, 3),
                ('TIMER-PERIOD', (65535,), 65534, 3)):
            with self.subTest(word=word, args=args):
                r = self.runner(*args)
                r.memory.timer[5] = 15  # Other pending sources must survive.
                self.assertTrue(r.call(word))
                self.assertEqual(self.timer_writes(r), [
                    (0xFFF4, 0), (0xFFF2, compare & 255),
                    (0xFFF3, compare >> 8), (0xFFF0, 0),
                    (0xFFF1, 0), (0xFFF4, mode)])
                self.assertEqual(r.memory.timer[5], 15)
                self.assertEqual(r.values(), [])

    def test_invalid_period_aborts_before_touching_registers(self):
        for ticks in (0, 1):
            r = self.runner(ticks)
            self.assertFalse(r.call('TIMER-PERIOD'))
            self.assertEqual(self.timer_writes(r), [])
            self.assertEqual(r.values(), [])

    def test_stop_start_preserve_auto_and_mask_timer_irq(self):
        for mode in range(8):
            for word, expected in (('TIMER-STOP', mode & 2),
                                   ('TIMER-START', (mode & 2) | 1)):
                r = self.runner()
                r.memory.timer[:] = bytes([42, 0, 100, 0, mode, 15])
                self.assertTrue(r.call(word))
                self.assertEqual(self.timer_writes(r), [(0xFFF4, expected)])
                self.assertEqual(r.memory.timer[:4], bytes([42, 0, 100, 0]))
                self.assertEqual(r.memory.timer[5], 15)

    def test_count_compare_reset_and_done(self):
        r = self.runner(0xABCD)
        self.assertTrue(r.call('TIMER-COUNT!'))
        self.assertTrue(r.call('TIMER-COUNT@'))
        self.assertEqual(r.values(), [0xABCD])
        self.assertTrue(r.call('TIMER-COMPARE!'))
        self.assertTrue(r.call('TIMER-COMPARE@'))
        self.assertEqual(r.values(), [0xABCD])
        self.assertTrue(r.call('DROP'))
        self.assertTrue(r.call('TIMER-DONE?'))
        self.assertEqual(r.values(), [65535])
        self.assertTrue(r.call('DROP'))
        self.assertTrue(r.call('TIMER-RESET'))
        self.assertTrue(r.call('TIMER-DONE?'))
        self.assertEqual(r.values(), [0])

    def test_wait_zero_wrap_overshoot_and_full_unsigned_range(self):
        for ticks, samples in (
                (0, [123]), (1, [10, 10, 11]), (5, [100, 102, 108]),
                (10, [65530, 65534, 2, 4]),
                (32768, [40000, 60000, 7232]),
                (65535, [0, 30000, 60000, 1000])):
            with self.subTest(ticks=ticks):
                r = self.runner(1234, ticks)
                original_read = r.memory.read16
                remaining = iter(samples)
                reads = []

                def read16(address):
                    if address == 0xFFF0:
                        value = next(remaining)  # Extra polls fail the test.
                        reads.append(value)
                        return value
                    return original_read(address)

                r.memory.read16 = read16
                self.assertTrue(r.call('TIMER-WAIT'))
                self.assertEqual(reads, samples)
                self.assertEqual(r.values(), [1234])
                self.assertEqual(self.timer_writes(r), [])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    _, remaining = parser.parse_known_args()
    unittest.main(argv=[sys.argv[0], *remaining])
