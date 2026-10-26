#!/usr/bin/env python3
"""Memory handshake regressions with fixed and reproducible random latency."""

import unittest

from prim.assembler import PrimAsm
from prim.isa import PrimOpcodes as Op
from sim_support.verilator import compare
from sim_support.cases import CASES

from sim_support.config import run_tests
from sim_support.unittest_bridge import VerilatorHarness


class MemoryChecks(VerilatorHarness, unittest.TestCase):
    def run_asm(self, asm, waits, seed=None):
        return compare(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), self.simulator,
                       wait_cycles=waits, wait_seed=seed)

    def test_existing_programs_with_waits(self):
        for waits, seed in ((1, None), (3, None), (8, None), (7, 0), (7, 12345)):
            for name, asm, _ in CASES:
                with self.subTest(case=name, waits=waits, seed=seed):
                    self.run_asm(asm, waits, seed)

    def test_unaligned_and_wrapped_memory(self):
        for address in (0x1000, 0x1001, 0xfffd, 0xfffe, 0xffff):
            program = (f'0x1234 {address} ! {address} @ drop '
                       f'{address} c@ drop {((address + 1) & 0xffff)} c@ drop '
                       f'0xabcd {address} c! {address} @')
            for waits, seed in ((0, None), (4, None), (9, 42)):
                with self.subTest(address=address, waits=waits, seed=seed):
                    self.run_asm(program, waits, seed)

    def test_repeated_access_to_same_address(self):
        self.run_asm('0xab 0x1000 c! 0xcd 0x1000 c! '
                     '0x1000 c@ 0x1000 c@ 0x1234 0x1000 ! 0x1000 @', 11)

    def test_self_modifying_code(self):
        for waits, seed in ((5, None), (11, 99)):
            with self.subTest(waits=waits, seed=seed):
                self.run_asm('7 9 c! nop nop nop 1', waits, seed)

    def test_memory_operations_with_return(self):
        for op in ('@', 'c@', '!', 'c!', '7', '0x1234'):
            body = f'0xabcd 0x1001 {op}.ret 0xdead BREAK'
            target = len(PrimAsm.assemble(f'0 >r {body}'))
            for waits, seed in ((6, None), (13, 7)):
                with self.subTest(op=op, waits=waits, seed=seed):
                    self.run_asm(f'{target} >r {body}', waits, seed)

    def test_long_stalls(self):
        self.run_asm('0xbeef 0x1001 ! 0x1001 @', 257)


if __name__ == '__main__':
    run_tests(MemoryChecks, simulator=True)
