#!/usr/bin/env python3
"""Compare instruction retirement in the Verilog CPU with src/prim.py."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
from prim import Prim, MemoryIf
from primasm import PrimAsm
from primconsts import PrimOpcodes as Op
from control_flow_regressions import CASES


class Memory(MemoryIf):
    """64 KiB little-endian RAM; optionally map writes at FFFF to UART."""

    def __init__(self, image, uart=False):
        self.data = bytearray([0xff]) * 65536
        self.data[:len(image)] = image
        self.writes = []
        self.reads = []
        self.uart = uart
        self.tx = []

    def read8(self, addr):
        addr &= 0xffff
        value = self.data[addr]
        self.reads.append([addr, value])
        return value

    def read16(self, addr):
        return self.read8(addr) | self.read8(addr + 1) << 8

    def write8(self, addr, value):
        addr, value = addr & 0xffff, value & 0xff
        if self.uart and addr == 0xffff:
            self.tx.append(value)
        else:
            self.data[addr] = value
        self.writes.append([addr, value])

    def write16(self, addr, value):
        self.write8(addr, value)
        self.write8(addr + 1, value >> 8)


class Difference(AssertionError):
    pass


def compare(image, simulator, max_steps=1000, wait_cycles=0, wait_seed=None):
    if not image or len(image) > 65536:
        raise ValueError('Image must contain 1..65536 bytes')
    if not 0 <= wait_cycles <= 10000:
        raise ValueError('wait_cycles must be in 0..10000')
    if wait_seed is not None and not 0 <= wait_seed <= 0xffffffff:
        raise ValueError('wait_seed must be an unsigned 32-bit integer')
    with tempfile.TemporaryDirectory(prefix='prim-compare-') as directory:
        directory = Path(directory)
        binary, trace = directory / 'image.bin', directory / 'retirement.jsonl'
        binary.write_bytes(image)
        command = [str(simulator), '-i', str(binary), '-j', str(trace),
                   '-c', str(max_steps * (2 * wait_cycles + 3) + wait_cycles + 20),
                   '-w', str(wait_cycles)]
        if wait_seed is not None:
            command += ['-s', str(wait_seed)]
        run = subprocess.run(
            command,
            cwd=directory, capture_output=True, text=True, timeout=30,
        )
        if run.returncode not in (0, 1) or not trace.exists():
            raise RuntimeError(f'RTL simulator failed ({run.returncode})\n{run.stdout[-3000:]}\n{run.stderr}')
        records = [json.loads(line) for line in trace.read_text().splitlines()]

    return compare_records(image, records, max_steps, run.returncode)


def compare_records(image, records, max_steps=1000, exit_code=0, uart=False):
    """Check retirement records from either the C++ or the SRAM simulation."""
    memory = Memory(image, uart=uart)
    cpu = Prim(memory)
    ds_depth = rs_depth = 0

    steps = 0
    for record in records:
        at = cpu._pc
        ir = memory.read8(at)
        label = f'step {steps + 1}, pc=0x{at:04x}, {PrimAsm.disassembleOpcode(ir)} (0x{ir:02x})'

        def equal(field, actual, expected):
            if actual != expected:
                raise Difference(f'{label}: {field}: RTL={actual!r}, Python={expected!r}')

        if ir in (Op.BREAK, Op.SIMEND):
            # Do not execute debugger markers. Both PCs still address the marker.
            equal('halt', record, {'kind': 'halt', 'pc': at, 'ir': ir})
            if record is not records[-1]:
                raise RuntimeError('Unexpected trace records after halt')
            return steps
        equal('kind', record['kind'], 'step')
        equal('at', record['at'], at)
        equal('ir', record['ir'], ir)
        if steps >= max_steps:
            raise RuntimeError(f'Instruction limit exceeded ({max_steps})')
        memory.writes.clear()
        memory.reads.clear()
        cpu.step()
        op = ir & 0x7f
        ds_delta = (1 if op in (Op.PUSH, Op.PUSH8, Op.DUP, Op.OVER, Op.CARRY, Op.FROM_R)
                    else -2 if op in (Op.JZ, Op.STORE, Op.BYTE_STORE)
                    else -1 if op in (Op.CALL, Op.JP, Op.AND, Op.OR, Op.XOR,
                                     Op.ADD, Op.SUB, Op.LTS, Op.LTU, Op.NIP,
                                     Op.DROP, Op.TO_R) else 0)
        rs_delta = (1 if op in (Op.CALL, Op.INT, Op.TO_R)
                    else -1 if op in (Op.FROM_R, Op.RDROP) else 0)
        ds_depth = min(16, max(0, ds_depth + ds_delta))
        rs_depth = min(16, max(0, rs_depth + rs_delta))
        # Apply push/pop and return in order, including saturation on overflow.
        if ir & 0x80 and op not in (Op.CALL, Op.JP, Op.JZ, Op.INT):
            rs_depth = max(0, rs_depth - 1)
        for field, expected in [('pc', cpu._pc), ('dsp', cpu._dsp),
                                ('rsp', cpu._rsp), ('carry', int(cpu._carry)),
                                ('reads', memory.reads),
                                ('writes', memory.writes)]:
            equal(field, record[field], expected)
        # Ignore unused cells: Python clears popped cells; hardware may retain them.
        equal('ds', record['ds'][:ds_depth],
              [cpu._ds[(cpu._dsp - i) % 16] for i in range(ds_depth)])
        equal('rs', record['rs'][:rs_depth],
              [cpu._rs[(cpu._rsp - i) % 16] for i in range(rs_depth)])
        steps += 1
    raise RuntimeError(f'RTL trace ended without a BREAK/SIMEND marker (exit {exit_code})')


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
    if args.simulator:
        simulator = args.simulator.resolve()
    else:
        build = ROOT / 'build' / 'rtl'
        subprocess.run(['cmake', '-S', str(ROOT / 'rtl'), '-B', str(build)], check=True)
        subprocess.run(['cmake', '--build', str(build)], check=True)
        simulator = build / 'simulator'
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
