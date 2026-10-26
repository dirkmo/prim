#!/usr/bin/env python3
"""Fresh .cf -> tokens -> compiled memory -> CPU/SRAM/UART end-to-end test."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest

import test_sram
from compare import ROOT, Op
from primconsts import Consts

test_sram.parser.add_argument('--compiler-python', type=Path,
                              help='Python interpreter with the toml package installed')
args, remaining = test_sram.parser.parse_known_args()
SRC = ROOT / 'src'
ARTIFACTS = ROOT / 'build' / 'tokenforth'
EXAMPLES = {'hello': b'Hello, World!\r\n',
            'control': b'BACCC012',
            'data': b'ABCZ'}


class TokenForthChecks(test_sram.SramHarness, unittest.TestCase):
    with_uart = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        candidates = ([args.compiler_python] if args.compiler_python else
                      [Path(sys.executable), ROOT / '.venv' / 'bin' / 'python'])
        cls.compiler_python = None
        for candidate in candidates:
            if candidate.is_file():
                probe = subprocess.run([str(candidate), '-c', 'import toml'],
                                       capture_output=True, text=True, timeout=10)
                if probe.returncode == 0:
                    # Preserve the venv executable path (resolving its symlink
                    # would bypass pyvenv.cfg and lose installed dependencies).
                    cls.compiler_python = candidate.absolute()
                    break
        if cls.compiler_python is None:
            raise RuntimeError('TokenForth requires toml: install toml==0.10.2 in your '
                               'Python environment or specify --compiler-python')
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        cls.stage('base-tokenize', 'tokenizer.py', '-i', SRC / 'base.cf',
                  '-o', ARTIFACTS / 'base.tok.toml')
        cls.stage('base-compile', 'tokenforth.py', '-i', ARTIFACTS / 'base.tok.toml',
                  '-o', ARTIFACTS / 'base.tf.toml')
        cls.images = {}
        for name in EXAMPLES:
            tokens = ARTIFACTS / f'{name}.tok.toml'
            compiled = ARTIFACTS / f'{name}.tf.toml'
            binary = ARTIFACTS / f'{name}.bin'
            cls.stage(f'{name}-tokenize', 'tokenizer.py', '-i', SRC / 'examples' / f'{name}.cf',
                      '-o', tokens, '-it', ARTIFACTS / 'base.tf.toml')
            cls.stage(f'{name}-compile', 'tokenforth.py', '-i', tokens, '-o', compiled)
            cls.stage(f'{name}-export', 'binexport.py', '-i', compiled, '-o', binary, '-s', 'memory')
            cls.images[name] = binary.read_bytes()

    @classmethod
    def stage(cls, name, script, *arguments):
        result = subprocess.run([str(cls.compiler_python), str(SRC / script),
                                 *(str(arg) for arg in arguments)],
                                cwd=ARTIFACTS, capture_output=True, text=True, timeout=30)
        (ARTIFACTS / f'{name}.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f'{name} failed\n{result.stdout}\n{result.stderr}')
        if 'uart-tx:' in result.stdout:
            raise RuntimeError(f'{name}: UART output happened at compile time, not runtime')

    def test_artifacts_and_reset_entry(self):
        base = tomllib.loads((ARTIFACTS / 'base.tf.toml').read_text())
        self.assertEqual(base['type'], 'tokenforth')
        for name, image in self.images.items():
            with self.subTest(program=name):
                tokens = tomllib.loads((ARTIFACTS / f'{name}.tok.toml').read_text())
                compiled = tomllib.loads((ARTIFACTS / f'{name}.tf.toml').read_text())
                self.assertEqual(tokens['type'], 'tokenizer')
                self.assertEqual(tokens['memory'], base['memory'])
                self.assertTrue(tokens['tokens'])
                self.assertEqual(compiled['type'], 'tokenforth')
                self.assertEqual(image, bytes(compiled['memory']))
                self.assertEqual(len(image), 65536)
                self.assertEqual((image[0], image[3], image[4]), (Op.PUSH, Op.CALL, Op.BREAK))
                entry = image[1] | image[2] << 8
                index = compiled['symbols'].index('main')
                cell = Consts.DICT - 2 * index
                self.assertEqual(entry, image[cell] | image[cell+1] << 8)

    def test_compiled_programs_on_cpu_sram_uart(self):
        for name, image in self.images.items():
            for timing in test_sram.TIMINGS:
                with self.subTest(program=name, timing=timing):
                    actual = self.compare_image(image, timing)
                    self.assertEqual(actual, EXAMPLES[name])
                    tag = f'{name}-{timing[0]}-{timing[1]}'
                    (ARTIFACTS / f'{tag}.uart.bin').write_bytes(actual)
                    trace = (self.directory / 'retirement.jsonl').read_text()
                    (ARTIFACTS / f'{tag}.jsonl').write_text(trace)
                    steps = len([line for line in trace.splitlines()
                                 if json.loads(line)['kind'] == 'step'])
                    print(f'PASS TokenForth {name}: {steps} instructions, '
                          f'UART={actual!r}, SRAM timing={timing}')


if __name__ == '__main__':
    unittest.main(argv=[__file__, *remaining])
