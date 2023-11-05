class Consts:
    HERE = 10
    LATEST = 12
    DICT = 0xFEFE
    AREA = DICT + 2

    iHERE = 0
    iLATEST = 1

class PrimOpcodes:
    NOP = 0x00
    CALL = 0x01
    JP = 0x02
    JZ = 0x03
    AND = 0x04
    OR = 0x05
    XOR = 0x06
    NOT = 0x07
    SR = 0x08
    SRW = 0x9
    SL = 0x0a
    SLW = 0x0b
    ADD = 0x0c
    SUB = 0x0d
    LTS = 0x0e
    LTU = 0x0f
    SWAP = 0x10
    OVER = 0x11
    DUP = 0x12
    NIP = 0x13
    ROT = 0x14
    NROT = 0x15
    DROP = 0x16
    RDROP = 0x17
    CARRY = 0x18
    TO_R = 0x19
    FROM_R = 0x1a
    INT = 0x1b
    FETCH = 0x1c
    BYTE_FETCH = 0x1d
    STORE = 0x1e
    BYTE_STORE = 0x1f
    PUSH8  = 0x20
    PUSH = 0x21
    BREAK = 0x22
