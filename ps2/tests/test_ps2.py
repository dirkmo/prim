#!/usr/bin/env python3
"""PS/2 receiver, FIFO and integrated byte-bus/interrupt scoreboards."""
import argparse
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PS2Tests(unittest.TestCase):
    iverilog = 'iverilog'
    vvp = 'vvp'

    def simulate(self, top, parameters, sources):
        with tempfile.TemporaryDirectory(prefix='prim-ps2-') as directory:
            binary = Path(directory) / top
            command = [self.iverilog, '-g2012', '-Wall', '-s', top, '-o', str(binary)]
            for key, value in parameters.items():
                command += ['-P', f'{top}.{key}={value}']
            subprocess.run([*command, *(str(ROOT / p) for p in sources)], check=True,
                           capture_output=True, text=True, timeout=30)
            result = subprocess.run([self.vvp, str(binary)], check=False,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS', result.stdout)

    def test_receiver(self):
        for filt in (1, 2, 8):
            with self.subTest(filter=filt):
                self.simulate('tb_ps2_rx', {'FILTER': filt},
                              ['ps2/rtl/ps2_rx.v', 'ps2/tests/tb_ps2_rx.sv'])

    def test_fifo(self):
        for depth in (1, 2, 16):
            with self.subTest(depth=depth):
                self.simulate('tb_ps2_fifo', {'DEPTH': depth},
                              ['ps2/rtl/ps2_fifo.v', 'ps2/tests/tb_ps2_fifo.sv'])

    @unittest.skipUnless(shutil.which('yosys') and shutil.which('yosys-config'),
                         'Yosys and its cell models needed for inferred-EBR check')
    def test_synthesized_fifo(self):
        # Exercise the independent FIFO scoreboard against the actual iCE40
        # primitives, including read/write forwarding inferred around EBR.
        with tempfile.TemporaryDirectory(prefix='prim-ps2-synth-') as directory:
            directory = Path(directory)
            netlist = directory / 'fifo.v'
            script = (f'read_verilog "{ROOT / "ps2/rtl/ps2_fifo.v"}"; '
                      f'synth_ice40 -top ps2_fifo; write_verilog -noattr "{netlist}"')
            result = subprocess.run(['yosys', '-Q', '-T', '-p', script],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            datdir = subprocess.check_output(['yosys-config', '--datdir'], text=True).strip()
            bench = directory / 'tb.sv'
            bench.write_text((ROOT / 'ps2/tests/tb_ps2_fifo.sv').read_text().replace(
                'ps2_fifo #(.DEPTH(DEPTH)) dut', 'ps2_fifo dut'))
            binary = directory / 'fifo'
            subprocess.run([self.iverilog, '-g2012', '-s', 'tb_ps2_fifo',
                            '-o', str(binary), str(netlist), str(bench),
                            str(Path(datdir) / 'ice40/cells_sim.v')],
                           check=True, capture_output=True, text=True, timeout=30)
            result = subprocess.run([self.vvp, str(binary)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS', result.stdout)

    def test_mmio_irq(self):
        for video in (0, 1):
            with self.subTest(video=video):
                self.simulate('tb_ps2_mmio', {'VIDEO': video}, [
                    'ps2/tests/tb_ps2_mmio.sv', 'ps2/rtl/ps2_rx.v', 'ps2/rtl/ps2_fifo.v',
                    'system/rtl/memory_io.v', 'system/rtl/memory.v',
                    'system/rtl/timer_mmio.v', 'timer/rtl/timer.v',
                    'vga/rtl/vga_text.v', 'vga/rtl/vga_font.v'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iverilog', default='iverilog')
    parser.add_argument('--vvp', default='vvp')
    args, remaining = parser.parse_known_args()
    PS2Tests.iverilog, PS2Tests.vvp = args.iverilog, args.vvp
    unittest.main(argv=[__file__, *remaining])
