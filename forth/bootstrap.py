"""Compile kernel Forth with the real target compiler, then seal its dictionary."""
from pathlib import Path

from prim.cpu import MemoryIf, Prim
from prim.isa import PrimOpcodes as Op
from forth.image import USER_LIMIT
from forth.kernel.boot import VARIABLES

CORE_SOURCE = Path(__file__).parent / 'kernel/core.fs'
# Stack contracts are metadata for maps/verification; definitions live in core.fs.
CORE_EFFECTS = {'2DUP': (2, 4), '2DROP': (2, 0), '1+': (1, 1), '1-': (1, 1),
                'CELL+': (1, 1), 'NEGATE': (1, 1), 'SPACE': (0, 0), 'CR': (0, 0)}


class BuildMemory(MemoryIf):
    """Flat build-time RAM and output capture; no peripheral events or host Forth."""
    def __init__(self, data):
        self.data = bytearray(65536)
        self.data[:len(data)] = data
        self.output = bytearray()
        self.peripheral_writes = []

    def read8(self, address):
        return self.data[address & 65535]

    def read16(self, address):
        return self.read8(address) | self.read8(address + 1) << 8

    def write8(self, address, value):
        if address == 0xFFFF:
            self.output.append(value & 127)
        else:
            if address >= 0xFFE0:
                self.peripheral_writes.append((address, value & 255))
            self.data[address & 65535] = value & 255

    def write16(self, address, value):
        self.write8(address, value)
        self.write8(address + 1, value >> 8)


def compile_core(image, source=CORE_SOURCE, *, sources=None):
    sources = [(Path(source), CORE_EFFECTS)] if sources is None else sources
    memory = BuildMemory(image.memory)
    cpu = Prim(memory)
    for _ in range(2000):
        if cpu._pc == image.symbols['idle']:
            break
        cpu.step()
    else:
        raise ValueError('kernel bootstrap: cold-start timeout')

    def get(name):
        return memory.read16(VARIABLES[name])

    def put(name, value):
        memory.write16(VARIABLES[name], value)

    start, previous = get('here'), get('latest')
    memory.peripheral_writes.clear()  # Cold-start initialization is intentional.
    locations = {}
    contracts = {}
    for source, effects in sources:
        source = Path(source)
        if contracts.keys() & effects.keys():
            raise ValueError(f'{source}: duplicate library stack contracts')
        contracts.update(effects)
        for line_number, line in enumerate(source.read_bytes().splitlines(), 1):
            if len(line) > 127 or any((b < 32 and b not in (9, 11, 12)) or b > 126 for b in line):
                raise ValueError(f'{source}:{line_number}: invalid kernel source line')
            memory.data[0x200:0x200 + len(line) + 1] = line + b'\0'
            put('input_length', len(line))
            for name in ('input_pos', 'token_addr', 'token_length', 'last_error'):
                put(name, 0)
            memory.output.clear()
            old_latest = get('latest')
            cpu._pc = image.symbols['interpret_line']
            for _ in range(200000):
                if cpu._pc == image.symbols['idle']:
                    detail = memory.output.decode('ascii', errors='replace').strip()
                    raise ValueError(f'{source}:{line_number}: {detail or "bootstrap aborted"}')
                if cpu._pc == image.symbols['console_next']:
                    break
                cpu.step()
            else:
                raise ValueError(f'{source}:{line_number}: bootstrap instruction limit')
            cursor, new_headers = get('latest'), set()
            while cursor != old_latest:
                if not start <= cursor < get('here') or cursor in new_headers:
                    raise ValueError(f'{source}:{line_number}: corrupted dictionary chain')
                new_headers.add(cursor)
                locations.setdefault(cursor, (source, line_number))
                cursor = memory.read16(cursor)
        if get('definition_open') or get('state') or get('control_depth') or get('depth'):
            raise ValueError(f'{source}: incomplete definition or nonempty build stack')
        if memory.peripheral_writes:
            raise ValueError(f'{source}: library initialization wrote peripheral registers')

    end, header = get('here'), get('latest')
    user_start = (end + 1) & ~1
    if end <= start or user_start >= (0xE000 if image.dual_console else USER_LIMIT):
        raise ValueError('kernel bootstrap leaves no valid dictionary space')
    entries, seen = [], set()
    while header != previous:
        if not start <= header < end or header in seen:
            raise ValueError('kernel bootstrap corrupted dictionary chain')
        seen.add(header)
        length = memory.read8(header + 3)
        name = bytes(memory.data[header + 6:header + 6 + length]).decode('ascii')
        entries.append((header, memory.read16(header + 4), name, memory.read8(header + 2)))
        header = memory.read16(header)
    if {name for _, _, name, _ in entries} != set(contracts) or len(entries) != len(contracts):
        raise ValueError('kernel source words do not match their stack contracts')

    image.memory[start:end] = memory.data[start:end]
    image.occupied.update(range(start, end))
    entries.reverse()
    for index, (header, xt, name, flags) in enumerate(entries):
        serial = len(image.words)
        hs, xs = f'header_{serial}', f'xt_{serial}'
        image.define(hs, header)
        image.define(xs, xt)
        image.labels[xs] = xt
        need, give = contracts[name]
        word_source, line_number = locations[header]
        try:
            source_name = word_source.resolve().relative_to(Path(__file__).resolve().parents[1]).as_posix()
        except ValueError:
            source_name = str(word_source)
        image.words.append({'name': name, 'header': hs, 'xt': xs, 'need': need,
                            'give': give, 'flags': flags, 'source': source_name,
                            'source_line': line_number})
        limit = entries[index + 1][0] if index + 1 < len(entries) else end
        pc, pushed = xt, None
        while pc < limit:
            image.instructions.append(pc)
            raw = image.memory[pc]
            opcode = raw & 127
            size = 3 if opcode == Op.PUSH else 2 if opcode == Op.PUSH8 else 1
            next_pc = pc + size
            if next_pc > limit:
                raise ValueError(f'{word_source}: truncated instruction in {name}')
            if opcode == Op.JP and pushed is not None:
                if not xt <= pushed < limit:
                    break  # Tail call, followed by padding or a data body.
                # String emission jumps over bytes, followed by a PUSH of their
                # address (possibly after the literal-depth helper call).
                if next_pc < pushed and pushed + 3 <= limit:
                    direct = memory.read8(pushed) == Op.PUSH and memory.read16(pushed + 1) == next_pc
                    literal = (pushed + 7 <= limit
                               and memory.read8(pushed) == Op.PUSH
                               and memory.read16(pushed + 1) == image.symbols['literal_depth']
                               and memory.read8(pushed + 3) == Op.CALL
                               and memory.read8(pushed + 4) == Op.PUSH
                               and memory.read16(pushed + 5) == next_pc)
                    if direct or literal:
                        next_pc = pushed
            if raw & 128 and opcode not in (Op.CALL, Op.JP, Op.JZ):
                break
            pushed = (int.from_bytes(image.memory[pc + 1:pc + size], 'little')
                      if opcode in (Op.PUSH, Op.PUSH8) else None)
            pc = next_pc

    image.pc = end
    image.symbols.update(kernel_end=end, kernel_latest=entries[-1][0], user_start=user_start)
    image.labels['kernel_end'] = end
    image.resolve()  # Patch cold boot and kernel bounds to the sealed dictionary.
