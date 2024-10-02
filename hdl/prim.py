#! /usr/bin/env python3

from amaranth import *
from amaranth.lib import enum
from amaranth.lib.memory import Memory
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.sim import Simulator, Period

from stack import Stack

class PrimOpcodes(enum.Enum):
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
    BREAK = 0x1c

    FETCH8 = 0x20
    FETCH = 0x21
    STORE8 = 0x22
    STORE = 0x23
    PUSH8 = 0x24
    PUSH = 0x25

    SIMEND = 0xff

class Prim(wiring.Component):
    def __init__(self):
        self.data_in = Signal(16)
        self.data_out = Signal(16)
        self.addr = Signal(16)
        self.we = Signal()
        self.acs = Signal(2) # access-size: 0: none, 1: byte (8bit) or 2: word (16bit)
        self.ack = Signal()

    def elaborate(self, platform):
        m = Module()

        self.dstack = m.submodules.dstack = Stack(width=16, depth=16)

        self.pc = pc = Signal(16)
        self.ir = ir = Signal(16)

        m.d.sync += self.dstack.pop.eq(0)
        m.d.sync += self.dstack.push.eq(0)

        with m.FSM(init="Reset"):
            with m.State("Reset"):
                m.d.sync += Print("State: Reset")
                m.d.sync += pc.eq(0)
                m.next = "Instruction Fetch"

            with m.State("Instruction Fetch"):
                m.d.comb += [
                    self.addr.eq(pc),
                    self.acs.eq(1),
                    self.we.eq(0)
                ]
                with m.If(self.ack):
                    m.d.sync += pc.eq(pc+1)
                    m.d.sync += Print(Format("Instruction Fetch: {:02x}", self.data_in))
                    with m.If(self.data_in & 0x20 == 0x20):
                        m.next = "Memory Fetch"
                    with m.Else():
                        m.next = "Execute"
                    m.d.sync += ir.eq(self.data_in)

            with m.State("Memory Fetch"):
                m.d.sync += Print("Memory Fetch")
                m.d.comb += [
                    self.addr.eq(pc),
                    self.acs.eq(1 + (self.ir & 1)),
                    self.we.eq(0)
                ]
                with m.If(self.ack):
                    m.d.sync += self.pc.eq(self.pc + 1 + (self.ir & 1))
                    m.next = "Execute"


            with m.State("Execute"):
                m.d.sync += Print("Execute")
                m.next = "Instruction Fetch"
                self.execute(m, ir)

        return m

    def execute(self, m, ir):
        pass
        # with m.Switch(ir):
        #     with m.Case(PrimOpcodes.NOP):
        #         pass
        #     with m.Case(PrimOpcodes.CALL):
        #         m.d.sync += self.pc.eq(self.dstack.top)
        #         m.d.sync += self.dstack.pop.eq(1)
        #     with m.Case(PrimOpcodes.PUSH8):
        #         m.d.sync += self.dstack.push.eq(1)
        #         m.d.comb += Print("push8")



def main():
    mem = [PrimOpcodes.PUSH8, 123, PrimOpcodes.SIMEND]

    dut = Prim()
    async def bench(ctx):
        memcyc = 0
        for _ in range(10):
            ir = ctx.get(dut.ir)
            if ir == PrimOpcodes.SIMEND.value:
                print("ENDSIM")
                break
            ctx.set(dut.ack, 0)
            if ctx.get(dut.acs) > 0:
                memcyc += 1
                if memcyc > 1:
                    addr = ctx.get(dut.addr)
                    if addr >= len(mem):
                        print(f"Out of memory bounds {addr}")
                        break
                    value = mem[addr]
                    if ctx.get(dut.acs) == 2:
                        if addr+1 >= len(mem):
                            print(f"Out of memory bounds {addr+1}")
                            break
                        value |= mem[addr+1] << 8
                    ctx.set(dut.data_in, value)
                    ctx.set(dut.ack, 1)
                    memcyc = 0
            await ctx.tick()

    sim = Simulator(dut)
    sim.add_clock(Period(MHz=1))
    sim.add_testbench(bench)
    with sim.write_vcd("prim.vcd"):
        sim.run()

    from amaranth.back import verilog
    with open("prim.v", "w") as f:
        f.write(verilog.convert(dut, ports=[dut.data_in, dut.data_out, dut.addr, dut.we, dut.acs, dut.ack]))


if __name__ == "__main__":
    main()
