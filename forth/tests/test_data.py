"""AP 8 allocation, transactional defining words and string lifetimes."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / 'src', ROOT / 'tests', ROOT / 'forth/tests'):
    sys.path.insert(0, str(directory))
from forth.build import build_image
from forth.image import Image, USER_LIMIT
from forth.kernel.boot import VARIABLES
from prim.isa import PrimOpcodes as Op
from forth.tests.model import Runner, cell, lookup, session

RTL = False


class DataChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = build_image()

    def test_allocation_cell_byte_and_here(self):
        source = b'HERE 1 ALLOT HERE 4660 , 43981 C, HERE\n'
        out, values, memory, _ = session(self.image, source)
        start = self.image.symbols['user_start']
        self.assertNotIn(b'error:', out)
        self.assertEqual(values, [start, start + 1, start + 4])
        self.assertEqual(memory.data[start + 1:start + 4], b'\x34\x12\xcd')
        self.assertEqual(cell(memory, VARIABLES['latest']), self.image.symbols['kernel_latest'])
        for count in (0, 1, 32767):
            out, _, memory, _ = session(self.image, f'#{count} ALLOT\n'.encode())
            self.assertNotIn(b'error:', out)
            self.assertEqual(cell(memory, VARIABLES['here']), start + count)

    def test_unused_tracks_allocation_and_compiled_execution(self):
        source = b'UNUSED 17 ALLOT UNUSED\n: free UNUSED ; free HERE\n'
        out, values, memory, _ = session(self.image, source)
        start = self.image.symbols['user_start']
        here = cell(memory, VARIABLES['here'])
        self.assertNotIn(b'error:', out)
        self.assertEqual(values, [USER_LIMIT - start, USER_LIMIT - start - 17,
                                  USER_LIMIT - here, here])

    def test_unused_at_limit_and_unsigned_output(self):
        for remaining in (0, 1, 32768):
            with self.subTest(remaining=remaining):
                def prepare(memory):
                    memory.write16(VARIABLES['here'], USER_LIMIT - remaining)
                out, values, memory, _ = session(self.image, b'UNUSED DUP U.\n', prepare)
                self.assertNotIn(b'error:', out)
                self.assertEqual(values, [remaining])
                self.assertTrue(out.endswith(f'{remaining} ok\r\n'.encode()), out)
                self.assertEqual(cell(memory, VARIABLES['here']), USER_LIMIT - remaining)

    def test_defining_words_and_runtime_stack_checks(self):
        cases = [(b'VARIABLE x x @ 123 x ! x @\n', [0, 123]),
                 (b'CREATE x 7 , x @\n', [7]),
                 (b'65535 CONSTANT value value\n', [65535]),
                 (b': var VARIABLE ; var x x @\n', [0]),
                 (b': const CONSTANT ; 42 const x x\n', [42])]
        for source, expected in cases:
            out, values, memory, budget = session(self.image, source)
            self.assertNotIn(b'error:', out)
            self.assertEqual(values, expected)
            self.assertEqual(cell(memory, VARIABLES['definition_open']), 0)
            self.assertLessEqual(budget[0], 16)
            self.assertLessEqual(budget[1], 16)
        out, _, memory, _ = session(self.image, b'VARIABLE x\n')
        header, xt = lookup(memory, 'x')
        self.assertEqual(cell(memory, xt + 5), xt + 8)
        self.assertEqual(cell(memory, xt + 8), 0)
        self.assertEqual(cell(memory, VARIABLES['here']), xt + 10)
        def dirty(memory):
            start = self.image.symbols['user_start']
            memory.data[start:start + 128] = b'\xa5' * 128
        _, values, memory, _ = session(self.image, b'VARIABLE x x @\n', dirty)
        self.assertEqual(values, [0])  # Initialization must not depend on image zeros.
        for value in (0, 255, 256, 65535):
            out, values, _, _ = session(self.image, f'#{value} CONSTANT c c\n'.encode())
            self.assertNotIn(b'error:', out)
            self.assertEqual(values, [value])
        for definition, target in ((b'CREATE x', b'x'), (b'VARIABLE x', b'x'),
                                   (b'42 CONSTANT x', b'x')):
            out, values, _, _ = session(self.image, definition + b'\n1 2 3 4 5 6 7 8 ' + target + b'\n')
            self.assertIn(b'error: stack overflow', out)
            self.assertEqual(values, [])

    def test_atomic_allocation_and_definition_failures(self):
        for command, remaining in ((b'VARIABLE x', 19), (b'CREATE x', 17), (b'42 CONSTANT x', 17)):
            before = USER_LIMIT - remaining
            def prepare(memory):
                memory.write16(VARIABLES['here'], before)
                memory.data[USER_LIMIT:USER_LIMIT + 4] = b'kept'
            out, _, memory, _ = session(self.image, command + b'\n', prepare)
            self.assertIn(b'dictionary full', out)
            self.assertEqual(cell(memory, VARIABLES['here']), before)
            self.assertEqual(cell(memory, VARIABLES['latest']), self.image.symbols['kernel_latest'])
            self.assertEqual(memory.data[USER_LIMIT:USER_LIMIT + 4], b'kept')
        for source, code in ((b'-1 ALLOT', 20), (b'32768 ALLOT', 20),
                              (b'CREATE', 14), (b'VARIABLE', 14),
                              (b': bad [ VARIABLE x', 13)):
            out, values, memory, _ = session(self.image, source + b'\n')
            self.assertEqual(cell(memory, VARIABLES['last_error']), code, out)
            self.assertEqual(values, [])
            self.assertEqual(cell(memory, VARIABLES['here']), self.image.symbols['user_start'])
        for source, capacity in ((b'4660 ,', 1), (b'42 C,', 0), (b'1 ALLOT', 0)):
            before = USER_LIMIT - capacity
            def prepare(memory):
                memory.write16(VARIABLES['here'], before)
                memory.data[before:USER_LIMIT + 2] = b'k' * (capacity + 2)
            out, _, memory, _ = session(self.image, source + b'\n', prepare)
            self.assertIn(b'dictionary full', out)
            self.assertEqual(cell(memory, VARIABLES['here']), before)
            self.assertEqual(memory.data[before:USER_LIMIT + 2], b'k' * (capacity + 2))
        def full(memory):
            memory.write16(VARIABLES['here'], USER_LIMIT)
        out, _, memory, _ = session(self.image, b'0 ALLOT\n', full)
        self.assertNotIn(b'error:', out)
        self.assertEqual(cell(memory, VARIABLES['here']), USER_LIMIT)

    def test_type_empty_and_byte_output(self):
        for data in (b'', b'abc', b'\x00\x7f\xe4'):
            runner = Runner(self.image, [1] * 6 + [0xD000, len(data)])
            runner.memory.data[0xD000:0xD000 + len(data)] = data
            self.assertTrue(runner.call('TYPE'))
            self.assertEqual(runner.values(), [1] * 6)
            self.assertEqual(bytes(runner.memory.tx), bytes(b & 127 for b in data))
        runner = Runner(self.image, [0xFFFF, 0])
        self.assertTrue(runner.call('TYPE'))  # Does not consume UART RX for length zero.
        self.assertEqual(runner.memory.tx, [])

    def test_interpreted_strings_whitespace_comments_and_lifetime(self):
        cases = [(b'S" hello" TYPE\n', b'hellook\r\n'),
                 (b'S"   ab" TYPE\n', b'  abok\r\n'),
                 (b'S" " TYPE\n', b'ok\r\n'),
                 (b'S" \\ ( ) ; [ ]" TYPE\n', b'\\ ( ) ; [ ]ok\r\n')]
        for source, suffix in cases:
            out, values, _, _ = session(self.image, source)
            self.assertTrue(out.endswith(suffix), out)
            self.assertEqual(values, [])
        source = b'S" old"\n." fresh"\nTYPE\n'
        out, values, _, _ = session(self.image, source)
        self.assertIn(b'freshok\r\n', out)
        self.assertTrue(out.endswith(b'oldok\r\n'))
        self.assertEqual(values, [])

    def test_string_stack_limits_and_full_stack_dot_quote(self):
        for n in range(9):
            prefix = b'1 ' * n
            out, values, _, _ = session(self.image, prefix + b'S" x"\n')
            self.assertEqual(b'stack overflow' in out, n > 6)
            if n <= 6:
                self.assertEqual(values, [1] * n + [0x280, 1])
            out, values, _, _ = session(self.image, prefix + b'." x"\n')
            self.assertNotIn(b'error:', out)
            self.assertEqual(values, [1] * n)
        out, values, _, _ = session(self.image, b': x ." text" ; 1 2 3 4 5 6 7 8 x\n')
        self.assertTrue(out.endswith(b'textok\r\n'))
        self.assertEqual(values, list(range(1, 9)))

    def test_compiled_strings_skip_data_and_survive_input_changes(self):
        source = b': msg S" old" ; msg\nS" new" TYPE\nTYPE\n'
        out, values, memory, _ = session(self.image, source)
        self.assertTrue(out.endswith(b'oldok\r\n'), out)
        self.assertIn(b'newok\r\n', out)
        self.assertEqual(values, [])
        _, xt = lookup(memory, 'msg')
        self.assertEqual(memory.data[xt], Op.PUSH)
        self.assertEqual(cell(memory, xt + 1), xt + 7)
        self.assertEqual(memory.data[xt + 3:xt + 7], b'\x02old')
        for source, suffix in ((b': x ." " ; x\n', b'ok\r\n'),
                               (b': x S" ! # []" TYPE ; x\n', b'! # []ok\r\n'),
                               (b': x IF ." yes" ELSE ." no" THEN ; 0 x 1 x\n', b'noyesok\r\n'),
                               (b': x BEGIN DUP WHILE ." x" 1- REPEAT ; 3 x DROP\n', b'xxxok\r\n')):
            out, values, _, _ = session(self.image, source)
            self.assertTrue(out.endswith(suffix), out)
            self.assertEqual(values, [])
        out, values, _, _ = session(self.image, b': x S" a" ; 1 2 3 4 5 6 7 x\n')
        self.assertIn(b'stack overflow', out)
        self.assertEqual(values, [])

    def test_string_errors_and_buffer_bounds(self):
        for source in (b'S" missing\n', b': bad ." missing\n', b': bad S" missing\n'):
            out, values, memory, _ = session(self.image, source)
            self.assertIn(b'unterminated string', out)
            self.assertEqual(values, [])
            self.assertEqual(cell(memory, VARIABLES['here']), self.image.symbols['user_start'])
        # Largest whole-line spelling: 2-byte word + space + 123 bytes + quote.
        source = b'S" ' + b'x' * 123 + b'"\n'
        def prepare(memory):
            memory.data[0x300:0x302] = b'ok'
        out, values, memory, _ = session(self.image, source, prepare)
        self.assertNotIn(b'error:', out)
        self.assertEqual(values, [0x280, 123])
        self.assertEqual(memory.data[0x280:0x280 + 124], b'x' * 123 + b'\0')
        self.assertEqual(memory.data[0x300:0x302], b'ok')
        def near_end(memory):
            memory.write16(VARIABLES['here'], USER_LIMIT - 20)
        out, _, memory, _ = session(self.image, b': x S" abc" ;\n', near_end)
        self.assertIn(b'dictionary full', out)
        self.assertEqual(cell(memory, VARIABLES['here']), USER_LIMIT - 20)

    def test_rtl_data_and_string_sessions(self):
        if not RTL:
            self.skipTest('enable data/string UART sessions with --rtl')
        from rtl_console import RtlConsole
        cases = [(b'VARIABLE x 7 x ! x @\n', [7], b'ok\r\n'),
                 (b'42 CONSTANT x x\n', [42], b'ok\r\n'),
                 (b'CREATE x 7 , x @\n', [7], b'ok\r\n'),
                 (b'S" hi" TYPE\n', [], b'hiok\r\n'),
                 (b': x S" hello" TYPE ; x\n', [], b'hellook\r\n'),
                 (b': x ." text" ; 1 2 3 4 5 6 7 8 x\n', list(range(1, 9)), b'textok\r\n'),
                 (b': x IF ." yes" ELSE ." no" THEN ; 0 x 1 x\n', [], b'noyesok\r\n'),
                 (b': x ." missing\n2\n', [2], b'ok\r\n')]
        with tempfile.TemporaryDirectory(prefix='forth-data-rtl-') as directory:
            sim = RtlConsole(directory, self.image)
            for source, expected, suffix in cases:
                with self.subTest(source=source):
                    out, values, _ = sim.session(source)
                    self.assertTrue(out.endswith(suffix), out)
                    self.assertEqual(values, expected)

    def test_rtl_strings_with_physical_sram(self):
        if not RTL:
            self.skipTest('enable physical SRAM string execution with --rtl')
        from forth.tests.tools import configured_tools as Tools
        from support.paths import TIMINGS
        from forth.tests.forth_sram import ForthSramSimulation
        source = b': x ." hi" ; x'
        image = build_image()
        p = Image(); p.org(USER_LIMIT)
        p.push(len(source)); p.push(VARIABLES['input_length']); p.op(Op.STORE)
        for index, byte in enumerate(source):
            p.push(byte); p.push(0x200 + index); p.op(Op.BYTE_STORE)
        p.push(image.symbols['interpret_line']); p.op(Op.JP)
        image.memory[USER_LIMIT:p.pc] = p.memory[USER_LIMIT:p.pc]
        idle = image.symbols['idle']
        image.memory[idle:idle + 4] = bytes([Op.PUSH, 0, USER_LIMIT >> 8, Op.JP])
        image.memory[image.symbols['console_next']] = Op.BREAK
        with tempfile.TemporaryDirectory(prefix='forth-data-sram-') as directory:
            sim = ForthSramSimulation(directory, Tools(), with_uart=True)
            sim.build()
            for timing in TIMINGS:
                result = sim.compare_image(image.memory, timing, max_steps=30000)
                self.assertEqual(result.serial, b'hiok\r\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
