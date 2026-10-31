"""Small relocatable image emitter, independent of TokenForth."""
from dataclasses import dataclass

from prim.assembler import PrimAsm
from prim.isa import PrimOpcodes as Op

RAM_END = 0xFFF0
USER_LIMIT = 0xF000
KERNEL_START = 0x0400


@dataclass(frozen=True)
class Ref:
    name: str


class Image:
    def __init__(self):
        self.memory = bytearray(RAM_END)
        self.symbols = {}
        self.labels = {}
        self.pc = 0
        self.instructions = []
        self.relocations = []
        self.occupied = set()
        self.words = []

    def define(self, name, value=None):
        if name in self.symbols:
            raise ValueError(f'duplicate symbol: {name}')
        if value is None:
            self.labels[name] = self.pc
        value = self.pc if value is None else value
        if not 0 <= value <= 0xFFFF:
            raise ValueError(f'symbol outside address space: {name}')
        self.symbols[name] = value

    def org(self, address):
        if not 0 <= address < RAM_END:
            raise ValueError('origin outside RAM')
        self.pc = address

    def emit(self, data):
        data = bytes(data)
        end = self.pc + len(data)
        if end > RAM_END:
            raise ValueError('image crosses MMIO boundary')
        if any(at in self.occupied for at in range(self.pc, end)):
            raise ValueError('overlapping image sections')
        self.memory[self.pc:end] = data
        self.occupied.update(range(self.pc, end))
        self.pc = end

    def op(self, opcode):
        self.instructions.append(self.pc)
        self.emit([opcode])

    def push(self, value):
        self.instructions.append(self.pc)
        if isinstance(value, Ref):
            self.relocations.append((self.pc + 1, value.name))
            self.emit([Op.PUSH, 0, 0])
        elif 0 <= value <= 0xFF:
            self.emit([Op.PUSH8, value])
        elif 0 <= value <= 0xFFFF:
            self.emit([Op.PUSH, value & 0xFF, value >> 8])
        else:
            raise ValueError('literal outside 16-bit range')

    def cell(self, value):
        """Emit a data cell (possibly relocated), never an instruction."""
        if isinstance(value, Ref):
            self.relocations.append((self.pc, value.name))
            self.emit([0, 0])
        else:
            self.emit(value.to_bytes(2, 'little'))

    def resolve(self):
        # Validate all references before patching any operand.
        for _, name in self.relocations:
            if name not in self.symbols:
                raise ValueError(f'undefined symbol: {name}')
        for address, name in self.relocations:
            self.memory[address:address + 2] = self.symbols[name].to_bytes(2, 'little')

    def disassembly(self):
        labels = {}
        for name, address in self.labels.items():
            labels.setdefault(address, []).append(name)
        lines = ['; Executable instructions only; data/reserved RAM omitted.']
        for address in self.instructions:
            if address in labels:
                lines.append(f"{address:04x} <{', '.join(sorted(labels[address]))}>:")
            opcode = self.memory[address] & 0x7F
            size = 3 if opcode == Op.PUSH else 2 if opcode == Op.PUSH8 else 1
            data = self.memory[address:address + size]
            _, _, assembly = PrimAsm.disassemble(data, address)[0]
            lines.append(f'{address:04x}: {data.hex(" "):<8}  {assembly}')
        return '\n'.join(lines) + '\n'
