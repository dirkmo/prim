// Only confirmed CPU halt grants the debug master access. No request storage.
module bus_mux(
    input i_halted,
    input [15:0] i_cpu_addr, i_cpu_data, i_debug_addr, i_debug_data,
    input [1:0] i_cpu_bs, i_debug_bs,
    input i_cpu_we, i_debug_we,
    output [15:0] o_addr, o_data,
    output [1:0] o_bs,
    output o_we,
    input i_ack,
    output o_cpu_ack, o_debug_ack
);
assign o_addr = i_halted ? i_debug_addr : i_cpu_addr;
assign o_data = i_halted ? i_debug_data : i_cpu_data;
assign o_bs = i_halted ? i_debug_bs : i_cpu_bs;
assign o_we = i_halted ? i_debug_we : i_cpu_we;
assign o_cpu_ack = i_ack && !i_halted;
assign o_debug_ack = i_ack && i_halted;
endmodule
