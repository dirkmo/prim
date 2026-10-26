from primasm import PrimAsm
from primconsts import *
from tferrors import CompileError

def encode_counted_string(s):
    raw = s.encode('utf-8')
    if len(raw) > 255:
        raise ValueError(f'Text exceeds 255 UTF-8 bytes (got {len(raw)})')
    return bytes([len(raw)]) + raw

def lohi(v):
    return [v & 0xff, (v >> 8) & 0xff]


class BuildIn:
    BUILDINS = [(";", "NOP.RET")]
    def lookupByIndex(idx):
        return BuildIn.BUILDINS[idx]
    def getIndexByName(name):
        for i,b in enumerate(BuildIn.BUILDINS):
            if b[0] == name:
                return i
        return -1


class Token:
    WORD_CALL = 0
    WORD_ADDRESS = 1
    NUMBER = 2
    STRING = 3
    MNEMONIC = 4
    BUILDIN = 5
    LIT_NUMBER = 6
    LIT_STRING = 7
    LIT_ADDRESS = 8

    DEFINITION = 9

    MODE = 10

    COMMENT_BRACES = 11
    COMMENT_BACKSLASH = 12
    WHITESPACE= 13

    MODE_COMPILE = 0
    MODE_IMMEDIATE = 1

    tagnames = ["WORD_CALL", "WORD_ADDRESS", "NUMBER", "STRING", "MNEMONIC", "BUILDIN", "LIT_NUMBER", "LIT_STRING", "LIT_ADDRESS", "DEFINITION", "MODE", "COMMENT_BRACES", "COMMENT_BACKSLASH", "WHITESPACE"]

    def __init__(self, tag, fragment):
        self.tag = tag
        self.fragment = fragment

    def generate(self):
        raise NotImplementedError

    def generateStringData(tag, s):
        return [tag, *encode_counted_string(s)]


class TokenDefinition(Token):
    def __init__(self, name, fragment):
        super().__init__(self.DEFINITION, fragment)
        self.name = name

    def generate(self):
        return Token.generateStringData(self.tag, self.name)


class TokenMode(Token):
    def __init__(self, name, fragment, mode):
        super().__init__(self.MODE, fragment)
        if mode not in (self.MODE_COMPILE, self.MODE_IMMEDIATE):
            raise CompileError(f"Invalid mode {mode}")
        self.mode = mode

    def generate(self):
        return [self.tag, self.mode]


class TokenWordCall(Token):
    def __init__(self, s, fragment, index):
        super().__init__(self.WORD_CALL, fragment)
        self.name = s
        self.index = index

    def generate(self):
        addr = self.index
        data = [self.tag]
        data.extend(lohi(addr))
        return data


class TokenWordAddress(Token):
    def __init__(self, s, fragment, index):
        super().__init__(self.WORD_ADDRESS, fragment)
        self.name = s
        self.index = index

    def generate(self):
        addr = self.index
        data = [self.tag]
        data.extend(lohi(addr))
        return data


class TokenNumber(Token):
    def __init__(self, num, fragment):
        super().__init__(self.NUMBER, fragment)
        self.value = num

    def generate(self):
        data = [self.tag]
        data.extend(lohi(self.value))
        return data


class TokenString(Token):
    def __init__(self, s, fragment):
        super().__init__(self.STRING, fragment)
        self.s = s

    def generate(self):
        return Token.generateStringData(self.tag, self.s)


class TokenMnemonic(Token):
    def __init__(self, s, fragment):
        super().__init__(self.MNEMONIC, fragment)
        self.mnemonic = s

    def generate(self):
        data = [self.tag]
        data.extend(PrimAsm.assemble(self.mnemonic))
        if len(data) != 2:
            raise CompileError(f"Mnemonic {self.mnemonic} must encode one byte")
        return data


class TokenBuildin(Token):
    def __init__(self, s, fragment):
        super().__init__(self.BUILDIN, fragment)
        self.name = s

    def generate(self):
        buildin = BuildIn.getIndexByName(self.name)
        if buildin < 0:
            raise CompileError(f"Builtin {self.name} not found")
        data = [self.tag, buildin]
        return data


class TokenLiteralNumber(Token):
    def __init__(self, num, fragment):
        super().__init__(self.LIT_NUMBER, fragment)
        self.value = num

    def generate(self):
        data = [self.tag]
        data.extend(lohi(self.value))
        return data


class TokenLiteralString(Token):
    def __init__(self, s, fragment):
        super().__init__(self.LIT_STRING, fragment)
        self.s = s

    def generate(self):
        return Token.generateStringData(self.tag, self.s)


class TokenLiteralAddress(Token):
    def __init__(self, name, fragment, index):
        super().__init__(self.LIT_ADDRESS, fragment)
        self.name = name
        self.index = index

    def generate(self):
        addr = self.index
        data = [self.tag]
        data.extend(lohi(addr))
        return data

class TokenCommentBraces(Token):
    def __init__(self, s, fragment):
        super().__init__(self.COMMENT_BRACES, fragment)
        self.comment = s

    def generate(self):
        return Token.generateStringData(self.tag, self.comment)


class TokenCommentBackslash(Token):
    def __init__(self, s, fragment):
        super().__init__(self.COMMENT_BACKSLASH, fragment)
        self.comment = s

    def generate(self):
        return Token.generateStringData(self.tag, self.comment)


class TokenWhitespace(Token):
    def __init__(self, s, fragment):
        super().__init__(self.WHITESPACE, fragment)
        self.ws = s

    def generate(self):
        return Token.generateStringData(self.tag, self.ws)
