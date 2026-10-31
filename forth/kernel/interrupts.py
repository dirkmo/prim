"""One non-nesting source dispatcher and bounded SRAM receive rings."""
from prim.isa import PrimOpcodes as Op
from forth.kernel.primitives import Code
from forth.kernel.io import set_cell

IRQ_NAMES = ('irq_carry', 'irq_snapshot', 'irq_progress', 'irq_base',
             'irq_byte', 'irq_next', 'irq_tail', 'irq_diagnostic')
IRQ_VARIABLES = {name: 0xF020 + 2 * n for n, name in enumerate(IRQ_NAMES)}
RINGS = {'uart': 0xF100, 'ps2': 0xF180}
RING_SIZE = 64  # One slot stays empty: 63 bytes usable per source.


def emit_interrupts(image):
    c = Code(image)
    c.mark('irq_wait')
    # Collector rendezvous; IRQs also remain enabled during Forth execution.
    c.ops(Op.NOP | 128)
    c.mark('irq_init')
    c.ops(Op.INTDI)
    # CPU-only reset retains peripherals: discard input before enabling sources.
    for address, value in ((0xFFFE, 0), (0xFFF4, 0), (0xFFFB, 24)):
        c.push(value)
        c.push(address)
        c.ops(Op.BYTE_STORE)
    for csr, data in ((0xFFFE, 0xFFFF), (0xFFFB, 0xFFFC)):
        loop, done = c.label('boot_drain'), c.label('boot_drained')
        c.mark(loop)
        c.push(csr)
        c.ops(Op.BYTE_FETCH)
        c.push(1)
        c.ops(Op.AND)
        c.jz(done)
        c.push(data)
        c.ops(Op.BYTE_FETCH, Op.DROP)
        c.jump(loop)
        c.mark(done)
    c.push(24)
    c.push(0xFFFB)
    c.ops(Op.BYTE_STORE)
    for base in RINGS.values():
        for offset in (0, 2, 4):  # head, tail, loss flag
            c.push(0)
            c.push(base + offset)
            c.ops(Op.STORE)
    c.push(15)
    c.push(0xFFF5)
    c.ops(Op.BYTE_STORE)
    c.push('irq_entry')
    c.ops(Op.INTAD)
    for address in (0xFFFE, 0xFFFB):
        c.push(4)
        c.push(address)
        c.ops(Op.BYTE_STORE)
    c.ops(Op.INTEI | 128)  # Vector, rings and source enables are now initialized.

    c.mark('irq_entry')
    c.ops(Op.INTDI, Op.CARRY)
    c.store('irq_carry')
    c.call('irq_service')
    # ADD sets carry iff the saved bit is 1; no later operation changes it.
    c.load('irq_carry')
    c.push(0xFFFF)
    c.ops(Op.ADD, Op.DROP, Op.INTEI | 128)

    # ISR-private: foreground code must not reenter the shared IRQ scratch.
    c.mark('irq_service')
    scan, done = c.label('irq_rescan'), c.label('irq_done')
    c.mark(scan)
    set_cell(c, 'irq_progress', 0)
    c.push(0xFFF5)
    c.ops(Op.BYTE_FETCH)
    c.store('irq_snapshot')
    for bit, csr, enable, handler in (
            (1, 0xFFF4, 4, 'irq_timer'), (2, 0xFFFE, 4, 'irq_uart'),
            (4, 0xFFFE, 8, 'irq_tx'), (8, 0xFFFB, 4, 'irq_ps2')):
        skip = c.label('irq_skip')
        c.load('irq_snapshot')
        c.push(bit)
        c.ops(Op.AND)
        c.jz(skip)
        c.push(csr)
        c.ops(Op.BYTE_FETCH)
        c.push(enable)
        c.ops(Op.AND)
        c.jz(skip)  # Disabled source identity remains pending.
        c.push(bit)
        c.push(0xFFF5)
        c.ops(Op.BYTE_STORE)  # Acknowledge snapshot BEFORE the handler.
        set_cell(c, 'irq_progress', 1)
        c.call(handler)
        c.mark(skip)
    c.load('irq_progress')
    c.jz(done)
    c.jump(scan)
    c.mark(done)
    c.ops(Op.NOP | 128)

    # Unused event sources have safe handlers: mask and record, never spin.
    for handler, address, mask, bit in (('irq_timer', 0xFFF4, 3, 1),
                                        ('irq_tx', 0xFFFE, 4, 4)):
        c.mark(handler)
        c.push(address)
        c.ops(Op.BYTE_FETCH)
        c.push(mask)
        c.ops(Op.AND)
        c.push(address)
        c.ops(Op.BYTE_STORE)
        c.load('irq_diagnostic')
        c.push(bit)
        c.ops(Op.OR)
        c.store('irq_diagnostic')
        c.ops(Op.NOP | 128)

    for name, csr, data in (('uart', 0xFFFE, 0xFFFF), ('ps2', 0xFFFB, 0xFFFC)):
        c.mark('irq_' + name)
        set_cell(c, 'irq_base', RINGS[name])
        if name == 'ps2':
            no_error = c.label('irq_ps2_no_error')
            c.push(csr)
            c.ops(Op.BYTE_FETCH)
            c.push(24)
            c.ops(Op.AND)
            c.jz(no_error)
            c.push(1)
            c.push(RINGS[name] + 4)
            c.ops(Op.STORE)
            c.push(28)
            c.push(csr)
            c.ops(Op.BYTE_STORE)
            c.mark(no_error)
        loop, finish = c.label('irq_drain'), c.label('irq_drained')
        c.mark(loop)
        c.push(csr)
        c.ops(Op.BYTE_FETCH)
        c.push(1)
        c.ops(Op.AND)
        c.jz(finish)
        c.push(data)
        c.ops(Op.BYTE_FETCH)
        c.store('irq_byte')
        c.call('irq_enqueue')
        c.jump(loop)
        c.mark(finish)
        c.ops(Op.NOP | 128)

    c.mark('irq_enqueue')
    c.load('irq_base')
    c.push(2)
    c.ops(Op.ADD, Op.FETCH)
    c.store('irq_tail')
    c.load('irq_tail')
    c.push(1)
    c.ops(Op.ADD)
    c.push(RING_SIZE - 1)
    c.ops(Op.AND)
    c.store('irq_next')
    c.load('irq_base')
    c.ops(Op.FETCH)
    c.load('irq_next')
    c.ops(Op.SUB)
    full = c.label('irq_ring_full')
    c.jz(full)
    c.load('irq_byte')
    c.load('irq_base')
    c.push(6)
    c.ops(Op.ADD)
    c.load('irq_tail')
    c.ops(Op.ADD, Op.BYTE_STORE)
    c.load('irq_next')
    c.load('irq_base')
    c.push(2)
    c.ops(Op.ADD, Op.STORE, Op.NOP | 128)
    c.mark(full)
    c.push(1)
    c.load('irq_base')
    c.push(4)
    c.ops(Op.ADD, Op.STORE, Op.NOP | 128)
