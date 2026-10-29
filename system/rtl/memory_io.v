// SRAM plus write-only UART mapping at byte address FFFF, matching tokenforth.Mif.
// Reads (including FFFF) still read SRAM. Split crossing writes in byte order.
module memory_io #(
    parameter integer READ_CYCLES = 2,
    parameter integer WRITE_CYCLES = 2
)(
    input i_clk,
    input i_reset,
    input [15:0] i_addr,
    input [15:0] i_cpu_to_mem,
    input [1:0] i_bs,
    input i_we,
    output [15:0] o_mem_to_cpu,
    output o_ack,
    output [6:0] o_output_data,
    output o_output_valid,
    input i_output_ready,
    output [15:0] ram_addr,
    inout [15:0] ram_data,
    output ram_cs_n,
    output ram_oe_n,
    output ram_we_n
);
wire uart_low = i_we && i_bs[0] && (i_addr == 16'hffff);
wire uart_high = i_we && i_bs[1] && (i_addr == 16'hfffe);
wire uart_access = uart_low || uart_high;
wire ram_access = (i_bs[0] && !uart_low) || (i_bs[1] && !uart_high);
wire split = uart_access && ram_access;
reg second;
wire uart_turn = uart_access && (!split || (second ? uart_high : uart_low));
wire ram_turn = ram_access && !uart_turn;
wire ram_ack;
assign o_output_data = uart_low ? i_cpu_to_mem[6:0] : i_cpu_to_mem[14:8];
assign o_output_valid = !i_reset && uart_turn;
wire complete = uart_turn ? i_output_ready : (ram_turn && ram_ack);
assign o_ack = !i_reset && complete && (!split || second);

always @(posedge i_clk) begin
    if (i_reset)
        second <= 0;
    else if (complete)
        second <= split && !second;
end

// For a split FFFF word write the RAM byte is the high lane, at address zero.
memory #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES)) sram(
    .i_clk(i_clk), .i_reset(i_reset),
    .i_addr(split && uart_low ? 16'h0000 : i_addr),
    .i_cpu_to_mem(split && uart_low ? {8'h00, i_cpu_to_mem[15:8]} : i_cpu_to_mem),
    .i_bs(ram_turn ? (split ? 2'b01 : i_bs) : 2'b00),
    .i_we(i_we), .o_mem_to_cpu(o_mem_to_cpu), .o_ack(ram_ack),
    .ram_addr(ram_addr), .ram_data(ram_data),
    .ram_cs_n(ram_cs_n), .ram_oe_n(ram_oe_n), .ram_we_n(ram_we_n));
endmodule
