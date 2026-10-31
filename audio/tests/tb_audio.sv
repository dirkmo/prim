`timescale 1ns/1ps
module tb_audio;
reg clk=0, reset=1, cs=0, we=0;
always #5 clk=~clk;
reg [3:0] addr=0;
reg [7:0] data=0;
wire [7:0] rd;
wire pwm;
wire ready;
audio #(.CLK_HZ(256000)) dut(clk,reset,cs,we,addr,data,rd,ready,pwm);
task write_reg(input [3:0] a,input [7:0] d);
begin @(negedge clk); cs=1;we=1;addr=a;data=d;#1;
 while(!ready) @(negedge clk);
 @(negedge clk);cs=0;we=0;end
endtask
task frames(input integer n);
begin repeat(n) begin @(negedge clk); while(dut.counter!=0) @(negedge clk); repeat(145) @(negedge clk); end end
endtask
task check(input bit ok,input string why);
begin if(!ok) $fatal(1,"%s",why); end
endtask
wire [111:0] voice_state [0:3];
genvar v,w;
generate for(v=0;v<4;v=v+1)begin: inspect_voice
 for(w=0;w<7;w=w+1)begin: inspect_word
  assign voice_state[v][w*16+:16] = dut.state_ram[v*8+w];
 end
end endgenerate
integer i,j,count;
reg [23:0] saved;
reg [14:0] seed;
reg [32767:0] seen;
initial begin
 repeat(3) @(negedge clk);reset=0;
 frames(2);check(dut.duty==128,"reset silence");
 write_reg(0,1);write_reg(3,15);write_reg(4,0);write_reg(5,0);write_reg(6,64);write_reg(7,128);
 write_reg(10,2);write_reg(5,99); // post-command staging must not alter snapshot
 frames(2);check(voice_state[0][30:7]==24'h400000,"snapshot rate");
 check(voice_state[0][82:79]==15,"constant level");
 saved=voice_state[0][78:55];frames(1);check(voice_state[0][78:55]==saved+24'h400000,"phase increment");
 // Single pulse voice: +/-1905 normalized down by 64 -> duty 98 or 157.
 frames(1);check(dut.duty==98 || dut.duty==157,"pulse mixer amplitude");
 // Muting must preserve phase progression and produce exactly midpoint PWM.
 write_reg(0,3);frames(2);check(dut.duty==128,"mute duty");count=0;
 repeat(256) begin @(negedge clk);count=count+pwm;end
 check(count==128,"midpoint PWM average");write_reg(0,1);
 // Four full-volume negative voices: sum -7635, no arithmetic wrap.
 for(i=0;i<4;i=i+1) begin
  write_reg(1,i);write_reg(2,0);write_reg(3,15);write_reg(4,0);write_reg(5,0);write_reg(6,0);write_reg(7,0);write_reg(10,2);
 end
 frames(3); // Noise seed is positive, tones negative: (-5715+1905)>>6 = -60.
 check(dut.duty==68,"four-voice sum");
 // Stop beats trigger, latest command wins, no phantom activity.
 write_reg(10,6);frames(2);check(voice_state[3][82:79]==0,"stop priority");
 write_reg(10,8);frames(2);check(dut.playing==0,"global stop");check(dut.duty==128,"stopped silence");
 // Attack / decay, zero-rate endpoints and retrigger.
 write_reg(1,0);write_reg(2,4);write_reg(3,3);write_reg(8,1);write_reg(9,1);write_reg(10,2);
 frames(1);check(voice_state[0][84:83]==1,"attack starts");
 repeat(256*8) @(negedge clk);check(voice_state[0][82:79]==0 && voice_state[0][84:83]==0,"envelope completes");
 write_reg(8,0);write_reg(9,10);write_reg(10,2);frames(1);check(voice_state[0][82:79]==3,"instant attack");
 write_reg(10,2);frames(1);check(voice_state[0][78:55]==0,"retrigger phase reset");
 // Waveforms at known phases, shared scaler sees signed endpoints.
 write_reg(2,1);write_reg(3,15);write_reg(10,2);frames(2);
 check(dut.duty==98,"triangle negative endpoint");
 write_reg(2,2);write_reg(10,2);frames(2);check(dut.duty==98,"saw negative endpoint");
 // Independently count the specified LFSR's complete sequence.
 seed=1;seen=0;
 for(j=0;j<32767;j=j+1) begin
  check(seed!=0 && !seen[seed],"LFSR period");seen[seed]=1;
  seed={seed[13:0],seed[14]^seed[13]};
 end
 check(seed==1,"LFSR returns after 32767");
 // Actual noise advances on overflow and retrigger seeds deterministically.
 write_reg(1,3);write_reg(2,0);write_reg(3,15);write_reg(4,255);write_reg(5,255);write_reg(6,255);write_reg(10,2);
 frames(1);check(dut.lfsr==1,"noise seed");frames(2);check(dut.lfsr==4,"noise shift on carry");
 // Read masks and reserved registers.
 write_reg(0,255);addr=0;#1;check(rd==15,"master mask");
 write_reg(1,255);addr=1;#1;check(rd==3,"voice mask");
 for(i=12;i<16;i=i+1) begin write_reg(i,255);addr=i;#1;check(rd==0,"reserved");end
 reset=1;@(negedge clk);reset=0;frames(2);check(dut.duty==128 && dut.playing==0,"system reset");
 $display("PASS audio synthesis, envelopes, snapshot, mixer, noise and PWM");$finish;
end
initial begin #100000000;$fatal(1,"watchdog");end
endmodule
