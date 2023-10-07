import sys
from primconsts import *

class PrimAsm:
    INSTRUCTIONS = {
        "NOP": PrimOpcodes.NOP,
        "CALL": PrimOpcodes.CALL,
        "JP": PrimOpcodes.JP,
        "JZ": PrimOpcodes.JZ,
        "AND": PrimOpcodes.AND,
        "OR": PrimOpcodes.OR,
        "XOR": PrimOpcodes.XOR,
        "NOT": PrimOpcodes.NOT,
        "LSR": PrimOpcodes.LSR,
        "LSL": PrimOpcodes.LSL,
        "+": PrimOpcodes.ADD,
        "-": PrimOpcodes.SUB,
        "<": PrimOpcodes.LTS,
        "<U": PrimOpcodes.LTU,
        "SWAP": PrimOpcodes.SWAP,
        "OVER": PrimOpcodes.OVER,
        "DUP": PrimOpcodes.DUP,
        "NIP": PrimOpcodes.NIP,
        "ROT": PrimOpcodes.ROT,
        "-ROT": PrimOpcodes.NROT,
        "DROP": PrimOpcodes.DROP,
        "RDROP": PrimOpcodes.RDROP,
        "CARRY": PrimOpcodes.CARRY,
        ">R": PrimOpcodes.TO_R,
        "R>": PrimOpcodes.FROM_R,
        "INT": PrimOpcodes.INT,
        "@": PrimOpcodes.FETCH,
        "C@": PrimOpcodes.BYTE_FETCH,
        "!": PrimOpcodes.STORE,
        "C!": PrimOpcodes.BYTE_STORE,
        "SIMEND": PrimOpcodes.SIMEND
    }

    LOOKUP = None

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
            # sys.stdout.write(f"{t} ")
            t = t.upper()
            (t, retbit) = PrimAsm.modifier(t)
            if t in PrimAsm.INSTRUCTIONS:
                opcodes = [PrimAsm.INSTRUCTIONS[t]]
            else: # try to convert as a number
                try:
                    num = PrimAsm.convertToNumber(t) & 0xffff
                except:
                    raise Exception(f"ERROR: {t} is not a valid instruction or number")
                if num < 0x100:
                    opcodes = [PrimOpcodes.PUSH8]
                    opcodes.append(num)
                else:
                    opcodes = [PrimOpcodes.PUSH]
                    opcodes.extend([num & 0xff, (num >> 8) & 0xff])
            if retbit:
                opcodes[0] |= 0x80
            # print(list(map(hex, opcodes)))
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


    def createLookup():
        if PrimAsm.LOOKUP == None:
            PrimAsm.LOOKUP = ["UNDEF"] * 256
            for instr in PrimAsm.INSTRUCTIONS:
                op = PrimAsm.INSTRUCTIONS[instr]
                PrimAsm.LOOKUP[op] = instr


    def disassembleOpcode(opcode):
        PrimAsm.createLookup()
        retbit = (opcode & 0x80) != 0
        opcode &= 0x7f
        s = PrimAsm.LOOKUP[opcode]
        if retbit:
            s += ".RET"
        return s


    def disassemble(data):
        PrimAsm.createLookup()
        i = 0
        s = ""
        while i < len(data):
            s += f"${i}: "
            retbit = (data[i] >> 7) & 1
            ir = data[i] & 0x7f
            if ir == PrimOpcodes.PUSH:
                s += f"0x{data[i+1]+(data[i+2]<<8):x}"
                i += 3
            elif ir == PrimOpcodes.PUSH8:
                s += f"0x{data[i+1]:x}"
                i += 2
            else:
                s += f"{PrimAsm.LOOKUP[ir]}"
                i += 1
            if retbit:
                s += ".RET "
            else:
                s += " "
        return s[:-1]

def main():
    # PrimAsm.assembleFile("src/test.asm", "src/test.bin")
    data = PrimAsm.assemble("123 nop call 0x1234 and or +.ret # kommentar")
    print(data)
    print(repr(PrimAsm.disassemble(data)))

if __name__ == "__main__":
    main()