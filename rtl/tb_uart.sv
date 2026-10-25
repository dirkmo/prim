`timescale 1ns/1ps
module tb_uart;
parameter integer CLKS_PER_BIT = 4;
reg clk=0, reset=1, valid=0;
always #5 clk=~clk;
reg [7:0] data;
wire ready, tx;
uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) dut(
    .i_clk(clk), .i_reset(reset), .i_data(data), .i_valid(valid), .o_ready(ready), .o_tx(tx));

task send(input [7:0] value);
    integer cycle;
    reg [9:0] expected;
    begin
        @(negedge clk);
        if (!ready) $fatal(1, "UART not ready before send");
        data=value; valid=1;
        @(posedge clk); #1;
        valid=0; data=~value; // Data must have been latched on acceptance.
        expected={1'b1, value, 1'b0};
        for(cycle=0; cycle<10*CLKS_PER_BIT; cycle=cycle+1) begin
            if (tx !== expected[cycle/CLKS_PER_BIT] || ready !== 0)
                $fatal(1, "UART framing/timing error byte=%h cycle=%0d", value, cycle);
            @(posedge clk); #1;
        end
        if (!ready || !tx) $fatal(1, "UART not idle after stop bit");
    end
endtask
integer i;
initial begin
    repeat(2) @(negedge clk);
    reset=0;
    for(i=0; i<256; i=i+1) send(i);
    // Reset aborts a frame and immediately restores idle-high TX.
    @(negedge clk); data=0; valid=1;
    @(posedge clk); #1; valid=0;
    @(negedge clk); reset=1;
    #1;
    if (tx !== 1 || ready !== 0) $fatal(1, "Invalid UART reset outputs");
    repeat(2) @(negedge clk);
    reset=0;
    send(8'h55);
    $display("PASS UART all bytes, timing and reset, divider=%0d", CLKS_PER_BIT);
    $finish;
end
endmodule
