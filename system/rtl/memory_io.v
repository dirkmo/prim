// FFF0..FFF5: timer; FFF6..FFFC: reserved; FFFD: LEDs; FFFE/FFFF: UART.
// Other lanes retain SRAM word/unaligned/wrapping semantics.
// LED/UART effects occur at ACK; cross-register timer words use two phases.
module memory_io_core #(
    parameter integer READ_CYCLES = 2,
    parameter integer WRITE_CYCLES = 2,
    parameter integer TIMER_DIVISOR = 50000
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
    input [3:0] i_uart_csr,
    output [7:0] o_uart_csr_data,
    output o_uart_csr_write,
    output o_input_read,
    output reg [1:0] o_leds,
    output o_timer_irq,
    output [15:0] ram_addr,
    inout [15:0] ram_data,
    output ram_cs_n, ram_oe_n, ram_we_n
);
wire [15:0] next_addr = i_addr + 16'd1;
wire mmio_low = i_bs[0] && i_addr[15:4] == 12'hfff;
wire mmio_high = i_bs[1] && next_addr[15:4] == 12'hfff;
wire timer_low = mmio_low && i_addr[3:0] <= 5;
wire timer_high = mmio_high && next_addr[3:0] <= 5;
wire timer_access = timer_low || timer_high;
wire timer_ack;
wire [15:0] timer_read;
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
wire csr_low = mmio_low && i_addr == 16'hfffe;
wire csr_high = mmio_high && next_addr == 16'hfffe;
wire led_low = mmio_low && i_addr == 16'hfffd;
wire led_high = mmio_high && i_addr == 16'hfffc;
wire tx_access = i_we && (rx_low || rx_high);
wire ram_ack;
wire [15:0] ram_read, ram_result;
// memory's BS=10 lane formatting is combinational. Once its request is
// deasserted for the MMIO phase, its retained byte is again in bits 7:0.
assign ram_read = !ram_turn && ram_mask == 2'b10 ? {ram_result[7:0],8'b0} : ram_result;
wire complete = mmio_turn ? (timer_access ? timer_ack : (!tx_access || i_output_ready)) : (ram_turn && ram_ack);
assign o_ack = !i_reset && complete && (!split || second);
assign o_output_data = rx_low ? i_cpu_to_mem[6:0] : i_cpu_to_mem[14:8];
assign o_output_valid = !i_reset && mmio_turn && tx_access;
assign o_uart_csr_data = csr_low ? i_cpu_to_mem[7:0] : i_cpu_to_mem[15:8];
assign o_uart_csr_write = o_ack && i_we && (csr_low || csr_high);
assign o_input_read = o_ack && !i_we && (rx_low || rx_high);
function [7:0] peripheral_read;
    input [3:0] address;
    input [1:0] leds;
    input [3:0] csr;
    input [6:0] data;
    begin
        case (address)
            4'hd: peripheral_read = {6'b0,leds};
            4'he: peripheral_read = {4'b0,csr};
            4'hf: peripheral_read = {1'b0,data};
            default: peripheral_read = 0;
        endcase
    end
endfunction
wire [7:0] low_read = mmio_low ? (timer_low ? timer_read[7:0] : peripheral_read(i_addr[3:0], o_leds, i_uart_csr, i_input_data)) : ram_read[7:0];
wire [7:0] high_read = mmio_high ? (timer_high ? timer_read[15:8] : peripheral_read(next_addr[3:0], o_leds, i_uart_csr, i_input_data)) : ram_read[15:8];
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
timer_mmio #(.DIVISOR(TIMER_DIVISOR)) timer_bus(
    .i_clk(i_clk), .i_reset(i_reset), .i_cs(mmio_turn && timer_access),
    .i_we(i_we), .i_addr(i_addr), .i_wdata(i_cpu_to_mem), .i_bs(i_bs),
    .o_rdata(timer_read), .o_ack(timer_ack), .o_irq(o_timer_irq));
memory #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES)) sram(
    .i_clk(i_clk), .i_reset(i_reset), .i_addr(i_addr), .i_cpu_to_mem(i_cpu_to_mem),
    .i_bs(ram_turn ? ram_mask : 2'b00), .i_we(i_we), .o_mem_to_cpu(ram_result), .o_ack(ram_ack),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(ram_cs_n),
    .ram_oe_n(ram_oe_n), .ram_we_n(ram_we_n));
endmodule

