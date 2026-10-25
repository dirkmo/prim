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

// stack pointers
reg [DSS-1:0] r_dsp /* verilator public */;
reg [RSS-1:0] r_rsp /* verilator public */;

// registers
reg [15:0] r_pc /* verilator public */; // program counter
reg [15:0] T /* verilator public */; // top of dstack
reg [15:0] N /* verilator public */; // 2nd on dstack
wire [15:0] R /* verilator public */ = r_rstack[r_rsp]; // top of rstack
reg [7:0] r_ir /* verilator public */; // instruction register
reg r_carry;

// stacks
reg [15:0] r_dstack[0:2**DSS-1] /* verilator public */;
reg [15:0] r_rstack[0:2**RSS-1] /* verilator public */;

//
wire [DSS-1:0] w_dsp_dec2_amt = {{(DSS-2){1'b0}}, 2'b10};
wire [15:0] THIRD = r_dstack[(r_dsp - 1'b1) & ((1 << DSS)-1)]; // third element

// pop from stack
wire w_popop;

//
localparam
    PHASE_FETCH = 2'h0,
    PHASE_MEMWAIT = 2'h1,
    PHASE_EXECUTE = 2'h2;

reg [1:0] r_phase /* verilator public */;
wire w_phase_fetch = (r_phase == PHASE_FETCH);
wire w_phase_execute = (r_phase == PHASE_EXECUTE);
wire w_phase_memop = (r_phase == PHASE_MEMWAIT);

reg [15:0] r_mem_data;

// alu
reg [16:0] r_alu;
always @(posedge i_clk) begin
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
        OP_SL:          r_alu = {T[15:0], 1'b0};
        OP_SLW:         r_alu = {T[7:0], 9'b0};
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
        OP_CARRY:       r_alu = {16'h0, r_carry};
        OP_TO_R:        r_alu = {1'b0, T};
        OP_FROM_R:      r_alu = {1'b0, T};
        OP_INT:         r_alu = {1'b0, T};
        OP_FETCH:       r_alu = {1'b0, T};
        OP_BYTE_FETCH:  r_alu = {1'b0, T};
        OP_STORE:       r_alu = {1'b0, T};
        OP_BYTE_STORE:  r_alu = {1'b0, T};
        // OP_PUSH8:       r_alu = T;
        // OP_PUSH:        r_alu = T;
        // OP_BREAK:       r_alu = T;
        default:        r_alu = {1'b0, T};
    endcase
end

// r_phase
// Strict 3-phase flow:
//   FETCH -> (optional MEMWAIT) -> EXECUTE -> FETCH
// The phase transition is driven together with the fetch latch so the decision
// to enter MEMWAIT is based on the opcode that was just fetched, not a stale
// value from a separate combinational path.
wire w_fetch_memop = (i_dat[6:0] == OP_PUSH) ||
                    (i_dat[6:0] == OP_PUSH8) ||
                    (i_dat[6:0] == OP_BYTE_FETCH) ||
                    (i_dat[6:0] == OP_FETCH) ||
                    (i_dat[6:0] == OP_BYTE_STORE) ||
                    (i_dat[6:0] == OP_STORE);

always @(posedge i_clk)
begin
    if (i_reset) begin
        r_phase <= PHASE_FETCH;
    end else begin
        case (r_phase)
            PHASE_FETCH:
                if (i_ack)
                    r_phase <= w_fetch_memop ? PHASE_MEMWAIT : PHASE_EXECUTE;
            PHASE_MEMWAIT:
                if (i_ack)
                    r_phase <= PHASE_EXECUTE;
            PHASE_EXECUTE:
                r_phase <= PHASE_FETCH;
            default:
                r_phase <= PHASE_FETCH;
        endcase
    end
end

// Program counter r_pc
reg [15:0] r_pc_next;
wire [15:0] pc_plus_1 = r_pc + 1'd1;
always @(*)
begin
    if (r_ir[7]) begin
        r_pc_next = R;
    end else begin
        casez (r_ir)
            {1'b0, OP_CALL}: r_pc_next = T;
            {1'b0, OP_JP}: r_pc_next = T;
            {1'b0, OP_JZ}: r_pc_next = (N==16'h0) ? T : pc_plus_1;
            {1'b0, OP_PUSH8}: r_pc_next = r_pc + 2;
            {1'b0, OP_PUSH}:  r_pc_next = r_pc + 3;
            default: r_pc_next = pc_plus_1;
        endcase
    end
end

always @(posedge i_clk)
begin
    if (i_reset) begin
        r_pc <= 16'h0000;
    end else if (w_phase_execute) begin
        // PC is advanced only after the instruction has fully completed its
        // fetch / memory wait sequence. This keeps immediate operands and memory
        // transactions aligned with the execute phase.
        $display("EXEC pc=%0d ir=%02x next=%04x T=%04x N=%04x R=%04x dsp=%0d rsp=%0d", r_pc, r_ir, r_pc_next, T, N, R, r_dsp, r_rsp);
        r_pc <= r_pc_next;
    end
end

// instruction register
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_ir <= 8'h00;
        r_mem_data <= 16'h0000;
    end else if (w_phase_fetch && i_ack) begin
        r_ir <= i_dat[7:0];
        `ifdef SIM
        if (i_dat[6:0] == OP_SIMEND) $finish();
        `endif
    end else if (w_phase_memop && i_ack) begin
        // Latch the immediate or memory operand once in MEMWAIT and consume it in
        // EXECUTE. Doing so avoids using stale fetched bytes when the next control
        // flow instruction sees the top-of-stack.
        r_mem_data <= i_dat;
    end
end

// stack helpers for stack-depth management in the execution phase.
wire [DSS-1:0] w_dsp_dec1 = r_dsp - {{(DSS-1){1'b0}}, 1'b1};
wire [DSS-1:0] w_dsp_dec2 = r_dsp - w_dsp_dec2_amt;
wire [DSS-1:0] w_dsp_inc1 = r_dsp + {{(DSS-1){1'b0}}, 1'b1};
wire [DSS-1:0] w_second_idx = (r_dsp - {{(DSS-1){1'b0}}, 1'b1}) & ((1 << DSS)-1);
wire [DSS-1:0] w_third_idx  = (r_dsp - {{(DSS-1){1'b0}}, 1'b1}) & ((1 << DSS)-1);
wire [DSS-1:0] w_fourth_idx = (r_dsp - w_dsp_dec2_amt) & ((1 << DSS)-1);
wire [15:0] w_stack_second = r_dstack[w_second_idx];
wire [15:0] w_stack_third  = r_dstack[w_third_idx];
wire [15:0] w_stack_fourth = r_dstack[w_fourth_idx];

// top of data stack
always @(posedge i_clk)
begin
    if (i_reset) begin
        T <= 16'h00;
    end else if (w_phase_execute) begin
        case (r_ir[6:0])
            OP_PUSH,
            OP_PUSH8: begin
                T <= r_mem_data;
            end
            OP_FETCH: begin
                T <= r_mem_data;
            end
            OP_BYTE_FETCH: begin
                T <= {8'h00, r_mem_data[7:0]};
            end
            OP_DUP: begin
                T <= T;
            end
            OP_SWAP: begin
                T <= N;
            end
            OP_OVER: begin
                T <= N;
            end
            OP_ROT: begin
                T <= w_stack_third;
            end
            OP_NROT: begin
                T <= N;
            end
            OP_DROP,
            OP_CALL,
            OP_JP,
            OP_AND,
            OP_OR,
            OP_XOR,
            OP_NOT,
            OP_ADD,
            OP_SUB,
            OP_LTS,
            OP_LTU,
            OP_TO_R,
            OP_INT: begin
                T <= N;
            end
            OP_STORE,
            OP_BYTE_STORE: begin
                T <= w_stack_third;
            end
            OP_JZ: begin
                T <= w_stack_third;
            end
            OP_FROM_R: begin
                T <= R;
            end
            default:
                if (r_ir[6:0] == OP_CARRY) begin
                    T <= {15'h0, r_carry};
                end else begin
                    T <= r_alu[15:0];
                end
        endcase
    end else if (w_phase_fetch) begin
        $display("T: %x, N: %x, 3rd: %x, R: %x", T, N, THIRD, R);
    end
end

// 2nd on data stack
always @(posedge i_clk)
begin
    if (i_reset) begin
        N <= 16'h00;
    end else if (w_phase_execute) begin
        case (r_ir[6:0])
            OP_PUSH,
            OP_PUSH8: begin
                N <= T;
            end
            OP_DUP: begin
                N <= T;
            end
            OP_SWAP: begin
                N <= T;
            end
            OP_OVER: begin
                N <= T;
            end
            OP_NIP: begin
                N <= w_stack_third;
            end
            OP_ROT: begin
                N <= T;
            end
            OP_NROT: begin
                N <= w_stack_third;
            end
            OP_DROP,
            OP_CALL,
            OP_JP,
            OP_AND,
            OP_OR,
            OP_XOR,
            OP_NOT,
            OP_ADD,
            OP_SUB,
            OP_LTS,
            OP_LTU,
            OP_TO_R,
            OP_INT: begin
                N <= w_stack_third;
            end
            OP_JZ,
            OP_STORE,
            OP_BYTE_STORE: begin
                N <= w_stack_fourth;
            end
            OP_FROM_R: begin
                N <= T;
            end
            default: begin
            end
        endcase
    end
end

// 3rd on data stack / stack-depth bookkeeping
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_dstack[0] <= 16'h0;
        r_dstack[1] <= 16'h0;
        r_dstack[2] <= 16'h0;
        r_dstack[3] <= 16'h0;
    end else if (w_phase_execute) begin
        // preserve the virtual stack order for later third-element access.
        case (r_ir[6:0])
            OP_PUSH,
            OP_PUSH8: begin
                r_dstack[w_dsp_inc1] <= T;
            end
            OP_DROP,
            OP_NIP,
            OP_CALL,
            OP_JP,
            OP_AND,
            OP_OR,
            OP_XOR,
            OP_NOT,
            OP_ADD,
            OP_SUB,
            OP_LTS,
            OP_LTU,
            OP_TO_R,
            OP_INT: begin
                r_dstack[r_dsp] <= N;
            end
            OP_DUP: begin
                r_dstack[w_dsp_inc1] <= T;
            end
            OP_SWAP: begin
                r_dstack[r_dsp] <= N;
                r_dstack[w_dsp_dec1] <= T;
            end
            OP_OVER: begin
                r_dstack[w_dsp_inc1] <= N;
            end
            OP_ROT: begin
                r_dstack[r_dsp] <= T;
                r_dstack[w_dsp_dec1] <= N;
            end
            OP_NROT: begin
                r_dstack[r_dsp] <= w_stack_third;
                r_dstack[w_dsp_dec1] <= T;
            end
            default: begin
            end
        endcase
    end
end

// return stack
// Match the Python model: push first increments the pointer, then writes to the
// new top-of-stack cell. Return pops by decrementing the pointer and reading
// the new top-of-stack value.
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_rstack[0] <= 16'h0000;
        r_rstack[1] <= 16'h0000;
        r_rstack[2] <= 16'h0000;
        r_rstack[3] <= 16'h0000;
    end else if (w_phase_execute) begin
        case (r_ir[7:0])
            {1'b0, OP_CALL}: r_rstack[r_rsp + 1'b1] <= pc_plus_1;
            {1'b0, OP_INT}:  r_rstack[r_rsp + 1'b1] <= pc_plus_1;
            {1'b0, OP_TO_R}: r_rstack[r_rsp + 1'b1] <= T;
            default: ;
        endcase
    end
end

// data stack pointer
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_dsp <= 'h00;
    end else if (w_phase_execute) begin
        case (r_ir[6:0])
            OP_PUSH,
            OP_PUSH8,
            OP_DUP,
            OP_OVER,
            OP_FROM_R: begin
                r_dsp <= w_dsp_inc1;
            end
            OP_DROP,
            OP_NIP,
            OP_CALL,
            OP_JP,
            OP_AND,
            OP_OR,
            OP_XOR,
            OP_NOT,
            OP_ADD,
            OP_SUB,
            OP_LTS,
            OP_LTU,
            OP_TO_R,
            OP_INT: begin
                r_dsp <= w_dsp_dec1;
            end
            OP_STORE,
            OP_BYTE_STORE: begin
                r_dsp <= w_dsp_dec2;
            end
            OP_JZ: begin
                r_dsp <= w_dsp_dec2;
            end
            default: begin
            end
        endcase
    end
end

// return stack pointer
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_rsp <= 'h00;
    end else if (w_phase_execute) begin
        casez (r_ir[7:0])
            {1'b0, OP_CALL}: r_rsp <= r_rsp + 1;
            {1'b0, OP_INT}: r_rsp <= r_rsp + 1;
            {1'b0, OP_TO_R}: r_rsp <= r_rsp + 1;
            {1'b0, OP_FROM_R}: r_rsp <= r_rsp - 1;
            {1'b0, OP_RDROP}: r_rsp <= r_rsp - 1;
            {1'b1, 7'b???????}: r_rsp <= r_rsp - 1;
            default: ;
        endcase
    end
end

// carry
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_carry <= 1'b0;
    end else if (w_phase_execute) begin
        casez (r_ir[6:0])
            OP_ADD: r_carry <= r_alu[16];
            OP_SUB: r_carry <= r_alu[16];
            OP_SL: r_carry <= r_alu[16];
            OP_LTS: r_carry <= r_alu[16];
            OP_LTU: r_carry <= r_alu[16];
            OP_CARRY: r_carry <= r_alu[16];
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
wire w_pushop = (r_ir[6:0] == OP_PUSH) | (r_ir[6:0] == OP_PUSH8);
assign w_popop = (r_ir[6:0] == OP_CALL) ||
                (r_ir[6:0] == OP_JZ) ||
                (r_ir[6:0] == OP_JP) ||
                (r_ir[6:0] == OP_AND) ||
                (r_ir[6:0] == OP_OR) ||
                (r_ir[6:0] == OP_XOR) ||
                (r_ir[6:0] == OP_NOT) ||
                (r_ir[6:0] == OP_ADD) ||
                (r_ir[6:0] == OP_SUB) ||
                (r_ir[6:0] == OP_LTS) ||
                (r_ir[6:0] == OP_LTU) ||
                (r_ir[6:0] == OP_NIP) ||
                (r_ir[6:0] == OP_DROP) ||
                (r_ir[6:0] == OP_TO_R) ||
                (r_ir[6:0] == OP_INT) ||
                (r_ir[6:0] == OP_FETCH) ||
                (r_ir[6:0] == OP_BYTE_FETCH) ||
                (r_ir[6:0] == OP_STORE) ||
                (r_ir[6:0] == OP_BYTE_STORE);
                //(r_ir[6:0] == OP_STORE) ||
                //(r_ir[6:0] == OP_BYTE_STORE);

// byte select
reg [1:0] r_bs;
always @(*) begin
    r_bs = 2'b00;
    if (w_phase_fetch) begin
        // instruction fetch is always an 8-bit read from the current PC byte.
        r_bs = 2'b01;
    end else if (w_phase_memop || w_phase_execute) begin
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

// address generation
reg [15:0] r_addr;
always @(*) begin
    if (i_reset) begin
        r_addr = 16'h0000;
    end else if (w_phase_fetch) begin
        // instruction fetch from pc
        r_addr = r_pc;
    end else if (w_phase_memop) begin
        if (w_memwrite) begin
            // store address is already on the stack during execute phase
            r_addr = T;
        end else if (r_ir[6:0] == OP_PUSH8) begin
            // byte immediate follows the opcode
            r_addr = r_pc + 1'd1;
        end else if (r_ir[6:0] == OP_PUSH) begin
            // 16-bit immediate follows the opcode
            r_addr = r_pc + 1'd1;
        end else begin
            // data memory access uses the stack address
            r_addr = T;
        end
    end else if (w_phase_execute) begin
        if (w_memwrite) begin
            r_addr = T;
        end else if (r_ir[6:0] == OP_FETCH || r_ir[6:0] == OP_BYTE_FETCH) begin
            r_addr = T;
        end else begin
            r_addr = r_pc;
        end
    end else begin
        r_addr = r_pc;
    end
end

assign o_addr = r_addr;
assign o_we = w_phase_execute && w_memwrite;
assign o_bs = r_bs;
assign o_dat = N;

endmodule
