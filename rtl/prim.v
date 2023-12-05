module Prim(
    input i_reset,
    input i_clk,

    output [15:0] o_addr,
    output [15:0] o_dat,
    input  [15:0] i_dat,
    output [1:0]  o_bs; // byte select
    input         i_ack,
    output        o_we,
    output        o_cs,

    input         i_irq
);

parameter
    DSS /* verilator public */ = 4, // data stack size: 2^DSS
    RSS /* verilator public */ = 4; // return stack size: 2^RSS

localparam
    OP_NOP = 7'h00,
    OP_CALL = 7'h01,
    OP_JP = 7'h02,
    OP_JZ = 7'h03,
    OP_AND = 7'h04,
    OP_OR = 7'h05,
    OP_XOR = 7'h06,
    OP_NOT = 7'h07,
    OP_SR = 7'h08,
    OP_SRW =7'hx9,
    OP_SL = 7'h0a,
    OP_SLW = 7'h0b,
    OP_ADD = 7'h0c,
    OP_SUB = 7'h0d,
    OP_LTS = 7'h0e,
    OP_LTU = 7'h0f,
    OP_SWAP = 7'h10,
    OP_OVER = 7'h11,
    OP_DUP = 7'h12,
    OP_NIP = 7'h13,
    OP_ROT = 7'h14,
    OP_NROT = 7'h15,
    OP_DROP = 7'h16,
    OP_RDROP = 7'h17,
    OP_CARRY = 7'h18,
    OP_TO_R = 7'h19,
    OP_FROM_R = 7'h1a,
    OP_INT = 7'h1b,
    OP_FETCH = 7'h1c,
    OP_BYTE_FETCH = 7'h1d,
    OP_STORE = 7'h1e,
    OP_BYTE_STORE = 7'h1f,
    OP_PUSH8  = 7'h20,
    OP_PUSH = 7'h21,
    OP_BREAK = 7'h22;


// registers
reg [15:0] r_pc /* verilator public */; // program counter
reg [15:0] T /* verilator public */; // top of dstack
reg [15:0] N /* verilator public */; // 2nd on dstack
reg [15:0] R /* verilator public */; // top of rstack
reg [15:0] r_ir /* verilator public */; // instruction register
reg r_carry;

// stacks
reg [15:0] r_dstack[0:2**DSS-1] /* verilator public */;
reg [15:0] r_rstack[0:2**RSS-1] /* verilator public */;

// stack pointers
reg [DSS-1:0] r_dsp /* verilator public */;
reg [RSS-1:0] r_rsp /* verilator public */;

//
wire [15:0] THIRD = r_dstack[r_dsp]; // third element

// alu
wire [16:0] w_alu;
always @(*)
    case (r_ir[6:0])
        OP_NOP:         w_alu = {1'b0, T};
        OP_CALL:        w_alu = {1'b0, T};
        OP_JP:          w_alu = {1'b0, T};
        OP_JZ:          w_alu = {1'b0, T};
        OP_AND:         w_alu = {1'b0, N & T};
        OP_OR:          w_alu = {1'b0, N | T};
        OP_XOR:         w_alu = {1'b0, N ^ T};
        OP_NOT:         w_alu = {1'b0, ~T};
        OP_SR:          w_alu = {2'b0, T[15:1]};
        OP_SRW:         w_alu = {9'b0, T[15:8]};
        OP_SL:          w_alu = {1'b0, T[14:0], 1'b0};
        OP_SLW:         w_alu = {1'b0, T[7:0], 8'b0};
        OP_ADD:         w_alu = {1'b0, N} + {1'b0, T};
        OP_SUB:         w_alu = {1'b0, N} - {1'b0, T};
        OP_LTS:         w_alu = {17{($signed(N) < $signed(T))}};
        OP_LTU:         w_alu = {17{(N < T)}};
        OP_SWAP:        w_alu = {1'b0, N};
        OP_OVER:        w_alu = {1'b0, N};
        OP_DUP:         w_alu = {1'b0, T};
        OP_NIP:         w_alu = {1'b0, T};
        OP_ROT:         w_alu = {1'b0, T};
        OP_NROT:        w_alu = {1'b0, T};
        OP_DROP:        w_alu = {1'b0, T};
        OP_RDROP:       w_alu = {1'b0, T};
        OP_CARRY:       w_alu = {1'b0, T};
        OP_TO_R:        w_alu = {1'b0, T};
        OP_FROM_R:      w_alu = {1'b0, T};
        OP_INT:         w_alu = {1'b0, T};
        OP_FETCH:       w_alu = {1'b0, T};
        OP_BYTE_FETCH:  w_alu = {1'b0, T};
        OP_STORE:       w_alu = {1'b0, T};
        OP_BYTE_STORE:  w_alu = {1'b0, T};
        OP_PUSH8:       w_alu = {1'b0, T};
        OP_PUSH:        w_alu = {1'b0, T};
        OP_BREAK:       w_alu = {1'b0, T};
        default:        w_alu = {1'b0, T};
    endcase



endmodule
