#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from .tokens import *
from . import assembler as primasm
from .artifacts import TokenDocument, ProgramImage, load_program, save
from .errors import CompileError


@dataclass
class Fragment:
    s: str
    linenum: int
    column: int = 1
    filename: str = '<string>'
    kind: str = 'word'

    def error(self, message):
        return CompileError(message, self.filename, self.linenum, self.column)


class SymbolTable:
    def __init__(self, names=()):
        self.names = []
        self.indices = {}
        for name in names:
            self.add(name)

    def add(self, name):
        if not isinstance(name, str) or not name:
            raise CompileError('Definition name must not be empty')
        if name in self.indices:
            raise CompileError(f'Duplicate definition {name!r}')
        if len(self.names) >= 65536:
            raise CompileError('Too many definitions for a 16-bit symbol index')
        self.indices[name] = len(self.names)
        self.names.append(name)

    def lookup(self, name):
        try:
            return self.indices[name]
        except KeyError:
            raise CompileError(f'Unknown word {name!r}') from None


@dataclass
class TokenizedSource:
    tokens: list
    symbols: list


def scan(source, filename='<string>'):
    """Scan once; quotes inside comments and comment markers inside strings are data.

    Forth words are whitespace-delimited. Strings are single-line, with literal
    backslashes (no new escape syntax). Parenthesized comments may span lines.
    """
    fragments = []
    pos, line, column = 0, 1, 1
    while pos < len(source):
        start, start_line, start_column = pos, line, column
        kind = 'word'
        if source[pos].isspace():
            kind = 'whitespace'
            while pos < len(source) and source[pos].isspace():
                pos += 1
        elif source[pos] == '\\' and (pos+1 == len(source) or source[pos+1].isspace()):
            kind = 'line_comment'
            end = source.find('\n', pos)
            pos = len(source) if end < 0 else end
        elif source[pos] == '(' and (pos+1 == len(source) or source[pos+1].isspace() or source[pos+1] == ')'):
            kind = 'comment'
            end = source.find(')', pos+1)
            if end < 0:
                raise CompileError('Unterminated parenthesized comment', filename, line, column)
            pos = end + 1
        elif source[pos] == '"' or source.startswith('#"', pos):
            kind = 'raw_string' if source[pos] == '#' else 'string'
            opening = pos + (2 if kind == 'raw_string' else 1)
            end = source.find('"', opening)
            newline = source.find('\n', opening)
            if end < 0 or (newline >= 0 and newline < end):
                raise CompileError('Unterminated string', filename, line, column)
            pos = end + 1
        else:
            while pos < len(source) and not source[pos].isspace():
                pos += 1
        if kind in ('string', 'raw_string', 'comment') and pos < len(source) and not source[pos].isspace():
            raise CompileError('Expected whitespace after closing delimiter', filename, start_line, start_column)
        text = source[start:pos]
        fragments.append(Fragment(text, start_line, start_column, str(filename), kind))
        lines = text.count('\n')
        line += lines
        column = len(text.rsplit('\n', 1)[-1]) + 1 if lines else column + len(text)
    return fragments


def isMnemonic(s):
    s = s.upper()
    if s.endswith('.RET'):
        s = s[:-4]
    return s in primasm.PrimAsm.INSTRUCTIONS


def stringToNumber(s):
    if s.startswith('$'):
        return int(s[1:], 16)
    if s.lower().startswith('0x'):
        return int(s[2:], 16)
    return int(s, 10)


