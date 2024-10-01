#! /usr/bin/env python3

from amaranth import *
from amaranth.lib import enum
from amaranth.lib.memory import Memory
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.sim import Simulator, Period

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
    FETCH = 0x1c
    BYTE_FETCH = 0x1d
    STORE = 0x1e
    BYTE_STORE = 0x1f
    PUSH8  = 0x20
    PUSH = 0x21
    BREAK = 0x22
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

        self.dstack = Memory(shape=unsigned(16), depth=16, init=[])
        self.dsp = Signal(16)

        self.pc = pc = Signal(16)
        self.ir = ir = Signal(16)

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
                    m.d.sync += ir.eq(self.data_in)
                    m.d.comb += Print("ir: ", ir)

            with m.State("Execute"):
                m.next = "Instruction Fetch"
                self.execute(m, ir)

        return m

    def execute(self, m, ir):
        with m.Switch(ir):
            with m.Case(PrimOpcodes.NOP):
                pass
            with m.Case(PrimOpcodes.CALL):
                m.d.sync += self.pc.eq(self.dstack[self.dsp])



mem = [PrimOpcodes.AND, PrimOpcodes.NOT, PrimOpcodes.SIMEND]

dut = Prim()
async def bench(ctx):
    memcyc = 0
    for _ in range(10):
        ctx.set(dut.ack, 0)
        if ctx.get(dut.acs) > 0:
            memcyc += 1
            if memcyc > 1:
                addr = ctx.get(dut.addr)
                ctx.set(dut.data_in, mem[addr] if addr < len(mem) else 0)
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
