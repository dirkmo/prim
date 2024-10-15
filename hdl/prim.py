#! /usr/bin/env python3

from amaranth import *
from amaranth.lib import enum, wiring
from amaranth.lib.memory import Memory
from amaranth.lib.wiring import In, Out
from amaranth.sim import Simulator, Period
from amaranth.back import verilog

# from stack import *
import PrimOpcodes

class Prim(wiring.Component):

    def __init__(self):
        self.data_in = Signal(16)
        self.data_out = Signal(16)
        self.addr = Signal(16)
        self.we = Signal()
        self.cs = Signal()
        self.int = Signal()

        self.dstack_depth = 8
        self.rstack_depth = 8

        self.ie = Signal() # interrupt enabled

    def decode(self, m):
        # 0 <imm:15>
        # 1 <src:3> <dst:3> <dsp:2> <rsp:2> <ret:1> <alu:4>

        # 1 1 1 1 1 1
        # 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
        # I|src  |dst  |dsp|rsp|r| alu

        self.op_alu = Signal(4) # 0-3
        self.op_ret = Signal() # 4
        self.op_rsp = Signal(2) # 5-6
        self.op_dsp = Signal(2) # 7-8
        self.op_dst = Signal(3) # 9-11
        self.op_src = Signal(3) # 12-14
        self.op_type = Signal() # 15
        m.d.comb += [
            self.op_alu.eq(self.ir[0:4]),
            self.op_ret.eq(self.ir[4]),
            self.op_rsp.eq(self.ir[5:7]),
            self.op_dsp.eq(self.ir[7:9]),
            self.op_dst.eq(self.ir[9:12]),
            self.op_src.eq(self.ir[12:15]),
            self.op_type.eq(self.ir[15])
        ]


    def elaborate(self, platform):
        m = Module()

        ## data stack
        self.dstack = dstack = m.submodules.dstack = Memory(shape=unsigned(16), depth=self.dstack_depth, init=[])
        self.dstack_rp = dstack_rp = dstack.read_port()
        self.dstack_wp = dstack_wp = dstack.write_port()

        # data stack pointer
        self.dsp = dsp = Signal(range(self.dstack_depth))
        # top register
        self.top = Signal(16)

        ## return stack
        self.rstack = rstack = m.submodules.rstack = Memory(shape=unsigned(16), depth=self.rstack_depth, init=[])
        self.rstack_rp = rstack_rp = rstack.read_port()
        self.rstack_wp = rstack_wp = rstack.write_port()

        # return stack pointer
        self.rsp = dsp = Signal(range(self.rstack_depth))

        # address register
        self.areg = Signal(16)

        ##
        # program counter
        self.pc = Signal(16)
        # instruction register
        self.ir = Signal(16)

        m.d.comb += [
            dstack_rp.addr.eq(self.dsp-1),
            dstack_wp.addr.eq(self.dsp),
            dstack_rp.en.eq(1),
        ]

        self.decode(m)

        with m.FSM(init="Reset"):
            with m.State("Reset"):
                m.d.sync += Print("Reset")
                m.d.sync += self.pc.eq(0)
                m.next = "Fetch-1"

            with m.State("Fetch-1"):
                m.d.comb += [
                    self.addr.eq(self.pc),
                    self.cs.eq(1),
                    self.we.eq(0)
                ]
                m.next = "Fetch-2"

            with m.State("Fetch-2"):
                m.d.sync += [
                    self.pc.eq(self.pc+1),
                    self.ir.eq(self.data_in),
                    Print(Format("{:04x}: Instruction Fetch: {:02x} ", self.pc, self.data_in)),
                ]
                m.d.comb += [
                    self.addr.eq(self.pc),
                    self.cs.eq(1),
                    self.we.eq(0)
                ]

                with m.If(self.data_in[15] == 0):
                    m.next = "Push"
                with m.Else():
                    m.next = "Execute-1"

            with m.State("Push"):
                m.d.sync += Print("Push")
                self.push(m)
                m.next = "Fetch-1"

            with m.State("Execute-1"):
                m.d.sync += Print("Execute-1")
                self.execute(m, write=False)
                m.next = "Execute-2"

            with m.State("Execute-2"):
                m.d.sync += Print("Execute-2")
                self.execute(m, write=True)
                m.next = "Fetch-1"

        return m

    def push(self, m): # push immediate
        m.d.comb += [
            self.dstack_wp.data.eq(self.top),
            self.dstack_wp.en.eq(1)
        ]
        m.d.sync += [
            self.top.eq(Cat(self.ir[0:15], Const(0, 1))),
            self.dsp.eq(self.dsp + 1)
        ]

    def execute(self, m, write):
        # data_out
        m.d.comb += self.data_out.eq(self.dstack_rp.data)

        pc_next = Signal(16)

        # default values
        m.d.comb += [
            self.addr.eq(self.pc),
            self.we.eq(0),
            self.cs.eq(0),
            pc_next.eq(self.pc),
            self.dstack_wp.data.eq(self.top),
        ]

        top_next = Signal(16)


        dsp_next = Signal(16)
        with m.Switch(self.op_dsp):
            with m.Case(PrimOpcodes.SP_INC):
                m.d.comb += [
                    dsp_next.eq(self.dsp + 1),
                    top_next.eq(self.dstack_rp.data),
                    self.dstack_wp.en.eq(write)
                ]
            with m.Case(PrimOpcodes.SP_DEC):
                m.d.comb += [
                    dsp_next.eq(self.dsp - 1),
                    top_next.eq(self.dstack_rp.data),
                ]
            with m.Default():
                top_next.eq(self.top),

        rsp_next = Signal(16)
        with m.Switch(self.op_rsp):
            with m.Case(PrimOpcodes.SP_INC):
                m.d.comb += rsp_next.eq(self.rsp + 1)
            with m.Case(PrimOpcodes.SP_DEC):
                m.d.comb += rsp_next.eq(self.rsp - 1)
            with m.Default():
                pass

        src = Signal(16)
        with m.Switch(self.op_src):
            with m.Case(PrimOpcodes.SD_ALU):
                m.d.comb += src.eq(self.alu_out(m, self.ir))
            with m.Case(PrimOpcodes.SD_D0):
                m.d.comb += src.eq(self.top)
            with m.Case(PrimOpcodes.SD_R0):
                m.d.comb += src.eq(self.rstack_rp.data)
            with m.Case(PrimOpcodes.SD_AR):
                m.d.comb += src.eq(self.areg)
            with m.Case(PrimOpcodes.SD_M_A):
                m.d.comb += [
                    src.eq(self.data_in),
                    self.addr.eq(self.areg)
                ]
            with m.Case(PrimOpcodes.SD_M_PC):
                m.d.comb += [
                    src.eq(self.data_in),
                    self.addr.eq(self.pc)
                ]
            with m.Case(PrimOpcodes.SD_PC):
                pass
            with m.Default():
                pass

        with m.Switch(self.op_dst):
            with m.Case(PrimOpcodes.SD_D0):
                m.d.comb += [
                    top_next.eq(src),
                ]
            with m.Case(PrimOpcodes.SD_R0):
                m.d.comb += [
                    self.rstack_wp.data.eq(src),
                    self.rstack_wp.en.eq(1)
                ]
            with m.Case(PrimOpcodes.SD_AR):
                m.d.sync += self.areg.eq(src)
            with m.Case(PrimOpcodes.SD_M_A):
                m.d.comb += [
                    self.addr.eq(self.areg),
                    self.we.eq(1),
                    self.cs.eq(1),
                ]
            with m.Case(PrimOpcodes.SD_M_PC):
                m.d.comb += [
                    self.addr.eq(self.pc),
                    self.we.eq(1),
                    self.cs.eq(1),
                ]
            with m.Case(PrimOpcodes.SD_PC):
                m.d.comb += [
                    pc_next.eq(self.dstack_rp.data),
                ]
            with m.Default():
                pass

        if write:
            m.d.sync += [
                self.dsp.eq(dsp_next),
                self.rsp.eq(rsp_next),
                self.pc.eq(pc_next),
                self.top.eq(top_next),
            ]

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
        mem = [PrimOpcodes.simend()]*0x10000
        for i in range(len(init)):
            mem[i] = init[i]
            print(f"{mem[i]:04x} ", end="")
        print()
        return mem

    dut = Prim()
    sim = Simulator(dut)
    sim.add_clock(Period(MHz=1))


    def memory_access(ctx, td):
        if ctx.get(dut.cs) > 0:
            dut.mem_cycle += 1
            ctx.set(dut.data_in, 0)
            if dut.mem_cycle > 1:
                addr = ctx.get(dut.addr)
                assert(addr < len(dut.mem)), f"Memory access out of bounds 0x{addr:x}"
                value = dut.mem[addr]
                ctx.set(dut.data_in, value)
                dut.mem_cycle = 0

    def test(td):
        print(td["name"])
        sim.reset()
        dut.mem_cycle = 0
        dut.mem = mem_create(init=td["mem-init"])
        async def bench(ctx):
            while ctx.get(dut.ir) != PrimOpcodes.simend():
                memory_access(ctx, td)
                await ctx.tick()
            for i in range(8):
                print(f"{ctx.get(dut.dstack.data[i])}")

            top = ctx.get(dut.top)
            dsp = ctx.get(dut.dsp)
            ds = [top] +  [ctx.get(dut.dstack.data[(dsp-i-1)%dut.dstack_depth]) for i in range(dut.dstack_depth)]
            rsp = ctx.get(dut.rsp)
            rs = [ctx.get(dut.rstack.data[(rsp-i-1)%dut.rstack_depth]) for i in range(dut.rstack_depth)]

            assert (not "dsp" in td) or (dsp == td["dsp"]), f"dsp has wrong value {dsp:x} instead of {td["dsp"]:x}"

            if "ds" in td:
                for i in range(len(td["ds"])):
                    assert ds[i] == td["ds"][i]

            if "rs" in td:
                for i in range(len(td["rs"])):
                    assert rs[i] == td["rs"][i]
            if "mem" in td:
                (addr, m) = (td["mem"][0], td["mem"][1:])
                for i,w in enumerate(m):
                    pass


        sim.add_testbench(bench)
        try:
            sim.run()
        except:
            sim.reset()
            with sim.write_vcd(f"{td["name"]}.vcd", gtkw_file=f"{td["name"]}.gtkw", traces=[dut.addr, dut.cs, dut.data_out, dut.data_in, dut.top]):
                sim.run()

    td = {
        "name": "push",
        "mem-init": [PrimOpcodes.push(100+i) for i in range(0,dut.dstack_depth+1)],
        "dsp": 1,
        "ds": [106, 105, 104, 103, 102, 101, 100],
    }
    test(td)
#    with open("prim.v", "w") as f:
#        f.write(verilog.convert(dut, ports=[dut.data_in, dut.data_out, dut.addr, dut.we, dut.cs]))


if __name__ == "__main__":
    main()
