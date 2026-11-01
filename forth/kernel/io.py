"""Shared console output and the small integrated VGA backend."""
from prim.isa import PrimOpcodes as Op
from forth.kernel.primitives import Code, emit_word

# Reserved SRAM above the user dictionary; never overlaps the banked window.
IO_NAMES = ('console_owner', 'vga_x', 'vga_y', 'vga_row', 'vga_saved',
            'vga_char', 'vga_clear', 'vga_left')
IO_VARIABLES = {name: 0xF000 + 2 * n for n, name in enumerate(IO_NAMES)}


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
    c.advance('vga_clear')
    c.advance('vga_left', -1)
    c.jump(loop)
    c.mark(done)
    c.ops(Op.NOP | 128)

    c.mark('vga_init')
    c.push(0x1E)
    c.push(0xFFF6)
    c.ops(Op.BYTE_STORE)
    c.mark('vga_page')
    for name in ('vga_x', 'vga_y', 'vga_row'):
        c.set_cell(name, 0)
    c.set_cell('vga_clear', 0xE000)
    c.set_cell('vga_left', 2560)
    c.call('vga_clear_span')
    c.jump('vga_cursor')

    c.mark('vga_newline')
    c.set_cell('vga_x', 0)
    c.advance('vga_y')
    c.load('vga_y')
    c.push(30)
    c.ops(Op.LTU)
    scroll = c.label('vga_scroll')
    c.jz(scroll)
    c.jump('vga_cursor')
    c.mark(scroll)
    c.set_cell('vga_y', 29)
    c.load('vga_row')
    c.push(1)
    c.ops(Op.ADD)
    c.push(31)
    c.ops(Op.AND)
    c.store('vga_row')
    c.call('vga_address')
    c.store('vga_clear')
    c.set_cell('vga_left', 80)
    c.call('vga_clear_span')
    c.jump('vga_cursor')

    c.mark('vga_emit')
    c.push(255)
    c.ops(Op.AND)  # EMIT consumes a byte, including control-byte interpretation.
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
    c.mark('vga_put')  # ( byte -- ); unfiltered write, followed by cursor advance.
    c.call('vga_address')
    c.call('vga_write')
    c.advance('vga_x')
    c.load('vga_x')
    c.push(80)
    c.ops(Op.SUB)
    c.jz(lf)
    c.jump('vga_cursor')
    c.mark(cr)
    c.set_cell('vga_x', 0)
    c.jump('vga_cursor')
    c.mark(lf)
    c.jump('vga_newline')
    c.mark(bs)
    c.load('vga_x')
    c.jz(done)
    c.advance('vga_x', -1)
    c.push(32)
    c.call('vga_address')
    c.call('vga_write')
    c.jump('vga_cursor')
    c.mark(done)
    c.ops(Op.NOP | 128)

    c.mark('vga_backspace')
    c.push(8)
    c.jump('vga_emit')

    c.mark('vga_clear_row')
    c.call('vga_address')
    c.load('vga_x')
    c.ops(Op.SUB)
    c.store('vga_clear')
    c.set_cell('vga_left', 80)
    c.jump('vga_clear_span')

    # Explicit VGA access shares the local console's cursor and scroll state.
    for name, target, need, give in (
            ('VGA-INIT', 'vga_init', 0, 0), ('VGA-PAGE', 'vga_page', 0, 0),
            ('VGA-EMIT', 'vga_emit', 1, 0), ('VGA-CR', 'vga_newline', 0, 0),
            ('VGA-PUT', 'vga_put', 1, 0), ('VGA-BS', 'vga_backspace', 0, 0),
            ('VGA-CLEAR-ROW', 'vga_clear_row', 0, 0),
            ('VGA-CURSOR', 'vga_cursor', 0, 0), ('VGA-ADDR', 'vga_address', 0, 1),
            ('VGA-C!', 'vga_write', 2, 0)):
        emit_word(c, name, need, give, lambda target=target: c.call(target))
    for name, cell in (('VX', 'vga_x'), ('VY', 'vga_y'), ('VO', 'vga_row')):
        emit_word(c, name, 0, 1, lambda cell=cell: c.push(cell))
