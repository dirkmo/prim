`timescale 1ns/1ps
module tb_debug;
parameter integer DIV=8;
reg clk=0, reset=1, rx=1;
always #5 clk=~clk;
wire tx;
wire [15:0] ra, rd;
wire cs, oe, we;
prim_system #(.CLK_HZ(115200*DIV), .READ_CYCLES(3), .WRITE_CYCLES(4)) dut(
    .i_clk(clk), .i_reset(reset), .i_rx(rx), .o_tx(tx),
    .ram_addr(ra), .ram_data(rd), .ram_cs_n(cs), .ram_oe_n(oe), .ram_we_n(we));
reg [15:0] mem[0:32767];
assign rd=(!cs && !oe && we) ? mem[ra[14:0]] : 16'hzzzz;
always @(posedge we) if (!reset && !cs) mem[ra[14:0]]=rd;
integer n=0, pos=0, breaks=0, outputs=0, j;
reg [7:0] captured[0:4095];
reg [7:0] b;
always begin
    @(negedge tx);
    repeat(DIV/2) @(negedge clk);
    if (tx !== 0) $fatal(1,"start");
    for(integer k=0;k<8;k=k+1) begin
        repeat(DIV) @(negedge clk); b[k]=tx;
    end
    repeat(DIV) @(negedge clk);
    if(tx !== 1) $fatal(1,"stop");
    captured[n]=b; n=n+1;
end
// Every request must remain stable through the acknowledging edge.
reg waiting=0;
reg [34:0] held;
always @(posedge clk) begin
    if(!reset) begin
        if(waiting && {dut.addr,dut.to_mem,dut.bs,dut.we} !== held)
            $fatal(1,"unstable bus");
        waiting <= dut.bs != 0 && !dut.ack;
        held <= {dut.addr,dut.to_mem,dut.bs,dut.we};
        if(dut.halted && dut.cpu_bs !== 0) $fatal(1,"halted CPU bus active");
        if(!dut.halted && dut.debug_bs !== 0) $fatal(1,"debug stole bus");
    end else waiting <= 0;
end

task sendbyte(input [7:0] c);
    begin
        @(negedge clk); rx=0;
        repeat(DIV) @(negedge clk);
        for(integer k=0;k<8;k=k+1) begin
            rx=c[k]; repeat(DIV) @(negedge clk);
        end
        rx=1; repeat(DIV) @(negedge clk);
    end
endtask
task send(input string s);
    for(integer k=0;k<s.len();k=k+1) sendbyte(s[k] | 8'h80);
endtask
task expect_reply(input string s);
    reg [7:0] c;
    begin
        for(integer k=0;k<s.len();k=k+1) begin
            wait(pos<n); c=captured[pos]; pos=pos+1;
            while(!c[7] || c==8'hc2) begin
                if(c==8'hc2) breaks=breaks+1;
                else outputs=outputs+1;
                wait(pos<n); c=captured[pos]; pos=pos+1;
            end
            if(c !== (s[k] | 8'h80)) $fatal(1,"reply expected %c got %h at %0d",s[k],c,pos);
        end
    end
endtask
task command(input string s, input string reply);
    begin $display("COMMAND %s -> %s pointer=%h",s,reply,dut.uart.debug.pointer); send(s); expect_reply(reply); end
endtask
initial begin
    #20000000; $fatal(1,"timeout pos=%0d n=%0d state=%0d",pos,n,dut.uart.debug.state);
end
initial begin
    for(j=0;j<32768;j=j+1) mem[j]=0;
    // BREAK.RET must ignore return bit, keep both stacks, advance PC.
    mem[0]=16'h00a2;
    repeat(4) @(negedge clk); reset=0;
    wait(dut.halted);
    command("?", "T3");
    if(breaks!=1 || dut.pc!=1 || dut.cpu.r_rsp!=0 || dut.cpu.r_dsp!=0) $fatal(1,"BREAK semantics");
    command("Z", "K"); command("?", "T1"); command("P", "K0000");
    // Ignore channel zero even when it looks like a debug command.
    sendbyte("G"); repeat(DIV*12) @(negedge clk);
    if(!dut.halted) $fatal(1,"channel separation");
    j=n;
    send("A12ab"); repeat(DIV*30) @(negedge clk);
    send("X"); sendbyte("a");
    if(n!=j || dut.bs!=0 || dut.uart.debug.pointer!=16'hba21)
        $fatal(1,"address pause/unknown/channel zero caused side effect");
    command("A12abw12", "K"); // BA21 = 21
    command("34", "K"); command("ab", "K");
    command("A12abr", "K12"); command("r", "K34"); command("r", "Kab");
    send("A12abAa");
    if(dut.uart.debug.pointer!=16'hba2a) $fatal(1,"partial nibble");
    send("A4c");
    if(dut.uart.debug.pointer!=16'hbac4) $fatal(1,"partial byte");
    command("w56", "K"); command("A4cr", "K56");
    command("A1001W1234", "K"); command("abcd", "K");
    command("A1001R", "K1234"); command("R", "Kabcd");
    // New commands discard partial values and terminate the old mode.
    command("A0002w1?", "T1");
    command("W123?", "T1");
    command("w1A0002r", "K00");
    send("A0002w1W"); command("1234", "K");
    command("A0002R", "K1234");
    // Debug writes to UART and split word MMIO must ACK before sending OK.
    command("Affffwff", "K");
    if(outputs!=1) $fatal(1,"MMIO output missing");
    if(dut.uart.debug.pointer!=0) $fatal(1,"byte wrap");
    command("AefffW1c24", "K"); // FFFE: C1 to RAM, 42 to UART
    command("AffffW3445", "K"); // FFFF: 43 to UART, 54 to RAM zero
    if(dut.uart.debug.pointer!=1 || outputs!=3 || mem[0][7:0]!=8'h54) $fatal(1,"word wrap/MMIO");
    command("AffffR", "K0045");
    if(dut.uart.debug.pointer!=1) $fatal(1,"read word wrap");
    command("Affffr", "K00");
    if(dut.uart.debug.pointer!=0) $fatal(1,"read byte wrap");
    command("A1001Z", "K");
    if(dut.uart.debug.pointer!=16'h1001) $fatal(1,"reset pointer");
    command("R", "K1234"); // SRAM survived CPU reset
    // Restore BREAK and STEP through it; busy TX must retain notification.
    command("A0000w2a", "K");
    command("Z", "K"); command("S", "K"); command("P", "K1000");
    command("?", "T3");
    if(breaks!=2) $fatal(1,"STEP BREAK notification count %0d", breaks);
    command("H", "K");
    // RUN clears saved reason and continues at PC=1 to another BREAK.
    command("A1000w22", "K"); command("G", "K"); command("?", "T3");
    if(breaks!=3 || dut.pc!=2) $fatal(1,"RUN/BREAK");
    // No duplicate event after it has been transmitted.
    command("?", "T3"); if(breaks!=3) $fatal(1,"duplicate BREAK");
    // Inject an event while a multi-character reply is being transmitted.
    j=n;
    fork
        send("P");
        begin
            wait(dut.uart.debug.prefix); wait(!dut.uart.debug.prefix);
            @(negedge clk); force dut.break_event=1;
            @(negedge clk); release dut.break_event;
        end
    join
    expect_reply("K2000");
    wait(n>=j+6);
    if(captured[j+5]!=8'hc2) $fatal(1,"BREAK interrupted numeric reply");
    command("?", "T3");
    if(breaks!=4) $fatal(1,"pending notification");
    // RUN a memory-using loop, then RESET-HALT without resetting SRAM/UART.
    command("A0000w12", "K"); // PUSH16 0000; JP
    command("00", "K"); command("00", "K"); command("20", "K");
    command("Z", "K"); command("G", "K"); command("Z", "K");
    command("P", "K0000"); command("?", "T1");
    command("A1001R", "K1234");
    $display("PASS debug system DIV=%0d",DIV); $finish;
end
endmodule
