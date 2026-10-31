"""Reusable Forth-owned UART-buffer session simulator, no host interpretation."""
from pathlib import Path
from support.process import run

ROOT = Path(__file__).resolve().parents[2]


class RtlConsole:
    def __init__(self, directory, image):
        self.directory, self.image = Path(directory), image
        self.simulator = self.directory / 'console'
        self.image_path = self.directory / 'image.hex'
        self.image_path.write_text(''.join(f'{b:02x}\n' for b in bytes(image.memory) + bytes(16)))
        run(['iverilog', '-g2012', '-s', 'tb_parser', '-P', 'tb_parser.SESSION=1',
             '-I', ROOT / 'cpu/rtl', '-o', self.simulator, ROOT / 'forth/tests/tb_parser.sv',
             ROOT / 'cpu/rtl/prim.v', ROOT / 'debug_uart/rtl/uart_buffers.v'])

    def session(self, payload):
        rx, tx, ram, stack = [self.directory / f'{n}.hex' for n in ('rx', 'tx', 'ram', 'stack')]
        rx.write_text(''.join(f'{b:02x}\n' for b in payload))
        result = run(['vvp', self.simulator, f'+image={self.image_path}', f'+rx={rx}',
                      f'+count={len(payload)}', f'+tx={tx}', f'+ram={ram}',
                      f'+stack={stack}', f'+waitpc={self.image.symbols["console_next"]}',
                      f'+keypc={self.image.symbols["raw_key"]}'])
        if 'PASS Forth console text session' not in result.stdout:
            raise AssertionError(result.stdout)
        memory = bytes(int(x, 16) for line in ram.read_text().splitlines()
                       for x in line.split('//')[0].split())
        return (bytes(int(x, 16) for x in tx.read_text().split()),
                [int(x, 16) for x in stack.read_text().split()], memory)
