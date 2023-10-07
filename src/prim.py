import sys

from primconsts import *
from primasm import *

class MemoryIf:
    def read8(self, addr):
        ...
    def read16(self, addr):
        ...
    def write8(self, addr, value):
        ...
    def write16(self, addr, value):
        ...

class Prim:
    # stack sizes
    DS_SIZE = 16
    RS_SIZE = 16
    # isr
    ISR_ADDR = 4

    LOG_LEVEL_MUTE = 0
    LOG_LEVEL_WARN = 1
    LOG_LEVEL_INF = 2
    LOG_LEVEL_DBG = 3

    def __init__(self, mif):
        self._mif = mif # memory interface with read, write methodes
        self.reset()
        self._log_level = Prim.LOG_LEVEL_MUTE

    def reset(self):
        self._pc = 0
        self._ds = [0] * Prim.DS_SIZE
        self._rs = [0] * Prim.RS_SIZE
        self._dsp = Prim.DS_SIZE - 1
        self._rsp = Prim.RS_SIZE - 1
        self._carry = 0

    def setLogLevel(self, level):
        self._log_level = level

    def log(self, level, s):
        sl = ["LOG_MUTE", "LOG_WARN", "LOG_INF", "LOG_DBG"]
        assert level >= Prim.LOG_LEVEL_MUTE and level <= Prim.LOG_LEVEL_DBG, f"Invalid log level {level}"
        if level <= self._log_level:
            print(f"<{sl[level]}>:  {s}")

    def read8(self, addr):
        return self._mif.read8(addr)

    def read16(self, addr):
        return self._mif.read16(addr)

    def write8(self, addr, value):
        self._mif.write8(addr, value)

    def write16(self, addr, value):
        self._mif.write16(addr, value)

    def fetch8(self):
        b = self.read8(self._pc)
        self._pc = (self._pc + 1) & 0xffff
        return b

    def fetch16(self):
        w = self.read16(self._pc)
        self._pc = (self._pc + 2) & 0xffff
        return w & 0xffff

    def dpush(self, value):
        self._dsp = (self._dsp + 1) % Prim.DS_SIZE
        self._ds[self._dsp] = value & 0xffff

    def rpush(self, value):
        self._rsp = (self._rsp + 1) % Prim.RS_SIZE
        self._rs[self._rsp] = value & 0xffff

    def dpop(self):
        self._dsp = (self._dsp - 1) % Prim.DS_SIZE
        return self._ds[(self._dsp + 1) % Prim.DS_SIZE]

    def rpop(self):
        self._rsp = (self._rsp - 1) % Prim.RS_SIZE
        return self._rs[(self._rsp + 1) % Prim.RS_SIZE]

    def T(self):
        return self._ds[self._dsp]

    def N(self):
        return self._ds[(self._dsp - 1) % Prim.DS_SIZE]

    def R(self):
        return self._rs[self._rsp]

    def comp2(value, bitwidth=16):
        # make 2s complement
        if value & (1<<(bitwidth-1)):
            return value - (1<<bitwidth)
        return value

    def execute(self, ir):
        self.log(Prim.LOG_LEVEL_DBG, f"execute: {PrimAsm.disassembleOpcode(ir)}")
        retbit = ir & 0x80
        ir &= 0x7f
        if ir == PrimOpcodes.NOP:
            pass
        elif ir == PrimOpcodes.CALL:
            retbit = 0
            self.rpush(self._pc)
            addr = self.dpop()
            self._pc = addr
        elif ir == PrimOpcodes.JP:
            retbit = 0
            addr = self.dpop()
            self._pc = addr
        elif ir == PrimOpcodes.JZ:
            retbit = 0
            (f,addr) = (self.dpop(), self.dpop())
            if f == 0:
                self._pc = addr
        elif ir == PrimOpcodes.AND:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N & T)
        elif ir == PrimOpcodes.OR:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N | T)
        elif ir == PrimOpcodes.XOR:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N ^ T)
        elif ir == PrimOpcodes.NOT:
            self.dpush(~self.dpop())
        elif ir == PrimOpcodes.LSR:
            T = self.dpop()
            self.dpush(T >> 1)
            self._carry = (T & 1) != 0
        elif ir == PrimOpcodes.LSL:
            T = self.dpop()
            self.dpush(T << 1)
            self._carry = (T & 0x10000) != 0
        elif ir == PrimOpcodes.ADD:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N + T)
            self._carry = (N + T) > 0xffff
        elif ir == PrimOpcodes.SUB:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N - T)
            self._carry = (N - T) < 0
        elif ir == PrimOpcodes.LTS:
            (T, N) = (self.dpop(), self.dpop())
            res = Prim.comp2(N) < Prim.comp2(T)
            self.dpush(0xffff if res else 0)
        elif ir == PrimOpcodes.LTU:
            (T, N) = (self.dpop(), self.dpop())
            res = N < T
            self.dpush(0xffff if res else 0)
        elif ir == PrimOpcodes.SWAP:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(T)
            self.dpush(N)
        elif ir == PrimOpcodes.OVER:
            self.dpush(self.N())
        elif ir == PrimOpcodes.DUP:
            self.dpush(self.T())
        elif ir == PrimOpcodes.ROT:
            (T, N, n2) = (self.dpop(), self.dpop(), self.dpop())
            self.dpush(N)
            self.dpush(T)
            self.dpush(n2)
        elif ir == PrimOpcodes.NROT:
            (T, N, n2) = (self.dpop(), self.dpop(), self.dpop())
            self.dpush(T)
            self.dpush(n2)
            self.dpush(N)
        elif ir == PrimOpcodes.DROP:
            self.dpop()
        elif ir == PrimOpcodes.RDROP:
            self.rpop()
        elif ir == PrimOpcodes.CARRY:
            self.dpush(self._carry)
        elif ir == PrimOpcodes.TO_R:
            self.rpush(self.dpop())
        elif ir == PrimOpcodes.FROM_R:
            self.dpush(self.rpop())
        elif ir == PrimOpcodes.INT:
            retbit = 0
            self.rpush(self._pc)
            self._pc = Prim.ISR_ADDR
        elif ir == PrimOpcodes.FETCH:
            self.dpush(self.read16(self.dpop()))
        elif ir == PrimOpcodes.BYTE_FETCH:
            self.dpush(self.read8(self.dpop()) & 0xff)
        elif ir == PrimOpcodes.STORE:
            (addr, data) = (self.dpop(), self.dpop())
            self._mif.write16(addr, data)
        elif ir == PrimOpcodes.BYTE_STORE:
            (addr, data) = (self.dpop(), self.dpop())
            self.write8(addr, data)
        elif ir == PrimOpcodes.PUSH8:
            self.dpush(self.fetch8())
        elif ir == PrimOpcodes.PUSH:
            self.dpush(self.fetch16())
        if retbit:
            self._pc = self.rpop()

    def step(self):
        ir = self.fetch8()
        if ir == PrimOpcodes.SIMEND:
            return False
        self.execute(ir)
        return True

    def status(self):
        print(f"pc: {self._pc:04x}")
        sys.stdout.write("ds: ")
        for d in range(self._dsp+1):
            sys.stdout.write(f"{self._ds[d]:x} ")
        print()
        sys.stdout.write("rs: ")
        for r in range(self._rsp+1):
            sys.stdout.write(f"{self._rs[r]:x} ")
        print()
