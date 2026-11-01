"""Build-time checks for the fixed Forth RAM allocations (exclusive ends)."""
from forth.image import KERNEL_START, USER_LIMIT, RAM_END


def check_spans(spans, lower, upper):
    """Validate independent allocations inside their containing RAM region."""
    previous = None
    for name, start, end in sorted(spans, key=lambda item: item[1]):
        if not lower <= start < end <= upper:
            raise ValueError(f'RAM layout: {name} [{start:#06x}, {end:#06x}) '
                             f'outside [{lower:#06x}, {upper:#06x})')
        if previous is not None and start < previous[2]:
            raise ValueError(f'RAM layout overlap: {previous[0]} and {name}')
        previous = (name, start, end)


def validate_static_layout(image):
    # Import here to keep boot's declaration table independent of this checker.
    from forth.kernel.boot import VARIABLES
    from forth.kernel.primitives import ARITHMETIC
    from forth.kernel.io import IO_VARIABLES
    from forth.kernel.interrupts import IRQ_VARIABLES, RINGS, RING_SIZE
    from forth.kernel.keyboard import KBD_VARIABLES
    from forth.kernel.frontend import FRONT_VARIABLES, LINES, BUFFER

    def cells(names):
        result = []
        for name in names:
            address = image.symbols[name]
            if address & 1:
                raise ValueError(f'RAM layout: unaligned cell {name} at {address:#06x}')
            result.append((name, address, address + 2))
        return result

    dual = getattr(image, 'dual_console', False)
    names = [name for name in VARIABLES if name != 'skip_lf' or not dual]
    check_spans(cells(names), 0x100, 0x200)
    buffers = [(name, image.symbols[name], image.symbols[name] + size)
               for name, size in (('input_buffer', 128), ('string_buffer', 128),
                                  ('control_stack', 32 * 4), ('digit_buffer', 16),
                                  ('stack_buffer', 32 * 2))]
    for name, lower, upper in (('input_buffer', 0x200, 0x280),
                                ('string_buffer', 0x280, 0x300),
                                ('control_stack', 0x300, 0x380)):
        check_spans([span for span in buffers if span[0] == name], lower, upper)
    # Before emission these symbols do not exist yet; afterwards inspect the
    # emitted addresses as well as the declaration table.
    for name, address in ARITHMETIC.items():
        address = image.symbols.get('arith_' + name, address)
        if address & 1:
            raise ValueError(f'RAM layout: unaligned arithmetic cell {name}')
        buffers.append(('arith_' + name, address, address + 2))
    check_spans(buffers, 0x200, KERNEL_START)
    if image.symbols['scratch'] != 0x380:
        raise ValueError('RAM layout: scratch base must be 0x0380')
    if dual:
        runtime = cells((*IO_VARIABLES, *IRQ_VARIABLES, *KBD_VARIABLES, *FRONT_VARIABLES))
        runtime += [(name + '_ring', base, base + 6 + RING_SIZE)
                    for name, base in RINGS.items()]
        runtime += [(f'line_{index}', base, base + BUFFER + 128)
                    for index, base in enumerate(LINES)]
        check_spans(runtime, USER_LIMIT, 0xF400)


def regions(image):
    return [
        ('boot', 0, 0x0100), ('variables', 0x0100, 0x0200),
        ('input', 0x0200, 0x0280), ('string', 0x0280, 0x0300),
        ('control', 0x0300, 0x0380), ('scratch', 0x0380, KERNEL_START),
        ('kernel', KERNEL_START, image.symbols['kernel_end']),
        ('alignment', image.symbols['kernel_end'], image.symbols['user_start']),
        ('user', image.symbols['user_start'], USER_LIMIT),
        *([('console_runtime', USER_LIMIT, 0xF400), ('reserved', 0xF400, RAM_END)]
          if image.dual_console else [('reserved', USER_LIMIT, RAM_END)]),
        ('mmio', RAM_END, 0x10000),
    ]


def validate_layout(image):
    validate_static_layout(image)
    spans = regions(image)
    # Alignment may be empty; all other regions must be nonempty.
    check_spans([span for span in spans if span[0] != 'alignment' or span[1] != span[2]],
                0, 0x10000)
    for left, right in zip(spans, spans[1:]):
        if left[2] != right[1]:
            raise ValueError(f'RAM layout gap: {left[0]} and {right[0]}')
    if image.symbols['user_start'] & 1:
        raise ValueError('RAM layout: unaligned user dictionary')
    if image.dual_console and image.symbols['user_start'] >= 0xE000:
        raise ValueError('RAM layout: kernel crosses banked VRAM window')
    end = image.symbols['kernel_end']
    if any(not (0 <= address < 0x100 or KERNEL_START <= address < end)
           for address in image.occupied):
        raise ValueError('RAM layout: emitted code/data outside boot/kernel regions')
