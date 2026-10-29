"""Architectural interrupt behavior in the instruction-level Python CPU."""
import unittest

from prim.assembler import PrimAsm
from prim.compiler import Mif
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op


class InterruptChecks(unittest.TestCase):
    def cpu(self, main='128 intad intei nop BREAK', isr='intdi intei.ret'):
        memory = bytearray(65536)
        code = PrimAsm.assemble(main)
        memory[:len(code)] = bytes(code)
        code = PrimAsm.assemble(isr)
        memory[128:128+len(code)] = bytes(code)
        return Prim(Mif(memory))

    def test_masked_request_and_first_isr_instruction(self):
        cpu = self.cpu()
        cpu.request_irq()
        cpu.request_irq()  # coalesced
        cpu.step()
        cpu.step()
        self.assertEqual((cpu._pc, cpu._dsp, cpu._int_addr), (3, 0, 128))
        cpu.step()  # INTEI accepts the pending request immediately
        self.assertEqual((cpu._pc, cpu.R(), cpu._rsp), (128, 4, 1))
        cpu.request_irq()
        cpu.step()  # first ISR instruction is allowed to disable interrupts
        self.assertFalse(cpu._int_enable)
        self.assertEqual((cpu._pc, cpu._rsp), (129, 1))
        cpu.step()  # INTEI.RET completes the return before re-entry
        self.assertEqual((cpu._pc, cpu.R(), cpu._rsp), (128, 4, 1))
        cpu.step()
        cpu.step()
        self.assertEqual((cpu._pc, cpu._rsp), (4, 0))

    def test_software_int_uses_vector_while_disabled(self):
        cpu = self.cpu('128 intad 85 int BREAK', '2.ret')
        for _ in range(4):
            cpu.step()
        self.assertEqual((cpu._pc, cpu.R(), cpu.T(), cpu._int_enable), (128, 6, 85, False))
        cpu.step()
        self.assertEqual((cpu._pc, cpu.T(), cpu.N(), cpu._rsp), (6, 2, 85, 0))

    def test_intdi_blocks_request_at_its_boundary(self):
        cpu = self.cpu('128 intad intei intdi intei BREAK')
        for _ in range(3):
            cpu.step()
        cpu.request_irq()
        cpu.step()
        self.assertEqual((cpu._pc, cpu._rsp, cpu._irq_pending), (5, 0, True))
        cpu.step()
        self.assertEqual((cpu._pc, cpu.R()), (128, 6))

    def test_nested_interrupt(self):
        cpu = self.cpu(isr='nop intdi intei.ret')
        for _ in range(3):
            cpu.step()
        cpu.request_irq()
        cpu.step()
        cpu.request_irq()
        cpu.step()
        self.assertEqual((cpu._pc, cpu.R(), cpu._rsp), (128, 129, 2))
        for _ in range(5):
            cpu.step()
        self.assertEqual((cpu._pc, cpu._rsp), (5, 0))

    def test_break_keeps_request_and_reset_clears_all_state(self):
        cpu = self.cpu('128 intad intei BREAK')
        for _ in range(3):
            cpu.step()
        cpu.request_irq()
        self.assertEqual(cpu.step(), Op.BREAK)
        self.assertEqual((cpu._pc, cpu._rsp, cpu._irq_pending), (5, 0, True))
        cpu.reset()
        self.assertEqual((cpu._int_enable, cpu._int_addr, cpu._irq_pending), (False, 0, False))

    def test_new_mnemonics_round_trip(self):
        self.assertEqual(PrimAsm.assemble('intei intdi intad intei.ret'), [0x23, 0x24, 0x25, 0xa3])
        for name in ('INTEI', 'INTDI', 'INTAD'):
            opcode = PrimAsm.assemble(name + '.RET')[0]
            self.assertEqual(PrimAsm.disassembleOpcode(opcode), name + '.RET')


if __name__ == '__main__':
    unittest.main()
