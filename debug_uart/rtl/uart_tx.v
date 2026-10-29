// Minimal unbuffered 8N1 transmitter. A byte is accepted on VALID && READY.
module uart_tx #(
    parameter integer CLKS_PER_BIT = 868
)(
    input i_clk,
    input i_reset,
    input [7:0] i_data,
    input i_valid,
    output o_ready,
    output o_tx
);
localparam integer COUNT_BITS = (CLKS_PER_BIT > 1) ? $clog2(CLKS_PER_BIT) : 1;
reg busy;
reg [9:0] frame;
reg [3:0] bit_index;
reg [COUNT_BITS-1:0] count;
assign o_ready = !i_reset && !busy;
assign o_tx = (i_reset || !busy) ? 1'b1 : frame[0];

always @(posedge i_clk) begin
    if (i_reset) begin
        busy <= 0;
    end else if (!busy) begin
        if (i_valid) begin
            frame <= {1'b1, i_data, 1'b0};
            bit_index <= 0;
            count <= CLKS_PER_BIT - 1;
            busy <= 1;
        end
    end else if (count == 0) begin
        count <= CLKS_PER_BIT - 1;
        if (bit_index == 9) begin
            busy <= 0;
        end else begin
            frame <= {1'b1, frame[9:1]};
            bit_index <= bit_index + 1'b1;
        end
    end else begin
        count <= count - 1'b1;
    end
end
endmodule
