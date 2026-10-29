`timescale 1ns/1ps
// Parser/master test without CPU, UART PHY or system/MMIO dependencies.
module tb_debug_controller;
reg clk=0, reset=1;
always #5 clk=~clk;
reg [7:0] rx=0;
reg valid=0, ready=1, break_event=0;
wire [7:0] tx;
wire tx_valid, halt_cpu, run_cpu, step_cpu, reset_cpu;
wire [15:0] addr, data;
wire [1:0] bs;
wire we;
reg ack=0;
integer wait_count=0, accesses=0, received=0;
reg [7:0] response[0:31];
reg [15:0] last_addr, last_data;
reg last_we;
debug_uart dut(.i_clk(clk), .i_reset(reset), .i_rx_data(rx), .i_rx_valid(valid),
    .o_tx_data(tx), .o_tx_valid(tx_valid), .i_tx_ready(ready), .o_halt(halt_cpu),
    .o_run(run_cpu), .o_step(step_cpu), .o_reset_cpu(reset_cpu),
    .i_halted(1'b1), .i_break_reason(1'b0), .i_break_event(break_event), .i_pc(16'h4321),
    .o_addr(addr), .o_data(data), .o_bs(bs), .o_we(we), .i_ack(ack), .i_data(16'hba21));
always @(negedge clk) begin
    ack=0;
    if(bs!=0) begin
        if(wait_count==7) begin ack=1; wait_count=0; end
        else wait_count=wait_count+1;
    end else wait_count=0;
end
always @(posedge clk) if(!reset) begin
    if(tx_valid && ready) begin response[received]=tx; received=received+1; end
    if(bs!=0 && ack) begin
        accesses=accesses+1; last_addr=addr; last_data=data; last_we=we;
    end
end
task send(input string text);
    for(integer k=0;k<text.len();k=k+1) begin
        @(negedge clk); rx=text[k] | 8'h80; valid=1;
        @(negedge clk); valid=0;
    end
endtask
task check(input integer offset, input string text);
    for(integer k=0;k<text.len();k=k+1)
        if(response[offset+k] !== (text[k] | 8'h80)) $fatal(1,"controller response");
endtask
initial begin
    repeat(3) @(negedge clk); reset=0;
    send("A12ab"); repeat(20) @(negedge clk);
    if(accesses!=0 || received!=0 || addr!=16'hba21) $fatal(1,"A side effects");
    send("R"); wait(received==5); check(0,"K12ab");
    if(last_addr!=16'hba21 || addr!=16'hba23) $fatal(1,"read pointer");
    send("AaW1234"); wait(received==6); check(5,"K");
    if(last_addr!=16'hba2a || last_data!=16'h4321 || !last_we) $fatal(1,"write value");
    send("abcd"); wait(received==7);
    if(last_addr!=16'hba2c || last_data!=16'hdcba) $fatal(1,"persistent mode");
    send("w1?"); wait(received==9); check(7,"T1");
    if(accesses!=3) $fatal(1,"partial write was committed");
    @(negedge clk); ready=0;
    send("P"); wait(tx_valid);
    @(negedge clk); break_event=1;
    @(negedge clk); break_event=0;
    repeat(5) @(negedge clk);
    if(received!=9) $fatal(1,"TX ignored backpressure");
    ready=1; wait(received==15); check(9,"K1234B");
    $display("PASS debug controller"); $finish;
end
initial begin #20000; $fatal(1,"controller timeout"); end
endmodule
