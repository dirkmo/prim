// Pin-independent CPU + SRAM controller + UART-TX integration.
module prim_system #(
    parameter integer CLK_HZ = 100000000,
    parameter integer BAUD = 115200,
    parameter integer READ_CYCLES = 2,
    parameter integer WRITE_CYCLES = 2
)(
    input i_clk,
    input i_reset,
    output o_tx,
    output [15:0] ram_addr,
    inout [15:0] ram_data,
    output ram_cs_n,
    output ram_oe_n,
    output ram_we_n
);
wire [15:0] addr, to_mem, from_mem;
wire [1:0] bs;
wire we, ack;
Prim cpu(.i_clk(i_clk), .i_reset(i_reset), .o_addr(addr), .o_dat(to_mem),
         .i_dat(from_mem), .o_bs(bs), .o_we(we), .i_ack(ack), .i_irq(1'b0));
memory_io #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES),
            .CLKS_PER_BIT((CLK_HZ + BAUD/2) / BAUD)) io(
    .i_clk(i_clk), .i_reset(i_reset), .i_addr(addr), .i_cpu_to_mem(to_mem),
    .i_bs(bs), .i_we(we), .o_mem_to_cpu(from_mem), .o_ack(ack), .o_tx(o_tx),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(ram_cs_n),
    .ram_oe_n(ram_oe_n), .ram_we_n(ram_we_n));
endmodule
