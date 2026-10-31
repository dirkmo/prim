"""CPU-native compilation, rollback, instruction boundaries and return behavior."""
import argparse
from pathlib import Path
import subprocess
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


class CompilerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = build_image()

    def test_definitions_multiline_and_compile_time_stack(self):
        cases = [
            (b': quadrat dup * ; 7 quadrat .\n', b'49 ok\r\n', []),
            (b': a\n1\n;\na .\n', b'compiled\r\n1\r\ncompiled\r\n;\r\nok\r\na .\r\n1 ok\r\n', []),
            (b': value [ 20 22 + ] LITERAL ; value .\n', b'42 ok\r\n', []),
            (b': answer 42 ; IMMEDIATE : value answer LITERAL ; value .\n', b'42 ok\r\n', []),
            (b': nothing ; 1 nothing .\n', b'1 ok\r\n', []),
            (b': a 1 ; : a a 1 + ; a .\n', b'2 ok\r\n', []),
            (b': a [ STATE @ ] LITERAL ; a . STATE @ .\n', b'0 0 ok\r\n', []),
            (b': mode STATE @ ; IMMEDIATE : value mode LITERAL ; value .\n', b'1 ok\r\n', []),
            (b': ' + b'X' * 31 + b' 1 ; ' + b'x' * 31 + b'\n', b'ok\r\n', [1]),
        ]
        for payload, suffix, values in cases:
            with self.subTest(payload=payload):
                out, stack, memory, budget = session(self.image, payload)
                self.assertTrue(out.endswith(suffix), out)
                self.assertNotIn(b'error:', out)
                self.assertEqual(stack, values)
                self.assertEqual(cell(memory, VARIABLES['definition_open']), 0)
                self.assertEqual(cell(memory, VARIABLES['state']), 0)
                self.assertLessEqual(budget[0], 16)
                self.assertLessEqual(budget[1], 16)

    def test_tick_bracket_tick_and_execute(self):
        cases = [(b"3 ' DUP EXECUTE .S\n", [3, 3]),
                 (b": get ['] DUP ; 4 get EXECUTE .S\n", [4, 4]),
                 (b": get ' ; 5 get DUP EXECUTE .S\n", [5, 5]),
                 (b": run EXECUTE ; 6 ' DUP run .S\n", [6, 6])]
        for payload, expected in cases:
            out, stack, _, _ = session(self.image, payload)
            self.assertNotIn(b'error:', out)
            self.assertEqual(stack, expected)
        # EXECUTE keeps the target's stack checks, including with a full stack.
        _, _, memory, _ = session(self.image, b': target DUP ;\n')
        _, xt = lookup(memory, 'target')
        for n in range(8):
            r = Runner(self.image, list(range(n)) + [xt])
            start = self.image.symbols['user_start']
            r.memory.data[start:USER_LIMIT] = memory.data[start:USER_LIMIT]
            ok = r.call('EXECUTE')
            self.assertEqual(ok, n > 0)
            if ok:
                self.assertEqual(r.values(), list(range(n)) + [n - 1])

    def test_hidden_header_and_compiler_data_stays_separate(self):
        out, stack, memory, _ = session(self.image, b': draft 42\n')
        self.assertTrue(out.endswith(b'compiled\r\n'))
        self.assertEqual(stack, [])  # 42 is compiled, not interpreted.
        header, _ = lookup(memory, 'draft')
        self.assertEqual(memory.data[header + 2], 4)
        self.assertEqual(cell(memory, VARIABLES['saved_latest']), self.image.symbols['kernel_latest'])
        r = Runner(self.image)
        r.memory.data[0x100:USER_LIMIT] = memory.data[0x100:USER_LIMIT]
        r.memory.data[0x200:0x205] = b'DRAFT'
        r.memory.write16(VARIABLES['token_addr'], 0x200)
        r.memory.write16(VARIABLES['token_length'], 5)
        self.assertTrue(r.invoke(self.image.symbols['find_word']))
        self.assertEqual(cell(r.memory, VARIABLES['found_xt']), 0)

    def test_literal_return_bit_never_changes_operand_bytes(self):
        guard = self.image.symbols['literal_guard']
        prefix = bytes([Op.PUSH, guard & 255, guard >> 8, Op.CALL])
        for value in (0, 127, 128, 129, 255, 256, 0x8021, 0xFFFF):
            payload = f': value #{value} ; value\n'.encode()
            _, stack, memory, _ = session(self.image, payload)
            _, xt = lookup(memory, 'value')
            literal = (bytes([Op.PUSH8 | 128, value]) if value < 256
                       else bytes([Op.PUSH | 128, value & 255, value >> 8]))
            self.assertEqual(memory.data[xt:cell(memory, VARIABLES['here'])], prefix + literal)
            self.assertEqual(stack, [value])

    def test_tail_calls_reduce_return_depth_and_fallback_is_equivalent(self):
        payload = b': leaf 1 ; : tail leaf ; : plain leaf ( no folding ) ;\n'
        _, _, memory, _ = session(self.image, payload)
        _, leaf = lookup(memory, 'leaf')
        _, tail = lookup(memory, 'tail')
        _, plain = lookup(memory, 'plain')
        self.assertEqual(memory.data[tail:tail + 4], bytes([Op.PUSH, leaf & 255, leaf >> 8, Op.JP]))
        self.assertEqual(memory.data[plain:plain + 5], bytes([Op.PUSH, leaf & 255, leaf >> 8, Op.CALL, 128]))
        budgets = []
        for xt in (tail, plain):
            r = Runner(self.image)
            start = self.image.symbols['user_start']
            r.memory.data[start:USER_LIMIT] = memory.data[start:USER_LIMIT]
            self.assertTrue(r.invoke(xt))
            self.assertEqual(r.values(), [1])
            budgets.append(r.max_return)
        self.assertEqual(budgets, [2, 3])
        # A chain much deeper than the physical return stack uses tail jumps.
        text = ': w0 7 ;\n' + ''.join(f': w{n} w{n-1} ;\n' for n in range(1, 40)) + 'w39 .\n'
        out, values, _, budget = session(self.image, text.encode())
        self.assertTrue(out.endswith(b'7 ok\r\n'))
        self.assertEqual(values, [])
        self.assertLessEqual(budget[1], 5)

    def test_immediate_execution_disables_folding_and_empty_return(self):
        payload = b': empty ; : value [ ] 128 ; value\n'
        _, values, memory, _ = session(self.image, payload)
        _, empty = lookup(memory, 'empty')
        _, xt = lookup(memory, 'value')
        self.assertEqual(memory.data[empty], 128)
        self.assertEqual(memory.data[xt + 4:cell(memory, VARIABLES['here'])], bytes([Op.PUSH8, 128, 128]))
        self.assertEqual(values, [128])

    def test_runtime_checks_of_compiled_literals_and_words(self):
        for source, expected_error in ((b': value 9 ; 1 2 3 4 5 6 7 8 value\n', b'stack overflow'),
                                       (b': dropper DROP ; dropper\n', b'stack underflow'),
                                       (b": target 1 2 ; 1 2 3 4 5 6 7 ' target EXECUTE\n", b'stack overflow')):
            out, values, memory, _ = session(self.image, source)
            self.assertIn(b'error: ' + expected_error + b'\r\n', out)
            self.assertEqual(values, [])
            self.assertEqual(cell(memory, VARIABLES['definition_open']), 0)
            self.assertGreater(cell(memory, VARIABLES['here']), self.image.symbols['user_start'])
        out, stack, memory, _ = session(self.image, b': bye ABORT 99 ; 1 bye 2\n3 .\n')
        self.assertTrue(out.endswith(b'3 ok\r\n'))
        self.assertNotIn(b'error:', out)
        self.assertEqual(stack, [])
        lookup(memory, 'bye')  # Runtime ABORT does not erase completed definitions.

    def test_rollback_preserves_previous_words_and_invalidates_pending(self):
        cases = [(b': bad Missing\n', 11), (b': bad [ ABORT\n', 0),
                 (b': bad [ 1 0 /\n', 4), (b': bad : nested\n', 13),
                 (b': bad [ ;\n', 12), (b': bad [ IMMEDIATE\n', 13),
                 (b': bad ( unclosed\n', 7), (b': bad\n' + b'x' * 128 + b'\n', 6),
                 (b': bad\nignored\0text\n', 9)]
        for bad, error in cases:
            out, stack, memory, _ = session(self.image, b': good 7 ;\n' + bad + b'good .\n')
            self.assertTrue(out.endswith(b'7 ok\r\n'), out)
            self.assertEqual(stack, [])
            self.assertEqual(cell(memory, VARIABLES['last_error']), error)
            header, xt = lookup(memory, 'good')
            self.assertEqual(cell(memory, VARIABLES['latest']), header)
            self.assertEqual(cell(memory, VARIABLES['here']), xt + 6)
            self.assertEqual(cell(memory, VARIABLES['definition_open']), 0)
            with self.assertRaises(AssertionError):
                lookup(memory, 'bad')

    def test_context_name_and_control_errors(self):
        cases = [(b';\n', 12), (b'[\n', 12), (b']\n', 13), (b'LITERAL\n', 12),
                 (b"['] DUP\n", 12), (b'IMMEDIATE\n', 16), (b':\n', 14),
                 (b': ' + b'x' * 32 + b'\n', 14), (b"' unknown\n", 11),
                 (f': bad [ 1 #{VARIABLES["control_depth"]} ! ] ;\n'.encode(), 17)]
        for payload, expected in cases:
            out, stack, memory, _ = session(self.image, payload)
            self.assertEqual(cell(memory, VARIABLES['last_error']), expected, (payload, out))
            self.assertEqual(stack, [])
            self.assertEqual(cell(memory, VARIABLES['here']), self.image.symbols['user_start'])
            self.assertEqual(cell(memory, VARIABLES['latest']), self.image.symbols['kernel_latest'])

    def test_dictionary_bounds_and_atomic_failure(self):
        for here in (0, self.image.symbols['user_start'] - 1, USER_LIMIT - 10, USER_LIMIT, 0xFFF0, 0xFFFF):
            def prepare(memory, here=here):
                memory.write16(VARIABLES['here'], here)
                memory.data[USER_LIMIT:USER_LIMIT + 16] = b'protected bytes!'
            out, stack, memory, _ = session(self.image, b': test 1 ;\n', prepare)
            self.assertIn(b'error: dictionary full\r\n', out)
            self.assertEqual(cell(memory, VARIABLES['here']), here)
            self.assertEqual(cell(memory, VARIABLES['latest']), self.image.symbols['kernel_latest'])
            self.assertEqual(memory.data[USER_LIMIT:USER_LIMIT + 16], b'protected bytes!')
        # A final literal can use the last RAM byte: return folded into its opcode.
        # Name 'x': 10-byte header + 6-byte checked literal.
        def exact(memory):
            memory.write16(VARIABLES['here'], USER_LIMIT - 16)
        out, stack, memory, _ = session(self.image, b': x 1 ; x\n', exact)
        self.assertNotIn(b'error:', out)
        self.assertEqual(stack, [1])
        self.assertEqual(cell(memory, VARIABLES['here']), USER_LIMIT)
        # Brackets force a separate return: fail and roll the entire word back.
        out, _, memory, _ = session(self.image, b': x [ ] 1 ;\n', exact)
        self.assertIn(b'error: dictionary full\r\n', out)
        self.assertEqual(cell(memory, VARIABLES['here']), USER_LIMIT - 16)
        self.assertEqual(cell(memory, VARIABLES['latest']), self.image.symbols['kernel_latest'])

    def test_cli_eof_rolls_back_open_definition(self):
        result = subprocess.run([sys.executable, str(ROOT / 'forth/run.py')],
                                input=b': unfinished 42\n', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue(result.stdout.endswith(b'compiled\r\nerror: unfinished definition\r\nok\r\n'))

    def test_rtl_compiler_text_sessions(self):
        if not RTL:
            self.skipTest('enable full compiler/UART sessions with --rtl')
        from rtl_console import RtlConsole
        cases = [
            (b': square dup * ; 7 square .\n', b'49 ok\r\n', []),
            (b': a\n128\n; a\n', b'compiled\r\n; a\r\nok\r\n', [128]),
            (b': value [ 20 22 + ] LITERAL ; value .\n', b'42 ok\r\n', []),
            (b': macro 42 ; IMMEDIATE : value macro LITERAL ; value\n', b'ok\r\n', [42]),
            (b": get ['] DUP ; 4 get EXECUTE\n", b'ok\r\n', [4, 4]),
            (b': good 7 ;\n: bad Missing\ngood .\n', b'7 ok\r\n', []),
            (b': bad [ ABORT\n3\n', b'ok\r\n', [3]),
            (b': value 9 ; 1 2 3 4 5 6 7 8 value\n', b'error: stack overflow\r\nok\r\n', []),
        ]
        with tempfile.TemporaryDirectory(prefix='forth-compiler-rtl-') as directory:
            sim = RtlConsole(directory, self.image)
            for payload, suffix, stack in cases:
                with self.subTest(payload=payload):
                    out, actual, ram = sim.session(payload)
                    self.assertTrue(out.endswith(suffix), out)
                    self.assertEqual(actual, stack)
                    self.assertEqual(cell(ram, VARIABLES['definition_open']), 0)
        print(f'PASS AP6: {len(cases)} on-CPU compiler/UART text sessions')

    def test_rtl_compile_and_execute_with_physical_sram(self):
        if not RTL:
            self.skipTest('enable CPU-side compilation with physical SRAM with --rtl')
        from forth.tests.tools import configured_tools as Tools
        from support.paths import TIMINGS
        from forth.tests.forth_sram import ForthSramSimulation as SramSimulation
        cases = [(b': x 128 ; x', b'ok\r\n', [128]),
                 (b': x Missing', b'error: unknown word Missing\r\n', [])]
        with tempfile.TemporaryDirectory(prefix='forth-compile-sram-') as directory:
            sim = SramSimulation(directory, Tools(), with_uart=True)
            sim.build()
            for source, expected, values in cases:
                image = build_image()
                p = Image()
                p.org(USER_LIMIT)
                p.push(len(source))
                p.push(VARIABLES['input_length'])
                p.op(Op.STORE)
                for index, byte in enumerate(source):
                    p.push(byte)
                    p.push(0x200 + index)
                    p.op(Op.BYTE_STORE)
                p.push(image.symbols['interpret_line'])
                p.op(Op.JP)
                image.memory[USER_LIMIT:p.pc] = p.memory[USER_LIMIT:p.pc]
                idle = image.symbols['idle']
                image.memory[idle:idle + 4] = bytes([Op.PUSH, 0, USER_LIMIT >> 8, Op.JP])
                image.memory[image.symbols['console_next']] = Op.BREAK
                image.memory[image.symbols['error_exit']] = Op.BREAK
                for timing in TIMINGS:
                    with self.subTest(source=source, timing=timing):
                        result = sim.compare_image(image.memory, timing, max_steps=20000)
                        self.assertEqual(result.serial, expected)
                        last = next(r for r in reversed(result.records) if r['kind'] == 'step')
                        self.assertEqual(last['ds'][:len(values)], list(reversed(values)))
                        memory = bytearray(image.memory)
                        for record in result.records:
                            for address, value in record.get('writes', []):
                                if address < len(memory):
                                    memory[address] = value
                        if values:
                            header, xt = lookup(memory, 'x')
                            self.assertEqual(memory[header + 2], 0)
                            self.assertEqual(memory[xt + 4:xt + 6], bytes([Op.PUSH8 | 128, 128]))
                        else:
                            self.assertEqual(cell(memory, VARIABLES['here']), image.symbols['user_start'])
                            self.assertEqual(cell(memory, VARIABLES['latest']), image.symbols['kernel_latest'])
        print('PASS AP6: compiler/rollback x 3 physical SRAM timings, every retirement compared')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
