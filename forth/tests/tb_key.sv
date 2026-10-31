`timescale 1ns/1ps
// Directed KEY test: actual UART buffers, delayed MMIO ACK and NUL reception.
// RAM bus model here; physical SRAM/TX are covered by SramSimulation separately.
module tb_key;
reg clk = 0, reset = 1;
always #5 clk = ~clk;
wire [15:0] addr, write_data, pc;
wire [1:0] bs;
wire we, halted;
reg ack = 0;
reg [15:0] read_data = 0;
reg [7:0] ram [0:65535];
wire [3:0] csr;
wire [6:0] input_data;
reg [7:0] rx_data = 0;
reg rx_valid = 0;
wire input_read = ack && bs == 1 && !we && addr == 16'hffff;
wire csr_write = ack && bs == 1 && we && addr == 16'hfffe;
integer waits = 0, polls = 0, consumed = 0, cycles = 0;
reg sent = 0;
string image_path;

Prim cpu(.i_clk(clk), .i_reset(reset), .i_halt(1'b0), .i_run(1'b0),
    .i_step(1'b0), .i_debug_reset(1'b0), .i_irq(1'b0),
    .o_addr(addr), .o_dat(write_data), .i_dat(read_data), .o_bs(bs),
    .o_we(we), .i_ack(ack), .o_pc(pc), .o_halted(halted));
uart_buffers buffers(.i_clk(clk), .i_reset(reset), .i_rx_data(rx_data),
    .i_rx_valid(rx_valid), .i_input_read(input_read), .o_input_data(input_data),
    .o_csr(csr), .i_csr_data(write_data[7:0]), .i_csr_write(csr_write),
    .i_output_data(7'b0), .i_output_valid(1'b0), .i_tx_ready(1'b1));

always @(negedge clk) begin
    ack = 0;
    rx_valid = 0;
    if (!reset) begin
        // RXAVAIL stays false during at least five completed status reads.
        // TXFREE remains true: testing the whole CSR would incorrectly return.
        if (polls >= 5 && !sent) begin
            sent = 1;
            rx_valid = 1;
            rx_data = 0;
        end
        if (bs != 0) begin
            if (waits == 3) begin
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
        if (cycles > 10000) $fatal(1, "KEY test timeout");
        if (ack && bs != 0) begin
            if (addr >= 16'hfffe) begin
                if (bs != 1) $fatal(1, "word access to UART");
                if (!we && addr == 16'hfffe) polls = polls + 1;
                if (!we && addr == 16'hffff) begin
                    if (!csr[0] || !sent) $fatal(1, "KEY consumed unavailable RX");
                    consumed = consumed + 1;
                end
                if (we && addr == 16'hffff) $fatal(1, "unexpected TX");
            end else if (we) begin
                ram[addr] <= write_data[7:0];
                if (bs[1]) ram[(addr + 1) & 65535] <= write_data[15:8];
            end
        end
        if (halted) begin
            if (consumed != 1 || polls < 5 || csr[0]) $fatal(1, "KEY RX side effects");
            if (cpu.T !== 0 || cpu.r_dsp !== 1 || cpu.r_rsp !== 0)
                $fatal(1, "KEY NUL/stack result");
            if ({ram[16'h0109], ram[16'h0108]} !== 16'h0001)
                $fatal(1, "KEY logical stack depth");
            $display("PASS Forth KEY: waits for RXAVAIL, consumes NUL once, returns normally");
            $finish;
        end
    end
end

initial begin
    if (!$value$plusargs("image=%s", image_path)) $fatal(1, "image required");
    $readmemh(image_path, ram);
    repeat (3) @(negedge clk);
    reset = 0;
end
endmodule
