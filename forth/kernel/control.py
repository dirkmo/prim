"""AP 7: typed compile-time control stack and checked native branches."""
from functools import partial
from prim.isa import PrimOpcodes as Op
from forth.kernel.primitives import Code, emit_word

IF, ELSE, BEGIN, WHILE = 1, 2, 3, 4


def emit_control(image):
    c = Code(image)
    word = partial(emit_word, c, need=0, give=0, flags=3)

    def set_cell(name, value):
        c.push(value)
        c.store(name)

    def byte(value):
        c.push(value)
        c.call('compile_byte')

    def cell(value):
        c.push(value)
        c.call('compile_cell')

    def slot():
        c.load('control_depth')
        c.ops(Op.SL, Op.SL)
        c.push('control_stack')
        c.ops(Op.ADD)
        c.store('control_slot')

    def change_depth(op):
        c.load('control_depth')
        c.push(1)
        c.ops(op)
        c.store('control_depth')

    c.mark('control_push')
    c.load('control_depth')
    c.push(32)
    c.ops(Op.LTU)
    c.jz('error_control_overflow')
    slot()
    c.load('control_type')
    c.load('control_slot')
    c.ops(Op.STORE)
    c.load('control_addr')
    c.load('control_slot')
    c.push(2)
    c.ops(Op.ADD, Op.STORE)
    change_depth(Op.ADD)
    c.ops(Op.NOP | 128)

    c.mark('control_peek')
    c.load('control_depth')
    c.jz('error_control')
    c.load('control_depth')
    c.push(33)
    c.ops(Op.LTU)
    c.jz('error_control_overflow')
    change_depth(Op.SUB)
    slot()
    change_depth(Op.ADD)
    c.load('control_slot')
    c.ops(Op.FETCH)
    c.store('control_type')
    c.load('control_slot')
    c.push(2)
    c.ops(Op.ADD, Op.FETCH)
    c.store('control_addr')
    c.ops(Op.NOP | 128)

    c.mark('patch_forward')  # control_patch points at the emitted target cell.
    c.load('control_patch')
    c.load('pending_header')
    c.push(4)
    c.ops(Op.ADD, Op.FETCH, Op.LTU)
    low = c.label('patch_low')
    c.jz(low)
    c.jump('error_control')
    c.mark(low)
    c.load('here')
    c.push(2)
    c.ops(Op.SUB)
    c.load('control_patch')
    c.ops(Op.LTU)
    high = c.label('patch_high')
    c.jz(high)
    c.jump('error_control')
    c.mark(high)
    c.load('here')
    c.load('control_patch')
    c.ops(Op.STORE, Op.NOP | 128)

    # Leaves the physical flag for JZ; only the semantic DEPTH is decreased.
    c.mark('branch_guard')
    c.guard(1, 0)
    c.ops(Op.NOP | 128)

    def expect(kind):
        c.call('control_peek')
        c.load('control_type')
        c.push(kind)
        c.ops(Op.SUB)
        good = c.label('control_type_ok')
        c.jz(good)
        c.jump('error_control')
        c.mark(good)

    def push(kind):
        set_cell('control_type', kind)
        c.call('control_push')

    def branch(conditional, forward):
        set_cell('compiler_needed', 8 if conditional else 4)
        c.call('compiler_reserve')
        if conditional:
            byte(Op.PUSH)
            cell('branch_guard')
            byte(Op.CALL)
        byte(Op.PUSH)
        if forward:
            c.load('here')
            c.store('control_addr')
            cell(0)
        else:
            c.load('control_addr')
            c.call('compile_cell')
        byte(Op.JZ if conditional else Op.JP)

    def if_word():
        c.call('require_compiling')
        branch(True, True)
        push(IF)
    word('IF', body=if_word)

    def else_word():
        c.call('require_compiling')
        expect(IF)
        c.load('control_addr')
        c.store('control_patch')
        change_depth(Op.SUB)
        branch(False, True)
        c.call('patch_forward')
        push(ELSE)
    word('ELSE', body=else_word)

    def then_word():
        c.call('require_compiling')
        c.call('control_peek')
        c.load('control_type')
        c.push(IF)
        c.ops(Op.SUB)
        good = c.label('then_type_ok')
        c.jz(good)
        c.load('control_type')
        c.push(ELSE)
        c.ops(Op.SUB)
        c.jz(good)
        c.jump('error_control')
        c.mark(good)
        c.load('control_addr')
        c.store('control_patch')
        c.call('patch_forward')
        change_depth(Op.SUB)
    word('THEN', body=then_word)

    def begin_word():
        c.call('require_compiling')
        c.load('here')
        c.store('control_addr')
        push(BEGIN)
    word('BEGIN', body=begin_word)

    for name, conditional in (('UNTIL', True), ('AGAIN', False)):
        def back(conditional=conditional):
            c.call('require_compiling')
            expect(BEGIN)
            change_depth(Op.SUB)
            branch(conditional, False)
        word(name, body=back)

    def while_word():
        c.call('require_compiling')
        expect(BEGIN)
        branch(True, True)
        push(WHILE)
    word('WHILE', body=while_word)

    def repeat_word():
        c.call('require_compiling')
        expect(WHILE)
        c.load('control_addr')
        c.store('control_patch')
        change_depth(Op.SUB)
        expect(BEGIN)
        change_depth(Op.SUB)
        branch(False, False)
        c.call('patch_forward')
    word('REPEAT', body=repeat_word)
