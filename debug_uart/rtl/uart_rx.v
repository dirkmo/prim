// Two-flop input synchronizer, one sample per bit at its centre. No FIFO.
module uart_rx #(parameter integer CLKS_PER_BIT = 868)(
    input i_clk, i_reset, i_rx,
    output reg [7:0] o_data,
    output reg o_valid
);
localparam integer CW = CLKS_PER_BIT > 1 ? $clog2(CLKS_PER_BIT) : 1;
localparam integer START_COUNT = (CLKS_PER_BIT > 1 ? CLKS_PER_BIT/2 : 1) - 1;
localparam integer BIT_COUNT = CLKS_PER_BIT - 1;
(* async_reg = "true" *) reg sync1, sync2;
reg [CW-1:0] count;
reg [3:0] bit_index;
reg busy;
always @(posedge i_clk) begin
    sync1 <= i_rx;
    sync2 <= sync1;
    o_valid <= 0;
    if (i_reset) begin
        sync1 <= 1; sync2 <= 1; busy <= 0;
    end else if (!busy) begin
        if (!sync2) begin
            busy <= 1;
            bit_index <= 0;
            count <= START_COUNT[CW-1:0];
        end
    end else if (count != 0) count <= count - 1'b1;
    else begin
        count <= BIT_COUNT[CW-1:0];
        if (bit_index == 0) begin
            if (sync2) busy <= 0; // reject a short start glitch
            else bit_index <= 1;
        end else if (bit_index == 9) begin
            busy <= 0;
            o_valid <= 1; // stop-bit diagnostics intentionally omitted
        end else begin
            o_data[bit_index-1] <= sync2;
            bit_index <= bit_index + 1'b1;
        end
    end
end
endmodule
