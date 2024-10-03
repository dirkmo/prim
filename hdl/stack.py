#! /usr/bin/env python3

from amaranth import *
from amaranth.lib import enum
from amaranth.lib.memory import Memory
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.sim import Simulator, Period

class DataStack(wiring.Component):
    def __init__(self, width=16, depth=16):
        self.top = Signal(width)
        self.second = Signal(width)
        self.data_in = Signal(width)
        self.push = Signal()
        self.pop1 = Signal()
        self.pop2 = Signal()
        self.dsp = Signal(4)
        self.depth = depth

    def port_list(self):
        return [self.top,self.second,self.data_in,self.push,self.pop,self.dsp]

    def elaborate(self, platform):
        m = Module()

        dstack = m.submodules.dstack = Memory(shape=unsigned(16), depth=self.depth, init=[])

        rdp_top = dstack.read_port()
        m.d.comb += self.top.eq(rdp_top.data)
        m.d.comb += rdp_top.addr.eq(self.dsp)
        m.d.comb += rdp_top.en.eq(1)

        rdp_second = dstack.read_port()
        m.d.comb += self.second.eq(rdp_second.data)
        m.d.comb += rdp_second.addr.eq(self.dsp-1)
        m.d.comb += rdp_second.en.eq(1)

        wdp = dstack.write_port()
        m.d.comb += wdp.data.eq(self.data_in)
        m.d.comb += wdp.addr.eq(self.dsp+1)
        m.d.comb += wdp.en.eq(self.push)

        with m.If(self.push):
            m.d.sync += self.dsp.eq(self.dsp+1)
        with m.Elif(self.pop1):
            m.d.sync += self.dsp.eq(self.dsp-1)
        with m.Elif(self.pop2):
            m.d.sync += self.dsp.eq(self.dsp-2)

        return m


if __name__ == "__main__":

    dut = Stack()
    async def bench(ctx):
        #val = 65
        async def push(ctx, val):
            ctx.set(dut.data_in, val)
            ctx.set(dut.push, 1)
            ctx.set(dut.pop, 0)
            await ctx.tick()
            ctx.set(dut.push, 0)
            await ctx.tick()

        await push(ctx, 65)
        await ctx.tick()


    sim = Simulator(dut)
    sim.add_clock(Period(MHz=1))
    sim.add_testbench(bench)
    with sim.write_vcd("stack.vcd"):
        sim.run()


    from amaranth.back import verilog
    with open("stack.v", "w") as f:
        f.write(verilog.convert(dut, ports=dut.port_list()))
