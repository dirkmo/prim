`timescale 1ns/1ps
module tb_interrupt_cpu;
parameter integer CASE = 0;
reg clk=0, reset=1, irq=0, halt=0, run_cpu=0, step_cpu=0, debug_reset=0;
always #5 clk=~clk;
wire [15:0] addr, data, pc;
wire [1:0] bs;
wire we, halted;
reg ack=0;
reg [15:0] rd=0;
Prim dut(.i_clk(clk), .i_reset(reset), .o_addr(addr), .o_dat(data), .i_dat(rd),
    .o_bs(bs), .o_we(we), .i_ack(ack), .i_irq(irq), .i_halt(halt),
    .i_run(run_cpu), .i_step(step_cpu), .i_debug_reset(debug_reset),
    .o_halted(halted), .o_pc(pc));
reg [7:0] mem[0:65535];
reg [15:0] expected_vector=128;
integer delay_count=0, entries=0, stores=0, j;
reg waiting=0;
reg [34:0] held;
always @(negedge clk) begin
    ack=0;
    if (bs!=0) begin
        if (delay_count==5) begin
            ack=1; rd={mem[(addr+1)&65535],mem[addr]}; delay_count=0;
        end else delay_count=delay_count+1;
    end else delay_count=0;
end
always @(posedge clk) begin
    if (reset || debug_reset) waiting<=0;
    else begin
        if (waiting && held !== {addr,data,bs,we}) $fatal(1,"unstable bus");
        waiting <= bs!=0 && !ack;
        held <= {addr,data,bs,we};
        if (halted && bs!=0) $fatal(1,"bus active while halted");
        if (dut.r_phase==3) begin
            if(bs!=0 || we) $fatal(1,"bus active during IRQ entry");
            entries=entries+1;
        end
        if (we && ack) begin
            stores=stores+1; mem[addr]<=data[7:0];
            if(bs[1]) mem[(addr+1)&65535]<=data[15:8];
        end
    end
end
task at_phase(input [15:0] target, input [1:0] phase);
    begin
        @(negedge clk);
        while(pc!=target || dut.r_phase!=phase) @(negedge clk);
    end
endtask
task pulse;
    begin irq=1; @(negedge clk); irq=0; end
endtask
task resume_cpu;
    begin run_cpu=1; @(negedge clk); run_cpu=0; end
endtask
task entered(input [15:0] saved, input integer depth);
    begin
        while(dut.r_phase!=3) @(negedge clk);
        if(pc!=saved) $fatal(1,"pre-entry PC %h expected %h",pc,saved);
        // Place the observation after the IRQ entry edge, before ISR fetch ACK.
        @(negedge clk);
        if(pc!=expected_vector || dut.r_rsp!=depth || dut.R!=saved)
            $fatal(1,"entry PC=%h R=%h rsp=%d",pc,dut.R,dut.r_rsp);
    end
endtask
initial begin #200000; $fatal(1,"IRQ timeout CASE=%0d",CASE); end
initial begin
    for(j=0;j<65536;j=j+1) mem[j]=0;
    // Configure a non-default vector, enable, NOP, BREAK.
    mem[0]=8'h20; mem[1]=128; mem[2]=8'h25; mem[3]=8'h23;
    mem[4]=0; mem[5]=8'h22;
    mem[128]=8'h24; mem[129]=8'ha3; // INTDI; INTEI.RET
    case(CASE)
        2: begin mem[4]=8'h21; mem[5]=8'h34; mem[6]=8'h12; mem[7]=8'h22; end
        3: begin
            mem[4]=8'h21; mem[5]=8'h34; mem[6]=8'h12;
            mem[7]=8'h21; mem[8]=0; mem[9]=2; mem[10]=8'h1e; mem[11]=8'h22;
        end
        4,5: begin mem[4]=8'h20; mem[5]=64; mem[6]=1; mem[7]=8'h22;
                   mem[64]=0; mem[65]=8'h80; end
        6: begin mem[4]=8'h24; mem[5]=8'h23; mem[6]=8'h22; end
        7: begin mem[4]=8'h22; mem[5]=0; mem[6]=8'h22; end
        8: begin mem[5]=0; mem[6]=8'h22; end
        12: begin
            mem[4]=8'h21; mem[5]=8'h80; mem[6]=1; mem[7]=8'h25; mem[8]=8'h22;
            mem[384]=8'h24; mem[385]=8'ha3;
        end
        9: begin mem[128]=0; mem[129]=8'h24; mem[130]=8'ha3; end
        default: begin end
    endcase
    repeat(3) @(negedge clk); reset=0;
    if(dut.r_int_enable || dut.r_int_addr || dut.r_irq_pending)
        $fatal(1,"reset interrupt state");
    case(CASE)
        0,10: begin
            pulse(); // pending while masked, even across the INTAD stack pop
            if(CASE==10) begin at_phase(3,2); pulse(); end
            entered(4,1);
        end
        1: begin at_phase(4,0); pulse(); entered(5,1); end
        2: begin
            at_phase(4,1); pulse(); entered(7,1);
            if(dut.T!=16'h1234 || dut.r_dsp!=1) $fatal(1,"PUSH corrupted by IRQ");
        end
        3: begin at_phase(10,1); pulse(); entered(11,1);
            if(stores!=1 || {mem[513],mem[512]}!=16'h1234) $fatal(1,"store IRQ"); end
        4: begin at_phase(6,2); pulse(); entered(64,2);
            if(dut.r_rstack[1]!=7) $fatal(1,"CALL return overwritten"); end
        5: begin at_phase(65,2); pulse(); entered(7,1); end
        6: begin at_phase(4,2); pulse(); entered(6,1); end
        7: begin
            at_phase(4,2); pulse(); wait(halted); @(negedge clk);
            if(entries || pc!=5 || !dut.r_irq_pending) $fatal(1,"BREAK priority");
            resume_cpu(); entered(6,1);
        end
        8: begin
            at_phase(3,2); halt=1; wait(halted); @(negedge clk); halt=0;
            pulse(); repeat(4) @(negedge clk);
            if(pc!=4 || entries || !dut.r_irq_pending) $fatal(1,"HALT IRQ");
            step_cpu=1; @(negedge clk); step_cpu=0;
            wait(!halted); wait(halted); @(negedge clk);
            if(pc!=5 || entries || !dut.r_irq_pending) $fatal(1,"STEP IRQ");
            resume_cpu(); entered(6,1);
        end
        9: begin
            at_phase(4,0); pulse(); wait(dut.r_phase==3); @(negedge clk);
            pulse(); // a second pulse in the entry cycle must survive
            entered(129,2);
        end
        12: begin
            at_phase(7,2); expected_vector=384; pulse(); entered(8,1);
        end
        11: begin
            at_phase(4,0); pulse(); entered(5,1);
            // A pending pulse while masked must survive INTDI and be accepted
            // atomically after INTEI.RET has popped the old return address.
            at_phase(129,0); pulse(); entered(5,1);
        end
    endcase
    wait(halted); @(negedge clk);
    if(dut.r_rsp!=0 || dut.r_irq_pending || !dut.r_int_enable || dut.r_int_addr!=expected_vector)
        $fatal(1,"final IRQ state rsp=%d pending=%d",dut.r_rsp,dut.r_irq_pending);
    if(entries!=((CASE==9 || CASE==10 || CASE==11)?2:1)) $fatal(1,"entry count %d",entries);
    if(CASE!=2 && dut.r_dsp!=0) $fatal(1,"INTAD did not pop stack");
    // Debug reset clears the vector, enable and pending, including while halted.
    pulse(); debug_reset=1; @(negedge clk); debug_reset=0;
    if(!halted || pc || dut.r_int_enable || dut.r_int_addr || dut.r_irq_pending)
        $fatal(1,"debug reset IRQ state");
    $display("PASS interrupt CASE=%0d",CASE); $finish;
end
endmodule
