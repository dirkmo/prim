module Prim(
    input i_reset,
    input i_clk,

    output [15:0] o_addr,
    output [15:0] o_dat,
    input  [15:0] i_dat,
    output [1:0]  o_bs, // byte select
    output        o_we,

    input         i_irq
);

parameter
    DSS /* verilator public */ = 4, // data stack size: 2^DSS
    RSS /* verilator public */ = 4; // return stack size: 2^RSS

parameter
    MEM_CYCLES_READ8 = 1,
    MEM_CYCLES_WRITE8 = 2,
    MEM_CYCLES_READ16_ALIGNED = 1,
    MEM_CYCLES_READ16_UNALIGNED = 2,
    MEM_CYCLES_WRITE16_ALIGNED = 2,
    MEM_CYCLES_WRITE16_UNALIGNED = 4;

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
wire [15:0] THIRD = r_dstack[r_dsp]; // third element

//
localparam
    PHASE_FETCH = 0,
    PHASE_EXECUTE = 1;

reg r_phase /* verilator public */;
wire w_fetch = (r_phase == PHASE_FETCH);
wire w_execute = (r_phase == PHASE_EXECUTE);

// memory access acknowledge
reg r_memack;

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
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_phase <= PHASE_FETCH;
    end else begin
        case (r_phase)
            PHASE_FETCH: if(r_memack) r_phase <= PHASE_EXECUTE;
            PHASE_EXECUTE: if (~w_memop || r_memack) r_phase <= PHASE_FETCH;
            default: r_phase <= PHASE_FETCH;
        endcase
    end
end

