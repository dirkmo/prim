#!/usr/bin/env python3
"""Compare instruction retirement in the Verilog CPU with prim.cpu."""
import argparse
from pathlib import Path
import subprocess
import sys
from prim.assembler import PrimAsm
from prim.isa import PrimOpcodes as Op
from sim_support.build import verilator
from sim_support.cases import CASES
from sim_support.reference import Difference, Memory, compare_records
from sim_support.verilator import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', type=Path, help='Existing simulator; skip build')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--asm', help='Assembly text; BREAK is appended')
    source.add_argument('--binary', type=Path, help='Raw binary with BREAK or SIMEND marker')
    parser.add_argument('--max-steps', type=int, default=1000)
    parser.add_argument('--wait-cycles', type=int, default=0,
                        help='Wait cycles per memory transfer (0..10000)')
    parser.add_argument('--wait-seed', type=int,
                        help='Seed for random waits from 0 to --wait-cycles')
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error('--max-steps must be positive')
    simulator = verilator(args.simulator)
    if args.binary:
        cases = [(args.binary.name, args.binary.read_bytes())]
    elif args.asm is not None:
        cases = [('assembly', bytes(PrimAsm.assemble(args.asm) + [Op.BREAK]))]
    else:
        cases = [(name, bytes(PrimAsm.assemble(asm) + [Op.BREAK]))
                 for name, asm, _ in CASES]
    failures = 0
    for name, image in cases:
        try:
            steps = compare(image, simulator, args.max_steps, args.wait_cycles, args.wait_seed)
            print(f'PASS {name}: {steps} instructions')
        except (Difference, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            failures += 1
            print(f'FAIL {name}: {exc}', file=sys.stderr)
    print(f'{len(cases) - failures}/{len(cases)} comparisons passed')
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
