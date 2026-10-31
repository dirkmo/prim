"""Longer watchdog for whole Forth compilation sessions, same SRAM/CPU model."""
from support.sram import SramSimulation
from support.paths import ROOT, TIMINGS, source_path
from support.process import run


class ForthSramSimulation(SramSimulation):
    def build(self):
        # Existing integration bench is otherwise byte-for-byte unchanged.
        source = (ROOT / 'system/tests/tb_memory.sv').read_text()
        limit = 'if (cycles > 100000)'
        if source.count(limit) != 1:
            raise RuntimeError('SRAM bench watchdog changed; review Forth test adapter')
        bench = self.directory / 'tb_memory_forth.sv'
        bench.write_text(source.replace(limit, 'if (cycles > 1000000)'))
        modules = ('memory.v', 'prim.v', 'uart_tx.v', 'uart_buffers.v',
                   'memory_io.v', 'timer_mmio.v', 'timer.v')
        for read, write, delay in TIMINGS:
            output = self.directory / f'sram-{read}-{write}-{delay}'
            self.simulators[read, write, delay] = output
            parameters = {'READ_CYCLES': read, 'WRITE_CYCLES': write,
                          'SRAM_DELAY_NS': delay, 'WITH_UART': int(self.with_uart)}
            args = [self.tools.iverilog, '-g2012', '-s', 'tb_memory',
                    '-I', ROOT / 'cpu/rtl', '-o', output]
            for name, value in parameters.items():
                args += ['-P', f'tb_memory.{name}={value}']
            run([*args, bench, *(source_path(name) for name in modules)])
