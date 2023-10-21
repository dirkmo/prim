#! /usr/bin/env python3

import argparse
import sys
import os
import toml

from primasm import PrimAsm
from primconsts import *

def nextOpIsCall(data, i):
    return (i < len(data)) and (data[i] == PrimOpcodes.CALL)

def disassemble(td, out_fn):
    offset = td["symbols"]["H"]
    data = td["memory"]
    strlits = td["string-literals"]
    numlits = td["num-literals"]
    symbols = td["symbols"]
    symaddr = dict((addr,name) for name,addr in symbols.items())
    i = offset
    PrimAsm.createLookup()
    if len(out_fn):
        f = open(out_fn, "wt")
    else:
        f =sys.stdout
    while i < len(data):
        if i in symaddr:
            f.write(f"{i:04x}:\t\t\t:{symaddr[i]}\n")
        if i in strlits:
            l = data[i]
            s = '"' + bytes(data[i+1:i+1+l]).decode() + '"'
            f.write(f"{i:04x}:\t")
            for d in data[i:i+l+1]:
                f.write(f"{d:02x} ")
            f.write(f"\t{s}\n")
            i += l + 1
            continue
        if i in numlits:
            num = data[i] | (data[i+1] << 8)
            f.write(f"{i:04x}:\t{data[i]:02x} {data[i+1]:02x}\t\tLiteral 0x{num:x}\n")
            i += 2
            continue
        ir = data[i] & 0x7f
        retbit = (data[i] >> 7) & 1
        ret = ".RET" if retbit else ""
        if ir == PrimOpcodes.PUSH:
            addr = data[i+1] | (data[i+2] << 8)
            if nextOpIsCall(data, i+3):
                s = f"{i:04x}:\t{data[i]:02x} {data[i+1]:02x} {data[i+2]:02x} {data[i+3]:02x}\t{symaddr[addr]}"
                i += 4
            else:
                s = f"{i:04x}:\t{data[i]:02x} {data[i+1]:02x} {data[i+2]:02x}\tPUSH16{ret} 0x{addr:x}"
                i += 3
            f.write(s + "\n")
        elif ir == PrimOpcodes.PUSH8:
            addr = data[i+1]
            if nextOpIsCall(data, i+2):
                s = f"{i:04x}:\t{data[i]:02x} {data[i+1]:02x} {data[i+2]:02x}\t{symaddr[addr]}"
                i += 3
            else:
                s = f"{i:04x}:\t{data[i]:02x} {data[i+1]:02x}\t\tPUSH8{ret} 0x{addr:x}"
                i += 2
            f.write(s + "\n")
        else:
            s = f"{i:04x}:\t{data[i]:02x}\t\t{PrimAsm.LOOKUP[ir]}{ret}"
            f.write(s + "\n")
            i += 1


def main():
    parser = argparse.ArgumentParser(description='Prim Disassembler')
    parser.add_argument("-i", help="Input file", action="store", metavar="<toml input file>", type=str, required=False, dest="input_filename",default="src/test.sym")
    parser.add_argument("-o", help="Output filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="")

    args = parser.parse_args()

    tomldata = toml.load(args.input_filename)

    disassemble(tomldata, args.output_filename)


if __name__ == "__main__":
    main()