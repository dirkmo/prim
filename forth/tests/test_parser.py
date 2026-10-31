"""AP 4 CPU-side input/parsing/conversion. --rtl adds RTL checks."""
import argparse
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / 'src', ROOT / 'tests', ROOT / 'forth/tests'):
    sys.path.insert(0, str(directory))

from forth.build import build_image
from forth.image import Image
from forth.kernel.boot import VARIABLES
from prim.isa import PrimOpcodes as Op
from forth.tests.model import Runner

from forth.tests.tools import configured_tools

RTL = False


class ParserChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = build_image()

    def runner(self, rx=()):
        # Exercise all private routines with a full eight-cell user stack.
        return Runner(self.image, [0xA000 + n for n in range(8)], rx)

    def cell(self, runner, name):
        return runner.memory.read16(VARIABLES[name])

    def invoke(self, runner, name):
        self.assertTrue(runner.invoke(self.image.symbols[name]), name)
        self.assertEqual(runner.values(), [0xA000 + n for n in range(8)])
        self.assertEqual(runner.cpu._rsp, 0)
        self.assertEqual(runner.cpu._dsp, 8)
        self.assertLessEqual(runner.max_extra, 8)

    def set_line(self, runner, text):
        data = text.encode('ascii') if isinstance(text, str) else text
        self.assertLessEqual(len(data), 127)
        runner.memory.data[0x200:0x200 + len(data) + 1] = data + b'\0'
        runner.memory.write16(VARIABLES['input_length'], len(data))
        runner.memory.write16(VARIABLES['input_pos'], 0)

    def token(self, runner):
        self.invoke(runner, 'parse_name')
        address, size = self.cell(runner, 'token_addr'), self.cell(runner, 'token_length')
        return bytes(runner.memory.data[address:address + size])

    def number(self, text, base=10):
        runner = self.runner()
        self.set_line(runner, text)
        self.token(runner)
        runner.memory.write16(VARIABLES['base'], base)
        self.invoke(runner, 'parse_number')
        return self.cell(runner, 'number_status'), self.cell(runner, 'number_value')

    def test_line_endings_editing_and_echo(self):
        cases = [(b'abc\n', b'abc', b'abc\r\n'),
                 (b'ab\bc\r', b'ac', b'ab\b \bc\r\n'),
                 (b'\x08\x7fA\x7fB\n', b'B', b'A\b \bB\r\n'),
                 (b'\tfoo\v\fbar\n', b'\tfoo\v\fbar', b'\tfoo\v\fbar\r\n'),
                 (b'\n', b'', b'\r\n'),
                 (b'x' * 127 + b'\n', b'x' * 127, b'x' * 127 + b'\r\n')]
        for payload, expected, echo in cases:
            with self.subTest(payload=payload):
                runner = self.runner(payload)
                runner.memory.data[0x1FF] = 0xA5
                runner.memory.data[0x280] = 0x5A
                self.invoke(runner, 'read_line')
                size = self.cell(runner, 'input_length')
                self.assertEqual(bytes(runner.memory.data[0x200:0x200 + size]), expected)
                self.assertEqual(runner.memory.data[0x200 + size], 0)
                self.assertEqual(bytes(runner.memory.tx), echo)
                self.assertEqual((runner.memory.data[0x1FF], runner.memory.data[0x280]), (0xA5, 0x5A))
        runner = self.runner(b'a\r\nb\rc\n\n')
        for expected in (b'a', b'b', b'c', b''):
            self.invoke(runner, 'read_line')
            size = self.cell(runner, 'input_length')
            self.assertEqual(bytes(runner.memory.data[0x200:0x200 + size]), expected)
        self.assertFalse(runner.memory.rx)
        self.assertEqual(bytes(runner.memory.tx), b'a\r\nb\r\nc\r\n\r\n')

    def test_invalid_lines_are_drained_before_error(self):
        for payload, code in ((b'x' * 128 + b'\b' * 5 + b'y\r\nnext\n', 6),
                              (b'ab\0ignored\nnext\n', 9)):
            runner = self.runner(payload)
            runner.memory.data[0x280] = 0x5A
            self.assertFalse(runner.invoke(self.image.symbols['read_line']))
            self.assertEqual(self.cell(runner, 'last_error'), code)
            self.assertEqual(self.cell(runner, 'input_length'), 0)
            self.assertEqual(self.cell(runner, 'depth'), 0)
            self.assertEqual(runner.memory.data[0x280], 0x5A)
            self.assertTrue(runner.invoke(self.image.symbols['read_line']))
            self.assertEqual(self.cell(runner, 'input_length'), 4)
            self.assertEqual(runner.memory.data[0x200:0x205], b'next\0')

    def test_whitespace_token_bounds_and_positions(self):
        runner = self.runner()
        self.set_line(runner, b' \tDUP\v-12\f$Ab\r#7\nend ')
        self.assertEqual([self.token(runner) for _ in range(6)],
                         [b'DUP', b'-12', b'$Ab', b'#7', b'end', b''])
        self.assertEqual(self.cell(runner, 'input_pos'), self.cell(runner, 'input_length'))
        self.assertEqual(self.cell(runner, 'token_addr'), 0)
        self.set_line(runner, b'a' * 127)
        self.assertEqual(self.token(runner), b'a' * 127)
        self.assertEqual(self.token(runner), b'')
        self.set_line(runner, 'word  tail')
        self.assertEqual(self.token(runner), b'word')
        self.assertEqual(self.cell(runner, 'input_pos'), 5)  # One delimiter consumed.

    def test_comments_and_base_words(self):
        runner = self.runner()
        self.set_line(runner, r'1 \ ignored ( ) 22')
        self.assertEqual(self.token(runner), b'1')
        self.assertEqual(self.token(runner), b'\\')
        self.assertTrue(runner.call('\\'))
        self.assertEqual(self.token(runner), b'')
        self.set_line(runner, '( first " \\ ( ignored ) 42')
        self.assertEqual(self.token(runner), b'(')
        self.assertTrue(runner.call('('))
        self.assertEqual(self.token(runner), b'42')  # Not nested.
        self.set_line(runner, '( unclosed')
        self.token(runner)
        self.assertFalse(runner.call('('))
        self.assertEqual(self.cell(runner, 'last_error'), 7)
        runner = Runner(self.image)
        self.assertTrue(runner.call('BASE'))
        self.assertEqual(runner.values(), [0x104])
        self.assertTrue(runner.call('DROP'))
        for word, base in (('HEX', 16), ('DECIMAL', 10)):
            self.assertTrue(runner.call(word))
            self.assertEqual(self.cell(runner, 'base'), base)
            self.assertEqual(runner.values(), [])

    def test_numbers_all_bases_and_boundaries(self):
        alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        rng = random.Random(3105)
        for base in range(2, 37):
            for value in (0, 1, 32767, 32768, 65535, rng.randrange(65536)):
                n, text = value, ''
                while n:
                    n, digit = divmod(n, base)
                    text = alphabet[digit] + text
                text = text or '0'
                self.assertEqual(self.number(text, base), (1, value), (text, base))
                self.assertEqual(self.number('+' + text.lower(), base), (1, value))
                if value <= 32768:
                    self.assertEqual(self.number('-' + text, base), (1, -value & 65535))
        for text, value in (('$ffff', 65535), ('+$aBcD', 0xABCD),
                            ('-$8000', 32768), ('#65535', 65535), ('-#32768', 32768)):
            self.assertEqual(self.number(text, 2), (1, value))
        self.assertEqual(self.number('0' * 127), (1, 0))

    def test_number_syntax_overflow_and_invalid_base(self):
        for text in ('', '+', '-', '$', '#', '-$', '+#', '$-1', '#+1',
                     '12z', '1_0', '12.0', '0x12', '655360000x', 'DUP'):
            self.assertEqual(self.number(text), (0, 0), text)
        for text in ('65536', '-32769', '$10000', '-$8001', '9' * 127):
            self.assertEqual(self.number(text), (2, 0), text)
        for base in (0, 1, 37, 65535):
            runner = self.runner()
            self.set_line(runner, '$10')
            self.token(runner)
            runner.memory.write16(VARIABLES['base'], base)
            self.assertFalse(runner.invoke(self.image.symbols['parse_number']))
            self.assertEqual(self.cell(runner, 'last_error'), 8)

    def test_rtl_parser_and_number_conversion(self):
        if not RTL:
            self.skipTest('enable SRAM/UART instruction comparisons with --rtl')
        from forth.tests.tools import configured_tools as Tools
        from support.paths import TIMINGS
        from forth.tests.forth_sram import ForthSramSimulation as SramSimulation

        with tempfile.TemporaryDirectory(prefix='forth-parser-rtl-') as directory:
            simulation = SramSimulation(directory, Tools(), with_uart=True)
            simulation.build()
            for text, status, value in ((' -$8000 next', 1, 32768),
                                        (' 65536', 2, 0), (' 12z', 0, 0)):
                image = build_image()
                p = Image()
                p.org(image.symbols['user_start'])
                p.push(len(text))
                p.push(VARIABLES['input_length'])
                p.op(Op.STORE)
                # Initialize line on CPU (boot owns input_length and first byte).
                for index, byte in enumerate(text.encode()):
                    p.push(byte)
                    p.push(0x200 + index)
                    p.op(Op.BYTE_STORE)
                for name in ('parse_name', 'parse_number'):
                    p.push(image.symbols[name])
                    p.op(Op.CALL)
                p.op(Op.BREAK)
                start = image.symbols['user_start']
                image.memory[start:p.pc] = p.memory[start:p.pc]
                idle = image.symbols['idle']
                image.memory[idle:idle + 4] = bytes([Op.PUSH, start & 255, start >> 8, Op.JP])
                for timing in TIMINGS:
                    with self.subTest(text=text, timing=timing):
                        result = simulation.compare_image(image.memory, timing, max_steps=20000)
                        writes = {a: v for r in result.records for a, v in r.get('writes', [])}
                        def cell(name):
                            a = VARIABLES[name]
                            return writes[a] | writes[a + 1] << 8
                        self.assertEqual(cell('number_status'), status)
                        self.assertEqual(cell('number_value'), value)
                        self.assertEqual(result.serial, b'')
            print('PASS AP4 parser/numbers: 3 programs x 3 SRAM timings')

    def test_rtl_line_editor_and_parser(self):
        if not RTL:
            self.skipTest('enable UART-buffer input/editor test with --rtl')
        from support.process import run

        image = build_image()
        p = Image()
        start = image.symbols['user_start']
        p.org(start)
        for value in range(0xA000, 0xA008):
            p.push(value)
        p.push(8)
        p.push(VARIABLES['depth'])
        p.op(Op.STORE)
        for name in ('read_line', 'read_line', 'parse_name', 'parse_number', 'parse_name'):
            p.push(image.symbols[name])
            p.op(Op.CALL)
        p.op(Op.BREAK)
        image.memory[start:p.pc] = p.memory[start:p.pc]
        idle = image.symbols['idle']
        image.memory[idle:idle + 4] = bytes([Op.PUSH, start & 255, start >> 8, Op.JP])
        payload = b'ab\bC\r\nx y\n'
        with tempfile.TemporaryDirectory(prefix='forth-line-rtl-') as directory:
            directory = Path(directory)
            simulator = directory / 'parser'
            image_path, rx_path = directory / 'image.hex', directory / 'rx.hex'
            tx_path, ram_path = directory / 'tx.hex', directory / 'ram.hex'
            image_path.write_text(''.join(f'{byte:02x}\n' for byte in bytes(image.memory) + bytes(16)))
            rx_path.write_text(''.join(f'{byte:02x}\n' for byte in payload))
            run([configured_tools().iverilog, '-g2012', '-s', 'tb_parser', '-I', ROOT / 'cpu/rtl',
                 '-o', simulator, ROOT / 'forth/tests/tb_parser.sv',
                 ROOT / 'cpu/rtl/prim.v', ROOT / 'debug_uart/rtl/uart_buffers.v'])
            result = run([configured_tools().vvp, simulator, f'+image={image_path}', f'+rx={rx_path}',
                          f'+count={len(payload)}', f'+tx={tx_path}', f'+ram={ram_path}'])
            self.assertIn('PASS Forth line/parser', result.stdout)
            actual_tx = bytes(int(line, 16) for line in tx_path.read_text().splitlines())
            self.assertEqual(actual_tx, b'ab\b \bC\r\nx y\r\n')
            ram = bytes(int(token, 16) for line in ram_path.read_text().splitlines()
                        for token in line.split('//')[0].split())
            self.assertEqual(ram[0x200:0x204], b'x y\0')
            def cell(name):
                a = VARIABLES[name]
                return int.from_bytes(ram[a:a + 2], 'little')
            self.assertEqual(cell('input_length'), 3)
            self.assertEqual(cell('input_pos'), 3)
            self.assertEqual((cell('token_addr'), cell('token_length')), (0x202, 1))
            self.assertEqual(cell('number_status'), 0)  # x was not a decimal number.


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
