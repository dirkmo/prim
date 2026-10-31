"""Set-2 German QWERTZ ASCII decoder, executed by Prim in foreground."""
from prim.isa import PrimOpcodes as Op
from forth.kernel.primitives import Code
from forth.kernel.io import set_cell, increment
from forth.kernel.interrupts import RINGS

KBD_NAMES = ('kbd_scan', 'kbd_char', 'kbd_available', 'kbd_extended', 'kbd_break',
             'kbd_skip', 'kbd_shift', 'kbd_ctrl', 'kbd_altgr', 'kbd_caps',
             'kbd_caps_down', 'kbd_work')
KBD_VARIABLES = {name: 0xF040 + 2 * n for n, name in enumerate(KBD_NAMES)}


def key_tables():
    normal, shifted, altgr = bytearray(128), bytearray(128), bytearray(128)
    letters = {0x1C: 'a', 0x32: 'b', 0x21: 'c', 0x23: 'd', 0x24: 'e',
               0x2B: 'f', 0x34: 'g', 0x33: 'h', 0x43: 'i', 0x3B: 'j',
               0x42: 'k', 0x4B: 'l', 0x3A: 'm', 0x31: 'n', 0x44: 'o',
               0x4D: 'p', 0x15: 'q', 0x2D: 'r', 0x1B: 's', 0x2C: 't',
               0x3C: 'u', 0x2A: 'v', 0x1D: 'w', 0x22: 'x', 0x1A: 'y', 0x35: 'z'}
    for scan, char in letters.items():
        normal[scan], shifted[scan] = ord(char), ord(char.upper())
    for scan, pair in {0x16: '1!', 0x1E: '2"', 0x26: '3\0', 0x25: '4$',
                       0x2E: '5%', 0x36: '6&', 0x3D: '7/', 0x3E: '8(',
                       0x46: '9)', 0x45: '0=', 0x4E: '\0?', 0x55: '\0`',
                       0x0E: '^\0', 0x5B: '+*', 0x5D: "#'", 0x41: ',;',
                       0x49: '.:', 0x4A: '-_', 0x61: '<>'}.items():
        normal[scan], shifted[scan] = map(ord, pair)
    for scan, byte in ((0x29, 32), (0x5A, 13), (0x66, 8), (0x0D, 9), (0x76, 27)):
        normal[scan] = shifted[scan] = byte
    for scan, char in {0x15: '@', 0x3D: '{', 0x3E: '[', 0x46: ']',
                       0x45: '}', 0x4E: '\\', 0x5B: '~', 0x61: '|'}.items():
        altgr[scan] = ord(char)
    return normal, shifted, altgr


