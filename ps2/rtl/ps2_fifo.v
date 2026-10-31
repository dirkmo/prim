// Raw scan-code FIFO and byte-register semantics. Reads are combinational;
// i_pop/i_csr_write denote a completed selected bus byte, not a request level.
module ps2_fifo #(
    parameter integer DEPTH = 16
)(
    input i_clk, i_reset,
    input [7:0] i_data,
    input i_valid, i_error, i_pop, i_csr_write,
    input [7:0] i_csr_data,
    output [7:0] o_data, o_csr,
    output o_event
);
localparam integer PW = DEPTH > 1 ? $clog2(DEPTH) : 1;
reg [7:0] storage [0:DEPTH-1];
reg [PW-1:0] head, tail;
reg [PW:0] count;
reg rxie, frame_error, overflow;
wire empty = count == 0;
wire full = count == DEPTH;
wire pop = i_pop && !empty;
wire push = i_valid && (!full || pop);
wire lost = i_valid && full && !pop;
assign o_data = empty ? 8'b0 : storage[head];
assign o_csr = {3'b0, overflow, frame_error, rxie, full, !empty};
// Enable/backlog replay belongs to the shared pending block, which already
// tracks source enable transitions. This avoids a duplicate enable IRQ.
assign o_event = !i_reset && rxie && (i_valid || i_error);
always @(posedge i_clk) begin
    if (i_reset) begin
        head <= 0; tail <= 0; count <= 0;
        rxie <= 0; frame_error <= 0; overflow <= 0;
    end else begin
        if (i_csr_write) begin
            rxie <= i_csr_data[2];
            if (i_csr_data[3]) frame_error <= 0;
            if (i_csr_data[4]) overflow <= 0;
        end
        if (i_error) frame_error <= 1;
        if (lost) overflow <= 1;
        if (pop) head <= DEPTH == 1 ? 0 : head + 1'b1;
        if (push) begin
            storage[tail] <= i_data;
            tail <= DEPTH == 1 ? 0 : tail + 1'b1;
        end
        case ({push,pop})
            2'b10: count <= count + 1'b1;
            2'b01: count <= count - 1'b1;
            default: begin end
        endcase
    end
end
`ifndef SYNTHESIS
initial begin
    if (DEPTH < 1 || (DEPTH & (DEPTH-1)) != 0)
        $fatal(1, "PS/2 FIFO depth must be a positive power of two");
end
`endif
endmodule
