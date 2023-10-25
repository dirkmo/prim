#! /usr/bin/env python3

from blessed import Terminal
from prim import *
import sys

class Mif(MemoryIf):
    def __init__(self, init=None):
        self._mem = bytearray(0x10000)
        if init is not None:
            l = len(init)
            self._mem[0:l] = init

    def read8(self, addr):
        addr &= 0xffff
        return self._mem[addr]

    def read16(self, addr):
        return self.read8(addr) | (self.read8(addr+1) << 8)

    def write8(self, addr, value):
        addr &= 0xffff
        value &= 0xff
        if addr == 0xffff:
            print(f"uart-tx: {chr(value)} (0x{value:02x})")
        else:
            self._mem[addr] = int(value)

    def write16(self, addr, value):
        self.write8(addr, value & 0xff)
        self.write8(addr+1, (value >> 8) & 0xff)


class PrimDebug:
    def __init__(self, cpu, term):
        self.cpu = cpu
        self.cpu._debug = self
        self.term = term
        self.code_height = term.height - 4

    def showStack(self, stack, sp, stacksize, term_y):
        s = self.term.bold + self.term.underline + f"{stack[sp]}" + self.term.normal
        for i in range(stacksize-1):
            ns = f"{stack[(sp-i) % stacksize]} "
            if self.term.length(ns+s) >= self.term.width:
                break
            s = ns + s
        with self.term.location(y=term_y):
            print(s, end="")

    def showDataStack(self):
        self.showStack(self.cpu._ds, self.cpu._dsp, Prim.DS_SIZE, self.term.height-3)

    def showReturnStack(self):
        self.showStack(self.cpu._rs, self.cpu._rsp, Prim.RS_SIZE, self.term.height-2)

    def addrPrevInstruction(self, addr):
        if addr > 2:
            if self.cpu._mif(addr-3) == PrimOpcodes.PUSH:
                return addr - 3
        if addr > 1:
            if self.cpu._mif(addr-2) == PrimOpcodes.PUSH8:
                return addr - 2
        return addr - 1

    def addrNextInstruction(self, addr):
        if self.cpu._mif(addr) == PrimOpcodes.PUSH:
            return addr + 3
        if self.cpu._mif(addr) == PrimOpcodes.PUSH8:
            return addr + 2
        return 1

    def disassemble(self, addr):
        pass

    def showCode(self):
        pc = self.cpu._pc
        start = pc
        linecount = 0
        while start > 0 and linecount < self.code_height // 2:
            start = self.addrPrevInstruction(start)
            linecount += 1
        stop = pc
        while stop < 0x10000 and linecount < self.code_height:
            stop = self.addrNextInstruction(stop)
            linecount += 1

    def show(self):
        print(self.term.clear)
        self.showCode()
        self.showDataStack()
        self.showReturnStack()


def main():
    term = Terminal()
    cpu = Prim(Mif())
    debug = PrimDebug(cpu, term)
    with term.fullscreen(), term.cbreak():
        debug.show()
        term.inkey()


if __name__ == "__main__":
    main()