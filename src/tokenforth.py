#! /usr/bin/env python3

import argparse
import sys
from prim import Prim, MemoryIf
from primasm import PrimAsm
from tokens import Token, Consts

class Mif(MemoryIf):
    def __init__(self, init=None):
        self._mem = bytearray(0x10000)
        if init is not None:
            l = len(init)
            self._mem[0:l] = init

    def read8(self, addr):
        return self._mem[addr]

    def read16(self, addr):
        return self._mem[addr] | (self._mem[addr+1] << 8)

    def write8(self, addr, value):
        self._mem[addr] = value & 0xff
        self._mem[addr+1] = (value >> 8) & 0xff

    def write16(self, addr, value):
        self._mem[addr] = value & 0xff
        self._mem[addr+1] = (value >> 8) & 0xff


class Dictionary:
    D = []
    def add(name, addr):
        Dictionary.D.append((name, addr))
    def lookup(idx):
        return Dictionary.D[idx]


def init(mif):
    Dictionary.add("H", Consts.HERE)
    mif.write16(Consts.HERE, Consts.HERE+2)


def comma(mif, values):
    here = mif.read16(Consts.HERE)
    if type(values) == list:
        for v in values:
            mif.write8(here, v)
            here += 1
    else:
        mif.write8(here, values)
        here += 1
    mif.write16(Consts.HERE, here)


def interpret(tokens, cpu):
    idx = 0
    mode = Token.MODE_COMPILE
    mif = cpu._mif
    while idx < len(tokens):
        tag = tokens[idx]
        print(f"tag: {tag}")
        idx += 1
        if mode == Token.MODE_COMPILE:
            if tag == Token.WORD_CALL:
                addr = Dictionary.lookup(tokens[idx])
                ops = [Prim.OP_CALL, addr & 0xff, (addr >> 8) & 0xff]
                if mode == Token.MODE_COMPILE:
                    comma(mif, ops)
                else:
                    pass # TODO
                idx += 1
            elif tag == Token.WORD_ADDRESS:
                addr = Dictionary.lookup(tokens[idx])
                ops = [Prim.OP_PUSH, addr & 0xff, (addr >> 8) & 0xff]
                if mode == Token.MODE_COMPILE:
                    comma(mif, ops)
                else:
                    pass # TODO
                idx += 1
            elif tag == Token.NUMBER:
                num = tokens[idx] | (tokens[idx+1] << 8)
                idx += 2
                ops = [Prim.OP_PUSH, num & 0xff, (num >> 8) & 0xff]
                if mode == Token.MODE_COMPILE:
                    comma(mif, ops)
                else:
                    pass # TODO
                idx += 1
            elif tag == Token.STRING:
                pass
            elif tag == Token.MNEMONIC:
                if mode == Token.MODE_COMPILE:
                    comma(mif, tokens[idx])
                else:
                    cpu.execute(tokens[idx])
                idx += 1
            elif tag == Token.BUILDIN:
                l = tokens[idx]
                idx += 1
                if mode == Token.MODE_COMPILE:
                    comma(mif, tokens[idx:idx+l])
                    idx += l
                else:
                    for op in tokens[idx:idx+l]:
                        cpu.execute(op)
            elif tag == Token.LIT_NUMBER:
                comma(mif, tokens[idx:idx+1])
                idx += 2
            elif tag == Token.LIT_STRING:
                l = tokens[idx]
                name = tokens[idx+1:idx+1+l].decode("utf-8")
                idx += l + 1
                comma(mif, l)
                comma(mif, tokens[idx:idx+1])
            elif tag == Token.DEFINITION:
                l = tokens[idx]
                name = tokens[idx+1:idx+1+l].decode("utf-8")
                idx += l + 1
                Dictionary.add(name, mif.read16(Consts.HERE))
            elif tag == Token.MODE:
                idx += 1
                mode = tokens[idx]
                if mode == Token.MODE_COMPILE:
                    print("compile mode")
                else:
                    print("immediate mode")
            elif tag in [Token.COMMENT_BACKSLASH, Token.COMMENT_BRACES, Token.WHITESPACE]:
                l = tokens[idx]
                idx += l + 1


def main():
    parser = argparse.ArgumentParser(description='Prim ColorForth Tokenizer')
    parser.add_argument("-i", help="Token input file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/test.tok")
    # parser.add_argument("-o", help="Binary token output filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="src/test.tok")
    args = parser.parse_args()

    with open(args.input_filename, mode="rb") as f:
        tokendata = f.read()

    mif = Mif()
    cpu = Prim(mif)
    init(mif)
    interpret(tokendata, cpu)

if __name__ == "__main__":
    sys.exit(main())
