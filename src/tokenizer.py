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


def merge_fragments(fragments):
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


def isMnemonic(s):
    return s.upper() in primasm.PrimAsm.INSTRUCTIONS


def isBuildin(s):
    s = s.upper()
    bi = [",", ";"]
    return s in bi


def tokenizeFragments(fragments):
    tokens = []
    immediate = False
    for f in fragments:
        t = f.s
        newTokens = []
        if len(t.strip()):
            print(f"'{t.strip()}'")
            if t == "[":
                immediate = True
            elif t == "]":
                immediate = False
            elif t[0] == ":": # add name to (virtual) dictionary ":name"
                assert immediate == False, f"ERROR on line {f.linenum+1}: Definitions not allowed in immediate mode"
                newTokens = TokenDefinition(t[1:], f, immediate)
            elif isMnemonic(t):
                #newTokens = TokenBuildin(t, f, immediate)
                pass
            elif isBuildin(t): # ";", ","
                newTokens = TokenBuildin(t, f, immediate)
            elif t[0] == "#":
                pass
            elif t[0] == '"' and len(t) > 2: # '"str"'
                newTokens = TokenLiteralString(t[1:-1], f, immediate)
            elif t[0:2] == "\ ": # "\ comment"
                newTokens = TokenCommentBackslash(t, f, immediate)
            elif t[0:2] == "( ": # "( comment )"
                newTokens = TokenCommentBraces(t, f, immediate)
            elif t[0] == "'": # "'name"
                newTokens = TokenImmediateWordAddress(t[1:], f, immediate)
            else: # "name", "123", "$1a2b"
                # compile word
                if Token.definitionAvailable(t): # "name"
                    newTokens = TokenCompileWordCall(t, f, immediate)
                else:
                    # compile literal
                    try:
                        if t[0] == '$': # "$1a2b"
                            num = int(t[1:], 16)
                        else: # "123"
                            num = int(t, 10)
                        newTokens = TokenLiteralNumber(num, f, immediate)
                    except:
                        assert False, f"ERROR on line {f.linenum+1}: Unknown word '{t[1:]}'"
        else: # empty line or whitespace
            if len(t) and t != ' ': # ignore single space
                if ord(t[0]) < 33:
                    newTokens = TokenWhitespace(t, f, immediate)
        tokens.append(newTokens)
    return tokens


def convert(fn):
    try:
        with open(fn,"r") as f:
            lines = f.readlines()
    except:
        print(f"ERROR: Cannot open file {fn}")
        return None

    fragments = []

    for num,line in enumerate(lines):
        frags = merge_fragments(fragment(line))
        for f in frags:
            fragments.append(Fragment(f, num))

    tokens = tokenizeFragments(fragments)

    data = []
    for t in tokens:
        tokendata = t.generate()
        print(f"'{t.fragment.s}' tag:{t.tag} data:{tokendata}")
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
