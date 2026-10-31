`timescale 1ns/1ps
// Complete serial RX -> Forth/Prim -> physical SRAM interface -> serial TX.
module tb_system;
localparam DIV = 8;
reg clk = 0, reset = 1, rx = 1;
always #5 clk = ~clk;
wire tx, halted, cs_n, oe_n, we_n;
wire [15:0] ram_addr, ram_data;
prim_system #(.CLK_HZ(115200*DIV), .READ_CYCLES(3), .WRITE_CYCLES(3)) dut(
    .i_clk(clk), .i_reset(reset), .i_rx(rx), .o_tx(tx), .o_halted(halted),
    .ram_addr(ram_addr), .ram_data(ram_data), .ram_cs_n(cs_n),
    .ram_oe_n(oe_n), .ram_we_n(we_n));
reg [15:0] memory [0:32767];
assign ram_data = !cs_n && !oe_n && we_n ? memory[ram_addr[14:0]] : 16'hzzzz;
always @(posedge we_n) if (!cs_n && !reset) memory[ram_addr[14:0]] = ram_data;
reg [7:0] source [0:4095], expected [0:4095], debug_bytes [0:65535];
reg [7:0] received;
integer cpu_count = 0, debug_count = 0, position = 0, source_count, expected_count;
integer tx_file, cycles = 0;
string image_path, source_path, expected_path, output_path;

always begin
    @(negedge tx);
    repeat(DIV/2) @(negedge clk);
    for (integer k=0; k<8; k=k+1) begin
        repeat(DIV) @(negedge clk);
        received[k] = tx;
    end
    repeat(DIV) @(negedge clk);
    if (tx !== 1) $fatal(1, "serial stop bit");
    if (received[7]) begin
        if (debug_count == 65536) $fatal(1, "debug receive buffer full");
        debug_bytes[debug_count] = received & 127;
        debug_count = debug_count + 1;
    end else begin
        if (cpu_count >= expected_count || received !== expected[cpu_count])
            $fatal(1, "CPU TX mismatch byte %0d got %02x expected %02x", cpu_count, received, expected[cpu_count]);
        $fwrite(tx_file, "%02x\n", received);
        cpu_count = cpu_count + 1;
    end
end

task send(input [7:0] value);
    @(negedge clk); rx = 0;
    repeat(DIV) @(negedge clk);
    for (integer k=0; k<8; k=k+1) begin
        rx = value[k]; repeat(DIV) @(negedge clk);
    end
    rx = 1; repeat(DIV) @(negedge clk);
endtask

function integer digit(input [7:0] value);
    if (value >= "0" && value <= "9") digit = value - "0";
    else if (value >= "a" && value <= "f") digit = value - "a" + 10;
    else digit = -1;
endfunction

task credit;
    integer status;
    begin
        status = 1;
        while (status & 1) begin
            send("q" | 128);
            wait(debug_count >= position + 2);
            if (debug_bytes[position] !== "K") $fatal(1, "status acknowledgement");
            status = digit(debug_bytes[position+1]);
            if (status < 0) $fatal(1, "invalid status digit");
            position = position + 2;
        end
    end
endtask

initial begin
    if (!$value$plusargs("image=%s", image_path) ||
        !$value$plusargs("source=%s", source_path) ||
        !$value$plusargs("expected=%s", expected_path) ||
        !$value$plusargs("output=%s", output_path) ||
        !$value$plusargs("source_count=%d", source_count) ||
        !$value$plusargs("expected_count=%d", expected_count)) $fatal(1, "missing files/counts");
    if (source_count < 1 || source_count > 4096 || expected_count < 4 || expected_count > 4096)
        $fatal(1, "invalid fixture size");
    $readmemh(image_path, memory);
    $readmemh(source_path, source, 0, source_count-1);
    $readmemh(expected_path, expected, 0, expected_count-1);
    tx_file = $fopen(output_path, "w");
    if (!tx_file) $fatal(1, "cannot open output");
    repeat(4) @(negedge clk); reset = 0;
    wait(cpu_count >= 4); // Initial ok/CRLF must come from the booted kernel.
    for (integer k=0; k<source_count; k=k+1) begin
        credit(); // Real high-bit debug traffic; no hierarchical RX injection.
        send(source[k]);
    end
    wait(cpu_count == expected_count);
    send("H" | 128);
    wait(debug_count > position);
    if (debug_bytes[position] !== "K") $fatal(1, "HALT acknowledgement");
    wait(halted);
    if (memory[16'h0108/2] !== 0 || memory[16'h0112/2] !== 0)
        $fatal(1, "final stack/definition state");
    $fclose(tx_file);
    $display("PASS complete Forth serial RX/TX, SRAM, debug credit and rollback");
    $finish;
end
always @(posedge clk) begin
    cycles = cycles + 1;
    if (cycles > 10000000) $fatal(1, "system session timeout");
end
endmodule
