"""Generated opcode words must emit the ISA bytes when actually executed."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prim.assembler import PrimAsm
from prim.compiler import compile_tokens, execute, Mif
from prim.cpu import Prim
from prim.isa import Consts, PrimOpcodes as Op, export_opcodes, export_tokenforth_opcodes
from prim.tokenizer import tokenize_document

SRC = Path(__file__).resolve().parent


class OpcodeWordChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory(prefix='prim-opcodes-') as directory:
            source = Path(directory) / 'opcodes.cf'
            export_tokenforth_opcodes(source)
            cls.generated = source.read_text(encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap = compile_tokens(tokenize_document((SRC / 'bootstrap.cf').read_text()))
            cls.opcodes = compile_tokens(tokenize_document(cls.generated, bootstrap))
            cls.base = compile_tokens(tokenize_document((SRC / 'base.cf').read_text(), cls.opcodes))

    def compile(self, source, library=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return compile_tokens(tokenize_document(source, library or self.base))

    def test_each_opcode_word_emits_exactly_one_byte(self):
        names = {word.lower() + ',': value for word, value in PrimAsm.INSTRUCTIONS.items()}
        self.assertEqual(set(self.opcodes.symbols) - {'H', 'LATEST', 'c,', ','}, set(names))
        self.assertEqual(len(names), len([name for name in vars(Op) if not name.startswith('_')]))
        here = int.from_bytes(self.opcodes.memory[Consts.HERE:Consts.HERE+2], 'little')
        for name, expected in names.items():
            with self.subTest(word=name):
                image = self.compile(f'[ {name} ]', self.opcodes)
                self.assertEqual(image.memory[here], expected)
                self.assertEqual(int.from_bytes(image.memory[Consts.HERE:Consts.HERE+2], 'little'), here + 1)
        for name in ('+,', '-,', '>r,', 'r>,', '@,', '!,', 'c@,', 'c!,', 'push,', 'break,', 'simend,'):
            self.assertIn(name, self.opcodes.symbols)

    def test_composite_emitters_keep_their_byte_sequences(self):
        here = int.from_bytes(self.base.memory[Consts.HERE:Consts.HERE+2], 'little')
        expected = bytes([Op.SWAP, Op.TO_R, Op.TO_R, Op.FROM_R, Op.FROM_R,
                          Op.SWAP, Op.SUB, Op.NOT, Op.OVER, Op.OVER])
        image = self.compile('[ 2>r, 2r>, =, 2dup, ]')
        self.assertEqual(image.memory[here:here+len(expected)], expected)
        self.assertEqual(int.from_bytes(image.memory[Consts.HERE:Consts.HERE+2], 'little'), here+len(expected))

    def test_boot_installs_entry_preserves_here_and_runs(self):
        source = ':main 41 1 + ;'
        before = self.compile(source)
        image = self.compile(source + " [ 'main boot! ]")
        cell = Consts.DICT - 2 * image.symbols.index('main')
        entry = image.memory[cell:cell+2]
        self.assertEqual(image.memory[:5], bytes([Op.PUSH, *entry, Op.CALL, Op.BREAK]))
        self.assertEqual(image.memory[Consts.HERE:Consts.LATEST+2], before.memory[Consts.HERE:Consts.LATEST+2])
        cpu = Prim(Mif(image.memory))
        for _ in range(100):
            if cpu.step() == Op.BREAK:
                break
        else:
            self.fail('Program did not halt')
        self.assertEqual(cpu.T(), 42)
        # Check the compile-time stacks too, which ProgramImage does not store.
        cell = Consts.DICT - 2 * before.symbols.index('boot!')
        boot = before.memory[cell:cell+2]
        cpu = Prim(Mif(before.memory))
        execute(cpu, [Op.PUSH, *entry, Op.PUSH, *boot, Op.CALL])
        self.assertEqual((cpu._dsp, cpu._rsp), (0, 0))

    def test_cli_exports_and_verilog_default(self):
        with tempfile.TemporaryDirectory(prefix='prim-opcode-cli-') as directory:
            directory = Path(directory)
            for arguments, output in (([], 'opcodes.v'),
                                      (['--format', 'tokenforth'], 'opcodes.cf'),
                                      (['--format', 'tokenforth', 'custom.cf'], 'custom.cf')):
                with self.subTest(arguments=arguments):
                    result = subprocess.run([sys.executable, '-m', 'prim', 'opcodes', *arguments],
                                            cwd=directory, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if output.endswith('.cf'):
                        self.assertEqual((directory / output).read_text(), self.generated)
            expected = directory / 'expected.v'
            export_opcodes(expected)
            self.assertEqual((directory / 'opcodes.v').read_bytes(), expected.read_bytes())


if __name__ == '__main__':
    unittest.main()
