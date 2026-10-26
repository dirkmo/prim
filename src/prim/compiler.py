#! /usr/bin/env python3

import argparse
from datetime import datetime
import sys
from .cpu import Prim, MemoryIf
from .assembler import PrimAsm
from .isa import *
from .tokens import Token, BuildIn, encode_counted_string
import toml
from . import tomlfix
from .errors import CompileError

DEFAULT_MAX_IMMEDIATE_STEPS = 100_000

class Mif(MemoryIf):
    def __init__(self, init=None):
        self._mem = bytearray(0x10000)
        self.dictionary = Dictionary()
        if init is not None:
            self.init(init)

    def init(self, mem):
        l = len(mem)
        self._mem[0:l] = mem

    def read8(self, addr):
        addr &= 0xffff
        return self._mem[addr]

    def read16(self, addr):
        return self.read8(addr) | (self.read8(addr+1) << 8)

    def write8(self, addr, value):
        addr &= 0xffff
        value &= 0xff
        if addr == 0xffff:
            print(f"uart-tx: {chr(value)} (0x{value:02x})")
        else:
            self._mem[addr] = int(value)

    def write16(self, addr, value):
        self.write8(addr, value & 0xff)
        self.write8(addr+1, (value >> 8) & 0xff)


class Dictionary:
    def __init__(self, symbols=(), string_literals=(), number_literals=()):
        self.D, self.S, self.N = [], list(string_literals), list(number_literals)
        for name in symbols:
            self.addNameDefinition(name)
        for addresses in (self.S, self.N):
            if any(type(addr) is not int or not 0 <= addr <= 65535 for addr in addresses):
                raise CompileError('Literal addresses must be integers in 0..65535')

    def addNameDefinition(self, name):
        if not isinstance(name, str) or not name:
            raise CompileError('Definition name must not be empty')
        if name in self.D:
            raise CompileError(f'Duplicate definition {name!r}')
        if len(self.D) < 2 and name != ('H', 'LATEST')[len(self.D)]:
            raise CompileError('The first definitions must be H and LATEST')
        self.D.append(name)

    def addStringLiteral(self, addr):
        self.S.append(addr)

    def addNumberLiteral(self, addr):
        self.N.append(addr)


def init(mif):
    if not mif.dictionary.D:
        mif.dictionary = Dictionary(("H", "LATEST"))
    # The word dictionary starts at address Consts.DICT and grows to lower addresses
    # Index 0: HERE pointer
    mif.write16(Consts.HERE, Consts.HERE+2)
    mif.write16(Consts.DICT, Consts.HERE)
    mif.dictionary.addNumberLiteral(Consts.HERE)
    # Index 1: LATEST pointer, which points behind the last dict entry
    comma16(mif, Consts.DICT-2)
    appendToIndex(mif, HERE_FETCH(mif)-2)
    mif.dictionary.addNumberLiteral(Consts.LATEST)

def fetchFromIndex(mif, idx):
    if not 0 <= idx < len(mif.dictionary.D):
        raise CompileError(f'Unknown symbol index {idx}')
    return mif.read16(Consts.DICT-idx*2)

def HERE_FETCH(mif):
    return mif.read16(Consts.HERE)

def HERE_STORE(mif, val):
    mif.write16(Consts.HERE, val)

def appendToIndex(mif, addr):
    latest = mif.read16(Consts.LATEST)
    idx = (Consts.DICT - latest) // 2
    print(f"append: idx {idx}: addr 0x{addr:04x}")
    mif.write16(latest, addr)
    mif.write16(Consts.LATEST, latest - 2)

def comma(mif, values):
    here = HERE_FETCH(mif)
    if hasattr(values, '__iter__'):
        for v in values:
            mif.write8(here, v)
            here += 1
    else:
        mif.write8(here, values)
        here += 1
    HERE_STORE(mif, here)

def comma16(mif, values):
    here = HERE_FETCH(mif)
    mif.write16(here, values)
    here += 2
    HERE_STORE(mif, here)

def getPushOps(num, shrink=True):
    if shrink and (num < 0x100):
        ops = [PrimOpcodes.PUSH8, num & 0xff]
    else:
        ops = [PrimOpcodes.PUSH, num & 0xff, (num >> 8) & 0xff]
    return ops


