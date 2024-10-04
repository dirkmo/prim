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

    T_ALU = 1
    T_D0 = 2
    T_D1 = 3
    T_R0 = 4
    T_RAM = 5

    D0_T = 1
    #D0_D1 = 2

    R_PC = 1
    R_R0 = 2
    R_T = 3

    R0_R = 1
    R0_R1 = 2

    PC_1 = 1
    PC_T = 2

    MA_NONE = 0
    MA_READ8 = 1
    MA_READ = 2
    MA_WRITE8 = 3
    MA_WRITE = 4

    ADDR_PC = 0
    ADDR_T = 1




    def __init__(self):
        self.data_in = Signal(16)
        self.data_out = Signal(16)
        self.addr = Signal(16)
        self.we = Signal()
        self.acs = Signal(2) # access-size: 0: none, 1: byte (8bit) or 2: word (16bit)
        self.ack = Signal()

        self.dstack_depth = 8

        self.rstack_depth = 8
        self.rtop = Signal(16)

        self.ie = Signal() # interrupt enabled

        self.Lut = Array([
            {"dsp":  0, "rsp": 0, "top": 0,          "d0": 0,         "rtop": 0,         "r0": 0, "pc": 0,         "ma": Prim.MA_NONE,  "addr": 0, }, # NOP
            {"dsp": -1, "rsp": 1, "top": Prim.T_D0,  "d0": 0,         "rtop": Prim.R_PC, "r0": 0, "pc": 0,         "ma": Prim.MA_NONE,  "addr": 0, }, # CALL
            {"dsp":  1, "rsp": 0, "top": Prim.T_RAM, "d0": Prim.D0_T, "rtop": 0,         "r0": 0, "pc": Prim.PC_1, "ma": Prim.MA_READ8, "addr": Prim.ADDR_PC, }, # PUSH8
            {"dsp":  1, "rsp": 0, "top": Prim.T_RAM, "d0": Prim.D0_T, "rtop": 0,         "r0": 0, "pc": Prim.PC_1, "ma": Prim.MA_READ,  "addr": Prim.ADDR_PC, }, # PUSH
            {"dsp": -2, "rsp": 0, "top": 0,          "d0": 0,         "rtop": 0,         "r0": 0, "pc": 0,         "ma": Prim.MA_WRITE8,"addr": Prim.ADDR_T, }, # STORE8


            {"dsp": -2, "rsp": 0, "top": Prim.T_D1,  "d0": 0,         "rtop": 0,         "r0": 0, "pc": Prim.PC_T, "ma": Prim.MA_WRITE,"addr": Prim.ADDR_T, }, # temp
        ])

    def elaborate(self, platform):
        m = Module()

        ## data stack
        dstack = m.submodules.dstack = Memory(shape=unsigned(16), depth=self.dstack_depth, init=[])
        self.dstack_rp = dstack_rp = dstack.read_port()
        self.dstack_wp = dstack_wp = dstack.write_port()

        # data stack pointer
        self.dsp = dsp = Signal(range(self.dstack_depth))
        # top register
        self.top = Signal(16)

        ## return stack
        rstack = m.submodules.rstack = Memory(shape=unsigned(16), depth=self.rstack_depth, init=[])
        self.rstack_rp = rstack_rp = rstack.read_port()
        self.rstack_wp = rstack_wp = rstack.write_port()

        # return stack pointer
        self.rsp = dsp = Signal(range(self.rstack_depth))
        # top register
        self.rtop = Signal(16)

        ##
        # program counter
        self.pc = pc = Signal(16)
        # instruction register
        self.ir = ir = Signal(8)
        # return bit
        self.retbit = Signal()
        m.d.comb += self.retbit.eq(self.ir & 0x80)

        # look-up current instruction
        self.lut = self.Lut[self.ir & 0x7f]

        # is memory access ongoing?
        self.mem_acc_done = Signal()
        m.d.comb += self.mem_acc_done.eq((self.lut["ma"] == Prim.MA_NONE) | self.ack),

        m.d.comb += [
            dstack_wp.addr.eq(self.dsp+1),
            dstack_rp.addr.eq(self.dsp),
            dstack_rp.en.eq(1),
        ]

        #m.d.comb += dstack_wp.en.eq(0)

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
                    m.d.sync += [
                        pc.eq(pc+1),
                        ir.eq(self.data_in),
                    ]
                    m.d.sync += Print(Format("{:04x}: Instruction Fetch: {:02x} ", self.pc, self.data_in))
                    m.next = "Execute"

            with m.State("Execute"):
                m.d.sync += Print("Execute")
                self.execute(m)
                with m.If(self.mem_acc_done):
                    m.next = "Instruction Fetch"

        return m

    def execute(self, m):
        ir = self.Lut[self.ir & 0x7f]

        with m.If(self.mem_acc_done):
            m.d.sync += [
                self.dsp.eq(self.dsp + ir["dsp"]),
                self.rsp.eq(self.dsp + ir["rsp"]),
            ]

        # top
        with m.Switch(ir["top"]):
            with m.Case(Prim.T_RAM):
                with m.If(self.mem_acc_done): # TODO: kann man sich vermutlich sparen
                    m.d.sync += self.top.eq(self.data_in)
            with m.Case(Prim.T_ALU):
                m.d.sync += self.top.eq(0) # TODO
            with m.Case(Prim.T_D0):
                m.d.sync += self.top.eq(self.dstack_rp.data)
            with m.Case(Prim.T_D1):
                m.d.sync += self.top.eq(self.dstack_rp.data)
            with m.Case(Prim.T_R0):
                m.d.sync += self.top.eq(self.rstack_rp.data)

        # data stack
        m.d.comb += self.dstack_rp.addr.eq(self.dsp-2) # TODO: evtl 0 besser?
        m.d.comb += self.dstack_wp.addr.eq(self.dsp-1) # TODO: evtl +1 besser?

        with m.Switch(ir["d0"]):
            with m.Case(Prim.D0_T):
                m.d.comb += self.dstack_wp.data.eq(self.top)
                m.d.comb += self.dstack_wp.en.eq(1)
            with m.Default():
                m.d.comb += self.dstack_wp.en.eq(0)

        # pc
        next_pc = Signal(self.pc.shape())
        with m.If(ir["ma"] == Prim.MA_READ):
            m.d.comb += next_pc.eq(self.pc+2) # assuming PUSH
        with m.Else():
            m.d.comb += next_pc.eq(self.pc+1) # assuming PUSH8

        with m.Switch(ir["pc"]):
            with m.Case(Prim.PC_1):
                with m.If(self.mem_acc_done):
                    m.d.sync += self.pc.eq(next_pc)
            with m.Case(Prim.PC_T):
                m.d.sync += self.pc.eq(self.top)

        # addr
        with m.Switch(ir["addr"]):
            with m.Case(Prim.ADDR_PC):
                m.d.comb += self.addr.eq(self.pc)
            with m.Case(Prim.ADDR_T):
                m.d.comb += self.addr.eq(self.top)

        # we
        with m.Switch(ir["ma"]):
            with m.Case(Prim.MA_WRITE, Prim.MA_WRITE8):
                m.d.comb += self.we.eq(1)
            with m.Default():
                m.d.comb += self.we.eq(0)

        # acs
        with m.Switch(ir["ma"]):
            with m.Case(Prim.MA_WRITE, Prim.MA_READ):
                m.d.comb += self.acs.eq(2)
            with m.Case(Prim.MA_WRITE8, Prim.MA_READ8):
                m.d.comb += self.acs.eq(1)
            with m.Default():
                m.d.comb += self.acs.eq(0)

        # data_out
        m.d.comb += self.data_out.eq(self.dstack_rp.data)


def main():
    def mem_create(init):
        mem = [PrimOpcodes.SIMEND.value]*0x10000
        for i in range(len(init)):
            mem[i] = init[i]
        return mem

    mem = mem_create(init=[
        2, 0x11, #push8
        2, 0x22, #push8
        2, 0x33, #push8
        3, 0x34, 0x12, #push16
        4, # store8
        PrimOpcodes.SIMEND.value
        ])
    print(mem[0:10])
    dut = Prim()

    async def bench(ctx):
        memcyc = 0
        for _ in range(30):
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
