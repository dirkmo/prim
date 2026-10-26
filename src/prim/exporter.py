#! /usr/bin/env python3

import argparse
import sys
from .artifacts import load, export_section

def main(argv=None):
    parser = argparse.ArgumentParser(description='binary data export tool')
    parser.add_argument("-i", help="Input TOML filename", action="store", metavar="<input file>", type=str, required=True, dest="input_filename",default="")
    parser.add_argument("-o", help="Output binary filename", metavar="<output filename>", action="store", type=str, required=True, dest="output_filename",default="")
    parser.add_argument("-s", help="Section name", metavar="<section name>", action="store", type=str, required=True, dest="sectionname",default="")
    args = parser.parse_args(argv)

    try:
        export_section(load(args.input_filename), args.sectionname, args.output_filename)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
