`timescale 1ns/1ps
// Real serial and PS/2 wires -> CPU + SRAM + shared IRQ -> UART and VGA RAM.
module tb_dual_system;
localparam DIV=217, HALF=625; // 25 MHz system, 115200 UART, 20 kHz PS/2.
`include "opcodes.v"
reg clk=0, reset=1, rx=1, psclk=1, psdata=1;
always #20 clk=~clk;
wire tx, halted, cs, oe, we, pixel;
wire [15:0] ram_addr, ram_data;
prim_system #(.CLK_HZ(25000000), .VGA_ENABLE(1), .PS2_ENABLE(1),
    .READ_CYCLES(3), .WRITE_CYCLES(3)) dut(
    .i_clk(clk), .i_reset(reset), .i_rx(rx), .o_tx(tx), .o_halted(halted),
    .i_ps2_clk(psclk), .i_ps2_data(psdata), .o_vga_pixel(pixel),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(cs), .ram_oe_n(oe), .ram_we_n(we));
reg [15:0] memory[0:32767];
assign ram_data=!cs&&!oe&&we ? memory[ram_addr[14:0]] : 16'hzzzz;
always @(posedge we) if(!reset&&!cs) memory[ram_addr[14:0]]=ram_data;
reg [7:0] expected[0:1023], keys[0:1023], debug_bytes[0:4095], video_snapshot[0:4095];
reg [7:0] received;
integer cpu_count=0, debug_count=0, position=0, key_position=0, expected_count;
integer k0,k1,k2,k3,k4,k5,waitpc,keypc,idlepc,cycles=0,tx_file,irq_entries=0,pixels=0;
integer ds=0,rs=0,max_ds=0,max_rs=0;
reg in_isr=0;
reg [6:0] opcode;
string image_path, expected_path, keys_path, output_path;

always begin
    @(negedge tx); repeat(DIV/2) @(negedge clk);
    for(integer j=0;j<8;j=j+1) begin repeat(DIV) @(negedge clk); received[j]=tx; end
    repeat(DIV) @(negedge clk);
    if(tx!==1) $fatal(1,"UART stop bit");
    if(received[7]) begin
        if(debug_count>=4096) $fatal(1,"debug capture overflow");
        debug_bytes[debug_count]=received&127; debug_count=debug_count+1;
    end else begin
        if(cpu_count>=expected_count || received!==expected[cpu_count])
            $fatal(1,"UART output %0d got=%h expected=%h",cpu_count,received,expected[cpu_count]);
        $fwrite(tx_file,"%02x\n",received); cpu_count=cpu_count+1;
    end
end
task uart_byte(input [7:0] value);
    @(negedge clk); rx=0; repeat(DIV) @(negedge clk);
    for(integer j=0;j<8;j=j+1) begin rx=value[j]; repeat(DIV) @(negedge clk); end
    rx=1; repeat(DIV) @(negedge clk);
endtask
function integer digit(input [7:0] value);
    if(value>="0" && value<="9") digit=value-"0";
    else if(value>="a" && value<="f") digit=value-"a"+10;
    else digit=-1;
endfunction
task credit;
    integer status;
    status=1;
    while(status&1) begin
        uart_byte("q"|128); wait(debug_count>=position+2);
        if(debug_bytes[position]!=="K") $fatal(1,"credit reply");
        status=digit(debug_bytes[position+1]); position=position+2;
        if(status<0) $fatal(1,"credit status");
    end
endtask
task uart_text(input string text);
    for(integer j=0;j<text.len();j=j+1) begin credit(); uart_byte(text[j]); end
endtask
task psbit(input bit value);
    psdata=value; repeat(HALF) @(negedge clk); psclk=0;
    repeat(HALF) @(negedge clk); psclk=1;
endtask
task psbyte(input [7:0] value);
    psbit(0);
    for(integer j=0;j<8;j=j+1) psbit(value[j]);
    psbit(~^value); psbit(1); psdata=1; repeat(HALF) @(negedge clk);
endtask
task keyboard_text(input integer count);
    for(integer j=0;j<count;j=j+1) begin psbyte(keys[key_position]); key_position=key_position+1; end
endtask
task quiet;
    @(negedge clk);
    wait(dut.pc==waitpc && !dut.io.keyboard.fifo.count && !dut.uart_csr[0] &&
         memory['hf100/2]==memory['hf102/2] && memory['hf180/2]==memory['hf182/2] &&
         memory['hf202/2]==0 && memory['hf302/2]==0 && dut.uart.tx.o_ready && dut.uart_csr[1]);
