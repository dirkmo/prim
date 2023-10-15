#!/usr/bin/env python3

import argparse
import sys
from tokens import *
import primasm

class Fragment:
    def __init__(self, _s, _linenum):
        self.s = _s
        self.linenum = _linenum


def fragment(s):
    # create list of words and whitespaces
    fragments = []
    t = ""
    space = False
    for c in s:
        o = ord(c)
        if space:
            if ord(c) < 33:
                t += c
            else:
                fragments.append(t)
                t = c
                space = False
        else:
            if ord(c) < 33:
                fragments.append(t)
                space = True
                t = c
            else:
                t += c
    fragments.append(t)
    return fragments


def merge_comment_fragments(fragments):
    ## merge comments to single fragment
    merge = []
    # \ comments
    try:
        f = fragments.index("\\")
        merge = fragments[0:f] # fragments before "\""
        merge.append("".join(fragments[f:-1])) # join fragments up to (but excluding) newline
        merge.append(fragments[-1]) # append newline as separate fragment
        fragments = merge
    except:
        pass
    # () comments
    try:
        c1 = fragments.index("(")
        c2 = fragments.index(")")
        merge = fragments[0:c1]
        comment = "".join(fragments[c1:c2+1])
        merge.append(comment)
        merge.extend(fragments[c2+1:])
        fragments = merge
    except:
        pass
    return fragments

def merge_string_fragments(fragments):
    ## merge strings like "Hello World" to single fragment
    merge = []
    nfl = [] # new fragment list
    stringfragment = False
    for i in range(len(fragments)):
        f = fragments[i]
        if (not stringfragment):
            if (len(f) > 0) and (f[0] == '"'):
                # start of string literal
                stringfragment = True
                merge = []
                merge.append(f)
            else:
                nfl.append(f)
        else:
            if (len(f) > 0) and (f[-1] == '"'):
                # end of string literal
                merge.append(f)
                nfl.append("".join(merge))
                stringfragment = False
            else:
                merge.append(f)
    assert stringfragment == False, f"ERROR: String literal {merge} missing double quote"
    return nfl


def isMnemonic(s):
    return s.upper() in primasm.PrimAsm.INSTRUCTIONS


def isBuildin(s):
    idx = BuildIn.getIndexByName(s)
    return idx >= 0


def stringToNumber(s):
    if s[0] == '$': # "$1a2b"
        return int(s[1:], 16)
    if s[0:2].lower() == "0x":
        return int(s[2:], 16)
    # "123"
    return int(s, 10)


def tokenizeFragments(fragments):
    tokens = []
    immediate = False
    for f in fragments:
        t = f.s
        newTokens = None
        if len(t.strip()):
            print(f"'{t.strip()}'")
            if t == "[":
                newTokens = TokenMode(t, f, Token.MODE_IMMEDIATE)
                immediate = True
            elif t == "]":
                newTokens = TokenMode(t, f, Token.MODE_COMPILE)
                immediate = False
            elif t[0] == ":": # add name to (virtual) dictionary ":name"
                assert not immediate, f"ERROR on line {f.linenum}: Definition {t[1:]} not possible in immediate mode."
                newTokens = TokenDefinition(t[1:], f)
            elif isMnemonic(t):
                newTokens = TokenMnemonic(t, f)
                pass
            elif isBuildin(t): # ";", ","
                newTokens = TokenBuildin(t, f)
            elif t[0] == "#":
                assert not immediate, f"ERROR on line {f.linenum}: Literal {t} not possible in immediate mode."
                if (len(t) > 3) and (t[1] == '"') and t[-1] == '"':
                    newTokens = TokenLiteralString(t[2:-1],f)
                else:
                    try:
                        num = stringToNumber(t[1:])
                        newTokens = TokenLiteralNumber(num, f)
                    except:
                        assert False, f"ERROR on line {f.linenum}: Unknown word '{t[1:]}'"
            elif t[0] == "'" and len(t) > 2: # 'name
                if Token.definitionAvailable(t[1:]):
                    newTokens = TokenWordAddress(t[1:], f)
            elif t[0] == '"' and len(t) > 2 and t[-1] == '"': # '"str"'
                assert not immediate, f"ERROR on line {f.linenum}: String {t} not possible in immediate mode."
                newTokens = TokenString(t[1:-1], f)
            elif t[0:2] == "\ ": # "\ comment"
                newTokens = TokenCommentBackslash(t, f)
            elif t[0:2] == "( ": # "( comment )"
                newTokens = TokenCommentBraces(t, f)
            elif t[0] == "'": # "'name"
                newTokens = TokenWordAddress(t[1:], f)
            else: # "name", "123", "$1a2b"
                # compile word
                if Token.definitionAvailable(t): # "name"
                    newTokens = TokenWordCall(t, f)
                else:
                    # compile literal
                    try:
                        num = stringToNumber(t)
                        newTokens = TokenNumber(num, f)
                    except:
                        assert False, f"ERROR on line {f.linenum}: Unknown word '{t[1:]}'"
        else: # empty line or whitespace
            if len(t) and t != ' ': # ignore single space
                if ord(t[0]) < 33:
                    newTokens = TokenWhitespace(t, f)
        if newTokens is not None:
            tokens.append(newTokens)
    return tokens


