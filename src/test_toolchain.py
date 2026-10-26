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
from tokenizer import scan, tokenizeFragments, tokenize_text, tokenize_file, convert
from tferrors import CompileError
from tokens import Token
from prim import Prim
from primconsts import Consts, PrimOpcodes as Op
from test import Mif as TestMemory

SRC = Path(__file__).resolve().parent


class ToolchainChecks(unittest.TestCase):
    def setUp(self):
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
                literals = self.memory.dictionary.S.copy()
                with self.assertRaisesRegex(ValueError, '255'):
                    tf.compile_string(self.memory, text)
                self.assertEqual(bytes(self.memory._mem), before)
                self.assertEqual(self.memory.dictionary.S, literals)

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
                self.assertIn(start, self.memory.dictionary.S)

    def test_raw_and_empty_string_tokenization(self):
        for source, tag, raw in (('#"Hello World"', Token.LIT_STRING, b'Hello World'),
                                 ('#""', Token.LIT_STRING, b''),
                                 ('""', Token.STRING, b'')):
            with self.subTest(source=source):
                fragments = scan(source)
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
        self.memory.dictionary.addNameDefinition("spin")
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


class ScannerAndContextChecks(unittest.TestCase):
    def test_comment_markers_inside_strings(self):
        result = tokenize_text('"A \\ ( B )" #"C ( D ) \\ E"')
        texts = [(tag, value) for _, tag, value in tf.decode_tokens(result.tokens)
                 if tag in (Token.STRING, Token.LIT_STRING)]
        self.assertEqual(texts, [(Token.STRING, b'A \\ ( B )'),
                                 (Token.LIT_STRING, b'C ( D ) \\ E')])

    def test_quotes_and_backslashes_inside_comments(self):
        source = '( first " \\ [ ) 1 ( second ) 2 \\ " unterminated quote [\n3'
        fragments = scan(source)
        self.assertEqual(''.join(f.s for f in fragments), source)
        tokens = tokenize_text(source).tokens
        numbers = [value for _, tag, value in tf.decode_tokens(tokens) if tag == Token.NUMBER]
        self.assertEqual(numbers, [1, 2, 3])

    def test_multiline_comment_preserves_following_location(self):
        source = '( first\n second " )\n  unknown'
        with self.assertRaisesRegex(CompileError, r'input.cf:3:3:.*unknown'):
            tokenize_text(source, filename='input.cf')

    def test_source_errors_have_locations(self):
        cases = [('missing', 'Unknown word'), ("'x", 'Unknown word'),
                 (':', 'must not be empty'), (':x ; :x ;', 'Duplicate'),
                 ('"open', 'Unterminated string'), ('#"open', 'Unterminated string'),
                 ('( open', 'Unterminated parenthesized comment'),
                 (']', 'Unexpected'), ('[ nop', 'missing ]'),
                 ('[ [ ] ]', 'Nested'), ('[ :x ]', 'Definitions'),
                 ('[ #1 ]', 'Literals'), ('[ "x" ]', 'Strings')]
        for source, message in cases:
            with self.subTest(source=source):
                with self.assertRaises(CompileError) as raised:
                    tokenize_text('\n  ' + source, filename='bad.cf')
                self.assertIn('bad.cf:2:', str(raised.exception))
                self.assertIn(message, str(raised.exception))

    def test_bad_token_streams_have_offsets(self):
        for tokens in ([255], [Token.NUMBER, 1], [Token.STRING, 3, 65],
                       [Token.MODE, 2], [Token.BUILDIN, 1], [Token.STRING, 1, 255]):
            with self.subTest(tokens=tokens):
                with self.assertRaisesRegex(CompileError, r'bad.tok.toml:token\[0\]'):
                    tf.interpret(tokens, Prim(tf.Mif()), filename='bad.tok.toml')

    def test_bad_symbol_index_has_offset(self):
        memory = tf.Mif()
        with contextlib.redirect_stdout(io.StringIO()):
            tf.init(memory)
        with self.assertRaisesRegex(CompileError, r'bad.tok.toml:token\[0\].*65535'):
            tf.interpret([Token.WORD_CALL, 255, 255], Prim(memory), filename='bad.tok.toml')

    def compile_source(self, source, library=None):
        initial_symbols = library['symbols'] if library else ['H', 'LATEST']
        result = tokenize_text(source, initial_symbols)
        document = dict(type='tokenizer', symbols=result.symbols, tokens=result.tokens,
                        memory=library['memory'] if library else [],
                        **{'string-literals': library['string-literals'] if library else [],
                           'num-literals': library['num-literals'] if library else []})
        with contextlib.redirect_stdout(io.StringIO()):
            return tf.compile_document(document)

    def test_repeated_and_interleaved_compilation_is_independent(self):
        first = self.compile_source(':same "ä" ; same')
        other = self.compile_source(':other #123')
        repeated = self.compile_source(':same "ä" ; same')
        self.assertEqual(first, repeated)
        self.assertEqual(other['symbols'], ['H', 'LATEST', 'other'])
        self.assertEqual(other['string-literals'], [])
        with self.assertRaisesRegex(CompileError, 'Unknown word'):
            tokenize_text('same')
        with self.assertRaises(CompileError):
            tokenize_text(':broken ; missing')
        self.assertEqual(self.compile_source(':same "ä" ; same'), first)

    def test_library_can_be_reused_without_mutation(self):
        import copy
        library = self.compile_source(':baseword 1 ;')
        before = copy.deepcopy(library)
        a = self.compile_source(':a baseword ;', library)
        b = self.compile_source(':b baseword ;', library)
        self.assertEqual(library, before)
        self.assertEqual(a['symbols'], ['H', 'LATEST', 'baseword', 'a'])
        self.assertEqual(b['symbols'], ['H', 'LATEST', 'baseword', 'b'])
        a['memory'][0] = 255
        self.assertEqual(library, before)
        self.assertEqual(b['memory'][0], 0)

    def test_repeated_file_conversion_has_no_symbol_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.cf'
            source.write_text(':word 42 ; word')
            symbols = ['H', 'LATEST']
            first = tokenize_file(source, symbols)
            self.assertEqual(convert(source, symbols), first.tokens)
            self.assertEqual(tokenize_file(source, symbols), first)
            self.assertEqual(symbols, ['H', 'LATEST'])


class OptimizedPythonChecks(unittest.TestCase):
    def test_source_validation_survives_python_optimization(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'bad.cf'
            output = Path(directory) / 'output.toml'
            for text in ('missing', ':x ; :x ;', '[ :x ]', '"open', ']'):
                with self.subTest(source=text):
                    source.write_text(text)
                    result = subprocess.run([sys.executable, '-O', str(SRC / 'tokenizer.py'),
                                             '-i', str(source), '-o', str(output)],
                                            capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f'{source}:1:', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertFalse(output.exists())

    def test_compiler_validation_survives_python_optimization(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'bad.tok.toml'
            output = Path(directory) / 'output.toml'
            source.write_text(toml.dumps(dict(type='tokenizer', symbols=['H', 'LATEST'],
                memory=[], tokens=[Token.NUMBER, 1],
                **{'string-literals': [], 'num-literals': []})))
            result = subprocess.run([sys.executable, '-O', str(SRC / 'tokenforth.py'),
                                     '-i', str(source), '-o', str(output)],
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f'{source}:token[0]', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
