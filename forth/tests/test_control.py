"""AP 7 conditional/loop compilation, checked flags and control stack limits."""
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
from test_console import session
from test_compiler import cell, lookup

RTL = False
CASES = [
    (b': select IF 11 ELSE 22 THEN ; 0 select 1 select\n', [22, 11]),
    (b': abs DUP 0< IF NEGATE THEN ; -7 abs 0 abs 7 abs\n', [7, 0, 7]),
    (b': n 4 BEGIN 1- DUP 0= UNTIL ; n\n', [0]),
    (b': n 4 BEGIN DUP WHILE 1- REPEAT ; n\n', [0]),
    (b': x IF IF 1 ELSE 2 THEN ELSE 3 THEN ; 0 x 0 1 x 1 1 x\n', [3, 2, 1]),
    (b': once IF 7 ELSE BEGIN AGAIN THEN ; 1 once\n', [7]),
    (b': n BEGIN DUP WHILE DUP IF 1- THEN REPEAT ; 5 n\n', [0]),
    (b': n BEGIN DUP 0= IF 1 ELSE 1- 0 THEN UNTIL ; 4 n\n', [0]),
]


class ControlChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = build_image()

    def test_conditionals_loops_and_nested_control(self):
        for source, expected in CASES:
            with self.subTest(source=source):
                output, stack, memory, budget = session(self.image, source)
                self.assertNotIn(b'error:', output)
                self.assertEqual(stack, expected)
                self.assertEqual(cell(memory, VARIABLES['control_depth']), 0)
                self.assertLessEqual(budget[0], 16)
                self.assertLessEqual(budget[1], 16)

    def test_flags_are_consumed_and_checked_at_runtime(self):
        for flag in (0, 1, 65535, 32768):
            source = f': test IF 9 THEN ; 1 2 3 4 5 6 7 #{flag} test\n'.encode()
            out, stack, _, _ = session(self.image, source)
            self.assertNotIn(b'error:', out)
            self.assertEqual(stack, list(range(1, 8)) + ([9] if flag else []))
        for source in (b': test IF THEN ; test\n', b': test BEGIN UNTIL ; test\n'):
            out, stack, memory, _ = session(self.image, source)
            self.assertIn(b'error: stack underflow', out)
            self.assertEqual(stack, [])
            self.assertGreater(cell(memory, VARIABLES['here']), self.image.symbols['user_start'])

    def test_bad_nesting_and_context_roll_back(self):
        bad = [b'ELSE', b'THEN', b'UNTIL', b'AGAIN', b'WHILE', b'REPEAT',
               b'IF', b'BEGIN', b'BEGIN THEN', b'IF AGAIN', b'BEGIN WHILE UNTIL',
               b'BEGIN WHILE WHILE REPEAT', b'IF ELSE ELSE THEN', b'IF BEGIN THEN']
        for body in bad:
            out, stack, memory, _ = session(self.image, b': good 7 ;\n: bad ' + body + b' ;\ngood\n')
            self.assertIn(b'error: unresolved control', out, body)
            self.assertEqual(stack, [7])
            self.assertEqual(cell(memory, VARIABLES['latest']), lookup(memory, 'good')[0])
            self.assertEqual(cell(memory, VARIABLES['control_depth']), 0)
        for word in ('IF', 'ELSE', 'THEN', 'BEGIN', 'UNTIL', 'AGAIN', 'WHILE', 'REPEAT'):
            out, _, memory, _ = session(self.image, (word + '\n').encode())
            self.assertIn(b'compile-only word', out)
            self.assertEqual(cell(memory, VARIABLES['last_error']), 12)

    def test_control_stack_capacity_and_sentinels(self):
        for count, error in ((32, False), (33, True)):
            source = b': deep\n' + b'IF\n' * count + b'THEN\n' * count + b';\n'
            def prepare(memory):
                memory.data[0x380:0x382] = b'ok'
                memory.data[0x2FE:0x300] = b'ok'
            out, _, memory, _ = session(self.image, source, prepare)
            self.assertEqual(b'control stack overflow' in out, error)
            self.assertEqual(memory.data[0x380:0x382], b'ok')
            self.assertEqual(memory.data[0x2FE:0x300], b'ok')
            if not error:
                self.assertNotIn(b'error:', out)
        # Control-flow compiler never uses the user's data stack for fixups.
        out, stack, _, _ = session(self.image, b'1 2 3 4 5 6 7 8 : x IF 0 THEN ;\n')
        self.assertNotIn(b'error:', out)
        self.assertEqual(stack, list(range(1, 9)))

    def test_forward_targets_reach_shared_return(self):
        out, stack, memory, _ = session(self.image, b': x IF 1 THEN ; 0 x\n')
        _, xt = lookup(memory, 'x')
        end = cell(memory, VARIABLES['here'])
        self.assertEqual(memory.data[end - 1], 128)
        self.assertEqual(cell(memory, xt + 5), end - 1)  # Guard CALL, PUSH16 target, JZ.
        self.assertEqual(stack, [])
        def near_end(memory):
            memory.write16(VARIABLES['here'], USER_LIMIT - 12)
        out, _, memory, _ = session(self.image, b': x IF THEN ;\n', near_end)
        self.assertIn(b'dictionary full', out)
        self.assertEqual(cell(memory, VARIABLES['here']), USER_LIMIT - 12)

    def test_rtl_control_sessions(self):
        if not RTL:
            self.skipTest('enable control/UART sessions with --rtl')
        from rtl_console import RtlConsole
        with tempfile.TemporaryDirectory(prefix='forth-control-rtl-') as directory:
            sim = RtlConsole(directory, self.image)
            for source, expected in CASES:
                with self.subTest(source=source):
                    output, stack, memory = sim.session(source)
                    self.assertNotIn(b'error:', output)
                    self.assertEqual(stack, expected)
                    self.assertEqual(cell(memory, VARIABLES['control_depth']), 0)

    def test_rtl_control_with_physical_sram(self):
        if not RTL:
            self.skipTest('enable physical SRAM branch execution with --rtl')
        from support.config import Tools
        from support.paths import TIMINGS
        from forth.tests.forth_sram import ForthSramSimulation as SramSimulation
        # Source is interpreted/compiled by Prim; host only installs its bytes.
        source = b': x IF 1 ELSE 2 THEN ; 0 x'
        image = build_image()
        p = Image()
        p.org(USER_LIMIT)
        p.push(len(source)); p.push(VARIABLES['input_length']); p.op(Op.STORE)
        for index, byte in enumerate(source):
            p.push(byte); p.push(0x200 + index); p.op(Op.BYTE_STORE)
        p.push(image.symbols['interpret_line']); p.op(Op.JP)
        image.memory[USER_LIMIT:p.pc] = p.memory[USER_LIMIT:p.pc]
        idle = image.symbols['idle']
        image.memory[idle:idle + 4] = bytes([Op.PUSH, 0, USER_LIMIT >> 8, Op.JP])
        image.memory[image.symbols['console_next']] = Op.BREAK
        with tempfile.TemporaryDirectory(prefix='forth-control-sram-') as directory:
            sim = SramSimulation(directory, Tools(), with_uart=True)
            sim.build()
            for timing in TIMINGS:
                # Dictionary traversal grows as subsequent APs add kernel words.
                result = sim.compare_image(image.memory, timing, max_steps=50000)
                self.assertEqual(result.serial, b'ok\r\n')
                last = next(r for r in reversed(result.records) if r['kind'] == 'step')
                self.assertEqual(last['ds'][0], 2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
