import sys

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
    # opcodes
    OP_NOP = 0x00
    OP_CALL = 0x01
    OP_JP = 0x02
    OP_JPZ = 0x03
    OP_AND = 0x04
    OP_OR = 0x05
    OP_XOR = 0x06
    OP_NOT = 0x07
    OP_LSR = 0x08
    OP_LSL = 0x09
    OP_ADD = 0x0a
    OP_SUB = 0x0b
    OP_LTS = 0x0c
    OP_LTU = 0x0d
    OP_SWAP = 0x0e
    OP_OVER = 0x0f
    OP_DUP = 0x10
    OP_NIP = 0x11
    OP_ROT = 0x12
    OP_NROT = 0x13
    OP_DROP = 0x14
    OP_RDROP = 0x15
    OP_CARRY = 0x16
    OP_TO_R = 0x17
    OP_FROM_R = 0x18
    OP_INT = 0x19
    OP_FETCH = 0x1a
    OP_BYTE_FETCH = 0x1b
    OP_STORE = 0x1c
    OP_BYTE_STORE = 0x1d
    OP_PUSH8  = 0x1e
    OP_PUSH = 0x1f
    OP_SIMEND = 0x7f
    # stack sizes
    DS_SIZE = 16
    RS_SIZE = 16
    # isr
    ISR_ADDR = 4

    def __init__(self, mif):
        self._mif = mif # memory interface with read, write methodes
        self.reset()

    def reset(self):
        self._pc = 0
        self._ds = [0] * Prim.DS_SIZE
        self._rs = [0] * Prim.RS_SIZE
        self._dsp = Prim.DS_SIZE - 1
        self._rsp = Prim.RS_SIZE - 1
        self._carry = 0

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
        retbit = ir & 0x80
        ir &= 0x7f
        if ir == Prim.OP_NOP:
            pass
        elif ir == Prim.OP_CALL:
            retbit = 0
            self.rpush(self._pc)
            addr = self.dpop()
            self._pc = addr
        elif ir == Prim.OP_JP:
            retbit = 0
            addr = self.dpop()
            self._pc = addr
        elif ir == Prim.OP_JPZ:
            retbit = 0
            (f,addr) = (self.dpop(), self.dpop())
            if f == 0:
                self._pc = addr
        elif ir == Prim.OP_AND:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N & T)
        elif ir == Prim.OP_OR:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N | T)
        elif ir == Prim.OP_XOR:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N ^ T)
        elif ir == Prim.OP_NOT:
            self.dpush(~self.dpop())
        elif ir == Prim.OP_LSR:
            T = self.dpop()
            self.dpush(T >> 1)
            self._carry = (T & 1) != 0
        elif ir == Prim.OP_LSL:
            T = self.dpop()
            self.dpush(T << 1)
            self._carry = (T & 0x10000) != 0
        elif ir == Prim.OP_ADD:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N + T)
            self._carry = (N + T) > 0xffff
        elif ir == Prim.OP_SUB:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(N - T)
            self._carry = (N - T) < 0
        elif ir == Prim.OP_LTS:
            (T, N) = (self.dpop(), self.dpop())
            res = Prim.comp2(N) < Prim.comp2(T)
            self.dpush(0xffff if res else 0)
        elif ir == Prim.OP_LTU:
            (T, N) = (self.dpop(), self.dpop())
            res = N < T
            self.dpush(0xffff if res else 0)
        elif ir == Prim.OP_SWAP:
            (T, N) = (self.dpop(), self.dpop())
            self.dpush(T)
            self.dpush(N)
        elif ir == Prim.OP_OVER:
            self.dpush(self.N())
        elif ir == Prim.OP_DUP:
            self.dpush(self.T())
        elif ir == Prim.OP_ROT:
            (T, N, n2) = (self.dpop(), self.dpop(), self.dpop())
            self.dpush(N)
            self.dpush(T)
            self.dpush(n2)
        elif ir == Prim.OP_NROT:
            (T, N, n2) = (self.dpop(), self.dpop(), self.dpop())
            self.dpush(T)
            self.dpush(n2)
            self.dpush(N)
        elif ir == Prim.OP_DROP:
            self.dpop()
        elif ir == Prim.OP_RDROP:
            self.rpop()
        elif ir == Prim.OP_CARRY:
            self.dpush(self._carry)
        elif ir == Prim.OP_TO_R:
            self.rpush(self.dpop())
        elif ir == Prim.OP_FROM_R:
            self.dpush(self.rpop())
        elif ir == Prim.OP_INT:
            retbit = 0
            self.rpush(self._pc)
            self._pc = Prim.ISR_ADDR
        elif ir == Prim.OP_FETCH:
            self.dpush(self.read16(self.dpop()))
        elif ir == Prim.OP_BYTE_FETCH:
            self.dpush(self.read8(self.dpop()) & 0xff)
        elif ir == Prim.OP_STORE:
            (addr, data) = (self.dpop(), self.dpop())
            self._mif.write16(addr, data)
        elif ir == Prim.OP_BYTE_STORE:
            (addr, data) = (self.dpop(), self.dpop())
            self.write8(addr, data)
        elif ir == Prim.OP_PUSH8:
            self.dpush(self.fetch8())
        elif ir == Prim.OP_PUSH:
            self.dpush(self.fetch16())
        if retbit:
            self._pc = self.rpop()

    def step(self):
        ir = self.fetch8()
        if ir == Prim.OP_SIMEND:
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
