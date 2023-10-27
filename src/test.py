import sys

from prim import Prim, MemoryIf
from primasm import PrimAsm
from primconsts import *

class Mif(MemoryIf):
    def __init__(self, init=None):
        self._mem = bytearray(0x10000)
        if init is not None:
            l = len(init)
            self._mem[0:l] = init

    def read8(self, addr):
        return self._mem[addr]

    def read16(self, addr):
        return self._mem[addr] | (self._mem[addr+1] << 8)

    def write8(self, addr, value):
        self._mem[addr] = value & 0xff
        self._mem[addr+1] = (value >> 8) & 0xff

    def write16(self, addr, value):
        self._mem[addr] = value & 0xff
        self._mem[addr+1] = (value >> 8) & 0xff

class Result:
    def __init__(self, T=None, N=None, R=None, carry=None, dsp=None, rsp=None, pc=None):
        self._T = T
        self._N = N
        self._R = R
        self._carry = carry
        self._dsp = dsp
        self._rsp = rsp
        self._pc = pc


def test(asm, result, idx):
    print(f"Test {idx}: {asm}")
    prog = PrimAsm.assemble(asm)
    if len(prog) % 2 == 0:
        prog.append(PrimOpcodes.SIMEND)
    prog.append(PrimOpcodes.SIMEND)
    print(repr(PrimAsm.disassemble(prog)))
    mif = Mif(prog)
    global cpu
    cpu = Prim(mif)
    count = 0
    while cpu.step() != PrimOpcodes.BREAK:
        # cpu.status()
        count += 1
        assert count < 10, "Test took too many steps"
    error = 0
    if result._T is not None and result._T != cpu.T():
        print(f" T ({cpu.T():x} != {result._T:x})")
        error += 1

    if result._N is not None and result._N != cpu.N():
        print(f" N ({cpu.N():x} != {result._N:x})")
        error += 1

    if result._R is not None and result._R != cpu.R():
        print(f" R ({cpu.R():x} != {result._R:x})")
        error += 1

    if result._carry is not None and result._carry != cpu._carry:
        print(f" carry ({cpu._carry:x} != {result._carry:x})")
        error += 1

    if result._dsp is not None and result._dsp != cpu._dsp:
        print(f" dsp ({cpu._dsp:x} != {result._dsp:x})")
        error += 1

    if result._rsp is not None and result._rsp != cpu._rsp:
        print(f" rsp ({cpu._rsp:x} != {result._rsp:x})")
        error += 1

    if result._pc is not None and result._pc != cpu._pc:
        print(f" pc ({cpu._pc:x} != {result._pc:x})")
        error += 1

    assert error == 0, f"Test {idx} Failed"

    if error == 0:
        print(f" ok")


def main():
    test("NOP", Result(pc=2), 0)
    test("5 call SIMEND nop 2.ret", Result(pc=4, T=2, dsp=0), 1)
    test("6 nop call SIMEND nop 2.ret", Result(pc=5, T=2, dsp=0), 2)
    test("1 2 +", Result(T=3, dsp=0, pc=6), 3)
    test("4 jp SIMEND 0xff", Result(T=0xff, dsp=0, pc=7), 4)
    test("6 0 jz SIMEND 0xfe", Result(T=0xfe, pc=9), 5)
    test("6 1 jz SIMEND 0xfe", Result(pc=6), 6)
    test("1 2 <", Result(T=0xffff, dsp=0, pc=6), 7)
    test("1 2 <u", Result(T=0xffff, dsp=0, pc=6), 8)
    test("2 1 <", Result(T=0, dsp=0, pc=6), 9)
    test("2 1 <u", Result(T=0, dsp=0, pc=6), 10)
    test("-1 1 <", Result(T=0xffff, dsp=0, pc=7), 11)
    test("-1 1 <u", Result(T=0, dsp=0, pc=7), 12)
    test("0xffff 0xf0f0 and", Result(T=0xf0f0), 13)
    test("0xf00f 0x0ff0 or", Result(T=0xffff), 14)
    test("1 0xffff xor", Result(T=0xfffe), 15)
    test("0 NOT", Result(T=0xffff), 16)
    test("2 LSR", Result(T=0x1), 17)
    test("2 LSL", Result(T=0x4), 18)
    test("2 1 -", Result(T=1), 19)
    test("1 2 swap", Result(T=1, N=2, dsp=1), 20)
    test("1 2 over", Result(T=1, N=2, dsp=2), 21)
    test("1 2 dup", Result(T=2, N=2, dsp=2), 22)
    test("1 2 3 rot", Result(T=1, N=3, dsp=2), 23)
    test("1 2 3 -rot", Result(T=2, N=1, dsp=2), 24)
    test("1 2 drop", Result(T=1, dsp=0), 25)
    test("1 >r", Result(R=1, dsp=cpu.DS_SIZE-1, rsp=0), 26)
    test("1 >r 2 >r rdrop", Result(R=1, dsp=cpu.DS_SIZE-1, rsp=0), 27)
    test("1 >r 2 >r 3 >r 4 r>", Result(T=3, N=4, R=2, dsp=1, rsp=1), 28)
    test("0xffff 1 + carry", Result(T=1, N=0, dsp=1), 29)
    test("0xffff 0 + carry", Result(T=0, N=0xffff, dsp=1), 29)
    test("1 0x100 !", Result(dsp=cpu.DS_SIZE-1), 30)
    test("1 0x100 ! 2 0x100 @", Result(N=2, T=1, dsp=1), 31)
    test("0x1234 0x100 ! 0x100 c@ 0x101 c@", Result(T=0x12, N=0x34, dsp=1), 32)
    test("0x1a 0x100 c! 0x1b 0x101 c! 0x100 @", Result(T=0x1b1a), 33)

    return 0

if __name__ == "__main__":
    exit(main())
