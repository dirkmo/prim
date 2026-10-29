`timescale 1ns/1ps
module tb_uart_buffers;
reg clk=0, reset=1;
always #5 clk=~clk;
reg [7:0] rx=0;
reg rx_valid=0, pop=0, out_valid=0, ready=0;
reg [6:0] out_data=0;
wire [6:0] input_data, tx_data;
wire [3:0] status;
reg [7:0] csr_data=0;
reg csr_write=0;
wire irq;
wire output_ready, tx_valid;
uart_buffers dut(.i_clk(clk),.i_reset(reset),.i_rx_data(rx),.i_rx_valid(rx_valid),
    .i_input_read(pop),.o_input_data(input_data),.o_csr(status),
    .i_csr_data(csr_data),.i_csr_write(csr_write),.o_irq(irq),
    .i_output_data(out_data),.i_output_valid(out_valid),.o_output_ready(output_ready),
    .o_tx_data(tx_data),.o_tx_valid(tx_valid),.i_tx_ready(ready));
task tick; @(posedge clk); @(negedge clk); endtask
initial begin
    tick(); reset=0;
    if(status!=2 || input_data!=0) $fatal(1,"reset");
    rx=8'h41;rx_valid=1;tick();rx_valid=0;
    if(status!=3 || input_data!=7'h41) $fatal(1,"CPU reception");
    pop=1;tick();pop=0;
    if(status!=2 || input_data!=7'h41) $fatal(1,"last byte retained");
    rx=8'hc2;rx_valid=1;tick();rx_valid=0;
    if(status!=2 || input_data!=7'h41) $fatal(1,"debug byte leaked");
    rx=8'h00;rx_valid=1;pop=1;tick();rx_valid=0;pop=0;
    if(status!=3 || input_data!=0) $fatal(1,"new NUL lost during read");
    rx=8'h44;rx_valid=1;tick();rx_valid=0;
    if(input_data!=7'h44 || status!=3) $fatal(1,"overwrite");
    out_data=7'h55;out_valid=1;tick();out_valid=0;
    if(output_ready || !tx_valid || tx_data!=7'h55 || status!=1) $fatal(1,"TX enqueue");
    out_data=7'h66;out_valid=1;repeat(4) tick();out_valid=0;
    if(tx_data!=7'h55) $fatal(1,"TX backpressure");
    ready=1;tick();ready=0;
    if(!output_ready || tx_valid || status!=3) $fatal(1,"TX dequeue");
    reset=1;tick();
    if(input_data!=0 || status!=2 || tx_valid) $fatal(1,"global reset");
    reset=0;
    // Enabling on an idle UART does not synthesize an event; RO bits ignored.
    csr_data=8'hff;csr_write=1;tick();csr_write=0;
    if(status!=14 || irq) $fatal(1,"CSR mask or retroactive IRQ");
    rx=8'hc1;rx_valid=1;tick();rx_valid=0;
    if(irq || status!=14) $fatal(1,"debug RX interrupt");
    rx=8'h41;rx_valid=1;tick();rx_valid=0;
    if(!irq || status!=15) $fatal(1,"enabled RX interrupt");
    tick();if(irq) $fatal(1,"RX interrupt held");
    rx=8'h42;rx_valid=1;pop=1;tick();rx_valid=0;pop=0;
    if(!irq || status!=15 || input_data!=7'h42) $fatal(1,"RX overwrite/read event");
    out_valid=1;tick();out_valid=0;
    if(irq || status!=13) $fatal(1,"enqueue caused IRQ");
    repeat(4) begin tick();if(irq) $fatal(1,"pending TX caused IRQ");end
    ready=1;tick();
    if(!irq || status!=15) $fatal(1,"TX free event missing");
    tick();ready=0;if(irq) $fatal(1,"empty TX repeats IRQ");
    // RX-only: TX dequeue must stay quiet.
    csr_data=4;csr_write=1;tick();csr_write=0;
    out_valid=1;tick();out_valid=0;ready=1;tick();ready=0;
    if(irq) $fatal(1,"TXIE disabled");
    // TX-only: RX stays quiet, simultaneous RX and TX still produces TX IRQ.
    csr_data=8;csr_write=1;tick();csr_write=0;
    rx_valid=1;tick();rx_valid=0;if(irq) $fatal(1,"RXIE disabled");
    out_valid=1;tick();out_valid=0;ready=1;rx_valid=1;tick();ready=0;rx_valid=0;
    if(!irq) $fatal(1,"simultaneous RX/TX");
    reset=1;tick();if(irq || status!=2) $fatal(1,"IRQ reset");
    reset=0;
    // A simultaneous enable write uses the old enables for this event.
    csr_data=4;csr_write=1;rx_valid=1;tick();csr_write=0;rx_valid=0;
    if(irq || status!=7) $fatal(1,"enable write replayed RX event");
    tick();if(irq) $fatal(1,"full RX generated retroactive IRQ");
    csr_data=0;csr_write=1;rx_valid=1;tick();csr_write=0;rx_valid=0;
    if(!irq || status!=3) $fatal(1,"disable edge must use old enable");
    tick();if(irq) $fatal(1,"IRQ not cleared after disable");
    $display("PASS UART buffers");$finish;
end
endmodule
