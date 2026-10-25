#!/usr/bin/env python3
"""Test the physical SRAM controller, then compare CPU+controller with Python."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
import unittest

from compare import ROOT, PrimAsm, Op, compare_records
from control_flow_regressions import CASES

parser = argparse.ArgumentParser()
parser.add_argument('--iverilog', default='iverilog')
parser.add_argument('--vvp', default='vvp')
args, remaining = parser.parse_known_args()
RTL = ROOT / 'rtl'
TIMINGS = ((1, 1, 3), (2, 2, 12), (3, 4, 19))


class SramChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='prim-sram-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.simulators = {}
        for read, write, delay in TIMINGS:
            simulator = cls.directory / f'sram-{read}-{write}-{delay}'
            subprocess.run([
                args.iverilog, '-g2012', '-s', 'tb_memory', '-I', str(RTL),
                '-P', f'tb_memory.READ_CYCLES={read}',
                '-P', f'tb_memory.WRITE_CYCLES={write}', '-o', str(simulator),
                '-P', f'tb_memory.SRAM_DELAY_NS={delay}',
                str(RTL / 'tb_memory.sv'), str(RTL / 'memory.v'), str(RTL / 'prim.v'),
            ], check=True, capture_output=True, text=True, timeout=30)
            cls.simulators[read, write, delay] = simulator

    def run_simulator(self, timing, *options):
        result = subprocess.run([args.vvp, str(self.simulators[timing]), *options],
                                capture_output=True, text=True, timeout=30,
                                cwd=self.directory)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def compare_image(self, image, timing):
        memory = bytearray([0xff]) * 65536
        memory[:len(image)] = image
        image_path = self.directory / 'image.hex'
        trace_path = self.directory / 'retirement.jsonl'
        image_path.write_text(''.join(f'{memory[i+1]:02x}{memory[i]:02x}\n'
                                      for i in range(0, 65536, 2)))
        output = self.run_simulator(timing, '+cpu', f'+image={image_path}', f'+trace={trace_path}')
        self.assertIn('PASS CPU SRAM integration', output)
        records = [json.loads(line) for line in trace_path.read_text().splitlines()]
        compare_records(image, records)

    def test_controller_transactions_and_bus_timing(self):
        # All masks, aligned/odd/boundary addresses, adjacent-byte preservation,
        # 512 random transactions, continuous BS, reset, and idle bus release.
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                self.assertIn('PASS SRAM controller', self.run_simulator(timing))

    def test_cpu_baseline_programs(self):
        for timing in TIMINGS:
            for name, asm, _ in CASES:
                with self.subTest(timing=timing, case=name):
                    image = bytes(PrimAsm.assemble(asm) + [Op.BREAK])
                    self.compare_image(image, timing)

    def test_cpu_memory_boundaries(self):
        for timing in TIMINGS:
            for address in (0x1000, 0x1001, 0xfffd, 0xfffe, 0xffff):
                asm = (f'0x1234 {address} ! {address} @ '
                       f'0xabcd {address} c! {address} @ '
                       f'{address} c@ {(address+1)&65535} c@')
                with self.subTest(timing=timing, address=address):
                    self.compare_image(bytes(PrimAsm.assemble(asm) + [Op.BREAK]), timing)

    def test_cpu_self_modifying_code(self):
        for timing in TIMINGS:
            with self.subTest(timing=timing):
                self.compare_image(bytes(PrimAsm.assemble('7 9 c! nop nop nop 1') + [Op.BREAK]), timing)

    def test_cpu_memory_return(self):
        for timing in TIMINGS:
            for op in ('@', 'c@', '!', 'c!'):
                body = f'0xabcd 0x1001 {op}.ret 0xdead BREAK'
                target = len(PrimAsm.assemble(f'0 >r {body}'))
                image = bytes(PrimAsm.assemble(f'{target} >r {body}') + [Op.BREAK])
                with self.subTest(timing=timing, op=op):
                    self.compare_image(image, timing)


if __name__ == '__main__':
    unittest.main(argv=[__file__, *remaining])
