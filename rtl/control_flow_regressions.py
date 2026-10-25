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

# These focused control-flow and stack cases are exercised against the Verilog
# implementation before the broader instruction set is added.
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
    (
        'stack_dup',
        '1 2 dup BREAK',
        {'pc': 0x0006, 'dsp': 3, 'rsp': 0, 'T': 0x0002, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'stack_swap',
        '1 2 swap BREAK',
        {'pc': 0x0006, 'dsp': 2, 'rsp': 0, 'T': 0x0001, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'stack_over',
        '1 2 over BREAK',
        {'pc': 0x0006, 'dsp': 3, 'rsp': 0, 'T': 0x0001, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'stack_nip',
        '1 2 nip BREAK',
        {'pc': 0x0006, 'dsp': 1, 'rsp': 0, 'T': 0x0002, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'stack_rot',
        '1 2 3 rot BREAK',
        {'pc': 0x0008, 'dsp': 3, 'rsp': 0, 'T': 0x0001, 'N': 0x0003, 'R': 0x0000},
    ),
    (
        'stack_rot_deep',
        '1 2 3 rot nip BREAK',
        {'pc': 0x0009, 'dsp': 2, 'rsp': 0, 'T': 0x0001, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'stack_nrot',
        '1 2 3 -rot BREAK',
        {'pc': 0x0008, 'dsp': 3, 'rsp': 0, 'T': 0x0002, 'N': 0x0001, 'R': 0x0000},
    ),
    (
        'stack_nrot_deep',
        '1 2 3 -rot nip BREAK',
        {'pc': 0x0009, 'dsp': 2, 'rsp': 0, 'T': 0x0002, 'N': 0x0003, 'R': 0x0000},
    ),
    (
        'stack_drop',
        '1 2 drop BREAK',
        {'pc': 0x0006, 'dsp': 1, 'rsp': 0, 'T': 0x0001, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'stack_to_r',
        '1 >r BREAK',
        {'pc': 0x0004, 'dsp': 0, 'rsp': 1, 'T': 0x0000, 'N': 0x0000, 'R': 0x0001},
    ),
    (
        'stack_rdrop',
        '1 >r 2 >r rdrop BREAK',
        {'pc': 0x0008, 'dsp': 0, 'rsp': 1, 'T': 0x0000, 'N': 0x0000, 'R': 0x0001},
    ),
    (
        'stack_from_r',
        '1 >r 2 r> BREAK',
        {'pc': 0x0007, 'dsp': 2, 'rsp': 0, 'T': 0x0001, 'N': 0x0002, 'R': 0x0000},
    ),
    (
        'memory_fetch_word',
        '0x1234 0x100 ! 0x100 @ BREAK',
        {'pc': 0x000c, 'dsp': 1, 'rsp': 0, 'T': 0x1234, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_store_word',
        '0x1234 0x100 ! BREAK',
        {'pc': 0x0008, 'dsp': 0, 'rsp': 0, 'T': 0x0000, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_fetch_byte_low',
        '0x1234 0x100 ! 0x100 c@ BREAK',
        {'pc': 0x000c, 'dsp': 1, 'rsp': 0, 'T': 0x0034, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_fetch_byte_high',
        '0x1234 0x100 ! 0x101 c@ BREAK',
        {'pc': 0x000c, 'dsp': 1, 'rsp': 0, 'T': 0x0012, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_store_byte_low',
        '0x1234 0x100 ! 0xab 0x100 c! 0x100 @ BREAK',
        {'pc': 0x0012, 'dsp': 1, 'rsp': 0, 'T': 0x12ab, 'N': 0x0000, 'R': 0x0000},
    ),
    (
        'memory_store_byte_high',
        '0x1234 0x100 ! 0xab 0x101 c! 0x100 @ BREAK',
        {'pc': 0x0012, 'dsp': 1, 'rsp': 0, 'T': 0xab34, 'N': 0x0000, 'R': 0x0000},
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
