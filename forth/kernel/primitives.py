"""Forth primitives and shared Prim code-generation helpers."""
from prim.isa import PrimOpcodes as Op
from forth.image import Ref
from functools import partial

ERRORS = {
    'shift': (3, 'shift range'),
    'division_zero': (4, 'division by zero'),
    'division_overflow': (5, 'division overflow'),
    'input_overflow': (6, 'input too long'),
    'comment': (7, 'unterminated comment'),
    'base': (8, 'invalid base'),
    'input_character': (9, 'input character'),
    'number_overflow': (10, 'number overflow'),
    'unknown': (11, 'unknown word'),
    'compile_only': (12, 'compile-only word'),
    'compiler': (13, 'compiler context'),
    'name': (14, 'invalid name'),
    'memory': (15, 'dictionary full'),
    'immediate': (16, 'no user definition'),
    'control': (17, 'unresolved control'),
    'incomplete': (18, 'unfinished definition'),
    'control_overflow': (19, 'control stack overflow'),
    'allot': (20, 'invalid allot'),
    'string': (21, 'unterminated string'),
    'forget': (22, 'cannot forget kernel word'),
}

# Foreground arithmetic scratch; the ISR uses separate IRQ-private cells.
ARITHMETIC = dict(zip(('a', 'b', 'q', 'rem', 'count', 'qsign', 'rsign'),
                      range(0x0380, 0x038E, 2)))


class Code:
    """Conveniences for emitting branches and private RAM operations."""
    def __init__(self, image):
        self.i = image

    def label(self, purpose):
        self.i.label_serial += 1
        return f'local_{self.i.label_serial}_{purpose}'

    def mark(self, label):
        self.i.define(label)

    def ops(self, *opcodes):
        for opcode in opcodes:
            self.i.op(opcode)

    def push(self, value):
        self.i.push(Ref(value) if isinstance(value, str) else value)

    def load(self, name):
        self.push(name)
        self.ops(Op.FETCH)

    def store(self, name):
        self.push(name)
        self.ops(Op.STORE)

    def set_cell(self, name, value):
        self.push(value)
        self.store(name)

    def advance(self, name, amount=1):
        self.load(name)
        self.push(abs(amount))
        self.ops(Op.ADD if amount > 0 else Op.SUB)
        self.store(name)

    def compile_byte(self, value):
        """Emit a runtime call that appends a byte to the Forth dictionary."""
        self.push(value)
        self.call('compile_byte')

    def compile_cell(self, value):
        """Emit a runtime call that appends a cell to the Forth dictionary."""
        self.push(value)
        self.call('compile_cell')

    def jump(self, label, opcode=Op.JP):
        self.push(label)
        self.ops(opcode)

    def jz(self, label):
        self.jump(label, Op.JZ)

    def call(self, label):
        self.jump(label, Op.CALL)

    def emit(self):
        if getattr(self.i, 'dual_console', False):
            self.call('raw_emit')
        else:
            self.push('uart_data')
            self.ops(Op.BYTE_STORE)

    def output(self, text):
        for byte in text:
            self.push(byte)
            self.emit()

    def negate(self):
        self.push(0)
        self.ops(Op.SWAP, Op.SUB)

    def boolean_zero(self):
        yes, done = self.label('zero'), self.label('boolean_done')
        self.jz(yes)
        self.push(0)
        self.jump(done)
        self.mark(yes)
        self.push(0xFFFF)
        self.mark(done)

    def adjust_depth(self, need, give):
        """Maintain DEPTH/.S bookkeeping without testing stack bounds."""
        delta = give - need
        if delta:
            self.advance('depth', delta)


def emit_word(c, name, need, give, body, flags=0):
    image = c.i
    index = len(image.words)
    header, xt = f'header_{index}', f'xt_{index}'
    if image.pc & 1:
        image.emit([0])
    image.define(header)
    previous = Ref(image.words[-1]['header']) if image.words else 0
    image.cell(previous)
    image.emit([flags, len(name)])
    image.cell(Ref(xt))
    image.emit(name.encode('ascii'))
    if image.pc & 1:
        image.emit([0])
    image.define(xt)
    image.words.append({'name': name, 'header': header, 'xt': xt,
                        'need': need, 'give': give, 'flags': flags})
    c.adjust_depth(need, give)
    body()
    c.ops(Op.NOP | 0x80)


