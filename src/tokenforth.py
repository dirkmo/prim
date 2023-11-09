#! /usr/bin/env python3

import argparse
from datetime import datetime
import os
import sys
from prim import Prim, MemoryIf
from primasm import PrimAsm
from primconsts import *
from tokens import Token, BuildIn
import toml
import tomlfix

class Mif(MemoryIf):
    def __init__(self, init=None):
        self._mem = bytearray(0x10000)
        if init is not None:
            self.init(init)

    def init(self, mem):
        l = len(mem)
        self._mem[0:l] = mem

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


class Dictionary:
    D = [] # definition names
    S = [] # string literal addresses
    N = [] # number literal addresses
    def addNameDefinition(name):
        if name == "H":
            assert len(Dictionary.D) == 0, "Definition of 'H' must be first."
        if name == "LATEST":
            assert len(Dictionary.D) == 1, "Definition of 'LATEST' must be second."
        Dictionary.D.append(name)
    def loadDefinitions(fn):
        with open(fn, mode="rt") as f:
            symbols = f.readlines()
        for sym in symbols:
            Dictionary.addNameDefinition(sym)
    def lookupNameDefinition(idx):
        return Dictionary.D[idx]
    def addStringLiteral(addr):
        Dictionary.S.append(addr)
    def addNumberLiteral(addr):
        Dictionary.N.append(addr)


def init(mif):
    # The word dictionary starts at address Consts.DICT and grows to lower addresses
    # Index 0: HERE pointer
    mif.write16(Consts.HERE, Consts.HERE+2)
    mif.write16(Consts.DICT, Consts.HERE)
    # Dictionary.addNameDefinition("H")
    # Index 1: LATEST pointer, which points behind the last dict entry
    comma16(mif, Consts.DICT-2)
    appendToIndex(mif, HERE_FETCH(mif)-2)
    # Dictionary.addNameDefinition("LATEST")

def fetchFromIndex(mif, idx):
    return mif.read16(Consts.DICT-idx*2)

def HERE_FETCH(mif):
    return mif.read16(Consts.HERE)

def HERE_STORE(mif, val):
    mif.write16(Consts.HERE, val)

def LATEST_FETCH(mif):
    return mif.read16(Consts.LATEST)

def appendToIndex(mif, addr):
    latest = LATEST_FETCH(mif)
    idx = (Consts.DICT - latest) // 2
    print(f"append: idx {idx}: addr 0x{addr:04x}")
    mif.write16(latest, addr)
    mif.write16(Consts.LATEST, latest - 2)

def comma(mif, values):
    here = HERE_FETCH(mif)
    if hasattr(values, '__iter__'):
        for v in values:
            mif.write8(here, v)
            here += 1
    else:
        mif.write8(here, values)
        here += 1
    HERE_STORE(mif, here)

def comma16(mif, values):
    here = HERE_FETCH(mif)
    mif.write16(here, values)
    here += 2
    HERE_STORE(mif, here)

def getPushOps(num, shrink=True):
    if shrink and (num < 0x100):
        ops = [PrimOpcodes.PUSH8, num & 0xff]
    else:
        ops = [PrimOpcodes.PUSH, num & 0xff, (num >> 8) & 0xff]
    return ops


def execute(cpu, opcodes):
    opcodes.append(PrimOpcodes.BREAK)
    l = len(opcodes)
    assert l < 0xf0, f"too much immediate code"
    cpu._mif._mem[Consts.AREA:Consts.AREA+l] = opcodes
    cpu._pc = Consts.AREA
    while cpu.step() != PrimOpcodes.BREAK:
        #cpu.status()
        pass


