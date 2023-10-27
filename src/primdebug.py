#! /usr/bin/env python3

import argparse
from blessed import Terminal
from prim import *
from primasm import *
from primconsts import *
import signal
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
    def __init__(self, cpu, term, symbols=None, numlits=None, strlits=None):
        self.cpu = cpu
        self.cpu._debug = self
        self.term = term
        # self.symbolDict = symbols if symbols is not None else {}
        self.symbols = dict((addr,name) for name,addr in symbols.items())
        self.strlits = strlits if strlits is not None else []
        self.numlits = numlits if numlits is not None else []
        PrimAsm.createLookup()

    def generateStackViewStr(self, prefix, stack, sp, stacksize, w):
        w -= len(prefix)
        s = self.term.bold + self.term.underline + f"{stack[sp % stacksize]:x}" + self.term.normal
        for i in range(1, stacksize):
            ns = f"{stack[(sp-i) % stacksize]:x} "
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

    def addrInStrLiterals(self, addr):
        # falls addr in a string literal range?
        for sladdr in self.strlits:
            if addr < sladdr:
                continue
            # range of string literal (cnt + chars)
            cnt = self.cpu._mif.read8(sladdr) # read string length
            if addr < sladdr + cnt + 1:
                return True
        return False

    def disassemble(self, addr, useSymbols=True):
        if addr in self.numlits:
            return f"LIT #{self.cpu._mif.read16(addr):x}"
        if self.addrInStrLiterals(addr):
            return "STR-LIT"
        opcode = self.cpu._mif.read8(addr)
        (ir, retbit) = (opcode & 0x7f, opcode & 0x80)
        s = PrimAsm.LOOKUP[ir] + (".RET" if retbit else "")
        if ir == PrimOpcodes.PUSH8:
            val = self.cpu._mif.read8(addr+1)
        elif ir == PrimOpcodes.PUSH:
            val = self.cpu._mif.read8(addr+1) | (self.cpu._mif.read8(addr+2) << 8)
        else:
            return s
        if useSymbols:
            nextIr = self.cpu._mif.read8(self.addrNextInstruction(addr)) & 0x7f
            if nextIr in [PrimOpcodes.JP, PrimOpcodes.JZ, PrimOpcodes.CALL, PrimOpcodes.BYTE_FETCH, PrimOpcodes.FETCH, PrimOpcodes.BYTE_STORE, PrimOpcodes.STORE] and val in self.symbols:
                s += " " + self.term.magenta(f"'{self.symbols[val]}") + f" (${val:x})"
            else:
                s += f" ${val:x}"
        else:
            s += f" ${val:x}"
        return s

    def showCode(self, x1, y1, x2, y2):
        h = y2 - y1 + 1
        w = x2 - x1 + 1
        addr = self.cpu._pc
        linecount = 0
        lines = []
        while addr >= 0 and linecount < h // 2:
            da = f"{addr:04x}:"
            for b in range(self.instructionLength(addr)):
                da += f" {self.cpu._mif.read8(addr + b):02x}"
            da += " " * (16 - len(da))
            da += self.disassemble(addr)
            lines.insert(0, da)
            linecount += 1
            if addr in self.symbols:
                lines.insert(0, f"{addr:04x}           " + self.term.red(":" + self.symbols[addr]))
                linecount += 1
            addr = self.addrPrevInstruction(addr)
        addr = self.addrNextInstruction(self.cpu._pc)
        while addr < 0x10000 and linecount < h:
            if addr in self.symbols:
                lines.append(f"{addr:04x}           " + self.term.red(":" + self.symbols[addr]))
                linecount += 1
            da = f"{addr:04x}:"
            for b in range(self.instructionLength(addr)):
                da += f" {self.cpu._mif.read8(addr + b):02x}"
            da += " " * (16 - len(da))
            da += self.disassemble(addr)
            lines.append(da)
            linecount += 1
            addr = self.addrNextInstruction(addr)
        for i,l in enumerate(lines):
            if int(l[0:4],base=16) == self.cpu._pc:
                print(self.term.reverse(self.term.move_xy(x1, y1 + i) + l), end='')
                print(self.term.reverse(" " * (w-self.term.length(l))), end='')
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

    def showVerticalSplitline(self, x, y1, y2):
        print(self.term.move_xy(x, y1) + "┬", end='')
        for y in range(y1+1, y2):
            print(self.term.move_xy(x, y) + "│", end='')
        print(self.term.move_xy(x, y2) + "┴", end='')

    def showMessageArea(self, x1, y1, x2, y2):
        pass

    def showMemory(self, x1, y1, x2, y2, num=8):
        w = x2 - x1 + 1
        h = y2 - y1 + 1
        start = self.cpu._pc - self.cpu._pc % 8
        s = ""
        for y in range(h):
            addr = start + y*8
            s = f"{addr:04x}:"
            chars = ""
            for a in range(8):
                val = self.cpu._mif.read8(addr + a)
                s += f" {val:02x}"
                chars += '.' if val < 32 else chr(val)
            s = s + " " + chars
            print(self.term.move_xy(x1 + 2, y1 + y) + s[0:w-3], end='')

    def show(self):
        print(self.term.clear, end='')
        self.showBox(0, 0, self.term.width, self.term.height-1)
        print(self.term.move_xy(2, 0) + " Prim Debugger ", end='')
        memshow_num = 8*3 + 7 # num of bytes per line
        memViewHeight = 16
        x2_code = min(self.term.width // 2, 40)
        self.showCode(2, 1, x2_code, self.term.height-8)
        self.showHorizontalSplitline(0, self.term.width, self.term.height - 7)
        self.showVerticalSplitline(x2_code + 1, 0, self.term.height - 7)
        self.showDataStack(2, self.term.width - 2, self.term.height-6)
        self.showReturnStack(2, self.term.width - 2, self.term.height-5)
        self.showCurrent(2, self.term.width - 2, self.term.height-4)
        self.showHorizontalSplitline(0, self.term.width, self.term.height - 3)
        self.showMemory(x2_code+1, 1, self.term.width-1, 1+memViewHeight)
        self.showHorizontalSplitline(x2_code + 1, self.term.width, 2+memViewHeight)
        self.showMessageArea(x2_code+1, 10, 3+memViewHeight, self.term.height - 8)
        self.showPrompt(2, self.term.width - 2, self.term.height - 2)
        sys.stdout.flush()

def debug(fn):
    tomldata = toml.load(fn)
    term = Terminal()
    cpu = Prim(Mif(tomldata["memory"]))
    debug = PrimDebug(cpu, term, tomldata["symbols"], tomldata["num-literals"], tomldata["string-literals"])
    
    def on_resize(sig, action):
        debug.show()
    signal.signal(signal.SIGWINCH, on_resize)

    with term.fullscreen(), term.cbreak():
        while True:
            debug.show()
            key = term.inkey()
            print(repr(key))
            if key.code == term.KEY_ESCAPE or key == '\x04': # 4: ctrl+d
                break
            if key.code == term.KEY_RIGHT:
                cpu.step()


def main():
    parser = argparse.ArgumentParser(description='Prim Debugger')
    parser.add_argument("-i", help="Input symbol file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/test.sym")
    args = parser.parse_args()
    
    debug(args.input_filename)


if __name__ == "__main__":
    main()