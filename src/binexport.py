#! /usr/bin/env python3

import argparse
import sys
import toml

parser = argparse.ArgumentParser(description='binary data export tool')
parser.add_argument("-i", help="Input TOML filename", action="store", metavar="<input file>", type=str, required=True, dest="input_filename",default="")
parser.add_argument("-o", help="Output binary filename", metavar="<output filename>", action="store", type=str, required=True, dest="output_filename",default="")
parser.add_argument("-s", help="Section name", metavar="<section name>", action="store", type=str, required=True, dest="sectionname",default="")
args = parser.parse_args()

tomldata = toml.load(args.input_filename)

if args.sectionname in tomldata:
    data = bytearray(tomldata[args.sectionname])
else:
    print(f"ERROR: Section '{args.sectionname}' not found in {args.input_filename}")
    exit(1)

with open(args.output_filename, "wb") as f:
    f.write(data)
