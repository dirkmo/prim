`timescale 1ns/1ps
// SRAM-only send-ahead loading: all nibbles are sent without waiting for OK.
module tb_stream_load;
parameter DIV=8;
reg clk=0, reset=1, rx=1;
always #5 clk=~clk;
wire tx, halted, cs, oe, we;
wire [15:0] addr, data;
prim_system #(.CLK_HZ(115200*DIV), .READ_CYCLES(3), .WRITE_CYCLES(3), .START_HALTED(1)) dut(
    .i_clk(clk), .i_reset(reset), .i_rx(rx), .o_tx(tx), .o_halted(halted),
    .ram_addr(addr), .ram_data(data), .ram_cs_n(cs), .ram_oe_n(oe), .ram_we_n(we));
reg [15:0] memory[0:32767];
assign data=!cs&&!oe&&we ? memory[addr[14:0]] : 16'hzzzz;
always @(posedge we) if(!cs&&!reset) memory[addr[14:0]]=data;
integer oks=0;
reg [7:0] value;
always begin
    @(negedge tx); repeat(DIV/2) @(negedge clk);
    for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin
        repeat(DIV) @(negedge clk); value[bit_index]=tx;
    end
    repeat(DIV) @(negedge clk);
    if(tx!==1 || value!==8'hcb) $fatal(1,"stream response %02x",value);
    oks=oks+1;
end
task send(input [7:0] c);
    @(negedge clk); rx=0; repeat(DIV) @(negedge clk);
    for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin
        rx=c[bit_index]; repeat(DIV) @(negedge clk);
    end
    rx=1; repeat(DIV) @(negedge clk);
endtask
function [7:0] hexchar(input [3:0] nibble);
    hexchar=8'h80 | (nibble<10 ? 8'd48+nibble : 8'd87+nibble);
endfunction
reg [15:0] word_value;
initial begin
    for(integer i=0;i<32768;i=i+1) memory[i]=16'haaaa;
    repeat(4) @(negedge clk); reset=0;
    repeat(8) @(negedge clk);
    if(!halted) $fatal(1,"stream requires halted CPU");
    send(8'hc1); // A
    repeat(4) send(8'hb0); // address 0000
    send(8'hd7); // W
    for(integer i=0;i<32;i=i+1) begin
        word_value=16'h4321 ^ i;
        for(integer nibble=0;nibble<4;nibble=nibble+1)
            send(hexchar(word_value[nibble*4+:4]));
    end
    wait(oks==32);
    repeat(DIV*12) @(negedge clk);
    if(oks!=32 || dut.uart.debug.pointer!=64) $fatal(1,"stream ACK/pointer count");
    for(integer i=0;i<32;i=i+1)
        if(memory[i] !== (16'h4321 ^ i)) $fatal(1,"stream memory word %0d",i);
    if(memory[32]!==16'haaaa || !halted) $fatal(1,"stream boundary/CPU state");
    $display("PASS SRAM streaming, DIV=%0d",DIV); $finish;
end
initial begin #50000000; $fatal(1,"stream timeout"); end
endmodule
