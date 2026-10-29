#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

from support import build
from support.config import Tools, run_tests
from support.process import run


class DebugCpuChecks(unittest.TestCase):
    tools = Tools()

    def test_waits(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = build.icarus(Path(directory) / 'cpu', tools=self.tools,
                                  top='tb_debug_cpu', sources=['tb_debug_cpu.sv', 'prim.v'])
            self.assertIn('PASS', run([self.tools.vvp, binary], timeout=30).stdout)


if __name__ == '__main__':
    run_tests(DebugCpuChecks)
