// FFFD: LEDs (bits 1:0); FFFE: UART status (RO); FFFF: RX/TX data.
// Other lanes retain SRAM word/unaligned/wrapping semantics. Effects occur at ACK.
module memory_io #(
    parameter integer READ_CYCLES = 2,
    parameter integer WRITE_CYCLES = 2
)(
    input i_clk, i_reset,
    input [15:0] i_addr, i_cpu_to_mem,
    input [1:0] i_bs,
    input i_we,
    output [15:0] o_mem_to_cpu,
    output o_ack,
    output [6:0] o_output_data,
    output o_output_valid,
    input i_output_ready,
    input [6:0] i_input_data,
    input [1:0] i_uart_status,
    output o_input_read,
    output reg [1:0] o_leds,
    output [15:0] ram_addr,
    inout [15:0] ram_data,
    output ram_cs_n, ram_oe_n, ram_we_n
);
wire mmio_low = i_bs[0] && (i_addr >= 16'hfffd);
wire mmio_high = i_bs[1] && (i_addr >= 16'hfffc && i_addr <= 16'hfffe);
wire [1:0] ram_mask = {i_bs[1] && !mmio_high, i_bs[0] && !mmio_low};
wire mmio_access = mmio_low || mmio_high;
wire ram_access = |ram_mask;
wire split = mmio_access && ram_access;
reg second;
// Finish a mixed SRAM lane first; all UART effects occur on the final ACK.
wire mmio_turn = mmio_access && (!split || second);
wire ram_turn = ram_access && !mmio_turn;
wire rx_low = mmio_low && i_addr == 16'hffff;
wire rx_high = mmio_high && i_addr == 16'hfffe;
wire led_low = mmio_low && i_addr == 16'hfffd;
wire led_high = mmio_high && i_addr == 16'hfffc;
wire tx_access = i_we && (rx_low || rx_high);
wire ram_ack;
wire [15:0] ram_read, ram_result;
// memory's BS=10 lane formatting is combinational. Once its request is
// deasserted for the MMIO phase, its retained byte is again in bits 7:0.
assign ram_read = !ram_turn && ram_mask == 2'b10 ? {ram_result[7:0],8'b0} : ram_result;
wire complete = mmio_turn ? (!tx_access || i_output_ready) : (ram_turn && ram_ack);
assign o_ack = !i_reset && complete && (!split || second);
assign o_output_data = rx_low ? i_cpu_to_mem[6:0] : i_cpu_to_mem[14:8];
assign o_output_valid = !i_reset && mmio_turn && tx_access;
assign o_input_read = o_ack && !i_we && (rx_low || rx_high);
wire [7:0] low_read = mmio_low ? (led_low ? {6'b0,o_leds} : rx_low ? {1'b0,i_input_data} : {6'b0,i_uart_status}) : ram_read[7:0];
wire [7:0] high_read = mmio_high ? (led_high ? {6'b0,o_leds} : rx_high ? {1'b0,i_input_data} : {6'b0,i_uart_status}) : ram_read[15:8];
assign o_mem_to_cpu = {i_bs[1] ? high_read : 8'b0, i_bs[0] ? low_read : 8'b0};
always @(posedge i_clk) begin
    if (i_reset) o_leds <= 0;
    else if (o_ack && i_we) begin
        if (led_low) o_leds <= i_cpu_to_mem[1:0];
        else if (led_high) o_leds <= i_cpu_to_mem[9:8];
    end
    if (i_reset) second <= 0;
    else if (complete) second <= split && !second;
end
memory #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES)) sram(
    .i_clk(i_clk), .i_reset(i_reset), .i_addr(i_addr), .i_cpu_to_mem(i_cpu_to_mem),
    .i_bs(ram_turn ? ram_mask : 2'b00), .i_we(i_we), .o_mem_to_cpu(ram_result), .o_ack(ram_ack),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(ram_cs_n),
    .ram_oe_n(ram_oe_n), .ram_we_n(ram_we_n));
endmodule
