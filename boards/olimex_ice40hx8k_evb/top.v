// Olimex iCE40HX8K-EVB Rev.B, 100 MHz oscillator, 3.3 V UART.
module olimex_ice40hx8k_evb(
    input clk_100mhz,
    input button_n,
    input uart_rx,
    input ps2_clk, ps2_data,
    output uart_tx,
    output vga_hsync, vga_vsync,
    output [2:0] vga_red, vga_green, vga_blue,
    output [1:0] leds,
    output [17:0] sram_addr,
    inout [15:0] sram_data,
    output sram_cs_n, sram_oe_n, sram_we_n
);
// icepll -i 100 -o 25: PFD=100 MHz, VCO=800 MHz, output=25 MHz.
// The PLL's global output is the only clock used by CPU/UART/SRAM logic.
wire clk_sys, pll_locked;
SB_PLL40_CORE #(
    .FEEDBACK_PATH("SIMPLE"), .DIVR(4'd0), .DIVF(7'd7), .DIVQ(3'd5),
    .FILTER_RANGE(3'd5)
) pll(.REFERENCECLK(clk_100mhz), .PLLOUTGLOBAL(clk_sys), .LOCK(pll_locked),
      .RESETB(1'b1), .BYPASS(1'b0));

// iCE40 configuration initializes these flops. Release reset only after LOCK
// crosses two synchronizer stages and the reset pipe has drained.
(* async_reg = "true" *) reg [1:0] lock_sync = 0;
(* async_reg = "true" *) reg [1:0] button_sync = 0;
reg [3:0] reset_pipe = 4'hf;
wire reset = |reset_pipe;
always @(posedge clk_sys) begin
    lock_sync <= {lock_sync[0], pll_locked};
    button_sync <= {button_sync[0], button_n};
    if (!lock_sync[1]) reset_pipe <= 4'hf;
    else reset_pipe <= {reset_pipe[2:0], !button_sync[1]};
end
wire [15:0] ram_addr;
wire pixel;
// Drive every DAC bit on iCE40-IO Rev.A: monochrome black or full white.
assign vga_red = {3{pixel}};
assign vga_green = {3{pixel}};
assign vga_blue = {3{pixel}};
assign sram_addr = {2'b00, ram_addr};
prim_system #(.CLK_HZ(25000000), .READ_CYCLES(3), .WRITE_CYCLES(3), .START_HALTED(1),
              .TIMER_DIVISOR(25000), .VGA_ENABLE(1), .PS2_ENABLE(1)) system(
    .i_clk(clk_sys), .i_reset(reset), .i_rx(uart_rx), .o_tx(uart_tx), .o_leds(leds),
    .i_ps2_clk(ps2_clk), .i_ps2_data(ps2_data),
    .o_vga_hsync(vga_hsync), .o_vga_vsync(vga_vsync), .o_vga_pixel(pixel),
    .ram_addr(ram_addr), .ram_data(sram_data), .ram_cs_n(sram_cs_n),
    .ram_oe_n(sram_oe_n), .ram_we_n(sram_we_n));
endmodule
