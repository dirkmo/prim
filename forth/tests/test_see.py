"""Independent expectations for a bounded native-code SEE on Prim."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'src', ROOT / 'tests'):
    sys.path.insert(0, str(path))

from forth.build import build_image
from forth.kernel.boot import VARIABLES
from forth.tests.model import session, cell
from forth.tests.dual_support import DualSession
from forth.tests.rtl_console import RtlConsole

RTL = False


class SeeChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = build_image(dual_console=False)

    def run_source(self, source):
        out, stack, memory, budget = session(self.image, source)
        self.assertNotIn(b'error:', out)
        return out, stack, memory

    def test_calls_literals_returns_shadowing_and_base(self):
        source = (b': old 11 ; : caller old ; : old 22 ;\n'
                  b': square DUP * ; : literal 65535 ; : empty ;\n'
                  b'7 HEX SEE square SEE literal SEE empty SEE caller BASE @ DECIMAL caller\n')
        out, stack, _ = self.run_source(source)
        self.assertIn(b'CALL DUP\r\n', out)
        self.assertIn(b'TAIL * ;\r\n', out)
        self.assertIn(b'LIT FFFF ;\r\n', out)
        self.assertIn(b'NOP ;\r\n', out)
        self.assertIn(b'TAIL old ;\r\n', out)
        self.assertEqual(stack, [7, 16, 11])
        self.assertRegex(out.decode(), r'\$[0-9A-F]{4}: CALL DUP')

    def test_branches_loops_and_strings_are_inspected_without_execution(self):
        source = (b': choice IF 11 ELSE 22 THEN ; : spin BEGIN AGAIN ;\n'
                  b': text ." hello world" S" value" ;\n'
                  b'123 SEE choice SEE spin SEE text\n')
        out, stack, _ = self.run_source(source)
        self.assertIn(b'0BRANCH $', out)
        self.assertGreaterEqual(out.count(b'BRANCH $'), 4)
        self.assertIn(b'LIT 11\r\n', out)
        self.assertIn(b'LIT 22\r\n', out)
        self.assertIn(b'DATA "hello world"\r\n', out)
        self.assertIn(b'DATA "value"\r\n', out)
        self.assertEqual(stack, [123])  # spin was never called, text never executed.
        self.assertNotIn(b'.BYTE', out)

    def test_data_bodies_and_truncated_operands_stay_bounded(self):
        source = (b'VARIABLE data 99 data !\n'
                  b': broken [ 33 C, ] ; : after 42 ;\n'
                  b'SEE data SEE broken data @\n')
        out, stack, _ = self.run_source(source)
        self.assertIn(b'.BYTE $0021\r\n', out)
        self.assertNotIn(b'LIT 99', out)
        self.assertNotIn(b'LIT 42', out)
        self.assertEqual(stack, [99])

    def test_name_errors_kernel_protection_and_open_definition_rollback(self):
        for source, code, message in (
            (b'SEE\n', 14, b'invalid name'),
            (b'SEE missing\n', 11, b'unknown word missing'),
            (b'SEE DUP\n', 23, b'SEE requires a user word'),
            (b'SEE CR\n', 23, b'SEE requires a user word'),
            (b': prior 3 ; : broken SEE prior\n', 13, b'compiler context'),
        ):
            with self.subTest(source=source):
                out, stack, memory, _ = session(self.image, source)
                self.assertIn(b'error: ' + message, out)
                self.assertEqual(cell(memory, VARIABLES['last_error']), code)
                self.assertEqual(cell(memory, VARIABLES['definition_open']), 0)
                self.assertEqual(stack, [])

    def test_both_consoles_preserve_stack_and_irq_during_inspection(self):
        for local in (False, True):
            r = DualSession()
            send = r.keyboard if local else r.uart
            send(': sample IF 1 ELSE 2 THEN ;\r')
            r.quiet()
            values = list(range(1, 17))
            send(' '.join(map(str, values)) + '\r')
            r.quiet()
            before_uart, before_screen = bytes(r.memory.tx), bytes(r.memory.vram)
            original, sent = r.step, False

            def interrupt():
                nonlocal sent
                if r.cpu._pc == r.image.symbols['see_hex'] and not sent:
                    sent = True
                    r.memory.receive_ps2(0x12)  # Queue Shift, without foreground text.
                original()
            r.step = interrupt
            send('SEE sample\r')
            r.quiet()
            self.assertTrue(sent)
            self.assertEqual(r.stack(), values)
            self.assertTrue(r.cpu._int_enable)
            if local:
                self.assertIn(b'0BRANCH $', r.memory.screen())
                self.assertEqual(bytes(r.memory.tx), before_uart)
            else:
                self.assertIn(b'0BRANCH $', bytes(r.memory.tx[len(before_uart):]))
                self.assertEqual(bytes(r.memory.vram), before_screen)

    def test_rtl_native_inspection_and_stack_preservation(self):
        if not RTL:
            self.skipTest('enable native SEE on CPU/UART RTL with --rtl')
        source = (b': x DUP 1+ ; : spin BEGIN AGAIN ; : text ." embedded" ;\n'
                  b'42 SEE x SEE spin SEE text\n')
        with tempfile.TemporaryDirectory() as directory:
            out, stack, _ = RtlConsole(directory, self.image).session(source)
            self.assertNotIn(b'error:', out)
            self.assertIn(b'CALL DUP\r\n', out)
            self.assertIn(b'TAIL 1+ ;\r\n', out)
            self.assertIn(b'BRANCH $', out)
            self.assertIn(b'DATA "embedded"\r\n', out)
            self.assertEqual(stack, [42])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
