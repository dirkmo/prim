"""Python reference state and instruction-retirement comparison."""
from prim.cpu import Prim, MemoryIf
from prim.assembler import PrimAsm
from prim.isa import PrimOpcodes as Op

class Memory(MemoryIf):
    """64 KiB RAM; optionally map FFFD LEDs, FFFE status and FFFF UART data."""

    def __init__(self, image, uart=False):
        self.data = bytearray([0xff]) * 65536
        self.data[:len(image)] = image
        self.writes = []
        self.reads = []
        self.uart = uart
        self.tx = []
        self.leds = 0
        self.status_samples = iter(())

    def read8(self, addr):
        addr &= 0xffff
        value = self.data[addr]
        if self.uart and addr == 0xfffd:
            value = self.leds
        elif self.uart and addr == 0xfffe:
            value = next(self.status_samples, 2) & 2
        elif self.uart and addr == 0xffff:
            value = 0
        self.reads.append([addr, value])
        return value

    def read16(self, addr):
        return self.read8(addr) | self.read8(addr + 1) << 8

    def write8(self, addr, value):
        addr, value = addr & 0xffff, value & 0xff
        if self.uart and addr == 0xfffd:
            self.leds = value & 3
        elif self.uart and addr == 0xffff:
            self.tx.append(value & 0x7f)
        elif not (self.uart and addr == 0xfffe):
            self.data[addr] = value
        self.writes.append([addr, value])

    def write16(self, addr, value):
        self.write8(addr, value)
        self.write8(addr + 1, value >> 8)


class Difference(AssertionError):
    pass


def compare_records(image, records, max_steps=1000, exit_code=0, uart=False, memory=None):
    """Check retirement records from either the C++ or the SRAM simulation."""
    memory = memory if memory is not None else Memory(image, uart=uart)
    cpu = Prim(memory)
    ds_depth = rs_depth = 0

    steps = 0
    for record in records:
        at = cpu._pc
        ir = memory.read8(at)
        label = f'step {steps + 1}, pc=0x{at:04x}, {PrimAsm.disassembleOpcode(ir)} (0x{ir:02x})'

        def equal(field, actual, expected):
            if actual != expected:
                raise Difference(f'{label}: {field}: RTL={actual!r}, Python={expected!r}')

        if ir in (Op.BREAK, Op.SIMEND):
            # Do not execute debugger markers. Both PCs still address the marker.
            equal('halt', record, {'kind': 'halt', 'pc': at, 'ir': ir})
            if record is not records[-1]:
                raise RuntimeError('Unexpected trace records after halt')
            return steps
        equal('kind', record['kind'], 'step')
        equal('at', record['at'], at)
        equal('ir', record['ir'], ir)
        if steps >= max_steps:
            raise RuntimeError(f'Instruction limit exceeded ({max_steps})')
        memory.writes.clear()
        memory.reads.clear()
        # TX-free is a timing-dependent peripheral input, checked separately in
        # RTL tests. Feed it into the ISA reference like other external input.
        memory.status_samples = iter(v for a, v in record['reads'] if a == 0xfffe)
        cpu.step()
        op = ir & 0x7f
        ds_delta = (1 if op in (Op.PUSH, Op.PUSH8, Op.DUP, Op.OVER, Op.CARRY, Op.FROM_R)
                    else -2 if op in (Op.JZ, Op.STORE, Op.BYTE_STORE)
                    else -1 if op in (Op.CALL, Op.JP, Op.AND, Op.OR, Op.XOR,
                                     Op.ADD, Op.SUB, Op.LTS, Op.LTU, Op.NIP,
                                     Op.DROP, Op.TO_R) else 0)
        rs_delta = (1 if op in (Op.CALL, Op.INT, Op.TO_R)
                    else -1 if op in (Op.FROM_R, Op.RDROP) else 0)
        ds_depth = min(16, max(0, ds_depth + ds_delta))
        rs_depth = min(16, max(0, rs_depth + rs_delta))
        # Apply push/pop and return in order, including saturation on overflow.
        if ir & 0x80 and op not in (Op.CALL, Op.JP, Op.JZ, Op.INT):
            rs_depth = max(0, rs_depth - 1)
        for field, expected in [('pc', cpu._pc), ('dsp', cpu._dsp),
                                ('rsp', cpu._rsp), ('carry', int(cpu._carry)),
                                ('reads', memory.reads),
                                ('writes', memory.writes)]:
            equal(field, record[field], expected)
        # Ignore unused cells: Python clears popped cells; hardware may retain them.
        equal('ds', record['ds'][:ds_depth],
              [cpu._ds[(cpu._dsp - i) % 16] for i in range(ds_depth)])
        equal('rs', record['rs'][:rs_depth],
              [cpu._rs[(cpu._rsp - i) % 16] for i in range(rs_depth)])
        steps += 1
    raise RuntimeError(f'RTL trace ended without a BREAK/SIMEND marker (exit {exit_code})')
