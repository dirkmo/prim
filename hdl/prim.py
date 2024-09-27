#! /usr/bin/env python3

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.sim import Simulator, Period

class Prim(wiring.Component):
    en: In(1)

    def elaborate(self, platform):
        m = Module()

        with m.FSM(init="Reset"):
            with m.State("Reset"):
                m.next = "Instruction Fetch"

            with m.State("Instruction Fetch"):
                m.next = "Execute"

            with m.State("Execute"):
                m.next = "Instruction Fetch"

        return m

dut = Prim()
async def bench(ctx):
    for _ in range(10):
        await ctx.tick()

sim = Simulator(dut)
sim.add_clock(Period(MHz=1))
sim.add_testbench(bench)
with sim.write_vcd("prim.vcd"):
    sim.run()