def emit_keyboard(image):
    c = Code(image)
    c.mark('kbd_reset')
    for name in KBD_VARIABLES:
        set_cell(c, name, 0)
    c.ops(Op.NOP | 128)

    c.mark('kbd_decode')  # Input kbd_scan; output kbd_char and kbd_available.
    set_cell(c, 'kbd_available', 0)
    skip_done = c.label('kbd_not_skipping')
    c.load('kbd_skip')
    c.jz(skip_done)
    increment(c, 'kbd_skip', -1)
    c.ops(Op.NOP | 128)
    c.mark(skip_done)
    done, clear, ordinary = (c.label('kbd_' + n) for n in ('done', 'clear', 'ordinary'))

    def equals(byte, target):
        c.load('kbd_scan')
        c.push(byte)
        c.ops(Op.SUB)
        c.jz(target)

    # BAT resets modifier state. Other protocol replies never become characters.
    equals(0xAA, 'kbd_reset')
    for byte in (0xFA, 0xFE):
        equals(byte, clear)
    for byte in (0xFC, 0xFD, 0x00, 0xFF):
        equals(byte, 'kbd_protocol_error')
    for byte, name, value in ((0xE1, 'kbd_skip', 7), (0xE0, 'kbd_extended', 1),
                               (0xF0, 'kbd_break', 1)):
        next_prefix = c.label('kbd_prefix_next')
        c.load('kbd_scan')
        c.push(byte)
        c.ops(Op.SUB)
        c.jz(next_prefix)
        continue_prefix = c.label('kbd_prefix_continue')
        c.jump(continue_prefix)
        c.mark(next_prefix)
        set_cell(c, name, value)
        if byte == 0xE1:
            set_cell(c, 'kbd_extended', 0)
            set_cell(c, 'kbd_break', 0)
        c.jump(done)
        c.mark(continue_prefix)

    # Distinguish extended Ctrl/AltGr from plain left modifiers. Fake extended
    # shifts in Print Screen are ignored, never changing the real Shift mask.
    plain = c.label('kbd_plain')
    c.load('kbd_extended')
    c.jz(plain)
    for scan, target in ((0x14, 'kbd_ctrl_right'), (0x11, 'kbd_alt_right')):
        equals(scan, target)
    equals(0x5A, ordinary)  # Keypad Enter.
    c.jump(clear)
    c.mark(plain)
    for scan, target in ((0x12, 'kbd_shift_left'), (0x59, 'kbd_shift_right'),
                          (0x14, 'kbd_ctrl_left'), (0x58, 'kbd_caps_key')):
        equals(scan, target)
    c.mark(ordinary)
    c.load('kbd_break')
    make = c.label('kbd_make')
    c.jz(make)
    c.jump(clear)
    c.mark(make)
    c.load('kbd_scan')
    c.push(128)
    c.ops(Op.LTU)
    c.jz(clear)
    normal, selected = c.label('kbd_normal'), c.label('kbd_selected')
    c.load('kbd_altgr')
    c.jz(normal)
    table = 'kbd_altgr_table'
    c.push(table)
    c.load('kbd_scan')
    c.ops(Op.ADD, Op.BYTE_FETCH)
    c.store('kbd_char')
    c.jump(selected)
    c.mark(normal)
    c.push('kbd_normal_table')
    c.load('kbd_scan')
    c.ops(Op.ADD, Op.BYTE_FETCH)
    c.store('kbd_char')
    # For letters use Shift XOR Caps; punctuation only observes Shift.
    set_cell(c, 'kbd_work', 0)
    shift_ready, punctuation = (c.label('kbd_' + n) for n in ('shift_ready', 'punctuation'))
    c.load('kbd_shift')
    c.jz(shift_ready)
    set_cell(c, 'kbd_work', 1)
    c.mark(shift_ready)
    c.load('kbd_char')
    c.push(97)
    c.ops(Op.LTU)
    letter_high = c.label('kbd_letter_high')
    c.jz(letter_high)
    c.jump(punctuation)
    c.mark(letter_high)
    c.load('kbd_char')
    c.push(123)
    c.ops(Op.LTU)
    c.jz(punctuation)
    c.load('kbd_work')
    c.load('kbd_caps')
    c.ops(Op.XOR)
    c.store('kbd_work')
    c.mark(punctuation)
    c.load('kbd_work')
    c.jz(selected)
    c.push('kbd_shift_table')
    c.load('kbd_scan')
    c.ops(Op.ADD, Op.BYTE_FETCH)
    c.store('kbd_char')
    c.mark(selected)
    c.load('kbd_char')
    c.jz(clear)  # Unmapped/non-ASCII keys; NUL may still result from Ctrl below.
    emit = c.label('kbd_emit')
    c.load('kbd_altgr')
    no_altgr = c.label('kbd_no_altgr')
    c.jz(no_altgr)
    c.jump(emit)
    c.mark(no_altgr)
    c.load('kbd_ctrl')
    c.jz(emit)
    ctrl_space, ctrl_range = c.label('kbd_ctrl_space'), c.label('kbd_ctrl_range')
    c.load('kbd_char')
    c.push(32)
    c.ops(Op.SUB)
    c.jz(ctrl_space)
    c.load('kbd_char')
    c.push(0x5F)
    c.ops(Op.AND)
    c.store('kbd_work')
    c.load('kbd_work')
    c.push(64)
    c.ops(Op.LTU)
    c.jz(ctrl_range)
    c.jump(emit)
    c.mark(ctrl_range)
    c.load('kbd_work')
    c.push(96)
    c.ops(Op.LTU)
    c.jz(emit)
    c.load('kbd_char')
    c.push(31)
    c.ops(Op.AND)
    c.store('kbd_char')
    c.jump(emit)
    c.mark(ctrl_space)
    set_cell(c, 'kbd_char', 0)
    c.mark(emit)
    set_cell(c, 'kbd_available', 1)
    c.jump(clear)

    for label, variable, mask in (('kbd_shift_left', 'kbd_shift', 1),
                                   ('kbd_shift_right', 'kbd_shift', 2),
                                   ('kbd_ctrl_left', 'kbd_ctrl', 1),
                                   ('kbd_ctrl_right', 'kbd_ctrl', 2),
                                   ('kbd_alt_right', 'kbd_altgr', 1)):
        c.mark(label)
        release = c.label('kbd_release')
        c.load('kbd_break')
        c.jz(release)
        c.load(variable)
        c.push(0xFFFF ^ mask)
        c.ops(Op.AND)
        c.store(variable)
        c.jump(clear)
        c.mark(release)
        c.load(variable)
        c.push(mask)
        c.ops(Op.OR)
        c.store(variable)
        c.jump(clear)

    c.mark('kbd_caps_key')
    caps_make = c.label('kbd_caps_make')
    c.load('kbd_break')
    c.jz(caps_make)
    set_cell(c, 'kbd_caps_down', 0)
    c.jump(clear)
    c.mark(caps_make)
    c.load('kbd_caps_down')
    caps_toggle = c.label('kbd_caps_toggle')
    c.jz(caps_toggle)
    c.jump(clear)
    c.mark(caps_toggle)
    set_cell(c, 'kbd_caps_down', 1)
    c.load('kbd_caps')
    c.push(1)
    c.ops(Op.XOR)
    c.store('kbd_caps')
    c.mark(clear)
    set_cell(c, 'kbd_extended', 0)
    set_cell(c, 'kbd_break', 0)
    c.mark(done)
    c.ops(Op.NOP | 128)

    c.mark('kbd_protocol_error')
    c.push(1)
    c.push(RINGS['ps2'] + 4)  # Local loss flag, consumed by foreground recovery.
    c.ops(Op.STORE)
    c.jump('kbd_reset')

    for name, data in zip(('kbd_normal_table', 'kbd_shift_table', 'kbd_altgr_table'), key_tables()):
        c.mark(name)
        image.emit(data)
