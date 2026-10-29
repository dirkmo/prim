`timescale 1ns/1ps
module tb_uart_arbiter;
reg clk=0, reset=1;
always #5 clk=~clk;
reg [7:0] debug_data=8'hcb;
reg [6:0] output_data=7'h41;
reg debug_valid=0, output_valid=0;
wire debug_ready, output_ready, ready, valid, tx;
wire [7:0] data;
uart_arbiter arbiter(.i_debug_data(debug_data), .i_debug_valid(debug_valid), .o_debug_ready(debug_ready),
    .i_output_data(output_data), .i_output_valid(output_valid), .o_output_ready(output_ready),
    .o_data(data), .o_valid(valid), .i_ready(ready));
uart_tx #(.CLKS_PER_BIT(4)) uart(.i_clk(clk), .i_reset(reset), .i_data(data),
    .i_valid(valid), .o_ready(ready), .o_tx(tx));
integer count=0;
reg [7:0] received;
always begin
    @(negedge tx); repeat(2) @(negedge clk);
    for(integer k=0;k<8;k=k+1) begin repeat(4) @(negedge clk); received[k]=tx; end
    repeat(4) @(negedge clk);
    if(tx!==1) $fatal(1,"stop bit");
    case(count)
        0: if(received!=8'h41) $fatal(1,"in-progress frame interrupted");
        1: if(received!=8'hcb) $fatal(1,"debug priority");
        2: if(received!=8'h42) $fatal(1,"CPU output lost");
        default: $fatal(1,"duplicate frame");
    endcase
    count=count+1;
end
initial begin
    repeat(3) @(negedge clk); reset=0; output_valid=1;
    @(negedge clk); output_valid=0;
    // Start a debug request while a CPU frame is still on the wire.
    repeat(5) @(negedge clk);
    debug_valid=1; output_valid=1; output_data=7'h42;
    #1; if(debug_ready || output_ready) $fatal(1,"backpressure missing");
    wait(debug_ready); #1;
    if(output_ready || data!=8'hcb) $fatal(1,"priority handshake");
    @(posedge clk); @(negedge clk); debug_valid=0;
    wait(output_ready); @(posedge clk); @(negedge clk); output_valid=0;
    wait(count==3); repeat(50) @(negedge clk);
    $display("PASS UART arbiter"); $finish;
end
initial begin #10000; $fatal(1,"timeout"); end
endmodule
