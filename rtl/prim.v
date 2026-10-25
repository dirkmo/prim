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

localparam [15:0] ISR_ADDR = 16'h0004;

`include "opcodes.v"

// stack pointers
reg [DSS-1:0] r_dsp /* verilator public */;
reg [RSS-1:0] r_rsp /* verilator public */;

// registers
reg [15:0] r_pc /* verilator public */; // program counter
reg [15:0] T /* verilator public */; // top of dstack
reg [15:0] N /* verilator public */; // 2nd on dstack
reg [7:0] r_ir /* verilator public */; // instruction register
reg r_carry /* verilator public */;

// Stack storage is intentionally not reset; unused cells are undefined.
reg [15:0] r_dstack[0:2**DSS-1] /* verilator public */;
reg [15:0] r_rstack[0:2**RSS-1] /* verilator public */;
wire [15:0] R /* verilator public */ = r_rstack[r_rsp]; // top of rstack

//
wire [DSS-1:0] w_dsp_dec2_amt = {{(DSS-2){1'b0}}, 2'b10};

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
always @(*) begin
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
// Control-flow instructions ignore the return bit, as in the Python ISA.
wire w_return = r_ir[7] && (r_ir[6:0] != OP_CALL) &&
                (r_ir[6:0] != OP_JP) && (r_ir[6:0] != OP_JZ) &&
                (r_ir[6:0] != OP_INT);
wire w_rpush = (r_ir[6:0] == OP_CALL) || (r_ir[6:0] == OP_INT) ||
               (r_ir[6:0] == OP_TO_R);
wire w_rpop = (r_ir[6:0] == OP_FROM_R) || (r_ir[6:0] == OP_RDROP);
wire [RSS-1:0] w_rsp_inc1 = r_rsp + 1'b1;
wire [RSS-1:0] w_rsp_dec1 = r_rsp - 1'b1;
wire [RSS-1:0] w_rsp_dec2 = r_rsp - 2;
wire [RSS-1:0] w_rsp_next = w_rpush ? (w_return ? r_rsp : w_rsp_inc1) :
                          w_rpop ? (w_return ? w_rsp_dec2 : w_rsp_dec1) :
                          w_return ? w_rsp_dec1 : r_rsp;
// Return happens after the opcode: >R returns through T, R>/RDROP through
// the cell below the old R. Neither case needs an additional execution cycle.
wire [15:0] w_return_addr = (r_ir[6:0] == OP_TO_R) ? T :
                           w_rpop ? r_rstack[w_rsp_dec1] : R;
always @(*)
begin
    if (w_return) begin
        r_pc_next = w_return_addr;
    end else begin
        case (r_ir[6:0])
            OP_CALL: r_pc_next = T;
            OP_JP: r_pc_next = T;
            OP_JZ: r_pc_next = (N==16'h0) ? T : pc_plus_1;
            OP_INT: r_pc_next = ISR_ADDR;
            OP_PUSH8: r_pc_next = r_pc + 2;
            OP_PUSH:  r_pc_next = r_pc + 3;
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
// The array uses the same circular indices as Python: T at dsp, N at dsp-1.
wire [DSS-1:0] w_third_idx = r_dsp - 2;
wire [DSS-1:0] w_fourth_idx = r_dsp - 3;
wire [15:0] w_stack_third = r_dstack[w_third_idx];
wire [15:0] w_stack_fourth = r_dstack[w_fourth_idx];
reg [15:0] t_next, n_next;
reg [DSS-1:0] dsp_next;
always @(*) begin
    dsp_next = r_dsp;
    case (r_ir[6:0])
        OP_PUSH, OP_PUSH8, OP_DUP, OP_OVER, OP_CARRY, OP_FROM_R:
            dsp_next = w_dsp_inc1;
        OP_DROP, OP_NIP, OP_CALL, OP_JP, OP_AND, OP_OR, OP_XOR,
        OP_ADD, OP_SUB, OP_LTS, OP_LTU, OP_TO_R:
            dsp_next = w_dsp_dec1;
        OP_STORE, OP_BYTE_STORE, OP_JZ: dsp_next = w_dsp_dec2;
        default: ;
    endcase
end

// Cached top cells: compute the complete result before updating any storage.
always @(*) begin
    t_next = T;
    n_next = N;
    case (r_ir[6:0])
        OP_PUSH, OP_FETCH: t_next = r_mem_data;
        OP_PUSH8, OP_BYTE_FETCH: t_next = {8'h00, r_mem_data[7:0]};
        OP_SWAP, OP_OVER, OP_NROT, OP_DROP, OP_CALL, OP_JP, OP_TO_R:
            t_next = N;
        OP_ROT, OP_STORE, OP_BYTE_STORE, OP_JZ: t_next = w_stack_third;
        OP_FROM_R: t_next = R;
        OP_AND, OP_OR, OP_XOR, OP_NOT, OP_SR, OP_SRW, OP_SL, OP_SLW,
        OP_ADD, OP_SUB, OP_LTS, OP_LTU, OP_CARRY: t_next = r_alu[15:0];
        default: ;
    endcase
    case (r_ir[6:0])
        OP_PUSH, OP_PUSH8, OP_CARRY, OP_DUP, OP_SWAP, OP_OVER, OP_ROT, OP_FROM_R:
            n_next = T;
        OP_NIP, OP_NROT, OP_DROP, OP_CALL, OP_JP, OP_AND, OP_OR, OP_XOR,
        OP_ADD, OP_SUB, OP_LTS, OP_LTU, OP_TO_R:
            n_next = w_stack_third;
        OP_JZ, OP_STORE, OP_BYTE_STORE: n_next = w_stack_fourth;
        default: ;
    endcase
end

// Keep the cached top cells and the circular array coherent at retirement.
// Clearing consumed cells preserves Python's behavior across pointer wraparound.
always @(posedge i_clk) begin
    if (i_reset) begin
        T <= 16'h0;
        N <= 16'h0;
    end else if (w_phase_execute) begin
        T <= t_next;
        N <= n_next;
        if (dsp_next == w_dsp_dec1 || dsp_next == w_dsp_dec2)
            r_dstack[r_dsp] <= 16'h0;
        if (dsp_next == w_dsp_dec2)
            r_dstack[w_dsp_dec1] <= 16'h0;
        case (r_ir[6:0])
            OP_ROT: r_dstack[w_third_idx] <= N;
            OP_NROT: r_dstack[w_third_idx] <= T;
            default: ;
        endcase
        r_dstack[dsp_next] <= t_next;
        r_dstack[(dsp_next - 1'b1) & ((1 << DSS)-1)] <= n_next;
    end
end

// return stack
// Push first increments the circular pointer, then writes the new top.
// >R.RET consumes the pushed value immediately as the return address, so it
// needs no array write. Popped cells remain unused and are not cleared.
always @(posedge i_clk)
begin
    if (!i_reset && w_phase_execute && w_rpush && !w_return)
        r_rstack[w_rsp_inc1] <= (r_ir[6:0] == OP_TO_R) ? T : pc_plus_1;
end

// data stack pointer
always @(posedge i_clk) begin
    if (i_reset)
        r_dsp <= 'h0;
    else if (w_phase_execute)
        r_dsp <= dsp_next;
end

// return stack pointer
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_rsp <= 'h00;
    end else if (w_phase_execute) begin
        r_rsp <= w_rsp_next;
    end
end

// Carry for shifts is the last bit shifted out of the 16-bit operand.
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_carry <= 1'b0;
    end else if (w_phase_execute) begin
        casez (r_ir[6:0])
            OP_ADD: r_carry <= r_alu[16];
            OP_SUB: r_carry <= r_alu[16];
            OP_SR: r_carry <= T[0];
            OP_SRW: r_carry <= T[7];
            OP_SL: r_carry <= T[15];
            OP_SLW: r_carry <= T[8];
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
    end else if (w_phase_memop) begin
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
        if (w_pushop) begin
            r_addr = r_pc + 1'd1;
        end else begin
            // Both reads and writes complete in MEMWAIT before stack changes.
            r_addr = T;
        end
    end else begin
        r_addr = r_pc;
    end
end

assign o_addr = r_addr;
assign o_we = !i_reset && w_phase_memop && w_memwrite;
assign o_bs = r_bs;
assign o_dat = N;

endmodule
