"""Installed-package and command-line smoke tests, independent of the cwd."""
from importlib import metadata
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class PackageChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prim-package-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def run_python(self, *arguments):
        return subprocess.run([sys.executable, '-I', *arguments], cwd=self.directory,
                              capture_output=True, text=True, timeout=15)

    def test_imports_are_independent_of_cwd_and_arguments(self):
        result = self.run_python('-c', '''
import sys
sys.argv = ['application', '--not-a-prim-option']
sys.modules['toml'] = None  # The old parser must no longer be required.
import prim
from prim import Prim, MemoryIf, PrimAsm, Consts, PrimOpcodes
from prim import cpu, isa, assembler, compiler, tokenizer, tokens, errors, exporter, disassembler, cli, artifacts
assert Prim is cpu.Prim
assert PrimOpcodes is isa.PrimOpcodes
assert not {'blessed', 'amaranth', 'amaranth_boards'} & set(sys.modules)
print('PASS imports')
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS imports')

    def test_metadata_and_optional_dependencies(self):
        package = metadata.distribution('prim-tokenforth')
        base = [item for item in package.requires if ';' not in item]
        self.assertEqual(base, ['tomli-w==1.2.0'])
        self.assertEqual(set(package.metadata.get_all('Provides-Extra')), {'debug', 'hdl'})
        commands = {entry.name for entry in package.entry_points if entry.group == 'console_scripts'}
        self.assertEqual(commands, {'prim', 'prim-asm', 'prim-tokenize', 'prim-compile',
                                    'prim-export', 'prim-disasm', 'prim-debug', 'prim-opcodes'})

    def test_module_commands(self):
        for command in ('asm', 'tokenize', 'compile', 'export', 'disasm', 'opcodes'):
            with self.subTest(command=command):
                result = self.run_python('-m', 'prim', command, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage:', result.stdout)
                self.assertNotIn('RuntimeWarning', result.stderr)

    def test_console_entry_points(self):
        scripts = Path(sys.executable).absolute().parent
        for command in ('prim', 'prim-asm', 'prim-tokenize', 'prim-compile',
                        'prim-export', 'prim-disasm', 'prim-opcodes'):
            with self.subTest(command=command):
                result = subprocess.run([str(scripts / command), '--help'], cwd=self.directory,
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage:', result.stdout)

    def test_legacy_and_package_assembler(self):
        source = self.directory / 'program.asm'
        source.write_text('1 2 + BREAK')
        for mode in ('module', 'legacy'):
            output = self.directory / f'{mode}.bin'
            command = (['-m', 'prim', 'asm'] if mode == 'module' else
                       [str(ROOT / 'src' / 'primasm.py')])
            result = self.run_python(*command, '-i', str(source), '-o', str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), bytes([0x20, 1, 0x20, 2, 0x0c, 0x22]))

    def test_optional_debugger_diagnostic(self):
        result = self.run_python('-m', 'prim', 'debug', '--help')
        if result.returncode:
            self.assertIn('debug extra', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
        else:
            self.assertIn('usage:', result.stdout)


if __name__ == '__main__':
    unittest.main()
