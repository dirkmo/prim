// Pin-independent CPU + SRAM controller + shared CPU/debug UART.
module prim_system #(
    parameter integer CLK_HZ = 100000000,
    parameter integer READ_CYCLES = 2,
    parameter integer WRITE_CYCLES = 2
)(
    input i_clk,
    input i_reset,
    input i_rx,
    output o_tx,
    output [15:0] ram_addr,
    inout [15:0] ram_data,
    output ram_cs_n,
    output ram_oe_n,
    output ram_we_n
);
localparam integer BAUD = 115200;
wire [15:0] addr, to_mem, from_mem, cpu_addr, cpu_data, debug_addr, debug_data, pc;
wire [1:0] bs, cpu_bs, debug_bs;
wire we, ack, cpu_we, debug_we, halted, halt_request, run_request, step_request, reset_cpu;
wire break_reason, break_event, rx_valid, tx_valid, tx_ready;
wire [7:0] rx_data, tx_data;
assign addr = halted ? debug_addr : cpu_addr;
assign to_mem = halted ? debug_data : cpu_data;
assign bs = halted ? debug_bs : cpu_bs;
assign we = halted ? debug_we : cpu_we;
Prim cpu(.i_clk(i_clk), .i_reset(i_reset), .o_addr(cpu_addr), .o_dat(cpu_data),
         .i_dat(from_mem), .o_bs(cpu_bs), .o_we(cpu_we), .i_ack(ack && !halted), .i_irq(1'b0),
         .i_halt(halt_request), .i_run(run_request), .i_step(step_request),
         .i_debug_reset(reset_cpu), .o_halted(halted), .o_pc(pc),
         .o_break_reason(break_reason), .o_break_event(break_event));
uart_rx #(.CLKS_PER_BIT((CLK_HZ + BAUD/2) / BAUD)) rx(
    .i_clk(i_clk), .i_reset(i_reset), .i_rx(i_rx), .o_data(rx_data), .o_valid(rx_valid));
debug_uart debug(.i_clk(i_clk), .i_reset(i_reset), .i_rx_data(rx_data), .i_rx_valid(rx_valid),
    .o_tx_data(tx_data), .o_tx_valid(tx_valid), .i_tx_ready(tx_ready),
    .o_halt(halt_request), .o_run(run_request), .o_step(step_request), .o_reset_cpu(reset_cpu),
    .i_halted(halted), .i_break_reason(break_reason), .i_break_event(break_event), .i_pc(pc),
    .o_addr(debug_addr), .o_data(debug_data), .o_bs(debug_bs), .o_we(debug_we),
    .i_ack(ack && halted), .i_data(from_mem));
memory_io #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES),
            .CLKS_PER_BIT((CLK_HZ + BAUD/2) / BAUD)) io(
    .i_clk(i_clk), .i_reset(i_reset), .i_addr(addr), .i_cpu_to_mem(to_mem),
    .i_debug_valid(tx_valid), .i_debug_data(tx_data), .o_debug_ready(tx_ready),
    .i_bs(bs), .i_we(we), .o_mem_to_cpu(from_mem), .o_ack(ack), .o_tx(o_tx),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(ram_cs_n),
    .ram_oe_n(ram_oe_n), .ram_we_n(ram_we_n));
endmodule
