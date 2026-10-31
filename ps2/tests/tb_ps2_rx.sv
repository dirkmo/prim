`timescale 1ns/1ps
module tb_ps2_rx;
parameter FILTER=8;
localparam HALF=FILTER+12;
reg clk=0, reset=1, psclk=1, psdata=1;
always #5 clk=~clk;
wire [7:0] data;
wire valid, error;
integer received=0, errors=0;
reg [7:0] last;
ps2_rx #(.FILTER_CYCLES(FILTER), .TIMEOUT_CYCLES(300)) dut(
    .i_clk(clk), .i_reset(reset), .i_ps2_clk(psclk), .i_ps2_data(psdata),
    .o_data(data), .o_valid(valid), .o_error(error));
always @(posedge clk) if (!reset) begin
    if (valid) begin last=data; received=received+1; end
    if (error) errors=errors+1;
end
task bit_send(input bit value);
    psdata=value;
    #(HALF*10+3); psclk=0;
    #(HALF*10+1); psclk=1;
endtask
task frame(input [7:0] value, input bit bad_parity, input bit bad_stop);
    bit_send(0);
    for(integer j=0;j<8;j=j+1) bit_send(value[j]);
    bit_send((~^value)^bad_parity); bit_send(!bad_stop);
    psdata=1; #(HALF*10+7);
endtask
integer saved, saved_errors;
initial begin
    repeat(4) @(negedge clk); reset=0;
    // Every byte, with non-clock-aligned transitions and immediate next frames.
    for(integer value=0;value<256;value=value+1) begin
        frame(value,0,0);
        if(received!=value+1 || last!==value[7:0] || errors)
            $fatal(1,"byte/order/phase value=%h got=%h count=%0d errors=%0d",value,last,received,errors);
    end
    saved=received;
    frame(8'h5a,1,0); frame(8'ha5,0,1);
    if(received!=saved || errors!=2) $fatal(1,"bad parity/stop accepted");
    // High data is not a start bit.
    bit_send(1); #(4000);
    if(received!=saved || errors!=2) $fatal(1,"invalid start");
    bit_send(0); bit_send(1); psdata=1; #(4000);
    if(errors!=3 || received!=saved) $fatal(1,"partial frame timeout");
    // Short clock pulse must not advance an in-progress frame.
    bit_send(0);
    #(13); psclk=0;
    if(FILTER>1) #((FILTER-1)*10); else #1;
    psclk=1; #(HALF*20);
    for(integer j=0;j<8;j=j+1) bit_send((8'hc3 >> j)&1);
    bit_send(~^8'hc3); bit_send(1); psdata=1; #(HALF*20);
    if(last!==8'hc3 || received!=saved+1 || errors!=3) $fatal(1,"glitch/recovery");
    // Reset halfway through a frame discards it without a stale pulse.
    bit_send(0); bit_send(0);
    @(negedge clk); reset=1; psclk=1; psdata=1;
    repeat(4) @(negedge clk); reset=0;
    saved_errors=errors;
    frame(0,0,0);
    if(last!==0 || received!=saved+2 || errors!=saved_errors) $fatal(1,"reset/recovery");
    $display("PASS PS/2 receiver FILTER=%0d",FILTER); $finish;
end
initial begin #20000000; $fatal(1,"receiver timeout"); end
endmodule
