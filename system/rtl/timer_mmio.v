// Adapt byte-addressed CPU lanes at FFF0..FFF5 to the timer's word registers.
// Odd words spanning two registers use two phases, lower address first.
module timer_mmio #(
    parameter integer DIVISOR = 50000
)(
    input i_clk, i_reset, i_cs, i_we,
    input [15:0] i_addr, i_wdata,
    input [1:0] i_bs,
    output [15:0] o_rdata,
    output o_ack, o_irq
);
wire [15:0] next_addr = i_addr + 16'd1;
wire low_sel = i_bs[0] && i_addr[15:4] == 12'hfff && i_addr[3:0] <= 5;
wire high_sel = i_bs[1] && next_addr[15:4] == 12'hfff && next_addr[3:0] <= 5;
wire split = low_sel && high_sel && i_addr[2:1] != next_addr[2:1];
reg second;
reg [7:0] first_read;
wire low_active = low_sel && (!split || !second);
wire high_active = high_sel && (!split || second);
wire [1:0] reg_addr = low_active ? i_addr[2:1] : next_addr[2:1];
wire [1:0] reg_be = { (low_active && i_addr[0]) || (high_active && next_addr[0]),
                      (low_active && !i_addr[0]) || (high_active && !next_addr[0]) };
wire [15:0] reg_wdata = {
    low_active && i_addr[0] ? i_wdata[7:0] : i_wdata[15:8],
    low_active && !i_addr[0] ? i_wdata[7:0] : i_wdata[15:8] };
wire [15:0] reg_rdata;
wire [7:0] low_read = i_addr[0] ? reg_rdata[15:8] : reg_rdata[7:0];
wire [7:0] high_read = next_addr[0] ? reg_rdata[15:8] : reg_rdata[7:0];
assign o_rdata = {high_sel ? high_read : 8'b0,
                 low_sel ? (split && second ? first_read : low_read) : 8'b0};
assign o_ack = !i_reset && i_cs && (low_sel || high_sel) && (!split || second);

always @(posedge i_clk) begin
    if (i_reset) second <= 0;
    else if (i_cs) second <= split && !second;
    if (i_cs && split && !second) first_read <= low_read;
end
timer #(.DIVISOR(DIVISOR)) counter(
    .i_clk(i_clk), .i_reset(i_reset), .i_cs(i_cs && (low_sel || high_sel)),
    .i_we(i_we), .i_addr(reg_addr), .i_be(reg_be), .i_wdata(reg_wdata),
    .o_rdata(reg_rdata), .o_irq(o_irq));
endmodule
