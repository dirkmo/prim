`timescale 1ns/1ps
module tb_ps2_mmio;
parameter VIDEO=0;
reg clk=0, reset=1, psclk=1, psdata=1;
always #5 clk=~clk;
reg [15:0] addr=0, wdata=0;
reg [1:0] bs=0;
reg wr=0, uart_rx=0, uart_tx=0, rxavail=0;
reg [1:0] uart_en=0;
wire [15:0] result, ram_addr, ram_data;
wire [1:0] leds;
wire ack, cs, oe, we, irq, csr_write, input_read;
wire [7:0] csr_data;
wire [3:0] uart_csr={uart_en,1'b1,rxavail};
memory_io #(.PS2_ENABLE(1), .VGA_ENABLE(VIDEO), .PS2_FIFO_DEPTH(4),
    .PS2_TIMEOUT_CYCLES(100), .TIMER_DIVISOR(1), .READ_CYCLES(3), .WRITE_CYCLES(4)) dut(
    .i_clk(clk), .i_reset(reset), .i_addr(addr), .i_cpu_to_mem(wdata),
    .i_bs(bs), .i_we(wr), .o_mem_to_cpu(result), .o_ack(ack),
    .i_input_data(7'h41), .i_uart_csr(uart_csr), .i_output_ready(1'b1),
    .o_uart_csr_data(csr_data), .o_uart_csr_write(csr_write), .o_input_read(input_read),
    .i_uart_rx_irq(uart_rx), .i_uart_tx_irq(uart_tx),
    .i_ps2_clk(psclk), .i_ps2_data(psdata), .o_irq(irq), .o_leds(leds),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(cs), .ram_oe_n(oe), .ram_we_n(we));
reg [15:0] memory[0:32767];
assign ram_data=!cs&&!oe&&we ? memory[ram_addr[14:0]] : 16'hzzzz;
always @(posedge we) if(!reset&&!cs) memory[ram_addr[14:0]]=ram_data;
always @(posedge clk) begin
    if(reset) uart_en<=0;
    else if(csr_write) uart_en<=csr_data[3:2];
end
integer pulses=0, pops=0, cycles;
always @(posedge clk) if(!reset) begin
    if(irq) pulses=pulses+1;
    if(dut.ps2_pop) pops=pops+1;
end
task access(input [15:0] a, input [15:0] value, input [1:0] lanes, input bit write_access);
    @(negedge clk); addr=a; wdata=value; bs=lanes; wr=write_access;
    cycles=0;
    do begin
        @(posedge clk); cycles=cycles+1;
        if(cycles>40) $fatal(1,"MMIO timeout %h",a);
    end while(!ack);
    // Keep ACK and read data available to the caller until the following edge.
    @(negedge clk); bs=0; wr=0;
endtask
task check_read(input [15:0] a, input [1:0] lanes, input [15:0] expected, input [15:0] compare_mask=16'hffff);
    reg [15:0] captured;
    @(negedge clk); addr=a; bs=lanes; wr=0;
    cycles=0;
    do begin
        @(posedge clk); captured=result; cycles=cycles+1;
        if(cycles>40) $fatal(1,"read timeout %h",a);
    end while(!ack);
    if((captured & compare_mask)!==expected) $fatal(1,"read %h mask=%b got=%h expected=%h",a,lanes,captured,expected);
    @(negedge clk); bs=0;
endtask
task psbit(input bit value);
    psdata=value; repeat(20) @(negedge clk); psclk=0;
    repeat(20) @(negedge clk); psclk=1;
endtask
task frame(input [7:0] value, input bit bad);
    psbit(0);
    for(integer j=0;j<8;j=j+1) psbit(value[j]);
    psbit((~^value)^bad); psbit(1); psdata=1;
    repeat(20) @(negedge clk);
endtask
integer saved, before_pops;
initial begin
    for(integer j=0;j<32768;j=j+1) memory[j]=16'ha55a;
    repeat(4) @(negedge clk); reset=0;
    check_read(16'hfffb,3,0); check_read(16'hfff5,1,0);
    frame(8'h00,0); frame(8'hf0,0);
    check_read(16'hfffb,1,1); // Polling works while RXIE is off.
    if(pulses) $fatal(1,"disabled PS/2 IRQ");
    access(16'hfffb,4,1,1);
    check_read(16'hfff5,1,8); // Backlog on enable, nondestructive pending.
    if(pulses!=1) $fatal(1,"backlog enable must generate one pulse");
    saved=pulses;
    check_read(16'hfff5,1,8);
    if(pulses!=saved) $fatal(1,"pending read replayed IRQ");
    before_pops=pops;
    check_read(16'hfffb,3,16'h0005); // CSR snapshot + one DATA pop.
    if(pops!=before_pops+1) $fatal(1,"word DATA pop repeated");
    check_read(16'hfffc,1,16'h00f0);
    check_read(16'hfffc,1,0); // Empty read does not replay last byte.
    check_read(16'hfff5,1,8); // Consumption does not acknowledge source identity.
    access(16'hfff5,8,1,1); check_read(16'hfff5,1,0);

    for(integer j=1;j<=5;j=j+1) frame(j,0);
    check_read(16'hfffb,1,16'h17); // Full, overflow, RXIE.
    access(16'hfffb,16'h14,1,1); // W1C overflow, retain RXIE.
    for(integer j=1;j<=4;j=j+1) check_read(16'hfffc,1,j);
    frame(8'h42,1);
    check_read(16'hfffb,1,12); // Bad parity discarded, sticky frame error.
    access(16'hfffb,12,1,1); check_read(16'hfffb,1,4);
    psbit(0); psbit(1); psdata=1; repeat(120) @(negedge clk);
    check_read(16'hfffb,1,12); // Partial-frame timeout.
    access(16'hfffb,12,1,1);

    // Error-only backlog is replayed on enable; while disabled it is polling-only.
    access(16'hfffb,0,1,1); access(16'hfff5,8,1,1);
    saved=pulses; frame(8'h33,1);
    check_read(16'hfffb,1,8); check_read(16'hfff5,1,0);
    if(pulses!=saved) $fatal(1,"disabled receive error generated IRQ");
    access(16'hfffb,4,1,1); check_read(16'hfff5,1,8);
    if(pulses!=saved+1) $fatal(1,"error-only backlog enable");
    access(16'hfffb,12,1,1);
    // Retained pending replays even after data/errors themselves were cleared.
    access(16'hfffb,0,1,1); saved=pulses;
    access(16'hfffb,4,1,1); check_read(16'hfff5,1,8);
    if(pulses!=saved+1) $fatal(1,"PS/2 retained pending enable");

    // Every byte mask at CSR/DATA and both neighboring register crossings.
    for(integer mask=1;mask<=3;mask=mask+1) begin
        frame(8'h5a,0); before_pops=pops;
        if(VIDEO) access(16'hfff6,0,1,1); // Known VGA blank status.
        check_read(16'hfffa,mask,((mask&2)!=0 ? 16'h0500 : 0), VIDEO ? 16'hfffc : 16'hffff);
        // CSR only: DATA lane unselected; it must remain queued.
        check_read(16'hfffb,1,5);
        if(pops!=before_pops) $fatal(1,"unselected DATA consumed");
        access(16'hfffc,16'h0355,mask,1); // DATA writes ignored; LED high lane selected.
        if((mask&2)!=0 && leds!==3) $fatal(1,"LED crossing write");
        check_read(16'hfffc,1,16'h5a);
        access(16'hfffd,0,1,1);
    end
    for(integer mask=1;mask<=3;mask=mask+1) begin
        frame(8'h5a,0); before_pops=pops;
        check_read(16'hfffb,mask,((mask&1)!=0 ? 5 : 0) | ((mask&2)!=0 ? 16'h5a00 : 0));
        if(pops!=before_pops+((mask&2)!=0)) $fatal(1,"CSR/DATA mask consumption");
        if((mask&2)==0) check_read(16'hfffc,1,16'h5a);
        access(16'hfffd,3,1,1);
        frame(8'ha5,0); before_pops=pops;
        check_read(16'hfffc,mask,((mask&1)!=0 ? 16'ha5 : 0) | ((mask&2)!=0 ? 16'h0300 : 0));
        if(pops!=before_pops+((mask&1)!=0)) $fatal(1,"DATA/LED mask consumption");
        if((mask&1)==0) check_read(16'hfffc,1,16'ha5);
    end

    // IRQ events from UART and PS/2 in the same sampling edge.
    access(16'hfffe,12,1,1); access(16'hfff5,15,1,1);
    fork
        frame(8'h1c,0);
        begin
            wait(dut.keyboard.receiver.o_valid);
            @(negedge clk); uart_rx=1; uart_tx=1;
            @(negedge clk); uart_rx=0; uart_tx=0;
        end
    join
    check_read(16'hfff5,1,14);
    check_read(16'hfffc,1,16'h1c);
    access(16'hfff5,15,1,1);
    // Timer source retains identity after COUNT no longer advances.
    access(16'hfff2,3,3,1); access(16'hfff0,0,3,1); access(16'hfff4,5,1,1);
    repeat(6) @(negedge clk);
    check_read(16'hfff5,1,1); check_read(16'hfff4,3,16'h0105);
    access(16'hfff4,0,1,1); // Masking does not erase pending.
    check_read(16'hfff5,1,1); saved=pulses;
    access(16'hfff4,4,1,1); repeat(3) @(negedge clk);
    if(pulses!=saved+1) $fatal(1,"timer retained pending replay");
    access(16'hfff4,16'h0104,3,1); // Aligned control + high-byte W1C.
    check_read(16'hfff5,1,0);
    // A high-byte-only pending write does not touch timer CSR/count.
    access(16'hfff4,16'hff00,2,1); check_read(16'hfff4,1,4);
    // Same-edge W1C/event: the new event must win.
    @(negedge clk); addr=16'hfff5; wdata=6; bs=1; wr=1; uart_rx=1; uart_tx=1;
    @(posedge clk); if(!ack) $fatal(1,"pending ACK");
    @(negedge clk); bs=0; wr=0; uart_rx=0; uart_tx=0;
    check_read(16'hfff5,1,6);
    access(16'hfff5,2,1,1); check_read(16'hfff5,1,4);
    access(16'hfff5,4,1,1);
    // Enabling UART RX seeds unread backlog, initial TXFREE does not.
    access(16'hfffe,0,1,1); rxavail=1;
    access(16'hfffe,12,1,1); repeat(3) @(negedge clk);
    check_read(16'hfff5,1,2);
    @(negedge clk); reset=1;
    repeat(3) @(negedge clk); reset=0; rxavail=0;
    check_read(16'hfff5,1,0); check_read(16'hfffb,3,0);
    for(integer j=16'hfff0/2;j<32768;j=j+1)
        if(memory[j]!==16'ha55a) $fatal(1,"MMIO modified hidden SRAM");
    $display("PASS PS/2 MMIO/shared IRQ VIDEO=%0d",VIDEO); $finish;
end
initial begin #4000000; $fatal(1,"MMIO test timeout"); end
endmodule
