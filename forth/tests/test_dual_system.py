"""Complete physical-wire RTL session for the default dual-console kernel."""
import argparse
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'src', ROOT / 'tests'):
    sys.path.insert(0, str(path))
from forth.build import build_image, memory_map
from forth.kernel.keyboard import key_tables
from forth.tests.tools import configured_tools
from support.paths import source_path
from support.process import run

RTL = False
EXPECTED = (b'ok\r\n7 twice .\r\n14 ok\r\n'
            b': take key . ;\r\nok\r\ntake\r\n65 ok\r\n'
            b'2 .\r\n2 ok\r\n'
            b': scroll 35 BEGIN CR 1- DUP 0= UNTIL DROP ;\r\nok\r\n'
            b': busy BEGIN 20480 @ UNTIL ;\r\nok\r\nbusy\r\nok\r\n'
            b'TIMER-INIT 2 MS 0 MS\r\nok\r\n'
            b'32768 4 65 FILL 32768 32769 3 MOVE 32771 C@ .\r\n65 ok\r\n'
            b'MARKER snap : gone 9 ; snap\r\nok\r\n'
            b'VARIABLE hits : tick 1 hits +! ; 5 \' tick TIMER-EVERY 12 MS '
            b'0 TIMER-CALLBACK! hits @ 0 > .\r\n-1 ok\r\n')
LOCAL = (': twice dup + ;\r', 'nope\r', '9 .\r', '3 .\r', 'scroll\r', '1234 .\r')


def scan_sequence(text):
    """Physical make and break bytes, including real modifier release."""
    normal, shifted, altgr = key_tables()
    result = []
    for byte in text.encode():
        if byte in normal and byte:
            scan = normal.index(byte)
            result += [scan, 0xF0, scan]
        elif byte in shifted and byte:
            scan = shifted.index(byte)
            result += [0x12, scan, 0xF0, scan, 0xF0, 0x12]
        elif byte in altgr and byte:
            scan = altgr.index(byte)
            result += [0xE0, 0x11, scan, 0xF0, scan, 0xE0, 0xF0, 0x11]
        else:
            raise ValueError(f'unencodable fixture byte {byte}')
    return result


class DualSystemChecks(unittest.TestCase):
    def test_wire_session(self):
        if not RTL:
            self.skipTest('use --rtl for CPU/SRAM/UART/PS2/VGA integration')
        directory = Path(os.environ.get('FORTH_TEST_ARTIFACTS', ROOT / 'build/dual-system-tests'))
        directory.mkdir(parents=True, exist_ok=True)
        image = build_image()
        data = bytes(image.memory).ljust(0x10000, b'\0')
        image_file = directory / 'image.hex'
        image_file.write_text(''.join(f'{data[n+1]:02x}{data[n]:02x}\n' for n in range(0, 65536, 2)))
        (directory / 'kernel.map.json').write_text(json.dumps(memory_map(image), indent=2) + '\n')
        expected_file, keys_file, output_file = (directory / n for n in ('expected.hex', 'keys.hex', 'actual.hex'))
        expected_file.write_text(''.join(f'{byte:02x}\n' for byte in EXPECTED))
        keys = [scan_sequence(text) for text in LOCAL]
        keys_file.write_text(''.join(f'{byte:02x}\n' for segment in keys for byte in segment))
        modules = ('prim_system.v', 'memory.v', 'memory_io.v', 'bus_mux.v',
                   'timer_mmio.v', 'timer.v', 'uart_rx.v', 'uart_tx.v', 'uart_buffers.v',
                   'uart_arbiter.v', 'debug_uart.v', 'debug_uart_link.v', 'ps2_rx.v', 'ps2_fifo.v')
        tools = configured_tools()
        binary = directory / 'dual-system'
        # This is a wire/behavior test, not a retirement-trace comparison.
        # Keep production CPU behavior while avoiding a log line per instruction.
        cpu_source = directory / 'prim.v'
        cpu_source.write_text('\n'.join(
            line for line in source_path('prim.v').read_text().splitlines()
            if '$display("EXEC' not in line) + '\n')
        run([tools.iverilog, '-g2012', '-s', 'tb_dual_system', '-I', ROOT / 'cpu/rtl',
             '-o', binary, ROOT / 'forth/tests/tb_dual_system.sv', cpu_source,
             *(source_path(n) for n in modules),
             ROOT / 'vga/rtl/vga_text.v', ROOT / 'vga/rtl/vga_font.v'], log=directory / 'compile.log')
        result = run([tools.vvp, binary, f'+image={image_file}', f'+expected={expected_file}',
                      f'+keys={keys_file}', f'+output={output_file}', f'+expected_count={len(EXPECTED)}',
                      f'+waitpc={image.symbols["irq_wait"]}', f'+keypc={image.symbols["raw_key"]}',
                      f'+idlepc={image.symbols["idle"]}',
                      *(f'+k{n}={len(segment)}' for n, segment in enumerate(keys))],
                     timeout=420, log=directory / 'simulation.log', allowed=(0, 1, 2))
        self.assertEqual(result.returncode, 0, result.stdout[-5000:] + result.stderr[-2000:])
        self.assertIn('PASS dual Forth wires', result.stdout)
        actual = bytes(int(line, 16) for line in output_file.read_text().split())
        self.assertEqual(actual, EXPECTED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    args, remaining = parser.parse_known_args()
    RTL = args.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
