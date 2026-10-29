#!/usr/bin/env python3
"""Directed debug protocol, CPU boundary control, and serial RX simulations."""
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

from support import build
from support.config import Tools, run_tests
from support.process import run


class DebugChecks(unittest.TestCase):
    tools = Tools()

    def simulate(self, top, sources, parameters=None):
        with tempfile.TemporaryDirectory() as directory:
            binary = build.icarus(Path(directory) / top, tools=self.tools, top=top,
                                  sources=sources, parameters=parameters)
            result = run([self.tools.vvp, binary], timeout=30).stdout
            self.assertIn('PASS', result)

    def test_system(self):
        for divider in (8, 9, 17):
            with self.subTest(divider=divider):
                self.simulate('tb_debug', ['tb_debug.sv', 'prim_system.v', 'prim.v',
                              'memory.v', 'memory_io.v', 'uart_tx.v', 'uart_rx.v',
                              'debug_uart.v', 'bus_mux.v', 'uart_arbiter.v', 'debug_uart_link.v'], {'DIV': divider})


if __name__ == '__main__':
    run_tests(DebugChecks)
