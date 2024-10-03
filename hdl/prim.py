#! /usr/bin/env python3

from amaranth import *
from amaranth.lib import enum
from amaranth.lib.memory import Memory
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.sim import Simulator, Period

# from stack import *
from primopcodes import *

class Prim(wiring.Component):
    def __init__(self):
        self.data_in = Signal(16)
        self.data_out = Signal(16)
        self.addr = Signal(16)
        self.we = Signal()
        self.acs = Signal(2) # access-size: 0: none, 1: byte (8bit) or 2: word (16bit)
        self.ack = Signal()

        self.dstack_depth = 8

        self.rstack_depth = 16
        self.rtop = Signal(16)

    def elaborate(self, platform):
        m = Module()

        dstack = m.submodules.dstack = Memory(shape=unsigned(16), depth=self.dstack_depth, init=[])
        dstack_rp = dstack.read_port()
        dstack_wp = dstack.write_port()
        self.dsp = dsp = Signal(range(self.dstack_depth))
        self.top = Signal(16)
        self.second = Signal(16)


        def dpush(m, signal):
            m.d.comb += [
                dstack_wp.data.eq(self.second),
                dstack_wp.en.eq(1)
            ]
            m.d.sync += [
                self.top.eq(signal),
                self.second.eq(self.top),
                self.dsp.eq(self.dsp+1)
            ]

        def dpop(m):
            m.d.sync += [
                self.top.eq(self.second),
                self.second.eq(dstack_rp.data),
                self.dsp.eq(self.dsp-1)
            ]

        self.pc = pc = Signal(16)
        self.ir = ir = Signal(16)

        m.d.comb += [
            dstack_wp.addr.eq(self.dsp+1),
            dstack_rp.addr.eq(self.dsp),
            dstack_rp.en.eq(1),
        ]

        memaccess16 = (self.ir & 1) # warum geht das ohne m.d.comb ??

        m.d.comb += dstack_wp.en.eq(0)

        with m.FSM(init="Reset"):
            with m.State("Reset"):
                m.d.sync += Print("Reset")
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
                    m.d.sync += Print(Format("{:04x}: Instruction Fetch: {:02x} ", self.pc, self.data_in))
                    with m.If(self.data_in & 0xf0 == 0x20):
                        m.next = "Memory Fetch"
                    with m.Elif(self.data_in & 0xf0 == 0x30):
                        m.next = "Memory Store"
                    with m.Else():
                        m.next = "Execute"
                    m.d.sync += ir.eq(self.data_in)

            with m.State("Memory Fetch"):
                m.d.comb += [
                    self.addr.eq(pc),
                    self.acs.eq(1 + (self.ir & 1)),
                    self.we.eq(0),
                ]

                with m.If(self.ack):
                    m.d.sync += Print(Format("{:04x}: Memory Fetch ({:d}): {:x}", self.pc, self.acs, self.data_in))
                    m.d.sync += self.pc.eq(self.pc + 1 + memaccess16)
                    dpush(m, self.data_in)
                    m.next = "Execute"

            with m.State("Memory Store"):
                m.d.comb += [
                    self.addr.eq(self.top),
                    self.acs.eq(1 + memaccess16),
                    self.data_out.eq(self.second),
                    self.we.eq(1)
                ]
                with m.If(self.ack):
                    m.d.sync += Print(Format("{:04x}: Memory Store {:04x}<-{:x}", self.pc, self.addr, self.data_out))
                    dpop(m)
                    m.next = "Instruction Fetch"


            with m.State("Execute"):
                m.d.sync += Print("Execute")
                m.next = "Instruction Fetch"
                self.execute(m, ir)

        return m

    def execute(self, m, ir):
        pass
        # with m.Switch(ir & 0x7f):
        #     with m.Case(PrimOpcodes.NOP):
        #         pass
        #     with m.Case(PrimOpcodes.CALL):
        #         m.d.sync += self.pc.eq(self.dstack.top)
        #         m.d.sync += self.dstack.pop.eq(1)
        #     with m.Case(PrimOpcodes.PUSH8):
        #         m.d.sync += self.dstack.push.eq(1)
        #         m.d.comb += Print("push8")



def main():
    def mem_create(init):
        mem = [PrimOpcodes.SIMEND]*0x10000
        for i in range(len(init)):
            mem[i] = init[i]
        return mem

    mem = mem_create(init=[
        PrimOpcodes.PUSH8, 1,
        PrimOpcodes.PUSH8, 2,
        PrimOpcodes.PUSH8, 3,
        PrimOpcodes.PUSH8, 4,
        PrimOpcodes.PUSH8, 5,
        PrimOpcodes.PUSH8, 6,
        PrimOpcodes.PUSH8, 7,
        PrimOpcodes.PUSH8, 123,
        PrimOpcodes.PUSH, 0x34, 0x12,
        PrimOpcodes.STORE8,
        PrimOpcodes.SIMEND
        ])
    print(mem[0:10])
    dut = Prim()
    async def bench(ctx):
        memcyc = 0
        for _ in range(100):
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
