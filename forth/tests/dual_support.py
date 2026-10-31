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
        if self.cpu._pc == self.image.symbols['idle']:
            self.physical = self.get('depth')
            self.frames = 0  # Errors/ABORT abandon the old call frames.
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


class DualSession(DualRunner):
    def __init__(self):
        super().__init__()
        self.uart_wire, self.ps2_wire = deque(), deque()
        self.clock = 0
        self.until(lambda: self.cpu._pc == self.image.symbols['read_line'] and self.get('console_initialized'))

    def step(self):
        # Host UART credit and physical keyboard pacing are independent. The
        # hardware slot/FIFO still have finite capacities; no model-side decoder.
        if hasattr(self, 'clock'):
            self.clock += 1
            if self.uart_wire and not self.memory.uart_rx and self.clock % 500 == 0:
                self.memory.receive_uart(self.uart_wire.popleft())
            if self.ps2_wire and self.clock % 1000 == 0:
                self.memory.receive_ps2(self.ps2_wire.popleft())
        super().step()

    def uart(self, text):
        self.uart_wire.extend(text.encode() if isinstance(text, str) else text)

    def keyboard(self, text):
        # Fixture encoding only; expected text/results are literal in tests.
        # Decoder correctness itself is checked by independent scan sequences.
        from forth.kernel.keyboard import key_tables
        normal, shifted, altgr = key_tables()
        for byte in text.encode() if isinstance(text, str) else text:
            if byte in normal and byte:
                self.ps2_wire.append(normal.index(byte))
            elif byte in shifted and byte:
                self.ps2_wire.extend([0x12, shifted.index(byte), 0xF0, 0x12])
            elif byte in altgr and byte:
                self.ps2_wire.extend([0xE0, 0x11, altgr.index(byte), 0xE0, 0xF0, 0x11])
            else:
                raise ValueError(f'fixture cannot encode {byte}')

    def drained(self):
        return (not self.uart_wire and not self.ps2_wire and not self.memory.uart_rx
                and not self.memory.ps2_rx
                and self.memory.read16(0xF100) == self.memory.read16(0xF102)
                and self.memory.read16(0xF180) == self.memory.read16(0xF182))

    def quiet(self):
        self.until(lambda: self.drained() and not self.memory.read16(0xF202)
                   and not self.memory.read16(0xF302)
                   and self.cpu._pc == self.image.symbols['irq_wait'], limit=2000000)

    def stack(self):
        depth = self.get('depth')
        return [self.cpu._ds[(self.cpu._dsp - depth + 1 + n) % 16] for n in range(depth)]


def run_tests():
    """Model suites share the integrated runner's --rtl option; no RTL claimed."""
    import unittest
    if '--rtl' in sys.argv:
        sys.argv.remove('--rtl')
    unittest.main()

