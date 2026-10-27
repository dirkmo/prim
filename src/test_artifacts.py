"""Schema, ownership and I/O regressions for TokenForth artifacts."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import contextlib
import io

from prim.artifacts import (TokenDocument, ProgramImage, load, load_tokens, load_program,
                            save, section_bytes, export_section)
from prim.compiler import compile_tokens, compile_document
from prim.tokenizer import tokenize_document
from prim.errors import CompileError
from prim.isa import PrimOpcodes as Op


class ArtifactChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prim-artifacts-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.symbols = ['H', 'LATEST', ',']

    def program(self, **changes):
        fields = dict(symbols=self.symbols, memory=bytes(65536))
        fields.update(changes)
        return ProgramImage(**fields)

    def test_roundtrip_both_existing_formats_and_comma_symbol(self):
        documents = (TokenDocument(symbols=self.symbols, tokens=[4, Op.NOP]),
                     self.program(string_literals=[100], number_literals=[200]))
        for document in documents:
            with self.subTest(kind=document.kind):
                path = self.directory / f'{document.kind}.toml'
                document = document.with_metadata(title='ä', date='26.10.2026',
                                                   **{'input-toml': 'input.toml', 'custom': {'labels': ['x']}})
                save(document, path)
                actual = load(path)
                self.assertIs(type(actual), type(document))
                self.assertEqual(actual, document)
                self.assertEqual(actual.symbols[-1], ',')
                mapping = actual.to_mapping()
                self.assertEqual(mapping['type'], document.kind)
                mapping['custom']['labels'].append('changed')
                self.assertEqual(actual.metadata['custom']['labels'], ['x'])

    def test_standard_toml_symbols_and_metadata(self):
        path = self.directory / 'handwritten.tok.toml'
        path.write_text('''# Legacy field names, independently of the writer.
type = 'tokenizer'
symbols = ['H', 'LATEST', ',', ',,', 'a,b', 'Grüße 🙂', '"', '\\']
memory = []
tokens = []
string-literals = []
num-literals = []
[custom]
label = 'a,b'
''', encoding='utf-8')
        document = load_tokens(path)
        self.assertEqual(document.symbols, ('H', 'LATEST', ',', ',,', 'a,b', 'Grüße 🙂', '"', '\\'))
        save(document, path)
        self.assertEqual(load_tokens(path), document)

    def test_empty_symbols_are_rejected_without_comma_repair(self):
        path = self.directory / 'empty-symbols.tok.toml'
        path.write_text("type = 'tokenizer'\nsymbols = ['H', 'LATEST', '', '']\n"
                        "memory = []\ntokens = []\nstring-literals = []\nnum-literals = []\n",
                        encoding='utf-8')
        with self.assertRaisesRegex(CompileError, 'nonempty names'):
            load_tokens(path)

    def test_inputs_and_exported_mappings_are_owned(self):
        memory, tokens, symbols, addresses = bytearray(65536), [4, Op.NOP], self.symbols.copy(), [100]
        metadata = {'custom': ['original']}
        document = TokenDocument(symbols=symbols, memory=memory, tokens=tokens,
                                 string_literals=addresses, metadata=metadata)
        memory[0] = 99; tokens[0] = 99; symbols[-1] = 'other'; addresses[0] = 200
        metadata['custom'].append('changed')
        self.assertEqual(document.memory[0], 0)
        self.assertEqual(document.tokens, bytes([4, Op.NOP]))
        self.assertEqual(document.symbols[-1], ',')
        self.assertEqual(document.string_literals, (100,))
        self.assertEqual(document.metadata['custom'], ['original'])
        mapping = document.to_mapping()
        mapping['memory'][0] = 88
        self.assertEqual(document.memory[0], 0)
        with self.assertRaises(FrozenInstanceError):
            document.memory = b''

    def test_memory_size_and_byte_validation(self):
        for length in (0, 65535, 65537):
            with self.subTest(length=length):
                with self.assertRaises(CompileError):
                    self.program(memory=bytes(length))
        for bad in ([True], [-1], [256], 'bytes'):
            with self.subTest(tokens=bad):
                with self.assertRaises(CompileError):
                    TokenDocument(symbols=self.symbols, tokens=bad)
        with self.assertRaises(CompileError):
            self.program(memory=[False] * 65536)
        self.assertEqual(TokenDocument(symbols=self.symbols, tokens=[]).memory, b'')

    def test_symbol_and_address_validation(self):
        for symbols in ([], ['LATEST', 'H'], ['H', 'LATEST', ''], ['H', 'LATEST', 'x', 'x']):
            with self.subTest(symbols=symbols):
                with self.assertRaises(CompileError):
                    self.program(symbols=symbols)
        for addresses in ([65536], [-1], [True], None):
            with self.subTest(addresses=addresses):
                with self.assertRaises(CompileError):
                    self.program(number_literals=addresses)

    def test_field_errors_include_input_filename(self):
        for field in ('symbols', 'memory', 'tokens', 'string-literals', 'num-literals'):
            with self.subTest(field=field):
                data = TokenDocument(symbols=self.symbols, tokens=[]).to_mapping()
                del data[field]
                with self.assertRaisesRegex(CompileError, 'broken.tok.toml'):
                    TokenDocument.from_mapping(data, filename='broken.tok.toml')

    def test_role_and_parse_errors_include_filename(self):
        path = self.directory / 'wrong.toml'
        save(TokenDocument(symbols=self.symbols, tokens=[]), path)
        with self.assertRaisesRegex(CompileError, str(path)):
            load_program(path)
        save(self.program(), path)
        with self.assertRaisesRegex(CompileError, str(path)):
            load_tokens(path)
        for text in ('broken = [', 'type = [1, 2]', 'type = "unknown"'):
            with self.subTest(text=text):
                path.write_text(text)
                with self.assertRaisesRegex(CompileError, str(path)):
                    load(path)

    def test_typed_compilation_and_dictionary_api_agree(self):
        document = tokenize_document(':main 1 2 + ;').with_metadata(custom='retained')
        with contextlib.redirect_stdout(io.StringIO()):
            image = compile_tokens(document)
            mapping = compile_document(document.to_mapping())
        self.assertIsInstance(image, ProgramImage)
        self.assertEqual(image.to_mapping(), mapping)
        self.assertEqual(image.metadata['custom'], 'retained')
        self.assertEqual(image.memory[14:19], bytes([Op.PUSH8, 1, Op.PUSH8, 2, Op.ADD | 0x80]))
        before = image.to_mapping()
        extension = tokenize_document(':second main ;', library=image)
        with contextlib.redirect_stdout(io.StringIO()):
            compiled = compile_tokens(extension)
        self.assertEqual(image.to_mapping(), before)
        self.assertEqual(compiled.symbols, ('H', 'LATEST', 'main', 'second'))

    def test_token_semantic_errors_keep_offsets(self):
        document = TokenDocument(symbols=self.symbols, tokens=[2, 1])
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(CompileError, r'input.tok.toml:token\[0\]'):
                compile_tokens(document, filename='input.tok.toml')

    def test_binary_sections_and_failed_export_preserve_output(self):
        document = TokenDocument(symbols=self.symbols, tokens=[4, Op.NOP], metadata={'extra': [1, 2]})
        path = self.directory / 'section.bin'
        export_section(document, 'tokens', path)
        self.assertEqual(path.read_bytes(), bytes([4, Op.NOP]))
        self.assertEqual(section_bytes(document, 'extra'), bytes([1, 2]))
        for section in ('missing', 'symbols'):
            with self.subTest(section=section):
                with self.assertRaises(CompileError):
                    export_section(document, section, path)
                self.assertEqual(path.read_bytes(), bytes([4, Op.NOP]))
        self.assertEqual(section_bytes(self.program(), 'memory'), bytes(65536))

    def test_program_does_not_accept_token_document_fields(self):
        mapping = self.program().to_mapping()
        mapping['tokens'] = []
        with self.assertRaises(CompileError):
            ProgramImage.from_mapping(mapping)
        with self.assertRaises(CompileError):
            self.program(metadata={'memory': []})
        with self.assertRaises(CompileError):
            self.program(metadata={1: 'not a TOML key'})

    def test_existing_fixture_documents_load(self):
        source = Path(__file__).resolve().parent
        paths = [source / name for name in ('base.tok.toml', 'base.tf.toml') if (source / name).exists()]
        if not paths:
            self.skipTest('No archived generated TOML fixtures present')
        for path in paths:
            with self.subTest(path=path.name):
                self.assertIsInstance(load(path), TokenDocument if '.tok.' in path.name else ProgramImage)

    def test_export_cli_uses_validated_artifacts(self):
        path, binary = self.directory / 'input.toml', self.directory / 'program.bin'
        save(self.program(), path)
        result = subprocess.run([sys.executable, '-m', 'prim', 'export', '-i', str(path),
                                 '-o', str(binary), '-s', 'memory'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(binary.read_bytes(), bytes(65536))
        path.write_text('type = "unknown"')
        result = subprocess.run([sys.executable, '-m', 'prim', 'export', '-i', str(path),
                                 '-o', str(binary), '-s', 'memory'], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(path), result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(binary.read_bytes(), bytes(65536))


if __name__ == '__main__':
    unittest.main()
