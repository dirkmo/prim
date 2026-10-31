"""Shared CPU-session fixtures and independent expected-value helpers."""
from collections import deque
from forth.image import Image, USER_LIMIT
from forth.kernel.boot import VARIABLES
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op
from support.reference import Memory

def stack_delta(op):
    return (1 if op in (Op.PUSH, Op.PUSH8, Op.DUP, Op.OVER, Op.CARRY, Op.FROM_R)
            else -2 if op in (Op.JZ, Op.STORE, Op.BYTE_STORE)
            else -1 if op in (Op.CALL, Op.JP, Op.AND, Op.OR, Op.XOR,
                             Op.ADD, Op.SUB, Op.LTS, Op.LTU, Op.NIP,
                             Op.DROP, Op.TO_R, Op.INTAD) else 0)


def signed(n):
    return n if n < 0x8000 else n - 65536


class UartMemory(Memory):
    def __init__(self, image, rx=()):
        super().__init__(image, uart=True)
        self.rx = deque(rx)
        self.polls = self.consumed = 0

    def read8(self, address):
        if address == 0xFFFE:
            self.polls += 1
            value = 2 | (bool(self.rx) and self.polls >= 5)
            self.reads.append([address, value])
            return value
        if address == 0xFFFF:
            if self.polls < 5 or not self.rx:
                raise AssertionError('RX read before RXAVAIL')
            value = self.rx.popleft()
            self.consumed += 1
            self.reads.append([address, value])
            return value
        return super().read8(address)


class Runner:
    def __init__(self, image, inputs=(), rx=()):
        self.image = image
        self.memory = UartMemory(image.memory, rx)
        self.cpu = Prim(self.memory)
        self.words = {word['name']: image.symbols[word['xt']] for word in image.words}
        self.max_data = self.max_return = self.max_extra = 0
        self.initial = len(inputs)
        for _ in range(500):
            if self.cpu._pc == image.symbols['idle']:
                break
            self.cpu.step()
        else:
            raise AssertionError('boot timeout')
        for value in inputs:
            self.cpu.dpush(value)
        self.memory.write16(VARIABLES['depth'], len(inputs))
        self.memory.writes.clear()
        self.base = self.cpu._dsp - len(inputs)

    def call(self, word, limit=10000):
        return self.invoke(self.words[word], word, limit)

    def invoke(self, target, word='private routine', limit=200000):
        program = Image()
        program.org(USER_LIMIT)  # Reserved RAM, outside the compiling dictionary.
        program.push(target)
        program.op(Op.CALL)
        program.op(Op.BREAK)
        start, end = USER_LIMIT, program.pc
        self.memory.data[start:end] = program.memory[start:end]
        self.cpu._pc = start
        physical_depth = self.memory.read16(VARIABLES['depth'])
        entry_depth = physical_depth
        for step in range(limit):
            if self.cpu._pc == self.image.symbols['idle']:
                return False  # Error abandons the current invocation.
            opcode = self.memory.data[self.cpu._pc]
            if opcode == Op.BREAK:
                return True
            op = opcode & 127
            physical_depth += stack_delta(op)
            if not 0 <= physical_depth <= 16:
                raise AssertionError(f'physical stack violation in {word}: {physical_depth}')
            self.max_data = max(self.max_data, physical_depth)
            self.max_extra = max(self.max_extra, physical_depth - entry_depth)
            self.cpu.step()
            self.max_return = max(self.max_return, self.cpu._rsp)
        raise AssertionError(f'timeout in {word}')

    def values(self):
        depth = self.memory.read16(VARIABLES['depth'])
        return [self.cpu._ds[(self.cpu._dsp - depth + 1 + n) % 16]
                for n in range(depth)]


def formatted(value, base, signed=False):
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    negative = signed and value >= 32768
    if negative:
        value = 65536 - value
    text = ''
    while value:
        value, digit = divmod(value, base)
        text = alphabet[digit] + text
    return ('-' if negative else '') + (text or '0')


def session(image, payload, prepare=None):
    memory = UartMemory(image.memory, payload)
    cpu = Prim(memory)
    physical = frames = max_data = max_frames = 0
    for steps in range(2000000):
        if cpu._pc in (image.symbols['console_next'], image.symbols['raw_key']) and not memory.rx:
            depth = memory.read16(VARIABLES['depth'])
            values = [cpu._ds[(cpu._dsp - depth + 1 + n) % 16] for n in range(depth)]
            return bytes(memory.tx), values, memory, (max_data, max_frames)
        if cpu._pc == image.symbols['idle']:
            if prepare:
                prepare(memory)
                prepare = None
            # Cold/error/ABORT entry abandons physical cells and frames;
            # pointers need not become zero to establish an empty stack base.
            physical = frames = 0
        opcode = memory.data[cpu._pc]
        op = opcode & 127
        physical += stack_delta(op)
        frames += int(op == Op.CALL)
        if opcode & 128 and op not in (Op.CALL, Op.JP, Op.JZ):
            frames -= 1
        if not (0 <= physical <= 16 and 0 <= frames <= 16):
            raise AssertionError(f'stack budget at {cpu._pc:04x}: DS={physical}, RS={frames}')
        max_data, max_frames = max(max_data, physical), max(max_frames, frames)
        cpu.step()
        memory.reads.clear()  # Long formatting sessions need no retained bus log.
    raise AssertionError('console timeout')


def cell(memory, address):
    data = memory.data if hasattr(memory, 'data') else memory
    return int.from_bytes(data[address:address + 2], 'little')


def lookup(memory, name):
    data = memory.data if hasattr(memory, 'data') else memory
    header = cell(data, VARIABLES['latest'])
    while header:
        length = data[header + 3]
        if bytes(data[header + 8:header + 8 + length]).upper() == name.upper().encode():
            return header, cell(data, header + 4)
        header = cell(data, header)
    raise AssertionError(f'missing dictionary entry: {name}')
