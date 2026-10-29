#!/usr/bin/env python3
"""Board startup simulation and fail-closed build/program command checks."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BOARD = Path(__file__).resolve().parent
ROOT = BOARD.parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from support.config import Tools, run_tests

spec = importlib.util.spec_from_file_location('board_build', BOARD / 'build.py')
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)


class BoardChecks(unittest.TestCase):
    tools = Tools()

    def test_failed_timing_removes_stale_binary_and_never_packs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'prim.bin').write_bytes(b'stale bitstream')
            args = argparse.Namespace(output=output,
                                      yosys='yosys', nextpnr='nextpnr-ice40', icepack='icepack')
            with patch.object(flow, 'run', side_effect=[None, RuntimeError('timing failed')]) as run:
                with self.assertRaisesRegex(RuntimeError, 'timing failed'):
                    flow.build(args)
            self.assertEqual(run.call_count, 2)
            route_command = run.call_args.args[0]
            self.assertEqual(route_command[route_command.index('--pcf') + 1], BOARD / 'board.pcf')
            self.assertFalse((output / 'prim.bin').exists())

    def test_program_is_explicit_bulk_flash_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'prim.bin'
            binary.write_bytes(b'bitstream')
            args = argparse.Namespace(bitstream=binary, iceprog='iceprog', interface='A', device=None)
            with patch.object(flow, 'run') as run:
                flow.program(args)
            self.assertEqual(run.call_args.args[0], ['iceprog', '-I', 'A', '-b', binary])

    def test_power_up_and_button_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'board'
            subprocess.run([self.tools.iverilog, '-g2012', '-I', str(ROOT / 'cpu/rtl'), '-s', 'tb_board',
                            '-o', str(binary), str(BOARD / 'tb_board.sv'), str(BOARD / 'pll_sim.v'),
                            *(str(p) for p in flow.SOURCES)], check=True, capture_output=True, text=True)
            result = subprocess.run([self.tools.vvp, str(binary)], check=True, capture_output=True, text=True, timeout=30)
            self.assertIn('PASS board', result.stdout)


if __name__ == '__main__':
    run_tests(BoardChecks)
