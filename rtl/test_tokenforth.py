#!/usr/bin/env python3
"""Fresh .cf -> tokens -> compiled memory -> CPU/SRAM/UART end-to-end test."""
import unittest

from prim.isa import PrimOpcodes as Op
import tomllib
from sim_support.config import run_tests
from sim_support.paths import ROOT, TIMINGS
from sim_support.tokenforth import TokenForthBuild
from sim_support.unittest_bridge import SramHarness
from prim.isa import Consts

ARTIFACTS = ROOT / 'build' / 'tokenforth'
EXAMPLES = {'hello': b'Hello, World!\r\n',
            'control': b'BACCC012',
            'data': b'ABCZ',
            'strings': 'Grüße 🙂 Raw ä \\ ( )\r\n'.encode('utf-8')}


class TokenForthChecks(SramHarness, unittest.TestCase):
    with_uart = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pipeline = TokenForthBuild(ARTIFACTS, cls.tools.compiler_python)
        cls.images = cls.pipeline.compile_examples(EXAMPLES)

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

    def test_python_toolchain_regressions(self):
        for script in ('test_toolchain.py', 'test.py', 'test_package.py'):
            with self.subTest(script=script):
                self.pipeline.run_regression(script)

    def test_compiled_programs_on_cpu_sram_uart(self):
        for name, image in self.images.items():
            for timing in TIMINGS:
                with self.subTest(program=name, timing=timing):
                    result = self.compare_result(image, timing)
                    actual = result.serial
                    self.assertEqual(actual, EXAMPLES[name])
                    tag = f'{name}-{timing[0]}-{timing[1]}'
                    result.save(ARTIFACTS / tag)
                    steps = result.steps
                    print(f'PASS TokenForth {name}: {steps} instructions, '
                          f'UART={actual!r}, SRAM timing={timing}')


if __name__ == '__main__':
    run_tests(TokenForthChecks, compiler=True)
