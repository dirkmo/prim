"""Ordered source builds, base selection and command-line output."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prim.artifacts import load_program
from prim.build import build_files
from prim.compiler import Mif
from prim.cpu import Prim
from prim.errors import CompileError
from prim.isa import Consts, PrimOpcodes as Op

ROOT = Path(__file__).resolve().parents[1]


class SourceBuildChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prim-build-cf-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.library = self.directory / 'my library.cf'
        self.program = self.directory / 'main.cf'
        self.library.write_text(':answer 41 ;\n', encoding='utf-8')

    def test_base_and_ordered_files_produce_runnable_image(self):
        self.program.write_text(":main answer 1+ ;\n[ 'main boot! ]\n")
        image = build_files([self.library, self.program])
        cpu = Prim(Mif(image.memory))
        for _ in range(100):
            if cpu.step() == Op.BREAK:
                break
        else:
            self.fail('Reset entry did not finish')
        self.assertEqual(cpu.dpop(), 42)

    def test_no_base_still_carries_custom_words_forward(self):
        self.program.write_text(':main answer 1 + ;\n')
        image = build_files([self.library, self.program], base=False)
        self.assertEqual(list(image.symbols), ['H', 'LATEST', 'answer', 'main'])
        memory = Mif(image.memory)
        cpu = Prim(memory)
        cpu._pc = memory.read16(Consts.DICT - 3 * 2)
        memory.write8(0, Op.BREAK)
        cpu.rpush(0)
        for _ in range(100):
            if cpu.step() == Op.BREAK:
                break
        else:
            self.fail('Custom word did not return')
        self.assertEqual(cpu.dpop(), 42)

    def test_dependencies_must_precede_use_and_base_can_be_disabled(self):
        self.program.write_text(':main answer 1+ ;\n')
        with self.assertRaisesRegex(CompileError, 'Unknown word.*answer'):
            build_files([self.program, self.library])
        with self.assertRaisesRegex(CompileError, r'Unknown word.*1\+'):
            build_files([self.library, self.program], base=False)

    def test_script_and_module_cli_from_other_directory(self):
        self.program.write_text(':main answer ;\n')
        for command in ([sys.executable, str(ROOT / 'tools/build_cf.py')],
                        [sys.executable, '-m', 'prim', 'build']):
            with self.subTest(command=command):
                result = subprocess.run([*command, '--no-base', str(self.library),
                                         str(self.program), '--toml', 'out/main.tf.toml'],
                                        cwd=self.directory, capture_output=True,
                                        text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                image = load_program(self.directory / 'out/main.tf.toml')
                self.assertEqual((self.directory / 'build/software/main.bin').read_bytes(),
                                 image.memory)
                self.assertEqual(len(image.memory), 65536)

    def test_failed_build_preserves_existing_output(self):
        self.program.write_text(':main missing ;\n')
        output = self.directory / 'main.bin'
        output.write_bytes(b'previous image')
        result = subprocess.run([sys.executable, '-m', 'prim', 'build', '--no-base',
                                 str(self.program), '-o', str(output)],
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f'{self.program}:1:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(output.read_bytes(), b'previous image')


if __name__ == '__main__':
    unittest.main()
