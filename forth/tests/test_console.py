"""AP 5 complete text sessions and independent formatting/lookup checks."""
import argparse
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / 'src', ROOT / 'tests', ROOT / 'forth/tests'):
    sys.path.insert(0, str(directory))

from forth.build import build_image
from forth.kernel.boot import VARIABLES
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op
from test_primitives import Runner, UartMemory, stack_delta

RTL = False


def formatted(value, base, signed=False):
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    negative = signed and value >= 32768
    if negative:
        value = 65536 - value
    text = ''
    while value:
        value, digit = divmod(value, base)
        text = alphabet[digit] + text
    return ('-' if negative else '') + (text or '0')


def session(image, payload, prepare=None):
    memory = UartMemory(image.memory, payload)
    cpu = Prim(memory)
    physical = frames = max_data = max_frames = 0
    for steps in range(2000000):
        if cpu._pc in (image.symbols['console_next'], image.symbols['raw_key']) and not memory.rx:
            depth = memory.read16(VARIABLES['depth'])
            values = [cpu._ds[(cpu._dsp - depth + 1 + n) % 16] for n in range(depth)]
            return bytes(memory.tx), values, memory, (max_data, max_frames)
        if cpu._pc == image.symbols['idle']:
            if prepare:
                prepare(memory)
                prepare = None
            # Cold/error/ABORT entry abandons physical cells and frames;
            # pointers need not become zero to establish an empty stack base.
            physical = frames = 0
        opcode = memory.data[cpu._pc]
        op = opcode & 127
        physical += stack_delta(op)
        frames += int(op == Op.CALL)
        if opcode & 128 and op not in (Op.CALL, Op.JP, Op.JZ):
            frames -= 1
        if not (0 <= physical <= 16 and 0 <= frames <= 16):
            raise AssertionError(f'stack budget at {cpu._pc:04x}: DS={physical}, RS={frames}')
        max_data, max_frames = max(max_data, physical), max(max_frames, frames)
        cpu.step()
        memory.reads.clear()  # Long formatting sessions need no retained bus log.
    raise AssertionError('console timeout')


class ConsoleChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = build_image()

    def test_number_output_all_bases(self):
        for base in range(2, 37):
            for value in (0, 1, 32767, 32768, 65535):
                for name, is_signed in (('.', True), ('U.', False)):
                    runner = Runner(self.image, [123] * 7 + [value])
                    runner.memory.data[0x39E:0x3A0] = b'ok'
                    runner.memory.write16(VARIABLES['base'], base)
                    self.assertTrue(runner.call(name, limit=100000))
                    self.assertEqual(bytes(runner.memory.tx), (formatted(value, base, is_signed) + ' ').encode())
                    self.assertEqual(runner.values(), [123] * 7)
                    self.assertEqual(runner.cpu._rsp, 0)
                    self.assertLessEqual(runner.max_extra, 8)
                    self.assertEqual(runner.memory.data[0x39E:0x3A0], b'ok')

    def test_stack_display_every_depth_and_base(self):
        values = [0, 1, 32767, 32768, 65535, 36, 2, 0xABCD]
        max_data = max_frames = 0
        for base in range(2, 37):
            for n in range(9):
                runner = Runner(self.image, values[:n])
                runner.memory.data[0x39E:0x3A0] = b'ok'
                runner.memory.data[0x3B0:0x3B2] = b'ok'
                runner.memory.write16(VARIABLES['base'], base)
                self.assertTrue(runner.call('.S', limit=300000))
                expected = '<' + formatted(n, base) + '> '
                expected += ''.join(formatted(v, base, True) + ' ' for v in values[:n])
                self.assertEqual(bytes(runner.memory.tx), expected.encode(), (base, n))
                self.assertEqual(runner.values(), values[:n])
                self.assertEqual(runner.cpu._dsp, n)
                self.assertEqual(runner.cpu._rsp, 0)
                self.assertLessEqual(runner.max_extra, 8)
                self.assertEqual(runner.memory.data[0x39E:0x3A0], b'ok')
                self.assertEqual(runner.memory.data[0x3B0:0x3B2], b'ok')
                max_data = max(max_data, runner.max_data)
                max_frames = max(max_frames, runner.max_return)
        print(f'.S all depths/bases: DS={max_data}/16, RS={max_frames}/16')

    def test_lookup_case_visibility_and_shadowing(self):
        for name in ('dup', 'DuP', 'DUP', '+', '-ROT', 'U.', '.S', '\\', '('):
            runner = Runner(self.image, [11] * 8)
            data = name.encode()
            runner.memory.data[0x200:0x200 + len(data)] = data
            runner.memory.write16(VARIABLES['token_addr'], 0x200)
            runner.memory.write16(VARIABLES['token_length'], len(data))
            self.assertTrue(runner.invoke(self.image.symbols['find_word']))
            word = next(w for w in self.image.words if w['name'] == name.upper())
            self.assertEqual(runner.memory.read16(VARIABLES['found_xt']), self.image.symbols[word['xt']])
            self.assertEqual(runner.values(), [11] * 8)
        for name in ('', 'du', 'dupp', 'a' * 32):
            runner = Runner(self.image)
            runner.memory.data[0x200:0x200 + len(name)] = name.encode()
            runner.memory.write16(VARIABLES['token_addr'], 0x200)
            runner.memory.write16(VARIABLES['token_length'], len(name))
            self.assertTrue(runner.invoke(self.image.symbols['find_word']))
            self.assertEqual(runner.memory.read16(VARIABLES['found_xt']), 0)

        def aliases(memory):
            latest = self.image.symbols['kernel_latest']
            true = next(w for w in self.image.words if w['name'] == 'TRUE')
            false = next(w for w in self.image.words if w['name'] == 'FALSE')
            address = self.image.symbols['user_start'] + 0x1000
            for name, flags, xt in (('cafe', 0, true['xt']), ('CAFE', 4, false['xt'])):
                data = (latest.to_bytes(2, 'little') + bytes([flags, len(name)])
                        + self.image.symbols[xt].to_bytes(2, 'little') + bytes(2) + name.encode())
                memory.data[address:address + len(data)] = data
                latest, address = address, address + 32
            memory.write16(VARIABLES['latest'], latest)
            memory.write16(VARIABLES['base'], 16)

        # Install aliases only after boot initialization, at first line entry.
        runner = Runner(self.image)
        aliases(runner.memory)
        runner.memory.data[0x200:0x204] = b'CaFe'
        runner.memory.write16(VARIABLES['token_addr'], 0x200)
        runner.memory.write16(VARIABLES['token_length'], 4)
        self.assertTrue(runner.invoke(self.image.symbols['find_word']))
        true = next(w for w in self.image.words if w['name'] == 'TRUE')
        self.assertEqual(runner.memory.read16(VARIABLES['found_xt']), self.image.symbols[true['xt']])

    def test_text_sessions_and_error_recovery(self):
        cases = [
            (b'2 3 + .\n', b'ok\r\n2 3 + .\r\n5 ok\r\n', []),
            (b'7 dUp * .\r\n', b'ok\r\n7 dUp * .\r\n49 ok\r\n', []),
            (b'1 2 .s\n+ depth . .\n',
             b'ok\r\n1 2 .s\r\n<2> 1 2 ok\r\n+ depth . .\r\n1 3 ok\r\n', []),
            (b'HEX ffff U. -8000 . DECIMAL\n',
             b'ok\r\nHEX ffff U. -8000 . DECIMAL\r\nFFFF -8000 ok\r\n', []),
            (b'1 ( ignored ) 2 + \\ ignored\n.\n',
             b'ok\r\n1 ( ignored ) 2 + \\ ignored\r\nok\r\n.\r\n3 ok\r\n', []),
            (b'1 Missing 99\n2 .\n',
             b'ok\r\n1 Missing 99\r\nerror: unknown word Missing\r\nok\r\n2 .\r\n2 ok\r\n', []),
            (b'65536\n3 .\n',
             b'ok\r\n65536\r\nerror: number overflow\r\nok\r\n3 .\r\n3 ok\r\n', []),
            (b'1 2 ABORT 99\nDEPTH .\n',
             b'ok\r\n1 2 ABORT 99\r\nok\r\nDEPTH .\r\n0 ok\r\n', []),
            (b'1 2 3 4 5 6 7 8\n', b'ok\r\n1 2 3 4 5 6 7 8\r\nok\r\n', list(range(1, 9))),
            (b'1 2 3 4 5 6 7 8 9\nDEPTH .\n',
             b'ok\r\n1 2 3 4 5 6 7 8 9\r\nerror: stack overflow\r\nok\r\nDEPTH .\r\n0 ok\r\n', []),
        ]
        for payload, expected, stack in cases:
            with self.subTest(payload=payload):
                output, values, memory, budget = session(self.image, payload)
                self.assertEqual(output, expected)
                self.assertEqual(values, stack)
                self.assertLessEqual(budget[0], 16)
                self.assertLessEqual(budget[1], 16)
        payload = b'DROP\n1 .\n' * 25
        output, values, _, budget = session(self.image, payload)
        self.assertEqual(output.count(b'error: stack underflow'), 25)
        self.assertEqual(output.count(b'1 ok\r\n'), 25)
        self.assertEqual(values, [])
        print(f'Console recovery across ring wrap: DS={budget[0]}/16, RS={budget[1]}/16')

    def test_words_and_bad_output_base(self):
        runner = Runner(self.image, [1] * 8)
        self.assertTrue(runner.call('WORDS', limit=100000))
        expected = ''.join(w['name'] + ' ' for w in reversed(self.image.words)) + '\r\n'
        self.assertEqual(bytes(runner.memory.tx), expected.encode())
        self.assertEqual(runner.values(), [1] * 8)
        for name, inputs in (('.', [65535]), ('U.', [65535]), ('.S', [1, 2])):
            runner = Runner(self.image, inputs)
            runner.memory.write16(VARIABLES['base'], 1)
            self.assertFalse(runner.call(name))
            self.assertEqual(bytes(runner.memory.tx), b'error: invalid base\r\n')

    def test_dictionary_priority_compile_only_and_invalid_base_recovery(self):
        def prepare_aliases(memory):
            header = self.image.symbols['user_start'] + 0x1000
            previous = memory.read16(VARIABLES['latest'])
            for name, flags, target in (('cafe', 0, 'TRUE'), ('CAFE', 4, 'FALSE'),
                                        ('only', 2, 'TRUE')):
                word = next(w for w in self.image.words if w['name'] == target)
                data = (previous.to_bytes(2, 'little') + bytes([flags, len(name)])
                        + self.image.symbols[word['xt']].to_bytes(2, 'little') + bytes(2)
                        + name.encode())
                memory.data[header:header + len(data)] = data
                previous, header = header, header + 32
            memory.write16(VARIABLES['latest'], previous)

        payload = b'HEX CaFe U.\nONLY\n1 U.\n'
        output, values, _, _ = session(self.image, payload, prepare_aliases)
        self.assertEqual(output, b'ok\r\nHEX CaFe U.\r\nFFFF ok\r\nONLY\r\n'
                                 b'error: compile-only word ONLY\r\nok\r\n1 U.\r\n1 ok\r\n')
        self.assertEqual(values, [])
        output, values, _, _ = session(self.image, b'1 BASE !\n1\nDECIMAL 2 .\n')
        self.assertEqual(output, b'ok\r\n1 BASE !\r\nok\r\n1\r\nerror: invalid base\r\nok\r\n'
                                 b'DECIMAL 2 .\r\n2 ok\r\n')
        self.assertEqual(values, [])

    def test_cli_runs_cpu_from_foreign_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(ROOT / 'forth/run.py')],
                                    input=b'2 3 + .\n65534 c@ .\n',
                                    capture_output=True, cwd=directory, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'ok\r\n2 3 + .\r\n5 ok\r\n65534 c@ .\r\n2 ok\r\n')

    def test_rtl_full_text_sessions(self):
        if not RTL:
            self.skipTest('enable full console/UART-buffer sessions with --rtl')
        from support.process import run
        cases = [
            (b'2 3 + .\n', b'ok\r\n2 3 + .\r\n5 ok\r\n', []),
            (b'7 dUp * .\r\n', b'ok\r\n7 dUp * .\r\n49 ok\r\n', []),
            (b'1 2 .s\n+ .\n', b'ok\r\n1 2 .s\r\n<2> 1 2 ok\r\n+ .\r\n3 ok\r\n', []),
            (b'1 Wrong 99\n8 .\n',
             b'ok\r\n1 Wrong 99\r\nerror: unknown word Wrong\r\nok\r\n8 .\r\n8 ok\r\n', []),
            (b'1 2 ABORT 99\n4\n', b'ok\r\n1 2 ABORT 99\r\nok\r\n4\r\nok\r\n', [4]),
            (b'1 2 3 4 5 6 7 8\n', b'ok\r\n1 2 3 4 5 6 7 8\r\nok\r\n', list(range(1, 9))),
        ]
        with tempfile.TemporaryDirectory(prefix='forth-console-rtl-') as directory:
            directory = Path(directory)
            simulator, image_path = directory / 'console', directory / 'image.hex'
            image_path.write_text(''.join(f'{b:02x}\n' for b in bytes(self.image.memory) + bytes(16)))
            run(['iverilog', '-g2012', '-s', 'tb_parser', '-P', 'tb_parser.SESSION=1',
                 '-I', ROOT / 'cpu/rtl', '-o', simulator, ROOT / 'forth/tests/tb_parser.sv',
                 ROOT / 'cpu/rtl/prim.v', ROOT / 'debug_uart/rtl/uart_buffers.v'])
            for payload, expected, stack in cases:
                with self.subTest(payload=payload):
                    rx, tx, ram, stack_path = [directory / f'{n}.hex' for n in ('rx', 'tx', 'ram', 'stack')]
                    rx.write_text(''.join(f'{b:02x}\n' for b in payload))
                    result = run(['vvp', simulator, f'+image={image_path}', f'+rx={rx}',
                                  f'+count={len(payload)}', f'+tx={tx}', f'+ram={ram}',
                                  f'+stack={stack_path}', f'+waitpc={self.image.symbols["console_next"]}',
                                  f'+keypc={self.image.symbols["raw_key"]}'])
                    self.assertIn('PASS Forth console text session', result.stdout)
                    self.assertEqual(bytes(int(x, 16) for x in tx.read_text().split()), expected)
                    self.assertEqual([int(x, 16) for x in stack_path.read_text().split()], stack)
        print(f'PASS AP5: {len(cases)} full on-CPU console/UART text sessions')

    def test_rtl_formatting_with_physical_sram(self):
        if not RTL:
            self.skipTest('enable formatting with physical SRAM/UART-TX with --rtl')
        from forth.image import Image
        from support.config import Tools
        from support.paths import TIMINGS
        from forth.tests.forth_sram import ForthSramSimulation as SramSimulation
        with tempfile.TemporaryDirectory(prefix='forth-format-rtl-') as directory:
            sim = SramSimulation(directory, Tools(), with_uart=True)
            sim.build()
            for name, values, expected in (('.', [65529], b'-7 '), ('U.', [42], b'42 '),
                                           ('.S', [1, 2], b'<2> 1 2 ')):
                image = build_image()
                p = Image()
                start = image.symbols['user_start']
                p.org(start)
                for value in values:
                    p.push(value)
                p.push(len(values))
                p.push(VARIABLES['depth'])
                p.op(Op.STORE)
                target = next(w for w in image.words if w['name'] == name)
                p.push(image.symbols[target['xt']])
                p.op(Op.CALL)
                p.op(Op.BREAK)
                image.memory[start:p.pc] = p.memory[start:p.pc]
                idle = image.symbols['idle']
                image.memory[idle:idle + 4] = bytes([Op.PUSH, start & 255, start >> 8, Op.JP])
                for timing in TIMINGS:
                    with self.subTest(name=name, timing=timing):
                        result = sim.compare_image(image.memory, timing, max_steps=20000)
                        self.assertEqual(result.serial, expected)
        print('PASS AP5 formatting: 3 programs x 3 physical SRAM timings')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
