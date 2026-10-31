`timescale 1ns/1ps
// CPU + real UART buffers, paced RX injection, TX backpressure and delayed ACK.
// Not a serial receiver or physical SRAM test (covered separately).
module tb_parser;
reg clk = 0, reset = 1;
always #5 clk = ~clk;
wire [15:0] addr, write_data;
wire [1:0] bs;
wire we, halted;
reg ack = 0;
reg [15:0] read_data = 0;
reg [7:0] ram [0:65535];
reg [7:0] rx_bytes [0:1023];
reg [7:0] rx_data = 0;
reg rx_valid = 0;
wire [3:0] csr;
wire [6:0] input_data, tx_data;
wire tx_valid, output_ready;
integer cycles = 0, waits = 0, rx_index = 0, consumed = 0, rx_count, tx_file;
reg tx_ready = 0;
wire input_read = ack && bs == 1 && !we && addr == 16'hffff;
wire csr_write = ack && bs == 1 && we && addr == 16'hfffe;
wire output_valid = ack && bs == 1 && we && addr == 16'hffff;
string image_path, rx_path, tx_path, ram_path;

Prim cpu(.i_clk(clk), .i_reset(reset), .i_halt(1'b0), .i_run(1'b0),
    .i_step(1'b0), .i_debug_reset(1'b0), .i_irq(1'b0), .o_addr(addr),
    .o_dat(write_data), .i_dat(read_data), .o_bs(bs), .o_we(we),
    .i_ack(ack), .o_halted(halted));
uart_buffers buffers(.i_clk(clk), .i_reset(reset), .i_rx_data(rx_data),
    .i_rx_valid(rx_valid), .i_input_read(input_read), .o_input_data(input_data),
    .o_csr(csr), .i_csr_data(write_data[7:0]), .i_csr_write(csr_write),
    .i_output_data(write_data[6:0]), .i_output_valid(output_valid),
    .o_output_ready(output_ready), .o_tx_data(tx_data), .o_tx_valid(tx_valid),
    .i_tx_ready(tx_ready));

always @(negedge clk) begin
    ack = 0;
    rx_valid = 0;
    // Stable at the sampling edge for both the buffer and the TX recorder.
    tx_ready = cycles % 17 == 0;
    if (!reset) begin
        if (!csr[0] && rx_index < rx_count && cycles > 20) begin
            rx_data = rx_bytes[rx_index];
            rx_index = rx_index + 1;
            rx_valid = 1;
        end
        if (bs != 0) begin
            if (waits >= 3 && (!(we && addr == 16'hffff) || output_ready)) begin
                waits = 0;
                ack = 1;
                if (addr == 16'hfffe) read_data = {12'b0, csr};
                else if (addr == 16'hffff) read_data = {9'b0, input_data};
                else read_data = {ram[(addr + 1) & 65535], ram[addr]};
            end else waits = waits + 1;
        end else waits = 0;
    end
end

always @(posedge clk) begin
    if (!reset) begin
        cycles = cycles + 1;
        if (cycles > 200000) $fatal(1, "input/parser timeout");
        if (tx_valid && tx_ready) $fwrite(tx_file, "%02x\n", tx_data);
        if (ack && bs != 0) begin
            if (addr >= 16'hfffe) begin
                if (bs != 1) $fatal(1, "word access to UART");
                if (input_read) begin
                    if (!csr[0]) $fatal(1, "unavailable RX consumed");
                    consumed = consumed + 1;
                end
            end else if (we) begin
                ram[addr] <= write_data[7:0];
                if (bs[1]) ram[(addr + 1) & 65535] <= write_data[15:8];
            end
        end
        if (halted && !tx_valid) begin
            if (consumed != rx_count || csr[0]) $fatal(1, "RX count/flag");
            if (cpu.r_dsp !== 8 || cpu.r_rsp !== 0 || cpu.T !== 16'ha007)
                $fatal(1, "parser damaged user stacks");
            if ({ram[16'h0109], ram[16'h0108]} !== 8) $fatal(1, "parser changed DEPTH");
            $writememh(ram_path, ram);
            $fclose(tx_file);
            $display("PASS Forth line/parser with RX pacing, TX backpressure and eight user cells");
            $finish;
        end
    end
end

initial begin
    if (!$value$plusargs("image=%s", image_path) ||
        !$value$plusargs("rx=%s", rx_path) || !$value$plusargs("count=%d", rx_count) ||
        !$value$plusargs("tx=%s", tx_path) || !$value$plusargs("ram=%s", ram_path))
        $fatal(1, "image/rx/count/tx/ram required");
    $readmemh(image_path, ram);
    $readmemh(rx_path, rx_bytes, 0, rx_count - 1);
    tx_file = $fopen(tx_path, "w");
    if (!tx_file) $fatal(1, "cannot open TX output");
    repeat (3) @(negedge clk);
    reset = 0;
end
endmodule