def initialFragments():
    fragments = []
    # add code fragments for comma
    F_bytecomma = fragment(":c, 'H @ c! 'H @ 1 + 'H c! ;")
    F_wordcomma = fragment(":, dup c, srw c, ;")
    F_ifcomma = fragment(f":if {PrimOpcodes.PUSH} c, 'H @ $ffff , {PrimOpcodes.JZ} c, ;")
    F_elsecomma = fragment(f":else {PrimOpcodes.PUSH} c, 'H @ >r $ffff , {PrimOpcodes.JP} c, 'H @ swap ! r> ;")
    F_thencomma = fragment(":then 'H @ swap ! ;")
    F_whilecomma = fragment(f":while 'H @ {PrimOpcodes.PUSH} c, 'H @ 0xffff , {PrimOpcodes.JZ} c, ;")
    F_repeatcomma = fragment(f":repeat {PrimOpcodes.PUSH} c, swap , {PrimOpcodes.JP} c, 'H @ swap ! ;")
    F_2dupcomma = fragment(f":2dup over over ;")
    F_2dropcomma = fragment(f":2drop drop drop ;")
    F_inccomma = fragment(":1+ 1 + ;")
    F_deccomma = fragment(":1- 1 - ;")
    F_allcomma = F_bytecomma + F_wordcomma + F_ifcomma + F_elsecomma + F_thencomma
    F_allcomma += F_whilecomma + F_repeatcomma + F_2dupcomma + F_2dropcomma
    f_allcomma += F_inccomma + F_deccomma
    for f in F_allcomma:
        fragments.append(Fragment(f,0))
    return fragments


def initialTokens():
    tokens = []
    # add definition for H, needed for comma
    T_here = TokenDefinition("H", Fragment("H", 0))
    tokens.append(T_here)
    return tokens


def convert(fn):
    try:
        with open(fn,"r") as f:
            lines = f.readlines()
    except:
        print(f"ERROR: Cannot open file {fn}")
        return None

    fragments = []

    tokens = initialTokens()
    fragments.extend(initialFragments())

    for num,line in enumerate(lines):
        frags = merge_comment_fragments(fragment(line))
        frags = merge_string_fragments(frags)
        for f in frags:
            fragments.append(Fragment(f, num+1))
    tokens.extend(tokenizeFragments(fragments))

    print("\nTokens:")
    data = []
    for t in tokens:
        tokendata = t.generate()
        if t.tag == Token.WHITESPACE:
            print(f"WS tag:{t.tag}")
        else:
            print(f"'{t.fragment.s}' {Token.tagnames[t.tag]} data:{tokendata}")
        data.extend(tokendata)

    return data


def main():
    parser = argparse.ArgumentParser(description='Prim ColorForth Tokenizer')
    parser.add_argument("-i", help="Assembly input file", action="store", metavar="<input file>", type=str, required=False, dest="input_filename",default="src/test.cf")
    parser.add_argument("-o", help="Binary token output filename", metavar="<output filename>", action="store", type=str, required=False, dest="output_filename",default="src/test.tok")
    args = parser.parse_args()
    data = convert(args.input_filename)
    # write to file
    with open(args.output_filename, mode="wb") as f:
        f.write(bytes(data))
    for b in data:
        sys.stdout.write(f"{b:02x} ")
    print()

if __name__ == "__main__":
    sys.exit(main())
