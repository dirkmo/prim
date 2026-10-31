"""Kernel dispatcher tests including carry/stack preservation under real IRQ entry."""
import unittest
from dual_support import DualRunner
from forth.image import Image
from prim.isa import PrimOpcodes as Op


class InterruptChecks(unittest.TestCase):
    def test_foreground_boundaries_and_return_handoff(self):
        for boundary in (0xFF80, 0xFF83, None):  # PUSH, CALL, callee return.
            for carry in (0, 1):
                r = DualRunner()
                r.cpu._carry = carry
                original = r.step
                sent = False

                def step():
                    nonlocal sent
                    if r.cpu._pc == (r.image.symbols['irq_wait'] if boundary is None else boundary) and not sent:
                        sent = True
                        r.memory.receive_uart(65)
                        r.memory.receive_ps2(0x1C)
                    original()
                r.step = step
                values = list(range(101, 109))
                r.invoke('irq_wait', values)
                self.assertEqual(int(r.cpu._carry), carry)
                r.invoke('irq_wait')
                self.assertEqual((r.memory.read16(0xF102), r.memory.read16(0xF182)), (1, 1))
                self.assertEqual([r.cpu._ds[(r.cpu._dsp - 7 + i) % 32] for i in range(8)], values)
                self.assertTrue(r.cpu._int_enable)
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

    def test_interrupt_at_every_instruction_of_division_and_banked_output(self):
        # Inject after every possible foreground instruction in separate runs.
        # Compare all arithmetic scratch and cached/array stack cells as well as
        # results, carry, output and bank restoration against an uninterrupted run.
        for name, values, local in (('/MOD', [11, 22, 33, 44, 55, 66, 32767, 17], False),
                                    ('raw_emit', [11, 22, 33, 44, 55, 66, 77, 65], True)):
            def fixture():
                r = DualRunner()
                r.set('console_owner', int(local))
                r.set('depth', len(values))
                r.memory.video[0] = 0x1E
                r.memory.data[0xE000:0xE004] = b'kept'
                return r

            baseline = fixture()
            target = next((w['xt'] for w in baseline.image.words if w['name'] == name), name)
            count = 0
            original = baseline.step

            def count_step():
                nonlocal count
                count += 1
                original()
            baseline.step = count_step
            baseline.invoke(target, values)
            peak_data = peak_frames = 0
            for boundary in range(count):
                with self.subTest(word=name, boundary=boundary):
                    r = fixture()
                    tick = 0
                    original_step = r.step

                    def inject():
                        nonlocal tick
                        if tick == boundary:
                            r.memory.receive_uart(90)
                            r.memory.receive_ps2(0x1C)
                        tick += 1
                        original_step()
                    r.step = inject
                    r.invoke(target, values)
                    peak_data = max(peak_data, r.max_data)
                    peak_frames = max(peak_frames, r.max_frames)
                    self.assertGreater(r.irq_entries, 0)
                    self.assertTrue(r.cpu._int_enable)
                    self.assertFalse(r.in_isr)
                    self.assertEqual((r.cpu._dsp, r.cpu._rsp, int(r.cpu._carry)),
                                     (baseline.cpu._dsp, baseline.cpu._rsp, int(baseline.cpu._carry)))
                    self.assertEqual(r.cpu._ds, baseline.cpu._ds)
                    self.assertEqual(r.memory.data[0x100:0x400], baseline.memory.data[0x100:0x400])
                    self.assertEqual(r.memory.video, baseline.memory.video)
                    self.assertEqual(r.memory.vram, baseline.memory.vram)
                    self.assertEqual(r.memory.data[0xE000:0xE004], b'kept')
                    self.assertEqual((r.memory.data[0xF106], r.memory.data[0xF186]), (90, 0x1C))
            print(f'Async IRQ boundaries: {name} {count}; DS peak={peak_data}, RS peak={peak_frames}')

    def test_receive_during_each_masked_loss_recovery_instruction(self):
        def fixture():
            r = DualRunner()
            r.set('poll_source', 1)
            r.invoke('source_select')
            r.memory.write16(0xF182, 3)
            r.memory.write16(0xF184, 1)
            return r

        baseline = fixture()
        masked_pcs = []
        original = baseline.step

        def trace():
            if not baseline.cpu._int_enable:
                masked_pcs.append(baseline.cpu._pc)
            original()
        baseline.step = trace
        baseline.invoke('source_recover')
        self.assertTrue(masked_pcs)
        for boundary in masked_pcs:
            with self.subTest(pc=boundary):
                r = fixture()
                original_step = r.step
                sent = False

                def inject():
                    nonlocal sent
                    if r.cpu._pc == boundary and not sent:
                        sent = True
                        r.memory.receive_ps2(0x1C)
                    original_step()
                r.step = inject
                r.invoke('source_recover')
                self.assertTrue(sent)
                self.assertTrue(r.cpu._int_enable)
                self.assertEqual(r.get('input_failed'), 1)
                self.assertEqual((r.memory.read16(0xF180), r.memory.read16(0xF182),
                                  r.memory.read16(0xF184)), (3, 4, 0))
                self.assertEqual(r.memory.data[0xF189], 0x1C)

    def test_boot_and_simultaneous_sources(self):
        r = DualRunner()
        self.assertTrue(r.cpu._int_enable)
        self.assertEqual(r.cpu._int_addr, r.image.symbols['irq_entry'])
        self.assertEqual((r.memory.uart_ie, r.memory.ps2_ie), (4, 4))
        r.memory.receive_uart(65)
        for byte in (0x12, 0x1C, 0xF0):
            r.memory.receive_ps2(byte)
        r.cpu.request_irq()
        r.invoke('irq_wait')
        self.assertEqual(r.memory.pending, 0)
        self.assertEqual(r.memory.read16(0xF102), 1)
        self.assertEqual(r.memory.data[0xF106], 65)
        self.assertEqual(r.memory.read16(0xF182), 3)
        self.assertEqual(r.memory.data[0xF186:0xF189], bytes([0x12, 0x1C, 0xF0]))
        self.assertFalse(r.memory.tx)

    def test_irq_with_data_and_return_stacks_beyond_sixteen_cells(self):
        r = DualRunner()
        code = Image()
        code.org(0x8000)
        for _ in range(22):
            code.push(code.pc + 5)
            code.op(Op.CALL)
            code.op(Op.NOP | 128)
        leaf = code.pc
        code.op(Op.NOP | 128)
        r.memory.data[0x8000:code.pc] = code.memory[0x8000:code.pc]
        r.image.define('deep_fixture', 0x8000)
        original = r.step

        def step():
            if r.cpu._pc == leaf:
                r.memory.receive_uart(65)
                r.memory.receive_ps2(0x1C)
            original()
        r.step = step
        values = list(range(100, 124))
        r.invoke('deep_fixture', values)
        self.assertEqual([r.cpu._ds[(r.cpu._dsp - 23 + i) % 32] for i in range(24)], values)
        self.assertEqual((r.physical, r.frames), (24, 0))
        self.assertGreater(r.max_data, 24)
        self.assertGreater(r.max_frames, 23)
        self.assertEqual(r.memory.pending, 0)
        self.assertTrue(r.cpu._int_enable)

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
            self.assertEqual([r.cpu._ds[(r.cpu._dsp - 7 + i) % 32] for i in range(8)], values)
            self.assertEqual(r.memory.data[0x380:0x400], b'\xa5' * 128)
            self.assertEqual((r.physical, r.frames, r.cpu._rsp), (8, 0, 0))
            self.assertLessEqual(r.max_data, 12)
            self.assertLessEqual(r.max_frames, 4)
            self.assertEqual(r.memory.pending, 0)

    def test_ring_wrap_overflow_and_receive_errors(self):
        r = DualRunner()
        for byte in range(70):
            r.memory.receive_uart(byte)
            r.cpu.request_irq()
            r.invoke('irq_wait')
        self.assertEqual(r.memory.read16(0xF102), 63)
        self.assertEqual(r.memory.read16(0xF104), 1)
        self.assertEqual(r.memory.data[0xF106:0xF145], bytes(range(63)))
        r.memory.write16(0xF100, 32)  # Foreground consumes first 32 bytes.
        for byte in range(70, 90):
            r.memory.receive_uart(byte)
            r.cpu.request_irq()
            r.invoke('irq_wait')
        self.assertEqual(r.memory.read16(0xF102), 19)
        self.assertEqual(r.memory.data[0xF106:0xF106 + 19], bytes(range(71, 90)))
        r.memory.ps2_errors = 24
        r.memory.event(8)
        r.cpu.request_irq()
        r.invoke('irq_wait')
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
        r.cpu.request_irq()
        r.invoke('irq_wait')
        self.assertEqual(r.memory.pending, 0)
        self.assertEqual(r.memory.read16(0xF182), 1)
        # Timer/TX sources are intentionally not used by the console. Their
        # safe default handlers mask them and report a private diagnostic.
        r.memory.timer[4] = 4
        r.memory.uart_ie = 12
        r.memory.pending = 5
        r.cpu.request_irq()
        r.invoke('irq_wait')
        self.assertEqual(r.get('irq_diagnostic'), 5)
        self.assertEqual((r.memory.timer[4] & 4, r.memory.uart_ie & 8), (0, 0))
        r.memory.uart_ie = 0
        r.memory.pending = 2
        r.cpu.request_irq()
        r.invoke('irq_wait')
        self.assertEqual(r.memory.pending, 2)  # Masked identity is retained.


if __name__ == '__main__':
    from dual_support import run_tests
    run_tests()
