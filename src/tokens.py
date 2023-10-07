from primasm import PrimAsm
from primconsts import *
import sys

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

    DEFINITION = 8

    MODE = 9

    COMMENT_BRACES = 10
    COMMENT_BACKSLASH = 11
    WHITESPACE= 12

    MODE_COMPILE = 0
    MODE_IMMEDIATE = 1

    D = {}
    Didx = 0
    mode = MODE_COMPILE

    tagnames = ["WORD_CALL", "WORD_ADDRESS", "NUMBER", "STRING", "MNEMONIC", "BUILDIN", "LIT_NUMBER", "LIT_STRING", "DEFINITION", "MODE", "COMMENT_BRACES", "COMMENT_BACKSLASH", "WHITESPACE"]

    def __init__(self, tag, fragment):
        self.tag = tag
        self.fragment = fragment

    def addDefinition(name):
        assert not name in Token.D, f"{name} already defined"
        print(f"Definition {Token.Didx}: {name}")
        Token.D[name] = Token.Didx
        Token.Didx += 1

    def definitionAvailable(name):
        return name in Token.D

    def generate(self):
        ...

    def generateStringData(tag, s):
        l = len(s) & 0xff
        data = [tag, l]
        data.extend(s.encode())
        return data


class TokenDefinition(Token):
    def __init__(self, name, fragment):
        super().__init__(self.DEFINITION, fragment)
        self.name = name
        Token.addDefinition(name)

    def generate(self):
        return Token.generateStringData(self.tag, self.name)


class TokenMode(Token):
    def __init__(self, name, fragment, mode):
        super().__init__(self.MODE, fragment)
        assert mode in [self.MODE_COMPILE, self.MODE_IMMEDIATE], f"Invalid mode {mode}"
        self.mode = mode
        if mode == Token.MODE_COMPILE:
            print("Compile Mode")
        else:
            print("Immediate Mode")

    def generate(self):
        return [self.tag, self.mode]


class TokenWordCall(Token):
    def __init__(self, s, fragment):
        super().__init__(self.WORD_CALL, fragment)
        if Token.mode == Token.MODE_IMMEDIATE:
            sys.stdout.write("Immediate ")
        print(f"Word Call {s}")
        self.name = s

    def generate(self):
        addr = Token.D[self.name]
        data = [self.tag]
        data.extend(lohi(addr))
        return data


class TokenWordAddress(Token):
    def __init__(self, s, fragment):
        super().__init__(self.WORD_ADDRESS, fragment)
        if Token.mode == Token.MODE_IMMEDIATE:
            sys.stdout.write("Immediate ")
        print(f"Word Address {s}")
        self.name = s

    def generate(self):
        addr = Token.D[self.name]
        data = [self.tag]
        data.extend(lohi(addr))
        return data


class TokenNumber(Token):
    def __init__(self, num, fragment):
        super().__init__(self.NUMBER, fragment)
        if Token.mode == Token.MODE_IMMEDIATE:
            sys.stdout.write("Immediate ")
        print(f"Compile Number {num}")
        self.value = num

    def generate(self):
        data = [self.tag]
        data.extend(lohi(self.value))
        return data


class TokenString(Token):
    def __init__(self, s, fragment):
        super().__init__(self.STRING, fragment)
        if Token.mode == Token.MODE_IMMEDIATE:
            sys.stdout.write("Immediate ")
        print(f"String {s}")
        self.s = s

    def generate(self):
        return Token.generateStringData(self.tag, self.s)


class TokenMnemonic(Token):
    def __init__(self, s, fragment):
        super().__init__(self.MNEMONIC, fragment)
        self.mnemonic = s
        if Token.mode == Token.MODE_IMMEDIATE:
            sys.stdout.write("Immediate ")
        print(f"Mnemonic {s}")

    def generate(self):
        data = [self.tag]
        data.extend(PrimAsm.assemble(self.mnemonic))
        return data


class TokenBuildin(Token):
    def __init__(self, s, fragment):
        super().__init__(self.BUILDIN, fragment)
        self.name = s
        if Token.mode == Token.MODE_IMMEDIATE:
            sys.stdout.write("Immediate ")
        print(f"Buildin {s}")

    def generate(self):
        buildin = BuildIn.getIndexByName(self.name)
        assert buildin >= 0, f"Buildin {self.name} not found"
        data = [self.tag, buildin]
        return data


class TokenLiteralNumber(Token):
    def __init__(self, num, fragment):
        super().__init__(self.LIT_NUMBER, fragment)
        self.value = num
        print(f"literal number: {self.value}")

    def generate(self):
        data = [self.tag]
        data.extend(lohi(self.value))
        return data


class TokenLiteralString(Token):
    def __init__(self, s, fragment):
        super().__init__(self.LIT_STRING, fragment)
        self.s = s
        print(f"Literal string '{s}'")

    def generate(self):
        return Token.generateStringData(self.tag, self.s)


class TokenCommentBraces(Token):
    def __init__(self, s, fragment):
        super().__init__(self.COMMENT_BRACES, fragment)
        self.comment = s
        print(f"Comment {self.comment}")

    def generate(self):
        return Token.generateStringData(self.tag, self.comment)


class TokenCommentBackslash(Token):
    def __init__(self, s, fragment):
        super().__init__(self.COMMENT_BACKSLASH, fragment)
        self.comment = s
        print(f"Comment {self.comment}")

    def generate(self):
        return Token.generateStringData(self.tag, self.comment)


class TokenWhitespace(Token):
    def __init__(self, s, fragment):
        super().__init__(self.WHITESPACE, fragment)
        self.ws = s
        print(f"Whitespace")

    def generate(self):
        return Token.generateStringData(self.tag, self.ws)
