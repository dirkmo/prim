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

def src(v):
    assert v < 8
    return v << 12

def dst(v):
    assert v < 8
    return v << 9

def dsp(v):
    assert v < 4
    return v << 7

def rsp(v):
    assert v < 4
    return v << 5

def ret(v):
    assert v < 2
    return v << 4

def alu(v):
    assert v < 32
    return v

# 0 <imm:15>
# 1 <src:3> <dst:3> <dsp:2> <rsp:2> <ret:1> <alu:5>

def simend():
    return 0xffff

def push(v):
    assert v < 0x8000
    return v

def drop():
    return 0x8000 | dsp(SP_DEC)

def dup():
    return 0x8000 | dsp(SP_INC) | src(SD_D0) | dst(SD_D0)

def to_a():
    return 0x8000 | src(SD_D0) | dst(SD_AR) | dsp(SP_DEC)

def to_r():
    return 0x8000 | src(SD_D0) | dst(SD_R0) | dsp(SP_DEC) | rsp(SP_INC)

def r_from():
    return 0x8000 | src(SD_R0) | dst(SD_D0) | dsp(SP_INC) | rsp(SP_DEC)

def r_to_a():
    return 0x8000 | src(SD_R0) | dst(SD_AR) | rsp(SP_DEC)

def a_to_r():
    return 0x8000 | src(SD_AR) | dst(SD_R0) | rsp(SP_INC)

def jp_d():
    return 0x8000 | src(SD_D0) | dst(SD_PC) | dsp(SP_DEC)

def jp_a():
    return 0x8000 | src(SD_AR) | dst(SD_PC)

def jp_r():
    return 0x8000 | src(SD_R0) | dst(SD_PC) | rsp(SP_DEC)

def jpz_a(): # condition in d0, jump address in ar
    return 0x8000 | src(SD_AR) | dst(SD_PC) | dsp(SP_DEC)

def jpz_r(): # condition in d0, jump address in r0
    return 0x8000 | src(SD_AR) | dst(SD_PC) | dsp(SP_DEC) | rsp(SP_DEC)

