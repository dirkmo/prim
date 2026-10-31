"""Shared console output and the small integrated VGA backend."""
from prim.isa import PrimOpcodes as Op
from forth.kernel.primitives import Code

# Reserved SRAM above the user dictionary; never overlaps the banked window.
IO_NAMES = ('console_owner', 'vga_x', 'vga_y', 'vga_row', 'vga_saved',
            'vga_char', 'vga_clear', 'vga_left')
IO_VARIABLES = {name: 0xF000 + 2 * n for n, name in enumerate(IO_NAMES)}


def set_cell(c, name, value):
    c.push(value)
    c.store(name)


def increment(c, name, delta=1):
    c.load(name)
    c.push(abs(delta))
    c.ops(Op.ADD if delta > 0 else Op.SUB)
    c.store(name)


def emit_io(image):
    c = Code(image)
    c.mark('raw_emit')  # ( byte -- ), preserves logical DEPTH.
    c.load('console_owner')
    local = c.label('emit_local')
    c.jz(local)
    c.jump('vga_emit')
    c.mark(local)
    c.push('uart_data')
    c.ops(Op.BYTE_STORE, Op.NOP | 128)

    c.mark('vga_write')  # ( byte address -- ); restore every CONTROL bit.
    c.push(0xFFF6)
    c.ops(Op.BYTE_FETCH)
    c.store('vga_saved')
    c.load('vga_saved')
    c.push(1)
    c.ops(Op.OR)
    c.push(0xFFF6)
    c.ops(Op.BYTE_STORE, Op.BYTE_STORE)
    c.load('vga_saved')
    c.push(0xFFF6)
    c.ops(Op.BYTE_STORE, Op.NOP | 128)

    c.mark('vga_address')  # ( -- address ); (row+y)%32 * 80 + x.
    c.load('vga_y')
    c.load('vga_row')
    c.ops(Op.ADD)
    c.push(31)
    c.ops(Op.AND, Op.DUP, *([Op.SL] * 4), Op.SWAP, *([Op.SL] * 6), Op.ADD)
    c.push(0xE000)
    c.ops(Op.ADD)
    c.load('vga_x')
    c.ops(Op.ADD, Op.NOP | 128)

    c.mark('vga_cursor')
    for name, address in (('vga_x', 0xFFF8), ('vga_y', 0xFFF9), ('vga_row', 0xFFF7)):
        c.load(name)
        c.push(address)
        c.ops(Op.BYTE_STORE)
    c.ops(Op.NOP | 128)

    c.mark('vga_clear_span')
    loop, done = c.label('vga_clear_loop'), c.label('vga_clear_done')
    c.mark(loop)
    c.load('vga_left')
    c.jz(done)
    c.push(32)
    c.load('vga_clear')
    c.call('vga_write')
    increment(c, 'vga_clear')
    increment(c, 'vga_left', -1)
    c.jump(loop)
    c.mark(done)
    c.ops(Op.NOP | 128)

    c.mark('vga_init')
    for name in ('vga_x', 'vga_y', 'vga_row'):
        set_cell(c, name, 0)
    c.push(0x1E)
    c.push(0xFFF6)
    c.ops(Op.BYTE_STORE)
    set_cell(c, 'vga_clear', 0xE000)
    set_cell(c, 'vga_left', 2560)
    c.call('vga_clear_span')
    c.jump('vga_cursor')

    c.mark('vga_newline')
    set_cell(c, 'vga_x', 0)
    increment(c, 'vga_y')
    c.load('vga_y')
    c.push(30)
    c.ops(Op.LTU)
    scroll = c.label('vga_scroll')
    c.jz(scroll)
    c.jump('vga_cursor')
    c.mark(scroll)
    set_cell(c, 'vga_y', 29)
    c.load('vga_row')
    c.push(1)
    c.ops(Op.ADD)
    c.push(31)
    c.ops(Op.AND)
    c.store('vga_row')
    c.call('vga_address')
    c.store('vga_clear')
    set_cell(c, 'vga_left', 80)
    c.call('vga_clear_span')
    c.jump('vga_cursor')

    c.mark('vga_emit')
    c.store('vga_char')
    cr, lf, bs, printable, done = (c.label('vga_' + n) for n in ('cr', 'lf', 'bs', 'print', 'done'))
    for byte, target in ((13, cr), (10, lf), (8, bs), (127, bs)):
        c.load('vga_char')
        c.push(byte)
        c.ops(Op.SUB)
        c.jz(target)
    c.load('vga_char')
    c.push(32)
    c.ops(Op.LTU)
    c.jz(printable)
    c.jump(done)  # Other control characters do not become visible glyphs.
    c.mark(printable)
    c.load('vga_char')
    c.call('vga_address')
    c.call('vga_write')
    increment(c, 'vga_x')
    c.load('vga_x')
    c.push(80)
    c.ops(Op.SUB)
    c.jz(lf)
    c.jump('vga_cursor')
    c.mark(cr)
    set_cell(c, 'vga_x', 0)
    c.jump('vga_cursor')
    c.mark(lf)
    c.jump('vga_newline')
    c.mark(bs)
    c.load('vga_x')
    c.jz(done)
    increment(c, 'vga_x', -1)
    c.push(32)
    c.call('vga_address')
    c.call('vga_write')
    c.jump('vga_cursor')
    c.mark(done)
    c.ops(Op.NOP | 128)
