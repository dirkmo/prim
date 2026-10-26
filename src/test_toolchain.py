"""Focused regressions for the TokenForth Python tools (requires toml)."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import toml
import tokenforth as tf
from tokenizer import Fragment, fragment, merge_string_fragments, tokenizeFragments
from tokens import Token
from prim import Prim
from primconsts import Consts, PrimOpcodes as Op
from test import Mif as TestMemory

SRC = Path(__file__).resolve().parent


class ToolchainChecks(unittest.TestCase):
    def setUp(self):
        for owner, names in ((Token, ('D', 'Didx', 'mode')), (tf.Dictionary, ('D', 'S', 'N'))):
            for name in names:
                old = getattr(owner, name)
                self.addCleanup(setattr, owner, name, old)
                setattr(owner, name, {} if name == 'D' and owner is Token else
                        0 if name in ('Didx', 'mode') else [])
        self.memory = tf.Mif()
        with contextlib.redirect_stdout(io.StringIO()):
            tf.init(self.memory)
        self.cpu = Prim(self.memory)

    def test_test_memory_byte_write_preserves_neighbour(self):
        memory = TestMemory()
        memory.write16(100, 0xbbaa)
        memory.write8(100, 0x1cc)
        self.assertEqual(memory.read16(100), 0xbbcc)
        memory.write8(0xffff, 0x55)
        self.assertEqual(memory.read8(0xffff), 0x55)

    def test_compiled_string_uses_utf8_byte_count(self):
        for text in ('', 'ASCII', 'ä🙂', 'ä' * 127 + 'x'):
            with self.subTest(text=text[:10]):
                start = tf.HERE_FETCH(self.memory)
                raw = text.encode('utf-8')
                tf.compile_string(self.memory, text)
                end = tf.HERE_FETCH(self.memory)
                tf.comma(self.memory, [Op.BREAK])
                self.cpu._pc = start
                for _ in range(10):
                    if self.cpu.step() == Op.BREAK:
                        break
                else:
                    self.fail('Compiled string did not jump over its payload')
                self.assertEqual(self.cpu.T(), start + 7)
                self.assertEqual(self.cpu._pc, end + 1)
                self.assertEqual(bytes(self.memory._mem[start+7:end]), bytes([len(raw)]) + raw)

    def test_string_length_overflow_is_rejected_before_writing(self):
        for text in ('x' * 256, 'ä' * 128):
            with self.subTest(text=text[:2]):
                before = bytes(self.memory._mem)
                literals = tf.Dictionary.S.copy()
                with self.assertRaisesRegex(ValueError, '255'):
                    tf.compile_string(self.memory, text)
                self.assertEqual(bytes(self.memory._mem), before)
                self.assertEqual(tf.Dictionary.S, literals)

    def test_token_string_lengths_are_not_truncated(self):
        for tag in (Token.STRING, Token.LIT_STRING, Token.DEFINITION,
                    Token.COMMENT_BRACES, Token.WHITESPACE):
            with self.subTest(tag=tag):
                raw = ('ä' * 127 + 'x').encode()
                self.assertEqual(Token.generateStringData(tag, 'ä' * 127 + 'x'),
                                 [tag, 255, *raw])
                with self.assertRaisesRegex(ValueError, '255'):
                    Token.generateStringData(tag, 'ä' * 128)

    def test_raw_string_payload_and_following_token(self):
        for text in ('', 'ABC', 'ä🙂', 'Hello World'):
            with self.subTest(text=text):
                start = tf.HERE_FETCH(self.memory)
                raw = text.encode()
                tf.interpret([Token.LIT_STRING, len(raw), *raw, Token.NUMBER, 42, 0], self.cpu)
                end = tf.HERE_FETCH(self.memory)
                self.assertEqual(bytes(self.memory._mem[start:end]),
                                 bytes([len(raw)]) + raw + bytes([Op.PUSH8, 42]))
                self.assertIn(start, tf.Dictionary.S)

    def test_raw_and_empty_string_tokenization(self):
        for source, tag, raw in (('#"Hello World"', Token.LIT_STRING, b'Hello World'),
                                 ('#""', Token.LIT_STRING, b''),
                                 ('""', Token.STRING, b'')):
            with self.subTest(source=source):
                fragments = [Fragment(item, 1) for item in merge_string_fragments(fragment(source))]
                tokens = tokenizeFragments(fragments)
                self.assertEqual([value for token in tokens for value in token.generate()],
                                 [tag, len(raw), *raw])

    def test_immediate_input_is_reusable(self):
        opcodes = [Op.PUSH8, 7]
        for _ in range(2):
            tf.execute(self.cpu, opcodes, max_steps=10)
            self.assertEqual(opcodes, [Op.PUSH8, 7])
        self.assertEqual((self.cpu.T(), self.cpu.N()), (7, 7))
        tf.execute(self.cpu, (Op.NOP,), max_steps=2)

    def test_immediate_loop_limit(self):
        program = [Op.PUSH, Consts.AREA & 255, Consts.AREA >> 8, Op.JP]
        with self.assertRaisesRegex(RuntimeError, r'10.*0x[0-9a-fA-F]{4}'):
            tf.execute(self.cpu, program, max_steps=10)
        self.assertEqual(program[-1], Op.JP)

    def test_immediate_limits_validate_before_modifying_memory(self):
        before = bytes(self.memory._mem)
        with self.assertRaises(ValueError):
            tf.execute(self.cpu, [Op.NOP], max_steps=0)
        with self.assertRaises(ValueError):
            tf.execute(self.cpu, [Op.NOP] * 239)
        self.assertEqual(bytes(self.memory._mem), before)

    def test_interpreter_propagates_immediate_limit(self):
        self.memory.write16(Consts.DICT-4, 0x100)
        self.memory._mem[0x100:0x104] = bytes([Op.PUSH, 0, 1, Op.JP])
        with self.assertRaisesRegex(RuntimeError, '12'):
            tf.interpret([Token.MODE, Token.MODE_IMMEDIATE, Token.WORD_CALL, 2, 0],
                         self.cpu, max_immediate_steps=12)


class CommandLineChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prim-python-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / 'input.cf'
        self.source.write_text('nop\n')
        self.output = self.directory / 'output.toml'

    def tokenize(self, *arguments):
        return subprocess.run([sys.executable, str(SRC / 'tokenizer.py'), '-i', str(self.source),
                               '-o', str(self.output), *arguments],
                              capture_output=True, text=True, timeout=10)

    def test_no_library_is_valid(self):
        result = self.tokenize()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(toml.load(self.output)['symbols'], ['H', 'LATEST'])

    def test_explicit_library_errors_do_not_fall_back(self):
        library = self.directory / 'library.toml'
        for contents in (None, 'broken = [', 'type = "tokenizer"\n',
                         'type = "tokenforth"\nsymbols = 123\n'):
            with self.subTest(contents=contents):
                if contents is not None:
                    library.write_text(contents)
                result = self.tokenize('-it', str(library))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(str(library), result.stderr)
                self.assertFalse(self.output.exists())

    def test_valid_library_is_carried_over(self):
        library = self.directory / 'library.toml'
        state = dict(type='tokenforth', symbols=['H', 'LATEST'], memory=[0]*65536,
                     **{'string-literals': [], 'num-literals': []})
        library.write_text(toml.dumps(state))
        result = self.tokenize('-it', str(library))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(toml.load(self.output)['memory'], state['memory'])

    def test_missing_source_has_filename_and_no_output(self):
        self.source = self.directory / 'missing.cf'
        result = self.tokenize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.source), result.stderr)
        self.assertFalse(self.output.exists())

    def test_oversize_string_has_source_line(self):
        self.source.write_text('nop\n"' + 'ä' * 128 + '"\n')
        result = self.tokenize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f'{self.source}:2', result.stderr)
        self.assertIn('255', result.stderr)
        self.assertFalse(self.output.exists())

    def test_cli_immediate_budget_failure(self):
        library = self.directory / 'loop.tok.toml'
        memory = [0]*65536
        memory[Consts.DICT-4:Consts.DICT-2] = [0, 1]
        memory[0x100:0x104] = [Op.PUSH, 0, 1, Op.JP]
        state = dict(type='tokenizer', symbols=['H', 'LATEST', 'spin'], memory=memory,
                     tokens=[Token.MODE, Token.MODE_IMMEDIATE, Token.WORD_CALL, 2, 0],
                     **{'string-literals': [], 'num-literals': []})
        library.write_text(toml.dumps(state))
        result = subprocess.run([sys.executable, str(SRC / 'tokenforth.py'), '-i', str(library),
                                 '-o', str(self.output), '--max-immediate-steps', '12'],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(library), result.stderr)
        self.assertIn('12', result.stderr)
        self.assertIn('0x', result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
