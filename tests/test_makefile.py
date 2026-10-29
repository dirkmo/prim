#!/usr/bin/env python3
"""Top-level workflow tests in a disposable checkout with fake hardware tools."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from prim.artifacts import load_program

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('make'), 'GNU make is required')
class MakefileChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prim-make-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT / 'Makefile', self.root / 'Makefile')
        shutil.copytree(ROOT / 'tools', self.root / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
        source = self.root / 'src'
        source.mkdir()
        for name in ('Makefile', 'bootstrap.cf', 'base.cf', 'test.cf', 'interpreter.cf'):
            shutil.copy2(ROOT / 'src' / name, source / name)
        shutil.copytree(ROOT / 'src/prim', source / 'prim', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'src/examples', source / 'examples')
        shutil.copy2(ROOT / 'pyproject.toml', self.root / 'pyproject.toml')
        self.log = self.root / 'actions.jsonl'
        board = self.root / 'boards/olimex_ice40hx8k_evb'
        board.mkdir(parents=True)
        (board / 'host.py').write_text(
            'import json,sys\nfrom pathlib import Path\n'
            f'with Path({str(self.log)!r}).open("a") as f: '
            'f.write(json.dumps({"kind":"host","args":sys.argv[1:]})+"\\n")\n')
        self.cmake = self.root / 'fake-cmake'
        self.cmake.write_text(
            f'#!{sys.executable}\nimport json,sys\nfrom pathlib import Path\n'
            f'with Path({str(self.log)!r}).open("a") as f: '
            'f.write(json.dumps({"kind":"cmake","args":sys.argv[1:]})+"\\n")\n'
            'if "--build" in sys.argv:\n'
            '    p=Path(sys.argv[sys.argv.index("--build")+1]);p.mkdir(parents=True,exist_ok=True)\n'
            '    (p/"prim.bin").write_bytes(b"bitstream")\n')
        self.cmake.chmod(0o755)
        (self.root / 'cpu/tests').mkdir(parents=True)
        (self.root / 'cpu/tests/test.asm').write_text('1 2 + BREAK\n')

    def make(self, *args, ok=True):
        env = dict(os.environ)
        for name in ('MAKEFLAGS', 'MFLAGS', 'MAKELEVEL'):
            env.pop(name, None)
        result = subprocess.run(['make', '--no-print-directory', f'PYTHON={sys.executable}',
                                 f'SYSTEM_PYTHON={sys.executable}', f'CMAKE={self.cmake}', *args],
                                cwd=self.root, env=env, text=True, capture_output=True, timeout=60)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def actions(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_default_only_prints_help(self):
        output = self.make('PYTHON=/missing/python')
        for target in ('image', 'flash', 'upload', 'load-run', 'uart-console', 'SKIP_UART_MMIO'):
            self.assertIn(target, output)
        self.assertEqual(self.actions(), [])
        self.assertFalse((self.root / 'build').exists())

    def test_image_pipeline_incremental_and_source_identity(self):
        self.make('-j4', 'software', 'image')
        binary = self.root / 'build/software/hello.bin'
        compiled = self.root / 'build/software/hello.tf.toml'
        data = binary.read_bytes()
        self.assertEqual(len(data), 65536)
        self.assertEqual(data, load_program(compiled).memory)
        self.assertEqual((data[0], data[3], data[4]), (0x21, 0x01, 0x22))
        stamps = {p: p.stat().st_mtime_ns for p in (binary, compiled, self.root / 'build/software/hello.tok.toml')}
        output = self.make('image')
        self.assertNotIn('-m prim compile', output)
        self.assertEqual(stamps, {p: p.stat().st_mtime_ns for p in stamps})
        # Same basename, different source path, with an older source timestamp.
        other = self.root / 'custom/hello.cf'
        other.parent.mkdir()
        other.write_text(':main 17 ; [ \'main boot! ]\n')
        os.utime(other, (1, 1))
        self.make('image', f'PROGRAM={other}')
        self.assertNotEqual(binary.read_bytes(), data)
        self.assertEqual(self.actions(), [])

    def test_assembly_and_upload_existing_binary_do_not_build_cf_or_flash(self):
        self.make('asm')
        binary = self.root / 'build/software/test.asm.bin'
        self.assertEqual(binary.read_bytes(), bytes([0x20, 1, 0x20, 2, 0x0c, 0x22]))
        port = "device'; touch injected; echo '"
        self.make('upload', f'IMAGE={binary}', f'PORT={port}', 'PROGRAM=/missing/source.cf', 'SKIP_UART_MMIO=1')
        actions = self.actions()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['kind'], 'host')
        self.assertEqual(actions[0]['args'], ['--port', port, '--timeout', '2', 'load', str(binary), '--skip-uart-mmio', '--write-delay', '0'])
        self.assertFalse((self.root / 'injected').exists())
        self.assertFalse((self.root / 'build/src').exists())
        self.make('upload', f'IMAGE={binary}', 'PORT=/dev/test', 'VERIFY=1')
        self.assertIn('--verify', self.actions()[-1]['args'])
        count = len(self.actions())
        self.make('upload', f'IMAGE={binary}', 'PORT=/dev/test', 'VERIFY=invalid', ok=False)
        self.assertEqual(len(self.actions()), count)

    def test_hardware_guards_and_dry_run(self):
        for target in ('status', 'uart-console', 'upload', 'load-run'):
            output = self.make('-j4', target, ok=False)
            self.assertIn('PORT is required', output)
        self.assertEqual(self.actions(), [])
        self.assertFalse((self.root / 'build').exists())
        self.make('-n', 'flash')
        self.make('-n', 'load-run', 'PORT=/dev/test', 'SKIP_UART_MMIO=1')
        self.assertEqual(self.actions(), [])
        self.assertFalse((self.root / 'build').exists())
        self.make('status', 'PORT=/dev/test', 'BOARD=unknown', ok=False)
        self.assertEqual(self.actions(), [])

    def test_load_run_orders_build_before_upload_and_stops_on_failure(self):
        self.make('load-run', 'PORT=/dev/test', 'SKIP_UART_MMIO=1', 'VERIFY=1', 'WRITE_DELAY=0.001')
        action = self.actions()[-1]
        self.assertEqual(action['kind'], 'host')
        self.assertEqual(action['args'][-1], '--run')
        self.assertIn('--skip-uart-mmio', action['args'])
        self.assertIn('--verify', action['args'])
        self.assertEqual(action['args'][-3:-1], ['--write-delay', '0.001'])
        image = self.root / 'build/software/hello.bin'
        self.assertTrue(image.is_file())
        self.log.unlink()
        (self.root / 'src/examples/hello.cf').write_text('word-that-does-not-exist\n')
        self.make('load-run', 'PORT=/dev/test', 'SKIP_UART_MMIO=1', ok=False)
        self.assertEqual(self.actions(), [])

    def test_board_targets_delegate_and_local_config(self):
        (self.root / 'config.local.mk').write_text('PORT := /dev/local-uart\nTIMEOUT := 5\n')
        self.make('status')
        self.assertEqual(self.actions()[-1]['args'][:4], ['--port', '/dev/local-uart', '--timeout', '5'])
        self.make('bitstream', "ICEPROG_DEVICE=s:0403:6010:serial's", 'ICEPROG_INTERFACE=B')
        actions = self.actions()
        self.assertTrue(any('-DOLIMEX_ICEPROG_DEVICE=s:0403:6010:serial\'s' in x['args'] for x in actions))
        self.assertFalse(any('fpga_program' in x['args'] for x in actions))
        self.make('flash')
        self.assertEqual(self.actions()[-1]['args'][3], 'fpga_program')
        self.assertEqual(self.actions()[-1]['kind'], 'cmake')
        self.assertTrue((self.root / 'build/olimex_ice40hx8k_evb/prim.bin').is_file())

    def test_clean_only_managed_trees_and_rejects_source_or_symlink(self):
        managed = ['src', 'software', 'sim', 'olimex_ice40hx8k_evb']
        for name in managed:
            directory = self.root / 'build' / name
            directory.mkdir(parents=True)
            (directory / 'artifact').write_text('generated')
        (self.root / 'build/keep.txt').write_text('keep')
        (self.root / '.venv').mkdir()
        (self.root / '.venv/keep').write_text('keep')
        self.make('clean', f'SIM_BUILD_DIR={self.root / "src"}', ok=False)
        for name in managed:
            self.assertTrue((self.root / 'build' / name / 'artifact').exists())
        (self.root / 'build/outside').symlink_to(self.root / 'src', target_is_directory=True)
        self.make('clean', 'SIM_BUILD_DIR=build/outside', ok=False)
        self.assertTrue((self.root / 'src/base.cf').exists())
        self.make('clean')
        for name in managed:
            self.assertFalse((self.root / 'build' / name).exists())
        self.assertTrue((self.root / 'build/keep.txt').is_file())
        self.assertTrue((self.root / '.venv/keep').is_file())

    def test_resource_report_uses_routed_and_synthesis_counts(self):
        directory = self.root / 'build/report'
        directory.mkdir(parents=True)
        usage = {name: {'used': used, 'available': available} for name, used, available in [
            ('ICESTORM_LC', 100, 7680), ('ICESTORM_RAM', 0, 32), ('ICESTORM_PLL', 1, 2),
            ('SB_GB', 3, 8), ('SB_IO', 43, 206)]}
        (directory / 'timing.json').write_text(json.dumps({'utilization': usage,
            'fmax': {'clk_sys': {'achieved': 50.12, 'constraint': 25}}}))
        cells = {str(i): {'type': kind} for i, kind in enumerate(['SB_LUT4', 'SB_LUT4', 'SB_DFF', 'SB_DFFE', 'SB_CARRY'])}
        (directory / 'prim.json').write_text(json.dumps({'modules': {'top': {'attributes': {'top': '1'}, 'cells': cells}}}))
        result = subprocess.run([sys.executable, self.root / 'tools/project.py', 'resources', '--build-dir', directory],
                                capture_output=True, text=True, check=True)
        self.assertIn('50.12 MHz (PASS)', result.stdout)
        self.assertIn('Carry cells (synthesized): 1', result.stdout)
        self.assertIn('Logic cells (routed)', result.stdout)
        self.assertNotIn('Traceback', result.stdout)


if __name__ == '__main__':
    unittest.main()
