from prim import Prim, MemoryIf
from primasm import PrimAsm

class Mif(MemoryIf):
    def __init__(self, init=None):
        self._mem = bytearray(0x20000)
        if init is not None:
            l = len(init)
            self._mem[0:l] = init

    def read(self, addr):
        return self._mem[addr*2] | (self._mem[addr*2+1] << 8)

    def write(self, addr, value):
        self._mem[addr*2] = value & 0xff
        self._mem[addr*2+1] = (value >> 8) & 0xff


def main():
    prog = PrimAsm.assemble("1 2 add")
    mif = Mif(prog)
    cpu = Prim(mif)

    cpu.step()
    cpu.status()

    cpu.step()
    cpu.status()

    cpu.step()
    cpu.status()

    return 0

if __name__ == "__main__":
    exit(main())
