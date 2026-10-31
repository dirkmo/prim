`timescale 1ns/1ps
// Port-only contract test; runs unchanged against RTL and mapped iCE40 cells.
module tb_audio_contract;
reg clk=0, reset=1, cs=0, we=0;
always #5 clk=~clk;
reg [3:0] addr=0;
reg [7:0] data=0;
wire [7:0] rd;
wire ready,pwm;
audio dut(.i_clk(clk),.i_reset(reset),.i_cs(cs),.i_we(we),.i_addr(addr),
 .i_data(data),.o_data(rd),.o_ready(ready),.o_pwm(pwm));
task write_reg(input [3:0] a,input [7:0] d);
integer waited;
begin
 @(negedge clk);cs=1;we=1;addr=a;data=d;#1;waited=0;
 while(!ready)begin @(negedge clk);#1;waited=waited+1;
  if(waited>600)$fatal(1,"write timeout");end
 @(negedge clk);cs=0;we=0;
end endtask
task read_reg(input[3:0]a,input[7:0] expected);
begin
 @(negedge clk);addr=a;we=0;cs=1;#1;
 if(!ready || rd!==expected)$fatal(1,"read %d got=%h expected=%h ready=%b",a,rd,expected,ready);
 @(negedge clk);cs=0;
end endtask
task pwm_count(input integer expected);
integer n,ones;
begin
 repeat(1024)@(negedge clk);ones=0;
 for(n=0;n<256;n=n+1)begin @(negedge clk);ones=ones+pwm;end
 if(ones!==expected)$fatal(1,"PWM average got=%0d expected=%0d",ones,expected);
end endtask
integer i;
initial begin
 repeat(3)@(negedge clk);reset=0;
 // System reset clears EBR through its write port; accesses wait for 32 clocks.
 write_reg(0,1);write_reg(3,15);write_reg(7,128);write_reg(10,2);
 // Pending must be observable without blocking a read; writing a new parameter
 // waits, then affects staging alone. The preceding trigger retains duty 128.
 @(negedge clk);addr=11;we=0;#1;
 if(!ready || rd[7:4]==0)$fatal(1,"pending/read readiness");
 write_reg(7,0);pwm_count(157);
 // VOICE changes target only; staging duty=0 and volume=15 remain visible.
 write_reg(1,1);read_reg(7,0);read_reg(3,15);write_reg(10,2);
 pwm_count(128); // voice0 +1905, voice1 -1905
 write_reg(1,0);read_reg(7,0); // no bank restoration on selecting old voice
 pwm_count(128); // selection itself cannot modify playback
 write_reg(1,2);write_reg(2,1);write_reg(3,8);write_reg(10,2);
 pwm_count(112); // add triangle -128*8
 write_reg(1,3);write_reg(2,4);write_reg(3,4);
 write_reg(8,0);write_reg(9,2);write_reg(10,2);
 pwm_count(119); // add seeded noise +127*4 before first millisecond tick
 repeat(25000*10)@(negedge clk);read_reg(11,7); // noise decay complete
 pwm_count(112);
 // Arbitrary partial RATE staging writes have no playback effect until APPLY.
 write_reg(4,255);write_reg(5,255);write_reg(6,255);pwm_count(112);
 write_reg(10,15);pwm_count(128);read_reg(11,0); // STOP ALL wins
 // Reset a dirty RAM, including an interrupted command, then replay a tone.
 write_reg(10,2);@(negedge clk);reset=1;
 repeat(2)@(negedge clk);reset=0;
 write_reg(0,1);read_reg(1,0);read_reg(2,0);read_reg(3,0);
 write_reg(3,15);write_reg(7,128);write_reg(10,2);pwm_count(157);
 $display("PASS port-only audio contract: common staging, isolated voices, EBR reset, envelopes and PWM");$finish;
end
initial begin #10000000;$fatal(1,"watchdog");end
endmodule
