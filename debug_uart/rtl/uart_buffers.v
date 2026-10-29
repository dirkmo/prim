// One CPU RX register and one pending CPU TX byte, independent of debug traffic.
module uart_buffers(
    input i_clk, i_reset,
    input [7:0] i_rx_data,
    input i_rx_valid, i_input_read,
    output reg [6:0] o_input_data,
    output [1:0] o_status,
    input [6:0] i_output_data,
    input i_output_valid,
    output o_output_ready,
    output reg [6:0] o_tx_data,
    output o_tx_valid,
    input i_tx_ready
);
reg received, pending;
assign o_status = {!pending, received};
assign o_output_ready = !i_reset && !pending;
assign o_tx_valid = !i_reset && pending;
always @(posedge i_clk) begin
    if (i_reset) begin
        o_input_data <= 0; received <= 0;
        o_tx_data <= 0; pending <= 0;
    end else begin
        if (i_input_read) received <= 0;
        // New reception wins over consumption; reads retain the last byte.
        if (i_rx_valid && !i_rx_data[7]) begin
            o_input_data <= i_rx_data[6:0]; received <= 1;
        end
        if (o_tx_valid && i_tx_ready) pending <= 0;
        if (i_output_valid && o_output_ready) begin
            o_tx_data <= i_output_data; pending <= 1;
        end
    end
end
endmodule