def compile_string(mif, s):
    # this compiles: [push str-addr] [push behind_strdata] [jp] [count,chars...] behind_strdata:
    # so when this is executed, the string address is pushed on the stack and execution
    # continues "behind" the string data.
    here = HERE_FETCH(mif)
    Dictionary.addStringLiteral(here + 7)
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
        # print(f"here: {HERE(cpu._mif)}")
        tag = tokens[idx]
        # print(f"tag: {Token.tagnames[tag]} ({tag})")
        idx += 1
        if tag == Token.WORD_CALL:
            di = tokens[idx] | (tokens[idx+1] << 8)
            idx += 2
            #(name, addr) = Dictionary.lookupNameDefinition(di)
            addr = fetchFromIndex(cpu._mif, di)
            ops = getPushOps(addr)
            ops.append(PrimOpcodes.CALL)
            # print(f"call {Dictionary.D[di]}")
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, ops)
            else:
                execute(cpu, ops)
        elif tag == Token.WORD_ADDRESS:
            di = tokens[idx] | (tokens[idx+1] << 8)
            idx += 2
            addr = fetchFromIndex(cpu._mif, di)
            ops = getPushOps(addr)
            # print(f"word address: {Dictionary.D[di]}")
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, ops)
            else:
                execute(cpu, ops)
        elif tag == Token.NUMBER:
            num = tokens[idx] | (tokens[idx+1] << 8)
            idx += 2
            ops = getPushOps(num)
            # print(f"number: {num}")
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, ops)
            else:
                execute(cpu, ops)
        elif tag == Token.STRING:
            l = tokens[idx]
            s = tokens[idx+1:idx+1+l].decode("utf-8")
            idx += l + 1
            # print(f"string: {s}")
            if mode == Token.MODE_COMPILE:
                compile_string(cpu._mif, s)
            else:
                execute_string(cpu, s)
        elif tag == Token.MNEMONIC:
            # print(f"mnemonic {PrimAsm.disassembleOpcode(tokens[idx])}")
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, [tokens[idx]])
            else:
                execute(cpu, [tokens[idx]])
            idx += 1
        elif tag == Token.BUILDIN:
            asm = BuildIn.lookupByIndex(tokens[idx])[1]
            ops = PrimAsm.assemble(asm)
            # print(f"buildin {tokens[idx]}: '{asm}' {ops}")
            idx += 1
            if mode == Token.MODE_COMPILE:
                comma(cpu._mif, ops)
            else:
                execute(cpu, ops)
        elif tag == Token.LIT_NUMBER:
            # print(f"Literal number: {tokens[idx] | (tokens[idx+1] << 8)}")
            Dictionary.addNumberLiteral(HERE_FETCH(cpu._mif))
            comma(cpu._mif, tokens[idx:idx+2])
            idx += 2
        elif tag == Token.LIT_STRING:
            l = tokens[idx]
            name = tokens[idx+1:idx+1+l].decode("utf-8")
            idx += l + 1
            # print(f"Literal string: {name}")
            comma(cpu._mif, [l])
            comma(cpu._mif, tokens[idx:idx+1])
        elif tag == Token.DEFINITION:
            l = tokens[idx]
            name_ba = bytearray(tokens[idx+1:idx+1+l])
            name = name_ba.decode("utf-8")
            idx += l + 1
            print(f"Definition: {name} @ 0x{HERE_FETCH(cpu._mif):x}")
            Dictionary.addNameDefinition(name)
            appendToIndex(cpu._mif, HERE_FETCH(cpu._mif))
        elif tag == Token.MODE:
            mode = tokens[idx]
            idx += 1
            # if mode == Token.MODE_COMPILE:
            #     print("compile mode")
            # else:
            #     print("immediate mode")
        elif tag in [Token.COMMENT_BACKSLASH, Token.COMMENT_BRACES, Token.WHITESPACE]:
            l = tokens[idx]
            idx += l + 1
        else:
            assert False, "Tag not handled!"


def saveData(infn, outfn, mif):
    # symbolMap = {}
    # for idx,sym in enumerate(Dictionary.D):
    #     symbolMap[sym] = fetchFromIndex(mif, idx)

    tomldata = {
        "title": f"tokenforthed {infn}",
        "date": f"{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        "input-toml": f"{infn}",
        "type": "tokenforth",
        "symbols": Dictionary.D,
        "string-literals": Dictionary.S,
        "num-literals": Dictionary.N,
        "memory": mif._mem
    }
    with open(outfn, mode="wt") as f:
        f.write(toml.dumps(tomldata))

def main():
    parser = argparse.ArgumentParser(description='Prim ColorForth Tokenizer')
    parser.add_argument("-i", help="Input TOML filename", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="")
    parser.add_argument("-o", help="Output TOML filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="")
    args = parser.parse_args()

    inTomlData = toml.load(args.input_filename)
    tokendata = inTomlData["tokens"]
    memory = inTomlData["memory"]
    symbols = tomlfix.workaround(inTomlData["symbols"])
    strlits = inTomlData["string-literals"]
    numlits = inTomlData["num-literals"]

    for sym in symbols:
        Dictionary.addNameDefinition(sym)

    for lit in strlits:
        Dictionary.S.append(lit)

    for lit in numlits:
        Dictionary.N.append(lit)

    mif = Mif()
    try:
        with open(args.image_filename, "rb") as f:
            memory = f.read()
        print(f"Using memory from tomldata in '{args.image_filename}'")
        mif.init(memory)
    except:
        init(mif)

    cpu = Prim(mif)

    interpret(tokendata, cpu)

    cpu.status()

    saveData(args.input_filename, args.output_filename, cpu._mif)


if __name__ == "__main__":
    sys.exit(main())
