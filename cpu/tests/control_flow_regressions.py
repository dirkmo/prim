#!/usr/bin/env python3
"""Run the fixed final-state instruction regression vectors."""
import argparse
from pathlib import Path
import sys
from prim.assembler import PrimAsm
from prim.isa import PrimOpcodes as Op
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

from support.build import verilator
from support.cases import CASES
from support.paths import SIMULATOR
from support.verilator import run_final_state


def run_case(name, asm, expected, simulator=SIMULATOR):
    image = bytes(PrimAsm.assemble(asm.replace('SIMEND', 'BREAK')) + [Op.BREAK])
    actual = run_final_state(image, simulator)
    mismatch = {key: (actual[key], expected[key]) for key in expected if actual[key] != expected[key]}
    if mismatch:
        raise AssertionError(f'{name}: mismatch {mismatch}')
    print(f'PASS {name}: {actual}')


def main():
    parser = argparse.ArgumentParser(description='Build and run RTL regressions')
    parser.add_argument('--simulator', type=Path,
                        help='Use an already built simulator (skip configure/build)')
    args = parser.parse_args()
    simulator = verilator(args.simulator)
    failures = 0
    for name, asm, expected in CASES:
        try:
            run_case(name, asm, expected, simulator)
        except Exception as exc:
            print(f'FAIL {name}: {exc}', file=sys.stderr)
            failures += 1
    print(f'{len(CASES) - failures}/{len(CASES)} regressions passed')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
