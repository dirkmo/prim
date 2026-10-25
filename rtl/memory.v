// Byte-addressed CPU interface to an asynchronous, whole-word-only SRAM.
// CPU inputs remain stable until ACK; no request registers or RAM reset needed.
module memory #(
    parameter integer READ_CYCLES = 2,
    parameter integer WRITE_CYCLES = 2
)(
    input           i_clk,
    input           i_reset,
    input [15:0]    i_addr,
    input [15:0]    i_cpu_to_mem,
    output [15:0]   o_mem_to_cpu,
    input [1:0]     i_bs,
    input           i_we,
    output          o_ack,

    output [15:0]   ram_addr,
    inout [15:0]    ram_data,
    output          ram_cs_n,
    output          ram_oe_n,
    output          ram_we_n
);

localparam IDLE = 4'd0, READ = 4'd1, TURN = 4'd2, SETUP = 4'd3,
           WRITE = 4'd4, HOLD = 4'd5, RELEASE = 4'd6, DONE = 4'd7;
localparam integer MAX_CYCLES = (READ_CYCLES > WRITE_CYCLES) ? READ_CYCLES : WRITE_CYCLES;
localparam integer WAIT_BITS = (MAX_CYCLES > 1) ? $clog2(MAX_CYCLES) : 1;
reg [3:0] state;
reg [WAIT_BITS-1:0] wait_count;
reg second;
reg [15:0] data; // Shared read result / read-modify-write buffer.

// BS lanes are relative to the CPU byte address, not physical SRAM lanes.
// BS=10 selects only the byte at i_addr+1 using CPU data bits 15:8.
wire high_only = (i_bs == 2'b10);
wire [15:0] byte_addr = i_addr + (high_only ? 16'd1 : 16'd0);
wire [15:0] cpu_data = high_only ? {8'h00, i_cpu_to_mem[15:8]} : i_cpu_to_mem;
wire word_access = (i_bs == 2'b11);
wire two_words = word_access && byte_addr[0];
wire [14:0] word_addr = byte_addr[15:1] + (second ? 15'd1 : 15'd0);
wire drive = !i_reset && ((state == SETUP) || (state == WRITE) || (state == HOLD));

assign ram_addr = {1'b0, word_addr};
assign ram_data = drive ? data : 16'hzzzz;
assign ram_cs_n = i_reset || (state == IDLE) || (state == DONE);
assign ram_oe_n = i_reset || (state != READ);
assign ram_we_n = i_reset || (state != WRITE);
assign o_ack = !i_reset && (state == DONE);
assign o_mem_to_cpu = high_only ? {data[7:0], 8'h00} : data;

always @(posedge i_clk) begin
    if (i_reset) begin
        state <= IDLE;
        wait_count <= 0;
        second <= 0;
    end else begin
        case (state)
            IDLE: begin
                second <= 0;
                wait_count <= 0;
                if (|i_bs) begin
                    if (i_we && word_access && !byte_addr[0]) begin
                        // A complete aligned word needs no read-modify-write.
                        data <= cpu_data;
                        state <= SETUP;
                    end else begin
                        state <= READ;
                    end
                end
            end
            READ: begin
                if (wait_count == READ_CYCLES - 1) begin
                    wait_count <= 0;
                    if (i_we) begin
                        if (second)
                            data <= {ram_data[15:8], cpu_data[15:8]};
                        else if (byte_addr[0])
                            data <= {cpu_data[7:0], ram_data[7:0]};
                        else
                            data <= {ram_data[15:8], cpu_data[7:0]};
                        state <= TURN;
                    end else if (second) begin
                        data[15:8] <= ram_data[7:0];
                        state <= DONE;
                    end else begin
                        data <= (word_access && !byte_addr[0]) ? ram_data :
                                     {8'h00, byte_addr[0] ? ram_data[15:8] : ram_data[7:0]};
                        if (two_words)
                            second <= 1;
                        else
                            state <= DONE;
                    end
                end else begin
                    wait_count <= wait_count + 1'b1;
                end
            end
            TURN: state <= SETUP; // SRAM output disabled, FPGA still high-Z.
            SETUP: state <= WRITE; // Address and data valid before WE falls.
            WRITE: begin
                if (wait_count == WRITE_CYCLES - 1) begin
                    wait_count <= 0;
                    state <= HOLD;
                end else begin
                    wait_count <= wait_count + 1'b1;
                end
            end
            HOLD: state <= RELEASE; // Hold address/data after WE rises.
            RELEASE: begin // Release FPGA data before enabling SRAM output.
                if (two_words && !second) begin
                    second <= 1;
                    state <= READ;
                end else begin
                    state <= DONE;
                end
            end
            DONE: state <= IDLE; // Accept the next request without a CS edge.
            default: state <= IDLE;
        endcase
    end
end
endmodule
