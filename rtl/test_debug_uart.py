#!/usr/bin/env python3
"""Directed debug protocol, CPU boundary control, and serial RX simulations."""
import tempfile
import unittest
from pathlib import Path

from sim_support import build
from sim_support.config import Tools, run_tests
from sim_support.process import run


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
                              'debug_uart.v'], {'DIV': divider})

    def test_cpu_waits(self):
        self.simulate('tb_debug_cpu', ['tb_debug_cpu.sv', 'prim.v'])

    def test_rx(self):
        for divider in (8, 9, 17, 868):
            with self.subTest(divider=divider):
                self.simulate('tb_uart_rx', ['tb_uart_rx.sv', 'uart_rx.v'], {'DIV': divider})


if __name__ == '__main__':
    run_tests(DebugChecks)
