import sys
from prim import Prim

class PrimAsm:
    INSTRUCTIONS = {
        "NOP": Prim.OP_NOP,
        "CALL": Prim.OP_CALL,
        "JP": Prim.OP_JP,
        "JPZ": Prim.OP_JPZ,
        "AND": Prim.OP_AND,
        "OR": Prim.OP_OR,
        "XOR": Prim.OP_XOR,
        "NOT": Prim.OP_NOT,
        "LSR": Prim.OP_LSR,
        "LSL": Prim.OP_LSL,
        "ADD": Prim.OP_ADD,
        "SUB": Prim.OP_SUB,
        "LTS": Prim.OP_LTS,
        "LTU": Prim.OP_LTU,
        "SWAP": Prim.OP_SWAP,
        "OVER": Prim.OP_OVER,
        "DUP": Prim.OP_DUP,
        "NIP": Prim.OP_NIP,
        "ROT": Prim.OP_ROT,
        "NROT": Prim.OP_NROT,
        "TO_R": Prim.OP_TO_R,
        "FROM_R": Prim.OP_FROM_R,
        "INT": Prim.OP_INT,
        "FETCH": Prim.OP_FETCH,
        "STORE": Prim.OP_STORE,
    }

    def convertToNumber(s):
        s = s.strip()
        sign = 1
        if s[0] == '+':
            s = s[1:]
        elif s[0] == '-':
            sign = -1
            s = s[1:]
        if s[0] == '$':
            num = int(s[1:],16)
        elif s[0:2].upper() == "0X":
            num = int(s[2:], 16)
        else:
            num = int(s)
        return sign*num

    def tokenize(line):
        tok = line.split(" ")
        for i,t in enumerate(tok):
            if t[0] in [";", "#"]:
                tok = tok[0:i]
                break
        return tok

    def modifier(token):
        mod = ".RET"
        idx = token.find(mod)
        if idx > 0:
            return (token[0:idx], token[idx:] == mod)
        return (token, False)

    def assemble(line):
        data = []
        tok = PrimAsm.tokenize(line)
        for t in tok:
            sys.stdout.write(f"{t} ")
            t = t.upper()
            (t, retbit) = PrimAsm.modifier(t)
            if t in PrimAsm.INSTRUCTIONS:
                opcodes = [PrimAsm.INSTRUCTIONS[t]]
            else: # try to convert as a number
                num = PrimAsm.convertToNumber(t) & 0xffff
                if num < 0x100:
                    opcodes = [Prim.OP_PUSH8]
                    opcodes.append(num)
                else:
                    opcodes = [Prim.OP_PUSH]
                    opcodes.extend([num & 0xff, (num >> 8) & 0xff])
            if retbit:
                opcodes[0] |= 0x80
            print(list(map(hex, opcodes)))
            data.extend(opcodes)
        return data

    def assembleFile(inputfn, outputfn=""):
        with open(inputfn, "rt") as f:
            lines = f.readlines()
        data = []
        for l in lines:
            data.extend(PrimAsm.assemble(l.strip()))
        if len(outputfn):
            with open(outputfn, "wb") as f:
                f.write(bytes(data))

    def disassemble(data):
        lookup = [""] * 256
        for instr in PrimAsm.INSTRUCTIONS:
            opcode = PrimAsm.INSTRUCTIONS[instr]
            lookup[opcode] = instr
        i = 0
        s = ""
        while i < len(data):
            retbit = (data[i] >> 7) & 1
            data[i] &= 0x7f
            if data[i] == Prim.OP_PUSH:
                s += f"0x{data[i+1]+(data[i+2]<<8):x}"
                i += 3
            elif data[i] == Prim.OP_PUSH8:
                s += f"0x{data[i+1]:x}"
                i += 2
            else:
                s += f"{lookup[data[i]]}"
                i += 1
            if retbit:
                s += ".RET "
            else:
                s += " "
        return s[:-1]

def main():
    # PrimAsm.assembleFile("src/test.asm", "src/test.bin")
    data = PrimAsm.assemble("123 0x1234 and or add.ret # kommentar")
    print(repr(PrimAsm.disassemble(data)))

if __name__ == "__main__":
    main()