// Program counter r_pc
reg [15:0] r_pc_next;
wire [15:0] pc_plus_1 = r_pc + 1'd1;
always @(*)
begin
    casez (r_ir)
        {1'b0, OP_CALL}: r_pc_next = T;
        {1'b0, OP_JP}: r_pc_next = T;
        {1'b0, OP_JZ}: r_pc_next = (T==16'h0) ? N : pc_plus_1;
        {1'b0, OP_PUSH8}: if (r_ir[7]) r_pc_next = T; else r_pc_next = r_pc + 2;
        {1'b0, OP_PUSH}:  if (r_ir[7]) r_pc_next = T; else r_pc_next = r_pc + 3;
        {1'b1, 7'b???????}: r_pc_next = R;
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
    end else if (w_fetch && r_memack) begin
        r_ir <= i_dat[7:0];
        $display("pc: %04x, ir: %02x", r_pc, i_dat);
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
    end else if (w_execute) begin
        case (r_ir[6:0])
            OP_JP: T <= N;
            OP_JZ: T <= N;
            OP_PUSH8: begin T <= i_dat; $display("push8 %x", i_dat); end
            OP_PUSH: begin T <= i_dat; $display("push %x", i_dat); end
            OP_SWAP: T <= N;
            OP_ROT: T <= THIRD;
            OP_NROT: T <= N;
            default: begin T <= r_alu[15:0]; $display("alu: %x", r_alu); end
        endcase
    end
end

// 2nd on data stack
always @(posedge i_clk)
begin
    if (i_reset) begin
        N <= 16'h00;
    end else if (w_execute) begin
        case (r_ir[6:0])
            OP_AND: r_dsp <= r_dsp - 1;
            OP_OR: N <= THIRD;
            OP_XOR: N <= THIRD;
            OP_ADD: N <= THIRD;
            OP_SUB: N <= THIRD;
            OP_LTS: N <= THIRD;
            OP_LTU: N <= THIRD;
            OP_PUSH8: N <= T;
            OP_PUSH: N <= T;
            default: ;
        endcase
    end
end

// top of return stack
always @(posedge i_clk)
begin
    if (w_execute) begin
        case (r_ir[7:0])
            {1'b0, OP_CALL}: r_rstack[r_rsp] <= r_pc;
            {1'b0, OP_INT}: r_rstack[r_rsp] <= r_pc;
            {1'b0, OP_TO_R}: r_rstack[r_rsp] <= T;
            default: ;
        endcase
    end
end

// data stack pointer
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_dsp <= 'h00;
    end else if (w_execute) begin
        case (r_ir[6:0])
            OP_AND: r_dsp <= r_dsp - 1;
            OP_OR: r_dsp <= r_dsp - 1;
            OP_XOR: r_dsp <= r_dsp - 1;
            OP_ADD: r_dsp <= r_dsp - 1;
            OP_SUB: r_dsp <= r_dsp - 1;
            OP_LTS: r_dsp <= r_dsp - 1;
            OP_LTU: r_dsp <= r_dsp - 1;
            OP_PUSH8: r_dsp <= r_dsp + 1;
            OP_PUSH: r_dsp <= r_dsp + 1;
            default: ;
        endcase
    end
end

// return stack pointer
always @(posedge i_clk)
begin
    if (i_reset) begin
        r_rsp <= 'h00;
    end else if (w_execute) begin
        casez (r_ir[7:0])
            {1'b0, OP_CALL}: r_rsp <= r_rsp + 1;
            {1'b0, OP_INT}: r_rsp <= r_rsp + 1;
            {1'b0, OP_TO_R}: r_rsp <= r_rsp + 1;
            {1'b0, OP_FROM_R}: r_rsp <= r_rsp - 1;
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
    end else if (w_execute) begin
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
wire w_pushop = (r_ir[6:0] == OP_PUSH) | (r_ir[6:0] == OP_PUSH8);
wire w_memop = w_memop8 || w_memop16;

reg [2:0] r_memaccesstype;
localparam
    MEMACCESS_NONE = 0,
    MEMACCESS_READ8 = 1,
    MEMACCESS_WRITE8 = 2,
    MEMACCESS_READ16_ALIGNED = 3,
    MEMACCESS_READ16_UNALIGNED = 4,
    MEMACCESS_WRITE16_ALIGNED = 5,
    MEMACCESS_WRITE16_UNALIGNED = 6;

reg [2:0] r_memdelay;
always @(posedge i_clk) begin
    if (i_reset) begin
        r_memdelay <= 'h0;
        r_memack = 'h0;
    end else begin
        r_memdelay <= r_memack ? 'h0 : (r_memdelay + 'h1);
        case (r_memaccesstype)
            MEMACCESS_READ8: r_memack = (r_memdelay == MEM_CYCLES_READ8);
            MEMACCESS_WRITE8: r_memack = (r_memdelay == MEM_CYCLES_WRITE8);
            MEMACCESS_READ16_ALIGNED: r_memack = (r_memdelay == MEM_CYCLES_READ16_ALIGNED);
            MEMACCESS_READ16_UNALIGNED: r_memack = (r_memdelay == MEM_CYCLES_READ16_UNALIGNED);
            MEMACCESS_WRITE16_ALIGNED: r_memack = (r_memdelay == MEM_CYCLES_WRITE16_ALIGNED);
            MEMACCESS_WRITE16_UNALIGNED: r_memack = (r_memdelay == MEM_CYCLES_WRITE16_ALIGNED);
            default: r_memack = 0;
        endcase
    end
end

always @(*) begin
    casez ({w_memwrite, w_memop16, o_addr[0]})
        {1'b0, 1'b0, 1'b?}: r_memaccesstype = MEMACCESS_READ8;
        {1'b0, 1'b1, 1'b0}: r_memaccesstype = MEMACCESS_READ16_ALIGNED;
        {1'b0, 1'b1, 1'b1}: r_memaccesstype = MEMACCESS_READ16_UNALIGNED;
        {1'b1, 1'b1, 1'b0}: r_memaccesstype = MEMACCESS_WRITE16_ALIGNED;
        {1'b1, 1'b1, 1'b1}: r_memaccesstype = MEMACCESS_WRITE16_UNALIGNED;
        default: r_memaccesstype = MEMACCESS_NONE;
    endcase
end

// byte select
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

// address generation
reg [15:0] r_addr;
always @(*) begin
    if (w_fetch) begin
        r_addr = r_pc;
    end else begin // w_execute
        if (w_pushop) begin
            r_addr = pc_plus_1;
        end else begin
            r_addr = T;
        end
    end
end

assign o_addr = r_addr;
assign o_we = w_execute && w_memwrite;
assign o_bs = r_bs;
assign o_dat = N;

endmodule
