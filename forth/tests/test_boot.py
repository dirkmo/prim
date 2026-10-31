"""AP 2 build/boot checks; add --rtl for physical SRAM/UART simulation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

from forth.build import build_image, memory_map
from forth.kernel.boot import VARIABLES
from forth.image import Image, Ref
from prim.cpu import Prim
from prim.isa import PrimOpcodes as Op
from support.reference import Memory

RTL = False


class BootChecks(unittest.TestCase):
    def test_artifacts_reproducible_from_foreign_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in ('a', 'b'):
                subprocess.run([sys.executable, str(ROOT / 'forth/build.py'),
                                '--output', str(directory / name)],
                               cwd=directory, check=True, capture_output=True)
            for name in ('kernel.bin', 'kernel.map.json', 'kernel.disasm'):
                self.assertEqual((directory / 'a' / name).read_bytes(),
                                 (directory / 'b' / name).read_bytes())
            data = (directory / 'a/kernel.bin').read_bytes()
            mapping = json.loads((directory / 'a/kernel.map.json').read_text())
            self.assertEqual(len(data), 65520)
            self.assertEqual(mapping['image']['entry'], 0)
            regions = mapping['regions']
            self.assertEqual(regions[0]['start'], 0)
            self.assertEqual(regions[-1]['end_exclusive'], 65536)
            for left, right in zip(regions, regions[1:]):
                self.assertEqual(left['end_exclusive'], right['start'])
            start = mapping['symbols']['user_start']
            self.assertEqual(start % 2, 0)
            self.assertLess(start, 0xF000)
            self.assertEqual(data[start:], bytes(65520 - start))

    def test_cold_start_reinitializes_dirty_runtime_without_erasing_user_ram(self):
        image = build_image()
        memory = Memory(image.memory, uart=True)
        memory.data[0x100:0x400] = b'\xa5' * 0x300
        memory.data[0xE000:0xE004] = b'kept'
        cpu = Prim(memory)
        for _ in range(2):
            variable_end = 0x100 + 2 * len(VARIABLES)
            memory.data[0x100:variable_end] = b'\xa5' * (variable_end - 0x100)
            memory.uart_ie = 12  # CPU reset alone preserves peripheral enables.
            cpu.reset()
            cpu._int_enable = True  # INTDI must actually disable, not rely on reset.
            max_data = max_return = 0
            for steps in range(500):
                if cpu._pc == image.symbols['idle']:
                    break
                cpu.step()
                max_data = max(max_data, cpu._dsp)
                max_return = max(max_return, cpu._rsp)
            else:
                self.fail('boot did not reach idle within 500 instructions')
            self.assertGreater(steps, 0)
            self.assertEqual((max_data, max_return), (2, 0))
            self.assertEqual((cpu._dsp, cpu._rsp), (0, 0))
            self.assertFalse(cpu._int_enable)
            self.assertEqual(memory.uart_ie, 0)
            self.assertEqual(memory.tx, [])
            self.assertEqual(memory.read16(0x100), image.symbols['user_start'])
            self.assertEqual(memory.read16(0x102), image.symbols['kernel_latest'])
            self.assertEqual(memory.read16(0x104), 10)
            self.assertEqual(memory.data[0x106:variable_end], bytes(variable_end - 0x106))
            self.assertEqual(memory.data[0x200], 0)
            self.assertEqual(memory.data[0x280], 0)
            self.assertEqual(memory.data[0xE000:0xE004], b'kept')
            self.assertEqual([w for w in memory.writes if w[0] >= 0xFFF0],
                             [[0xFFFE, 0]])
            memory.writes.clear()
            # The production image idles indefinitely, without BREAK or frames.
            for _ in range(12):
                self.assertNotIn(cpu.step(), (Op.BREAK, Op.SIMEND))
            self.assertEqual(cpu._pc, image.symbols['idle'])
            self.assertEqual((cpu._dsp, cpu._rsp), (0, 0))
            self.assertEqual(memory.writes, [])

    def test_invalid_image_rejected(self):
        image = Image()
        image.push(Ref('missing'))
        with self.assertRaisesRegex(ValueError, 'undefined symbol'):
            image.resolve()
        with self.assertRaisesRegex(ValueError, 'duplicate symbol'):
            image.define('x', 1)
            image.define('x', 2)
        image.org(0)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            image.emit([0])
        image.org(0xFFEF)
        with self.assertRaisesRegex(ValueError, 'MMIO'):
            image.emit([0, 0])

    def test_rtl_cold_start(self):
        if not RTL:
            self.skipTest('enable CPU + physical SRAM + UART checks with --rtl')
        from support.config import Tools
        from support.paths import TIMINGS
        from support.sram import SramSimulation

        image = build_image()
        fixture = bytearray(image.memory)
        # Test-only stop at idle; the production binary has an infinite JP loop.
        fixture[image.symbols['idle']] = Op.BREAK
        fixture[0x100:0x400] = b'\xa5' * 0x300
        with tempfile.TemporaryDirectory(prefix='forth-boot-rtl-') as directory:
            simulation = SramSimulation(directory, Tools(), with_uart=True)
            simulation.build()
            for timing in TIMINGS:
                with self.subTest(timing=timing):
                    result = simulation.compare_image(fixture, timing, max_steps=500)
                    self.assertEqual(result.serial, b'')
                    writes = [w for record in result.records
                              for w in record.get('writes', [])]
                    expected = {address: 0 for address in range(0x100, 0x100 + 2 * len(VARIABLES))}
                    start = image.symbols['user_start']
                    latest = image.symbols['kernel_latest']
                    expected.update({0x100: start & 255, 0x101: start >> 8,
                                     0x102: latest & 255, 0x103: latest >> 8,
                                     0x104: 10, 0x200: 0, 0x280: 0, 0xFFFE: 0})
                    self.assertEqual(dict(writes), expected)
                    self.assertEqual(len(writes), len(expected))
                    retired = [r for r in result.records if r['kind'] == 'step']
                    self.assertEqual(max(r['dsp'] for r in retired), 2)
                    self.assertTrue(all(r['rsp'] == 0 for r in retired))
                    self.assertEqual(retired[-1]['pc'], image.symbols['idle'])
                    print(f'PASS Forth boot RTL {timing}: {result.steps} instructions')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl', action='store_true')
    options, remaining = parser.parse_known_args()
    RTL = options.rtl
    unittest.main(argv=[sys.argv[0], *remaining])