def emit_primitives(image):
    c = Code(image)
    for name, address in ARITHMETIC.items():
        image.define('arith_' + name, address)
    word = partial(emit_word, c)

    simple = (
        ('DUP', 1, 2, (Op.DUP,)), ('DROP', 1, 0, (Op.DROP,)),
        ('SWAP', 2, 2, (Op.SWAP,)), ('OVER', 2, 3, (Op.OVER,)),
        ('ROT', 3, 3, (Op.ROT,)), ('-ROT', 3, 3, (Op.NROT,)),
        ('NIP', 2, 1, (Op.NIP,)), ('2DUP', 2, 4, (Op.OVER, Op.OVER)),
        ('2DROP', 2, 0, (Op.DROP, Op.DROP)),
        ('+', 2, 1, (Op.ADD,)), ('-', 2, 1, (Op.SUB,)),
        ('AND', 2, 1, (Op.AND,)), ('OR', 2, 1, (Op.OR,)),
        ('XOR', 2, 1, (Op.XOR,)), ('INVERT', 1, 1, (Op.NOT,)),
        ('<', 2, 1, (Op.LTS,)), ('>', 2, 1, (Op.SWAP, Op.LTS)),
        ('U<', 2, 1, (Op.LTU,)), ('@', 1, 1, (Op.FETCH,)),
        ('!', 2, 0, (Op.STORE,)), ('C@', 1, 1, (Op.BYTE_FETCH,)),
        ('C!', 2, 0, (Op.BYTE_STORE,)), ('2*', 1, 1, (Op.SL,)),
        ('CELLS', 1, 1, (Op.SL,)),
    )
    for name, need, give, ops in simple:
        word(name, need, give, lambda ops=ops: c.ops(*ops))

    for name, amount, opcode in (('1+', 1, Op.ADD), ('1-', 1, Op.SUB),
                                  ('CELL+', 2, Op.ADD)):
        def body(amount=amount, opcode=opcode):
            c.push(amount)
            c.ops(opcode)
        word(name, 1, 1, body)
    word('NEGATE', 1, 1, c.negate)

    def absolute():
        done = c.label('abs_done')
        c.ops(Op.DUP)
        c.push(0)
        c.ops(Op.LTS)
        c.jz(done)
        c.negate()
        c.mark(done)
    word('ABS', 1, 1, absolute)

    def arithmetic_half():
        c.ops(Op.DUP)
        c.push(0x8000)
        c.ops(Op.AND, Op.SWAP, Op.SR, Op.OR)
    word('2/', 1, 1, arithmetic_half)

    word('0=', 1, 1, c.boolean_zero)
    def nonzero():
        c.boolean_zero()
        c.ops(Op.NOT)
    word('0<>', 1, 1, nonzero)
    def negative():
        c.push(0)
        c.ops(Op.LTS)
    word('0<', 1, 1, negative)
    def equal():
        c.ops(Op.SUB)
        c.boolean_zero()
    word('=', 2, 1, equal)
    def unequal():
        equal()
        c.ops(Op.NOT)
    word('<>', 2, 1, unequal)

    for name, want_min in (('MIN', True), ('MAX', False)):
        def minmax(want_min=want_min):
            other, done = c.label('minmax_other'), c.label('minmax_done')
            c.ops(Op.OVER, Op.OVER, Op.LTS)
            c.jz(other)
            c.ops(Op.DROP if want_min else Op.NIP)
            c.jump(done)
            c.mark(other)
            c.ops(Op.NIP if want_min else Op.DROP)
            c.mark(done)
        word(name, 2, 1, minmax)
    word('TRUE', 0, 1, lambda: c.push(0xFFFF))
    word('FALSE', 0, 1, lambda: c.push(0))

    for name, opcode in (('LSHIFT', Op.SL), ('RSHIFT', Op.SR)):
        def shift(opcode=opcode):
            loop, done = c.label('shift_loop'), c.label('shift_done')
            c.ops(Op.DUP)
            c.push(16)
            c.ops(Op.LTU)
            c.jz('error_shift')
            c.mark(loop)
            c.ops(Op.DUP)
            c.jz(done)
            c.ops(Op.SWAP, opcode, Op.SWAP)
            c.push(1)
            c.ops(Op.SUB)
            c.jump(loop)
            c.mark(done)
            c.ops(Op.DROP)
        word(name, 2, 1, shift)

    def add_store():
        c.ops(Op.DUP, Op.FETCH, Op.ROT, Op.ADD, Op.SWAP, Op.STORE)
    word('+!', 2, 0, add_store)

    def multiply():
        loop, skip, done = (c.label('multiply_' + x) for x in ('loop', 'skip', 'done'))
        c.store('arith_b')
        c.store('arith_a')
        c.push(0)
        c.store('arith_q')
        c.mark(loop)
        c.load('arith_b')
        c.jz(done)
        c.load('arith_b')
        c.push(1)
        c.ops(Op.AND)
        c.jz(skip)
        c.load('arith_q')
        c.load('arith_a')
        c.ops(Op.ADD)
        c.store('arith_q')
        c.mark(skip)
        c.load('arith_a')
        c.ops(Op.SL)
        c.store('arith_a')
        c.load('arith_b')
        c.ops(Op.SR)
        c.store('arith_b')
        c.jump(loop)
        c.mark(done)
        c.load('arith_q')
    word('*', 2, 1, multiply)

    for name, give, after in (('/MOD', 2, ()), ('/', 1, (Op.NIP,)),
                               ('MOD', 1, (Op.DROP,))):
        def divide(after=after):
            c.call('signed_divmod')
            c.ops(*after)
        word(name, 2, give, divide)

    def key():
        c.call('raw_key')
    word('KEY', 0, 1, key)
    def emit():
        c.emit()
    word('EMIT', 1, 0, emit)
    word('CR', 0, 0, lambda: c.output(b'\r\n'))
    word('SPACE', 0, 0, lambda: c.output(b' '))

    # Shared private routine. Inputs/outputs are raw; public wrappers own DEPTH.
    c.mark('signed_divmod')
    c.store('arith_b')
    c.store('arith_a')
    c.load('arith_b')
    c.jz('error_division_zero')
    safe = c.label('division_safe')
    c.load('arith_a')
    c.push(0x8000)
    c.ops(Op.SUB)
    c.boolean_zero()
    c.load('arith_b')
    c.push(0xFFFF)
    c.ops(Op.SUB)
    c.boolean_zero()
    c.ops(Op.AND)
    c.jz(safe)
    c.jump('error_division_overflow')
    c.mark(safe)
    c.load('arith_a')
    c.push(0x8000)
    c.ops(Op.AND)
    c.store('arith_rsign')
    c.load('arith_a')
    c.load('arith_b')
    c.ops(Op.XOR)
    c.push(0x8000)
    c.ops(Op.AND)
    c.store('arith_qsign')
    for slot in ('arith_a', 'arith_b'):
        c.load(slot)
        absolute()
        c.store(slot)
    c.call('unsigned_divide')
    for value, sign in (('arith_q', 'arith_qsign'), ('arith_rem', 'arith_rsign')):
        positive = c.label('division_positive')
        c.load(sign)
        c.jz(positive)
        c.load(value)
        c.negate()
        c.store(value)
        c.mark(positive)
    c.load('arith_rem')
    c.load('arith_q')
    c.ops(Op.NOP | 0x80)

    # Private unsigned division: a=0..65535, b=1..32768, results in q/rem.
    # Larger divisors would require a 17-bit remainder. No public UM/MOD yet.
    c.mark('unsigned_divide')
    for slot in ('arith_q', 'arith_rem'):
        c.push(0)
        c.store(slot)
    c.push(16)
    c.store('arith_count')
    loop, subtract, next_bit = (c.label('division_' + x)
                               for x in ('loop', 'subtract', 'next'))
    c.mark(loop)
    c.load('arith_rem')
    c.ops(Op.SL)
    c.load('arith_a')
    c.push(0)
    c.ops(Op.LTS)
    c.push(1)
    c.ops(Op.AND, Op.OR)
    c.store('arith_rem')
    for slot in ('arith_a', 'arith_q'):
        c.load(slot)
        c.ops(Op.SL)
        c.store(slot)
    c.load('arith_rem')
    c.load('arith_b')
    c.ops(Op.LTU)
    c.jz(subtract)
    c.jump(next_bit)
    c.mark(subtract)
    c.load('arith_rem')
    c.load('arith_b')
    c.ops(Op.SUB)
    c.store('arith_rem')
    c.load('arith_q')
    c.push(1)
    c.ops(Op.OR)
    c.store('arith_q')
    c.mark(next_bit)
    c.load('arith_count')
    c.push(1)
    c.ops(Op.SUB, Op.DUP)
    c.store('arith_count')
    finished = c.label('division_finished')
    c.jz(finished)
    c.jump(loop)
    c.mark(finished)
    c.ops(Op.NOP | 0x80)

    # Small entry stubs select a message; all errors share recovery and output.
    for name, (number, message) in ERRORS.items():
        c.mark('error_' + name)
        c.set_cell('last_error', number)
        c.set_cell('print_addr', 'error_message_' + name)
        c.set_cell('print_left', len(message))
        c.jump('error_report')

    c.mark('error_report')
    # Roll back before clearing definition_open; preserve the token until printed.
    c.call('rollback_definition')
    for slot in ('depth', 'state', 'control_depth', 'definition_open'):
        c.set_cell(slot, 0)
    c.output(b'error: ')
    c.call('print_span')
    token, finish = c.label('error_token'), c.label('error_finish')
    for name in ('unknown', 'compile_only'):
        c.load('last_error')
        c.push(ERRORS[name][0])
        c.ops(Op.SUB)
        c.jz(token)
    c.jump(finish)
    c.mark(token)
    c.output(b' ')
    c.call('print_token')
    c.mark(finish)
    c.output(b'\r\n')
    for slot in ('input_length', 'input_pos', 'token_addr', 'token_length'):
        c.set_cell(slot, 0)
    c.mark('error_exit')
    c.jump('idle')  # Abandon all call frames; never return through old ones.

    # Literal data, deliberately excluded from the instruction disassembly.
    for name, (_, message) in ERRORS.items():
        c.mark('error_message_' + name)
        image.emit(message.encode('ascii'))
