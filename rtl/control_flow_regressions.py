#!/usr/bin/env python3

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RTL = ROOT / 'rtl'
BUILD = RTL / 'build'
SIM = BUILD / 'simulator'

# These are the current control-flow regression cases to be exercised against the
# Verilog implementation before the broader instruction set is added.
CASES = [
    (
        'call_ret_1',
        '5 call BREAK nop 2.ret',
        {'pc': 0x0004, 'dsp': 1, 'rsp': 0, 'T': 0x0002, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'call_ret_2',
        '6 nop call BREAK nop 2.ret',
        {'pc': 0x0005, 'dsp': 1, 'rsp': 0, 'T': 0x0002, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'jp',
        '4 jp BREAK 0xff',
        {'pc': 0x0007, 'dsp': 1, 'rsp': 0, 'T': 0x00ff, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'jz_zero',
        '0 8 jz BREAK 0xfe',
        {'pc': 0x0009, 'dsp': 0, 'rsp': 0, 'T': 0x0000, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'jz_nonzero',
        '1 8 jz BREAK 0xfe',
        {'pc': 0x0006, 'dsp': 0, 'rsp': 0, 'T': 0x0000, 'N': 0x0000, 'R': 0x0000},
    ),
]

assert SIM.exists(), f'Verilator simulator not built yet: {SIM}'


def assemble(asm):
    import sys
    sys.path.insert(0, str(ROOT / 'src'))
    from primasm import PrimAsm
    from primconsts import PrimOpcodes

    prog = PrimAsm.assemble(asm.replace('SIMEND', 'BREAK'))
    prog.append(PrimOpcodes.BREAK)
    return bytes(prog)


def run_case(name, asm, expected):
    image = assemble(asm)
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tmp:
        tmp.write(image)
        tmp_name = tmp.name
    try:
        out = subprocess.run(
            [str(SIM), '-i', tmp_name],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        Path(tmp_name).unlink(missing_ok=True)

    text = (out.stdout or '') + (out.stderr or '')
    match = re.search(r'state:\s+pc=([0-9a-fA-F]+)\s+dsp=(\d+)\s+rsp=(\d+)\s+T=([0-9a-fA-F]+)\s+N=([0-9a-fA-F]+)\s+R=([0-9a-fA-F]+)\s+ir=([0-9a-fA-F]+)', text, re.IGNORECASE)
    if not match:
        raise AssertionError(f'{name}: simulator did not emit a final state\n{text}')

    actual = {
        'pc': int(match.group(1), 16),
        'dsp': int(match.group(2), 10),
        'rsp': int(match.group(3), 10),
        'T': int(match.group(4), 16),
        'N': int(match.group(5), 16),
        'R': int(match.group(6), 16),
    }

    mismatch = {key: (actual[key], expected[key]) for key in expected if actual[key] != expected[key]}
    if mismatch:
        raise AssertionError(f'{name}: mismatch {mismatch}\n{text}')

    print(f'PASS {name}: {actual}')
    return 0


def main():
    # Ensure the simulator is present; the project already contains a built copy under
    # rtl/build, but a fresh build is attempted if it is missing.
    if not SIM.exists():
        subprocess.run(['cmake', '-S', str(RTL), '-B', str(BUILD)], check=True)
        subprocess.run(['cmake', '--build', str(BUILD)], check=True)
    failures = 0
    for name, asm, expected in CASES:
        try:
            run_case(name, asm, expected)
        except Exception as exc:
            print(f'FAIL {name}: {exc}', file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
