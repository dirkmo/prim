`timescale 1ns/1ps
module tb_audio_mmio;
parameter ENABLED=1;
reg clk=0,reset=1;
always #5 clk=~clk;
reg [15:0] addr=0,data=0;
reg [1:0] bs=0;
reg we=0;
wire [15:0] rd,ram_data;
wire ack,cs,oe,wr,pwm;
wire [15:0] ram_addr;
reg [15:0] ram[0:65535];
assign ram_data=(!cs && !oe && wr) ? ram[ram_addr] : 16'bz;
always @(posedge wr) if(!cs) ram[ram_addr]=ram_data;
memory_io #(.AUDIO_ENABLE(ENABLED),.CLK_HZ(256000)) dut(
 .i_clk(clk),.i_reset(reset),.i_addr(addr),.i_cpu_to_mem(data),.i_bs(bs),.i_we(we),
 .o_mem_to_cpu(rd),.o_ack(ack),.i_output_ready(1'b1),.i_input_data(7'b0),.i_uart_csr(4'b0010),
 .i_ps2_clk(1'b1),.i_ps2_data(1'b1),.i_uart_rx_irq(1'b0),.i_uart_tx_irq(1'b0),
 .ram_addr(ram_addr),.ram_data(ram_data),.ram_cs_n(cs),.ram_oe_n(oe),.ram_we_n(wr),.o_audio_pwm(pwm));
task access(input[15:0] a,input[15:0] d,input[1:0] lanes,input bit write_it,input[15:0] expected);
integer n;
begin
 @(negedge clk);addr=a;data=d;bs=lanes;we=write_it;n=0;
 do begin @(posedge clk);n=n+1;if(n>600)$fatal(1,"ACK timeout");end while(!ack);
 if(!write_it && rd!==expected)$fatal(1,"read %h got %h expected %h",a,rd,expected);
 @(negedge clk);bs=0;we=0;
end endtask
integer i;

initial begin
 for(i=0;i<65536;i=i+1)ram[i]=16'h5a5a;
 repeat(3)@(negedge clk);reset=0;
 // Low SRAM byte, high master register. Verify hidden SRAM is preserved.
 access(16'hffdf,16'h0187,3,1,0);
 access(16'hffdf,0,3,0,ENABLED?16'h0187:16'h0087);
 if(ram[16'h7ff0]!==16'h5a5a)$fatal(1,"audio wrote physical SRAM");
 access(16'hffe1,16'h0702,3,1,0);
 access(16'hffe1,0,3,0,ENABLED?16'h0702:16'h0000);
 // High-only lane, masks, unaligned RATE writes, reserved-to-timer crossing.
 access(16'hffe2,16'hff00,2,1,0);
 access(16'hffe3,0,1,0,ENABLED?15:0);
 access(16'hffe4,16'h3412,3,1,0);
 access(16'hffe5,16'h7856,3,1,0);
 access(16'hffe4,0,3,0,ENABLED?16'h5612:0);
 access(16'hffe6,0,1,0,ENABLED?16'h0078:0);
 access(16'hffea,2,1,1,0);
 access(16'hffe4,16'habcd,3,1,0);
 access(16'hffe4,0,3,0,ENABLED?16'habcd:0);
 access(16'hffef,16'hbeef,3,1,0);
 access(16'hffef,0,3,0,16'hbe00);
 access(16'hfff0,0,1,0,16'h00be);
 // Wrapping access retains SRAM lane and UART lane behavior.
 access(16'hffff,16'h7441,3,1,0);
 access(0,0,1,0,16'h0074);
 @(negedge clk);addr=16'hffe0;data=0;bs=0;we=1;
 repeat(3)@(negedge clk);we=0;
 reset=1;@(negedge clk);reset=0;
 access(16'hffe0,0,3,0,0);
 $display("PASS audio integrated bus, enabled=%0d",ENABLED);$finish;
end
endmodule
