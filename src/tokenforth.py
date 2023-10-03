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


def interpret(tokens):
    idx = 0
    mode = Token.MODE_COMPILE
    while True:
        tag = tokens[idx]
        if mode == Token.MODE_COMPILE:
            if tag == Token.WORD_CALL:
                pass
            elif tag == Token.WORD_ADDRESS:
                pass
            elif tag == Token.NUMBER:
                pass
            elif tag == Token.STRING:
                pass
            elif tag == Token.MNEMONIC:
                pass
            elif tag == Token.BUILDIN:
                pass
            elif tag == Token.LIT_NUMBER:
                pass
            elif tag == Token.LIT_STRING:
                pass
            elif tag == Token.DEFINITION:
                pass
            elif tag == Token.MODE:
                pass


def init(data):
    data[0:Consts.HERE] = Prim.OP_NOP
    data[Consts.HERE] = Consts.HERE + 2


def main():
    parser = argparse.ArgumentParser(description='Prim ColorForth Tokenizer')
    parser.add_argument("-i", help="Token input file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/test.tok")
    # parser.add_argument("-o", help="Binary token output filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="src/test.tok")
    args = parser.parse_args()

    with open(args.input_filename, mode="rb") as f:
        tokendata = f.read()

    mif = Mif()
    init(mif)
    interpret(tokendata, mif)

if __name__ == "__main__":
    sys.exit(main())