def execute(cpu, opcodes, max_steps=DEFAULT_MAX_IMMEDIATE_STEPS):
    if max_steps < 1:
        raise ValueError('Immediate step limit must be positive')
    program = [*opcodes, PrimOpcodes.BREAK]
    l = len(program)
    if l >= 0xf0:
        raise ValueError('Too much immediate code (maximum 238 code bytes)')
    cpu._mif._mem[Consts.AREA:Consts.AREA+l] = program
    cpu._pc = Consts.AREA
    for _ in range(max_steps):
        if cpu.step() == PrimOpcodes.BREAK:
            return
    raise RuntimeError(f'Immediate execution exceeded {max_steps} steps at PC 0x{cpu._pc:04x}')


def compile_string(mif, s):
    # this compiles: [push str-addr] [push behind_strdata] [jp] [count,chars...] behind_strdata:
    # so when this is executed, the string address is pushed on the stack and execution
    # continues "behind" the string data.
    counted = encode_counted_string(s)
    here = HERE_FETCH(mif)
    mif.dictionary.addStringLiteral(here + 7)
    ops = []
    ops.extend(getPushOps(here + 7, shrink=False)) # 3 bytes
    ops.extend(getPushOps(here + 7 + len(counted), shrink=False)) # 3 bytes
    ops.append(PrimOpcodes.JP) # 1 byte
    ops.extend(counted)
    comma(mif, ops)


def decode_tokens(tokens, filename=None):
    if not isinstance(tokens, (list, tuple, bytes, bytearray)) or any(type(t) is not int or not 0 <= t <= 255 for t in tokens):
        raise CompileError('tokens must be a sequence of bytes', filename)
    decoded = []
    idx = 0
    words = (Token.WORD_CALL, Token.WORD_ADDRESS, Token.NUMBER, Token.LIT_NUMBER, Token.LIT_ADDRESS)
    texts = (Token.STRING, Token.LIT_STRING, Token.DEFINITION,
             Token.COMMENT_BACKSLASH, Token.COMMENT_BRACES, Token.WHITESPACE)
    while idx < len(tokens):
        offset, tag = idx, tokens[idx]
        idx += 1
        if tag not in (*words, *texts, Token.MNEMONIC, Token.BUILDIN, Token.MODE):
            raise CompileError(f'Unknown token tag {tag}', filename, offset=offset)
        count = 2 if tag in words else 1
        if idx + count > len(tokens):
            raise CompileError('Truncated token payload', filename, offset=offset)
        if tag in texts:
            count = tokens[idx]
            idx += 1
            if idx + count > len(tokens):
                raise CompileError('Truncated text payload', filename, offset=offset)
            value = bytes(tokens[idx:idx+count])
            try:
                value.decode('utf-8')
            except UnicodeDecodeError as exc:
                raise CompileError(f'Invalid UTF-8: {exc}', filename, offset=offset) from exc
        elif tag in words:
            value = tokens[idx] | tokens[idx+1] << 8
        else:
            value = tokens[idx]
        idx += count
        if tag == Token.MODE and value not in (Token.MODE_COMPILE, Token.MODE_IMMEDIATE):
            raise CompileError(f'Invalid mode {value}', filename, offset=offset)
        if tag == Token.BUILDIN and value >= len(BuildIn.BUILDINS):
            raise CompileError(f'Unknown builtin index {value}', filename, offset=offset)
        decoded.append((offset, tag, value))
    return decoded


