from amaranth.lib import enum

class PrimOpcodes:
    # Source/Destination
    SD_ALU = 0
    SD_D0 = 1
    SD_R0 = 2
    SD_AR = 3
    SD_PC = 4
    SD_M_A = 5   # mem access, addressed by A
    SD_M_PC = 6  # mem access, addressed by PC
    # stack pointer manipulation
    SP_INC = 1
    SP_DEC = 2

    @staticmethod
    def src(v):
        assert v < 8
        return v << 12

    @staticmethod
    def dst(v):
        assert v < 8
        return v << 9

    @staticmethod
    def dsp(v):
        assert v < 4
        return v << 7

    @staticmethod
    def rsp(v):
        assert v < 4
        return v << 5

    @staticmethod
    def ret(v):
        assert v < 2
        return v << 4

    @staticmethod
    def alu(v):
        assert v < 32
        return v

    # 0 <imm:15>
    # 1 <src:3> <dst:3> <dsp:2> <rsp:2> <ret:1> <alu:5>

    @staticmethod
    def simend():
        return 0xffff

    @staticmethod
    def push(v):
        assert v < 0x8000
        return v

    @staticmethod
    def jp_d():
        return 0x8000 | PrimOpcodes.src(PrimOpcodes.SD_D0) | PrimOpcodes.dst(PrimOpcodes.SD_PC) | PrimOpcodes.dsp(PrimOpcodes.SP_DEC)

    @staticmethod
    def jp_a():
        return 0x8000 | PrimOpcodes.src(PrimOpcodes.SD_AR) | PrimOpcodes.dst(PrimOpcodes.SD_PC)

    @staticmethod
    def jp_r():
        return 0x8000 | PrimOpcodes.src(PrimOpcodes.SD_R0) | PrimOpcodes.dst(PrimOpcodes.SD_PC) | PrimOpcodes.rsp(PrimOpcodes.SP_DEC)

    @staticmethod
    def jpz_a(): # condition in d0, jump address in ar
        return 0x8000 | PrimOpcodes.src(PrimOpcodes.SD_AR) | PrimOpcodes.dst(PrimOpcodes.SD_PC) | PrimOpcodes.dsp(PrimOpcodes.SP_DEC)

    @staticmethod
    def jpz_r(): # condition in d0, jump address in r0
        return 0x8000 | PrimOpcodes.src(PrimOpcodes.SD_AR) | PrimOpcodes.dst(PrimOpcodes.SD_PC) | PrimOpcodes.dsp(PrimOpcodes.SP_DEC) | PrimOpcodes.rsp(PrimOpcodes.SP_DEC)

