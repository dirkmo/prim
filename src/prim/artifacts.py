"""Owned TokenForth documents and the single TOML/binary I/O boundary."""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import ClassVar

import toml
from .errors import CompileError
from . import tomlfix

_RESERVED = {'type', 'symbols', 'memory', 'tokens', 'string-literals', 'num-literals'}


def _bytes(value, name):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, (list, tuple)) or any(type(item) is not int or not 0 <= item <= 255 for item in value):
        raise CompileError(f'{name} must be a sequence of bytes in 0..255')
    return bytes(value)


def _addresses(value, name):
    if not isinstance(value, (list, tuple)) or any(type(item) is not int or not 0 <= item <= 65535 for item in value):
        raise CompileError(f'{name} must be a sequence of addresses in 0..65535')
    return tuple(value)


def _symbols(value):
    if not isinstance(value, (list, tuple)) or any(not isinstance(name, str) or not name for name in value):
        raise CompileError('symbols must be a sequence of nonempty names')
    if tuple(value[:2]) != ('H', 'LATEST'):
        raise CompileError('symbols must start with H and LATEST')
    if len(set(value)) != len(value):
        raise CompileError('symbols must not contain duplicate definitions')
    if len(value) > 65536:
        raise CompileError('Too many definitions for a 16-bit symbol index')
    return tuple(value)


@dataclass(frozen=True, kw_only=True)
class _Document:
    symbols: tuple[str, ...]
    memory: bytes = b''
    string_literals: tuple[int, ...] = ()
    number_literals: tuple[int, ...] = ()
    metadata: dict = field(default_factory=dict)
    kind: ClassVar[str]

    def __post_init__(self):
        object.__setattr__(self, 'symbols', _symbols(self.symbols))
        object.__setattr__(self, 'memory', _bytes(self.memory, 'memory'))
        object.__setattr__(self, 'string_literals', _addresses(self.string_literals, 'string-literals'))
        object.__setattr__(self, 'number_literals', _addresses(self.number_literals, 'num-literals'))
        if (not isinstance(self.metadata, Mapping) or
                any(not isinstance(name, str) for name in self.metadata) or
                _RESERVED.intersection(self.metadata)):
            raise CompileError('metadata must be a mapping without reserved document fields')
        object.__setattr__(self, 'metadata', deepcopy(dict(self.metadata)))
        if len(self.memory) not in ((0, 65536) if self.kind == 'tokenizer' else (65536,)):
            raise CompileError('memory must be empty or contain 65536 bytes' if self.kind == 'tokenizer'
                               else 'Program memory must contain exactly 65536 bytes')

    @classmethod
    def from_mapping(cls, value, filename=None):
        if isinstance(value, cls):
            return value
        try:
            if not isinstance(value, Mapping) or value.get('type') != cls.kind:
                raise CompileError(f'Expected a {cls.kind} document')
            fields = dict(symbols=value['symbols'], memory=value['memory'],
                          string_literals=value['string-literals'], number_literals=value['num-literals'],
                          metadata={name: item for name, item in value.items() if name not in _RESERVED})
            if cls.kind == 'tokenizer':
                fields['tokens'] = value['tokens']
            elif 'tokens' in value:
                raise CompileError('A compiled program must not contain a tokens section')
            return cls(**fields)
        except (ValueError, KeyError, TypeError) as exc:
            raise CompileError(str(exc), filename) from exc

    def to_mapping(self):
        result = deepcopy(self.metadata)
        result.update(type=self.kind, symbols=list(self.symbols), memory=list(self.memory),
                      **{'string-literals': list(self.string_literals), 'num-literals': list(self.number_literals)})
        if self.kind == 'tokenizer':
            result['tokens'] = list(self.tokens)
        return result

    def with_metadata(self, **metadata):
        return replace(self, metadata={**self.metadata, **metadata})


@dataclass(frozen=True, kw_only=True)
class TokenDocument(_Document):
    tokens: bytes
    kind: ClassVar[str] = 'tokenizer'

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'tokens', _bytes(self.tokens, 'tokens'))


@dataclass(frozen=True, kw_only=True)
class ProgramImage(_Document):
    kind: ClassVar[str] = 'tokenforth'


def load(filename, expected=None):
    """Load and validate either existing TOML format; retain unknown metadata."""
    try:
        with open(filename, encoding='utf-8') as source:
            data = toml.load(source)
        kind = data.get('type')
        if kind not in ('tokenizer', 'tokenforth'):
            raise CompileError(f'Unknown document type {kind!r}')
        document_type = TokenDocument if kind == 'tokenizer' else ProgramImage
        if expected is not None and document_type is not expected:
            raise CompileError(f'Expected a {expected.kind} document')
        # Compatibility with the existing TOML reader; remove with its replacement.
        if isinstance(data.get('symbols'), list):
            data['symbols'] = tomlfix.workaround(data['symbols'])
    except (OSError, ValueError, TypeError) as exc:
        raise CompileError(str(exc), filename) from exc
    return document_type.from_mapping(data, filename=filename)


def load_tokens(filename):
    return load(filename, TokenDocument)


def load_program(filename):
    return load(filename, ProgramImage)


def save(document, filename):
    if not isinstance(document, (TokenDocument, ProgramImage)):
        raise CompileError('save expects a TokenDocument or ProgramImage', filename)
    try:
        # Serialize before opening the output, so encoding errors cannot truncate it.
        text = toml.dumps(document.to_mapping())
        Path(filename).write_text(text, encoding='utf-8')
    except (OSError, ValueError, TypeError) as exc:
        raise CompileError(str(exc), filename) from exc


def section_bytes(document, section):
    if section == 'memory':
        return document.memory
    if section == 'tokens' and isinstance(document, TokenDocument):
        return document.tokens
    data = document.to_mapping()
    if section not in data:
        raise CompileError(f'Section {section!r} not found in {document.kind} document')
    return _bytes(data[section], section)


def export_section(document, section, filename):
    data = section_bytes(document, section)
    try:
        Path(filename).write_bytes(data)
    except OSError as exc:
        raise CompileError(str(exc), filename) from exc
