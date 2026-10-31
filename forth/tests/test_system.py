"""Mixed whole-kernel programs and the complete serial system boundary."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'src', ROOT / 'tests'):
    sys.path.insert(0, str(path))
from forth.build import build_image
from forth.tests.model import cell, lookup, session
from forth.tests.tools import configured_tools
from forth.tests.rtl_console import RtlConsole
from forth.kernel.boot import VARIABLES
from support.paths import source_path
from support.process import run

RTL = False
LINES = [
    (b'VARIABLE total', b''),
    (b': sum BEGIN DUP WHILE DUP total +! 1- REPEAT DROP ;', b''),
    (b'0 total ! 3 sum total @ .', b'6 '),
    (b': text ." done" ; text', b'done'),
    (b': bad IF ;', b'error: unresolved control\r\n'),
    (b'42 .', b'42 '),
]
SOURCE = b''.join(line + b'\n' for line, _ in LINES)
EXPECTED = b'ok\r\n' + b''.join(line + b'\r\n' + result + b'ok\r\n' for line, result in LINES)


class SystemChecks(unittest.TestCase):
    def test_mixed_session_and_reset(self):
        image = build_image()
        output, stack, memory, _ = session(image, SOURCE)
        self.assertEqual(output, EXPECTED)
        self.assertEqual(stack, [])
        self.assertEqual(cell(memory, lookup(memory, 'total')[1] + 8), 6)
        self.assertEqual(cell(memory, VARIABLES['last_error']), 17)
        output, _, reset_memory, _ = session(image, b'WORDS\n')
        self.assertNotIn(b'total', output)
        self.assertEqual(cell(reset_memory, VARIABLES['latest']), image.symbols['kernel_latest'])

    def test_mixed_uart_buffer_session(self):
        if not RTL:
            self.skipTest('enable mixed UART-buffer session with --rtl')
        with tempfile.TemporaryDirectory(prefix='forth-mixed-') as directory:
            output, stack, _ = RtlConsole(directory, build_image()).session(SOURCE)
            self.assertEqual(output, EXPECTED)
            self.assertEqual(stack, [])

    def test_complete_serial_rx_tx_system(self):
        if not RTL:
            self.skipTest('enable complete serial RX/TX system with --rtl')
        tools = configured_tools()
        with tempfile.TemporaryDirectory(prefix='forth-wire-') as directory:
            directory = Path(directory)
            image = bytes(build_image().memory) + bytes(16)
            image_file, source_file, expected_file, tx_file = [directory / (n + '.hex')
                for n in ('image', 'source', 'expected', 'tx')]
            image_file.write_text(''.join(f'{image[n+1]:02x}{image[n]:02x}\n' for n in range(0, 65536, 2)))
            for file, data in ((source_file, SOURCE), (expected_file, EXPECTED)):
                file.write_text(''.join(f'{b:02x}\n' for b in data))
            modules = ('prim.v', 'prim_system.v', 'memory.v', 'memory_io.v', 'bus_mux.v',
                       'timer_mmio.v', 'timer.v', 'uart_rx.v', 'uart_tx.v', 'uart_buffers.v',
                       'uart_arbiter.v', 'debug_uart.v', 'debug_uart_link.v')
            binary = directory / 'system'
            run([tools.iverilog, '-g2012', '-s', 'tb_system', '-I', ROOT / 'cpu/rtl',
                 '-o', binary, ROOT / 'forth/tests/tb_system.sv', *(source_path(n) for n in modules)])
            result = run([tools.vvp, binary, f'+image={image_file}', f'+source={source_file}',
                          f'+expected={expected_file}', f'+output={tx_file}',
                          f'+source_count={len(SOURCE)}', f'+expected_count={len(EXPECTED)}'], timeout=120)
            self.assertIn('PASS complete Forth serial', result.stdout)
            captured = bytes(int(line, 16) for line in tx_file.read_text().split())
            if os.environ.get('FORTH_TEST_ARTIFACTS'):
                artifacts = Path(os.environ['FORTH_TEST_ARTIFACTS'])
                artifacts.mkdir(parents=True, exist_ok=True)
                (artifacts / 'session.fs').write_bytes(SOURCE)
                (artifacts / 'expected.uart.bin').write_bytes(EXPECTED)
                (artifacts / 'actual.uart.bin').write_bytes(captured)
            self.assertEqual(captured, EXPECTED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
