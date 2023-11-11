#!/usr/bin/env python3

import argparse
from datetime import datetime
import sys
from tokens import *
import primasm
import toml
import tomlfix

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
        if fragments[-1] == '\n':
            merge.append("".join(fragments[f:-1])) # join fragments up to (but excluding) newline
            merge.append(fragments[-1]) # append newline as separate fragment
        else:
            merge.append("".join(fragments[f:])) # join rest of line (there is no newline)
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
    s = s.upper()
    if s[-4:] == ".RET":
        s = s[0:-4]
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
            # print(f"'{t.strip()}'")
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
            elif isBuildin(t): # ";"
                newTokens = TokenBuildin(t, f)
            elif t[0] == "#":
                assert not immediate, f"ERROR on line {f.linenum}: Literal {t} not possible in immediate mode."
                if (len(t) > 3) and (t[1] == '"') and t[-1] == '"':
                    newTokens = TokenLiteralString(t[2:-1],f)
                elif (len(t) > 1) and Token.definitionAvailable(t[1:]):
                   newTokens = TokenLiteralAddress(t[1:],f)
                else:
                    try:
                        num = stringToNumber(t[1:])
                        newTokens = TokenLiteralNumber(num, f)
                    except:
                        assert False, f"ERROR on line {f.linenum}: Unknown word '{t[1:]}'"
            elif t[0] == "'" and len(t) > 2: # 'name
                assert Token.definitionAvailable(t[1:]), f"ERROR on line {f.linenum}: Definition '{t[1:]}' not found."
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
                        assert False, f"ERROR on line {f.linenum}: Unknown word '{t}'"
        else: # empty line or whitespace
            if len(t) and t != ' ': # ignore single space
                if ord(t[0]) < 33:
                    newTokens = TokenWhitespace(t, f)
        if newTokens is not None:
            tokens.append(newTokens)
    return tokens

def convert(sourcefn, symbols):
    for sym in symbols:
        Token.addDefinition(sym)

    # load colorforth source file
    try:
        with open(sourcefn,"r") as f:
            lines = f.readlines()
    except:
        print(f"ERROR: Cannot open file {sourcefn}")
        return None

    fragments = []
    for num,line in enumerate(lines):
        frags = merge_comment_fragments(fragment(line))
        frags = merge_string_fragments(frags)
        for f in frags:
            fragments.append(Fragment(f, num+1))

    tokens = tokenizeFragments(fragments)

    # print("\nTokens:")
    data = []
    for t in tokens:
        tokendata = t.generate()
        # if t.tag == Token.WHITESPACE:
        #     print(f"WS tag:{t.tag}")
        # else:
        #     print(f"'{t.fragment.s}' {Token.tagnames[t.tag]} data:{tokendata}")
        data.extend(tokendata)

    return data


def main():
    parser = argparse.ArgumentParser(description='Prim ColorForth Tokenizer')
    parser.add_argument("-i", help="Assembly input filename", action="store", metavar="<input filename>", type=str, required=True, dest="input_filename",default="")
    parser.add_argument("-it", help="Input TOML filename", action="store", metavar="<input filename>", type=str, required=False, dest="input_toml_filename",default="")
    parser.add_argument("-o", help="Output TOML filename", metavar="<output filename>", action="store", type=str, required=True, dest="output_toml_filename",default="")
    args = parser.parse_args()

    try:
        inTomlData = toml.load(args.input_toml_filename)
        symbols = tomlfix.workaround(inTomlData["symbols"])
        tomlTypeIsCorrent = ("type" in inTomlData) and (inTomlData["type"] == "tokenforth")
    except:
        symbols = ["H", "LATEST"]
        tomlTypeIsCorrent = True

    if not tomlTypeIsCorrent:
        raise Exception("Wrong TOML type (cannot use tokenizer TOML files)")

    # create token data
    tokendata = convert(args.input_filename, symbols)

    # make list from symbol dictionary
    symbols = [""] * len(Token.D)
    for key,value in Token.D.items():
        symbols[value] = key

    # carry over data if exists
    # memory
    try:
        memory = inTomlData["memory"]
    except:
        memory = []
    try:
        strlits = inTomlData["string-literals"]
    except:
        strlits = []
    try:
        numlits = inTomlData["num-literals"]
    except:
        numlits = []

    # compile data to write toml file
    tomldata = { "title": f"Tokenized {args.input_filename}",
                 "date": f"{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
                 "input-toml": f"{args.input_toml_filename}",
                 "type": "tokenizer",
                 "symbols": symbols,
                 "string-literals": strlits,
                 "num-literals": numlits,
                 "tokens": tokendata,
                 "memory": memory }

    # write to file
    with open(args.output_toml_filename, mode="wt") as f:
        f.write(toml.dumps(tomldata))

if __name__ == "__main__":
    sys.exit(main())
