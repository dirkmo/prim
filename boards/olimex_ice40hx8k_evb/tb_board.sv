`timescale 1ns/1ps
module tb_board;
reg clk=0, button_n=1, rx=1;
always #5 clk=~clk;
wire tx, cs, oe, we;
wire [1:0] leds;
wire halted = dut.system.halted;
wire [17:0] addr;
wire [15:0] data;
olimex_ice40hx8k_evb dut(.clk_100mhz(clk), .button_n(button_n), .uart_rx(rx), .uart_tx(tx),
    .ps2_clk(1'b1), .ps2_data(1'b1),
    .leds(leds), .sram_addr(addr), .sram_data(data),
    .sram_cs_n(cs), .sram_oe_n(oe), .sram_we_n(we));
reg [15:0] mem[0:32767];
assign data = !cs && !oe && we ? mem[addr[14:0]] : 16'hzzzz;
always @(posedge we) if(!cs) mem[addr[14:0]]=data;
always @(posedge clk) if(addr[17:15]!==0) $fatal(1,"upper SRAM address not tied low");
localparam DIV=217; // 25 MHz / 115200, rounded
task send(input [7:0] c);
    @(negedge dut.clk_sys); rx=0; repeat(DIV) @(negedge dut.clk_sys);
    for(integer k=0;k<8;k=k+1) begin rx=c[k]; repeat(DIV) @(negedge dut.clk_sys); end
    rx=1; repeat(DIV) @(negedge dut.clk_sys);
endtask
reg [7:0] reply[0:7];
integer received=0;
reg [7:0] value;
always begin
    @(negedge tx); repeat(DIV/2) @(negedge dut.clk_sys);
    for(integer k=0;k<8;k=k+1) begin repeat(DIV) @(negedge dut.clk_sys); value[k]=tx; end
    repeat(DIV) @(negedge dut.clk_sys);
    if(tx!==1) $fatal(1,"stop");
    reply[received]=value;received=received+1;
end
initial begin
    // CPU program: 1/2/3 0xfffd c!, then BREAK (little-endian words).
    mem[0]=16'h0120; mem[1]=16'hfd21; mem[2]=16'h1fff;
    mem[3]=16'h0220; mem[4]=16'hfd21; mem[5]=16'h1fff;
    mem[6]=16'h0320; mem[7]=16'hfd21; mem[8]=16'h1fff;
    mem[9]=16'h0022;
    // Model clocks run before LOCK; reset must remain asserted throughout.
    repeat(8) @(negedge clk);
    if(dut.pll_locked || !dut.reset || !cs || !we || !oe)
        $fatal(1,"system released before PLL lock");
    wait(dut.pll_locked);
    if(!dut.reset) $fatal(1,"reset needs synchronized lock release");
    wait(!dut.reset);
    repeat(8) @(negedge dut.clk_sys);
    if(!halted || dut.system.pc!=0 || !cs || !oe || !we || !tx)
        $fatal(1,"power-up must halt before first SRAM access");
    if (leds !== 0) $fatal(1,"LED power-up reset");
    send(8'hbf); // debug '?'
    wait(received==2);
    if(reply[0]!=8'hd4 || reply[1]!=8'hb1) $fatal(1,"startup status");
    // Start the real CPU through the debug UART RUN command.
    fork
        send(8'hc7); // 'G' with debug-channel bit set
        begin
            wait(leds == 1);
            wait(leds == 2);
            wait(leds == 3);
            wait(halted);
        end
    join
    @(negedge dut.clk_sys); button_n=0;
    repeat(16) @(negedge dut.clk_sys); button_n=1;
    repeat(16) @(negedge dut.clk_sys);
    if(!halted || dut.system.pc!=0 || mem[0]!=16'h0120 || leds !== 0)
        $fatal(1,"button reset");
    // A loss of lock must reassert reset, then drain the reset pipe again.
    force dut.pll_locked=0;
    repeat(8) @(negedge dut.clk_sys);
    if(!dut.reset || !cs || !oe || !we) $fatal(1,"PLL lock-loss reset");
    release dut.pll_locked;
    wait(!dut.reset);
    repeat(8) @(negedge dut.clk_sys);
    if(!halted || dut.system.pc!=0 || mem[0]!=16'h0120)
        $fatal(1,"PLL lock recovery");
    $display("PASS board PLL reset and startup halt"); $finish;
end
initial begin #1000000; $fatal(1,"board timeout"); end
endmodule
