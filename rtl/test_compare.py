#!/usr/bin/env python3
"""Instruction-by-instruction integration checks against the Python CPU."""

import argparse
import random
from pathlib import Path
import unittest

from compare import compare, Prim, Memory, PrimAsm, Op

parser = argparse.ArgumentParser()
parser.add_argument('--simulator', type=Path, required=True)
args, remaining = parser.parse_known_args()
SIMULATOR = args.simulator.resolve()


class ComparisonChecks(unittest.TestCase):
    def run_asm(self, asm, max_steps=1000):
        return compare(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), SIMULATOR, max_steps)

    def test_empty_program(self):
        self.assertEqual(self.run_asm(''), 0)

    def test_simend_marker(self):
        self.assertEqual(compare(bytes([Op.NOP, Op.SIMEND]), SIMULATOR), 1)

    def test_memory_wrapping_and_self_modifying_code(self):
        self.run_asm('0x1234 0xffff ! 0xffff @ 0xffff c@ 0 c@')
        # Replace the first byte of the following PUSH8 operand before fetching it.
        self.run_asm('7 9 c! nop nop nop 1')

    def test_loop_limit(self):
        with self.assertRaisesRegex(RuntimeError, 'limit|without a BREAK'):
            self.run_asm('0 jp', max_steps=5)

    def test_deep_stack(self):
        self.run_asm('1 2 over 3')

    def test_return_stack_transfer(self):
        self.run_asm('9 >r 1 2 r> 3')

    def test_stack_operations_at_every_depth(self):
        # Distinct values expose wrong ordering anywhere in the occupied stack.
        for depth in range(3, 17):
            prefix = ' '.join(str(0x100 + i) for i in range(depth))
            for op, delta in [('swap', 0), ('over', 1), ('dup', 1),
                              ('nip', -1), ('rot', 0), ('-rot', 0), ('drop', -1),
                              ('>r r>', 0), ('>r rdrop', -1)]:
                with self.subTest(depth=depth, op=op):
                    count = min(16, depth + delta)
                    self.run_asm(f'{prefix} {op} ' + 'drop ' * count)

    def test_data_stack_wraparound(self):
        # Cross the ring boundary repeatedly, then drain and reuse all cells.
        for count in (16, 17, 31, 32, 48):
            with self.subTest(pushes=count):
                prefix = ' '.join(str(i + 1) for i in range(count))
                refill = ' '.join(str(0x8000 + i) for i in range(16))
                self.run_asm(prefix + ' ' + 'drop ' * 16 + refill + ' ' + 'drop ' * 16)

    def test_stack_across_memory_and_branches(self):
        for depth in (3, 8, 16):
            prefix = ' '.join(str(0x100 + i) for i in range(depth))
            for suffix in ('0xabcd 0x1000 ! 0x1000 @ drop',
                           '0xab 0x1001 c! 0x1001 c@ drop', '1 0 jz'):
                with self.subTest(depth=depth, suffix=suffix):
                    self.run_asm(f'{prefix} {suffix}')
            target = len(PrimAsm.assemble(f'{prefix} 0 jp'))
            self.run_asm(f'{prefix} {target} jp 99')
            target = len(PrimAsm.assemble(f'{prefix} 0 call BREAK'))
            self.run_asm(f'{prefix} {target} call BREAK 42.ret')

    def test_mixed_stack_sequences(self):
        # Fixed seeds make failures reproducible; avoid underflow and RS overflow.
        for seed in range(20):
            rng = random.Random(seed)
            ds = rs = 0
            program = []
            for _ in range(200):
                choices = [('push', 1, 0), ('carry', 1, 0), ('nop', 0, 0)]
                if ds:
                    choices += [('dup', 1, 0), ('drop', -1, 0), ('not', 0, 0),
                                ('sr', 0, 0), ('sl', 0, 0)]
                    if rs < 14:
                        choices += [('>r', -1, 1)]
                if ds >= 2:
                    choices += [('swap', 0, 0), ('over', 1, 0), ('nip', -1, 0),
                                ('+', -1, 0), ('xor', -1, 0)]
                if ds >= 3:
                    choices += [('rot', 0, 0), ('-rot', 0, 0)]
                if rs:
                    choices += [('r>', 1, -1), ('rdrop', 0, -1)]
                op, dd, rd = rng.choice(choices)
                program.append(str(rng.randrange(65536)) if op == 'push' else op)
                ds, rs = min(16, ds + dd), rs + rd
            program += ['drop'] * ds + ['rdrop'] * rs
            with self.subTest(seed=seed):
                self.run_asm(' '.join(program))

    def test_return_bit_control_flow_exceptions(self):
        for asm in ('5 call.ret BREAK nop 2.ret',
                    '4 jp.ret BREAK 0xff',
                    '0 6 jz.ret BREAK 0xfe', '1 6 jz.ret BREAK 0xfe',
                    'int.ret BREAK nop nop 2.ret'):
            with self.subTest(asm=asm):
                self.run_asm(asm)

    def test_return_after_regular_operations(self):
        operations = ('nop and or xor not sr srw sl slw + - < <u swap over '
                      'dup nip rot -rot drop carry @ c@ ! c! 7 0x1234').split()
        for op in operations:
            # The fall-through path must not run; return skips it to BREAK.
            body = f'0xaaaa 0xbbbb 0x1000 {op}.ret 0xdead BREAK'
            target = len(PrimAsm.assemble(f'0 >r {body}'))
            with self.subTest(op=op):
                self.run_asm(f'{target} >r {body}')

    def test_return_after_return_stack_operations(self):
        for asm in ('9 >r 7 >r.ret BREAK nop nop BREAK',
                    '8 >r 0x1234 >r r>.ret BREAK',
                    '7 >r 0x55 >r rdrop.ret BREAK'):
            with self.subTest(asm=asm):
                self.run_asm(asm)

    def test_return_stack_wraparound(self):
        for count in (16, 17, 31, 32, 48):
            prefix = ' '.join(f'{i + 1} >r' for i in range(count))
            with self.subTest(pushes=count):
                self.run_asm(prefix + ' ' + 'r> drop ' * 16)

    def test_to_r_return_at_ring_boundary(self):
        for count in (0, 1, 14, 15, 16, 17, 31, 32):
            prefix = ' '.join(f'{i + 1} >r' for i in range(count))
            target = len(PrimAsm.assemble(f'{prefix} 0 >r.ret 0xdead BREAK'))
            remaining = min(count, 15)
            with self.subTest(pushes=count):
                self.run_asm(f'{prefix} {target} >r.ret 0xdead BREAK ' +
                             'r> drop ' * remaining)

    def test_double_return_pop_at_ring_boundary(self):
        prefix = ' '.join(f'{i + 1} >r' for i in range(14))
        for op in ('r>', 'rdrop'):
            body = f'0x1234 >r {op}.ret 0xdead BREAK'
            target = len(PrimAsm.assemble(f'{prefix} 0 >r {body}'))
            with self.subTest(op=op):
                self.run_asm(f'{prefix} {target} >r {body} ' + 'rdrop ' * 14)

    def test_nested_calls(self):
        for depth in (1, 2, 15, 16):
            program = ['4 call BREAK']
            program += [f'{8 + 4*i} call nop.ret' for i in range(depth - 1)]
            program += ['42.ret']
            with self.subTest(depth=depth):
                self.run_asm(' '.join(program))

    def test_call_return_address_wraparound(self):
        image = bytearray([Op.SIMEND]) * 65536
        main = bytes(PrimAsm.assemble('0x100 0x22 0 c! 0xffff jp'))
        image[:len(main)] = main
        image[0x100:0x102] = bytes(PrimAsm.assemble('7.ret'))
        image[0xffff] = Op.CALL
        compare(image, SIMULATOR)

    def check_alu(self, asm, result, carry):
        # Check an independent arithmetic expectation as well as Python/RTL
        # agreement, so a shared bug cannot make this test pass unnoticed.
        image = bytes(PrimAsm.assemble(asm + ' carry') + [Op.BREAK])
        cpu = Prim(Memory(image))
        for _ in range(30):
            if cpu.step() == Op.BREAK:
                break
        else:
            self.fail('ALU fixture did not halt')
        self.assertEqual((cpu.N(), cpu.T(), cpu._dsp), (result, carry, 2))
        compare(image, SIMULATOR)

    def test_alu_binary_boundaries(self):
        values = (0, 1, 2, 0xff, 0x100, 0x7fff, 0x8000, 0xfffe, 0xffff)
        for a in values:
            for b in values:
                signed_a = a if a < 0x8000 else a - 0x10000
                signed_b = b if b < 0x8000 else b - 0x10000
                cases = [('+', (a + b) & 0xffff, int(a + b > 0xffff)),
                         ('-', (a - b) & 0xffff, int(a < b)),
                         ('and', a & b, 1), ('or', a | b, 1),
                         ('xor', a ^ b, 1),
                         ('<', 0xffff if signed_a < signed_b else 0, 1),
                         ('<u', 0xffff if a < b else 0, 1)]
                for op, result, carry in cases:
                    with self.subTest(a=a, b=b, op=op):
                        self.check_alu(f'1 sr drop {a} {b} {op}', result, carry)

    def test_alu_not_preserves_carry(self):
        for value in (0, 1, 0x7fff, 0x8000, 0xffff):
            for carry in (0, 1):
                with self.subTest(value=value, carry=carry):
                    self.check_alu(f'{carry} sr drop {value} not',
                                   value ^ 0xffff, carry)

    def test_alu_shifts(self):
        # Single-bit operands isolate the carry tap, especially SRW/SLW.
        values = (0, 0xffff, *(1 << i for i in range(16)))
        for value in values:
            cases = [('sr', value >> 1, value & 1),
                     ('srw', value >> 8, (value >> 7) & 1),
                     ('sl', (value << 1) & 0xffff, (value >> 15) & 1),
                     ('slw', (value << 8) & 0xffff, (value >> 8) & 1)]
            for op, result, carry in cases:
                for initial in (0, 1):
                    with self.subTest(value=value, op=op, initial=initial):
                        self.check_alu(f'{initial} sr drop {value} {op}', result, carry)

    def test_alu_binary_preserves_zero_carry(self):
        for op, result in [('and', 1), ('or', 3), ('xor', 2),
                           ('<', 0), ('<u', 0)]:
            with self.subTest(op=op):
                self.check_alu(f'0 sr drop 3 1 {op}', result, 0)

    def test_carry_preservation(self):
        # Exercise instructions which must leave carry untouched, including
        # memory, stack transfers, control flow, and return-bit execution.
        for carry in (0, 1):
            prefix = f'{carry} sr drop'
            program = f'{prefix} 0x1234 dup swap over rot -rot nip >r r> '
            program += '0x1000 ! 0x1000 @ 0x1000 c@ drop drop 9 >r rdrop carry'
            self.run_asm(program)
            self.check_alu(f'{prefix} 0x1234 dup >r r> drop', 0x1234, carry)
            target = len(PrimAsm.assemble(f'{prefix} 0 call BREAK'))
            self.run_asm(f'{prefix} {target} call BREAK 0x1234.ret')


if __name__ == '__main__':
    unittest.main(argv=[__file__, *remaining])
