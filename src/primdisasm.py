#! /usr/bin/env python3

import argparse
import sys

from primasm import PrimAsm
from primconsts import Consts

def disassemble(in_fn, out_fn, offset):
    with open(in_fn, "rb") as f:
        data = f.read()
    with open(in_fn + ".sym", "rt") as f:
        lines = f.readlines()
        symbols = {}
        for l in lines:
            (name, saddr) = l.strip().split(" ")
            addr = int(saddr,16)
            symbols[addr] = name
    disasm = PrimAsm.disassemble(data[offset:], Consts.HERE+2)

    if out_fn == "":
        stream = sys.stdout
    else:
        stream = open(out_fn, "wt")
    for d in disasm:
        (addr, ops, ds) = d
        if addr in symbols:
            stream.write(f"{addr:04x}: {symbols[addr]}\n")
        stream.write(f"{addr:04x}: ")
        for o in ops:
            stream.write(f"{o:02x} ")
        stream.write(f"\t{ds}\n")


def main():
    parser = argparse.ArgumentParser(description='Prim Disassembler')
    parser.add_argument("-i", help="Input file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/test.bin")
    parser.add_argument("-o", help="Output filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="")
    parser.add_argument("-s", help="Offset", action="store", metavar="<offset>", type=int, required=False, dest="offset",default=Consts.HERE+2)
    
    args = parser.parse_args()
    disassemble(args.input_filename, args.output_filename, args.offset)


if __name__ == "__main__":
    main()