endtask
task row_check(input integer row,input string text);
    integer physical;
    physical=((row+dut.io.video.display.row_offset)&31)*80;
    for(integer j=0;j<80;j=j+1)
        if(dut.io.video.display.ram[physical+j] !== (j<text.len() ? text[j] : 8'h20))
            $fatal(1,"VGA row=%0d col=%0d got=%h text=%s",row,j,dut.io.video.display.ram[physical+j],text);
endtask
task snapshot;
    for(integer j=0;j<4096;j=j+1) video_snapshot[j]=dut.io.video.display.ram[j];
endtask
task unchanged;
    for(integer j=0;j<4096;j=j+1)
        if(video_snapshot[j]!==dut.io.video.display.ram[j]) $fatal(1,"UART changed VGA RAM at %0d",j);
endtask

// Track occupied cells/frames, including CPU IRQ PC pushes. Errors/ABORT
// establish a new logical base at idle without resetting circular pointers.
always @(posedge clk) if(!reset) begin
    cycles=cycles+1;
    if(cycles>12000000) $fatal(1,"dual system timeout pc=%h UART=%0d",dut.pc,cpu_count);
    if(pixel) pixels=pixels+1;
    if(dut.pc==idlepc) begin ds=memory['h108/2]; rs=0; end
    if(dut.cpu.w_phase_execute && !halted) begin
        opcode=dut.cpu.r_ir[6:0];
        case(opcode)
            OP_PUSH,OP_PUSH8,OP_DUP,OP_OVER,OP_CARRY,OP_FROM_R: ds=ds+1;
            OP_JZ,OP_STORE,OP_BYTE_STORE: ds=ds-2;
            OP_CALL,OP_JP,OP_AND,OP_OR,OP_XOR,OP_ADD,OP_SUB,OP_LTS,OP_LTU,
            OP_NIP,OP_DROP,OP_TO_R,OP_INTAD: ds=ds-1;
        endcase
        if(opcode==OP_CALL || opcode==OP_INT || opcode==OP_TO_R) rs=rs+1;
        if(opcode==OP_FROM_R || opcode==OP_RDROP) rs=rs-1;
        if(dut.cpu.r_ir[7] && opcode!=OP_CALL && opcode!=OP_JP && opcode!=OP_JZ && opcode!=OP_INT)
            rs=rs-1;
        if(in_isr) begin
            if(opcode!=OP_INTDI && dut.cpu.r_int_enable)
                $fatal(1,"interrupts enabled inside ISR opcode=%h",opcode);
            if(dut.cpu.r_ir==(OP_INTEI|128)) in_isr=0;
        end
    end
    if(dut.cpu.w_phase_irq) begin
        if(in_isr) $fatal(1,"nested ISR entry");
        in_isr=1; rs=rs+1; irq_entries=irq_entries+1;
    end
    if(ds<0 || ds>32 || rs<0 || rs>32) $fatal(1,"physical stack budget DS=%0d RS=%0d",ds,rs);
    if(ds>max_ds) max_ds=ds;
    if(rs>max_rs) max_rs=rs;
end

integer saved_uart, final_uart, saved_irq, saved_tail;
reg [9:0] saved_h;
initial begin
    if(!$value$plusargs("image=%s",image_path) || !$value$plusargs("expected=%s",expected_path) ||
       !$value$plusargs("keys=%s",keys_path) || !$value$plusargs("output=%s",output_path) ||
       !$value$plusargs("expected_count=%d",expected_count) || !$value$plusargs("waitpc=%d",waitpc) ||
       !$value$plusargs("keypc=%d",keypc) || !$value$plusargs("idlepc=%d",idlepc) ||
       !$value$plusargs("k0=%d",k0) || !$value$plusargs("k1=%d",k1) || !$value$plusargs("k2=%d",k2) ||
       !$value$plusargs("k3=%d",k3) || !$value$plusargs("k4=%d",k4) ||
       !$value$plusargs("k5=%d",k5)) $fatal(1,"missing fixtures");
    $readmemh(image_path,memory);
    $readmemh(expected_path,expected,0,expected_count-1);
    $readmemh(keys_path,keys,0,k0+k1+k2+k3+k4+k5-1);
    memory['he000/2]=16'h1234; memory['he002/2]=16'h5678;
    tx_file=$fopen(output_path,"w");
    repeat(4) @(negedge clk); reset=0;
    wait(cpu_count==4); quiet(); row_check(0,"ok");
    saved_uart=cpu_count;
    keyboard_text(k0); quiet(); // : twice dup + ;
    row_check(1,": twice dup + ;"); row_check(2,"ok");
    if(cpu_count!=saved_uart) $fatal(1,"PS/2 definition leaked to UART");
    snapshot(); uart_text("7 twice .\015"); quiet(); unchanged();
    saved_uart=cpu_count;
    keyboard_text(k1); quiet(); // nope
    row_check(3,"nope"); row_check(4,"error: unknown word nope"); row_check(5,"ok");
    if(cpu_count!=saved_uart) $fatal(1,"local error leaked to UART");
    uart_text(": take key . ;\015take\015");
    wait(dut.pc==keypc); snapshot();
    keyboard_text(k2); // 9 . ; must remain queued while UART KEY waits.
    repeat(2000) @(negedge clk); unchanged();
    if(memory['hf000/2]!==0) $fatal(1,"KEY owner changed");
    credit(); uart_byte("A"); quiet();
    row_check(6,"9 ."); row_check(7,"9 ok");
    fork
        uart_text("2 .\015");
        keyboard_text(k3); // 3 .
    join
    quiet(); row_check(8,"3 ."); row_check(9,"3 ok");
    uart_text(": scroll 35 BEGIN CR 1- DUP 0= UNTIL DROP ;\015"); quiet();
    saved_uart=cpu_count;
    keyboard_text(k4); quiet(); // scroll
    row_check(28,"ok"); row_check(29,"");
    if(!dut.io.video.display.row_offset || dut.io.video.display.cursor_y!=29)
        $fatal(1,"VGA scroll/cursor");
    if(cpu_count!=saved_uart) $fatal(1,"local scroll leaked to UART");
    // A user word executes continuously while >16 physical PS/2 bytes arrive.
    // No KEY or collector polling can service the hardware FIFO here.
    memory['h5000/2]=0;
    uart_text(": busy BEGIN 20480 @ UNTIL ;\015"); quiet();
    uart_text("busy\015");
    wait(dut.cpu.w_phase_memop && dut.cpu.T==16'h5000 && !dut.cpu.o_we);
    snapshot(); saved_irq=irq_entries; saved_tail=memory['hf182/2];
    keyboard_text(k5);
    wait(!dut.io.keyboard.fifo.count && memory['hf182/2]==((saved_tail+k5)&63));
    unchanged();
    if(irq_entries<=saved_irq || memory['hf180/2]!=saved_tail || memory['hf184/2]!=0)
        $fatal(1,"asynchronous input was not buffered during busy word");
    @(negedge clk); memory['h5000/2]=1;
    quiet(); row_check(28,"1234 ok"); row_check(29,"");
    if(cpu_count!=expected_count) $fatal(1,"UART final length");
    if(memory['he000/2]!==16'h1234 || memory['he002/2]!==16'h5678 || dut.io.bank)
        $fatal(1,"VRAM mapping damaged SRAM or was left enabled");
    if(memory['h108/2]!==0 || memory['h112/2]!==0 || !irq_entries || !pixels)
        $fatal(1,"final depth/definition or missing IRQ/video activity");
    uart_byte("H"|128); wait(debug_count>position);
    if(debug_bytes[position]!=="K") $fatal(1,"HALT reply"); position=position+1;
    wait(halted); snapshot(); saved_h=dut.io.video.display.h;
    repeat(1000) @(negedge clk);
    if(dut.io.video.display.h==saved_h) $fatal(1,"VGA paused during HALT");
    uart_byte("Z"|128); wait(debug_count>position);
    if(debug_bytes[position]!=="K") $fatal(1,"RESET-HALT reply");
    unchanged();
    if(dut.uart_csr[2]!==1 || dut.io.ps2_csr[2]!==1 || !halted || dut.cpu.r_int_enable)
        $fatal(1,"CPU-only reset peripheral retention");
    $fclose(tx_file);
    $display("PASS dual Forth wires/SRAM/IRQ/VGA UART=%0d cycles=%0d DS=%0d RS=%0d IRQ=%0d",cpu_count,cycles,max_ds,max_rs,irq_entries);
    $finish;
end
endmodule
