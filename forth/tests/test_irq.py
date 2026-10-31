"""Kernel dispatcher tests including carry/stack preservation under real IRQ entry."""
import unittest
from dual_support import DualRunner
from forth.image import Image
from prim.isa import PrimOpcodes as Op


class InterruptChecks(unittest.TestCase):
    def test_every_wait_boundary_and_return_handoff(self):
        for offset in range(3):  # Before INTEI, NOP and INTDI respectively.
            for carry in (0, 1):
                r = DualRunner()
                r.cpu._carry = carry
                original = r.step
                sent = False

                def step():
                    nonlocal sent
                    if r.cpu._pc == r.image.symbols['irq_wait'] + offset and not sent:
                        sent = True
                        r.memory.receive_uart(65)
                        r.memory.receive_ps2(0x1C)
                    original()
                r.step = step
                values = list(range(101, 109))
                r.invoke('irq_wait', values)
                self.assertEqual(int(r.cpu._carry), carry)
                # Event coinciding with INTDI is retained until the next window.
                r.invoke('irq_wait')
                self.assertEqual((r.memory.read16(0xF102), r.memory.read16(0xF182)), (1, 1))
                self.assertEqual([r.cpu._ds[(r.cpu._dsp - 7 + i) % 16] for i in range(8)], values)
                self.assertFalse(r.cpu._int_enable)
                self.assertLessEqual(r.max_data, 12)
                self.assertLessEqual(r.max_frames, 5)

        r = DualRunner()
        r.cpu._carry = 1
        r.memory.receive_uart(65)
        original = r.step
        sent = False

        def handoff():
            nonlocal sent
            if r.cpu._pc == r.image.symbols['irq_service'] - 1 and not sent:
                sent = True
                r.memory.receive_uart(66)  # New event at ISR's INTEI.RET.
            original()
        r.step = handoff
        r.invoke('irq_wait', list(range(8)))
        self.assertTrue(sent)
        self.assertEqual(r.memory.data[0xF106:0xF108], b'AB')
        self.assertEqual(int(r.cpu._carry), 1)

    def test_boot_and_simultaneous_sources(self):
        r = DualRunner()
        self.assertFalse(r.cpu._int_enable)
        self.assertEqual(r.cpu._int_addr, r.image.symbols['irq_entry'])
        self.assertEqual((r.memory.uart_ie, r.memory.ps2_ie), (4, 4))
        r.memory.receive_uart(65)
        for byte in (0x12, 0x1C, 0xF0):
            r.memory.receive_ps2(byte)
        r.invoke('irq_service')
        self.assertEqual(r.memory.pending, 0)
        self.assertEqual(r.memory.read16(0xF102), 1)
        self.assertEqual(r.memory.data[0xF106], 65)
        self.assertEqual(r.memory.read16(0xF182), 3)
        self.assertEqual(r.memory.data[0xF186:0xF189], bytes([0x12, 0x1C, 0xF0]))
        self.assertFalse(r.memory.tx)

    def test_irq_preserves_eight_user_cells_carry_and_scratch(self):
        for carry in (0, 1):
            r = DualRunner()
            values = [0x1234 + i for i in range(8)]
            for value in values:
                r.cpu.dpush(value)
                r.physical += 1
            r.set('depth', 8)
            r.memory.data[0x380:0x400] = b'\xa5' * 128
            r.cpu._carry = carry
            code = Image()
            code.org(0xFF80)
            code.op(Op.INTEI)
            code.op(Op.NOP)
            code.op(Op.INTDI)
            code.op(Op.BREAK)
            r.memory.data[0xFF80:code.pc] = code.memory[0xFF80:code.pc]
            r.cpu._pc = 0xFF80
            r.memory.receive_uart(0x7F)
            r.memory.receive_ps2(0x5A)
            r.until(lambda: r.memory.data[r.cpu._pc] == Op.BREAK)
            self.assertEqual(int(r.cpu._carry), carry)
            self.assertEqual([r.cpu._ds[(r.cpu._dsp - 7 + i) % 16] for i in range(8)], values)
            self.assertEqual(r.memory.data[0x380:0x400], b'\xa5' * 128)
            self.assertEqual((r.physical, r.frames, r.cpu._rsp), (8, 0, 0))
            self.assertLessEqual(r.max_data, 12)
            self.assertLessEqual(r.max_frames, 4)
            self.assertEqual(r.memory.pending, 0)

    def test_ring_wrap_overflow_and_receive_errors(self):
        r = DualRunner()
        for byte in range(70):
            r.memory.receive_uart(byte)
            r.invoke('irq_service')
        self.assertEqual(r.memory.read16(0xF102), 63)
        self.assertEqual(r.memory.read16(0xF104), 1)
        self.assertEqual(r.memory.data[0xF106:0xF145], bytes(range(63)))
        r.memory.write16(0xF100, 32)  # Foreground consumes first 32 bytes.
        for byte in range(70, 90):
            r.memory.receive_uart(byte)
            r.invoke('irq_service')
        self.assertEqual(r.memory.read16(0xF102), 19)
        self.assertEqual(r.memory.data[0xF106:0xF106 + 19], bytes(range(71, 90)))
        r.memory.ps2_errors = 24
        r.memory.event(8)
        r.invoke('irq_service')
        self.assertEqual(r.memory.read16(0xF184), 1)
        self.assertEqual((r.memory.ps2_errors, r.memory.ps2_ie), (0, 4))

    def test_event_during_handler_and_unhandled_sources(self):
        r = DualRunner()
        r.memory.receive_uart(65)
        original = r.memory.write8
        sent = False

        def write(address, value):
            nonlocal sent
            original(address, value)
            if address == 0xFFF5 and value == 2 and not sent:
                sent = True
                r.memory.receive_ps2(0x1C)
        r.memory.write8 = write
        r.invoke('irq_service')
        self.assertEqual(r.memory.pending, 0)
        self.assertEqual(r.memory.read16(0xF182), 1)
        # Timer/TX sources are intentionally not used by the console. Their
        # safe default handlers mask them and report a private diagnostic.
        r.memory.timer[4] = 4
        r.memory.uart_ie = 12
        r.memory.pending = 5
        r.invoke('irq_service')
        self.assertEqual(r.get('irq_diagnostic'), 5)
        self.assertEqual((r.memory.timer[4] & 4, r.memory.uart_ie & 8), (0, 0))
        r.memory.uart_ie = 0
        r.memory.pending = 2
        r.invoke('irq_service')
        self.assertEqual(r.memory.pending, 2)  # Masked identity is retained.


if __name__ == '__main__':
    from dual_support import run_tests
    run_tests()
