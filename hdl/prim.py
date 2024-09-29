#! /usr/bin/env python3

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.sim import Simulator, Period

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

        pc = Signal(16)

        with m.FSM(init="Reset"):
            with m.State("Reset"):
                m.d.sync += pc.eq(0)
                m.next = "Instruction Fetch"

            with m.State("Instruction Fetch"):
                m.d.comb += [
                    self.addr.eq(pc),
                    self.acs.eq(1),
                    self.we.eq(0)
                ]
                m.d.sync += pc.eq(pc+1)
                with m.If(self.ack):
                    m.next = "Execute"

            with m.State("Execute"):
                m.next = "Instruction Fetch"

        return m

dut = Prim()
async def bench(ctx):
    for _ in range(10):
        ctx.set(dut.ack, 0)
        if ctx.get(dut.acs) > 0:
            ctx.set(dut.ack, 1)
        await ctx.tick()

sim = Simulator(dut)
sim.add_clock(Period(MHz=1))
sim.add_testbench(bench)
with sim.write_vcd("prim.vcd"):
    sim.run()
