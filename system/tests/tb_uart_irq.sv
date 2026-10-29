`timescale 1ns/1ps
module tb_uart_irq;
// 0: RX while running; 1: TX slot release; 2: RX while halted and masked.
// 3: CPU TX queued during a debug response.
parameter integer MODE=0;
localparam DIV=8;
reg clk=0, reset=1, rx=1;
always #5 clk=~clk;
wire tx, halted, cs, oe, we;
wire [1:0] leds;
wire [15:0] addr, data;
prim_system #(.CLK_HZ(115200*DIV),.READ_CYCLES(4),.WRITE_CYCLES(5)) dut(
    .i_clk(clk),.i_reset(reset),.i_rx(rx),.o_tx(tx),.o_halted(halted),.o_leds(leds),
    .ram_addr(addr),.ram_data(data),.ram_cs_n(cs),.ram_oe_n(oe),.ram_we_n(we));
reg [15:0] memory[0:32767];
assign data=!cs&&!oe&&we ? memory[addr[14:0]] : 16'hzzzz;
always @(posedge we) if(!cs&&!reset) memory[addr[14:0]]=data;
integer pulses=0, entries=0, replies=0, position=0, tx_wait=0;
reg [7:0] captured[0:63], byte_rx;
always @(posedge clk) if(!reset) begin
    if(MODE==3 && dut.uart.buffers.o_tx_valid && !dut.uart.buffered_ready) begin
        tx_wait=tx_wait+1;
        if(dut.uart_irq) $fatal(1,"IRQ before CPU slot was released");
    end
    if(dut.uart_irq) begin
        pulses=pulses+1;
        if((MODE==1 || MODE==3) && (!dut.uart_csr[1] || !dut.uart.tx.busy))
            $fatal(1,"TX interrupt must coincide with free slot and active frame");
    end
    if(dut.cpu.r_phase==3) entries=entries+1;
    if(dut.cpu.i_irq !== (dut.uart_irq | dut.timer_irq)) $fatal(1,"IRQ wiring");
end
always begin
    @(negedge tx);repeat(DIV/2) @(negedge clk);
    for(integer k=0;k<8;k=k+1) begin repeat(DIV) @(negedge clk);byte_rx[k]=tx;end
    repeat(DIV) @(negedge clk);
    if(tx!==1) $fatal(1,"UART stop");
    if(byte_rx[7]) begin captured[replies]=byte_rx&127;replies=replies+1;end
end
task send(input [7:0] b);
    @(negedge clk);rx=0;repeat(DIV) @(negedge clk);
    for(integer k=0;k<8;k=k+1) begin rx=b[k];repeat(DIV) @(negedge clk);end
    rx=1;repeat(DIV) @(negedge clk);
endtask
task command(input [7:0] c,input string expected);
    send(c|128);
    for(integer k=0;k<expected.len();k=k+1) begin
        wait(replies>position);
        while(captured[position]=="B") begin position=position+1;wait(replies>position);end
        if(captured[position]!==expected[k]) $fatal(1,"debug reply %c got %c",expected[k],captured[position]);
        position=position+1;
    end
endtask
task code(input integer at,input [7:0] value);
    memory[at/2][(at%2)*8+:8]=value;
endtask
integer loop_pc;
initial begin
    for(integer k=0;k<32768;k=k+1) memory[k]=0;
    // 128 intad 12 0xfffe c! intei
    code(0,'h20);code(1,'h80);code(2,'h25);code(3,'h20);code(4,12);
    code(5,'h21);code(6,'hfe);code(7,'hff);code(8,'h1f);code(9,'h23);
    loop_pc=10;
    if(MODE==1 || MODE==3) begin
        // 65 0xffff c!: first enqueue starts TX, releasing the slot raises IRQ.
        code(10,'h20);code(11,65);code(12,'h21);code(13,'hff);code(14,'hff);code(15,'h1f);
        loop_pc=16;
        if(MODE==3) begin
            // Stop before TX; RUN queues the byte behind its own debug reply.
            code(9,'h22);
            for(integer k=15;k>=10;k=k-1) code(k+1,memory[k/2][(k%2)*8+:8]);
            code(10,'h23);loop_pc=17;
        end
    end else if(MODE==2) begin
        code(9,'h22); // BREAK while global IRQ is still disabled.
        code(10,'h23);loop_pc=11; // INTEI after debug RUN.
    end
    code(loop_pc,'h21);code(loop_pc+1,loop_pc);code(loop_pc+2,0);code(loop_pc+3,2);
    // ISR: intdi 3 0xfffd c! BREAK. LED write proves handler execution.
    code(128,'h24);code(129,'h20);code(130,3);code(131,'h21);
    code(132,'hfd);code(133,'hff);code(134,'h1f);code(135,'h22);
    repeat(4) @(negedge clk);reset=0;
    wait(dut.uart_csr[3:2]==3);
    if(MODE==3) begin
        wait(halted);command("q","K2");
        if(pulses) $fatal(1,"debug response generated IRQ");
        command("G","K");
    end else if(MODE!=1) begin
        if(MODE==2) begin wait(halted);command("?","T3");end
        else wait(dut.cpu.r_int_enable);
        command("q","K2"); // Enables must not appear in the debug status reply.
        command("q","K2");
        if(pulses || entries) $fatal(1,"debug traffic or idle TX generated IRQ");
        send(8'h41);
        if(MODE==2) begin
            repeat(8) @(negedge clk);
            if(!halted || !dut.cpu.r_irq_pending || entries || pulses!=1)
                $fatal(1,"halted/masked CPU did not retain UART IRQ");
            command("q","K3");command("G","K");
        end
    end
    wait(leds==3);wait(halted);
    // Consume outstanding BREAK notification before querying/resetting.
    wait(dut.uart.tx.o_ready && !dut.uart.debug.o_tx_valid);
    repeat(DIV*12) @(negedge clk);position=replies;
    if(pulses!=1 || entries!=1) $fatal(1,"IRQ counts pulses=%0d entries=%0d",pulses,entries);
    if(MODE==3 && !tx_wait) $fatal(1,"CPU TX did not wait for debug frame");
    command("Z","K");
    if(dut.uart_csr[3:2]!=3 || dut.cpu.r_irq_pending || dut.cpu.r_int_enable)
        $fatal(1,"CPU reset must preserve CSR and clear CPU IRQ state");
    if(MODE==1 || MODE==3) command("q","K2");else command("q","K3");
    if(pulses!=1 || entries!=1) $fatal(1,"debug reset/status generated IRQ");
    $display("PASS UART IRQ MODE=%0d",MODE);$finish;
end
initial begin #2000000;$fatal(1,"UART IRQ timeout");end
endmodule
