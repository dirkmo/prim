#!/usr/bin/env python3
"""Stdlib-only reporting/cleanup helpers for the top-level Makefile."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def check_tools(args):
    missing = []
    for tool in args.tools:
        found = shutil.which(tool)
        if found:
            print(f'{tool}: {found}')
        else:
            missing.append(tool)
    python = shutil.which(args.python)
    if not python:
        missing.append(args.python + ' (run make setup)')
    else:
        result = subprocess.run([python, '-c', 'import prim.artifacts, prim_debug_uart, serial; print("Python packages: OK")'],
                                text=True, capture_output=True)
        if result.returncode:
            missing.append('Python packages (run make setup, or install the project and pyserial in PYTHON)')
            print(result.stderr.strip())
        else:
            print(result.stdout.strip())
    if missing:
        raise ValueError('Missing requirements: ' + ', '.join(missing))


def resources(args):
    report = json.loads((args.build_dir / 'timing.json').read_text())
    netlist = json.loads((args.build_dir / 'prim.json').read_text())
    top = [module for module in netlist['modules'].values()
           if int(str(module.get('attributes', {}).get('top', '0')), 2) == 1]
    if len(top) != 1:
        raise ValueError('Expected exactly one synthesized top module')
    cells = Counter(cell['type'] for cell in top[0]['cells'].values())
    usage = report['utilization']
    lc_total = usage['ICESTORM_LC']['available']
    print(f'Resources: {args.build_dir.resolve()}')
    print(f'{"Resource":<23} {"Used":>8} {"Total":>8} {"Free":>8} {"Usage":>8}')

    def row(name, used, total):
        print(f'{name:<23} {used:>8} {total:>8} {total-used:>8} {100*used/total:>7.1f}%')

    row('Logic cells (routed)', usage['ICESTORM_LC']['used'], lc_total)
    row('LUT4 (synthesized)', cells['SB_LUT4'], lc_total)
    row('Flip-flops (synth.)', sum(n for kind, n in cells.items() if kind.startswith('SB_DFF')), lc_total)
    for key, name in [('ICESTORM_RAM', 'Block RAM (4 Kibit)'), ('ICESTORM_PLL', 'PLLs'),
                      ('SB_GB', 'Global buffers'), ('SB_IO', 'I/O pins')]:
        value = usage[key]
        row(name, value['used'], value['available'])
    print(f'Carry cells (synthesized): {cells["SB_CARRY"]}')
    print('LUT/FF/carry are parts of logic cells; do not add these rows together.')
    for clock, timing in report.get('fmax', {}).items():
        actual, target = timing['achieved'], timing['constraint']
        print(f'{clock}: target {target:.2f} MHz, reported maximum {actual:.2f} MHz '
              f'({"PASS" if actual >= target else "FAIL"})')
    print('Internal timing report; physical UART/SRAM behavior requires board verification.')


def clean(args):
    # Validate every path before deleting anything. Never follow a build symlink
    # into source/.venv or outside the checkout, even with variable overrides.
    allowed = ROOT / 'build'
    paths = [path.resolve() for path in args.paths]
    for path in paths:
        if path == allowed or not path.is_relative_to(allowed):
            raise ValueError(f'Refusing to remove {path}: clean accepts subdirectories of {allowed} only')
        if path.exists() and not path.is_dir():
            raise ValueError(f'Expected a build directory: {path}')
    for path in dict.fromkeys(paths):
        if path.exists():
            shutil.rmtree(path)
            print(f'Removed {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    p = commands.add_parser('check-tools')
    p.add_argument('--python', required=True)
    p.add_argument('--tools', nargs='+', required=True)
    p.set_defaults(function=check_tools)
    p = commands.add_parser('resources')
    p.add_argument('--build-dir', type=Path, required=True)
    p.set_defaults(function=resources)
    p = commands.add_parser('clean')
    p.add_argument('paths', type=Path, nargs='+')
    p.set_defaults(function=clean)
    args = parser.parse_args()
    try:
        args.function(args)
    except (OSError, ValueError, KeyError, ZeroDivisionError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
