`timescale 1ns/1ps
module tb_timer_divider;
parameter integer DIVISOR = 50000;
localparam integer DIV = DIVISOR;
reg clk = 0, reset = 1, cs = 0, we = 0;
reg [1:0] addr = 0;
reg [15:0] wdata = 0;
wire [15:0] rdata;
wire irq;
integer n;
timer #(.DIVISOR(DIVISOR)) dut (
    .i_clk(clk), .i_reset(reset), .i_cs(cs), .i_we(we), .i_addr(addr),
    .i_be(2'b11), .i_wdata(wdata), .o_rdata(rdata), .o_irq(irq));

task cycle;
begin
    #5; clk = 1; #5; clk = 0;
end
endtask

task expect_state(input [15:0] count, input irq_value);
begin
    if (rdata !== count || irq !== irq_value)
        $fatal(1, "divisor=%0d cycle=%0d COUNT=%0d IRQ=%b expected %0d/%b",
               DIVISOR, n, rdata, irq, count, irq_value);
end
endtask

initial begin
    cycle(); reset = 0;
    cs = 1; we = 1; addr = 1; wdata = 2; cycle();
    addr = 2; wdata = 5; cycle();
    we = 0; addr = 0;
    // Exact first/second interval boundary and one-system-clock IRQ.
    for (n = 1; n <= 2*DIV+2; n = n + 1) begin
        cycle();
        if (n < DIV) expect_state(0, 0);
        else if (n < 2*DIV) expect_state(1, 0);
        else expect_state(2, n == 2*DIV);
    end
    // Reset COUNT=0 mid-divider; next tick must be one full interval away.
    we = 1; wdata = 0; cycle(); we = 0;
    for (n = 1; n <= DIV; n = n + 1) begin
        cycle(); expect_state(n == DIV ? 16'd1 : 16'd0, 0);
    end
    $display("PASS timer divider DIVISOR=%0d", DIVISOR);
    $finish;
end
endmodule
