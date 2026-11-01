"""Cold start and kernel composition for the on-CPU Forth console."""
from prim.isa import PrimOpcodes as Op

from forth.image import KERNEL_START, USER_LIMIT, Ref
from forth.kernel.primitives import emit_primitives
from forth.kernel.parser import emit_parser
from forth.kernel.console import emit_console
from forth.kernel.compiler import emit_compiler
from forth.kernel.control import emit_control
from forth.kernel.data import emit_data
from forth.kernel.io import IO_VARIABLES, emit_io
from forth.kernel.interrupts import IRQ_VARIABLES, emit_interrupts
from forth.kernel.keyboard import KBD_VARIABLES, emit_keyboard
from forth.kernel.frontend import FRONT_VARIABLES, emit_frontend
from forth.kernel.see import SEE_NAMES, emit_see

# Private RAM layout. Keep addresses stable across profiles; skip_lf is only
# emitted/initialized for UART polling, since dual editors have per-source state.
VARIABLES = {
    name: 0x0100 + 2 * index
    for index, name in enumerate((
        'here', 'latest', 'base', 'state', 'depth',
        'input_length', 'input_pos', 'string_length', 'control_depth',
        'definition_open', 'saved_here', 'saved_latest', 'pending_header',
        'last_opcode', 'last_end', 'fold_safe', 'skip_lf',
        'token_addr', 'token_length', 'last_error',
        'io_char', 'line_error', 'number_pos', 'number_left', 'number_base',
        'number_negative', 'number_acc', 'number_overflow', 'number_digit',
        'number_sum', 'number_count', 'number_status', 'number_value',
        'find_header', 'find_index', 'found_header', 'found_xt', 'found_flags',
        'print_addr', 'print_left', 'format_count', 'dump_count', 'dump_index',
        'word_cursor',
        'last_kind', 'emit_value', 'compiler_needed', 'compile_value',
        'compiler_index',
        'control_type', 'control_addr', 'control_slot', 'control_patch',
        'data_kind', 'data_value', 'string_addr', 'string_index', 'string_code_addr',
        *SEE_NAMES,
    ))
}


def emit_kernel(image):
    dual = getattr(image, 'dual_console', False)
    variables = {name: address for name, address in VARIABLES.items()
                 if not dual or name != 'skip_lf'}
    for name, address in variables.items():
        image.define(name, address)
    if dual:
        for name, address in {**IO_VARIABLES, **IRQ_VARIABLES, **KBD_VARIABLES, **FRONT_VARIABLES}.items():
            image.define(name, address)
    for name, address in {
        'input_buffer': 0x0200, 'string_buffer': 0x0280,
        'control_stack': 0x0300, 'scratch': 0x0380,
        'uart_csr': 0xFFFE, 'uart_data': 0xFFFF,
        'user_limit': USER_LIMIT,
        'digit_buffer': 0x038E, 'stack_buffer': 0x03A0,
    }.items():
        image.define(name, address)

    image.org(0)
    image.define('entry')
    image.push(Ref('cold_start'))
    image.op(Op.JP)

    image.org(KERNEL_START)
    image.define('cold_start')
    image.op(Op.INTDI)
    image.push(0)
    image.push(Ref('uart_csr'))
    image.op(Op.BYTE_STORE)

    for name in variables:
        initial = {'base': 10, 'here': Ref('user_start'),
                   'latest': Ref('kernel_latest')}.get(name, 0)
        image.push(initial)
        image.push(Ref(name))
        image.op(Op.STORE)
    for name in ('input_buffer', 'string_buffer'):
        image.push(0)
        image.push(Ref(name))
        image.op(Op.BYTE_STORE)

    if dual:
        for name in (*IO_VARIABLES, *IRQ_VARIABLES, *KBD_VARIABLES, *FRONT_VARIABLES):
            image.push(0)
            image.push(Ref(name))
            image.op(Op.STORE)
        image.push(Ref('irq_init'))
        image.op(Op.CALL)

    # Non-returning entry also used after errors/ABORT; no stale frames resumed.
    image.define('idle')
    if dual:
        image.push(Ref('timer_cancel'))
        image.op(Op.CALL)
    image.push(Ref('console_start'))
    image.op(Op.JP)
    emit_primitives(image)
    emit_parser(image)
    emit_console(image)
    emit_compiler(image)
    emit_control(image)
    emit_data(image)
    emit_see(image)
    # Keep the core vocabulary older than the hardware extensions in the
    # dictionary; WORDS traverses these entries newest first.
    if dual:
        emit_io(image)
        emit_interrupts(image)
        emit_keyboard(image)
        emit_frontend(image)
    image.define('kernel_end')
    image.define('kernel_latest', image.symbols[image.words[-1]['header']])
    user_start = (image.pc + 1) & ~1
    if dual and user_start >= 0xE000:
        raise ValueError('dual-console kernel must reside below banked VRAM')
    if user_start >= USER_LIMIT:
        raise ValueError('kernel leaves no user dictionary space')
    image.define('user_start', user_start)
