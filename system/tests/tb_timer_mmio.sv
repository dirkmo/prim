`timescale 1ns/1ps
module tb_timer_mmio;
reg clk=0, reset=1;
always #5 clk=~clk;
reg [15:0] addr=0, data=0;
reg [1:0] bs=0;
reg we=0;
wire [15:0] result, ram_addr, ram_data;
wire ack, ram_cs, ram_oe, ram_we, irq;
integer timer_writes=0, saved_writes, expected_writes, n, a, mask, j;
reg [15:0] memory[0:32767];
reg [7:0] reference[0:65535];
memory_io #(.TIMER_DIVISOR(1)) dut(
    .i_clk(clk), .i_reset(reset), .i_addr(addr), .i_cpu_to_mem(data),
    .i_bs(bs), .i_we(we), .o_mem_to_cpu(result), .o_ack(ack),
    .i_output_ready(1'b1), .i_input_data(7'b0), .i_uart_csr(4'b0010),
    .o_timer_irq(irq), .ram_addr(ram_addr), .ram_data(ram_data),
    .ram_cs_n(ram_cs), .ram_oe_n(ram_oe), .ram_we_n(ram_we));
assign ram_data = !ram_cs && !ram_oe && ram_we ? memory[ram_addr[14:0]] : 16'hzzzz;
always @(posedge ram_we) if (!reset && !ram_cs) memory[ram_addr[14:0]]=ram_data;
always @(posedge clk) begin
    if (!reset && dut.core.timer_bus.counter.i_cs && dut.core.timer_bus.counter.i_we &&
        (|dut.core.timer_bus.counter.i_be)) timer_writes=timer_writes+1;
    if (!reset && irq) $fatal(1,"disabled timer generated IRQ");
end

task write_byte_model(input integer address, input [7:0] value);
begin
    if (address < 65524) reference[address]=value;
    else if (address == 65524) reference[address]=value & 7;
end
endtask

// Keep BS continuously active between calls, including register crossings.
task access(input [15:0] address, input [15:0] value, input [1:0] lanes, input wr);
reg [15:0] expected;
begin
    @(negedge clk); addr=address; data=value; bs=lanes; we=wr;
    expected={lanes[1] ? reference[(address+1)&65535] : 8'b0,
              lanes[0] ? reference[address] : 8'b0};
    saved_writes=timer_writes;
    expected_writes=0;
    if (wr) begin
        if (lanes[0] && address>=16'hfff0 && address<=16'hfff5) expected_writes=1;
        if (lanes[1] && address>=16'hffef && address<=16'hfff4 &&
            (!lanes[0] || address<16'hfff0 || address[0])) expected_writes=expected_writes+1;
    end
    n=0;
    do begin
        @(posedge clk); n=n+1;
        if (n>50) $fatal(1,"timer MMIO timeout at %h", address);
    end while (!ack);
    if (!wr && result!==expected)
        $fatal(1,"timer MMIO read %h mask=%b got=%h expected=%h",address,lanes,result,expected);
    if (wr) begin
        if (lanes[0]) write_byte_model(address,value[7:0]);
        if (lanes[1]) write_byte_model((address+1)&65535,value[15:8]);
    end
    #1;
    if (timer_writes-saved_writes!=expected_writes)
        $fatal(1,"timer MMIO write count %h got=%0d expected=%0d",
               address,timer_writes-saved_writes,expected_writes);
end
endtask

initial begin
    for(j=0;j<32768;j=j+1) begin
        memory[j]=16'ha55a;
        reference[2*j]=8'h5a; reference[2*j+1]=8'ha5;
    end
    for(j=65520;j<65533;j=j+1) reference[j]=0;
    repeat(3) @(negedge clk); reset=0;
    for(a=65519;a<=65526;a=a+1) begin
        for(mask=1;mask<=3;mask=mask+1) begin
            access(16'hfff0,16'h1234,3,1);
            access(16'hfff2,16'h5678,3,1);
            access(16'hfff4,16'h0006,3,1);
            access(a[15:0],0,mask[1:0],0);
            // Both bytes even: CSR.ENABLE stays clear for static comparisons.
            access(a[15:0],16'haa56,mask[1:0],1);
            access(a[15:0],0,mask[1:0],0);
            access(16'hfff0,0,3,0);
            access(16'hfff2,0,3,0);
            access(16'hfff4,0,3,0);
        end
    end
    @(negedge clk); bs=0;
    repeat(3) @(negedge clk);
    if(ack || !ram_cs || !ram_oe || !ram_we) $fatal(1,"bus active while idle");
    for(j=65520/2;j<32768;j=j+1)
        if(memory[j]!==16'ha55a) $fatal(1,"MMIO changed hidden SRAM at %h",j);
    $display("PASS timer MMIO masks, crossings, write counts, SRAM isolation");
    $finish;
end
endmodule
