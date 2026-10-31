"""Complete dual-console sessions with one real interpreter/compiler instance."""
import unittest
from dual_support import DualSession


class FrontendChecks(unittest.TestCase):
    def test_twenty_four_cell_display_with_interrupt(self):
        r = DualSession()
        values = list(range(1, 25))
        r.uart(' '.join(map(str, values)) + '\r')
        r.quiet()
        self.assertEqual(r.stack(), values)
        r.memory.data[0x3E0:0x3E2] = b'ok'
        original = r.step
        sent = False

        def interrupt():
            nonlocal sent
            # Interrupt the last restored value's formatting, with the larger
            # user stack back in hardware and .S scratch still in use.
            if r.cpu._pc == r.image.symbols['print_signed'] and r.get('dump_index') == 0 and not sent:
                sent = True
                r.memory.receive_ps2(0x12)  # Shift: queued without adding text.
            original()
        r.step = interrupt
        r.uart('.S\r')
        r.quiet()
        self.assertTrue(sent)
        self.assertIn(b'<24> ' + ' '.join(map(str, values)).encode() + b' ', bytes(r.memory.tx))
        self.assertEqual(r.stack(), values)
        self.assertEqual(r.memory.data[0x3E0:0x3E2], b'ok')
        self.assertTrue(r.cpu._int_enable)

    def test_boot_and_strict_routing(self):
        r = DualSession()
        self.assertEqual(bytes(r.memory.tx), b'ok\r\n')
        self.assertTrue(r.memory.screen().startswith(b'ok'))
        r.keyboard('1 2 + .\r')
        r.quiet()
        self.assertIn(b'3 ok', r.memory.screen())
        self.assertEqual(bytes(r.memory.tx), b'ok\r\n')
        before = bytes(r.memory.vram)
        r.uart('4 5 + .\r\n')
        r.quiet()
        self.assertEqual(bytes(r.memory.tx), b'ok\r\n4 5 + .\r\n9 ok\r\n')
        self.assertEqual(bytes(r.memory.vram), before)
        self.assertEqual(r.stack(), [])

    def test_shared_dictionary_stack_and_partial_line_independence(self):
        r = DualSession()
        r.keyboard(': doppelt dup + ;\r')
        r.quiet()
        r.uart('7 doppelt .\r11\r')
        r.quiet()
        self.assertIn(b'14 ok\r\n', bytes(r.memory.tx))
        self.assertEqual(r.stack(), [11])
        r.keyboard('2 + .\r')
        r.quiet()
        self.assertIn(b'13 ok', r.memory.screen())
        self.assertEqual(r.stack(), [])
        r.uart('12')  # Partial input cannot acquire interpreter ownership.
        r.keyboard('3 .\r')
        r.quiet()
        self.assertIn(b'3 ok', r.memory.screen())
        self.assertNotIn(b'12 ok', bytes(r.memory.tx))
        r.uart(' .\r')
        r.quiet()
        self.assertTrue(bytes(r.memory.tx).endswith(b'12 .\r\n12 ok\r\n'))

    def test_multiline_ownership_including_bracket_interpretation(self):
        r = DualSession()
        r.keyboard(': LOCAL [\r')
        r.quiet()
        self.assertEqual((r.get('definition_open'), r.get('state')), (1, 0))
        r.uart('9 .\r')
        r.until(lambda: not r.uart_wire and r.memory.read16(0xF202) == 1
                and r.cpu._pc == r.image.symbols['irq_wait'])
        self.assertNotIn(b'\r\n9 ok', bytes(r.memory.tx))
        self.assertEqual(r.get('console_owner'), 1)
        r.keyboard('] 4 ;\r')
        r.quiet()
        self.assertEqual(r.get('definition_open'), 0)
        self.assertTrue(bytes(r.memory.tx).endswith(b'9 ok\r\n'))
        r.uart('LOCAL .\r')
        r.quiet()
        self.assertTrue(bytes(r.memory.tx).endswith(b'4 ok\r\n'))

    def test_key_is_bound_to_owner_and_other_input_waits(self):
        r = DualSession()
        r.uart(': TAKE KEY . ;\rTAKE\r')
        r.until(lambda: not r.uart_wire and r.cpu._pc == r.image.symbols['raw_key'])
        r.keyboard('9 .\r')
        r.until(lambda: not r.ps2_wire and not r.memory.ps2_rx
                and r.cpu._pc == r.image.symbols['raw_key'])
        self.assertEqual(r.get('console_owner'), 0)
        self.assertTrue(r.cpu._int_enable)
        self.assertNotIn(b'9 .', r.memory.screen())
        r.uart('A')
        r.quiet()
        self.assertTrue(bytes(r.memory.tx).endswith(b'65 ok\r\n'))
        self.assertIn(b'9 ok', r.memory.screen())

    def test_simultaneous_ready_lines_alternate(self):
        for last in (0, 1):
            r = DualSession()
            r.set('last_source', last)
            for base, text in ((0xF200, b'111 .'), (0xF300, b'222 .')):
                r.memory.write16(base, len(text))
                r.memory.write16(base + 2, 1)
                r.memory.data[base + 16:base + 16 + len(text)] = text
            first = 1 - last
            r.until(lambda: r.cpu._pc == r.image.symbols['interpret_line'])
            self.assertEqual(r.get('console_owner'), first)
            r.quiet()
            self.assertIn(b'111 ok', bytes(r.memory.tx))
            self.assertIn(b'222 ok', r.memory.screen())
            self.assertEqual(r.get('last_source'), last)

    def test_local_errors_abort_editing_and_overflow_recovery(self):
        r = DualSession()
        r.keyboard('1 2 x\b+ .\rnope\rABORT\r')
        r.quiet()
        self.assertIn(b'3 ok', r.memory.screen())
        self.assertIn(b'error: unknown word nope', r.memory.screen())
        self.assertEqual(bytes(r.memory.tx), b'ok\r\n')
        self.assertEqual(r.stack(), [])
        r.uart('1' * 128 + '\r')
        r.quiet()
        self.assertIn(b'error: input too long', bytes(r.memory.tx))
        self.assertEqual(r.stack(), [])
        # Physical FIFO overrun while no CPU instruction executes.
        r.set('kbd_shift', 1)
        for _ in range(17):
            r.memory.receive_ps2(0x1C)
        r.until(lambda: r.memory.read16(0xF308) == 1
                and r.cpu._pc == r.image.symbols['irq_wait'])
        self.assertEqual(r.get('kbd_shift'), 0)
        r.keyboard('\r')  # Explicit synchronization after loss.
        r.quiet()
        self.assertIn(b'error: input too long', r.memory.screen())
        r.keyboard('2 .\r')
        r.quiet()
        self.assertIn(b'2 ok', r.memory.screen())
        self.assertLessEqual(r.max_data, 16)
        self.assertLessEqual(r.max_frames, 16)

    def test_errors_release_definition_owner_and_full_stack_survives_output(self):
        r = DualSession()
        r.keyboard(': BROKEN\r')
        r.quiet()
        r.uart('8 .\r')
        r.until(lambda: r.memory.read16(0xF202) == 1 and r.cpu._pc == r.image.symbols['irq_wait'])
        r.keyboard('missing\r')
        r.quiet()
        self.assertEqual(r.get('definition_open'), 0)
        self.assertTrue(bytes(r.memory.tx).endswith(b'8 ok\r\n'))
        self.assertIn(b'error: unknown word missing', r.memory.screen())
        r.uart('1 2 3 4 5 6 7 8\r')
        r.quiet()
        r.keyboard('.S\r')
        r.quiet()
        self.assertIn(b'<8> 1 2 3 4 5 6 7 8 ', r.memory.screen())
        self.assertEqual(r.stack(), list(range(1, 9)))
        r.keyboard('WORDS\r')
        r.quiet()
        self.assertEqual(r.stack(), list(range(1, 9)))
        self.assertLessEqual(r.max_data, 16)
        self.assertLessEqual(r.max_frames, 16)
        print(f'Dual model stack peak: DS={r.max_data}/32 RS={r.max_frames}/32')

    def test_cpu_reset_discards_stale_input_and_rebuilds_dictionary(self):
        r = DualSession()
        r.uart(': old 7 ;\r1 2\r')
        r.quiet()
        r.memory.receive_uart(ord('X'))
        r.memory.receive_ps2(0x12)
        r.memory.receive_ps2(0x1C)
        r.memory.ps2_errors = 24
        r.memory.event(8)
        before = len(r.memory.tx)
        r.cpu.reset()
        r.physical = r.frames = 0
        r.until(lambda: r.cpu._pc == r.image.symbols['read_line'] and r.get('console_initialized'))
        r.quiet()
        self.assertEqual(bytes(r.memory.tx[before:]), b'ok\r\n')
        self.assertTrue(r.memory.screen().startswith(b'ok'))
        self.assertEqual(r.stack(), [])
        self.assertEqual(r.get('latest'), r.image.symbols['kernel_latest'])
        self.assertEqual((r.memory.pending, r.memory.ps2_errors, r.get('kbd_shift')), (0, 0, 0))
        self.assertEqual((r.memory.uart_ie, r.memory.ps2_ie), (4, 4))

    def test_loss_during_key_aborts_and_discards_to_resynchronizing_enter(self):
        r = DualSession()
        r.uart(': take KEY . ;\rtake\r')
        r.until(lambda: not r.uart_wire and r.cpu._pc == r.image.symbols['raw_key'])
        r.memory.write16(0xF104, 1)  # Software ring loss while KEY is blocked.
        r.until(lambda: b'error: input too long' in bytes(r.memory.tx)
                and r.cpu._pc == r.image.symbols['irq_wait'])
        before = bytes(r.memory.tx)
        r.uart('123 .\r')  # Damaged line is drained, never executed or echoed.
        r.quiet()
        self.assertEqual(bytes(r.memory.tx), before)
        self.assertEqual(r.stack(), [])
        r.uart('2 .\r')
        r.quiet()
        self.assertTrue(bytes(r.memory.tx).endswith(b'2 .\r\n2 ok\r\n'))


if __name__ == '__main__':
    from dual_support import run_tests
    run_tests()
