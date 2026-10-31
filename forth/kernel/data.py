"""AP 8: data definitions, allocation, byte spans and immediate string words."""
from functools import partial
from prim.isa import PrimOpcodes as Op
from forth.kernel.primitives import Code, emit_word


def emit_data(image):
    c = Code(image)
    word = partial(emit_word, c)

    def set_cell(name, value):
        c.push(value)
        c.store(name)

    def advance(name):
        c.load(name)
        c.push(1)
        c.ops(Op.ADD)
        c.store(name)

    def byte(value):
        c.push(value)
        c.call('compile_byte')

    def cell(value):
        c.push(value)
        c.call('compile_cell')

    word('HERE', 0, 1, lambda: c.load('here'))

    def allot():
        c.store('compiler_needed')
        c.load('compiler_needed')
        c.push(0x8000)
        c.ops(Op.LTU)
        c.jz('error_allot')
        c.call('compiler_reserve')
        c.load('here')
        c.load('compiler_needed')
        c.ops(Op.ADD)
        c.store('here')
    word('ALLOT', 1, 0, allot)
    word(',', 1, 0, lambda: c.call('compile_cell'))
    word('C,', 1, 0, lambda: c.call('compile_byte'))

    c.mark('define_data')
    c.call('colon_xt')  # Begins hidden, rollback-capable header transaction.
    c.load('data_kind')
    c.push(2)
    c.ops(Op.SUB)
    constant, reserved = c.label('data_constant'), c.label('data_reserved')
    c.jz(constant)
    c.load('here')
    c.push(8)
    c.ops(Op.ADD)
    c.store('data_value')
    c.mark(constant)
    set_cell('compiler_needed', 8)
    c.load('data_kind')
    c.push(1)
    c.ops(Op.SUB)
    c.jz(reserved)
    write = c.label('data_write')
    c.jump(write)
    c.mark(reserved)
    set_cell('compiler_needed', 10)
    c.mark(write)
    c.call('compiler_reserve')
    # Fixed eight-byte checked stub, regardless of constant value magnitude.
    byte(Op.PUSH)
    cell('literal_guard')
    byte(Op.CALL)
    byte(Op.PUSH)
    c.load('data_value')
    c.call('compile_cell')
    byte(Op.NOP | 128)
    c.load('data_kind')
    c.push(1)
    c.ops(Op.SUB)
    variable, publish = c.label('data_variable'), c.label('data_publish')
    c.jz(variable)
    c.jump(publish)
    c.mark(variable)
    cell(0)
    c.mark(publish)
    c.call('publish_definition')  # Only publish after variable initialization.
    c.ops(Op.NOP | 128)

    for name, kind, need in (('CREATE', 0, 0), ('VARIABLE', 1, 0), ('CONSTANT', 2, 1)):
        def define(kind=kind):
            if kind == 2:
                c.store('data_value')
            set_cell('data_kind', kind)
            c.call('define_data')
        word(name, need, 0, define)

    c.mark('raw_type')  # ( addr len -- ), temporary raw arguments; DEPTH unchanged.
    c.store('print_left')
    c.store('print_addr')
    c.jump('print_span')
    word('TYPE', 2, 0, lambda: c.call('raw_type'))
    image.define('type_xt', image.symbols[image.words[-1]['xt']])

    c.mark('parse_string')  # Input position is after exactly one opening delimiter.
    c.push('input_buffer')
    c.load('input_pos')
    c.ops(Op.ADD)
    c.store('string_addr')
    set_cell('string_length', 0)
    loop, done = c.label('string_scan'), c.label('string_closed')
    c.mark(loop)
    c.load('input_pos')
    c.load('input_length')
    c.ops(Op.LTU)
    c.jz('error_string')
    c.push('input_buffer')
    c.load('input_pos')
    c.ops(Op.ADD, Op.BYTE_FETCH)
    c.push(34)
    c.ops(Op.SUB)
    c.jz(done)
    advance('input_pos')
    advance('string_length')
    c.jump(loop)
    c.mark(done)
    advance('input_pos')
    c.ops(Op.NOP | 128)

    c.mark('copy_string_buffer')
    set_cell('string_index', 0)
    loop, done = c.label('string_copy'), c.label('string_copied')
    c.mark(loop)
    c.load('string_index')
    c.load('string_length')
    c.ops(Op.LTU)
    c.jz(done)
    c.load('string_addr')
    c.load('string_index')
    c.ops(Op.ADD, Op.BYTE_FETCH)
    c.push('string_buffer')
    c.load('string_index')
    c.ops(Op.ADD, Op.BYTE_STORE)
    advance('string_index')
    c.jump(loop)
    c.mark(done)
    c.push(0)
    c.push('string_buffer')
    c.load('string_length')
    c.ops(Op.ADD, Op.BYTE_STORE)
    c.ops(Op.NOP | 128)

    def compile_string(printing):
        c.call('require_compiling')
        c.load('string_length')
        c.push(13 if printing else 17)
        c.ops(Op.ADD)
        c.store('compiler_needed')
        c.call('compiler_reserve')
        c.load('here')
        c.push(4)
        c.ops(Op.ADD)
        c.store('string_code_addr')
        byte(Op.PUSH)
        c.load('string_code_addr')
        c.load('string_length')
        c.ops(Op.ADD)
        c.call('compile_cell')
        byte(Op.JP)  # Skip embedded bytes; never fetch them as opcodes.
        set_cell('string_index', 0)
        loop, done = c.label('string_emit'), c.label('string_emitted')
        c.mark(loop)
        c.load('string_index')
        c.load('string_length')
        c.ops(Op.LTU)
        c.jz(done)
        c.load('string_addr')
        c.load('string_index')
        c.ops(Op.ADD, Op.BYTE_FETCH)
        c.call('compile_byte')
        advance('string_index')
        c.jump(loop)
        c.mark(done)
        if printing:
            # Private temporaries, so ." works even with eight user cells.
            byte(Op.PUSH)
            c.load('string_code_addr')
            c.call('compile_cell')
            byte(Op.PUSH8)
            c.load('string_length')
            c.call('compile_byte')
            byte(Op.PUSH)
            cell('raw_type')
            byte(Op.CALL)
        else:
            for source in ('string_code_addr', 'string_length'):
                c.load(source)
                c.store('compile_value')
                c.call('compile_literal')

    for name, printing in (('S"', False), ('."', True)):
        def string_word(printing=printing):
            c.call('parse_string')
            interpreted, done = c.label('string_interpreted'), c.label('string_done')
            c.load('state')
            c.jz(interpreted)
            compile_string(printing)
            c.jump(done)
            c.mark(interpreted)
            if printing:
                c.load('string_addr')
                c.load('string_length')
                c.call('raw_type')
            else:
                c.guard(0, 2)
                c.call('copy_string_buffer')
                c.push('string_buffer')
                c.load('string_length')
            c.mark(done)
        # S" has mode-dependent effect: +2 interpreted, zero while compiling.
        word(name, 0, 0, string_word, flags=1)
        if not printing:
            image.words[-1]['mode_effects'] = {
                'interpret': {'need': 0, 'give': 2},
                'compile': {'need': 0, 'give': 0},
            }
