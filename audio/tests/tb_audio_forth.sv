`timescale 1ns/1ps
// Compiled Forth check on Prim, physical SRAM bus and system/audio MMIO.
module tb_audio_forth;
reg clk=0,reset=1;
always #5 clk=~clk;
wire [15:0] addr,data,rd,pc,ram_addr,ram_data;
wire [1:0] bs;
wire we,ack,cs,oe,wr,halted,pwm;
reg [15:0] ram[0:65535];
reg [7:0] rx[0:16383];
reg [6:0] rx_data=0;
reg rx_valid=0;
wire [6:0] input_data,output_data,tx_data;
wire [3:0] csr;
wire [7:0] csr_data;
wire input_read,output_valid,output_ready,csr_write,tx_valid;
integer count,rx_index=0,cycles=0,quiet=0,waitpc,tx_file,i,ram_file;
string image_path,rx_path,tx_path,ram_path;
assign ram_data=(!cs && !oe && wr) ? ram[ram_addr] : 16'bz;
always @(posedge wr) if(!cs) ram[ram_addr]=ram_data;
wire halt_request = pc==4 && cpu.r_phase==0;
Prim cpu(.i_clk(clk),.i_reset(reset),.i_halt(halt_request),.i_run(1'b0),.i_step(1'b0),
 .i_debug_reset(1'b0),.i_irq(1'b0),.o_addr(addr),.o_dat(data),.i_dat(rd),.o_bs(bs),
 .o_we(we),.i_ack(ack),.o_pc(pc),.o_halted(halted));
uart_buffers uart(.i_clk(clk),.i_reset(reset),.i_rx_data(rx_data),.i_rx_valid(rx_valid),
 .i_input_read(input_read),.o_input_data(input_data),.o_csr(csr),.i_csr_data(csr_data),
 .i_csr_write(csr_write),.i_output_data(output_data),.i_output_valid(output_valid),
 .o_output_ready(output_ready),.o_tx_data(tx_data),.o_tx_valid(tx_valid),.i_tx_ready(1'b1));
memory_io #(.AUDIO_ENABLE(1),.CLK_HZ(25000000)) io(
 .i_clk(clk),.i_reset(reset),.i_addr(addr),.i_cpu_to_mem(data),.i_bs(bs),.i_we(we),
 .o_mem_to_cpu(rd),.o_ack(ack),.i_output_ready(output_ready),.i_input_data(input_data),
 .i_uart_csr(csr),.o_uart_csr_data(csr_data),.o_uart_csr_write(csr_write),
 .o_input_read(input_read),.o_output_data(output_data),.o_output_valid(output_valid),
 .i_ps2_clk(1'b1),.i_ps2_data(1'b1),.i_uart_rx_irq(1'b0),.i_uart_tx_irq(1'b0),
 .ram_addr(ram_addr),.ram_data(ram_data),.ram_cs_n(cs),.ram_oe_n(oe),.ram_we_n(wr),.o_audio_pwm(pwm));
wire [111:0] voice_state [0:3];
genvar v,w;
generate for(v=0;v<4;v=v+1)begin: inspect_voice
 for(w=0;w<7;w=w+1)begin: inspect_word
  assign voice_state[v][w*16+:16] = io.sound.generator.state_ram[v*8+w];
 end
end endgenerate
always @(negedge clk) begin
 rx_valid=0;
 if(!reset && !csr[0] && rx_index<count) begin
  rx_data=rx[rx_index];rx_index=rx_index+1;rx_valid=1;
 end
end
always @(posedge clk) if(!reset) begin
 cycles=cycles+1;

 if(cycles>20000000)$fatal(1,"Forth audio timeout, consumed=%0d/%0d pc=%h",rx_index,count,pc);
 if(tx_valid)$fwrite(tx_file,"%02x\n",tx_data);
 if(halted)quiet=quiet+1;
 if(quiet==1024)begin
  if(io.core.timer_bus.counter.count < 3)$fatal(1,"audio timer delay did not elapse");
  if(io.core.timer_bus.counter.compare !== 16'hffff ||
     io.core.timer_bus.counter.csr !== 3'b011)$fatal(1,"audio timer setup");
  if(voice_state[0][30:7]!==24'd75590)$fatal(1,"440 Hz driver rate %d",voice_state[0][30:7]);
  if(voice_state[0][1:0]!==1)$fatal(1,"triangle driver");
  if(voice_state[1][30:7]!==24'd89849)$fatal(1,"523 Hz driver rate %d",voice_state[1][30:7]);
  if(voice_state[2][30:7]!==24'h123456)$fatal(1,"24-bit raw rate");
  if(voice_state[3][30:7]!==24'd687187)$fatal(1,"noise rate %d, staging=%d pending=%b",voice_state[3][30:7],io.sound.generator.staging[30:7],io.sound.generator.pending);
  if(voice_state[3][2]!==1)$fatal(1,"noise envelope");
  ram_file=$fopen(ram_path,"w");
  for(i=0;i<32768;i=i+1)$fwrite(ram_file,"%04x\n",ram[i]);
  $fclose(ram_file);$fclose(tx_file);
  $display("PASS Forth audio driver on CPU/SRAM/system/audio RTL");$finish;
 end
end
initial begin
 if(!$value$plusargs("image=%s",image_path)||!$value$plusargs("rx=%s",rx_path)||
 !$value$plusargs("count=%d",count)||!$value$plusargs("waitpc=%d",waitpc)||
 !$value$plusargs("tx=%s",tx_path)||!$value$plusargs("ram=%s",ram_path))$fatal(1,"arguments");
 $readmemh(image_path,ram,0,32767);if(count>0)$readmemh(rx_path,rx,0,count-1);
 tx_file=$fopen(tx_path,"w");repeat(3)@(negedge clk);reset=0;
end
endmodule
