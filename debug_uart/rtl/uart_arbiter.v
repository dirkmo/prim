// Combinational valid/ready arbitration. The downstream TX owns frame timing.
module uart_arbiter(
    input [7:0] i_debug_data,
    input i_debug_valid,
    output o_debug_ready,
    input [6:0] i_output_data,
    input i_output_valid,
    output o_output_ready,
    output [7:0] o_data,
    output o_valid,
    input i_ready
);
assign o_data = i_debug_valid ? i_debug_data : {1'b0, i_output_data};
assign o_valid = i_debug_valid || i_output_valid;
assign o_debug_ready = i_ready;
assign o_output_ready = i_ready && !i_debug_valid;
endmodule
