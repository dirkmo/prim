`timescale 1ns/1ps
module tb_debug_cpu;
reg clk=0, reset=1, halt=0, run_cpu=0, step_cpu=0, reset_cpu=0;
always #5 clk=~clk;
wire [15:0] addr, data, pc;
wire [1:0] bs;
wire we, halted, reason, event_break;
reg ack=0;
reg [15:0] rd=0;
Prim dut(.i_clk(clk),.i_reset(reset),.o_addr(addr),.o_dat(data),.i_dat(rd),
    .o_bs(bs),.o_we(we),.i_ack(ack),.i_irq(1'b0),.i_halt(halt),.i_run(run_cpu),
    .i_step(step_cpu),.i_debug_reset(reset_cpu),.o_halted(halted),.o_pc(pc),
    .o_break_reason(reason),.o_break_event(event_break));
reg [7:0] mem[0:65535];
integer delay_count=0, stores=0;
reg waiting=0;
reg [34:0] held;
always @(negedge clk) begin
    ack=0;
    if(bs!=0) begin
        if(delay_count==17) begin
            ack=1; rd={mem[(addr+1)&65535],mem[addr]}; delay_count=0;
        end else delay_count=delay_count+1;
    end else delay_count=0;
end
always @(posedge clk) begin
    if(!reset) begin
        if(waiting && held !== {addr,data,bs,we}) $fatal(1,"CPU bus changed before ACK");
        waiting <= bs!=0 && !ack;
        held <= {addr,data,bs,we};
        if(bs!=0 && ack && we) begin
            stores=stores+1; mem[addr]<=data[7:0];
            if(bs[1]) mem[(addr+1)&65535]<=data[15:8];
        end
        if(halted && bs!=0) $fatal(1,"bus during halt");
    end else waiting<=0;
end
task step_one(input [15:0] expected_pc);
    begin
        @(negedge clk); step_cpu=1;
        @(negedge clk); step_cpu=0;
        wait(!halted); wait(halted); @(negedge clk);
        if(pc!=expected_pc) $fatal(1,"STEP PC %h expected %h",pc,expected_pc);
    end
endtask
initial begin #100000; $fatal(1,"CPU timeout"); end
initial begin
    // PUSH16 1234; PUSH16 0200; STORE; BYTE_FETCH (for another wait); BREAK
    mem[0]=8'h21;mem[1]=8'h34;mem[2]=8'h12;
    mem[3]=8'h21;mem[4]=0;mem[5]=2;mem[6]=8'h1e;mem[7]=8'h22;
    repeat(3) @(negedge clk); reset=0;
    // Request halt during immediate read: finish instruction, including wait.
    wait(dut.r_phase==1); @(negedge clk); halt=1;
    repeat(3) @(negedge clk);
    if(halted) $fatal(1,"premature HALT");
    wait(halted); @(negedge clk); halt=0;
    if(pc!=3 || dut.T!=16'h1234) $fatal(1,"HALT immediate");
    step_one(6);
    if(dut.T!=16'h0200) $fatal(1,"STEP immediate");
    step_one(7);
    if(stores!=1 || {mem[513],mem[512]}!=16'h1234) $fatal(1,"STEP store");
    step_one(8);
    if(!reason) $fatal(1,"STEP BREAK");
    @(negedge clk); reset_cpu=1;
    @(negedge clk); reset_cpu=0;
    if(!halted || pc!=0 || reason || mem[512]!=8'h34) $fatal(1,"RESET-HALT");
    // HALT requested in a delayed store must wait for its ACK and retirement.
    step_one(3); step_one(6);
    @(negedge clk); run_cpu=1;
    @(negedge clk); run_cpu=0;
    wait(we && bs!=0); @(negedge clk); halt=1;
    repeat(3) @(negedge clk);
    if(halted) $fatal(1,"premature store HALT");
    wait(halted); @(negedge clk);
    if(stores!=2 || pc!=7) $fatal(1,"HALT store completion");
    // BREAK.RET with occupied stacks must preserve them and ignore return.
    halt=0;
    mem[0]=8'h20; mem[1]=8'h44; mem[2]=8'h19;
    mem[3]=8'h20; mem[4]=8'h55; mem[5]=8'ha2;
    reset_cpu=1; @(negedge clk); reset_cpu=0;
    step_one(2); step_one(3); step_one(5); step_one(6);
    if(dut.T!=16'h55 || dut.r_dsp!=1 || dut.r_rsp!=1 || dut.R!=16'h44)
        $fatal(1,"BREAK changed stack");
    $display("PASS debug CPU waits"); $finish;
end
endmodule
