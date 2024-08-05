module memory(
    input i_clk,

    input [15:0]    i_addr,
    input [15:0]    i_cpu_to_mem,
    output [15:0]   o_mem_to_cpu,
    input [1:0]     i_bs, // byte select
    input           i_we,
    output reg      o_ack,

    output [15:0]   ram_addr,
    inout [15:0]    ram_data,
    output reg      ram_oe_n,
    output reg      ram_we_n
);

reg [15:0] data;

assign ram_addr = i_addr;
assign ram_data = i_we ? i_dat : 15'hz;
assign o_mem_to_cpu = data;

wire cs = |i_bs;
reg r_cs;
always @(posedge i_clk)
    r_cs <= cs;
wire start = cs && ~r_cs;

wire unaligned = i_addr[0];


/*
aligned read:
    ram_addr = (i_addr >> 1), data[] = ram_data[?:?], o_ack = 1
aligned write:
wenn bs&3==3:
    ram_addr = (i_addr >> 1), ram_data = i_cpu_to_mem, o_ack = 1
wenn bs&3!=3:
    read: ram_addr = (i_addr >> 1), data[] = ram_data[?:?], o_ack = 0
    write: ram_addr = (i_addr >> 1), ram_data = {data[], i_cpu_to_mem[]}, o_ack = 1

unaligned read:
wenn bs&1:
    ram_addr = (i_addr >> 1), data[7:0] = ram_data[16:8], o_ack = ~(bs&2)
wenn bs&2:
    ram_addr = (i_addr >> 1)+1, data[15:8] = ram_data[7:0], o_ack = 1

unaligned write:
wenn bs&1:
    read: ram_addr = (i_addr >> 1), data[7:0] = ram_data[7:0], o_ack = 0
    write: ram_addr = (i_addr >> 1), ram_data = {i_cpu_to_mem[7:0], data[7:0]}, o_ack = ~(bs&2)
wenn bs&2:
    read: ram_addr = (i_addr >> 1)+1, data[15:8] = ram_data[7:0], o_ack = 0
    write: ram_addr = (i_addr >> 1)+1, ram_data = {data[15:8], i_cpu_to_mem[15:8]}, o_ack = 1

*/



reg r_state[2:0];
always @(posedge i_clk)
begin
    case (r_state)
        'h0: if (start) begin
            if (notaligned) begin
                r_state <= {2'b10, i_rw};
            end
        end
        'h100: begin

        end
    endcase
end

always @(*)
begin
    if (cs) begin
        ram_oe_n = i_we;
        ram_we_n = ~i_we;
    end else begin
        ram_oe_n = 1'b1;
        ram_we_n = 1'b1;
    end
end


endmodule
