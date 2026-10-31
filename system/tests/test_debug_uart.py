#!/usr/bin/env python3
"""Directed debug, peripheral MMIO, CPU boundary control and serial simulations."""
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

    def test_duplex_cpu_echo(self):
        self.simulate('tb_uart_duplex', ['tb_uart_duplex.sv', 'prim_system.v', 'prim.v',
                      'memory.v', 'memory_io.v', 'timer_mmio.v', 'timer.v', 'uart_tx.v', 'uart_rx.v', 'uart_buffers.v',
                      'debug_uart.v', 'bus_mux.v', 'uart_arbiter.v', 'debug_uart_link.v'])

    def test_uart_interrupts(self):
        for mode in (0, 1, 2, 3, 4):
            with self.subTest(mode=mode):
                self.simulate('tb_uart_irq', ['tb_uart_irq.sv', 'prim_system.v', 'prim.v',
                              'memory.v', 'memory_io.v', 'timer_mmio.v', 'timer.v',
                              'uart_tx.v', 'uart_rx.v', 'uart_buffers.v', 'debug_uart.v',
                              'bus_mux.v', 'uart_arbiter.v', 'debug_uart_link.v',
                              'ps2_rx.v', 'ps2_fifo.v'], {'MODE': mode})

    def test_timer_mmio(self):
        self.simulate('tb_timer_mmio', ['tb_timer_mmio.sv', 'memory.v', 'memory_io.v',
                                      'timer_mmio.v', 'timer.v'])

    def test_streaming_sram_loader(self):
        for divider in (8, 217):
            with self.subTest(divider=divider):
                self.simulate('tb_stream_load', ['tb_stream_load.sv', 'prim_system.v', 'prim.v',
                              'memory.v', 'memory_io.v', 'timer_mmio.v', 'timer.v', 'uart_tx.v', 'uart_rx.v', 'uart_buffers.v',
                              'debug_uart.v', 'bus_mux.v', 'uart_arbiter.v', 'debug_uart_link.v'], {'DIV': divider})

    def test_system(self):
        for divider in (8, 9, 17):
            with self.subTest(divider=divider):
                self.simulate('tb_debug', ['tb_debug.sv', 'prim_system.v', 'prim.v',
                              'memory.v', 'memory_io.v', 'timer_mmio.v', 'timer.v', 'uart_tx.v', 'uart_rx.v', 'uart_buffers.v',
                              'debug_uart.v', 'bus_mux.v', 'uart_arbiter.v', 'debug_uart_link.v'], {'DIV': divider})


if __name__ == '__main__':
    run_tests(DebugChecks)
