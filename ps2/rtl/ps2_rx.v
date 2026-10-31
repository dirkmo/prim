// Receive-only PS/2, entirely in the system clock domain.
module ps2_rx #(
    parameter integer CLK_HZ = 25000000,
    parameter integer FILTER_CYCLES = 8,
    parameter integer TIMEOUT_CYCLES = CLK_HZ / 500
)(
    input i_clk, i_reset, i_ps2_clk, i_ps2_data,
    output reg [7:0] o_data,
    output reg o_valid, o_error
);
localparam integer FW = FILTER_CYCLES > 1 ? $clog2(FILTER_CYCLES) : 1;
localparam integer TW = TIMEOUT_CYCLES > 1 ? $clog2(TIMEOUT_CYCLES) : 1;
(* async_reg = "true" *) reg [1:0] clk_sync, data_sync;
reg filtered_clk;
reg [FW-1:0] stable;
reg [TW-1:0] timeout_count;
reg [3:0] bit_count;
reg [7:0] shift;
reg parity;
wire transition = clk_sync[1] != filtered_clk && stable == FILTER_CYCLES-1;
wire falling = transition && !clk_sync[1];

always @(posedge i_clk) begin
    if (i_reset) begin
        clk_sync <= 2'b11; data_sync <= 2'b11;
        filtered_clk <= 1; stable <= 0;
        bit_count <= 0; timeout_count <= 0;
        shift <= 0; parity <= 0;
        o_data <= 0; o_valid <= 0; o_error <= 0;
    end else begin
        clk_sync <= {clk_sync[0], i_ps2_clk};
        data_sync <= {data_sync[0], i_ps2_data};
        o_valid <= 0; o_error <= 0;
        if (clk_sync[1] == filtered_clk) stable <= 0;
        else if (transition) begin
            filtered_clk <= clk_sync[1]; stable <= 0;
        end else stable <= stable + 1'b1;

        if (falling) begin
            timeout_count <= 0;
            if (bit_count == 0) begin
                if (!data_sync[1]) begin bit_count <= 1; parity <= 0; end
            end else if (bit_count <= 8) begin
                shift <= {data_sync[1], shift[7:1]};
                parity <= parity ^ data_sync[1];
                bit_count <= bit_count + 1'b1;
            end else if (bit_count == 9) begin
                parity <= parity ^ data_sync[1]; bit_count <= 10;
            end else begin
                bit_count <= 0;
                if (data_sync[1] && parity) begin o_data <= shift; o_valid <= 1; end
                else o_error <= 1;
            end
        end else if (bit_count != 0) begin
            if (timeout_count == TIMEOUT_CYCLES-1) begin
                bit_count <= 0; timeout_count <= 0; o_error <= 1;
            end else timeout_count <= timeout_count + 1'b1;
        end else timeout_count <= 0;
    end
end
`ifndef SYNTHESIS
initial begin
    if (CLK_HZ < 1 || FILTER_CYCLES < 1 || TIMEOUT_CYCLES < 1)
        $fatal(1, "PS/2 receiver parameters must be positive");
end
`endif
endmodule
