from prim import Prim, MemoryIf
from primasm import PrimAsm

class Mif(MemoryIf):
    def __init__(self, init=None):
        self._mem16 = [0] * 0x10000
        if not init is None:
            for i in range(len(init)):
                self._mem16[i//2] = (self._mem16[i//2] >> 8) | (init[i] << 8)

    def read(self, addr):
        return self._mem16[addr]

    def write(self, addr, value):
        self._mem16[addr] = value & 0xffff


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
