`timescale 1ns/1ps
module tb_vga;
reg clk=0, reset=1;
always #20 clk=~clk;
reg [15:0] addr=0, data=0;
reg [1:0] bs=0;
reg we=0;
wire [15:0] result, ram_addr, ram_data;
wire ack, cs, oe, wr, hs, vs, pixel, active;
reg [15:0] memory [0:32767];
integer i, cycles;
reg [15:0] value;
reg [7:0] expected_glyph;
reg [7:0] character;
reg [7:0] screen [0:4095];
reg [7:0] font [0:4095];
memory_io #(.VGA_ENABLE(1)) dut(
    .i_clk(clk), .i_reset(reset), .i_addr(addr), .i_cpu_to_mem(data),
    .i_bs(bs), .i_we(we), .o_mem_to_cpu(result), .o_ack(ack),
    .i_output_ready(1'b1), .i_input_data(7'b0), .i_uart_rx_irq(1'b0), .i_uart_tx_irq(1'b0), .i_uart_csr(4'b0010),
    .o_vga_hsync(hs), .o_vga_vsync(vs), .o_vga_pixel(pixel), .o_vga_active(active),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(cs), .ram_oe_n(oe), .ram_we_n(wr));
assign ram_data = !cs && !oe && wr ? memory[ram_addr[14:0]] : 16'hzzzz;
always @(posedge wr) if (!reset && !cs) memory[ram_addr[14:0]]=ram_data;

task access(input [15:0] address, input [15:0] payload, input [1:0] lanes, input writing);
begin
    @(negedge clk); addr=address; data=payload; bs=lanes; we=writing;
    cycles=0;
    do begin
        @(posedge clk); cycles=cycles+1;
        if(cycles>100) $fatal(1,"bus timeout %h", address);
    end while (!ack);
    value=result;
end
endtask

task read_check(input [15:0] address, input [1:0] lanes, input [15:0] expected);
begin
    access(address,0,lanes,0);
    if(value !== expected) $fatal(1,"read %h bs=%b got %h expected %h",address,lanes,value,expected);
end
endtask

task idle;
begin @(negedge clk); bs=0; we=0; end
endtask

// Independent raster scoreboard: the output's two-stage pipeline corresponds
// to source coordinate 0,0 one clock after reset is released.
task frame_check(input integer offset, input integer cx, input integer cy,
                 input integer cursor_mode);
integer xx, yy, t, row;
reg wanted, cursor_visible;
begin
    idle;
    // Synchronize to the delayed rising edge of VSYNC, raster line 492.
    @(posedge vs); @(negedge clk);
    xx=0; yy=492;
    // At this point output is x=0 of line 492 (check alignment below).
    for(t=0;t<800*525;t=t+1) begin
        if(hs !== !(xx>=656 && xx<752) || vs !== !(yy>=490 && yy<492))
            $fatal(1,"sync mismatch x=%0d y=%0d hs=%b vs=%b",xx,yy,hs,vs);
        if(active !== (xx<640 && yy<480)) $fatal(1,"active mismatch %0d %0d",xx,yy);
        wanted=0;
        if(xx<640 && yy<480) begin
            row=((yy/16)+offset)%32;
            character=screen[row*80+xx/8];
            expected_glyph=font[character*16+(yy%16)];
            cursor_visible=cursor_mode!=0 && xx/8==cx && yy/16==cy &&
                           (cursor_mode==1 || yy%16==15);
            wanted=expected_glyph[7-(xx%8)] || cursor_visible;
        end
        if(pixel !== wanted)
            $fatal(1,"pixel mismatch x=%0d y=%0d got=%b expected=%b char=%h row=%h",xx,yy,pixel,wanted,character,expected_glyph);
        @(negedge clk);
        xx=xx+1;
        if(xx==800) begin xx=0; yy=(yy+1)%525; end
    end
end
endtask

initial begin
    for(i=0;i<32768;i=i+1) memory[i]=16'ha55a;
    for(i=0;i<4096;i=i+1) begin
        screen[i]=8'h20;
        font[i]=dut.video.display.font.rom[i];
    end
    // Independent anchors guard font extraction and left/right bit order.
    if(font[32*16+7]!==0 || font[65*16+4]!==8'h38)
        $fatal(1,"unexpected source font anchors: A scanline4=%h",font[65*16+4]);
    repeat(3) @(negedge clk); reset=0;
    read_check(16'hfff6,3,0);
    read_check(16'he000,3,16'ha55a);
    access(16'hfff6,1,1,1); // Map VRAM, keep display blank.
    read_check(16'he000,3,16'h2020);
    access(16'he000,16'h4241,3,1);
    access(16'he001,16'h4443,3,1);
    read_check(16'he000,3,16'h4341);
    read_check(16'he001,3,16'h4443);
    read_check(16'he000,2,16'h4300);
    access(16'hefff,16'h7172,3,1); // VRAM -> SRAM crossing.
    read_check(16'hefff,3,16'h7172);
    access(16'hdfff,16'h7374,3,1); // SRAM -> VRAM crossing.
    read_check(16'hdfff,3,16'h7374);
    access(16'hfff6,0,1,1);
    read_check(16'he000,3,16'ha55a); // Hidden SRAM unchanged.
    access(16'he000,16'h1234,3,1);
    access(16'hfff6,1,1,1);
    read_check(16'he000,3,16'h4373); // VRAM retained while unmapped.
    access(16'hfff6,16'hffff,3,1);
    read_check(16'hfff6,3,16'h1f1f); // Reserved register bits masked.
    access(16'hfff8,16'hffff,3,1);
    read_check(16'hfff8,3,16'h1f7f);
    access(16'hfff5,16'h0100,3,1); // Timer -> VGA crossing.
    read_check(16'hfff5,3,16'h0100);
    access(16'hfffa,16'hffff,3,1); // Status RO, FFFB reserved.
    read_check(16'hfffb,3,0);
    // Fill physical rows with patterns through the CPU bus while scanning.
    for(i=0;i<2560;i=i+1) begin
        screen[i]=(i*13+i/80)&255;
        access(16'he000+i,screen[i],1,1);
    end
    access(16'hfff6,3,1,1); // Display on, cursor off.
    access(16'hfff7,0,1,1);
    fork
        frame_check(0,0,0,0);
        begin
            @(posedge vs);
            repeat(30000) @(negedge clk);
            for(i=0;i<100;i=i+1) begin
                access(16'hec00,i,1,1); // Off-screen storage, active scanout.
                read_check(16'hec00,1,i);
            end
            idle;
        end
    join
    access(16'hfff7,31,1,1);
    access(16'hfff8,16'h1d4f,3,1); // Bottom-right cursor.
    access(16'hfff6,7,1,1);
    frame_check(31,79,29,1);
    access(16'hfff6,23,1,1); // Underline, no blink.
    frame_check(31,79,29,2);
    access(16'hfff7,32,1,1); // Offset wraps.
    read_check(16'hfff7,1,0);
    access(16'hfff6,15,1,1); // Blinking block.
    idle;
    @(negedge clk); dut.video.display.blink_frames=0;
    frame_check(0,79,29,1);
    // Set frame counter near the phase boundary, then check frame-clock toggle.
    @(negedge clk); dut.video.display.blink_frames=15;
    @(posedge dut.video.display.v);
    wait(dut.video.display.blink_frames==16);
    frame_check(0,0,0,0); // Cursor is hidden in this phase.
    access(16'hfff6,7,1,1);
    access(16'hfff8,16'h1f7f,3,1);
    frame_check(0,127,31,0); // Out-of-screen coordinates hide the cursor.
    // System reset disables mapping without clearing VRAM or SRAM.
    @(negedge clk); reset=1;
    repeat(3) @(negedge clk); reset=0;
    read_check(16'hfff6,3,0);
    read_check(16'he000,3,16'h1234);
    access(16'hfff6,1,1,1);
    read_check(16'he000,1,screen[0]);
    idle;
    $display("PASS VGA bus, banking, font, full-frame timing/pixels, scrolling, cursor and reset");
    $finish;
end
initial begin #300000000; $fatal(1,"simulation timeout"); end
endmodule