def interpret(tokens, cpu, max_immediate_steps=DEFAULT_MAX_IMMEDIATE_STEPS, filename=None):
    mode = Token.MODE_COMPILE
    mif = cpu._mif
    for offset, tag, value in decode_tokens(tokens, filename):
        try:
            if mode == Token.MODE_IMMEDIATE and tag in (Token.DEFINITION, Token.LIT_NUMBER, Token.LIT_STRING, Token.LIT_ADDRESS, Token.STRING):
                raise CompileError('Definitions, literals and strings are not allowed in immediate mode')
            if tag in (Token.WORD_CALL, Token.WORD_ADDRESS, Token.NUMBER, Token.MNEMONIC, Token.BUILDIN):
                if tag in (Token.WORD_CALL, Token.WORD_ADDRESS):
                    ops = getPushOps(fetchFromIndex(mif, value))
                    if tag == Token.WORD_CALL:
                        ops.append(PrimOpcodes.CALL)
                elif tag == Token.NUMBER:
                    ops = getPushOps(value)
                elif tag == Token.MNEMONIC:
                    ops = [value]
                else:
                    ops = PrimAsm.assemble(BuildIn.lookupByIndex(value)[1])
                if mode == Token.MODE_COMPILE:
                    comma(mif, ops)
                else:
                    execute(cpu, ops, max_steps=max_immediate_steps)
            elif tag == Token.STRING:
                compile_string(mif, value.decode('utf-8'))
            elif tag == Token.LIT_NUMBER:
                mif.dictionary.addNumberLiteral(HERE_FETCH(mif))
                comma16(mif, value)
            elif tag == Token.LIT_STRING:
                mif.dictionary.addStringLiteral(HERE_FETCH(mif))
                comma(mif, [len(value), *value])
            elif tag == Token.LIT_ADDRESS:
                address = fetchFromIndex(mif, value)
                mif.dictionary.addNumberLiteral(HERE_FETCH(mif))
                comma16(mif, address)
            elif tag == Token.DEFINITION:
                name = value.decode('utf-8')
                index = (Consts.DICT - mif.read16(Consts.LATEST)) // 2
                if not name or not 0 <= index < len(mif.dictionary.D) or mif.dictionary.D[index] != name:
                    raise CompileError(f'Definition {name!r} does not match symbol table index {index}')
                appendToIndex(mif, HERE_FETCH(mif))
            elif tag == Token.MODE:
                mode = value
        except ValueError as exc:
            raise CompileError(str(exc), filename, offset=offset) from exc
        except RuntimeError as exc:
            location = CompileError(str(exc), filename, offset=offset)
            raise RuntimeError(str(location)) from exc


def snapshot(mif):
    return {'type': 'tokenforth', 'symbols': mif.dictionary.D.copy(),
            'string-literals': mif.dictionary.S.copy(),
            'num-literals': mif.dictionary.N.copy(), 'memory': list(mif._mem)}


def compile_document(document, max_immediate_steps=DEFAULT_MAX_IMMEDIATE_STEPS, filename=None):
    """Compile one token document with independent CPU, memory and metadata."""
    try:
        if not isinstance(document, dict) or document.get('type') != 'tokenizer':
            raise CompileError('Expected a tokenizer document')
        if max_immediate_steps < 1:
            raise CompileError('Immediate step limit must be positive')
        symbols = document['symbols']
        memory = document['memory']
        if not isinstance(symbols, list):
            raise CompileError('symbols must be a list')
        if not isinstance(memory, list) or len(memory) not in (0, 65536) or any(type(b) is not int or not 0 <= b <= 255 for b in memory):
            raise CompileError('memory must be empty or contain 65536 bytes')
        dictionary = Dictionary(tomlfix.workaround(symbols), document['string-literals'], document['num-literals'])
        if dictionary.D[:2] != ['H', 'LATEST']:
            raise CompileError('symbols must start with H and LATEST')
        tokens = document['tokens']
    except (ValueError, KeyError, TypeError) as exc:
        raise CompileError(str(exc), filename) from exc
    mif = Mif(memory)
    mif.dictionary = dictionary
    if not memory:
        init(mif)
    interpret(tokens, Prim(mif), max_immediate_steps=max_immediate_steps, filename=filename)
    return snapshot(mif)


def saveData(infn, outfn, mif):
    data = snapshot(mif)
    data.update(title=f'tokenforthed {infn}', date=datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                **{'input-toml': str(infn)})
    with open(outfn, mode='wt', encoding='utf-8') as output:
        output.write(toml.dumps(data))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Prim TokenForth compiler')
    parser.add_argument("-i", help="Input TOML filename", metavar="<input file>", required=True, dest="input_filename")
    parser.add_argument("-o", help="Output TOML filename", metavar="<output filename>", required=True, dest="output_filename")
    parser.add_argument('--max-immediate-steps', type=int, default=DEFAULT_MAX_IMMEDIATE_STEPS,
                        help='Maximum CPU steps per immediate execution, including BREAK (default: 100000)')
    args = parser.parse_args(argv)
    if args.max_immediate_steps < 1:
        parser.error('--max-immediate-steps must be positive')

    try:
        inTomlData = toml.load(args.input_filename)
    except (OSError, ValueError) as exc:
        parser.error(f'{args.input_filename}: {exc}')
    try:
        data = compile_document(inTomlData, max_immediate_steps=args.max_immediate_steps,
                                filename=args.input_filename)
        data.update(title=f'tokenforthed {args.input_filename}',
                    date=datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                    **{'input-toml': args.input_filename})
        with open(args.output_filename, 'w', encoding='utf-8') as output:
            output.write(toml.dumps(data))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    sys.exit(main())
