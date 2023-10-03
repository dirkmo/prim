#! /usr/bin/env python3

import argparse
import sys
from prim import Prim
from primasm import PrimAsm




def main():
    parser = argparse.ArgumentParser(description='Prim ColorForth Tokenizer')
    parser.add_argument("-i", help="Token input file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/test.tok")
    # parser.add_argument("-o", help="Binary token output filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="src/test.tok")
    args = parser.parse_args()

    with open(args.input_filename, mode="rb") as f:
        tokendata = f.read()


if __name__ == "__main__":
    sys.exit(main())
