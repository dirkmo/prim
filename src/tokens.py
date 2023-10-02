from primasm import PrimAsm

def hilo(v):
    return [(v >> 8) & 0xff, v & 0xff]

class Consts:
    HERE = 8 # here is at address 8

class Token:
    DEFINITION = 0

    LIT_NUMBER = 1
    LIT_STRING = 2

    COMPILE_WORD_CALL = 3
    COMPILE_WORD_ADDRESS = 4
    COMPILE_NUMBER = 5
    COMPILE_STRING = 6

    IMMEDIATE_WORD_CALL = 7
    IMMEDIATE_WORD_ADDRESS = 8
    IMMEDIATE_NUMBER = 9
    IMMEDIATE_STRING = 10

    MNEMONIC = 11
    BUILDIN = 12

    COMMENT_BRACES = 13
    COMMENT_BACKSLASH = 14
    WHITESPACE= 15

    D = {}
    Didx = 0

    def __init__(self, tag, fragment, immediate):
        self.tag = tag
        self.fragment = fragment
        self.immediate = immediate

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
    def __init__(self, name, fragment, immediate):
        super().__init__(self.DEFINITION, fragment, immediate)
        self.name = name
        Token.addDefinition(name)

    def generate(self):
        return Token.generateStringData(self.tag, self.name)


class TokenLiteralNumber(Token):
    def __init__(self, num, fragment, immediate):
        super().__init__(self.LIT_NUMBER, fragment, immediate)
        self.value = num
        print(f"literal number: {self.value}")

    def generate(self):
        data = [self.tag]
        data.extend(hilo(self.value))
        return data


class TokenLiteralString(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.LIT_STRING, fragment, immediate)
        self.s = s
        print(f"Literal string '{s}'")

    def generate(self):
        return Token.generateStringData(self.tag, self.s)


class TokenCompileWordCall(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.COMPILE_WORD_CALL, fragment, immediate)
        self.name = s
        print(f"Compile Word Call {s}")

    def generate(self):
        return [self.tag, Token.D[self.name]]


class TokenCompileWordAddress(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.COMPILE_WORD_ADDRESS, fragment, immediate)
        self.name = s
        print(f"Literal word address {s}")

    def generate(self):
        addr = Token.D[self.name]
        data = [self.tag]
        data.extend(hilo(addr))
        return data


class TokenCompileNumber(Token):
    def __init__(self, num, fragment, immediate):
        super().__init__(self.COMPILE_NUMBER, fragment, immediate)
        self.value = num
        print(f"Compile Number {num}")

    def generate(self):
        data = [self.tag]
        data.extend(hilo(self.value))


class TokenCompileString(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.WHITESPACE, fragment, immediate)
        self.s = s
        print(f"Compile String {s}")

    def generate(self):
        return Token.generateStringData(self.tag, self.s)













class TokenImmediate(Token):
    def __init__(self, name, fragment, immediate):
        super().__init__(self.IMMEDIATE, fragment, immediate)
        self.name = name
        print(f"Immediate call: {name}")

    def generate(self):
        idx = Token.D[self.name]
        return [self.tag, idx & 0xff, (idx >> 8) & 0xff]


class TokenImmediateNumberHex(Token):
    def __init__(self, num, fragment, immediate):
        super().__init__(self.IMMEDIATE_NUMBER_HEX, fragment, immediate)
        self.value = num
        print(f"Immedate number ${num:x}")

    def generate(self):
        data = [self.tag]
        data.extend(hilo(self.value))
        return data


class TokenImmediateNumberDec(Token):
    def __init__(self, num, fragment, immediate):
        super().__init__(self.IMMEDIATE_NUMBER_DEC, fragment, immediate)
        self.value = num
        print(f"Immedate number {num}")

    def generate(self):
        data = [self.tag]
        data.extend(hilo(self.value))
        return data


class TokenCommentBraces(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.COMMENT_BRACES, fragment, immediate)
        self.comment = s
        print(f"Comment {self.comment}")

    def generate(self): # TODO
        return Token.generateStringData(self.tag, self.comment)


class TokenCommentBackslash(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.COMMENT_BACKSLASH, fragment, immediate)
        self.comment = s
        print(f"Comment {self.comment}")

    def generate(self):
        return Token.generateStringData(self.tag, self.comment)


class TokenImmediateWordAddress(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.IMMEDIATE_WORD_ADDRESS, fragment, immediate)
        self.name = s
        print(f"Push word address {s}")

    def generate(self):
        return [self.tag]


class TokenWhitespace(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.WHITESPACE, fragment, immediate)
        self.ws = s
        print(f"Whitespace")

    def generate(self):
        return Token.generateStringData(self.tag, self.ws)


class TokenBuildin(Token):
    def __init__(self, s, fragment, immediate):
        super().__init__(self.BUILDIN, fragment, immediate)
        self.name = s
        print(f"Buildin")

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
