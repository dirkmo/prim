"""Independent Forth primitive expectations; --rtl adds SRAM/UART checks."""
import argparse
from collections import deque
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / 'src', ROOT / 'tests'):
    sys.path.insert(0, str(directory))

from forth.build import build_image
from forth.image import Image
from forth.kernel.boot import VARIABLES
from forth.kernel.primitives import ERRORS
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op
from support.reference import Memory

RTL = False


def stack_delta(op):
    return (1 if op in (Op.PUSH, Op.PUSH8, Op.DUP, Op.OVER, Op.CARRY, Op.FROM_R)
            else -2 if op in (Op.JZ, Op.STORE, Op.BYTE_STORE)
            else -1 if op in (Op.CALL, Op.JP, Op.AND, Op.OR, Op.XOR,
                             Op.ADD, Op.SUB, Op.LTS, Op.LTU, Op.NIP,
                             Op.DROP, Op.TO_R, Op.INTAD) else 0)


def signed(n):
    return n if n < 0x8000 else n - 65536


class UartMemory(Memory):
    def __init__(self, image, rx=()):
        super().__init__(image, uart=True)
        self.rx = deque(rx)
        self.polls = self.consumed = 0

    def read8(self, address):
        if address == 0xFFFE:
            self.polls += 1
            value = 2 | (bool(self.rx) and self.polls >= 5)
            self.reads.append([address, value])
            return value
        if address == 0xFFFF:
            if self.polls < 5 or not self.rx:
                raise AssertionError('RX read before RXAVAIL')
            value = self.rx.popleft()
            self.consumed += 1
            self.reads.append([address, value])
            return value
        return super().read8(address)


class Runner:
    def __init__(self, image, inputs=(), rx=()):
        self.image = image
        self.memory = UartMemory(image.memory, rx)
        self.cpu = Prim(self.memory)
        self.words = {word['name']: image.symbols[word['xt']] for word in image.words}
        self.max_data = self.max_return = self.max_extra = 0
        self.initial = len(inputs)
        for _ in range(500):
            if self.cpu._pc == image.symbols['idle']:
                break
            self.cpu.step()
        else:
            raise AssertionError('boot timeout')
        for value in inputs:
            self.cpu.dpush(value)
        self.memory.write16(VARIABLES['depth'], len(inputs))
        self.memory.writes.clear()
        self.base = self.cpu._dsp - len(inputs)

    def call(self, word, limit=10000):
        program = Image()
        program.org(self.image.symbols['user_start'])
        program.push(self.words[word])
        program.op(Op.CALL)
        program.op(Op.BREAK)
        start, end = self.image.symbols['user_start'], program.pc
        self.memory.data[start:end] = program.memory[start:end]
        self.cpu._pc = start
        physical_depth = self.memory.read16(VARIABLES['depth'])
        entry_depth = physical_depth
        for step in range(limit):
            if self.cpu._pc == self.image.symbols['idle']:
                return False  # Error abandons the current invocation.
            opcode = self.memory.data[self.cpu._pc]
            if opcode == Op.BREAK:
                return True
            op = opcode & 127
            physical_depth += stack_delta(op)
            if not 0 <= physical_depth <= 16:
                raise AssertionError(f'physical stack violation in {word}: {physical_depth}')
            self.max_data = max(self.max_data, physical_depth)
            self.max_extra = max(self.max_extra, physical_depth - entry_depth)
            self.cpu.step()
            self.max_return = max(self.max_return, self.cpu._rsp)
        raise AssertionError(f'timeout in {word}')

    def values(self):
        depth = self.memory.read16(VARIABLES['depth'])
        return [self.cpu._ds[(self.cpu._dsp - depth + 1 + n) % 16]
                for n in range(depth)]


class PrimitiveChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = build_image()
        cls.budget_data = cls.budget_return = cls.budget_extra = 0

    def check(self, word, inputs, expected):
        runner = Runner(self.image, [x & 65535 for x in inputs])
        self.assertTrue(runner.call(word), word)
        self.assertEqual(runner.values(), [x & 65535 for x in expected], (word, inputs))
        self.assertEqual(runner.cpu._rsp, 0)
        self.assertEqual(runner.cpu._dsp, len(expected))
        self.assertLessEqual(runner.max_extra, 8)
        cls = type(self)
        cls.budget_data = max(cls.budget_data, runner.max_data)
        cls.budget_return = max(cls.budget_return, runner.max_return)
        cls.budget_extra = max(cls.budget_extra, runner.max_extra)
        return runner

    def test_dictionary_headers(self):
        data = self.image.memory
        cell = lambda at: int.from_bytes(data[at:at + 2], 'little')
        header = self.image.symbols['kernel_latest']
        names = []
        while header:
            self.assertEqual(header % 2, 0)
            self.assertEqual(data[header + 2], 0)
            self.assertEqual(data[header + 6:header + 8], b'\0\0')
            length = data[header + 3]
            self.assertTrue(1 <= length <= 31)
            name = bytes(data[header + 8:header + 8 + length]).decode('ascii')
            xt = cell(header + 4)
            self.assertIn(xt, self.image.instructions)
            self.assertGreater(xt, header + 7)
            names.append(name)
            previous = cell(header)
            self.assertLess(previous, header)
            header = previous
        self.assertEqual(names, [w['name'] for w in reversed(self.image.words)])
        self.assertEqual(len(names), len(set(names)))

    def test_static_stack_budgets_all_control_paths(self):
        # Explore both sides of every conditional, including error paths. Loop
        # states converge only if their stack depth is invariant. No values or
        # arithmetic algorithm are simulated by this structural check.
        image = self.image
        data = image.memory
        preceding = dict(zip(image.instructions[1:], image.instructions))
        budget_data = budget_return = budget_extra = 0
        for word in image.words:
            for initial in range(word['need'], 9 - max(0, word['give'] - word['need'])):
                pending = [(image.symbols[word['xt']], initial, (None,))]
                visited = set()
                while pending:
                    pc, depth, returns = pending.pop()
                    if pc == image.symbols['idle']:
                        continue  # Non-returning error exit.
                    state = (pc, depth, returns)
                    if state in visited:
                        continue
                    visited.add(state)
                    self.assertLess(len(visited), 5000, 'unbounded stack growth in loop')
                    self.assertIn(pc, image.instructions)
                    opcode = data[pc]
                    op = opcode & 127
                    next_pc = pc + (3 if op == Op.PUSH else 2 if op == Op.PUSH8 else 1)
                    depth += stack_delta(op)
                    self.assertTrue(0 <= depth <= 16, (word['name'], pc, depth))
                    budget_data = max(budget_data, depth)
                    budget_return = max(budget_return, len(returns))
                    budget_extra = max(budget_extra, depth - initial)
                    if op in (Op.CALL, Op.JP, Op.JZ):
                        before = preceding[pc]
                        push_op = data[before]
                        self.assertIn(push_op, (Op.PUSH, Op.PUSH8))
                        size = 3 if push_op == Op.PUSH else 2
                        self.assertEqual(before + size, pc)
                        target = int.from_bytes(data[before + 1:pc], 'little')
                        if op == Op.CALL:
                            pending.append((target, depth, returns + (next_pc,)))
                        else:
                            pending.append((target, depth, returns))
                            if op == Op.JZ:
                                pending.append((next_pc, depth, returns))
                    elif opcode & 128:
                        if returns[-1] is None:
                            self.assertEqual(depth, initial + word['give'] - word['need'],
                                             word['name'])
                        else:
                            pending.append((returns[-1], depth, returns[:-1]))
                    else:
                        pending.append((next_pc, depth, returns))
        self.assertLessEqual(budget_extra, 8)
        self.assertLessEqual(budget_return, 16)
        print(f'Static AP3 budgets (all branches): DS={budget_data}/16, '
              f'RS={budget_return}/16, extra DS={budget_extra}/8')

    def test_stack_words_and_full_stack_preservation(self):
        cases = {
            'DUP': ([7], [7, 7]), 'DROP': ([7], []),
            'SWAP': ([1, 2], [2, 1]), 'OVER': ([1, 2], [1, 2, 1]),
            'ROT': ([1, 2, 3], [2, 3, 1]), '-ROT': ([1, 2, 3], [3, 1, 2]),
            'NIP': ([1, 2], [2]), '2DUP': ([1, 2], [1, 2, 1, 2]),
            '2DROP': ([1, 2], []),
        }
        for word, (args, expected) in cases.items():
            for fill in range(9 - max(len(args), len(expected))):
                prefix = list(range(100, 100 + fill))
                self.check(word, prefix + args, prefix + expected)

    def test_arithmetic_comparisons_and_bits(self):
        values = [0, 1, 2, 0x7FFF, 0x8000, 0x8001, 0xFFFE, 0xFFFF]
        rng = random.Random(3103)
        pairs = [(a, b) for a in values for b in values]
        pairs += [(rng.randrange(65536), rng.randrange(65536)) for _ in range(50)]
        operations = {
            '+': lambda a, b: a + b, '-': lambda a, b: a - b,
            '*': lambda a, b: a * b, 'AND': lambda a, b: a & b,
            'OR': lambda a, b: a | b, 'XOR': lambda a, b: a ^ b,
            '<': lambda a, b: -int(signed(a) < signed(b)),
            '>': lambda a, b: -int(signed(a) > signed(b)),
            'U<': lambda a, b: -int(a < b), '=': lambda a, b: -int(a == b),
            '<>': lambda a, b: -int(a != b),
            'MIN': lambda a, b: min(signed(a), signed(b)),
            'MAX': lambda a, b: max(signed(a), signed(b)),
        }
        for a, b in pairs:
            for word, function in operations.items():
                prefix = [100, 101, 102, 103, 104, 105]  # Eight user cells at entry.
                self.check(word, prefix + [a, b], prefix + [function(a, b)])
        for a in values:
            unary = {'1+': a + 1, '1-': a - 1, 'NEGATE': -a,
                     'ABS': abs(signed(a)), '2*': a * 2, '2/': signed(a) // 2,
                     'INVERT': ~a, '0=': -int(a == 0), '0<>': -int(a != 0),
                     '0<': -int(signed(a) < 0), 'CELL+': a + 2, 'CELLS': a * 2}
            for word, expected in unary.items():
                self.check(word, [11] * 7 + [a], [11] * 7 + [expected])
            for n in range(16):
                self.check('LSHIFT', [11] * 6 + [a, n], [11] * 6 + [a << n])
                self.check('RSHIFT', [11] * 6 + [a, n], [11] * 6 + [a >> n])
        self.check('TRUE', [11] * 7, [11] * 7 + [65535])
        self.check('FALSE', [11] * 7, [11] * 7 + [0])

    def test_signed_division(self):
        values = [-32768, -32767, -257, -7, -1, 0, 1, 3, 7, 256, 32767]
        pairs = [(a, b) for a in values for b in values if b and (a, b) != (-32768, -1)]
        rng = random.Random(3104)
        pairs += [(rng.randrange(-32768, 32768), rng.choice([-1, 1]) * rng.randrange(1, 32768))
                  for _ in range(50)]
        for a, b in pairs:
            q = (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)
            r = a - q * b
            self.assertLess(abs(r), abs(b))
            for word, expected in (('/MOD', [r, q]), ('/', [q]), ('MOD', [r])):
                self.check(word, [9] * 6 + [a, b], [9] * 6 + expected)

    def test_memory_words_and_uart(self):
        for address in (0xD000, 0xD001):
            runner = Runner(self.image, [0xABCD, address])
            self.assertTrue(runner.call('!'))
            self.assertEqual(runner.memory.data[address:address + 3], b'\xcd\xab\x00')
            runner.cpu.dpush(address)
            runner.memory.write16(VARIABLES['depth'], 1)
            self.assertTrue(runner.call('@'))
            self.assertEqual(runner.values(), [0xABCD])
            runner = Runner(self.image, [0x1234, address])
            runner.memory.write16(address, 0xF000)
            self.assertTrue(runner.call('+!'))
            self.assertEqual(runner.memory.read16(address), 0x0234)
            self.assertEqual(runner.values(), [])
            runner = Runner(self.image, [0xABCD, address])
            runner.memory.data[address + 1] = 0xEF
            self.assertTrue(runner.call('C!'))
            self.assertEqual(runner.memory.data[address:address + 2], b'\xcd\xef')
            runner.cpu.dpush(address)
            runner.memory.write16(VARIABLES['depth'], 1)
            self.assertTrue(runner.call('C@'))
            self.assertEqual(runner.values(), [0xCD])
        for byte in (0, 65, 127):
            runner = Runner(self.image, [1] * 7, rx=[byte])
            self.assertTrue(runner.call('KEY'))
            self.assertEqual(runner.values(), [1] * 7 + [byte])
            self.assertEqual(runner.memory.consumed, 1)
            self.assertGreaterEqual(runner.memory.polls, 5)
            self.assertTrue(runner.call('EMIT'))
            self.assertEqual(runner.values(), [1] * 7)
            self.assertEqual(runner.memory.tx, [byte])
        runner = self.check('CR', [1] * 8, [1] * 8)
        self.assertEqual(runner.memory.tx, [13, 10])
        runner = self.check('SPACE', [1] * 8, [1] * 8)
        self.assertEqual(runner.memory.tx, [32])
        runner = self.check('EMIT', [0xE4], [])
        self.assertEqual(runner.memory.tx, [0x64])

    def assert_error(self, word, inputs, error):
        runner = Runner(self.image, inputs)
        runner.memory.data[0xD000:0xD004] = b'kept'
        here = runner.memory.read16(VARIABLES['here'])
        latest = runner.memory.read16(VARIABLES['latest'])
        self.assertFalse(runner.call(word))
        number, message = ERRORS[error]
        self.assertEqual(runner.memory.read16(VARIABLES['last_error']), number)
        self.assertEqual(runner.memory.read16(VARIABLES['depth']), 0)
        self.assertEqual(bytes(runner.memory.tx), f'error: {message}\r\n'.encode())
        self.assertEqual(runner.memory.data[0xD000:0xD004], b'kept')
        self.assertEqual(runner.memory.read16(VARIABLES['here']), here)
        self.assertEqual(runner.memory.read16(VARIABLES['latest']), latest)
        # Logical reset establishes a fresh stack base at current physical pointers.
        self.assertTrue(runner.call('TRUE'))
        self.assertEqual(runner.values(), [65535])

    def test_all_stack_guards_and_arithmetic_errors(self):
        for word in self.image.words:
            need, give = word['need'], word['give']
            for n in range(need):
                self.assert_error(word['name'], [0] * n, 'underflow')
            if give > need:
                for n in range(9 - (give - need), 9):
                    self.assert_error(word['name'], [0] * n, 'overflow')
        for word in ('LSHIFT', 'RSHIFT'):
            for count in (16, 17, 0x8000, 0xFFFF):
                self.assert_error(word, [123, count], 'shift')
        for word in ('/', 'MOD', '/MOD'):
            self.assert_error(word, [123, 0], 'division_zero')
            self.assert_error(word, [0x8000, 0xFFFF], 'division_overflow')

    def test_rtl_representative_programs(self):
        if not RTL:
            self.skipTest('enable CPU + physical SRAM + UART checks with --rtl')
        from support.config import Tools
        from support.paths import TIMINGS
        from support.sram import SramSimulation
        with tempfile.TemporaryDirectory(prefix='forth-primitives-rtl-') as directory:
            simulation = SramSimulation(directory, Tools(), with_uart=True)
            simulation.build()
            cases = [('*', [0xFFFF, 17], [0xFFEF]),
                     ('/MOD', [(-32768) & 65535, 7], [(-1) & 65535, (-4681) & 65535]),
                     ('2/', [0x8001], [0xC000]),
                     ('LSHIFT', [3, 15], [0x8000]),
                     ('ROT', [11, 22, 33], [22, 33, 11]),
                     ('EMIT', [65], []), ('CR', [], []),
                     ('/', [7, 0], None), ('DUP', [1] * 8, None)]
            for word, args, expected in cases:
                image = build_image()
                program = Image()
                start = image.symbols['user_start']
                program.org(start)
                for value in args:
                    program.push(value)
                program.push(len(args))
                program.push(VARIABLES['depth'])
                program.op(Op.STORE)
                metadata = next(w for w in image.words if w['name'] == word)
                program.push(image.symbols[metadata['xt']])
                program.op(Op.CALL)
                program.op(Op.BREAK)
                image.memory[start:program.pc] = program.memory[start:program.pc]
                idle = image.symbols['idle']
                image.memory[idle:idle + 4] = bytes([Op.PUSH, start & 255, start >> 8, Op.JP])
                image.memory[image.symbols['error_exit']] = Op.BREAK
                for timing in TIMINGS:
                    with self.subTest(word=word, timing=timing):
                        result = simulation.compare_image(image.memory, timing, max_steps=10000)
                        last = next(r for r in reversed(result.records) if r['kind'] == 'step')
                        if expected is not None:
                            self.assertEqual(last['ds'][:len(expected)], list(reversed(expected)))
                            self.assertEqual(last['rsp'], 0)
                        output = (b'A' if word == 'EMIT' else b'\r\n' if word == 'CR'
                                  else b'error: division by zero\r\n' if word == '/'
                                  else b'error: stack overflow\r\n' if word == 'DUP' else b'')
                        self.assertEqual(result.serial, output)
            print(f'PASS Forth primitives RTL: {len(cases)} programs x {len(TIMINGS)} timings')

    def test_rtl_key_waits_for_nul(self):
        if not RTL:
            self.skipTest('enable directed KEY + UART-buffer RTL test with --rtl')
        from support.process import run

        image = build_image()
        program = Image()
        start = image.symbols['user_start']
        program.org(start)
        word = next(w for w in image.words if w['name'] == 'KEY')
        program.push(image.symbols[word['xt']])
        program.op(Op.CALL)
        program.op(Op.BREAK)
        image.memory[start:program.pc] = program.memory[start:program.pc]
        idle = image.symbols['idle']
        image.memory[idle:idle + 4] = bytes([Op.PUSH, start & 255, start >> 8, Op.JP])
        with tempfile.TemporaryDirectory(prefix='forth-key-rtl-') as directory:
            directory = Path(directory)
            binary = directory / 'key'
            source = ROOT / 'forth/tests/tb_key.sv'
            # The shared source resolver intentionally only knows CPU/system
            # sources. Compile this Forth-owned testbench explicitly.
            run(['iverilog', '-g2012', '-s', 'tb_key', '-I', ROOT / 'cpu/rtl',
                 '-o', binary, source, ROOT / 'cpu/rtl/prim.v',
                 ROOT / 'debug_uart/rtl/uart_buffers.v'])
            hexfile = directory / 'image.hex'
            memory = bytes(image.memory) + bytes(16)
            hexfile.write_text(''.join(f'{byte:02x}\n' for byte in memory))
            result = run(['vvp', binary, f'+image={hexfile}'], cwd=directory)
            self.assertIn('PASS Forth KEY', result.stdout)

    @classmethod
    def tearDownClass(cls):
        print(f'Observed successful-word budgets: DS={cls.budget_data}/16, '
              f'RS={cls.budget_return}/16, extra DS={cls.budget_extra}/8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
