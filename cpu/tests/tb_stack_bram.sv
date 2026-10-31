`timescale 1ns/1ps
// Black-box bus trace, also usable with the mapped iCE40 netlist. No access
// to CPU internals: this exercises the actual synchronous SB_RAM40_4K cells.
module tb_stack_bram;
reg clk=0, reset=1, irq=0, second_irq_sent=0;
always #5 clk=~clk;
wire [15:0] addr, data, pc;
wire [1:0] bs;
wire we, halted;
reg ack=0;
reg [15:0] rd=0;
Prim dut(.i_clk(clk), .i_reset(reset), .o_addr(addr), .o_dat(data),
    .i_dat(rd), .o_bs(bs), .o_we(we), .i_ack(ack), .i_irq(irq),
    .i_halt(1'b0), .i_run(1'b0), .i_step(1'b0), .i_debug_reset(1'b0),
    .o_halted(halted), .o_pc(pc));
reg [7:0] mem [0:65535];
reg [1023:0] image;
integer j, delay_count=0, transactions=0;
reg waiting=0;
reg [34:0] held;
always @(negedge clk) begin
    ack=0;
    rd=16'hdead;
    if (!reset && bs!=0) begin
        // Alternate immediate ACK and delayed transfers deterministically.
        if (delay_count == transactions % 4) begin
            ack=1;
            rd={mem[(addr+1)&65535],mem[addr]};
            delay_count=0;
        end else delay_count=delay_count+1;
    end else delay_count=0;
end
always @(posedge clk) begin
    irq<=0;
    if (reset) waiting<=0;
    else begin
        if (waiting && held !== {addr,data,bs,we})
            $fatal(1,"bus changed before ACK");
        waiting <= bs!=0 && !ack;
        held <= {addr,data,bs,we};
        if (bs!=0 && ack) begin
            transactions=transactions+1;
            if (we) begin
                if (addr==16'h4300 || (addr==16'h4302 && !second_irq_sent)) begin
                    irq<=1;
                    if (addr==16'h4302) second_irq_sent<=1;
                end
                if (bs[0]) begin
                    mem[addr]<=data[7:0];
                    $display("W %0d %0d",addr,data[7:0]);
                end
                if (bs[1]) begin
                    mem[(addr+1)&65535]<=data[15:8];
                    $display("W %0d %0d",(addr+1)&65535,data[15:8]);
                end
            end else begin
                if (bs[0]) $display("R %0d %0d",addr,rd[7:0]);
                if (bs[1]) $display("R %0d %0d",(addr+1)&65535,rd[15:8]);
            end
        end
    end
end
initial begin
    if (!$value$plusargs("image=%s",image)) $fatal(1,"missing image");
    for(j=0;j<65536;j=j+1) mem[j]=0;
    $readmemh(image,mem);
    repeat(3) @(negedge clk);
    reset=0;
    wait(halted);
    @(negedge clk);
    if (bs!=0) $fatal(1,"bus active while halted");
    $display("HALT %0d",pc);
    $finish;
end
initial begin #2000000; $fatal(1,"mapped stack CPU timeout"); end
endmodule
