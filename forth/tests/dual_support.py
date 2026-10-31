"""Independent dual-console MMIO model and instruction-level kernel fixture."""
from collections import deque
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / 'src', ROOT / 'tests'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from forth.build import build_image
from forth.image import Image
from forth.tests.model import stack_delta
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op
from support.reference import Memory


class DualMemory(Memory):
    def __init__(self, image):
        super().__init__(image, uart=True)
        self.vram = bytearray(b' ' * 4096)
        self.video = bytearray(5)
        self.uart_rx = deque()
        self.ps2_rx = deque()
        self.ps2_ie = self.ps2_errors = self.pending = 0
        self.cpu = None

    def event(self, bit):
        self.pending |= bit
        if self.cpu:
            self.cpu.request_irq()

    def receive_uart(self, byte):
        self.uart_rx.clear()
        self.uart_rx.append(byte & 127)
        if self.uart_ie & 4:
            self.event(2)

    def receive_ps2(self, byte):
        if len(self.ps2_rx) == 16:
            self.ps2_errors |= 16
        else:
            self.ps2_rx.append(byte)
        if self.ps2_ie:
            self.event(8)

    def read8(self, address):
        address &= 65535
        if address == 0xFFF5:
            return self.pending
        if 0xFFF6 <= address <= 0xFFFA:
            return self.video[address - 0xFFF6] if address != 0xFFFA else 0
        if address == 0xFFFB:
            return self.ps2_ie | self.ps2_errors | bool(self.ps2_rx) | (2 if len(self.ps2_rx) == 16 else 0)
        if address == 0xFFFC:
            return self.ps2_rx.popleft() if self.ps2_rx else 0
        if address == 0xFFFE:
            return 2 | self.uart_ie | bool(self.uart_rx)
        if address == 0xFFFF:
            return self.uart_rx.popleft() if self.uart_rx else 0
        if 0xE000 <= address < 0xF000 and self.video[0] & 1:
            return self.vram[address - 0xE000]
        return super().read8(address)

    def write8(self, address, value):
        address, value = address & 65535, value & 255
        if address == 0xFFF5:
            self.pending &= ~value
        elif 0xFFF6 <= address <= 0xFFF9:
            self.video[address - 0xFFF6] = value
        elif address == 0xFFFA or address == 0xFFFC:
            pass
        elif address == 0xFFFB:
            old = self.ps2_ie
            self.ps2_ie = value & 4
            self.ps2_errors &= ~(value & 24)
            if self.ps2_ie and not old and (self.ps2_rx or self.ps2_errors or self.pending & 8):
                self.event(8)
        elif address == 0xFFFE:
            old = self.uart_ie
            self.uart_ie = value & 12
            if self.uart_ie & 4 and not old & 4 and (self.uart_rx or self.pending & 2):
                self.event(2)
        elif 0xE000 <= address < 0xF000 and self.video[0] & 1:
            self.vram[address - 0xE000] = value
        else:
            return super().write8(address, value)

    def screen(self):
        offset = self.video[1] & 31
        return b'\n'.join(bytes(self.vram[((row + offset) & 31) * 80:((row + offset) & 31) * 80 + 80])
                          for row in range(30))


class DualRunner:
    def __init__(self):
        self.image = build_image(dual_console=True)
        self.memory = DualMemory(self.image.memory)
        self.cpu = Prim(self.memory)
        self.memory.cpu = self.cpu
        self.physical = self.frames = self.max_data = self.max_frames = 0
        self.until(lambda: self.cpu._pc == self.image.symbols['idle'])

    def step(self):
        opcode = self.memory.data[self.cpu._pc]
        op = opcode & 127
        self.physical += stack_delta(op)
        self.frames += int(op in (Op.CALL, Op.INT, Op.TO_R)) - int(op in (Op.FROM_R, Op.RDROP))
        if opcode & 128 and op not in (Op.CALL, Op.JP, Op.JZ, Op.INT):
            self.frames -= 1
        self.cpu.step()
        if self.cpu._pc == self.image.symbols.get('irq_entry'):
            self.frames += 1
        if not (0 <= self.physical <= 16 and 0 <= self.frames <= 16):
            raise AssertionError(f'stack budget: DS={self.physical} RS={self.frames} PC={self.cpu._pc:04x}')
        self.max_data = max(self.max_data, self.physical)
        self.max_frames = max(self.max_frames, self.frames)
        self.memory.reads.clear()
        self.memory.writes.clear()

    def until(self, condition, limit=500000):
        for _ in range(limit):
            if condition():
                return
            self.step()
        raise AssertionError(f'timeout PC={self.cpu._pc:04x}')

    def set(self, name, value):
        self.memory.write16(self.image.symbols[name], value)

    def get(self, name):
        return self.memory.read16(self.image.symbols[name])

    def invoke(self, name, values=()):
        stub = Image()
        stub.org(0xFF80)
        stub.push(self.image.symbols[name])
        stub.op(Op.CALL)
        stub.op(Op.BREAK)
        self.memory.data[0xFF80:stub.pc] = stub.memory[0xFF80:stub.pc]
        for value in values:
            self.cpu.dpush(value)
            self.physical += 1
        self.cpu._pc = 0xFF80
        self.until(lambda: self.memory.data[self.cpu._pc] == Op.BREAK)

