module Prim(
    input i_reset,
    input i_clk,

    output [15:0] o_addr,
    output [15:0] o_dat,
    input  [15:0] i_dat,
    output [1:0]  o_bs, // byte select
    input         i_ack,
    output        o_we,
    output        o_cs,

    input         i_irq
);

parameter
    DSS /* verilator public */ = 4, // data stack size: 2^DSS
    RSS /* verilator public */ = 4; // return stack size: 2^RSS

`include "opcodes.v"

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

//
reg r_phase /* verilator public */;

// alu
reg [16:0] r_alu;
always @(*)
    case (r_ir[6:0])
        OP_NOP:         r_alu = {1'b0, T};
        OP_CALL:        r_alu = {1'b0, T};
        OP_JP:          r_alu = {1'b0, T};
        OP_JZ:          r_alu = {1'b0, T};
        OP_AND:         r_alu = {1'b0, N & T};
        OP_OR:          r_alu = {1'b0, N | T};
        OP_XOR:         r_alu = {1'b0, N ^ T};
        OP_NOT:         r_alu = {1'b0, ~T};
        OP_SR:          r_alu = {2'b0, T[15:1]};
        OP_SRW:         r_alu = {9'b0, T[15:8]};
        OP_SL:          r_alu = {1'b0, T[14:0], 1'b0};
        OP_SLW:         r_alu = {1'b0, T[7:0], 8'b0};
        OP_ADD:         r_alu = {1'b0, N} + {1'b0, T};
        OP_SUB:         r_alu = {1'b0, N} - {1'b0, T};
        OP_LTS:         r_alu = {17{($signed(N) < $signed(T))}};
        OP_LTU:         r_alu = {17{(N < T)}};
        OP_SWAP:        r_alu = {1'b0, N};
        OP_OVER:        r_alu = {1'b0, N};
        OP_DUP:         r_alu = {1'b0, T};
        OP_NIP:         r_alu = {1'b0, T};
        OP_ROT:         r_alu = {1'b0, T};
        OP_NROT:        r_alu = {1'b0, T};
        OP_DROP:        r_alu = {1'b0, T};
        OP_RDROP:       r_alu = {1'b0, T};
        OP_CARRY:       r_alu = {1'b0, T};
        OP_TO_R:        r_alu = {1'b0, T};
        OP_FROM_R:      r_alu = {1'b0, T};
        OP_INT:         r_alu = {1'b0, T};
        OP_FETCH:       r_alu = {1'b0, T};
        OP_BYTE_FETCH:  r_alu = {1'b0, T};
        OP_STORE:       r_alu = {1'b0, T};
        OP_BYTE_STORE:  r_alu = {1'b0, T};
        OP_PUSH8:       r_alu = {1'b0, T};
        OP_PUSH:        r_alu = {1'b0, T};
        OP_BREAK:       r_alu = {1'b0, T};
        default:        r_alu = {1'b0, T};
    endcase

// r_phase
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_phase = 0;
    end else begin
        r_phase <= r_phase + 1;
    end
end

// Program counter r_pc
reg [15:0] r_pc_next;
wire [15:0] pc_plus_1 = r_pc + 1'd1;
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_pc_next = 16'h0000;
    end else begin
        case (r_ir[6:0])
            OP_CALL: r_pc_next = T;
            OP_JP: r_pc_next = T;
            OP_JZ: r_pc_next = (T==16'h0) ? N : pc_plus_1;
            default: r_pc_next = pc_plus_1;
        endcase
    end
end

/*
# ALU-OPs
1. fetch
2. *--dsp=alu, pc++

# call
1. fetch
2. *(++rsp)=pc, pc=*dsp--

# jp
1. fetch
2. pc=(cond ? pc=*dsp-- : pc=pc+1)

# memory read
1. fetch
2. *dsp = mem[*dsp]

# memory write
1. fetch
2. mem[*dsp] = *--dsp

# stack
1. fetch
rot
nrot
swap
dup
nip
drop
rdrop
>r
r>
*/

endmodule
