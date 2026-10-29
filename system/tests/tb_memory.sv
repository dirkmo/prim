`timescale 1ns/1ps
// Whole-word asynchronous SRAM, with delayed bus release and write timing checks.
module tb_memory;
parameter integer READ_CYCLES = 2, WRITE_CYCLES = 2, SRAM_DELAY_NS = 3;
parameter integer WITH_UART = 0, CLKS_PER_BIT = 4;
reg clk = 0;
always #10 clk = ~clk;
reg reset = 1;
reg cpu_mode = 0;
reg halted = 0;
reg [15:0] addr = 0, data = 0;
reg [1:0] bs = 0;
reg we = 0;
wire [15:0] cpu_addr, cpu_data, cpu_read, ram_addr;
wire [1:0] cpu_bs;
wire cpu_we, ack, cs_n, oe_n, we_n;
wire timer_irq;
wire [15:0] ram_data;
wire serial_tx, uart_busy, controller_drive;
wire [6:0] output_data;
wire output_valid, output_ready, input_read, buffered_valid, tx_ready;
wire [6:0] input_data, buffered_data;
wire [1:0] uart_status, leds;
reg [1:0] expected_leds = 0;
wire [15:0] request_addr = cpu_mode ? cpu_addr : addr;
wire [15:0] request_data = cpu_mode ? cpu_data : data;
wire [1:0] request_bs = cpu_mode ? cpu_bs : bs;
wire request_we = cpu_mode ? cpu_we : we;

Prim cpu(.i_clk(clk), .i_reset(reset || !cpu_mode || halted), .o_addr(cpu_addr), .o_dat(cpu_data),
         .i_dat(cpu_read), .o_bs(cpu_bs), .o_we(cpu_we), .i_ack(ack), .i_irq(timer_irq),
         .i_halt(1'b0), .i_run(1'b0), .i_step(1'b0), .i_debug_reset(1'b0));
generate if (WITH_UART) begin: io
memory_io #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES)) dut(
    .i_clk(clk), .i_reset(reset), .i_addr(request_addr), .i_cpu_to_mem(request_data),
    .o_mem_to_cpu(cpu_read), .i_bs(request_bs), .i_we(request_we), .o_ack(ack),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(cs_n),
    .ram_oe_n(oe_n), .ram_we_n(we_n), .o_output_data(output_data), .o_output_valid(output_valid), .i_output_ready(output_ready),
    .i_input_data(input_data), .i_uart_status(uart_status), .o_input_read(input_read), .o_leds(leds),
    .o_timer_irq(timer_irq));
assign controller_drive = dut.sram.drive;
uart_buffers buffers(.i_clk(clk), .i_reset(reset), .i_rx_data(8'b0), .i_rx_valid(1'b0),
    .i_input_read(input_read), .o_input_data(input_data), .o_status(uart_status),
    .i_output_data(output_data), .i_output_valid(output_valid), .o_output_ready(output_ready),
    .o_tx_data(buffered_data), .o_tx_valid(buffered_valid), .i_tx_ready(tx_ready));
uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) uart(.i_clk(clk), .i_reset(reset),
    .i_data({1'b0, buffered_data}), .i_valid(buffered_valid), .o_ready(tx_ready), .o_tx(serial_tx));
assign uart_busy = !tx_ready || buffered_valid;
end else begin: flat
memory #(.READ_CYCLES(READ_CYCLES), .WRITE_CYCLES(WRITE_CYCLES)) dut(
    .i_clk(clk), .i_reset(reset), .i_addr(request_addr), .i_cpu_to_mem(request_data),
    .o_mem_to_cpu(cpu_read), .i_bs(request_bs), .i_we(request_we), .o_ack(ack),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(cs_n),
    .ram_oe_n(oe_n), .ram_we_n(we_n));
assign controller_drive = dut.drive;
assign serial_tx = 1'b1;
assign uart_busy = 1'b0;
assign timer_irq = 1'b0;
end endgenerate

reg [15:0] sram [0:32767];
reg [7:0] reference [0:65535];
assign #(SRAM_DELAY_NS) ram_data = (!cs_n && !oe_n && we_n) ? sram[ram_addr[14:0]] : 16'hzzzz;

integer reads = 0, writes = 0;
reg last_oe = 1;
reg [15:0] last_read_addr;
always @(ram_addr or oe_n or we_n or cs_n) begin
    if (!reset && !cs_n && !oe_n && we_n && (last_oe || ram_addr !== last_read_addr))
        reads = reads + 1;
    last_oe = cs_n || oe_n;
    last_read_addr = ram_addr;
    if (!reset && !oe_n && !we_n) $fatal(1, "OE and WE active together");
    if (!reset && !cs_n && ram_addr[15] !== 0) $fatal(1, "SRAM address did not wrap at 64 KiB");
end

reg write_pending = 0;
reg [15:0] write_addr, write_value;
time write_start;
time last_bus_change = 0;
reg hold_active = 0;
always @(ram_addr or ram_data) begin
    last_bus_change = $time;
    if ((write_pending || hold_active) && (ram_addr !== write_addr || ram_data !== write_value))
        $fatal(1, "Write bus changed during pulse or hold time");
end
always @(negedge we_n) begin
    if (!reset) begin
        if (cs_n || !oe_n || !controller_drive) $fatal(1, "Invalid write bus direction");
        if ((^ram_data) === 1'bx) $fatal(1, "Invalid SRAM write data");
        if ($time - last_bus_change < 19) $fatal(1, "Missing write setup time");
        write_pending = 1;
        write_addr = ram_addr;
        write_value = ram_data;
        write_start = $time;
    end
end
always @(posedge we_n) begin
    if (write_pending) begin
        if ($time - write_start < WRITE_CYCLES * 20) $fatal(1, "Short write pulse");
        if (ram_addr !== write_addr || ram_data !== write_value) $fatal(1, "Write bus changed");
        sram[write_addr[14:0]] = write_value;
        writes = writes + 1;
        write_pending = 0;
        hold_active = 1;
        #19;
        hold_active = 0;
        if (!reset && (ram_addr !== write_addr || ram_data !== write_value))
            $fatal(1, "Missing write hold time");
    end
end
always @(posedge clk) begin
    if (!reset && WITH_UART && ((input_read && !ack) || (output_valid && output_ready && !ack)))
        $fatal(1, "UART effect occurred before final bus ACK");
    if (!reset && !cs_n && !oe_n && (^ram_data) === 1'bx)
        $fatal(1, "Unknown read data or SRAM/FPGA bus contention");
    #1;
    if (!reset && controller_drive && !oe_n) $fatal(1, "SRAM/FPGA bus contention");
end

function [15:0] expected_word(input integer word_index);
    expected_word = {reference[2*word_index+1], reference[2*word_index]};
endfunction

// Unused stack cells deliberately have no reset. Keep their X values out of
// JSON, but use an impossible 16-bit value so an occupied X cell still fails.
function integer trace_value(input [15:0] value);
    trace_value = ((^value) === 1'bx) ? 65536 : value;
endfunction

reg [7:0] expected_tx [0:4095];
integer expected_count = 0, received_count = 0;
integer uart_file = 0, serial_bit;
reg [7:0] serial_byte;
string uart_path;
always @(negedge serial_tx) begin
    if (WITH_UART && !reset) begin
        #(CLKS_PER_BIT * 10);
        if (serial_tx !== 0) $fatal(1, "Invalid UART start bit");
        for (serial_bit=0; serial_bit<8; serial_bit=serial_bit+1) begin
            #(CLKS_PER_BIT * 20);
            serial_byte[serial_bit] = serial_tx;
        end
        #(CLKS_PER_BIT * 20);
        if (serial_tx !== 1) $fatal(1, "Invalid UART stop bit");
        if (cpu_mode) $fwrite(uart_file, "%02x\n", serial_byte);
        else if (received_count >= expected_count || serial_byte !== expected_tx[received_count])
            $fatal(1, "Wrong/duplicate UART byte %h at index %0d", serial_byte, received_count);
        received_count = received_count + 1;
    end
end

task access(input [15:0] a, input [15:0] d, input [1:0] b, input wr);
    reg [15:0] expected;
    reg [1:0] ram_mask;
    integer before_reads, before_writes, n, read_count, write_count;
    begin
        @(negedge clk);
        addr = a; data = d; bs = b; we = wr;
        before_reads = reads; before_writes = writes;
        expected = {(b[1] ? reference[(a+1)&65535] : 8'h00),
                    (b[0] ? reference[a] : 8'h00)};
        read_count = (b == 3 && a[0]) ? 2 : 1;
        write_count = wr ? read_count : 0;
        if (wr && b == 3 && !a[0]) read_count = 0;
        if (WITH_UART) begin
            ram_mask = {b[1] && (((a+1)&65535) < 65520), b[0] && (a < 65520)};
            if (ram_mask != b) begin
                read_count = ram_mask!=0 ? 1 : 0;
                write_count = wr ? read_count : 0;
            end
            if (wr && ((b[0] && a==16'hffff) || (b[1] && a==16'hfffe))) begin
                expected_tx[expected_count] = a==16'hffff ? {1'b0,d[6:0]} : {1'b0,d[14:8]};
                expected_count = expected_count + 1;
            end
        end
        n = 0;
        do begin
            @(posedge clk);
            n = n + 1;
            if (n > 200) $fatal(1, "ACK timeout addr=%h bs=%b we=%b", a, b, wr);
        end while (ack !== 1'b1);
        if (reads - before_reads != read_count || writes - before_writes != write_count)
            $fatal(1, "Wrong SRAM access count addr=%h bs=%b we=%b reads=%0d expected=%0d writes=%0d expected=%0d",
                   a, b, wr, reads-before_reads, read_count, writes-before_writes, write_count);
        if (WITH_UART && !wr) begin
            if (b[0] && a>=16'hfff6 && a<=16'hfffc) expected[7:0]=0;
            if (b[1] && a>=16'hfff5 && a<=16'hfffb) expected[15:8]=0;
            if(b[0] && a==16'hfffd) expected[7:0]={6'b0,expected_leds};
            if(b[1] && a==16'hfffc) expected[15:8]={6'b0,expected_leds};
            if(b[0] && a==16'hfffe) expected[7:0]={6'b0,uart_status};
            if(b[0] && a==16'hffff) expected[7:0]={1'b0,input_data};
            if(b[1] && a==16'hfffd) expected[15:8]={6'b0,uart_status};
            if(b[1] && a==16'hfffe) expected[15:8]={1'b0,input_data};
        end
        if (!wr && cpu_read !== expected)
            $fatal(1, "Read mismatch addr=%h bs=%b actual=%h expected=%h", a, b, cpu_read, expected);
        if (WITH_UART && wr) begin
            if (b[0] && a==16'hfffd) expected_leds = d[1:0];
            if (b[1] && a==16'hfffc) expected_leds = d[9:8];
        end
        #1;
        if (WITH_UART && leds !== expected_leds) $fatal(1, "LED register mismatch");
        if (wr) begin
            if (b[0] && !(WITH_UART && a>=16'hfff0)) reference[a] = d[7:0];
            if (b[1] && !(WITH_UART && ((a+1)&65535)>=65520)) reference[(a+1)&65535] = d[15:8];
        end
        if (sram[a>>1] !== expected_word(a>>1) ||
            sram[((a+1)&65535)>>1] !== expected_word(((a+1)&65535)>>1))
            $fatal(1, "Neighbour byte overwritten addr=%h bs=%b", a, b);
    end
endtask

integer i, j, lane, operation, seed = 12345;
reg [15:0] addresses [0:7];
reg [15:0] random_addr, random_data;
string image_path, trace_path;
integer trace_file, cycles = 0;
string pending_reads = "", pending_writes = "";
reg [15:0] at;
reg [7:0] ir;

// Logical CPU transactions, independent of the physical SRAM RMW operations.
always @(posedge clk) begin
    cycles = cycles + 1;
    if (cycles > 100000) $fatal(1, "Simulation timeout");
    if (cpu_mode && halted && !uart_busy) begin
        if (uart_file) $fclose(uart_file);
        $display("PASS CPU SRAM integration");
        $finish;
    end
    if (cpu_mode && !reset && !halted) begin
        if (ack && |cpu_bs) begin
            if (cpu.r_phase == 0 && (cpu_read[7:0] == 8'h22 || cpu_read[7:0] == 8'hff)) begin
                $fwrite(trace_file, "{\"kind\":\"halt\",\"pc\":%0d,\"ir\":%0d}\n", cpu.r_pc, cpu_read[7:0]);
                $fclose(trace_file);
                halted = 1;
                if (!WITH_UART) begin
                    $display("PASS CPU SRAM integration");
                    $finish;
                end
            end
            if (cpu_bs[0]) begin
                if (cpu_we) pending_writes = {pending_writes, pending_writes == "" ? "" : ",",
                    $sformatf("[%0d,%0d]", cpu_addr, cpu_data[7:0])};
                else pending_reads = {pending_reads, pending_reads == "" ? "" : ",",
                    $sformatf("[%0d,%0d]", cpu_addr, cpu_read[7:0])};
            end
            if (cpu_bs[1]) begin
                if (cpu_we) pending_writes = {pending_writes, pending_writes == "" ? "" : ",",
                    $sformatf("[%0d,%0d]", (cpu_addr+1)&65535, cpu_data[15:8])};
                else pending_reads = {pending_reads, pending_reads == "" ? "" : ",",
                    $sformatf("[%0d,%0d]", (cpu_addr+1)&65535, cpu_read[15:8])};
            end
        end
        if (cpu.r_phase == 2) begin
            at = cpu.r_pc; ir = cpu.r_ir;
            #1;
            $fwrite(trace_file, "{\"kind\":\"step\",\"at\":%0d,\"ir\":%0d,\"pc\":%0d,\"dsp\":%0d,\"rsp\":%0d,\"carry\":%0d,\"ds\":[",
                    at, ir, cpu.r_pc, cpu.r_dsp, cpu.r_rsp, cpu.r_carry);
            for (j=0; j<16; j=j+1)
                $fwrite(trace_file, "%s%0d", j ? "," : "", trace_value(j==0 ? cpu.T : j==1 ? cpu.N : cpu.r_dstack[(cpu.r_dsp-j)&15]));
            $fwrite(trace_file, "],\"rs\":[");
            for (j=0; j<16; j=j+1)
                $fwrite(trace_file, "%s%0d", j ? "," : "", trace_value(cpu.r_rstack[(cpu.r_rsp-j)&15]));
            $fwrite(trace_file, "],\"reads\":[%s],\"writes\":[%s]}\n", pending_reads, pending_writes);
            pending_reads = ""; pending_writes = "";
        end
    end
end

initial begin
    cpu_mode = $test$plusargs("cpu");
    for (i=0; i<32768; i=i+1) begin
        sram[i] = (i * 257) ^ 16'h5a3c;
        reference[2*i] = sram[i][7:0];
        reference[2*i+1] = sram[i][15:8];
    end
    if (cpu_mode) begin
        if (!$value$plusargs("image=%s", image_path) || !$value$plusargs("trace=%s", trace_path))
            $fatal(1, "CPU mode requires image and trace paths");
        $readmemh(image_path, sram);
        trace_file = $fopen(trace_path, "w");
        if (!trace_file) $fatal(1, "Cannot open trace");
        if (WITH_UART) begin
            if (!$value$plusargs("uart=%s", uart_path)) $fatal(1, "UART path required");
            uart_file = $fopen(uart_path, "w");
            if (!uart_file) $fatal(1, "Cannot open UART output");
        end
    end
    repeat(2) @(negedge clk);
    reset = 0;
    if (!cpu_mode) begin
        addresses[0]=0; addresses[1]=1; addresses[2]=16'h1000; addresses[3]=16'h1001;
        addresses[4]=16'hfffc; addresses[5]=16'hfffd; addresses[6]=16'hfffe; addresses[7]=16'hffff;
        for (i=0; i<8; i=i+1)
            for (lane=1; lane<4; lane=lane+1)
                for (operation=0; operation<2; operation=operation+1) begin
                    access(addresses[i], 16'hbadd, lane, operation);
                    access(addresses[i], 0, lane, 0);
                end
        for (i=0; i<512; i=i+1) begin
            random_addr = $random(seed); random_data = $random(seed);
            access(random_addr, random_data, 1+(i%3), i%2);
        end
        // Reset discards controller state, retaining external SRAM contents.
        wait(!uart_busy);
        @(negedge clk); bs=0; reset=1;
        #1;
        if (!cs_n || !oe_n || !we_n || ack || ram_data !== 16'hzzzz)
            $fatal(1, "SRAM bus active during reset");
        repeat(2) @(negedge clk);
        reset=0; expected_leds=0;
        if (WITH_UART && leds !== 0) $fatal(1, "LED reset");
        access(16'h1001, 0, 3, 0);
        // Abort a read before ACK, then issue a fresh request.
        @(negedge clk); addr=16'h4321; bs=3; we=0;
        @(negedge oe_n);
        @(negedge clk); reset=1; bs=0;
        repeat(2) @(negedge clk);
        reset=0;
        access(16'hffff, 0, 3, 0);
        @(negedge clk); bs=0;
        repeat(3) @(negedge clk);
        wait(!uart_busy);
        if (WITH_UART && received_count != expected_count) $fatal(1, "Missing UART bytes");
        if (ack || !cs_n || !oe_n || !we_n || ram_data !== 16'hzzzz)
            $fatal(1, "SRAM bus active while idle");
        for (i=0; i<32768; i=i+1)
            if (sram[i] !== expected_word(i)) $fatal(1, "Final SRAM mismatch at %h", i);
        $display("PASS SRAM controller READ_CYCLES=%0d WRITE_CYCLES=%0d", READ_CYCLES, WRITE_CYCLES);
        $finish;
    end
end
endmodule
