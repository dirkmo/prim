#! /usr/bin/env python3

import argparse
import sys
import toml
import tomlfix

from primasm import PrimAsm
from primconsts import *

def nextOpIsCall(data, i):
    return (i < len(data)) and (data[i] == PrimOpcodes.CALL)

def nextOpIsMemAccess(data, i):
    return (i < len(data)) and (data[i] in [PrimOpcodes.FETCH, PrimOpcodes.BYTE_FETCH, PrimOpcodes.STORE, PrimOpcodes.BYTE_STORE])

def disassembleOpcode(opcode):
    ir = opcode & 0x7f
    sr = ".RET" if opcode & 0x80 else ""
    return PrimAsm.LOOKUP[ir] + sr


def disassemble(td, out_fn):
    data = td["memory"]
    strlits = td["string-literals"]
    numlits = td["num-literals"]
    symbols = tomlfix.workaround(td["symbols"])

    symbolMap = {}
    for idx,sym in enumerate(symbols):
        addr = data[Consts.DICT-idx*2] | (data[Consts.DICT-idx*2+1] << 8)
        symbolMap[addr] = sym

    PrimAsm.createLookup()
    if len(out_fn):
        f = open(out_fn, "wt")
    else:
        f =sys.stdout
    i = 0
    while i < len(data):
        if i in symbolMap:
            f.write(f"{i:04x}:                :{symbolMap[i]}\n")
        if i in strlits:
            l = data[i]
            s = '"' + bytes(data[i+1:i+1+l]).decode() + '"'
            f.write(f"{i:04x}:   ")
            for d in data[i:i+l+1]:
                f.write(f"{d:02x} ")
            f.write(f"\t{s}\n")
            i += l + 1
            continue
        if i in numlits:
            num = data[i] | (data[i+1] << 8)
            if num in symbolMap:
                s = f"{symbolMap[num]}"
            else:
                s = f"0x{num:x}"
            f.write(f"{i:04x}:   {data[i]:02x} {data[i+1]:02x}        Literal {s}\n")
            i += 2
            continue

        ir = data[i] & 0x7f
        retbit = (data[i] >> 7) & 1
        ret = ".RET" if retbit else ""
        if ir == PrimOpcodes.PUSH:
            addr = data[i+1] | (data[i+2] << 8)
            if nextOpIsCall(data, i+3):
                s = f"{i:04x}:   {data[i]:02x} {data[i+1]:02x} {data[i+2]:02x} {data[i+3]:02x}  {symbolMap[addr]}"
                i += 4
            elif nextOpIsMemAccess(data, i+3):
                ns = "'" + symbolMap[addr] if addr in symbolMap else f"0x{addr:x}"
                s = f"{i:04x}:   {data[i]:02x} {data[i+1]:02x} {data[i+2]:02x} {data[i+3]:02x}  {ns} {disassembleOpcode(data[i+3])}"
                i += 4
            else:
                s = f"{i:04x}:   {data[i]:02x} {data[i+1]:02x} {data[i+2]:02x}     PUSH16{ret} 0x{addr:x}"
                i += 3
            f.write(s + "\n")
        elif ir == PrimOpcodes.PUSH8:
            addr = data[i+1]
            if nextOpIsCall(data, i+2):
                s = f"{i:04x}:   {data[i]:02x} {data[i+1]:02x} {data[i+2]:02x}     {symbolMap[addr]}"
                i += 3
            elif nextOpIsMemAccess(data, i+2):
                ns = "'" + symbolMap[addr] if addr in symbolMap else f"0x{addr:x}"
                s = f"{i:04x}:   {data[i]:02x} {data[i+1]:02x} {data[i+2]:02x}     {ns} {disassembleOpcode(data[i+2])}"
                i += 3
            else:
                s = f"{i:04x}:   {data[i]:02x} {data[i+1]:02x}        PUSH8{ret} 0x{addr:x}"
                i += 2
            f.write(s + "\n")
        else:
            s = f"{i:04x}:   {data[i]:02x}           {PrimAsm.LOOKUP[ir]}{ret}"
            f.write(s + "\n")
            i += 1


def main():
    parser = argparse.ArgumentParser(description='Prim Disassembler')
    parser.add_argument("-i", help="Input file", action="store", metavar="<toml input file>", type=str, required=False, dest="input_filename",default="src/base.tf.toml")
    parser.add_argument("-o", help="Output filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="src/base.tf.toml.disasm")

    args = parser.parse_args()

    tomldata = toml.load(args.input_filename)

    disassemble(tomldata, args.output_filename)


if __name__ == "__main__":
    main()