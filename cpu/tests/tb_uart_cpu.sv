`timescale 1ns/1ps
// CPU-only peripheral model: status, last-byte reads and a blocked TX write.
module tb_uart_cpu;
reg clk=0, reset=1, halt_cpu=0, step_cpu=0;
always #5 clk=~clk;
wire [15:0] addr, data, pc;
wire [1:0] bs;
wire we, halted;
reg ack=0;
reg [15:0] read_data=0;
reg [7:0] rom[0:31];
reg received=1;
integer waits=0, writes=0, rx_reads=0;
Prim dut(.i_clk(clk),.i_reset(reset),.i_halt(halt_cpu),.i_run(1'b0),.i_step(step_cpu),
    .i_debug_reset(1'b0),.o_addr(addr),.o_dat(data),.i_dat(read_data),.o_bs(bs),.o_we(we),
    .i_ack(ack),.i_irq(1'b0),.o_pc(pc),.o_halted(halted));
reg pending=0;
reg [34:0] held;
always @(negedge clk) begin
    ack=0;
    if(bs!=0) begin
        if(waits==(we ? 25 : 5)) begin
            waits=0; ack=1;
            if(addr==16'hfffe) read_data={14'b0,1'b1,received};
            else if(addr==16'hffff) read_data=16'h0041;
            else read_data={rom[(addr+1)&31],rom[addr&31]};
        end else waits=waits+1;
    end else waits=0;
end
always @(posedge clk) begin
    if(!reset) begin
        if(pending && held!=={addr,data,bs,we}) $fatal(1,"UART wait changed CPU request");
        pending<=bs!=0 && !ack;
        held<={addr,data,bs,we};
        if(ack && bs!=0 && addr==16'hffff) begin
            if(we) begin
                writes=writes+1;
                if(data[7:0]!=8'h55) $fatal(1,"UART TX data");
            end else begin received=0; rx_reads=rx_reads+1; end
        end
        if(halted && bs!=0) $fatal(1,"halted CPU requested bus");
    end else pending<=0;
end
initial begin
    // FFFE c@; FFFF c@; FFFF c@; 55 FFFF c!; BREAK
    rom[0]=8'h21;rom[1]=8'hfe;rom[2]=8'hff;rom[3]=8'h1d;
    rom[4]=8'h21;rom[5]=8'hff;rom[6]=8'hff;rom[7]=8'h1d;
    rom[8]=8'h21;rom[9]=8'hff;rom[10]=8'hff;rom[11]=8'h1d;
    rom[12]=8'h20;rom[13]=8'h55;
    rom[14]=8'h21;rom[15]=8'hff;rom[16]=8'hff;rom[17]=8'h1f;rom[18]=8'h22;
    repeat(3) @(negedge clk); reset=0;
    wait(we && bs!=0); @(negedge clk); halt_cpu=1;
    repeat(10) @(negedge clk);
    if(halted || writes!=0) $fatal(1,"HALT truncated UART write");
    wait(halted); @(negedge clk); halt_cpu=0;
    if(pc!=18 || writes!=1 || rx_reads!=2 || received || dut.T!=16'h41 || dut.N!=16'h41)
        $fatal(1,"CPU UART program result");
    step_cpu=1; @(negedge clk);step_cpu=0;
    wait(!halted);wait(halted);@(negedge clk);
    if(pc!=19 || writes!=1) $fatal(1,"STEP after UART wait");
    $display("PASS CPU UART bus handshake");$finish;
end
initial begin #100000;$fatal(1,"CPU UART timeout");end
endmodule
