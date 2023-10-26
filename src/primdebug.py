#! /usr/bin/env python3

import argparse
from blessed import Terminal
from prim import *
from primasm import *
from primconsts import *
import sys
import toml


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
        PrimAsm.createLookup()

    def generateStackViewStr(self, prefix, stack, sp, stacksize, w):
        w -= len(prefix)
        s = self.term.bold + self.term.underline + f"{stack[sp]}" + self.term.normal
        for i in range(stacksize-1):
            ns = f"{stack[(sp-i) % stacksize]} "
            if self.term.length(ns+s) >= w:
                break
            s = ns + s
        return prefix + s
    
    def showDataStack(self, x1, x2, y):
        s = self.generateStackViewStr("D: ", self.cpu._ds, self.cpu._dsp, Prim.DS_SIZE, x2 - x1)
        with self.term.location(x=x1, y=y):
            print(s, end="")

    def showReturnStack(self, x1, x2, y):
        s = self.generateStackViewStr("R: ", self.cpu._rs, self.cpu._rsp, Prim.RS_SIZE, x2 - x1)
        with self.term.location(x=x1, y=y):
            print(s, end="")
    
    def showCurrent(self, x1, x2, y):
        pc = self.cpu._pc
        s = f"PC {pc:04x}: {self.disassemble(pc)}"
        print(self.term.move_xy(x1, y) + s, end='')

    def instructionLength(self, addr):
        ir = self.cpu._mif.read8(addr) & 0x7f
        if ir == PrimOpcodes.PUSH:
            return 3
        elif ir == PrimOpcodes.PUSH8:
            return 2
        return 1

    def addrPrevInstruction(self, addr):
        if addr > 2:
            if self.cpu._mif.read8(addr-3) == PrimOpcodes.PUSH:
                return addr - 3
        if addr > 1:
            if self.cpu._mif.read8(addr-2) == PrimOpcodes.PUSH8:
                return addr - 2
        return addr - 1

    def addrNextInstruction(self, addr):
        return addr + self.instructionLength(addr)

    def disassemble(self, addr):
        opcode = self.cpu._mif.read8(addr)
        (ir, retbit) = (opcode & 0x7f, opcode & 0x80)
        s = PrimAsm.LOOKUP[ir] + (".RET" if retbit else "")
        if ir == PrimOpcodes.PUSH8:
            val = self.cpu._mif.read8(addr+1)
            s += f" ${val:x}"
        elif ir == PrimOpcodes.PUSH:
            val = self.cpu._mif.read8(addr+1) | (self.cpu._mif.read8(addr+2) << 8)
            s += f" ${val:x}"
        return s

    def showCode(self, x1, y1, x2, y2):
        h = y2 - y1 + 1
        w = x2 - x1 + 1
        pc = self.cpu._pc+12
        pc_is_on_line = -1
        addr = pc
        linecount = 0
        lines = []
        while addr > 0 and linecount < h // 2:
            da = f"{addr:04x}:"
            for b in range(self.instructionLength(addr)):
                da += f" {self.cpu._mif.read8(addr + b):02x}"
            da += " " * (16 - len(da))
            da += self.disassemble(addr)
            lines.insert(0, da)
            linecount += 1
            pc_is_on_line += 1
            addr = self.addrPrevInstruction(addr)
        addr = pc + 1
        while addr < 0x10000 and linecount < h:
            da = f"{addr:04x}:"
            for b in range(self.instructionLength(addr)):
                da += f" {self.cpu._mif.read8(addr + b):02x}"
            da += " " * (16 - len(da))
            da += self.disassemble(addr)
            lines.append(da)
            linecount += 1
            addr = self.addrNextInstruction(addr)

        for i,l in enumerate(lines):
            if i==pc_is_on_line:
                print(self.term.reverse(self.term.move_xy(x1, y1 + i) + l), end='')
            else:
                print(self.term.move_xy(x1, y1 + i) + l, end='')

    def showBox(self, x1, y1, x2, y2):
        w = x2 - x1
        print(self.term.move_xy(x1,y1) + "┌", end='')
        print("─" * (w-2) + "┐", end='')
        for y in range(y1+1, y2):
            print(self.term.move_xy(x1, y) + "│", end='')
            print(self.term.move_xy(x2, y) + "│", end='')
        print(self.term.move_xy(x1,y2) + "└", end='')
        print("─" * (w-2) + "┘", end='')
        # ├ ┤ ┬ ┴

    def showPrompt(self, x1, x2, y):
        print(self.term.move_xy(x1, y) + "> ", end='')

    def showHorizontalSplitline(self, x1, x2, y):
        print(self.term.move_xy(x1, y) + "├", end='')
        print("─" * (x2-x1-2) + "┤", end='')

    def show(self):
        print(self.term.clear, end='')
        self.showBox(0, 0, self.term.width, self.term.height-1)
        print(self.term.move_xy(2, 0) + " Prim Debugger ", end='')
        self.showCode(2, 1, self.term.width - 2, self.term.height-8)
        self.showHorizontalSplitline(0, self.term.width, self.term.height - 7)
        self.showDataStack(2, self.term.width - 2, self.term.height-6)
        self.showReturnStack(2, self.term.width - 2, self.term.height-5)
        self.showCurrent(2, self.term.width - 2, self.term.height-4)
        self.showHorizontalSplitline(0, self.term.width, self.term.height - 3)
        self.showPrompt(2, self.term.width - 2, self.term.height - 2)
        sys.stdout.flush()


def debug(fn):
    tomldata = toml.load(fn)
    term = Terminal()
    cpu = Prim(Mif(tomldata["memory"]))
    debug = PrimDebug(cpu, term)
    with term.fullscreen(), term.cbreak():
        debug.show()
        term.inkey()


def main():
    parser = argparse.ArgumentParser(description='Prim Debugger')
    parser.add_argument("-i", help="Input symbol file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/test.sym")
    args = parser.parse_args()
    debug(args.input_filename)


if __name__ == "__main__":
    main()