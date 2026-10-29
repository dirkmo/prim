#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))

from support import build
from support.config import Tools, run_tests
from support.process import run


class UartChecks(unittest.TestCase):
    tools = Tools()

    def simulate(self, top, sources, parameters=None):
        with tempfile.TemporaryDirectory() as directory:
            binary = build.icarus(Path(directory) / top, tools=self.tools, top=top,
                                  sources=sources, parameters=parameters)
            self.assertIn('PASS', run([self.tools.vvp, binary], timeout=30).stdout)

    def test_rx(self):
        for divider in (8, 9, 17, 868):
            with self.subTest(divider=divider):
                self.simulate('tb_uart_rx', ['tb_uart_rx.sv', 'uart_rx.v'], {'DIV': divider})

    def test_tx(self):
        for divider in (1, 4, 7):
            with self.subTest(divider=divider):
                self.simulate('tb_uart', ['tb_uart.sv', 'uart_tx.v'], {'CLKS_PER_BIT': divider})

    def test_controller(self):
        self.simulate('tb_debug_controller', ['tb_debug_controller.sv', 'debug_uart.v'])

    def test_arbiter(self):
        self.simulate('tb_uart_arbiter', ['tb_uart_arbiter.sv', 'uart_arbiter.v', 'uart_tx.v'])


if __name__ == '__main__':
    run_tests(UartChecks)
