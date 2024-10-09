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
    # Source/Destination
    SD_ALU = 0
    SD_D0 = 1
    SD_R0 = 2
    SD_AR = 3
    SD_M8_A = 4  #  8-bit mem access, addressed by A
    SD_M8_PC = 5 #  8-bit mem access, addressed by PC
    SD_M_A = 6   # 16-bit mem access, addressed by A
    SD_M_PC = 7  # 16-bit mem access, addressed by PC
    # stack pointer manipulation
    SP_INC = 1
    SP_DEC = 2

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

        self.Table = Array([
            { "src": Prim.SD_AR,    "dst": Prim.SD_AR,  "dsp": 0,           "rsp": 0, "alu": 0}, # NOP
            { "src": Prim.SD_M8_PC, "dst": Prim.SD_D0,  "dsp": Prim.SP_INC, "rsp": 0, "alu": 0}, # PUSH8
            { "src": Prim.SD_M_PC,  "dst": Prim.SD_D0,  "dsp": Prim.SP_INC, "rsp": 0, "alu": 0}, # PUSH

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

        # address register
        self.areg = Signal(16)

        ##
        # program counter
        self.pc = pc = Signal(16)
        # instruction register
        self.ir = ir = Signal(8)
        # return bit
        self.retbit = Signal()
        m.d.comb += self.retbit.eq(self.ir & 0x80)

        # look-up current instruction
        self.lut = self.Table[self.ir & 0x7f]

        # is memory access ongoing?
        self.mem_acc_done = Signal()
        is_mem_op = Signal()
        src = Signal(range(Prim.SD_M_PC))
        dst = Signal(range(Prim.SD_M_PC))
        m.d.comb += [
            src.eq(self.lut["src"]),
            dst.eq(self.lut["dst"]),
            is_mem_op.eq((src[2] | dst[2]).bool()),
            self.mem_acc_done.eq( (~is_mem_op) | self.ack ),
        ]

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
        ir = self.Table[self.ir & 0x7f]

        # data_out
        m.d.comb += self.data_out.eq(self.dstack_rp.data)

         # data stack
        m.d.comb += [
            self.dstack_rp.addr.eq(self.dsp-2), # TODO: evtl 0 besser?
            self.dstack_wp.addr.eq(self.dsp-1) # TODO: evtl +1 besser?
        ]

        # default values
        m.d.comb += [
            self.addr.eq(self.pc),
            self.we.eq(0),
            self.acs.eq(0)
        ]

        # next_pc = Signal(self.pc.shape())

        dsp_next = Signal(16)
        with m.Switch(ir["dsp"]):
            with m.Case(Prim.SP_INC):
                m.d.comb += dsp_next.eq(self.dsp + 1)
            with m.Case(Prim.SP_DEC):
                m.d.comb += dsp_next.eq(self.dsp - 1)
            with m.Default():
                pass

        rsp_next = Signal(16)
        with m.Switch(ir["rsp"]):
            with m.Case(Prim.SP_INC):
                m.d.comb += rsp_next.eq(self.rsp + 1)
            with m.Case(Prim.SP_DEC):
                m.d.comb += rsp_next.eq(self.rsp - 1)
            with m.Default():
                pass

        src = Signal(16)
        with m.Switch(ir["src"]):
            with m.Case(Prim.SD_ALU):
                m.d.comb += src.eq(self.alu_out(m, self.ir))
            with m.Case(Prim.SD_D0):
                m.d.comb += src.eq(self.dstack_rp.data)
            with m.Case(Prim.SD_R0):
                m.d.comb += src.eq(self.rstack_rp.data)
            with m.Case(Prim.SD_AR):
                m.d.comb += src.eq(self.areg)
            with m.Case(Prim.SD_M8_A):
                m.d.comb += [
                    src.eq(Cat(self.data_in[:8], Const(0, 8))),
                    self.addr.eq(self.areg)
                ]
            with m.Case(Prim.SD_M8_PC):
                m.d.comb += [
                    src.eq(Cat(self.data_in[:8], Const(0, 8))),
                    self.addr.eq(self.pc)
                ]
            with m.Case(Prim.SD_M_A):
                m.d.comb += [
                    src.eq(self.data_in),
                    self.addr.eq(self.areg)
                ]
            with m.Case(Prim.SD_M_PC):
                m.d.comb += [
                    src.eq(self.data_in),
                    self.addr.eq(self.pc)
                ]
            with m.Default():
                pass

        with m.Switch(ir["dst"]):
            with m.Case(Prim.SD_D0):
                m.d.comb += [
                    self.dstack_wp.data.eq(src),
                    self.dstack_wp.en.eq(1)
                ]
            with m.Case(Prim.SD_R0):
                m.d.comb += [
                    self.rstack_wp.data.eq(src),
                    self.rstack_wp.en.eq(1)
                ]
            with m.Case(Prim.SD_AR):
                m.d.comb += self.areg.eq(src)
            with m.Case(Prim.SD_M8_A):
                m.d.comb += [
                    self.addr.eq(self.areg),
                    self.we.eq(1),
                    self.acs.eq(1),
                ]
            with m.Case(Prim.SD_M8_PC):
                m.d.comb += [
                    self.addr.eq(self.pc),
                    self.we.eq(1),
                    self.acs.eq(1),
                ]
            with m.Case(Prim.SD_M_A):
                m.d.comb += [
                    self.addr.eq(self.areg),
                    self.we.eq(1),
                    self.acs.eq(2),
                ]
            with m.Case(Prim.SD_M_PC):
                m.d.comb += [
                    self.addr.eq(self.pc),
                    self.we.eq(1),
                    self.acs.eq(2),
                ]
            with m.Default():
                pass

    def alu_out(self, m, op):
        out = Signal(16)
        with m.Switch(op & 0xf):
            with m.Case(0):
                m.d.comb += out.eq(0)
            with m.Default():
                m.d.comb += out.eq(0xffff)
        return out


def main():
    def mem_create(init):
        mem = [PrimOpcodes.SIMEND.value]*0x10000
        for i in range(len(init)):
            mem[i] = init[i]
        return mem

    mem = mem_create(init=[
        0,
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
