"""Cold start and kernel composition; idle awaits the later text console."""
from prim.isa import PrimOpcodes as Op

from forth.image import KERNEL_START, USER_LIMIT, Ref
from forth.kernel.primitives import emit_primitives

# Private RAM cells; public Forth words will expose selected cells later.
VARIABLES = {
    name: 0x0100 + 2 * index
    for index, name in enumerate((
        'here', 'latest', 'base', 'state', 'depth',
        'input_length', 'input_pos', 'string_length', 'control_depth',
        'definition_open', 'saved_here', 'saved_latest', 'pending_header',
        'last_opcode', 'last_end', 'fold_safe', 'skip_lf',
        'token_addr', 'token_length', 'last_error',
    ))
}


def emit_kernel(image):
    for name, address in VARIABLES.items():
        image.define(name, address)
    for name, address in {
        'input_buffer': 0x0200, 'string_buffer': 0x0280,
        'control_stack': 0x0300, 'scratch': 0x0380,
        'uart_csr': 0xFFFE, 'uart_data': 0xFFFF,
        'user_limit': USER_LIMIT,
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

    for name in VARIABLES:
        initial = {'base': 10, 'here': Ref('user_start'),
                   'latest': Ref('kernel_latest')}.get(name, 0)
        image.push(initial)
        image.push(Ref(name))
        image.op(Op.STORE)
    for name in ('input_buffer', 'string_buffer'):
        image.push(0)
        image.push(Ref(name))
        image.op(Op.BYTE_STORE)

    # No CALL frames, UART input/output, or debugger halt in the shipped image.
    image.define('idle')
    image.push(Ref('idle'))
    image.op(Op.JP)
    emit_primitives(image)
    image.define('kernel_end')
    image.define('kernel_latest', image.symbols[image.words[-1]['header']])
    user_start = (image.pc + 1) & ~1
    if user_start >= USER_LIMIT:
        raise ValueError('kernel leaves no user dictionary space')
    image.define('user_start', user_start)
