from primasm import PrimAsm

def hilo(v):
    return [(v >> 8) & 0xff, v & 0xff]

class Consts:
    HERE = 8 # here is at address 8

class Token:
    COMPILE_WORD_CALL = 0
    COMPILE_WORD_ADDRESS = 1
    COMPILE_NUMBER = 2
    COMPILE_STRING = 3

    IMMEDIATE_WORD_CALL = 4
    IMMEDIATE_WORD_ADDRESS = 5
    IMMEDIATE_NUMBER = 6
    IMMEDIATE_STRING = 7

    MNEMONIC = 8
    BUILDIN = 9
    LIT_NUMBER = 10
    LIT_STRING = 11

    DEFINITION = 12

    COMMENT_BRACES = 13
    COMMENT_BACKSLASH = 14
    WHITESPACE= 15

    D = {}
    Didx = 0

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
        for i in range(l):
            data.append(ord(s[i]) & 0xff)
        return data


class TokenDefinition(Token):
    def __init__(self, name, fragment):
        super().__init__(self.DEFINITION, fragment)
        self.name = name
        Token.addDefinition(name)

    def generate(self):
        return Token.generateStringData(self.tag, self.name)


class TokenWordCall(Token):
    def __init__(self, s, fragment, immediate):
        if immediate:
            super().__init__(self.IMMEDIATE_WORD_CALL, fragment)
            print(f"Immediate Word Call {s}")
        else:
            super().__init__(self.COMPILE_WORD_CALL, fragment)
            print(f"Compile Word Call {s}")
        self.name = s

    def generate(self):
        return [self.tag, Token.D[self.name]]


class TokenWordAddress(Token):
    def __init__(self, s, fragment, immediate):
        if immediate:
            super().__init__(self.IMMEDIATE_WORD_ADDRESS, fragment)
            print(f"Immediate word address {s}")
        else:
            super().__init__(self.COMPILE_WORD_ADDRESS, fragment)
            print(f"Compile word address {s}")
        self.name = s

    def generate(self):
        addr = Token.D[self.name]
        data = [self.tag]
        data.extend(hilo(addr))
        return data


class TokenNumber(Token):
    def __init__(self, num, fragment, immediate):
        if immediate:
            super().__init__(self.COMPILE_NUMBER, fragment)
        else:
            super().__init__(self.IMMEDIATE_NUMBER, fragment)
        self.value = num
        print(f"Compile Number {num}")

    def generate(self):
        data = [self.tag]
        data.extend(hilo(self.value))
        return data


class TokenString(Token):
    def __init__(self, s, fragment, immediate):
        if immediate:
            super().__init__(self.IMMEDIATE_STRING, fragment)
            print(f"Immediate String {s}")
        else:
            super().__init__(self.COMPILE_STRING, fragment)
            print(f"Compile String {s}")
        self.s = s

    def generate(self):
        return Token.generateStringData(self.tag, self.s)


class TokenMnemonic(Token):
    def __init__(self, s, fragment):
        super().__init__(self.MNEMONIC, fragment)
        self.mnemonic = s
        print(f"Mnemonic {s}")

    def generate(self):
        data = [self.tag]
        data.extend(PrimAsm.assemble(self.mnemonic))
        return data


class TokenBuildin(Token):
    def __init__(self, s, fragment):
        super().__init__(self.BUILDIN, fragment)
        self.name = s
        print(f"Buildin {s}")

    def generate(self):
        data = [self.tag]
        if self.name == ";":
            data.extend(PrimAsm.assemble("NOP.RET"))
        elif self.name == ",":
            data.extend(PrimAsm.assemble(f"{Consts.HERE} @ ! {Consts.HERE} @ 1 + {Consts.HERE} !"))
        elif self.name == "H":
            data.extend(PrimAsm.assemble(f"{Consts.HERE}"))
        else:
            data.extend(PrimAsm.assemble(self.name))
        return data


class TokenLiteralNumber(Token):
    def __init__(self, num, fragment):
        super().__init__(self.LIT_NUMBER, fragment)
        self.value = num
        print(f"literal number: {self.value}")

    def generate(self):
        data = [self.tag]
        data.extend(hilo(self.value))
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
