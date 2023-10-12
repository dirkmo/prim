#! /usr/bin/env python3

import argparse
import sys
from prim import Prim, MemoryIf
from primasm import PrimAsm
from primconsts import *
from tokens import Token, BuildIn


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
            print(f"uart-tx: {chr(value)}")
        else:
            self._mem[addr] = int(value)

    def write16(self, addr, value):
        self.write8(addr, value & 0xff)
        self.write8(addr+1, (value >> 8) & 0xff)


class Dictionary:
    D = []
    def add(name, addr):
        if name == "H":
            addr = Consts.HERE
        Dictionary.D.append((name, addr))
    def lookup(idx):
        return Dictionary.D[idx]


def init(mif):
    mif.write16(Consts.HERE, Consts.HERE+2)


def comma(mif, values):
    here = mif.read16(Consts.HERE)
    if hasattr(values, '__iter__'):
        for v in values:
            mif.write8(here, v)
            here += 1
    else:
        mif.write8(here, values)
        here += 1
    mif.write16(Consts.HERE, here)


def getPushOps(num, shrink=True):
    if shrink and (num < 0x100):
        ops = [PrimOpcodes.PUSH8, num & 0xff]
    else:
        ops = [PrimOpcodes.PUSH, num & 0xff, (num >> 8) & 0xff]
    return ops


def execute(cpu, opcodes):
    opcodes.append(PrimOpcodes.SIMEND)
    l = len(opcodes)
    cpu._mif._mem[0xf000:0xf000+l] = opcodes
    cpu._pc = 0xf000
    while cpu.step():
        #cpu.status()
        pass


def compile_string(mif, s):
    here = mif.read16(Consts.HERE)
    strbytes = s.encode("utf-8")
    ops = []
    ops.extend(getPushOps(here + 7, shrink=False)) # 3 bytes
    ops.extend(getPushOps(here + 7 + 1 + len(strbytes), shrink=False)) # 3 bytes
    ops.append(PrimOpcodes.JP) # 1 byte
    ops.append(len(s)) #  1 byte
    ops.extend(strbytes) # len(s) bytes
    comma(mif, ops)


def execute_string(cpu, s):
    print("execute_string not implemented")


def interpret(tokens, cpu):
    idx = 0
    mode = Token.MODE_COMPILE
    while idx < len(tokens):
        tag = tokens[idx]
        print(f"tag: {Token.tagnames[tag]} ({tag})")
        idx += 1
        if tag == Token.WORD_CALL:
            di = tokens[idx] | (tokens[idx+1] << 8)
            idx += 2
            (name, addr) = Dictionary.lookup(di)
            ops = getPushOps(addr)
            ops.append(PrimOpcodes.CALL)
            print(f"word call: {name}")
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, ops)
            else:
                execute(cpu, ops)
        elif tag == Token.WORD_ADDRESS:
            di = tokens[idx] | (tokens[idx+1] << 8)
            idx += 2
            (name, addr) = Dictionary.lookup(di)
            ops = getPushOps(addr)
            print(f"word address: {name}")
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, ops)
            else:
                execute(cpu, ops)
        elif tag == Token.NUMBER:
            num = tokens[idx] | (tokens[idx+1] << 8)
            idx += 2
            ops = getPushOps(num)
            print(f"number: {num}")
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, ops)
            else:
                execute(cpu, ops)
        elif tag == Token.STRING:
            l = tokens[idx]
            s = tokens[idx+1:idx+1+l].decode("utf-8")
            idx += l + 1
            print(f"string: {s}")
            if mode == Token.MODE_COMPILE:
                compile_string(cpu._mif, s)
            else:
                execute_string(cpu, s)
        elif tag == Token.MNEMONIC:
            print(f"mnemonic {PrimAsm.disassembleOpcode(tokens[idx])}")
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, [tokens[idx]])
            else:
                execute(cpu, [tokens[idx]])
            idx += 1
        elif tag == Token.BUILDIN:
            asm = BuildIn.lookupByIndex(tokens[idx])[1]
            ops = PrimAsm.assemble(asm)
            print(f"buildin {tokens[idx]}: '{asm}' {ops}")
            idx += 1
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, ops)
            else:
                execute(cpu, ops)
        elif tag == Token.LIT_NUMBER:
            print(f"Literal number: {tokens[idx] | (tokens[idx+1] << 8)}")
            comma(cpu._mif, tokens[idx:idx+1])
            idx += 2
        elif tag == Token.LIT_STRING:
            l = tokens[idx]
            name = tokens[idx+1:idx+1+l].decode("utf-8")
            idx += l + 1
            print(f"Literal string: {name}")
            comma(cpu._mif, [l])
            comma(cpu._mif, tokens[idx:idx+1])
        elif tag == Token.DEFINITION:
            l = tokens[idx]
            name = tokens[idx+1:idx+1+l].decode("utf-8")
            idx += l + 1
            print(f"Definition: {name}")
            Dictionary.add(name, cpu._mif.read16(Consts.HERE))
        elif tag == Token.MODE:
            mode = tokens[idx]
            idx += 1
            if mode == Token.MODE_COMPILE:
                print("compile mode")
            else:
                print("immediate mode")
        elif tag in [Token.COMMENT_BACKSLASH, Token.COMMENT_BRACES, Token.WHITESPACE]:
            l = tokens[idx]
            idx += l + 1
        else:
            assert False, "Tag not handled!"


def main():
    parser = argparse.ArgumentParser(description='Prim ColorForth Tokenizer')
    parser.add_argument("-i", help="Token input file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/test.tok")
    parser.add_argument("-o", help="Binary token output filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="src/test.bin")
    args = parser.parse_args()

    with open(args.input_filename, mode="rb") as f:
        tokendata = f.read()

    mif = Mif()
    cpu = Prim(mif)
    init(mif)
    interpret(tokendata, cpu)

    with open(args.output_filename, mode="wb") as f:
        here = cpu._mif.read16(Consts.HERE)
        f.write(cpu._mif._mem[0:here])
    
    with open(args.output_filename + ".sym", mode="wt") as f:
        for d in Dictionary.D:
            f.write(f"{d[0]} 0x{d[1]:x}\n")


if __name__ == "__main__":
    sys.exit(main())
