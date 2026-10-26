"""Shared SRAM test scenarios, reusable with and without UART mapping."""
from prim.assembler import PrimAsm
from prim.isa import PrimOpcodes as Op
from .cases import CASES
from .paths import TIMINGS


class SramScenarios:
    def test_controller_transactions_and_bus_timing(self):
        # All masks, aligned/odd/boundary addresses, adjacent-byte preservation,
        # 512 random transactions, continuous BS, reset, and idle bus release.
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                self.assertIn('PASS SRAM controller', self.run_simulator(timing))

    def test_cpu_baseline_programs(self):
        for timing in TIMINGS:
            for name, asm, _ in CASES:
                with self.subTest(timing=timing, case=name):
                    image = bytes(PrimAsm.assemble(asm) + [Op.BREAK])
                    self.compare_image(image, timing)

    def test_cpu_memory_boundaries(self):
        for timing in TIMINGS:
            for address in (0x1000, 0x1001, 0xfffd, 0xfffe, 0xffff):
                asm = (f'0x1234 {address} ! {address} @ '
                       f'0xabcd {address} c! {address} @ '
                       f'{address} c@ {(address+1)&65535} c@')
                with self.subTest(timing=timing, address=address):
                    self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), timing)

    def test_cpu_self_modifying_code(self):
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                self.compare_image(bytes(PrimAsm.assemble('7 9 c! nop nop nop 1') + [Op.BREAK]), timing)

    def test_cpu_memory_return(self):
        for timing in TIMINGS:
            for op in ('@', 'c@', '!', 'c!'):
                body = f'0xabcd 0x1001 {op}.ret 0xdead BREAK'
                target = len(PrimAsm.assemble(f'0 >r {body}'))
                image = bytes(PrimAsm.assemble(f'{target} >r {body}') + [Op.BREAK])
                with self.subTest(timing=timing, op=op):
                    self.compare_image(image, timing)