// Optional VGA banking wraps the existing bus without changing ordinary SRAM,
// timer or UART transactions. Only words touching VGA are split into bytes.
module memory_io #(
    parameter integer READ_CYCLES = 2,
    parameter integer WRITE_CYCLES = 2,
    parameter integer TIMER_DIVISOR = 50000,
    parameter integer VGA_ENABLE = 0
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
    input [3:0] i_uart_csr,
    output [7:0] o_uart_csr_data,
    output o_uart_csr_write, o_input_read,
    output [1:0] o_leds,
    output o_timer_irq,
    output [15:0] ram_addr,
    inout [15:0] ram_data,
    output ram_cs_n, ram_oe_n, ram_we_n,
    output o_vga_hsync, o_vga_vsync, o_vga_pixel, o_vga_active
);
wire [15:0] core_addr, core_wdata, core_rdata;
wire [1:0] core_bs;
wire core_ack;
generate if (VGA_ENABLE) begin: video
    wire bank;
    wire [15:0] next_addr = i_addr + 16'd1;
    wire reg_lo = i_addr >= 16'hfff6 && i_addr <= 16'hfffa;
    wire reg_hi = next_addr >= 16'hfff6 && next_addr <= 16'hfffa;
    wire ram_lo = bank && i_addr[15:12] == 4'he;
    wire ram_hi = bank && next_addr[15:12] == 4'he;
    wire split = (i_bs[0] && (reg_lo || ram_lo)) ||
                 (i_bs[1] && (reg_hi || ram_hi));
    reg second;
    reg [7:0] low_data;
    wire high_lane = second || !i_bs[0];
    wire [15:0] address = high_lane ? next_addr : i_addr;
    wire [7:0] wdata = high_lane ? i_cpu_to_mem[15:8] : i_cpu_to_mem[7:0];
    wire reg_sel = high_lane ? reg_hi : reg_lo;
    wire ram_sel = high_lane ? ram_hi : ram_lo;
    wire selected = !i_reset && split && (|i_bs);
    wire [7:0] reg_data, video_data;
    wire video_ack;
    wire byte_ack = reg_sel ? 1'b1 : ram_sel ? video_ack : core_ack;
    wire [7:0] byte_data = reg_sel ? reg_data : ram_sel ? video_data : core_rdata[7:0];
    wire last = high_lane || !i_bs[1];
    assign core_addr = split ? address : i_addr;
    assign core_wdata = split ? {8'b0,wdata} : i_cpu_to_mem;
    assign core_bs = split ? ((selected && !reg_sel && !ram_sel) ? 2'b01 : 2'b00) : i_bs;
    assign o_ack = split ? (selected && last && byte_ack) : core_ack;
    assign o_mem_to_cpu = split ?
        {i_bs[1] ? byte_data : 8'b0, i_bs[0] ? (second ? low_data : byte_data) : 8'b0} : core_rdata;
    always @(posedge i_clk) begin
        if (i_reset) second <= 0;
        else if (selected && byte_ack) begin
            second <= !last;
            if (!high_lane) low_data <= byte_data;
        end
    end
    vga_text display(
        .i_clk(i_clk), .i_reset(i_reset), .i_cs(selected && ram_sel),
        .i_we(i_we), .i_addr(address[11:0]), .i_data(wdata),
        .o_data(video_data), .o_ack(video_ack),
        .i_reg_cs(selected && reg_sel), .i_reg_addr(address[2:0] - 3'd6),
        .o_reg_data(reg_data), .o_bank(bank),
        .o_hsync(o_vga_hsync), .o_vsync(o_vga_vsync),
        .o_pixel(o_vga_pixel), .o_active(o_vga_active));
end else begin: no_video
    assign core_addr = i_addr;
    assign core_wdata = i_cpu_to_mem;
    assign core_bs = i_bs;
    assign o_mem_to_cpu = core_rdata;
    assign o_ack = core_ack;
    assign o_vga_hsync = 1;
    assign o_vga_vsync = 1;
    assign o_vga_pixel = 0;
    assign o_vga_active = 0;
end endgenerate
memory_io_core #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES),
    .TIMER_DIVISOR(TIMER_DIVISOR)) core(
    .i_clk(i_clk), .i_reset(i_reset), .i_addr(core_addr), .i_cpu_to_mem(core_wdata),
    .i_bs(core_bs), .i_we(i_we), .o_mem_to_cpu(core_rdata), .o_ack(core_ack),
    .o_output_data(o_output_data), .o_output_valid(o_output_valid),
    .i_output_ready(i_output_ready), .i_input_data(i_input_data), .i_uart_csr(i_uart_csr),
    .o_uart_csr_data(o_uart_csr_data), .o_uart_csr_write(o_uart_csr_write),
    .o_input_read(o_input_read), .o_leds(o_leds), .o_timer_irq(o_timer_irq),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(ram_cs_n),
    .ram_oe_n(ram_oe_n), .ram_we_n(ram_we_n));
endmodule
