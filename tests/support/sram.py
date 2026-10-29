"""Icarus SRAM/system runner, independent of unittest and test modules."""
from dataclasses import dataclass
import json
from pathlib import Path
from . import build
from .paths import TIMINGS
from .process import run
from .reference import Memory, Prim, Op, compare_records
from .traces import load_records


@dataclass
class SimulationResult:
    serial: bytes | None
    steps: int
    records: list

    def save(self, prefix):
        prefix = Path(prefix)
        prefix.with_suffix('.jsonl').write_text(''.join(json.dumps(record) + '\n' for record in self.records))
        if self.serial is not None:
            prefix.with_suffix('.uart.bin').write_bytes(self.serial)


class SramSimulation:
    def __init__(self, directory, tools, with_uart=False):
        self.directory, self.tools = Path(directory), tools
        self.with_uart = with_uart
        self.simulators = {}

    def build(self):
        for read, write, delay in TIMINGS:
            output = self.directory / f'sram-{read}-{write}-{delay}'
            self.simulators[read, write, delay] = build.icarus(output, tools=self.tools, top='tb_memory',
                parameters={'READ_CYCLES': read, 'WRITE_CYCLES': write, 'SRAM_DELAY_NS': delay,
                            'WITH_UART': int(self.with_uart)},
                sources=('tb_memory.sv', 'memory.v', 'prim.v', 'uart_tx.v', 'memory_io.v'))

    def run(self, timing, *options):
        return run([self.tools.vvp, self.simulators[timing], *options], cwd=self.directory).stdout

    def compare_image(self, image, timing, max_steps=1000):
        if not image or len(image) > 65536:
            raise ValueError('Image must contain 1..65536 bytes')
        memory = bytearray([0xff]) * 65536
        memory[:len(image)] = image
        image_path = self.directory / 'image.hex'
        trace_path = self.directory / 'retirement.jsonl'
        uart_path = self.directory / 'uart.hex'
        image_path.write_text(''.join(f'{memory[i+1]:02x}{memory[i]:02x}\n'
                                      for i in range(0, 65536, 2)))
        output = self.run(timing, '+cpu', f'+image={image_path}', f'+trace={trace_path}', f'+uart={uart_path}')
        if 'PASS CPU SRAM integration' not in output:
            raise RuntimeError(f'CPU/SRAM simulation did not finish\n{output}')
        records = load_records(trace_path)
        steps = compare_records(image, records, max_steps=max_steps, uart=self.with_uart)
        actual = None
        if self.with_uart:
            memory = Memory(image, uart=True)
            cpu = Prim(memory)
            for _ in range(max_steps):
                if memory.read8(cpu._pc) in (Op.BREAK, Op.SIMEND):
                    break
                cpu.step()
            else:
                raise RuntimeError('Python UART reference did not halt')
            actual = bytes(int(line, 16) for line in uart_path.read_text().splitlines())
            if actual != bytes(memory.tx):
                raise AssertionError(f'UART output differs: RTL={actual!r}, Python={bytes(memory.tx)!r}')
        return SimulationResult(actual, steps, records)
