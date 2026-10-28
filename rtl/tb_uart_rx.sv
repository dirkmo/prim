`timescale 1ns/1ps
module tb_uart_rx;
parameter integer DIV=8;
reg clk=0, reset=1, rx=1;
always #5 clk=~clk;
wire [7:0] data;
wire valid;
uart_rx #(.CLKS_PER_BIT(DIV)) dut(.i_clk(clk),.i_reset(reset),.i_rx(rx),.o_data(data),.o_valid(valid));
integer count=0, expected=0;
always @(posedge clk) if(valid) begin
    if(data !== expected[7:0]) $fatal(1,"RX expected %h got %h",expected,data);
    count=count+1;
end
task send(input [7:0] b);
    begin
        rx=0; #(10*DIV);
        for(integer k=0;k<8;k=k+1) begin
            rx=b[k]; #(10*DIV + (k%2 ? -2 : 2));
        end
        rx=1; #(10*DIV);
    end
endtask
initial begin
    repeat(4) @(negedge clk); reset=0;
    // A pulse shorter than half a bit must not become a character.
    #2; rx=0; #10; rx=1; #(DIV*120);
    if(count!=0) $fatal(1,"short glitch accepted");
    for(integer k=0;k<256;k=k+1) begin
        expected=k; #3; send(k); #(DIV*20);
        if(count!=k+1) $fatal(1,"missing RX byte %0d", k);
    end
    // Reset discards an unfinished frame and restores reception.
    rx=0; #(DIV*25); reset=1; #30; rx=1;
    repeat(4) @(negedge clk); reset=0; #(DIV*20);
    expected=8'h5a; send(8'h5a); #(DIV*20);
    if(count!=257) $fatal(1,"RX reset");
    $display("PASS UART RX DIV=%0d",DIV); $finish;
end
initial begin #100000000; $fatal(1,"RX timeout"); end
endmodule
