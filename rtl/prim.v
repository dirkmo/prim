module Prim(
    input i_reset,
    input i_clk,

    output [15:0] o_addr,
    output [15:0] o_dat,
    input  [15:0] i_dat,
    output [1:0]  o_bs, // byte select
    output        o_we,
    input         i_ack,

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
reg [7:0] r_ir /* verilator public */; // instruction register
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
localparam
    PHASE_FETCH = 0,
    PHASE_EXECUTE = 1;

reg r_phase /* verilator public */;
wire w_fetch = (r_phase == PHASE_FETCH);
wire w_execute = (r_phase == PHASE_EXECUTE);

// alu
reg [15:0] r_alu;
always @(posedge i_clk) begin
    case (r_ir[6:0])
        OP_NOP:         r_alu <= {T};
        OP_CALL:        r_alu <= {T};
        OP_JP:          r_alu <= {T};
        OP_JZ:          r_alu <= {T};
        OP_AND:         r_alu <= {N & T};
        OP_OR:          r_alu <= {N | T};
        OP_XOR:         r_alu <= {N ^ T};
        OP_NOT:         r_alu <= {~T};
        OP_SR:          r_alu <= {1'b0, T[15:1]};
        OP_SRW:         r_alu <= {8'b0, T[15:8]};
        OP_SL:          {r_carry, r_alu} <= {T[15:0], 1'b0};
        OP_SLW:         r_alu <= {T[7:0], 8'b0};
        OP_ADD:         {r_carry, r_alu} <= {1'b0, N} + {1'b0, T};
        OP_SUB:         {r_carry, r_alu} <= {1'b0, N} - {1'b0, T};
        OP_LTS:         r_alu <= {16{($signed(N) < $signed(T))}};
        OP_LTU:         r_alu <= {16{(N < T)}};
        OP_SWAP:        r_alu <= N;
        OP_OVER:        r_alu <= N;
        OP_DUP:         r_alu <= T;
        OP_NIP:         r_alu <= T;
        OP_ROT:         r_alu <= T;
        OP_NROT:        r_alu <= T;
        OP_DROP:        r_alu <= T;
        OP_RDROP:       r_alu <= T;
        OP_CARRY:       r_alu <= {15'h0, r_carry};
        OP_TO_R:        r_alu <= T;
        OP_FROM_R:      r_alu <= T;
        OP_INT:         r_alu <= T;
        OP_FETCH:       r_alu <= T;
        OP_BYTE_FETCH:  r_alu <= T;
        OP_STORE:       r_alu <= T;
        OP_BYTE_STORE:  r_alu <= T;
        // OP_PUSH8:       r_alu <= T;
        // OP_PUSH:        r_alu <= T;
        // OP_BREAK:       r_alu <= T;
        default:        r_alu <= T;
    endcase
end

// r_phase
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_phase <= 0;
    end else begin
        case (r_phase)
            PHASE_FETCH: if(i_ack) r_phase <= PHASE_EXECUTE;
            PHASE_EXECUTE: if (~w_memop || i_ack) r_phase <= PHASE_FETCH;
            default: r_phase <= PHASE_FETCH;
        endcase
    end
end

// Program counter r_pc
reg [15:0] r_pc_next;
wire [15:0] pc_plus_1 = r_pc + 1'd1;
always @(*)
begin
    casez (r_ir[6:0])
        OP_CALL: r_pc_next = T;
        OP_JP: r_pc_next = T;
        OP_JZ: r_pc_next = (T==16'h0) ? N : pc_plus_1;
        OP_PUSH8: if (r_ir[7]) r_pc_next = T; else r_pc_next = r_pc + 2;
        OP_PUSH:  if (r_ir[7]) r_pc_next = T; else r_pc_next = r_pc + 3;
        default: r_pc_next = pc_plus_1;
    endcase
end

always @(posedge i_clk)
begin
    if (i_reset) begin
        r_pc <= 16'h0000;
    end else if (w_execute) begin // TODO: nicht richtig, warten auf Ende der Mem-Op
        r_pc <= r_pc_next;
    end
end

// instruction register
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_ir <= 8'h00;
    end else if ((w_fetch) && i_ack) begin
        r_ir <= i_dat[7:0];
        `ifdef SIM
        if (i_dat[6:0] == OP_SIMEND) $finish();
        `endif
    end
end

// top of data stack
always @(posedge i_clk)
begin
    if (i_reset) begin
        T <= 16'h00;
    end else begin
        case (r_ir[6:0])
            OP_PUSH8: T <= i_dat;
            OP_PUSH: T <= i_dat;
            OP_SWAP: T <= N;
            OP_ROT: T <= THIRD;
            OP_NROT: T <= N;
            default: ;
        endcase
    end
end

// ----------------------------------------------------------------------------
// memory interface

wire w_memwrite = (r_ir[6:0] == OP_STORE) || (r_ir[6:0] == OP_BYTE_STORE);
wire w_memop8 = (r_ir[6:0] == OP_BYTE_STORE) || (r_ir[6:0] == OP_BYTE_FETCH) || (r_ir[6:0] == OP_PUSH8);
wire w_memop16 = (r_ir[6:0] == OP_STORE) || (r_ir[6:0] == OP_FETCH) || (r_ir[6:0] == OP_PUSH);
wire w_memop = w_memop8 || w_memop16;

reg [1:0] r_bs;
always @(*) begin
    r_bs = 2'b00;
    if (w_fetch) begin
        r_bs = 2'b01;
    end else if (w_execute) begin
        if (w_memop8) begin
            r_bs = 2'b01;
        end else if (w_memop16) begin
            r_bs = 2'b11;
        end
    end
    if (i_reset) begin
        r_bs = 2'b00;
    end
end

assign o_addr = w_execute ? T : r_pc;
assign o_we = w_execute && w_memwrite;
assign o_bs = r_bs;
assign o_dat = N;



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
