#!/usr/bin/env python3
"""Execute the real Forth driver on Prim against an independent bank model."""
from io import BytesIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from forth.build import build_image
from forth.run import ConsoleMemory
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op


class VideoMemory(ConsoleMemory):
    def __init__(self, image, source):
        super().__init__(image, BytesIO(source), BytesIO())
        self.video = bytearray(b' ' * 4096)
        self.registers = bytearray(4)
        self.data[0xe000:0xf000] = b'Z' * 4096
        self.video_writes = 0

    def read8(self, address):
        if 0xfff6 <= address <= 0xfff9:
            return self.registers[address - 0xfff6]
        if 0xe000 <= address < 0xf000 and self.registers[0] & 1:
            return self.video[address - 0xe000]
        return super().read8(address)

    def write8(self, address, value):
        if 0xfff6 <= address <= 0xfff9:
            self.registers[address - 0xfff6] = value & (31, 31, 127, 31)[address - 0xfff6]
        elif 0xe000 <= address < 0xf000 and self.registers[0] & 1:
            self.video[address - 0xe000] = value & 255
            self.video_writes += 1
        else:
            super().write8(address, value)


def main():
    image = build_image()
    driver = (ROOT / 'vga/examples/console.fs').read_bytes()
    # 64 newlines scroll 35 times: the offset wraps 32; each scroll clears 80 bytes.
    commands = b'VGA-INIT\n' + b'VGA-CR\n' * 64
    commands += b'S" Hello" VGA-TYPE 8 VGA-EMIT 33 VGA-EMIT\n'
    memory = VideoMemory(image.memory, driver + commands)
    cpu = Prim(memory)
    physical = frames = max_data = max_frames = 0
    for step in range(12000000):
        if memory.eof and cpu._pc == image.symbols['raw_key']:
            break
        if cpu._pc == image.symbols['idle']:
            physical = frames = 0
        opcode = memory.read8(cpu._pc)
        op = opcode & 127
        physical += (1 if op in (Op.PUSH, Op.PUSH8, Op.DUP, Op.OVER, Op.CARRY, Op.FROM_R)
                     else -2 if op in (Op.JZ, Op.STORE, Op.BYTE_STORE)
                     else -1 if op in (Op.CALL, Op.JP, Op.AND, Op.OR, Op.XOR, Op.ADD,
                                     Op.SUB, Op.LTS, Op.LTU, Op.NIP, Op.DROP, Op.TO_R, Op.INTAD) else 0)
        frames += int(op == Op.CALL)
        if opcode & 128 and op not in (Op.CALL, Op.JP, Op.JZ):
            frames -= 1
        assert 0 <= physical <= 16 and 0 <= frames <= 16, (cpu._pc, physical, frames)
        max_data, max_frames = max(max_data, physical), max(max_frames, frames)
        cpu.step()
    else:
        raise AssertionError('Forth VGA session timed out')
    output = memory.sink.getvalue()
    assert b'error' not in output.lower(), output
    assert memory.read16(image.symbols['depth']) == 0
    # After 64 newlines: y=29, scroll=(64-29) mod32=3.
    assert memory.registers == bytes([30, 3, 5, 29]), memory.registers
    assert memory.video[:5] == b'Hell!', memory.video[:8]
    assert memory.video[5:2560] == b' ' * (2560-5)
    assert memory.video[2560:] == b' ' * (4096-2560)
    assert memory.video_writes == 2560 + 35*80 + 7, memory.video_writes
    assert memory.data[0xe000:0xf000] == b'Z' * 4096, 'driver changed hidden SRAM'
    print(f'PASS Forth VGA driver: scroll wrap, row clearing, text, backspace; DS={max_data}/16 RS={max_frames}/16')


if __name__ == '__main__':
    main()
