`timescale 1ns/1ps
module tb_uart_duplex;
localparam DIV=8;
reg clk=0, reset=1, rx=1;
always #5 clk=~clk;
wire tx, halted, cs, oe, we;
wire [15:0] addr, data;
prim_system #(.CLK_HZ(115200*DIV),.READ_CYCLES(4),.WRITE_CYCLES(5)) dut(
    .i_clk(clk),.i_reset(reset),.i_rx(rx),.o_tx(tx),.o_halted(halted),
    .ram_addr(addr),.ram_data(data),.ram_cs_n(cs),.ram_oe_n(oe),.ram_we_n(we));
reg [15:0] memory[0:32767];
assign data=!cs&&!oe&&we ? memory[addr[14:0]] : 16'hzzzz;
always @(posedge we) if(!cs&&!reset) memory[addr[14:0]]=data;
reg [7:0] code[0:22];
reg [7:0] debug_rx[0:63], echoes[0:15], byte_rx;
integer debug_count=0, echo_count=0, position=0;
always begin
    @(negedge tx);repeat(DIV/2) @(negedge clk);
    for(integer k=0;k<8;k=k+1) begin repeat(DIV) @(negedge clk);byte_rx[k]=tx;end
    repeat(DIV) @(negedge clk);
    if(tx!==1) $fatal(1,"UART stop");
    if(byte_rx[7]) begin debug_rx[debug_count]=byte_rx&127;debug_count=debug_count+1;end
    else begin echoes[echo_count]=byte_rx;echo_count=echo_count+1;end
end
task send(input [7:0] b);
    @(negedge clk);rx=0;repeat(DIV) @(negedge clk);
    for(integer k=0;k<8;k=k+1) begin rx=b[k];repeat(DIV) @(negedge clk);end
    rx=1;repeat(DIV) @(negedge clk);
endtask
task command(input [7:0] c,input string expected);
    send(c|128);
    for(integer k=0;k<expected.len();k=k+1) begin
        wait(debug_count>position);
        if(debug_rx[position]!==expected[k]) $fatal(1,"duplex reply %c got %c",expected[k],debug_rx[position]);
        position=position+1;
    end
endtask
initial begin
    // Poll received bit, read/echo FFFF, loop. No debug-specific CPU instructions.
    code[0]=8'h21;code[1]=8'hfe;code[2]=8'hff;code[3]=8'h1d;
    code[4]=8'h20;code[5]=1;code[6]=4;
    code[7]=8'h21;code[8]=0;code[9]=0;code[10]=3;
    code[11]=8'h21;code[12]=8'hff;code[13]=8'hff;code[14]=8'h1d;
    code[15]=8'h21;code[16]=8'hff;code[17]=8'hff;code[18]=8'h1f;
    code[19]=8'h21;code[20]=0;code[21]=0;code[22]=2;
    for(integer k=0;k<32768;k=k+1) memory[k]=0;
    for(integer k=0;k<23;k=k+1) memory[k/2][(k%2)*8+:8]=code[k];
    repeat(4) @(negedge clk);reset=0;
    send(8'h41);
    command("?","T0"); // CPU echo may appear between debug reply bytes.
    wait(echo_count==1);if(echoes[0]!=8'h41) $fatal(1,"first echo");
    command("q","K2");
    command("H","K");
    if(!halted || dut.cpu_bs!=0) $fatal(1,"HALT while echoing");
    send(8'h00); // NUL remains buffered while CPU is halted.
    command("q","K3");command("?","T1");
    command("Z","K");command("q","K3"); // CPU-only reset retains UART RX.
    command("G","K");
    wait(echo_count==2);if(echoes[1]!=0) $fatal(1,"retained NUL echo");
    command("q","K2");
    send(8'h7f);command("?","T0");
    wait(echo_count==3);if(echoes[2]!=8'h7f) $fatal(1,"DEL echo");
    command("H","K");
    $display("PASS simultaneous CPU/debug UART");$finish;
end
initial begin #2000000;$fatal(1,"duplex timeout");end
endmodule
