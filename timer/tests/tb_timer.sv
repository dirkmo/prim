`timescale 1ns/1ps
module tb_timer;
parameter integer DIVISOR = 7;
localparam integer DIV = DIVISOR;
reg clk = 0, reset = 0, cs = 0, we = 0;
reg [1:0] addr = 0, be = 0;
reg [15:0] wdata = 0;
wire [15:0] rdata;
wire irq;
integer irqs = 0;
integer n, target, ticks, expected, seed = 32'h1250abcd;
timer #(.DIVISOR(DIVISOR)) dut (
    .i_clk(clk), .i_reset(reset), .i_cs(cs), .i_we(we),
    .i_addr(addr), .i_be(be), .i_wdata(wdata), .o_rdata(rdata), .o_irq(irq));

task cycle;
begin
    #5; clk = 1; #1;
    if (irq === 1'b1) irqs = irqs + 1;
    else if (irq !== 1'b0) $fatal(1, "unknown IRQ");
    #4; clk = 0;
end
endtask

task advance(input integer cycles);
integer j;
begin
    for (j = 0; j < cycles; j = j + 1) cycle();
end
endtask

task read_expect(input [1:0] index, input [15:0] value);
begin
    cs = 1; we = 0; addr = index; #1;
    if (rdata !== value)
        $fatal(1, "register %0d: got %04h, expected %04h", index, rdata, value);
    cs = 0;
end
endtask

task irq_expect(input integer value);
begin
    if (irqs != value) $fatal(1, "IRQ cycles %0d, expected %0d", irqs, value);
end
endtask

task write_reg(input [1:0] index, input [15:0] value, input [1:0] mask);
begin
    cs = 1; we = 1; addr = index; wdata = value; be = mask;
    cycle();
    cs = 0; we = 0; be = 0;
end
endtask

task reset_timer;
begin
    reset = 1; cycle(); reset = 0; irqs = 0;
    read_expect(0, 0); read_expect(1, 0); read_expect(2, 0);
    if (irq !== 0) $fatal(1, "reset failed to clear IRQ");
end
endtask

task configure(input [15:0] initial_count, input [15:0] limit, input [2:0] control);
begin
    reset_timer();
    write_reg(1, limit, 3);
    write_reg(0, initial_count, 3);
    write_reg(2, {13'b0, control}, 3);
end
endtask

initial begin
    reset_timer();
    // Byte writes preserve neighbours; reserved bits/index and no-CS writes.
    write_reg(0, 16'h1234, 3);
    write_reg(0, 16'habcd, 1); read_expect(0, 16'h12cd);
    write_reg(0, 16'h5678, 2); read_expect(0, 16'h56cd);
    write_reg(1, 16'habcd, 3);
    write_reg(1, 16'h1234, 1); read_expect(1, 16'hab34);
    write_reg(1, 16'h5678, 2); read_expect(1, 16'h5634);
    write_reg(0, 0, 0); read_expect(0, 16'h56cd);
    write_reg(2, 16'hfffe, 3); read_expect(2, 6);
    write_reg(2, 16'hff00, 2); read_expect(2, 6);
    write_reg(3, 16'hffff, 3); read_expect(3, 0);
    addr = 0; wdata = 0; be = 3; we = 1; cs = 0; cycle();
    if (rdata !== 0) $fatal(1, "unselected read is nonzero");
    we = 0; read_expect(0, 16'h56cd);
    advance(3*DIV); read_expect(0, 16'h56cd);

    // One-shot: interrupt on arrival, COUNT and ENABLE remain at terminal.
    configure(0, 3, 5);
    advance(2*DIV); read_expect(0, 2); irq_expect(0);
    advance(DIV); read_expect(0, 3); irq_expect(1);
    if (!irq) $fatal(1, "missing arrival IRQ");
    cycle(); if (irq) $fatal(1, "IRQ wider than one system clock");
    advance(4*DIV); read_expect(0, 3); read_expect(2, 5); irq_expect(1);
    write_reg(0, 0, 3);
    advance(DIV-1); read_expect(0, 0);
    cycle(); read_expect(0, 1);
    advance(2*DIV); read_expect(0, 3); irq_expect(2);

    // No hidden stopped state: changing COMPARE resumes counting.
    write_reg(1, 5, 3);
    advance(3*DIV); read_expect(0, 5); irq_expect(3);
    // Writing equality does not signal an interrupt, even when INTEN is set.
    write_reg(0, 5, 3); advance(2*DIV); irq_expect(3);
    write_reg(0, 4, 3); advance(DIV); read_expect(0, 5); irq_expect(4);

    // AUTO retains the terminal value for one tick, then reloads zero.
    configure(0, 3, 7);
    advance(3*DIV); read_expect(0, 3); irq_expect(1);
    advance(DIV); read_expect(0, 0); irq_expect(1);
    advance(3*DIV); read_expect(0, 3); irq_expect(2);

    // INTEN gates reporting only; enabling it at equality is not retroactive.
    configure(0, 2, 1);
    advance(3*DIV); read_expect(0, 2); irq_expect(0);
    write_reg(2, 5, 3); advance(2*DIV); irq_expect(0);
    write_reg(0, 0, 3); advance(2*DIV); irq_expect(1);

    // COMPARE=0: holds at zero for either AUTO setting, no recurring IRQ.
    configure(0, 0, 5); advance(4*DIV); read_expect(0, 0); irq_expect(0);
    write_reg(2, 7, 3); advance(4*DIV); read_expect(0, 0); irq_expect(0);
    // A full wrap from positive COUNT generates exactly one arrival IRQ.
    configure(1, 0, 7);
    advance(65534*DIV); read_expect(0, 16'hffff); irq_expect(0);
    advance(DIV); read_expect(0, 0); irq_expect(1);
    advance(3*DIV); read_expect(0, 0); irq_expect(1);
    configure(16'hffff, 0, 5);
    advance(DIV); read_expect(0, 0); irq_expect(1);
    advance(3*DIV); read_expect(0, 0); irq_expect(1);

    // A smaller new comparison value does not cause an early reload.
    configure(16'hfffe, 1, 5);
    advance(DIV); read_expect(0, 16'hffff); irq_expect(0);
    advance(DIV); read_expect(0, 0); irq_expect(0);
    advance(DIV); read_expect(0, 1); irq_expect(1);
    configure(16'hfffe, 16'hffff, 5);
    advance(DIV); read_expect(0, 16'hffff); irq_expect(1);

    // Disable preserves COUNT; enabling starts a complete new interval.
    configure(0, 20, 5);
    advance(2*DIV);
    write_reg(2, 4, 3); read_expect(0, 2);
    advance(3*DIV); read_expect(0, 2);
    write_reg(2, 5, 3);
    advance(DIV-1); read_expect(0, 2);
    cycle(); read_expect(0, 3);

    // A partial COUNT write that makes the complete word zero restarts phase.
    configure(16'h0100, 20, 5);
    advance(DIV/2);
    write_reg(0, 0, 2);
    advance(DIV-1); read_expect(0, 0); irq_expect(0);
    cycle(); read_expect(0, 1);
    // Reset of phase on disable, including a partially elapsed interval.
    if (DIV > 1) begin
        configure(0, 20, 5);
        advance(DIV/2);
        write_reg(2, 4, 3);
        advance(2*DIV); read_expect(0, 0);
        write_reg(2, 5, 3);
        advance(DIV-1); read_expect(0, 0);
        cycle(); read_expect(0, 1);
    end

    // Writes on the arrival edge override both counting and IRQ generation.
    configure(0, 1, 5);
    advance(DIV-1); write_reg(1, 2, 3);
    read_expect(0, 0); irq_expect(0);
    advance(DIV); read_expect(0, 1); irq_expect(0);
    advance(DIV); read_expect(0, 2); irq_expect(1);
    configure(0, 1, 5);
    advance(DIV-1); write_reg(0, 0, 3);
    advance(DIV-1); read_expect(0, 0); irq_expect(0);
    cycle(); read_expect(0, 1); irq_expect(1);
    configure(0, 1, 5);
    advance(DIV-1); write_reg(2, 1, 3);
    advance(DIV); read_expect(0, 1); irq_expect(0);

    // Invalid/no-byte writes do not suppress a coincident tick.
    configure(0, 1, 5);
    advance(DIV-1); write_reg(3, 0, 3);
    read_expect(0, 1); irq_expect(1);
    configure(0, 1, 5);
    advance(DIV-1); write_reg(0, 0, 0);
    read_expect(0, 1); irq_expect(1);

    // Reads have no side effects; reset wins even over a simultaneous write.
    configure(0, 1, 5);
    cs = 1; we = 0; addr = 0; advance(DIV);
    read_expect(0, 1); irq_expect(1);
    reset = 1; write_reg(0, 16'hffff, 3); reset = 0;
    read_expect(0, 0); read_expect(1, 0); read_expect(2, 0);
    if (irq) $fatal(1, "reset failed to clear active IRQ");

    // Random periods checked against closed-form timing, not an RTL model.
    for (n = 0; n < 40; n = n + 1) begin
        target = 1 + ($random(seed) & 32'h7fffffff) % 31;
        ticks = ($random(seed) & 32'h7fffffff) % 200;
        configure(0, target[15:0], 7);
        advance(ticks*DIV);
        expected = ticks % (target+1);
        read_expect(0, expected[15:0]);
        irq_expect((ticks+1)/(target+1));
        configure(0, target[15:0], 5);
        advance((target+ticks)*DIV);
        read_expect(0, target[15:0]); read_expect(2, 5); irq_expect(1);
    end
    $display("PASS timer behavior DIVISOR=%0d", DIVISOR);
    $finish;
end
endmodule