def tokenizeFragments(fragments, symbols=None):
    symbols = SymbolTable() if symbols is None else symbols
    tokens = []
    immediate = None
    for f in fragments:
        text = f.s
        try:
            if f.kind == 'whitespace' or not text.strip():
                token = TokenWhitespace(text, f) if text and text != ' ' else None
            elif f.kind == 'line_comment':
                token = TokenCommentBackslash(text, f)
            elif f.kind == 'comment':
                token = TokenCommentBraces(text, f)
            elif f.kind in ('string', 'raw_string'):
                if immediate is not None:
                    raise CompileError('Strings are not allowed in immediate mode')
                token = (TokenLiteralString(text[2:-1], f) if f.kind == 'raw_string'
                         else TokenString(text[1:-1], f))
            elif text == '[':
                if immediate is not None:
                    raise CompileError('Nested immediate mode is not allowed')
                immediate = f
                token = TokenMode(text, f, Token.MODE_IMMEDIATE)
            elif text == ']':
                if immediate is None:
                    raise CompileError('Unexpected ] without [')
                immediate = None
                token = TokenMode(text, f, Token.MODE_COMPILE)
            elif text.startswith(':'):
                if immediate is not None:
                    raise CompileError('Definitions are not allowed in immediate mode')
                symbols.add(text[1:])
                token = TokenDefinition(text[1:], f)
            elif isMnemonic(text):
                token = TokenMnemonic(text, f)
            elif BuildIn.getIndexByName(text) >= 0:
                token = TokenBuildin(text, f)
            elif text.startswith('#'):
                if immediate is not None:
                    raise CompileError('Literals are not allowed in immediate mode')
                value = text[1:]
                if value in symbols.indices:
                    token = TokenLiteralAddress(value, f, symbols.lookup(value))
                else:
                    try:
                        token = TokenLiteralNumber(stringToNumber(value), f)
                    except ValueError:
                        raise CompileError(f'Unknown literal {value!r}') from None
            elif text.startswith("'"):
                name = text[1:]
                token = TokenWordAddress(name, f, symbols.lookup(name))
            elif text in symbols.indices:
                token = TokenWordCall(text, f, symbols.lookup(text))
            else:
                try:
                    token = TokenNumber(stringToNumber(text), f)
                except ValueError:
                    raise CompileError(f'Unknown word {text!r}') from None
            if token is not None:
                tokens.append(token)
        except ValueError as exc:
            raise f.error(str(exc)) from exc
    if immediate is not None:
        raise immediate.error('Unterminated immediate mode: missing ]')
    return tokens


def tokenize_text(source, symbols=('H', 'LATEST'), filename='<string>'):
    try:
        table = SymbolTable(symbols)
    except ValueError as exc:
        raise CompileError(str(exc), filename) from exc
    tokens = tokenizeFragments(scan(source, filename), table)
    data = []
    for token in tokens:
        try:
            data.extend(token.generate())
        except ValueError as exc:
            raise token.fragment.error(str(exc)) from exc
    return TokenizedSource(data, table.names.copy())


def tokenize_file(filename, symbols=('H', 'LATEST')):
    return tokenize_text(Path(filename).read_text(encoding='utf-8'), symbols, str(filename))


def convert(sourcefn, symbols):
    """Compatibility helper returning token bytes; no shared symbol state."""
    return tokenize_file(sourcefn, symbols).tokens


def load_library(filename):
    """Compatibility mapping API; file validation lives in artifacts."""
    if filename is None:
        return {'symbols': ['H', 'LATEST'], 'memory': [],
                'string-literals': [], 'num-literals': []}
    return load_program(filename).to_mapping()


def tokenize_document(source, library=None, filename='<string>'):
    """Tokenize against an optional compiled library without sharing its buffers."""
    if library is not None:
        library = ProgramImage.from_mapping(library)
    result = tokenize_text(source, library.symbols if library else ('H', 'LATEST'), filename)
    return TokenDocument(tokens=result.tokens, symbols=result.symbols,
                         memory=library.memory if library else b'',
                         string_literals=library.string_literals if library else (),
                         number_literals=library.number_literals if library else ())


def main(argv=None):
    parser = argparse.ArgumentParser(description='Prim ColorForth Tokenizer')
    parser.add_argument("-i", help="Assembly input filename", action="store", metavar="<input filename>", type=str, required=True, dest="input_filename",default="")
    parser.add_argument("-it", help="Input TOML filename", action="store", metavar="<input filename>", type=str, required=False, dest="input_toml_filename",default=None)
    parser.add_argument("-o", help="Output TOML filename", metavar="<output filename>", action="store", type=str, required=True, dest="output_toml_filename",default="")
    args = parser.parse_args(argv)

    try:
        library = load_program(args.input_toml_filename) if args.input_toml_filename is not None else None
        document = tokenize_document(Path(args.input_filename).read_text(encoding='utf-8'),
                                     library=library, filename=args.input_filename)
        document = document.with_metadata(title=f'Tokenized {args.input_filename}',
            date=datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            **{'input-toml': args.input_toml_filename or ''})
        save(document, args.output_toml_filename)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

if __name__ == "__main__":
    sys.exit(main())
